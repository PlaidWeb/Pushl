""" Functions for handling entries """

import hashlib
import logging
import urllib.parse

from bs4 import BeautifulSoup

from . import caching, utils

LOGGER = logging.getLogger(__name__)
SCHEMA_VERSION = 3


class Entry:
    """ Encapsulates a scanned entry """
    # pylint:disable=too-few-public-methods,too-many-instance-attributes

    def __init__(self, request):
        """ Build an Entry from a completed request """
        text = request.text

        md5 = hashlib.md5(text.encode('utf-8'))
        self.digest = md5.digest()

        self.url = str(request.url)  # the canonical, final URL
        self.status = request.status
        self.caching = caching.make_headers(request.headers)

        if 200 <= self.status < 300:
            # We have new content, so parse out the relevant stuff
            soup = BeautifulSoup(text, 'html.parser')
            articles = self._get_articles(soup)

            self._targets = []
            for node in articles:
                self._targets += [link.attrs
                                  for link in node.find_all('a')
                                  if 'href' in link.attrs]

            self.feeds = [urllib.parse.urljoin(self.url, link.attrs['href'])
                          for link in soup.find_all('link')
                          if 'href' in link.attrs
                          and 'type' in link.attrs
                          and link.attrs['type'] in ('application/rss.xml',
                                                     'application/atom+xml')]

            self.hubs = [link.attrs['href'] for link in soup.find_all('link', rel='hub')]
            if 'hub' in request.links:
                self.hubs.append(request.links['hub']['url'])

        else:
            self._targets = []
            self.feeds = []
            self.hubs = []

        self.schema = SCHEMA_VERSION

    @staticmethod
    def _get_articles(soup):
        return (soup.find_all(class_="h-entry")
                or soup.find_all("article")
                or soup.find_all(class_="entry")
                or [soup])

    @staticmethod
    def _check_rel(attrs, rel_whitelist, rel_blacklist):
        """ Check a link's relations against the whitelist or blacklist.

        First, this will reject based on blacklist.

        Next, if there is a whitelist, there must be at least one rel that matches.
        To explicitly allow links without a rel you can add None to the whitelist
        (e.g. ['in-reply-to',None])
        """

        rels = attrs.get('rel', [None])

        if rel_blacklist:
            # Never return True for a link whose rel appears in the blacklist
            for rel in rels:
                if rel in rel_blacklist:
                    return False

        if rel_whitelist:
            # If there is a whitelist for rels, only return true for a rel that
            # appears in it
            for rel in rels:
                if rel in rel_whitelist:
                    return True
            # If there is a whitelist and we don't match, then reject
            return False

        return True

    def _domain_differs(self, href):
        """ Check that a link is not on the same domain as the source URL """
        target = utils.get_domain(href)
        if not target:
            return False

        origin = utils.get_domain(self.url)
        return target != origin

    def get_targets(self, config):
        """ Given an Entry object, return all of the outgoing links. """

        return {urllib.parse.urljoin(self.url, attrs['href'])
                for attrs in self._targets
                if self._check_rel(attrs, config.rel_whitelist, config.rel_blacklist)
                and self._domain_differs(attrs['href'])}


async def get_entry(config, url):
    """ Given an entry URL, return the entry

    Arguments:

    config -- the configuration
    url -- the URL of the entry

    Returns: 3-tuple of (current, previous, updated) """

    previous = config.cache.get(
        'entry', url,
        schema_version=SCHEMA_VERSION) if config.cache else None

    headers = previous.caching if previous else None

    request = await utils.retry_get(config, url, headers=headers)
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
        config.cache.set('entry', url, current)

    return current, previous, (not previous
                               or previous.digest != current.digest
                               or previous.status != current.status)
