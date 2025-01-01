""" Functions for handling entries """

import hashlib
import logging
import typing
import urllib.parse

from bs4 import BeautifulSoup

from . import caching, utils

LOGGER = logging.getLogger(__name__)
SCHEMA_VERSION = 3

ACCEPT_HEADER = 'text/html, application/xhtml+xml, */*;q=0.1'


class Entry:
    """ Encapsulates a scanned entry """
    # pylint:disable=too-few-public-methods,too-many-instance-attributes

    def __init__(self, request: utils.RequestResult):
        """ Build an Entry from a completed request """
        text = request.text
        self.digest = hashlib.md5(text.encode('utf-8')).digest()

        self.url = str(request.url)  # the resolved URL
        self.status = request.status
        self.caching = caching.make_headers(request.headers)

        if 200 <= self.status < 300:
            # We have new content, so parse out the relevant stuff
            soup = BeautifulSoup(text, 'html.parser')
            articles = self._get_articles(soup)

            self._targets: typing.List[typing.Dict] = []
            for node in articles:
                self._targets += [link.attrs
                                  for link in node.find_all('a', href=True)]

            self.feeds = [urllib.parse.urljoin(self.url, link.attrs['href'])
                          for link
                          in soup.find_all('link',
                                           rel="alternate",
                                           href=True,
                                           type={'text/xml',
                                                 'application/rdf+xml',
                                                 'application/rss+xml',
                                                 'application/atom+xml',
                                                 'application/xml'}
                                           )]
            self.feeds += [urllib.parse.urljoin(self.url, link.attrs['href'])
                           for link
                           in soup.find_all('link', rel="hub")]

            self.hubs = [link.attrs['href']
                         for link in soup.find_all('link', rel='hub', href=True)]
            if 'hub' in request.links:
                self.hubs.append(request.links['hub']['url'])

            # Use the canonical URL if available
            for link in soup.find_all('link', rel='canonical', href=True):
                self.url = urllib.parse.urljoin(self.url, link.attrs['href'])

        else:
            self._targets = []
            self.feeds = []
            self.hubs = []

        self.schema = SCHEMA_VERSION

    @staticmethod
    def _get_articles(soup: BeautifulSoup) -> typing.List[BeautifulSoup]:
        return (soup.find_all(class_="h-entry")
                or soup.find_all("article")
                or soup.find_all(class_="entry")
                or [soup])

    @staticmethod
    def _check_rel(attrs: typing.Dict,
                   rel_include: typing.Optional[typing.List[str]],
                   rel_exclude: typing.Optional[typing.List[str]]) -> bool:
        """ Check a link's relations against the include or exclude.

        First, this will reject based on exclude.

        Next, if there is a include, there must be at least one rel that matches.
        To explicitly allow links without a rel you can add None to the include
        (e.g. ['in-reply-to',None])
        """

        rels = attrs.get('rel', [None])

        if rel_exclude:
            # Never return True for a link whose rel appears in the exclusion list
            for rel in rels:
                if rel in rel_exclude:
                    return False

        if rel_include:
            # If there is a inclusion list for rels, only return true for a rel that
            # appears in it
            for rel in rels:
                if rel in rel_include:
                    return True
            # If there is a include and we don't match, then reject
            return False

        return True

    def _domain_differs(self, href: str) -> bool:
        """ Check that a link is not on the same domain as the source URL """
        target = utils.get_domain(href)
        if not target:
            return False

        origin = utils.get_domain(self.url)
        return target != origin

    def get_targets(self, config) -> typing.Set[typing.Tuple[str, str]]:
        """ Given an Entry object, return all of the outgoing links, as a tuple
        of (resolved_url, original_href). """

        hrefs = [attrs['href']
                 for attrs in self._targets
                 if 'href' in attrs and self._check_rel(attrs,
                                                        config.rel_include,
                                                        config.rel_exclude)]

        return {(urllib.parse.urljoin(self.url, href), href)
                for href in hrefs
                if config.args.self_pings or self._domain_differs(href)}


async def get_entry(config,
                    url: str,
                    cache_ns: str) -> typing.Tuple[typing.Optional[Entry],
                                                   typing.Optional[Entry],
                                                   bool]:
    """ Given an entry URL, return the entry

    Arguments:

    config -- the configuration
    url -- the URL of the entry
    cache_ns -- the cache namespace to use

    Returns: 3-tuple of (current, previous, updated) """

    previous = config.cache.get(
        cache_ns, url,
        schema_version=SCHEMA_VERSION) if config.cache else None

    LOGGER.debug("cache=%s previous=%s previous.caching=%s",
                 config.cache,
                 previous,
                 previous.caching if previous else None)

    headers = {'Accept': ACCEPT_HEADER}
    if previous:
        headers.update(previous.caching)

    LOGGER.debug("+++WAIT: request get %s %s", url, headers)
    request = await utils.retry_get(config, url, headers=headers)
    LOGGER.debug("---WAIT: request get %s", url)

    if not request or not request.success:
        LOGGER.error("Could not get entry %s: %d", url,
                     request.status if request else -1)
        return None, previous, False

    # cache hit
    if request.cached:
        LOGGER.debug("%s: entry unchanged", url)
        return previous, previous, False

    current = Entry(request)

    # Content updated
    if config.cache:
        config.cache.set(cache_ns, url, current)

    return current, previous, (not previous
                               or previous.digest != current.digest
                               or previous.status != current.status)
