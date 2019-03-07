""" Utility functions """

import re
import logging

LOGGER = logging.getLogger('utils')


def guess_encoding(request):
    """ Try to guess the encoding of a request without going through the slow chardet process"""
    ctype = request.headers.get('content-type')

    # explicit declaration
    match = re.search(r'charset=([^ ;]*)(;| |$)', str(ctype))
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
        self.text = data.decode(guess_encoding(request), 'ignore')

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

async def _retry_do(session, func, url):
    retries = 5
    while retries > 0:
        retries -= 1
        try:
            async with func(url) as request:
                return RequestResult(request, await request.read())
        except Exception as err:
            logging.INFO("%s: got error %s %s", url,
                         err.__class__.__name__, err)

    logging.WARNING("%s: Exceeded maximum retries")
    return None


async def retry_get(session, url, *args, **kwargs):
    """ aiohttp wrapper for GET """
    return await _retry_do(session, (lambda url: session.get(url, *args, **kwargs)), url)


async def retry_post(session, url, *args, **kwargs):
    """ aiohttp wrapper for POST """
    return await _retry_do(session, (lambda url: session.post(url, *args, **kwargs)), url)
