""" Pushl - a tool for pushing updates from a content feed to another destination """

import argparse
import logging
import collections

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


def main():
    """ main entry point """
    args = parse_args()
    logging.basicConfig(level=LOG_LEVELS[min(
        args.verbosity, len(LOG_LEVELS) - 1)])

    cache = caching.Cache(args.cache_dir)

    # TODO this is really freaking slow and should go through a
    # ThreadPoolExecutor instead. Also, sending webmentions should cache
    # endpoints where possible and do the endpoint request and webmention send
    # as a pipelined series of events and so on

    feed_urls = collections.deque(args.feed_url)
    entry_urls = collections.deque()

    while feed_urls:
        url = feed_urls.popleft()
        LOGGER.info("Retrieving %s", url)
        feed, updated = feeds.get_feed(url, cache)

        if updated:
            # Process the various links...
            for link in feed.feed.links:

                # Archive links
                if args.archive and link.get('rel') == 'prev-archive':
                    feed_urls.append(link['href'])

                # WebSub
                if link.get('rel') == 'hub' and not feeds.is_archive(feed):
                    feeds.update_websub(url, link['href'])

                # Schedule the entries
                entry_urls += [entry.link for entry in feed.entries]

    while entry_urls:
        url = entry_urls.popleft()
        LOGGER.info("Retrieving %s", url)
        entry, previous, updated = entries.get_entry(url, cache)

        if updated:
            entries.send_webmentions(entry, previous, [None])

if __name__ == "__main__":
    main()
