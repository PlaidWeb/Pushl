""" Functionality for handling feeds """

import logging
import collections
import itertools

import feedparser

from .common import session

LOGGER = logging.getLogger(__name__)


def get_feed(url, cache=None):
    """ Get the current parsed feed

    Arguments:

    url -- The URL of the feed
    cache -- a caching.Cache object (optional)

    retval -- a tuple of feed,previous_version,changed
    """

    cached = cache.get('feed', url) if cache else None

    current = feedparser.parse(
        url,
        etag=cached.get('etag') if cached else None,
        modified=cached.get('modified') if cached else None)

    if current.bozo:
        LOGGER.error("%s: Got error %s", url, current.bozo_exception)
        return current, cached, False

    if current.status == 304:
        LOGGER.debug("%s: Reusing cached version", url)
        return cached, cached, False

    if cache:
        LOGGER.debug("%s: Saving to cache", url)
        cache.set('feed', url, current)

    LOGGER.debug("%s: Returning new content", url)
    return current, cached, True


def get_archive_namespace(feed):
    """ Returns the known namespace of the RFC5005 extension, if any """
    try:
        for ns_prefix, url in feed.namespaces.items():
            if url == 'http://purl.org/syndication/history/1.0':
                return ns_prefix
    except AttributeError:
        pass
    return None


def get_entry_links(feed, previous=None):
    """ Given a parsed feed, return the links to its entries, including ones
    which disappeared (as a quick-and-dirty way to support deletions)
    """
    entries = feed.entries
    if previous:
        entries = itertools.chain(entries, previous.entries)
    return {entry['link'] for entry in entries if entry and entry.get('link')}


def get_links(feed):
    """ Given a parsed feed, return the links based on their `rel` attribute """
    rels = collections.defaultdict(list)
    for link in feed.feed.links:
        rels[link.rel].append(link.href)
    return rels


def is_archive(feed):
    """ Given a parsed feed, returns True if this is an archive feed """

    ns_prefix = get_archive_namespace(feed)
    if ns_prefix:
        if ns_prefix + '_archive' in feed.feed:
            # This is declared to be an archive view
            return True
        if ns_prefix + '_current' in feed.feed:
            # This is declared to be the current view
            return False

    # Either we don't have the namespace, or the view wasn't declared.
    rels = get_links(feed)
    return ('current' in rels and
            'self' in rels and
            rels['self'] != rels['current'])


def update_websub(url, hub):
    """ Given a parsed feed, send a WebSub update

    Arguments:

    url -- the feed URL
    hub -- the hub URL
    """

    LOGGER.debug("Sending update notification for %s to %s", url, hub)
    request = session.post(hub, {'hub.mode': 'publish', 'hub.url': url})
    if 200 <= request.status_code < 300:
        LOGGER.info("%s: WebSub notification sent to %s", url, hub)
    else:
        LOGGER.warning("%s: Hub %s returned status code %s: %s", url, hub,
                       request.status_code, request.text)
