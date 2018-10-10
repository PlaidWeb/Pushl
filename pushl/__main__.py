""" Pushl - a tool for pushing updates from a content feed to another destination """

import argparse
import logging
import queue
import concurrent.futures

from . import feeds, caching, entries

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

    # TODO: parsing for the rel whitelist/blacklist

    return parser.parse_args(*args)


class Worker:

    def __init__(self, args):
        self.args = args
        self.cache = caching.Cache(args.cache_dir)
        self.pending = queue.Queue()
        self.threadpool = concurrent.futures.ThreadPoolExecutor()

    def wait_complete(self):
        self.threadpool.shutdown(True)

    def submit(self, fn, *args, **kwargs):
        self.threadpool.submit(fn, *args, **kwargs)

    def process_feed(self, url):
        feed, updated = feeds.get_feed(url, self.cache)

        if updated:
            for link in feed.feed.links:
                #  RFC5005 archive links
                if self.args.archive and link.get('rel') == 'prev-archive':
                    self.threadpool.submit(self.process_feed, link['href'])

                # WebSub notification
                if link.get('rel') == 'hub' and not feeds.is_archive(feed):
                    self.threadpool.submit(
                        feeds.update_websub, url, link['href'])

                # Schedule the entries
                for entry in feed.entries:
                    self.threadpool.submit(self.process_entry, entry.link)

    def process_entry(self, url):
        entry, previous, updated = entries.get_entry(url, self.cache)

        if updated:
            # get the webmention targets
            targets = entries.get_targets(entry, [None])
            if previous:
                targets = links.union(entries.get_targets(previous, [None]))

            for target in targets:
                self.threadpool.submit(self.send_webmention, entry, target)

    def send_webmention(self, entry, url):
        target = webmentions.get_target(url, self.cache)
        target.send(entry)


def main():
    """ main entry point """
    args = parse_args()
    logging.basicConfig(level=LOG_LEVELS[min(
        args.verbosity, len(LOG_LEVELS) - 1)])

    worker = Worker(args)

    for url in args.feed_url:
        worker.submit(worker.process_feed, url)

    worker.wait_complete()

if __name__ == "__main__":
    main()
