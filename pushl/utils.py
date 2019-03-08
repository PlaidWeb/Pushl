""" Utility functions """

import re
import logging
import sys

import aiohttp

LOGGER = logging.getLogger('utils')


def guess_encoding(request):
    """ Try to guess the encoding of a request without going through the slow chardet process"""
    ctype = request.headers.get('content-type')
    if not ctype:
        # we don't have a content-type, somehow, so...
        LOGGER.warning("%s: no content-type; headers are %s",
                       request.url, request.headers)
        return 'utf-8'

    # explicit declaration
    match = re.search(r'charset=([^ ;]*)(;| |$)', ctype)
    if match:
        return match[1]

    # html default
    if ctype.startswith('text/html'):
        return 'iso-8859-1'

    # everything else's default
    return 'utf-8'


class RequestResult:
    """ The results we need from a request """

    def __init__(self, request, data):
        self.url = request.url
        self.headers = request.headers
        self.status = request.status
        self.links = request.links
        if data:
            self.text = data.decode(guess_encoding(request), 'ignore')
        else:
            self.text = ''

    @property
    def success(self):
        """ Was this request successful? """
        return 200 <= self.status < 300 or self.cached

    @property
    def gone(self):
        """ Is this request for a deleted resource? """
        return self.status == 410

    @property
    def cached(self):
        """ Is this request for a cache hit? """
        return self.status == 304


async def _retry_do(func, url):
    retries = 5
    errors = set()
    while retries > 0:
        retries -= 1
        try:
            async with func(url) as request:
                if request.status == 304:
                    return RequestResult(request, None)
                return RequestResult(request, await request.read())
        except aiohttp.client_exceptions.ClientResponseError as err:
            LOGGER.warning("%s: got client response error: %s", url, str(err))
            return None
        except Exception:  # pylint:disable=broad-except
            exc_type, exc_value, _ = sys.exc_info()
            LOGGER.debug("%s: got error %s %s (retries=%d)", url,
                         exc_type, exc_value, retries)
            errors.add(exc_value)

    LOGGER.warning("%s: Exceeded maximum retries; errors: %s", url, errors)
    return None


async def retry_get(session, url, *args, **kwargs):
    """ aiohttp wrapper for GET """
    return await _retry_do((lambda url: session.get(url, *args, **kwargs)), url)


async def retry_post(session, url, *args, **kwargs):
    """ aiohttp wrapper for POST """
    return await _retry_do((lambda url: session.post(url, *args, **kwargs)), url)
