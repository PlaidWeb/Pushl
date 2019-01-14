""" Pushl - a tool for pushing updates from a content feed to another destination """

import argparse
import logging
import queue
import concurrent.futures
import threading

from . import feeds, caching, entries, webmentions, common

LOG_LEVELS = [logging.ERROR, logging.WARNING, logging.INFO, logging.DEBUG]

LOGGER = logging.getLogger("pushl")


def parse_args(*args):
    """ Parse the arguments for the command """
    parser = argparse.ArgumentParser(
        description="Send push notifications for a feed")
    parser.add_argument('feeds', type=str, nargs='*', metavar='feed_url',
                        help='A URL for a feed to process')
    parser.add_argument('--cache', '-c', type=str, dest='cache_dir',
                        help='Cache storage directory',
                        required=False)
    parser.add_argument("-v", "--verbosity", action="count",
                        help="increase output verbosity",
                        default=0)
    parser.add_argument("-e", "--entry", nargs='+',
                        help='URLs to entries/pages to index directly',
                        metavar='entry_url',
                        dest='entries')
    parser.add_argument('--max-workers', '-w', type=int, dest='max_workers',
                        help='Maximum number of worker threads',
                        default=20)

    feature = parser.add_mutually_exclusive_group(required=False)
    feature.add_argument('--archive', '-a', dest='archive', action='store_true',
                         help='Process archive links in the feed per RFC 5005')
    feature.add_argument('--no-archive', dest='archive', action='store_false',
                         help='Do not process archive links in the feed')
    feature.set_defaults(archive=False)

    feature = parser.add_mutually_exclusive_group(required=False)
    feature.add_argument('--recurse', '-r',
                         help="Recursively check other discovered feeds",
                         action='store_true', dest='recurse')
    feature.add_argument('--no-recurse', dest='recurse',
                         action='store_false',
                         help="Do not recurse into other feeds")
    feature.set_defaults(recurse=False)

    return parser.parse_args(*args)


class Processor:
    """ Top-level process controller """
    # pylint:disable=too-many-instance-attributes

    def __init__(self, args):
        """ Set up the process worker """
        self.args = args
        self.cache = caching.Cache(args.cache_dir)
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

        common.set_pool_size(args.max_workers)

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
        feed, previous, updated = feeds.get_feed(url, self.cache)

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
                    self.submit(feeds.update_websub, url, link['href'])
        except AttributeError:
            LOGGER.info("Feed %s has no links", url)

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

        entry, previous, updated = entries.get_entry(url, self.cache)

        if updated:
            # get the webmention targets
            links = entries.get_targets(
                entry, self.rel_whitelist, self.rel_blacklist)
            if previous:
                links = links.union(entries.get_targets(
                    previous, self.rel_whitelist, self.rel_blacklist))

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
            target = webmentions.get_target(url, self.cache)
            target.send(entry)
        except Exception as error:  # pylint:disable=broad-except
            LOGGER.exception("%s -> %s: Got error %s", entry.url, url, error)


def main():
    """ main entry point """
    args = parse_args()
    logging.basicConfig(level=LOG_LEVELS[min(
        args.verbosity, len(LOG_LEVELS) - 1)])

    worker = Processor(args)

    for url in args.feeds or []:
        worker.submit(worker.process_feed, url)

    for url in args.entries or []:
        worker.submit(worker.process_entry, url)

    try:
        worker.wait_finished()
    except KeyboardInterrupt:
        LOGGER.error("Got keyboard interrupt; shutting down")
        worker.threadpool.shutdown(False)

if __name__ == "__main__":
    main()
