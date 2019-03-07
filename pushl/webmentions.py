""" Functions for sending webmentions """

import urllib.parse
import logging
from abc import ABC, abstractmethod
import asyncio
from lxml import etree

from bs4 import BeautifulSoup

from . import caching

LOGGER = logging.getLogger(__name__)
SCHEMA_VERSION = 2


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
            async with config.session.post(self.endpoint,
                                           data={'source': entry,
                                                 'target': target
                                                 }) as request:
                result = request.status

                if 'retry-after' in request.headers:
                    retries -= 1
                    LOGGER.info("%s: retrying after %s seconds",
                                self.endpoint, request.headers['retry-after'])
                    asyncio.sleep(float(request.headers['retry-after']))
                else:
                    break

        return 200 <= result < 300


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

        async with config.session.post(self.endpoint,
                                       data=body) as request:
            success = 200 <= request.status < 300
            if not success:
                LOGGER.warning("%s -> %s: Got status code %d",
                               entry, target, request.status)
            # someday I'll parse out the response but IDGAF

        return success


class Target:
    """ A target of a webmention """
    # pylint:disable=too-few-public-methods

    def __init__(self, request, text):
        self.url = str(request.url)  # the canonical, final URL
        self.status = request.status
        self.caching = caching.make_headers(request.headers)
        self.schema = SCHEMA_VERSION

        if 200 <= request.status < 300:
            self.endpoint = self._get_endpoint(request, text)
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
            LOGGER.debug("%s -> %s", entry.url, self.url)
            try:
                await self.endpoint.send(config, entry.url, self.url)
            except Exception as err:  # pylint:disable=broad-except
                LOGGER.warning("Ping %s: got %s: %s",
                               self.url, err.__class__.__name__, err)


async def get_target(config, url):
    """ Given a URL, get the webmention endpoint """

    previous = config.cache.get(
        'target', url, schema_version=SCHEMA_VERSION) if config.cache else None

    headers = previous.caching if previous else None

    try:
        async with config.session.get(url, headers=headers) as request:
            text = (await request.read()).decode(request.get_encoding(), 'ignore')
            current = Target(request, text)
    except Exception as err:  # pylint:disable=broad-except
        LOGGER.warning("Target %s: got %s: %s",
                       url, err.__class__.__name__, err)
        return previous

    if current.status == 304:
        # cache hit
        return previous

    if config.cache:
        config.cache.set('target', url, current)

    return current
