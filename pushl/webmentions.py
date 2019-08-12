""" Functions for sending webmentions """

import asyncio
import logging
import urllib.parse
from abc import ABC, abstractmethod

import async_lru
from bs4 import BeautifulSoup
from lxml import etree

from . import caching, utils

LOGGER = logging.getLogger(__name__)
SCHEMA_VERSION = 3


class Endpoint(ABC):
    """ Base class for target endpoints """
    # pylint:disable=too-few-public-methods

    def __init__(self, endpoint):
        self.endpoint = endpoint

    @abstractmethod
    async def send(self, config, entry, target):
        """ Send the mention via this protocol """


class WebmentionEndpoint(Endpoint):
    """ Implementation of the webmention protocol """
    # pylint:disable=too-few-public-methods

    async def send(self, config, entry, target):
        LOGGER.info("Sending Webmention %s -> %s", entry, target)
        retries = 5
        while retries > 0:
            request = await utils.retry_post(config,
                                             self.endpoint,
                                             data={'source': entry,
                                                   'target': target
                                                   })

            if request and 'retry-after' in request.headers:
                retries -= 1
                LOGGER.info("%s: retrying after %s seconds",
                            self.endpoint, request.headers['retry-after'])
                asyncio.sleep(float(request.headers['retry-after']))
            else:
                if request:
                    text = request.text
                    LOGGER.debug("%s: %s gave response %s",
                                 self.endpoint, target, text)
                return request and request.success

        LOGGER.info("%s: no more retries", self.endpoint)
        return False


class PingbackEndpoint(Endpoint):
    """ Implementation of the pingback protocol """
    # pylint:disable=too-few-public-methods

    @staticmethod
    def _make_param(text):
        param = etree.Element('param')
        value = etree.Element('value')
        leaf = etree.Element('string')
        leaf.text = text
        value.append(leaf)
        param.append(value)
        return param

    async def send(self, config, entry, target):
        LOGGER.info("Sending Pingback %s -> %s", entry, target)

        root = etree.Element('methodCall')
        method = etree.Element('methodName')
        method.text = 'pingback.ping'
        root.append(method)

        params = etree.Element('params')
        root.append(params)

        params.append(self._make_param(entry))
        params.append(self._make_param(target))

        body = etree.tostring(root,
                              xml_declaration=True)

        request = await utils.retry_post(config,
                                         self.endpoint,
                                         data=body)
        if not request:
            LOGGER.info("%s: failed to send ping")
            return False

        if not request.success:
            LOGGER.info("%s -> %s: Got status code %d",
                        entry, target, request.status)
            # someday I'll parse out the response but IDGAF

        return request.success


class Target:
    """ A target of a webmention """
    # pylint:disable=too-few-public-methods

    def __init__(self, request):
        self.url = str(request.url)  # the canonical, final URL
        self.status = request.status
        self.caching = caching.make_headers(request.headers)
        self.schema = SCHEMA_VERSION

        if request.success and not request.cached:
            self.endpoint = self._get_endpoint(request, request.text)
        else:
            self.endpoint = None

    def _get_endpoint(self, request, text):
        def join(url):
            return urllib.parse.urljoin(self.url, str(url))

        for rel, link in request.links.items():
            if link.get('url') and 'webmention' in rel.split():
                return WebmentionEndpoint(join(link.get('url')))

        if 'X-Pingback' in request.headers:
            return PingbackEndpoint(join(request.headers['X-Pingback']))

        # Don't try to get a link tag out of a non-text document
        ctype = request.headers.get('content-type')
        if 'html' not in ctype and 'xml' not in ctype:
            return None

        soup = BeautifulSoup(text, 'html.parser')
        for link in soup.find_all(('link', 'a'), rel='webmention'):
            if link.attrs.get('href'):
                return WebmentionEndpoint(
                    urllib.parse.urljoin(self.url,
                                         link.attrs['href']))

        for link in soup.find_all(('link', 'a'), rel='pingback'):
            if link.attrs.get('href'):
                return PingbackEndpoint(
                    urllib.parse.urljoin(self.url,
                                         link.attrs['href']))

        return None

    async def send(self, config, entry):
        """ Send a webmention to this target from the specified entry """
        if self.endpoint:
            LOGGER.debug("%s -> %s via %s", entry.url, self.url, self.endpoint)
            try:
                await self.endpoint.send(config, entry.url, self.url)
            except Exception as err:  # pylint:disable=broad-except
                LOGGER.exception("Ping %s: got %s: %s",
                                 self.url, err.__class__.__name__, err)


@async_lru.alru_cache(maxsize=1000)
async def get_target(config, url):
    """ Given a URL, get the webmention endpoint """

    previous = config.cache.get(
        'target', url, schema_version=SCHEMA_VERSION) if config.cache else None

    headers = previous.caching if previous else None

    request = await utils.retry_get(config, url, headers=headers)
    if not request or not request.success:
        return previous

    if request.cached:
        return previous

    current = Target(request)

    if config.cache:
        config.cache.set('target', url, current)

    return current
