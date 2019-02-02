""" Functionality to add push-ish notifications to feed-based sites """

import concurrent.futures
import queue
import threading
import logging

import requests

from . import feeds, caching, entries, webmentions

__version__ = "0.1.7"

LOGGER = logging.getLogger("pushl")


class Pushl:
    """ Top-level process controller """
    # pylint:disable=too-many-instance-attributes

    def __init__(self, args):
        """ Set up the process worker """
        self.args = args
        self.cache = caching.Cache(args.cache_dir) if args.cache_dir else None
        self.threadpool = concurrent.futures.ThreadPoolExecutor(
            max_workers=args.max_workers)
        self.pending = queue.Queue()
        self.rel_whitelist = None
        self.rel_blacklist = None

        self.lock = threading.Lock()
        self.processed_feeds = set()
        self.processed_entries = set()
        self.processed_mentions = set()

        self.num_submitted = 0
        self.num_finished = 0

        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=args.max_workers, pool_maxsize=args.max_workers)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

        self.timeout = args.timeout

    def submit(self, func, *args, **kwargs):
        """ Submit a task """
        LOGGER.debug("submit %s (%s, %s)", func, args, kwargs)
        task = self.threadpool.submit(
            self._run_wrapped, func, *args, **kwargs)
        self.pending.put(task)
        self.num_submitted += 1
        return task

    @staticmethod
    def _run_wrapped(func, *args, **kwargs):
        return func(*args, **kwargs)

    def wait_finished(self):
        """ Wait for all tasks to finish """
        while self.num_finished < self.num_submitted:
            try:
                queued = self.pending.get(timeout=0.1)
                queued.result()
                self.num_finished += 1
            except queue.Empty:
                pass
            except KeyboardInterrupt:
                raise
            except:  # pylint:disable=bare-except
                LOGGER.exception("Task threw exception")
        LOGGER.info("%d/%d tasks finished",
                    self.num_finished, self.num_submitted)

    def process_feed(self, url):
        """ process a feed """

        with self.lock:
            if url in self.processed_feeds:
                LOGGER.debug("Skipping already processed feed %s", url)
                return
            self.processed_feeds.add(url)

        LOGGER.debug("process feed %s", url)
        feed, previous, updated = feeds.get_feed(self, url)

        try:
            for link in feed.feed.links:
                #  RFC5005 archive links
                if self.args.archive and link.get('rel') in ('prev-archive',
                                                             'next-archive',
                                                             'prev-page',
                                                             'next-page'):
                    LOGGER.info("Found prev-archive link %s", link)
                    self.submit(self.process_feed, link['href'])

                # WebSub notification
                if updated and link.get('rel') == 'hub' and not feeds.is_archive(feed):
                    LOGGER.info("Found WebSub hub %s", link)
                    self.submit(feeds.update_websub, self, url, link['href'])
        except (AttributeError, KeyError):
            LOGGER.debug("Feed %s has no links", url)

        # Schedule the entries
        for entry in feeds.get_entry_links(feed, previous):
            self.submit(self.process_entry, entry)

    def process_entry(self, url):
        """ process an entry """

        with self.lock:
            if url in self.processed_entries:
                LOGGER.debug("Skipping already processed entry %s", url)
                return
            self.processed_entries.add(url)

        entry, previous, updated = entries.get_entry(self, url)

        if updated:
            # get the webmention targets
            links = entries.get_targets(self, entry)
            if previous:
                links = links.union(entries.get_targets(self, previous))

            for link in links:
                self.submit(self.send_webmention, entry, link)

            if self.args.recurse:
                for feed in entries.get_feeds(entry):
                    self.submit(self.process_feed, feed)

    def send_webmention(self, entry, url):
        """ send a webmention from an entry to a URL """

        with self.lock:
            if (entry.url, url) in self.processed_mentions:
                LOGGER.debug(
                    "Skipping already processed mention %s -> %s", entry.url, url)
            self.processed_mentions.add((entry.url, url))

        LOGGER.debug("Sending webmention %s -> %s", entry.url, url)
        try:
            target = webmentions.get_target(self, url)
            if target:
                target.send(self, entry)
        except Exception as error:  # pylint:disable=broad-except
            LOGGER.exception("%s -> %s: Got error %s", entry.url, url, error)
