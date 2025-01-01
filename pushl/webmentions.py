""" Functions for sending webmentions """

import asyncio
import logging
import re
import typing
import urllib.parse
from abc import ABC, abstractmethod

import async_lru
from bs4 import BeautifulSoup

from . import caching, utils

LOGGER = logging.getLogger(__name__)
SCHEMA_VERSION = 5


class Endpoint(ABC):
    """ Base class for target endpoints """
    # pylint:disable=too-few-public-methods

    def __init__(self, endpoint: str):
        self.endpoint = endpoint

    @abstractmethod
    async def send(self, config, source: str, destination: str) -> bool:
        """ Send the mention via this protocol """


class WebmentionEndpoint(Endpoint):
    """ Implementation of the webmention protocol """
    # pylint:disable=too-few-public-methods

    async def send(self, config, source, destination):
        LOGGER.info("Sending Webmention %s -> %s [%s]",
                    source, destination, self.endpoint)
        retries = 5
        while retries > 0:

            data = {'source': source,
                    'target': destination,
                    }
            LOGGER.debug('POST %s %s', self.endpoint, data)
            request = await utils.retry_post(
                config,
                self.endpoint,
                data=data
            )

            if request and 'retry-after' in request.headers:
                retries -= 1
                LOGGER.info("%s: retrying %s after %s seconds",
                            self.endpoint, destination, request.headers['retry-after'])
                await asyncio.sleep(float(request.headers['retry-after']))
            else:
                if request:
                    LOGGER.info("%s: mention of %s -> %s %s: %s",
                                self.endpoint, source, destination,
                                "succeeded" if request.success else "failed",
                                request.text)
                return request and request.success

        LOGGER.info("%s: no more retries", self.endpoint)
        return False


class Target:
    """ A target of a webmention """
    # pylint:disable=too-few-public-methods

    def __init__(self, request):
        self.canonical = str(request.url)  # the canonical, final URL
        self.status = request.status
        self.caching = caching.make_headers(request.headers)
        self.schema = SCHEMA_VERSION

        if request.success and not request.cached:
            self.endpoint = self._get_endpoint(request, request.text)
        else:
            self.endpoint = None

    def _get_endpoint(self, request: utils.RequestResult, text: str) -> typing.Optional[Endpoint]:
        def join(url):
            return urllib.parse.urljoin(str(request.url), str(url))

        # only attempt to parse the page if it's HTML or XML
        ctype = request.headers.get('content-type')
        if ctype and ('html' in ctype or 'xml' in ctype):
            soup = BeautifulSoup(text, 'html.parser')
        else:
            soup = None

        # If there's a canonical URL for the page, use that
        if soup:
            for link in soup.find_all('link', rel='canonical', href=True):
                self.canonical = join(link.attrs['href'])
                LOGGER.debug('%s: got canonical URL %s',
                             request.url, self.canonical)

        # Response headers always take priority over page links
        for rel, link in request.links.items():
            if link.get('url') and 'webmention' in rel.split():
                return WebmentionEndpoint(join(link.get('url')))

        # attempt to parse the document (if parseable)
        if not soup:
            return None

        for link in soup.find_all(('link', 'a'), rel='webmention', href=True):
            return WebmentionEndpoint(join(link.attrs['href']))

        return None

    async def send(self, config, source: str, href: str):
        """ Send a mention from source to href via this target's endpoint """
        if self.endpoint:
            LOGGER.debug("%s: %s->%s via %s [%s]",
                         self.canonical,
                         source, href,
                         self.endpoint.endpoint, self.endpoint.__class__.__name__)
            try:
                await self.endpoint.send(config, source, href)
            except Exception as err:  # pylint:disable=broad-except
                LOGGER.exception("Ping %s(%s): got %s: %s",
                                 self.canonical, self.endpoint.endpoint,
                                 err.__class__.__name__, err)

            # If the resolved URL is different than the (de-fragmented) HREF URL,
            # show a warning since that can affect the validity of webmentions
            match = re.match('([^#]*)(#(.*))?', href)
            if match and self.canonical != match.group(1):
                LOGGER.warning("""\
For the best compatibility, URL %s (referenced from %s) should be updated to %s\
""",
                               href, source,
                               self.canonical + ('#' + match.group(3)
                                                 if match.group(3) else ''))


@async_lru.alru_cache(maxsize=1000)
async def get_target(config, url: str) -> typing.Tuple[typing.Optional[Target], int, bool]:
    """ Given a resolved URL, get the webmention endpoint """

    previous = config.cache.get(
        'target', url, schema_version=SCHEMA_VERSION) if config.cache else None

    headers = previous.caching if previous else None

    request = await utils.retry_get(config, url, headers=headers)
    if not request or not request.success:
        return previous, request.status if request else 0, False

    if request.cached:
        return previous, previous.status if previous else 0, True

    current = Target(request)

    if config.cache:
        config.cache.set('target', url, current)

    return current, request.status, False
