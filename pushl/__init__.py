""" Functionality to add push-ish notifications to feed-based sites """

import logging
import asyncio

from . import feeds, caching, entries, webmentions, utils

LOGGER = logging.getLogger("pushl")


class Pushl:
    """ Top-level process controller """
    # pylint:disable=too-many-instance-attributes

    def __init__(self, session, args):
        """ Set up the process worker """
        self.args = args
        self.cache = caching.Cache(args.cache_dir) if args.cache_dir else None
        self.rel_whitelist = args.rel_whitelist.split(
            ',') if args.rel_whitelist else None
        self.rel_blacklist = args.rel_blacklist.split(
            ',') if args.rel_blacklist else None

        self._processed_feeds = set()
        self._processed_entries = set()
        self._processed_mentions = set()
        self._feed_domains = set()

        self.session = session

    async def process_feed(self, url):
        """ process a feed """

        self._feed_domains.add(utils.get_domain(url))

        if url in self._processed_feeds:
            LOGGER.debug("Skipping already processed feed %s", url)
            return
        self._processed_feeds.add(url)

        LOGGER.debug("++WAIT: %s: get feed", url)
        feed, previous, updated = await feeds.get_feed(self, url)
        LOGGER.debug("++DONE: %s: get feed", url)

        if updated:
            LOGGER.info("Feed %s has been updated", url)

        if not feed:
            return

        LOGGER.debug("--- starting process_feed %s", url)

        pending = []

        try:
            for link in feed.links:
                href = link['href']
                if not href:
                    continue

                #  RFC5005 archive links
                if self.args.archive and link.get('rel') in ('prev-archive',
                                                             'next-archive',
                                                             'prev-page',
                                                             'next-page'):
                    LOGGER.info("Found archive link %s", link)
                    pending.append(
                        ("process feed " + href, self.process_feed(href)))

                # WebSub notification
                if updated and link.get('rel') == 'hub' and not feed.is_archive:
                    LOGGER.info("Found WebSub hub %s", link)
                    pending.append(
                        ("update websub " + href, feed.update_websub(self, href)))
        except (AttributeError, KeyError):
            LOGGER.debug("Feed %s has no links", url)

        # Schedule the entries
        items = set(feed.entry_links)
        if previous:
            items |= set(previous.entry_links)
        for entry in items:
            pending.append(("process entry " + entry,
                            self.process_entry(entry)))

        LOGGER.debug("--- finish process_feed %s", url)

        if pending:
            LOGGER.debug("+++WAIT: process_feed(%s): %d subtasks",
                         url, len(pending))
            LOGGER.debug("%s", [name for (name, _) in pending])
            await asyncio.wait([task for (_, task) in pending])
            LOGGER.debug("+++DONE: process_feed(%s): %d subtasks",
                         url, len(pending))

    async def process_entry(self, url, add_domain=False):
        """ process an entry """

        if add_domain:
            self._feed_domains.add(utils.get_domain(url))

        if url in self._processed_entries:
            LOGGER.debug("Skipping already processed entry %s", url)
            return
        self._processed_entries.add(url)

        LOGGER.debug("++WAIT: get entry %s", url)
        entry, previous, updated = await entries.get_entry(self, url)
        LOGGER.debug("++DONE: get entry %s", url)

        LOGGER.debug("--- starting process_entry %s", url)

        pending = []

        if updated:
            # get the webmention targets
            links = entry.get_targets(self)
            if previous:
                # Only bother with links that changed from the last time
                links = links ^ previous.get_targets(self)

            for link in links:
                pending.append(("send webmention {} -> {}".format(url, link),
                                self.send_webmention(entry, link)))

            if self.args.recurse:
                for feed in entry.feeds:
                    if utils.get_domain(feed) in self._feed_domains:
                        pending.append(("process feed " + feed,
                                        self.process_feed(feed)))

        LOGGER.debug("--- finish process_entry %s", url)

        if pending:
            LOGGER.debug("+++WAIT: process_entry(%s): %d subtasks",
                         url, len(pending))
            LOGGER.debug("%s", [name for (name, _) in pending])
            await asyncio.wait([task for (_, task) in pending])
            LOGGER.debug("+++DONE: process_entry(%s): %d subtasks",
                         url, len(pending))

    async def send_webmention(self, entry, url):
        """ send a webmention from an entry to a URL """

        if (entry.url, url) in self._processed_mentions:
            LOGGER.debug(
                "Skipping already processed mention %s -> %s", entry.url, url)
        self._processed_mentions.add((entry.url, url))

        LOGGER.debug("++WAIT: webmentions.get_target %s", url)
        target = await webmentions.get_target(self, url)
        LOGGER.debug("++DONE: webmentions.get_target %s", url)

        if target:
            LOGGER.debug("++WAIT: Sending webmention %s -> %s", entry.url, url)
            await target.send(self, entry)
            LOGGER.debug("++DONE: Sending webmention %s -> %s", entry.url, url)
