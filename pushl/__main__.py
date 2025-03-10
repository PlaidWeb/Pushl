""" Pushl - a tool for pushing updates from a content feed to another destination """

import argparse
import asyncio
import logging
import typing

import aiohttp

from . import Pushl, __version__

LOG_LEVELS = [logging.ERROR, logging.WARNING, logging.INFO, logging.DEBUG]

LOGGER = logging.getLogger("pushl.main")

DEFAULT_USERAGENT = f"Pushl/{__version__.__version__}; +https://github.com/PlaidWeb/pushl"


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
    parser.add_argument("-s", "--websub-only", nargs='+',
                        help='URLs/feeds to only send WebSub notifications for',
                        metavar='feed_url', dest='websub_only')
    parser.add_argument('--timeout', '-t', type=int, dest='timeout',
                        help='Connection timeout, in seconds',
                        default=120)

    parser.add_argument('--max-connections', type=int, dest='max_connections',
                        help='Maximum number of connections to have open at once',
                        default=100)
    parser.add_argument('--max-per-host', type=int, dest='max_per_host',
                        help='Maximum number of connections per host',
                        default=8)

    parser.add_argument('--rel-include', dest='rel_include', type=str,
                        help="Comma-separated list of link RELs to include"
                        + " for sending webmentions")
    parser.add_argument('--rel-exclude', dest='rel_exclude', type=str,
                        help="Comma-separated list of link RELs to exclude"
                        + " from sending webmentions",
                        default="nofollow")

    parser.add_argument('--max-time', '-m', dest='max_time', type=float,
                        help="Maximum time (in seconds) to spend on this", default=1800)

    parser.add_argument('--user-agent', dest='user_agent', type=str,
                        help="User-agent string to send",
                        default=DEFAULT_USERAGENT)

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

    feature = parser.add_mutually_exclusive_group(required=False)
    feature.add_argument('--wayback-machine', '-k',
                         help="Request linked-to pages to be stored in the Wayback Machine",
                         dest='wayback_machine', action='store_true')
    feature.add_argument('--no-wayback-machine',
                         help="Disable the Wayback Machine preservation request",
                         dest='wayback_machine', action='store_false')
    feature.set_defaults(wayback_machine=False)

    feature = parser.add_mutually_exclusive_group(required=False)
    feature.add_argument('--self-pings',
                         help="Allow entries to ping other entries on the same domain",
                         dest='self_pings', action='store_true')
    feature.add_argument('--no-self-pings',
                         help="Don't allow entries to ping other entries on the same domain",
                         dest='self_pings', action='store_false')
    feature.set_defaults(self_pings=False)

    feature = parser.add_mutually_exclusive_group(required=False)
    feature.add_argument('--dry-run', '-n',
                         help="Only perform a dry run; don't send any pings",
                         dest='dry_run', action='store_true')
    feature.add_argument('--no-dry-run',
                         help="Send pings normally",
                         dest='dry_run', action='store_false')
    feature.set_defaults(dry_run=False)

    return parser.parse_args(*args)


def main():
    """ main entry point """
    args = parse_args()
    logging.basicConfig(level=LOG_LEVELS[min(
        args.verbosity, len(LOG_LEVELS) - 1)])

    loop = asyncio.get_event_loop()
    loop.run_until_complete(_run(args))


async def _run(args: argparse.Namespace):
    connector = aiohttp.TCPConnector(
        limit=args.max_connections,
        limit_per_host=args.max_per_host,
        enable_cleanup_closed=True,
        force_close=not args.keepalive
    )

    # Time spent waiting for a connection pool entry to free up counts against
    # total and connect, so instead we just set the new connection and the read
    # timeout
    timeout = aiohttp.ClientTimeout(
        total=None,
        connect=None,
        sock_connect=args.timeout,
        sock_read=args.timeout)

    async with aiohttp.ClientSession(timeout=timeout,
                                     connector=connector) as session:
        worker = Pushl(session, args)

        pending: typing.List[typing.Coroutine] = []
        for url in args.feeds or []:
            pending.append(worker.process_feed(url))

        for url in args.websub_only or []:
            pending.append(worker.process_feed(url, False))

        for url in args.entries or []:
            pending.append(worker.process_entry(url, add_domain=True))

        if pending:
            _, timed_out = await asyncio.wait([asyncio.create_task(coro) for coro in pending],
                                              timeout=args.max_time)
            if timed_out:
                LOGGER.warning("Done. %d tasks did not complete within %d seconds",
                               len(timed_out), args.max_time)
            else:
                LOGGER.info("Completed all tasks")


if __name__ == "__main__":
    main()
