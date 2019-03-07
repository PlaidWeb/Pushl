""" Functions for handling entries """

import logging
import urllib.parse
import hashlib

from bs4 import BeautifulSoup
import aiohttp

from . import caching

LOGGER = logging.getLogger(__name__)
SCHEMA_VERSION = 2


class Entry:
    """ Encapsulates a scanned entry """
    # pylint:disable=too-few-public-methods

    def __init__(self, url, request, text):
        """ Build an Entry from a completed request; requires that the text already be retrieved """
        md5 = hashlib.md5(text.encode('utf-8'))
        self.digest = md5.digest()

        self.url = str(request.url)  # the canonical, final URL
        self.original_url = url  # the original request URL
        self.status = request.status
        self.headers = request.headers

        if 200 <= self.status < 300:
            """ We have new content, so parse out the relevant stuff """
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
        else:
            self._targets = []
            self.feeds = []

        self.schema = SCHEMA_VERSION

    @staticmethod
    def _get_articles(soup):
        return (soup.find_all(class_="h-entry")
                or soup.find_all("article")
                or soup.find_all(class_="entry")
                or soup)

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
        target = urllib.parse.urlparse(href).netloc.lower()
        if not target:
            return False

        origin = urllib.parse.urlparse(self.url).netloc.lower()
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

    headers = caching.make_headers(previous)

    async with config.session.get(url, headers=headers) as request:
        if 200 <= request.status < 300:
            text = await request.text()
        else:
            text = None

        current = Entry(url, request, text)

    # Cache hit
    if current.status == 304:
        return previous, previous, False

    # Content updated
    if 200 <= current.status < 300 or current.status == 410:
        if config.cache:
            config.cache.set('entry', url, current)

    return current, previous, (not previous
                               or previous.digest != current.digest
                               or previous.status != current.status)


def get_feeds(entry):
    """ Given an Entry object, return all of the discovered feeds """
    soup = entry.soup
    return [urllib.parse.urljoin(entry.url, link.attrs['href'])
            for link in soup.find_all('link', rel='alternate')
            if _is_feed(link)]


def _is_feed(link):
    return ('href' in link.attrs
            and link.attrs.get('type') in ('application/rss+xml',
                                           'application/atom+xml'))
