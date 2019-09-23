""" Functionality to add push-ish notifications to feed-based sites """

import asyncio
import logging

from . import caching, entries, feeds, utils, webmentions, websub

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

        self._processed_websub = set()

        self._processed_wayback = set()

        self.session = session

    async def process_feed(self, url, send_mentions=True):
        """ process a feed """

        self._feed_domains.add(utils.get_domain(url))

        if (url, send_mentions) in self._processed_feeds:
            LOGGER.debug("Skipping already processed feed %s", url)
            return
        self._processed_feeds.add((url, send_mentions))

        LOGGER.debug("++WAIT: %s: get feed", url)
        feed, previous, updated = await feeds.get_feed(self, url)
        LOGGER.debug("++DONE: %s: get feed", url)

        if updated:
            LOGGER.info("Feed %s has been updated", url)

        if not feed:
            return

        LOGGER.debug("--- starting process_feed %s %s", url, send_mentions)

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
                    LOGGER.debug("Found archive link %s", link)
                    pending.append(
                        ("process feed " + href, self.process_feed(href, send_mentions)))

                # WebSub notification
                if updated and link.get('rel') == 'hub' and not feed.is_archive:
                    LOGGER.debug("Found WebSub hub %s", link)
                    pending.append(
                        ("update websub " + href, self.send_websub(feed.url, href)))
        except (AttributeError, KeyError):
            LOGGER.debug("Feed %s has no links", url)

        # Schedule the entries
        items = set(feed.entry_links)
        if previous:
            items |= set(previous.entry_links)
        for entry in items:
            pending.append(("process entry " + entry,
                            self.process_entry(entry, send_mentions=send_mentions)))

        LOGGER.debug("--- finish process_feed %s %s", url, send_mentions)

        if pending:
            LOGGER.debug("+++WAIT: process_feed(%s): %d subtasks",
                         url, len(pending))
            LOGGER.debug("%s", [name for (name, _) in pending])
            await asyncio.wait([task for (_, task) in pending])
            LOGGER.debug("+++DONE: process_feed(%s): %d subtasks",
                         url, len(pending))

    async def process_entry(self, url, add_domain=False, send_mentions=True):
        """ process an entry """
        # pylint:disable=too-many-branches

        if add_domain:
            self._feed_domains.add(utils.get_domain(url))

        if (url, send_mentions) in self._processed_entries:
            LOGGER.debug("Skipping already processed entry %s", url)
            return
        self._processed_entries.add((url, send_mentions))

        LOGGER.debug("++WAIT: get entry %s", url)
        entry, previous, updated = await entries.get_entry(self, url)
        LOGGER.debug("++DONE: get entry %s entry=%s previous=%s updated=%s", url,
                     bool(entry), bool(previous), updated)

        LOGGER.debug("--- starting process_entry %s", url)

        pending = []

        if updated:
            LOGGER.info("Processing entry: %s send_mentions=%s",
                        url, send_mentions)
            if send_mentions:
                # get the webmention targets
                targets = entry.get_targets(self)
                if previous:
                    # Only bother with links that changed from the last time
                    LOGGER.debug("targets before: %s", targets)
                    invert = previous.get_targets(self)
                    LOGGER.debug(
                        "%s: excluding previously-checked targets %s", url, invert)
                    targets = targets ^ invert

                if targets:
                    LOGGER.info("%s: Mention targets: %s", url, ' '.join(
                        target for (target, _) in targets))
                for (target, href) in targets:
                    pending.append(("send webmention {} -> {} ({})".format(url, target, href),
                                    self.send_webmention(entry, target, href)))

            if self.args.recurse:
                for feed in entry.feeds:
                    if utils.get_domain(feed) in self._feed_domains:
                        pending.append(("process feed " + feed,
                                        self.process_feed(feed, send_mentions=send_mentions)))
                    else:
                        LOGGER.info("Ignoring non-local feed %s", feed)

            for hub in entry.hubs:
                pending.append(("send websub {} -> {}".format(url, hub),
                                self.send_websub(url, hub)))

        LOGGER.debug("--- finish process_entry %s", url)

        if pending:
            LOGGER.debug("+++WAIT: process_entry(%s): %d subtasks",
                         url, len(pending))
            LOGGER.debug("%s", [name for (name, _) in pending])
            await asyncio.wait([task for (_, task) in pending])
            LOGGER.debug("+++DONE: process_entry(%s): %d subtasks",
                         url, len(pending))

    async def send_webmention(self, entry, dest, href):
        """ send a webmention from an entry to a URL """

        if (entry.url, dest) in self._processed_mentions:
            LOGGER.debug(
                "Skipping already processed mention %s -> %s", entry.url, dest)
            return
        self._processed_mentions.add((entry.url, dest))

        LOGGER.debug("++WAIT: webmentions.get_target %s", dest)
        target, code, cached = await webmentions.get_target(self, dest)
        LOGGER.debug("++DONE: webmentions.get_target %s", dest)

        if code and 400 <= code < 500:
            # Resource is nonexistent or forbidden
            LOGGER.warning("%s: link to %s generated client error %d",
                           entry.url, href, code)

        pending = []

        if target:
            pending.append(("webmention {}->{}".format(entry.url, href),
                            target.send(self, entry.url, href)))

        if (not cached
                and self.args.wayback_machine
                and dest not in self._processed_wayback):
            pending.append(("wayback machine {}".format(dest),
                            utils.retry_get(self, 'https://web.archive.org/save/' + dest)))
            self._processed_wayback.add(dest)

        if pending:
            LOGGER.debug("+++WAIT: send_webmention(%s): %d subtasks", dest, len(pending))
            LOGGER.debug("%s", [name for (name, _) in pending])
            await asyncio.wait([task for (_, task) in pending])
            LOGGER.debug("---DONE: send_webmention(%s): %d subtasks", dest, len(pending))

    async def send_websub(self, url, hub):
        """ send a websub notification """

        if (url, hub) in self._processed_websub:
            LOGGER.debug(
                "Skipping already processed websub %s -> %s", url, hub)
            return
        self._processed_websub.add((url, hub))

        await websub.send(self, url, hub)
