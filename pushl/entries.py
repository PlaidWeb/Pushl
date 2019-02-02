""" Functions for handling entries """

import logging
import urllib.parse
import functools
import hashlib

from bs4 import BeautifulSoup
import requests

from . import caching

LOGGER = logging.getLogger(__name__)
SCHEMA_VERSION = 1


class Entry:
    """ Encapsulates a scanned entry """
    # pylint:disable=too-few-public-methods

    def __init__(self, config, url, previous=None):
        request = config.session.get(url, headers=caching.make_headers(previous),
                                     timeout=config.args.timeout)

        md5 = hashlib.md5(request.text.encode('utf-8'))

        self.text = request.text
        self.digest = md5.digest()
        self.url = request.url  # the canonical, final URL
        self.original_url = url  # the original request URL
        self.status_code = request.status_code
        self.headers = request.headers
        self.schema = SCHEMA_VERSION

    @property
    def soup(self):
        """ Get the BeautifulSoup instance for this entry """
        return BeautifulSoup(self.text, 'html.parser')


@functools.lru_cache()
def get_entry(config, url):
    """ Given an entry URL, return the entry document

    Arguments:

    config -- the configuration
    url -- the URL of the entry

    Returns: 3-tuple of (current, previous, updated) """

    previous = config.cache.get(
        'entry', url,
        schema_version=SCHEMA_VERSION) if config.cache else None

    try:
        current = Entry(config, url, previous)
    except requests.RequestException as error:
        LOGGER.warning("%s: %s", url, error)
        return None, None, False

    # Cache hit
    if current.status_code == 304:
        return previous, previous, False

    # Content updated
    if 200 <= current.status_code < 300 or current.status_code == 410:
        if config.cache:
            config.cache.set('entry', url, current)

    return current, previous, (not previous
                               or previous.digest != current.digest
                               or previous.status_code != current.status_code)


def _check_rel(link, rel_whitelist, rel_blacklist):
    """ Check a link's relations against the whitelist or blacklist.

    First, this will reject based on blacklist.

    Next, if there is a whitelist, there must be at least one rel that matches.
    To explicitly allow links without a rel you can add None to the whitelist
    (e.g. ['in-reply-to',None])
    """

    if not 'href' in link.attrs:
        # degenerate link
        return False

    rels = link.attrs.get('rel', [None])

    if rel_blacklist:
        # Never return True for a link whose rel appears in the blacklist
        for rel in rels:
            if rel in rel_blacklist:
                return False

    if rel_whitelist:
        # If there is a whitelist for rels, only return true for a rel that
        # appears in it
        for rel in rels:
            if rel in rel_whitelist:
                return True
        # If there is a whitelist and we don't match, then reject
        return False

    return True


def _domains_differ(link, source):
    """ Check that a link is not on the same domain as the source URL """
    target = urllib.parse.urlparse(link.attrs.get('href')).netloc.lower()
    if not target:
        return False

    origin = urllib.parse.urlparse(source).netloc.lower()
    return target != origin


def get_top_nodes(entry):
    """ Given an Entry object, return all of the top-level entry nodes """
    soup = entry.soup
    return (soup.find_all(class_="h-entry")
            or soup.find_all("article")
            or soup.find_all(class_="entry")
            or [soup])


def get_targets(config, entry):
    """ Given an Entry object, return all of the outgoing links. """

    targets = set()
    for top_node in get_top_nodes(entry):
        targets = targets.union({urllib.parse.urljoin(entry.url, link.attrs['href'])
                                 for link in top_node.find_all('a')
                                 if _check_rel(link, config.rel_whitelist, config.rel_blacklist)
                                 and _domains_differ(link, entry.url)})

    return targets


def get_feeds(entry):
    """ Given an Entry object, return all of the discovered feeds """
    soup = entry.soup
    return [urllib.parse.urljoin(entry.url, link.attrs['href'])
            for link in soup.find_all('link', rel='alternate')
            if _is_feed(link)]


def _is_feed(link):
    return ('href' in link.attrs
            and link.attrs.get('type') in ('application/rss+xml',
                                           'application/atom+xml'))
