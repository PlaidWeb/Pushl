""" Functionality for handling feeds """

import collections
import hashlib
import logging

import feedparser

from . import caching, utils

LOGGER = logging.getLogger(__name__)
SCHEMA_VERSION = 2


class Feed:
    """ Encapsulates stuff on feeds """

    def __init__(self, request):
        """ Given a request object and retrieved text, parse out the feed """
        text = request.text
        md5 = hashlib.md5(text.encode('utf-8'))
        self.digest = md5.digest()

        self.url = str(request.url)
        self.caching = caching.make_headers(request.headers)
        self.feed = feedparser.parse(text)
        self.status = request.status
        self.links = self.feed.feed.links

        self.schema = SCHEMA_VERSION

    @property
    def archive_namespace(self):
        """ Returns the known namespace of the RFC5005 extension, if any """
        try:
            for ns_prefix, url in self.feed.namespaces.items():
                if url == 'http://purl.org/syndication/history/1.0':
                    return ns_prefix
        except AttributeError:
            pass
        return None

    @property
    def entry_links(self):
        """ Given a parsed feed, return the links to its entries, including ones
        which disappeared (as a quick-and-dirty way to support deletions)
        """
        return {entry['link'] for entry in self.feed.entries if entry and entry.get('link')}

    @property
    def is_archive(self):
        """ Given a parsed feed, returns True if this is an archive feed """

        ns_prefix = self.archive_namespace
        if ns_prefix:
            if ns_prefix + '_archive' in self.feed.feed:
                # This is declared to be an archive view
                return True
            if ns_prefix + '_current' in self.feed.feed:
                # This is declared to be the current view
                return False

        # Either we don't have the namespace, or the view wasn't declared.
        rels = collections.defaultdict(list)
        for link in self.feed.feed.links:
            rels[link.rel].append(link.href)

        return ('current' in rels and
                ('self' not in rels or
                 rels['self'] != rels['current']))


async def get_feed(config, url):
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

    LOGGER.debug("++WAIT: request get %s", url)
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
