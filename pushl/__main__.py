""" Pushl - a tool for pushing updates from a content feed to another destination """

import argparse
import logging

from . import Pushl, __version__


LOG_LEVELS = [logging.ERROR, logging.WARNING, logging.INFO, logging.DEBUG]

LOGGER = logging.getLogger("pushl.main")


def parse_args(*args):
    """ Parse the arguments for the command """
    parser = argparse.ArgumentParser(
        description="Send push notifications for a feed")

    parser.add_argument('--version', action='version',
                        version="%(prog)s " + __version__)

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
    parser.add_argument('--timeout', '-t', type=int, dest='timeout',
                        help='Connection timeout, in seconds',
                        default=15)

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


def main():
    """ main entry point """
    args = parse_args()
    logging.basicConfig(level=LOG_LEVELS[min(
        args.verbosity, len(LOG_LEVELS) - 1)])

    worker = Pushl(args)

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
