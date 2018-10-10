""" Functions for handling entries """

import logging
import urllib.parse
import functools
import hashlib

from bs4 import BeautifulSoup
import requests

from . import caching

LOGGER = logging.getLogger(__name__)


class Entry:
    """ Encapsulates a local entry """
    # pylint:disable=too-few-public-methods

    def __init__(self, url, previous=None):
        request = requests.get(url, headers=caching.make_headers(previous))

        md5 = hashlib.md5(request.text.encode('utf-8'))

        self.text = request.text
        self.digest = md5.digest()
        self.url = request.url  # the canonical, final URL
        self.status_code = request.status_code
        self.headers = request.headers


@functools.lru_cache()
def get_entry(url, cache=None):
    """ Given an entry URL, return the entry document

    Arguments:

    url -- the URL of the entry
    cache -- the cache of previous results

    Returns: 3-tuple of (current, previous, updated) """

    previous = cache.get('entry', url) if cache else None

    try:
        current = Entry(url, previous)
    except requests.RequestException as error:
        LOGGER.warning("%s: %s", url, error)
        return None, None, False

    # Cache hit
    if current.status_code == 304:
        return previous, previous, False

    # Content updated
    if 200 <= current.status_code < 300:
        if cache:
            cache.set('entry', url, current)
        return current, previous, not previous or previous.digest != current.digest

    # An error occurred
    return None, previous, False


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


def _check_site(link, entry):
    """ Check that a link is not on the same site as the referring entry """
    target = urllib.parse.urlparse(link.attrs.get('href')).netloc.lower()
    if not target:
        return False

    origin = urllib.parse.urlparse(entry.url).netloc.lower()
    return target != origin


def get_top_nodes(entry):
    """ Given an Entry object, return all of the top-level entry nodes """
    soup = BeautifulSoup(entry.text, 'html.parser')
    return (soup.find_all(class_="h-entry")
            or soup.find_all("article")
            or soup.find_all(class_="entry")
            or [soup])


def get_targets(entry, rel_whitelist=None, rel_blacklist=None):
    """ Given an Entry object, return all of the outgoing links. """

    targets = set()
    for top_node in get_top_nodes(entry):
        targets = targets.union({urllib.parse.urljoin(entry.url, link.attrs['href'])
                                 for link in top_node.find_all('a')
                                 if _check_rel(link, rel_whitelist, rel_blacklist)
                                 and _check_site(link, entry)})

    return targets
