""" Pushl - a tool for pushing updates from a content feed to another destination """

import argparse
import logging
import asyncio

import aiohttp

from . import Pushl, __version__


LOG_LEVELS = [logging.ERROR, logging.WARNING, logging.INFO, logging.DEBUG]

LOGGER = logging.getLogger("pushl.main")


def parse_args(*args):
    """ Parse the arguments for the command """
    parser = argparse.ArgumentParser(
        description="Send push notifications for a feed")

    parser.add_argument('--version', action='version',
                        version="%(prog)s " + __version__.__version__)

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
    parser.add_argument('--timeout', '-t', type=int, dest='timeout',
                        help='Connection timeout, in seconds',
                        default=120)

    parser.add_argument('--max-connections', type=int, dest='max_connections',
                        help='Maximum number of connections to have open at once',
                        default=100)
    parser.add_argument('--max-per-host', type=int, dest='max_per_host',
                        help='Maximum number of connections per host',
                        default=0)

    parser.add_argument('--rel-whitelist', '-w', dest='rel_whitelist', type=str,
                        help="Comma-separated list of link RELs to whitelist"
                        + " for sending webmentions")
    parser.add_argument('--rel-blacklist', '-b', dest='rel_blacklist', type=str,
                        help="Comma-separated list of link RELs to blacklist"
                        + " from sending webmentions",
                        default="nofollow")

    feature = parser.add_mutually_exclusive_group(required=False)
    feature.add_argument('--keepalive', dest='keepalive', action='store_true',
                         help="Keep TCP connections alive")
    feature.add_argument('--no-keepalive', dest='keepalive', action='store_false',
                         help="Don't keep TCP connections alive")
    feature.set_defaults(keepalive=False)

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
    loop = asyncio.get_event_loop()
    loop.run_until_complete(_run(loop))


async def _run(loop):
    args = parse_args()
    logging.basicConfig(level=LOG_LEVELS[min(
        args.verbosity, len(LOG_LEVELS) - 1)])

    connector = aiohttp.TCPConnector(
        limit=args.max_connections,
        limit_per_host=args.max_per_host,
        enable_cleanup_closed=True,
        force_close=not args.keepalive
    )

    # Time waiting for a connection pool entry to free up counts against total
    # and connect, so instead we just set the new connection and the read
    # timeout
    timeout = aiohttp.ClientTimeout(
        total=None,
        connect=None,
        sock_connect=args.timeout,
        sock_read=args.timeout)

    async with aiohttp.ClientSession(loop=loop,
                                     timeout=timeout,
                                     connector=connector) as session:
        worker = Pushl(session, args)
        pending = []

        for url in args.feeds or []:
            pending.append(worker.process_feed(url))

        for url in args.entries or []:
            pending.append(worker.process_entry(url))

        if pending:
            await asyncio.wait(pending)

    LOGGER.info("Completed all tasks")


if __name__ == "__main__":
    main()
