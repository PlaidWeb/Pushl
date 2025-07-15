""" Utility functions """

import asyncio
import logging
import ssl
import sys
import typing
import urllib.parse

import aiohttp
import bs4
from bs4 import BeautifulSoup

LOGGER = logging.getLogger('utils')


def decode_text(data: bytes, request: aiohttp.ClientResponse) -> str:
    """ Try to guess the encoding of a request without going through the slow chardet process"""
    ctype = request.headers.get('content-type', '')
    encoding = request.get_encoding()

    if not ctype:
        # we don't have a content-type, somehow, so...
        LOGGER.warning("%s: no content-type; headers are %s",
                       request.url, request.headers)

    # try to derive it from the document
    text = data.decode(encoding or 'utf-8', 'ignore')
    if 'html' in ctype:
        soup = BeautifulSoup(text, 'html.parser')
        meta = typing.cast(bs4.element.Tag, soup.find('meta', charset=True))
        if meta:
            encoding = meta.attrs['charset']
        else:
            meta = typing.cast(bs4.element.Tag,
                               soup.find('meta', {'http-equiv': True, 'content': True}))
            if meta and meta.attrs['http-equiv'].lower() == 'content-type':
                ctype = meta.attrs['content']

    # html default (or at least close enough)
    if not encoding and ctype in ('text/html', 'text/plain'):
        encoding = 'iso-8859-1'

    if not encoding or encoding == request.get_encoding():
        # use the already-decoded version
        return text

    return data.decode(encoding, 'ignore')


def get_domain(url: str) -> str:
    """ Get the domain part of a URL """
    return urllib.parse.urlparse(url).netloc.lower()


class RequestResult:
    """ The results we need from a request """

    def __init__(self, request: aiohttp.ClientResponse, data: typing.Optional[bytes]):
        self.url = request.url
        self.headers = request.headers.copy()
        self.status = request.status
        self.links = request.links
        if data:
            self.text = decode_text(data, request)
        else:
            self.text = ''

    @property
    def success(self) -> bool:
        """ Was this request successful? """
        return 200 <= self.status < 300 or self.cached or self.gone

    @property
    def gone(self) -> bool:
        """ Is this request for a deleted resource? """
        return self.status == 410

    @property
    def cached(self) -> bool:
        """ Is this request for a cache hit? """
        return self.status == 304


async def _retry_do(func: typing.Callable,
                    url: str, *args,
                    **kwargs) -> typing.Optional[RequestResult]:
    errors = set()
    for retries in range(5):
        try:
            async with func(url, *args, **kwargs) as request:
                if request.status == 304:
                    return RequestResult(request, None)
                return RequestResult(request, await request.read())
        except aiohttp.client_exceptions.ClientResponseError as err:
            LOGGER.warning("%s: got client response error: %s", url, str(err))
            return None
        except ssl.SSLError as err:
            LOGGER.warning(
                "%s: SSL error: %s", url, str(err))
            return None
        except Exception:  # pylint:disable=broad-except
            exc_type, exc_value, _ = sys.exc_info()
            LOGGER.debug("%s: got error %s %s (retry=%d)", url,
                         exc_type, exc_value, retries)
            errors.add(str(exc_value))
            await asyncio.sleep(retries)

    LOGGER.warning("%s: Exceeded maximum retries; errors: %s", url, errors)
    return None


def _make_headers(config, kwargs):
    """ Replace the kwargs with one where the headers include our user-agent """

    headers = kwargs.get('headers')
    headers = headers.copy() if headers is not None else {}
    headers['User-Agent'] = config.args.user_agent

    kwargs = kwargs.copy()
    kwargs['headers'] = headers
    return kwargs


async def retry_get(config, url, *args, **kwargs):
    """ aiohttp wrapper for GET """
    return await _retry_do(config.session.get, url, *args,
                           **_make_headers(config, kwargs))


async def retry_post(config, url, *args, **kwargs):
    """ aiohttp wrapper for POST """
    return await _retry_do(config.session.post, url, *args,
                           **_make_headers(config, kwargs))
