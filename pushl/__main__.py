""" Pushl - a tool for pushing updates from a content feed to another destination """

import argparse
import logging
import queue
import concurrent.futures

from . import feeds, caching, entries, webmentions

LOG_LEVELS = [logging.ERROR, logging.WARNING, logging.INFO, logging.DEBUG]

LOGGER = logging.getLogger("pushl")


def parse_args(*args):
    """ Parse the arguments for the command """
    parser = argparse.ArgumentParser(
        description="Send push notifications for a feed")
    parser.add_argument('feed_url', type=str, nargs='+',
                        help='A URL for a feed to process')
    parser.add_argument('--cache', '-c', type=str, dest='cache_dir',
                        help='Cache storage directory',
                        required=False)
    parser.add_argument("-v", "--verbosity", action="count",
                        help="increase output verbosity",
                        default=0)

    feature = parser.add_mutually_exclusive_group(required=False)
    feature.add_argument('--archive', '-a', dest='archive', action='store_true',
                         help='Process archive links in the feed per RFC 5005')
    feature.add_argument('--no-archive', dest='archive', action='store_false',
                         help='Do not process archive links in the feed')
    feature.set_defaults(archive=False)

    return parser.parse_args(*args)


class Processor:
    """ Top-level process controller """

    def __init__(self, args):
        """ Set up the process worker """
        self.args = args
        self.cache = caching.Cache(args.cache_dir)
        self.threadpool = concurrent.futures.ThreadPoolExecutor()
        self.pending = queue.Queue()
        self.rel_whitelist = None
        self.rel_blacklist = None

    def submit(self, func, *args, **kwargs):
        """ Submit a task """
        LOGGER.debug("submit %s (%s, %s)", func, args, kwargs)
        self.pending.put(self.threadpool.submit(func, *args, **kwargs))

    def wait_finished(self, timeout=5):
        """ Wait for all tasks to finish """
        try:
            while True:
                queued = self.pending.get(timeout=timeout)
                queued.result()
        except queue.Empty:
            LOGGER.info("Thread pool finished all tasks")

    def process_feed(self, url):
        """ process a feed """
        LOGGER.debug("process feed %s", url)
        feed, updated = feeds.get_feed(url, self.cache)

        for link in feed.feed.links:
            #  RFC5005 archive links
            if self.args.archive and link.get('rel') == 'prev-archive':
                LOGGER.info("Found prev-archive link %s", link)
                self.submit(self.process_feed, link['href'])

            # WebSub notification
            if updated and link.get('rel') == 'hub' and not feeds.is_archive(feed):
                LOGGER.info("Found WebSub hub %s", link)
                self.submit(feeds.update_websub, url, link['href'])

            # Schedule the entries
            for entry in feed.entries:
                self.submit(self.process_entry, entry.link)

    def process_entry(self, url):
        """ process an entry """
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

    def send_webmention(self, entry, url):
        """ send a webmention from an entry to a URL """
        LOGGER.debug("Sending webmention %s -> %s", entry.url, url)
        target = webmentions.get_target(url, self.cache)
        if target:
            response = target.send(entry)
            if response and response.status_code == 429:
                retry = int(response.headers.get('retry-after', 30))
                LOGGER.warning(
                    "%s Got try-again error from endpoint; Retry in %d seconds",
                    url, retry)


def main():
    """ main entry point """
    args = parse_args()
    logging.basicConfig(level=LOG_LEVELS[min(
        args.verbosity, len(LOG_LEVELS) - 1)])

    worker = Processor(args)

    for url in args.feed_url:
        worker.submit(worker.process_feed, url)

    worker.wait_finished()

if __name__ == "__main__":
    main()
