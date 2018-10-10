""" Functions for sending webmentions """

import urllib.parse
import logging
import functools

import requests
from bs4 import BeautifulSoup

from . import caching

LOGGER = logging.getLogger(__name__)


class Target:
    """ A target of a webmention """
    # pylint:disable=too-few-public-methods

    def __init__(self, url, previous=None):
        request = requests.get(url, headers=caching.make_headers(previous))

        self.url = request.url  # the canonical, final URL
        self.status_code = request.status_code
        self.headers = request.headers

        if 200 <= request.status_code < 300:
            self.endpoint = self._get_endpoint(request)
        else:
            self.endpoint = None

    @staticmethod
    def _get_endpoint(request):
        if 'webmention' in request.links:
            return request.links['webmention']['url']

        # Don't try to get a link tag out of a non-text document
        ctype = request.headers.get('content-type')
        if 'html' not in ctype and 'xml' not in ctype:
            return None

        soup = BeautifulSoup(request.text, 'html.parser')
        for link in soup.find_all('link'):
            if 'rel' in link.attrs and 'webmention' in link.attrs['rel']:
                return urllib.parse.urljoin(request.url, link.attrs['href'])

        return None

    def send(self, entry):
        """ Send a webmention to this target from the specified entry """
        if self.endpoint:
            LOGGER.debug("%s -> %s", entry.url, self.url)
            request = requests.post(self.endpoint, data={
                'source': entry.url,
                'target': self.url
            })
            if 200 <= request.status_code < 300:
                LOGGER.info("%s: ping of %s -> %s successful (%s)",
                            self.endpoint, entry.url, self.url, request.status_code)
            else:
                LOGGER.warning("%s: ping of %s -> %s failed (%s)",
                               self.endpoint, entry.url, self.url, request.status_code)
            return request
        return None


@functools.lru_cache()
def get_target(url, cache):
    """ Given a URL, get the webmention endpoint """

    previous = cache.get('target', url) if cache else None

    try:
        current = Target(url)
    except requests.RequestException as error:
        LOGGER.warning("%s: %s", url, error)
        return None

    # cache hit
    if current.status_code == 304:
        return previous

    cache.set('target', url, current)
    return current
