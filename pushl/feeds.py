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
SCHEMA_VERSION = 4


class Feed:
    """ Encapsulates stuff on feeds """
    # pylint:disable=too-many-instance-attributes

    def __init__(self, request: utils.RequestResult):
        """ Given a request object and retrieved text, parse out the feed """
        text = request.text
        md5 = hashlib.md5(text.encode('utf-8'))
        self.digest = md5.digest()

        self.url = str(request.url)
        self.caching = caching.make_headers(request.headers)

        self.feed = feedparser.parse(text)
        if 'bozo_exception' in self.feed:
            # feedparser couldn't handle this, so maybe it's mf2
            self.mf2 = mf2py.parse(text)
        else:
            self.mf2 = None

        self.status = request.status
        self.links: typing.DefaultDict[str, typing.Set[str]] = collections.defaultdict(set)

        try:
            for link in self.feed.feed.links:
                # conveniently this also contains the rel links from HTML
                # documents, so no need to handle the mf2 version (if any)
                href = link.get('href')
                rel = link.get('rel')

                if rel and href:
                    self.links[rel].add(href)
        except (AttributeError, KeyError):
            pass

        self.schema = SCHEMA_VERSION

    @property
    def archive_namespace(self) -> typing.Optional[str]:
        """ Returns the known namespace of the RFC5005 extension, if any """
        try:
            for ns_prefix, url in self.feed.namespaces.items():
                if url == 'http://purl.org/syndication/history/1.0':
                    return ns_prefix
        except AttributeError:
            pass
        return None

    @property
    def entry_links(self) -> typing.Set[str]:
        """ Given a parsed feed, return the links to its entries """
        entries = {urllib.parse.urljoin(self.url, entry['link'])
                   for entry in self.feed.entries
                   if entry and entry.get('link')}

        def consume_mf2(entries, items):
            for item in items:
                if ('type' in item and 'h-entry' in item['type']
                        and 'properties' in item and 'url' in item['properties']):
                    print(self.url, item['properties'])
                    entries |= set(urllib.parse.urljoin(self.url, url)
                                   for url in item['properties']['url'])
                if 'children' in item:
                    consume_mf2(entries, item['children'])

        if self.mf2:
            consume_mf2(entries, self.mf2['items'])

        return entries

    @property
    def is_archive(self) -> bool:
        """ Given a parsed feed, returns True if this is an archive feed """

        ns_prefix = self.archive_namespace
        if ns_prefix:
            if ns_prefix + '_archive' in self.feed.feed:
                # This is declared to be an archive view
                return True
            if ns_prefix + '_current' in self.feed.feed:
                # This is declared to be the current view
                return False

        # Either we don't have the namespace, or the view wasn't declared, so
        # return whether there's a rel=current that doesn't match rel=self
        return (bool(self.links['current']) and
                self.links['self'] != self.links['current'])

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

    headers = previous.caching if previous else None

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
