""" Functions for sending webmentions """

import urllib.parse
import logging
import functools
import xmlrpc.client
from abc import ABC, abstractmethod

import requests.exceptions
import defusedxml.xmlrpc
from bs4 import BeautifulSoup

from . import caching

LOGGER = logging.getLogger(__name__)
SCHEMA_VERSION = 1

defusedxml.xmlrpc.monkey_patch()


class Endpoint(ABC):
    """ Base class for target endpoints """
    # pylint:disable=too-few-public-methods

    def __init__(self, config, endpoint):
        self.config = config
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
            request = self.config.session.post(self.endpoint, data={
                'source': entry,
                'target': target
            }, timeout=self.config.timeout)
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

    def __init__(self, config, request):
        self.url = request.url  # the canonical, final URL
        self.status_code = request.status_code
        self.headers = request.headers
        self.schema = SCHEMA_VERSION

        if 200 <= request.status_code < 300:
            self.endpoint = self._get_endpoint(config, request)
        else:
            self.endpoint = None

    @staticmethod
    def _get_endpoint(config, request):
        def join(url):
            return urllib.parse.urljoin(request.url, url)

        for rel, link in request.links.items():
            if link.get('url') and 'webmention' in rel.split():
                return WebmentionEndpoint(config, join(link.get('url')))

        if 'X-Pingback' in request.headers:
            return PingbackEndpoint(config, join(request.headers['X-Pingback']))

        # Don't try to get a link tag out of a non-text document
        ctype = request.headers.get('content-type')
        if 'html' not in ctype and 'xml' not in ctype:
            return None

        soup = BeautifulSoup(request.text, 'html.parser')
        for link in soup.find_all(('link', 'a'), rel='webmention'):
            if link.attrs.get('href'):
                return WebmentionEndpoint(config,
                                          urllib.parse.urljoin(request.url,
                                                               link.attrs['href']))
        for link in soup.find_all(('link', 'a'), rel='pingback'):
            if link.attrs.get('href'):
                return PingbackEndpoint(config,
                                        urllib.parse.urljoin(request.url,
                                                             link.attrs['href']))

        return None

    def send(self, entry):
        """ Send a webmention to this target from the specified entry """
        if self.endpoint:
            LOGGER.debug("%s -> %s", entry.url, self.url)
            self.endpoint.send(entry.url, self.url)


@functools.lru_cache()
def get_target(config, url):
    """ Given a URL, get the webmention endpoint """

    previous = config.cache.get(
        'target', url, schema_version=SCHEMA_VERSION) if config.cache else None

    try:
        request = config.session.get(
            url, headers=caching.make_headers(previous), timeout=config.timeout)
        current = Target(config, request)
    except (TimeoutError, requests.exceptions.RequestException):
        return None

    if current.status_code == 304:
        # cache hit
        return previous

    if config.cache:
        config.cache.set('target', url, current)

    return current
