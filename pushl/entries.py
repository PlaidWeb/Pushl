""" Functions for handling entries """

import logging
import urllib.parse
import functools

from bs4 import BeautifulSoup
import requests
import ronkyuu

LOGGER = logging.getLogger(__name__)


class Entry:

    def __init__(self, url, previous=None):
        headers = {}
        if previous:
            if 'etag' in previous.headers:
                headers['if-none-match'] = previous.headers['etag']
            if 'last-modified' in previous.headers:
                headers['if-modified-since'] = previous.headers['last-modified']

        r = requests.get(url, headers=headers)

        self.text = r.text
        self.url = r.url  # the canonical, final URL
        self.status_code = r.status_code
        self.headers = r.headers


def get_entry(url, cache):
    """ Given an entry URL, return the entry document

    Arguments:

    url -- the URL of the entry
    cache -- the cache of previous results

    Returns: 3-tuple of (current, previous, updated) """

    previous = cache.get(url) if cache else None

    current = Entry(url, previous)

    # Cache hit
    if current.status_code == 304:
        return previous, previous, False

    # Content updated
    if 200 <= current.status_code < 300:
        cache.set(url, current)
        return current, previous, True

    # An error occurred
    return None, previous, False


def _check_rel(link, rel_whitelist, rel_blacklist):
    """ Check a link's relations against the whitelist or blacklist.

    First, this will reject based on blacklist.

    Next, if there is a whitelist, there must be at least one rel that matches.
    To explicitly allow links without a rel you can add None to the whitelist
    (e.g. ['in-reply-to',None])
    """

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


def get_targets(entry, rel_whitelist=None, rel_blacklist=None):
    """ Given an Entry object, return all of the outgoing links. """

    # Just use the whole document; eventually we want to filter this to only
    # links which live within an entry node
    soup = BeautifulSoup(entry.text, 'html.parser')

    return {urllib.parse.urljoin(entry.url, link.attrs['href'])
            for link in soup.find_all('a')
            if _check_rel(link, rel_whitelist, rel_blacklist)}


@functools.lru_cache()
def get_webmention_endpoint(target):
    """ Given a target URL, determine the webmention endpoint, if any """
    try:
        r = requests.get(target)
    except requests.RequestException:
        LOGGER.exception("Could not determine endpoint for %s", target)
        return None

    if not 200 <= r.status_code < 300:
        LOGGER.warning("Target %s got error code %d", target, r.status_code)
        return None

    if 'webmention' in r.links:
        return r.links['webmention']['url']

    # Don't try to get a link tag out of a non-text document
    ctype = r.headers.get('content-type')
    if 'html' not in ctype and 'xml' not in ctype:
        return None

    soup = BeautifulSoup(r.text, 'html.parser')
    for link in soup.find_all('link'):
        if 'rel' in link.attrs and 'webmention' in link.attrs['rel']:
            return urllib.parse.urljoin(target, link.attrs['href'])

    return None


def send_webmentions(entry, previous=None, rel_whitelist=None, rel_blacklist=None):
    """ Given an Entry object, send all outgoing webmentions

    Arguments:

    entry -- the current entry object
    previous -- the previous version of the entry object, if available
    rel_whitelist -- a list of whitelisted link relations (can include None)
    rel_blacklist -- a list of blacklisted link relations (can include None)

    Any link which was listed in the previous version but not the current version
    will also get an outgoing WebMention, per the WebMention specification (to cover
    link deletions).
    """

    targets = get_targets(entry, rel_whitelist, rel_blacklist)
    if previous:
        targets = targets.union(get_targets(
            previous, rel_whitelist, rel_blacklist))

    for target in targets:
        LOGGER.debug("%s -> %s", entry.url, target)
        endpoint = get_webmention_endpoint(target)
        if endpoint:
            r = requests.post(endpoint, data={
                'source': entry.url,
                'target': target
            })
            if 200 <= r.status_code < 300:
                LOGGER.info("%s: ping of %s successful (%s)",
                            endpoint, target, r.status_code)
            else:
                LOGGER.warning("%s: ping of %s failed (%s)",
                               endpoint, target, r.status_code)
