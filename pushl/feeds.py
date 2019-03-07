""" Functionality for handling feeds """

import logging
import collections
import hashlib

import feedparser

from . import caching

LOGGER = logging.getLogger(__name__)
SCHEMA_VERSION = 1


class Feed:
    """ Encapsulates stuff on feeds """

    def __init__(self, request, text):
        """ Given a request object and retrieved text, parse out the feed """
        md5 = hashlib.md5(text.encode('utf-8'))
        self.digest = md5.digest()

        self.url = str(request.url)
        self.caching = caching.make_headers(request.headers)
        self.feed = feedparser.parse(text)
        self.status = request.status

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
    def links(self):
        """ Given a parsed feed, return the links based on their `rel` attribute """
        rels = collections.defaultdict(list)
        for link in self.feed.feed.links:
            rels[link.rel].append(link.href)
        return rels

    @property
    def is_archive(self):
        """ Given a parsed feed, returns True if this is an archive feed """

        ns_prefix = self.archive_namespace
        if ns_prefix:
            if ns_prefix + '_archive' in self.feed:
                # This is declared to be an archive view
                return True
            if ns_prefix + '_current' in self.feed:
                # This is declared to be the current view
                return False

        # Either we don't have the namespace, or the view wasn't declared.
        rels = self.links
        return ('current' in rels and
                'self' in rels and
                rels['self'] != rels['current'])

    async def update_websub(self, config, hub):
        """ Update WebSub hub to know about this feed """
        try:
            LOGGER.info("WebSub: Notifying %s of %s", hub, self.url)
            async with config.session.post(
                    hub, {
                        'hub.mode': 'publish',
                        'hub.url': self.url
                    }) as request:
                if 200 <= request.status < 300:
                    LOGGER.info("%s: WebSub notification sent to %s",
                                self.url, hub)
                else:
                    LOGGER.warning("%s: Hub %s returned status code %s: %s", self.url, hub,
                                   request.status, await request.text())
        except Exception as err:  # pylint:disable=broad-except
            LOGGER.warning("WebSub %s: got %s: %s",
                           hub, err.__class__.__name__, err)


async def get_feed(config, url):
    """ Get a feed

    Arguments:

    config -- the configuration
    url -- The URL of the feed

    retval -- a tuple of feed,previous_version,changed
    """

    previous = config.cache.get(
        'feed', url, schema_version=SCHEMA_VERSION) if config.cache else None

    headers = previous.caching if previous else None

    try:
        async with config.session.get(url, headers=headers) as request:
            if not 200 <= request.status < 300:
                return None, previous, False

            if request.status == 304:
                LOGGER.debug("%s: Reusing cached version", url)
                return previous, previous, False

            text = (await request.read()).decode(request.get_encoding(), 'ignore')
            current = Feed(request, text)
    except Exception as err:  # pylint:disable=broad-except
        LOGGER.warning("Feed %s: Got %s: %s",
                       url, err.__class__.__name__, err)
        return None, previous, False

    if config.cache:
        LOGGER.debug("%s: Saving to cache", url)
        config.cache.set('feed', url, current)

    LOGGER.debug("%s: Returning new content", url)
    return current, previous, (not previous
                               or current.digest != previous.digest
                               or current.status != previous.status)
