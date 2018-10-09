""" Pushl - a tool for pushing updates from a content feed to another destination """

import argparse
import logging
import collections

from . import feeds, caching

logging.basicConfig(level=logging.INFO)
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

    feature = parser.add_mutually_exclusive_group(required=False)
    feature.add_argument('--archive', '-a', dest='archive', action='store_true',
                         help='Process archive links in the feed per RFC 5005')
    feature.add_argument('--no-archive', dest='archive', action='store_false',
                         help='Do not process archive links in the feed')
    feature.set_defaults(archive=False)

    return parser.parse_args(*args)


def main():
    """ main entry point """
    args = parse_args()

    cache = caching.Cache(args.cache_dir)
    feed_urls = collections.deque(args.feed_url)

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


if __name__ == "__main__":
    main()
