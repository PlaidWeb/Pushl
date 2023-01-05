""" Functionality to add push-ish notifications to feed-based sites """

import asyncio
import logging
import typing

import aiohttp

from . import caching, entries, feeds, utils, webmentions, websub

LOGGER = logging.getLogger("pushl")


class Pushl:
    """ Top-level process controller """
    # pylint:disable=too-many-instance-attributes

    def __init__(self, session: aiohttp.ClientSession, args):
        """ Set up the process worker """
        self.args = args
        self.cache = caching.Cache(args.cache_dir) if args.cache_dir else None
        self.rel_include = args.rel_include.split(
            ',') if args.rel_include else None
        self.rel_exclude = args.rel_exclude.split(
            ',') if args.rel_exclude else None

        self._processed_feeds: typing.Set[typing.Tuple[str, bool]] = set()
        self._processed_entries: typing.Set[typing.Tuple[str, bool]] = set()
        self._processed_mentions: typing.Set[typing.Tuple[str, str]] = set()
        self._feed_domains: typing.Set[str] = set()

        self._processed_websub: typing.Set[typing.Tuple[str, str]] = set()

        self._processed_wayback: typing.Set[str] = set()

        self.session = session

    @staticmethod
    async def _run_pending(pending, label: str):
        if pending:
            LOGGER.debug("+++WAIT: %s: %d subtasks",
                         label, len(pending))
            LOGGER.debug("%s", [name for (name, _) in pending])
            await asyncio.wait([asyncio.create_task(coro) for (_, coro) in pending])
            LOGGER.debug("+++DONE: %s: %d subtasks",
                         label, len(pending))

    async def process_feed(self, url: str, send_mentions: bool = True):
        """ process a feed """

        self._feed_domains.add(utils.get_domain(url))

        if (url, send_mentions) in self._processed_feeds:
            LOGGER.debug("Skipping already processed feed %s", url)
            return
        self._processed_feeds.add((url, send_mentions))

        LOGGER.debug("++WAIT: %s: get feed", url)
        feed, previous, updated = await feeds.get_feed(self, url)
        LOGGER.debug("++DONE: %s: get feed", url)

        LOGGER.log(updated and logging.INFO, "Feed %s has been updated %s -> %s", url,
                   previous and previous.digest.hex(), feed and feed.digest.hex())

        if not feed:
            return

        LOGGER.debug("--- starting process_feed %s %s", url, send_mentions)

        pending: typing.List[typing.Tuple[str, typing.Coroutine]] = []

        # RFC5005
        if self.args.archive:
            for rel in ('prev-archive', 'next-archive', 'prev-page', 'next-page'):
                for link in feed.links[rel]:
                    LOGGER.debug('%s: %s', rel, link)
                    pending.append(("process feed " + link,
                                    self.process_feed(link, send_mentions)))

        # WebSub
        if updated and not feed.is_archive:
            for hub in feed.links['hub']:
                LOGGER.debug("Found hub %s", hub)
                pending.append(("update websub " + hub,
                                self.send_websub(feed.canonical, hub)))

        # Schedule the entries
        items = set(feed.entry_links)
        if previous:
            items |= set(previous.entry_links)
        for entry in items:
            pending.append(("process entry " + entry,
                            self.process_entry(entry, send_mentions=send_mentions)))

        await self._run_pending(pending, f'process_feed({url})')

        LOGGER.debug("--- finish process_feed %s %s", url, send_mentions)

    async def process_entry(self, url: str, add_domain: bool = False, send_mentions: bool = True):
        """ process an entry """

        if add_domain:
            self._feed_domains.add(utils.get_domain(url))

        if (url, send_mentions) in self._processed_entries:
            LOGGER.debug("Skipping already processed entry %s", url)
            return
        self._processed_entries.add((url, send_mentions))

        LOGGER.debug("++WAIT: get entry %s", url)
        entry, previous, updated = await entries.get_entry(
            self, url,
            'entries' if send_mentions else 'entries_websub')
        LOGGER.debug("++DONE: get entry %s entry=%s previous=%s updated=%s", url,
                     bool(entry), bool(previous), updated)

        LOGGER.debug("--- starting process_entry %s", url)

        pending = []

        if updated and entry:
            LOGGER.info("Processing entry: %s send_mentions=%s %s -> %s",
                        url, send_mentions,
                        previous and previous.digest.hex(),
                        entry and entry.digest.hex())
            if send_mentions:
                pending.append((f"process entry mentions {url}",
                                self.process_entry_mentions(url, entry, previous)))

            if self.args.recurse:
                for feed in entry.feeds:
                    if utils.get_domain(feed) in self._feed_domains:
                        pending.append((f"process feed {feed}",
                                        self.process_feed(feed, send_mentions=send_mentions)))
                    else:
                        LOGGER.info("Ignoring non-local feed %s", feed)

            for hub in entry.hubs:
                pending.append((f"send websub {url} -> {hub}",
                                self.send_websub(url, hub)))

        LOGGER.debug("--- finish process_entry %s", url)

        await self._run_pending(pending, f'process_entry({url})')

    async def process_entry_mentions(self, url: str,
                                     entry: entries.Entry,
                                     previous: typing.Optional[entries.Entry]):
        """ Process an entry's webmentions """
        pending = []

        def send_pings(source, targets):
            for (target, href) in targets:
                pending.append((f"send webmention {source} -> {target} ({href})",
                                self.send_webmention(source, target, href)))

        # get the webmention targets
        targets = entry.get_targets(self)
        if previous:
            # Only bother with links that changed from the last time
            LOGGER.debug("targets before: %s", targets)
            prior = previous.get_targets(self)
            if previous.url != entry.url:
                LOGGER.info("%s: Entry changed URLs from %s to %s; re-sending old pings %s",
                            url, previous.url, entry.url,
                            [target for (target, _) in prior])
                send_pings(previous.url, prior)
            else:
                LOGGER.debug(
                    "%s: excluding previously-checked targets %s", url, targets & prior)
                targets = targets ^ prior

        if targets:
            LOGGER.info("%s: Updating targets %s", url, [
                        target for (target, _) in targets])
            send_pings(entry.url, targets)

        await self._run_pending(pending, f'process_entry_mentions({url})')

    async def send_webmention(self, entry_url: str, dest: str, href: str):
        """ send a webmention from an entry to a URL """

        if (entry_url, dest) in self._processed_mentions:
            LOGGER.debug(
                "Skipping already processed mention %s -> %s", entry_url, dest)
            return
        self._processed_mentions.add((entry_url, dest))

        LOGGER.debug("++WAIT: webmentions.get_target %s", dest)
        target, code, cached = await webmentions.get_target(self, dest)
        LOGGER.debug("++DONE: webmentions.get_target %s", dest)

        if code and 400 <= code < 500:
            # Resource is nonexistent or forbidden
            LOGGER.warning("%s: link to %s generated client error %d",
                           entry_url, href, code)

        pending = []

        if target:
            pending.append((f"webmention {entry_url}->{href}",
                            target.send(self, entry_url, href)))

        if (not cached
                and self.args.wayback_machine
                and dest not in self._processed_wayback):
            pending.append((f"wayback machine {dest}",
                            utils.retry_get(self, 'https://web.archive.org/save/' + dest)))
            self._processed_wayback.add(dest)

        if self.args.dry_run:
            LOGGER.info("DRY RUN: not sending ping %s -> %s", entry_url, dest)
            return

        await self._run_pending(pending, f'send_webmention({entry_url},{dest})')

    async def send_websub(self, url: str, hub: str):
        """ send a websub notification """

        if (url, hub) in self._processed_websub:
            LOGGER.debug(
                "Skipping already processed websub %s -> %s", url, hub)
            return
        self._processed_websub.add((url, hub))

        if self.args.dry_run:
            LOGGER.info("DRY RUN: not sending websub %s -> %s", url, hub)

        await websub.send(self, url, hub)
