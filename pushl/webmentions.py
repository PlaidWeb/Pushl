""" Functions for sending webmentions """

import urllib.parse
import logging
import functools
import xmlrpc.client
from abc import ABC, abstractmethod

import defusedxml.xmlrpc
from bs4 import BeautifulSoup

from . import caching
from .common import session

LOGGER = logging.getLogger(__name__)
SCHEMA_VERSION = 1

defusedxml.xmlrpc.monkey_patch()


class Endpoint(ABC):
    """ Base class for target endpoints """
    # pylint:disable=too-few-public-methods

    def __init__(self, endpoint):
        self.endpoint = endpoint

    @abstractmethod
    def send(self, entry, target):
        """ Send the mention via this protocol """


class WebmentionEndpoint(Endpoint):
    """ Implementation of the webmention protocol """
    # pylint:disable=too-few-public-methods

    def send(self, entry, target):
        LOGGER.info("Sending Webmention %s -> %s", entry, target)
        try:
            request = session.post(self.endpoint, data={
                'source': entry,
                'target': target
            })
            if 'retry-after' in request.headers:
                LOGGER.warning("  %s retry-after %s",
                               self.endpoint, request.headers['retry-after'])
        except Exception as error:  # pylint:disable=broad-except
            LOGGER.warning('%s: %s', self.endpoint, error)

        return 200 <= request.status_code < 300


class PingbackEndpoint(Endpoint):
    """ Implementation of the pingback protocol """
    # pylint:disable=too-few-public-methods

    def send(self, entry, target):
        LOGGER.info("Sending Pingback %s -> %s", entry, target)
        server = xmlrpc.client.ServerProxy(self.endpoint)
        try:
            result = server.pingback.ping(entry, target)
            LOGGER.debug("%s: %s", self.endpoint, result)
            return True
        except Exception as error:  # pylint:disable=broad-except
            LOGGER.warning('%s: %s', self.endpoint, error)

        return False


class Target:
    """ A target of a webmention """
    # pylint:disable=too-few-public-methods

    def __init__(self, url, previous=None):
        request = session.get(url, headers=caching.make_headers(previous))

        self.url = request.url  # the canonical, final URL
        self.status_code = request.status_code
        self.headers = request.headers
        self.schema = SCHEMA_VERSION

        if 200 <= request.status_code < 300:
            self.endpoint = self._get_endpoint(request)
        else:
            self.endpoint = None

    @staticmethod
    def _get_endpoint(request):
        def join(url):
            return urllib.parse.urljoin(request.url, url)

        for rel, link in request.links.items():
            if link.get('url') and 'webmention' in rel.split():
                return WebmentionEndpoint(join(link.get('url')))

        if 'X-Pingback' in request.headers:
            return PingbackEndpoint(join(request.headers['X-Pingback']))

        # Don't try to get a link tag out of a non-text document
        ctype = request.headers.get('content-type')
        if 'html' not in ctype and 'xml' not in ctype:
            return None

        soup = BeautifulSoup(request.text, 'html.parser')
        for link in soup.find_all(('link', 'a'), rel='webmention'):
            if link.attrs.get('href'):
                return WebmentionEndpoint(urllib.parse.urljoin(request.url,
                                                               link.attrs['href']))
        for link in soup.find_all(('link', 'a'), rel='pingback'):
            if link.attrs.get('href'):
                return PingbackEndpoint(urllib.parse.urljoin(request.url,
                                                             link.attrs['href']))

        return None

    def send(self, entry):
        """ Send a webmention to this target from the specified entry """
        if self.endpoint:
            LOGGER.debug("%s -> %s", entry.url, self.url)
            self.endpoint.send(entry.url, self.url)


@functools.lru_cache()
def get_target(url, cache):
    """ Given a URL, get the webmention endpoint """

    previous = cache.get('target', url) if cache else None
    try:
        if previous.schema != SCHEMA_VERSION:
            previous = None
    except AttributeError:
        previous = None

    current = Target(url)

    # cache hit
    if current.status_code == 304:
        return previous

    cache.set('target', url, current)
    return current
