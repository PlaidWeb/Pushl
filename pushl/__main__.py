""" Pushl - a tool for pushing updates from a content feed to another destination """

import argparse
import logging

import feedparser
import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def parse_args(*args):
    parser = argparse.ArgumentParser(
        description="Send push notifications for a feed")
    parser.add_argument('feed_url', type=str, nargs='+',
                        description='A URL for a feed to process')
    return parser.parse_args(*args)


def parse_feed(request):
    pass


def main():
    args = parse_args()

    for url in args.feed_url do:
        logger.info("Retrieving %s", url)
        request = requests.get(url)
        if 200 <= request.status_code < 300:
            parse_feed(request)
        else:
            logger.error("Got response code %d", request.status_code)

if __name__ == "__main__":
    main()
