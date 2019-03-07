""" Functionality to add push-ish notifications to feed-based sites """

import queue
import logging
import asyncio

from . import feeds, caching, entries, webmentions

LOGGER = logging.getLogger("pushl")


class Pushl:
    """ Top-level process controller """
    # pylint:disable=too-many-instance-attributes

    def __init__(self, session, args):
        """ Set up the process worker """
        self.args = args
        self.cache = caching.Cache(args.cache_dir) if args.cache_dir else None
        self.pending = queue.Queue()
        self.rel_whitelist = args.rel_whitelist.split(
            ',') if args.rel_whitelist else None
        self.rel_blacklist = args.rel_blacklist.split(
            ',') if args.rel_blacklist else None

        self.processed_feeds = set()
        self.processed_entries = set()
        self.processed_mentions = set()

        self.num_submitted = 0
        self.num_finished = 0

        self.session = session

    async def process_feed(self, url):
        """ process a feed """

        if url in self.processed_feeds:
            LOGGER.debug("Skipping already processed feed %s", url)
            return
        self.processed_feeds.add(url)

        LOGGER.debug("process feed %s", url)
        feed, previous, updated = await feeds.get_feed(self, url)
        if updated:
            LOGGER.info("Feed %s has been updated", url)

        pending = []

        if not feed:
            return

        try:
            for link in feed.links:
                #  RFC5005 archive links
                if self.args.archive and link.get('rel') in ('prev-archive',
                                                             'next-archive',
                                                             'prev-page',
                                                             'next-page'):
                    LOGGER.info("Found archive link %s", link)
                    pending.append(self.process_feed(link['href']))

                # WebSub notification
                if updated and link.get('rel') == 'hub' and not feed.is_archive:
                    LOGGER.info("Found WebSub hub %s", link)
                    pending.append(feed.update_websub(self, link['href']))
        except (AttributeError, KeyError):
            LOGGER.debug("Feed %s has no links", url)

        # Schedule the entries
        items = set(feed.entry_links)
        if previous:
            items |= set(previous.entry_links)
        for entry in items:
            pending.append(self.process_entry(entry))

        if pending:
            await asyncio.wait(pending)

    async def process_entry(self, url):
        """ process an entry """

        if url in self.processed_entries:
            LOGGER.debug("Skipping already processed entry %s", url)
            return
        self.processed_entries.add(url)

        LOGGER.debug("process entry %s", url)
        entry, previous, updated = await entries.get_entry(self, url)

        pending = []

        if updated:
            # get the webmention targets
            links = entry.get_targets(self)
            if previous:
                # Only bother with links that changed from the last time
                links = links ^ previous.get_targets(self)

            for link in links:
                pending.append(self.send_webmention(entry, link))

            if self.args.recurse:
                for feed in entry.feeds:
                    pending.append(self.process_feed(feed))

        if pending:
            await asyncio.wait(pending)

    async def send_webmention(self, entry, url):
        """ send a webmention from an entry to a URL """

        if (entry.url, url) in self.processed_mentions:
            LOGGER.debug(
                "Skipping already processed mention %s -> %s", entry.url, url)
        self.processed_mentions.add((entry.url, url))

        target = await webmentions.get_target(self, url)
        if target:
            LOGGER.debug("Sending webmention %s -> %s", entry.url, url)
            await target.send(self, entry)
