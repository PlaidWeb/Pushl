""" Functionality for handling feeds """

import collections
import hashlib
import itertools
import logging
import typing
import urllib.parse

import feedparser
import mf2py

from . import caching, utils

LOGGER = logging.getLogger(__name__)
SCHEMA_VERSION = 5

ACCEPT_HEADER = \
    'application/atom+xml, application/rss+xml, application/rdf+xml;q=0.9,'\
    'application/xml;q=0.8, text/xml;q=0.8, text/html;q=0.5,'\
    '*/*;q=0.1'


class Feed:
    """ Encapsulates stuff on feeds """
    # pylint:disable=too-many-instance-attributes,too-few-public-methods

    def __init__(self, request: utils.RequestResult):
        """ Given a request object and retrieved text, parse out the feed """
        text = request.text
        self.digest = hashlib.md5(text.encode('utf-8')).digest()

        self.url = str(request.url)
        self.caching = caching.make_headers(request.headers)

        self.is_archive = None

        feed = feedparser.parse(text)
        self.entry_links, self.links = self._consume_feed(feed)

        if 'bozo_exception' in feed:
            LOGGER.warning("Feed %s: got error '%s' on line %d", self.url,
                           feed.bozo_exception.getMessage(),
                           feed.bozo_exception.getLineNumber())

        if not self.entry_links:
            # feedparser couldn't find any entries, so maybe it's an mf2 document
            LOGGER.debug("%s: Found no entries, retrying as mf2", self.url)
            self._consume_mf2(mf2py.parse(text).get('items', []), self.entry_links)

        LOGGER.debug("%s: Found %d entries", self.url, len(self.entry_links))

        try:
            for ns_prefix, url in feed.namespaces.items():
                if url == 'http://purl.org/syndication/history/1.0':
                    if ns_prefix + '_archive' in feed.feed:
                        self.is_archive = True
                        break
                    if ns_prefix + '_current' in feed.feed:
                        self.is_archive = False
                        break
        except AttributeError:
            pass

        if self.is_archive is None:
            # We haven't found an archive namespace prefix, so see if there's
            # a 'current' which mismatches 'self' (if any)
            self.is_archive = ('current' in self.links and
                               self.links.get('self') != self.links['current'])

        self.status = request.status
        self.schema = SCHEMA_VERSION

    def _consume_feed(self, feed) -> typing.Tuple[typing.Set[str],
                                                  typing.Dict[str, typing.Set[str]]]:
        """ Given a parsed feed, return the links to its entries and the
        rel-links for the feed """
        entries: typing.Set[str] = set()
        for attr in ('link', 'comments'):
            entries |= {
                urllib.parse.urldefrag(
                    urllib.parse.urljoin(self.url, entry[attr])).url
                for entry in feed['entries']
                if entry and entry.get(attr)
            }

        feed_links: typing.DefaultDict[str,
                                       typing.Set[str]] = collections.defaultdict(set)
        if 'feed' in feed and 'links' in feed.feed:
            for link in feed.feed.links:
                # conveniently this also contains the rel links from HTML
                # documents, so no need to handle the mf2 version (if any)
                href = link.get('href')
                rel = link.get('rel')

                if rel and href:
                    feed_links[rel].add(href)

        return entries, feed_links

    def _consume_mf2(self, items, entries: typing.Set[str]):
        """ Given a parsed mf2 feed, return the links to its entries """
        for item in items:
            if ('h-entry' in item.get('type', []) and
                    'properties' in item and 'url' in item['properties']):
                for url in item['properties']['url']:
                    entries.add(urllib.parse.urljoin(self.url, url))
            if 'children' in item:
                self._consume_mf2(item['children'], entries)

    @property
    def canonical(self) -> str:
        """ Return the canonical URL for this feed """
        for href in itertools.chain(self.links['canonical'], self.links['self']):
            return href

        return self.url


async def get_feed(config, url: str) -> typing.Tuple[typing.Optional[Feed],
                                                     typing.Optional[Feed],
                                                     bool]:
    """ Get a feed

    Arguments:

    config -- the configuration
    url -- The URL of the feed

    retval -- a tuple of feed,previous_version,changed
    """

    LOGGER.debug("++WAIT: cache get feed %s", url)
    previous = config.cache.get(
        'feed', url, schema_version=SCHEMA_VERSION) if config.cache else None
    LOGGER.debug("++DONE: cache get feed %s", url)

    headers = {'Accept': ACCEPT_HEADER}
    if previous:
        headers.update(previous.caching)

    LOGGER.debug("++WAIT: request get %s %s)", url, headers)
    request = await utils.retry_get(config, url, headers=headers)
    LOGGER.debug("++DONE: request get %s", url)
    if not request or not request.success:
        LOGGER.error("Could not get feed %s: %d",
                     url,
                     request.status if request else -1)
        return None, previous, False

    if request.cached:
        LOGGER.debug("%s: Reusing cached version", url)
        return previous, previous, False

    current = Feed(request)

    if config.cache:
        LOGGER.debug("%s: Saving to cache", url)
        LOGGER.debug("++WAIT: cache set feed %s", url)
        config.cache.set('feed', url, current)
        LOGGER.debug("++DONE: cache set feed %s", url)

    LOGGER.debug("%s: Returning new content", url)
    return current, previous, (not previous
                               or current.digest != previous.digest
                               or current.status != previous.status)
