""" Functionality for handling feeds """

import logging
import collections
import itertools

import feedparser
import requests

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
    rels = get_links(feed)

    return ('fh_archive' in feed.feed or
            ('current' in rels and
             'self' in rels and
             rels['self'] != rels['current']
             ))


def update_websub(url, hub):
    """ Given a parsed feed, send a WebSub update

    Arguments:

    url -- the feed URL
    hub -- the hub URL
    """

    LOGGER.debug("Sending update notification for %s to %s", url, hub)
    request = requests.post(hub, {'hub.mode': 'publish', 'hub.url': url})
    if 200 <= request.status_code < 300:
        LOGGER.info("%s: WebSub notification sent to %s", url, hub)
    else:
        LOGGER.warning("%s: Hub %s returned status code %s: %s", url, hub,
                       request.status_code, request.text)
