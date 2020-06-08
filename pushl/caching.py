""" Simple caching functions """

import hashlib
import logging
import os
import pickle
import sys
import typing

from slugify import slugify

LOGGER = logging.getLogger(__name__)


class Cache:
    """ A very simple file-based object cache """

    def __init__(self, cache_dir: str):
        self.cache_dir = cache_dir

    def _get_cache_file(self, prefix: str, url: str):
        if not self.cache_dir:
            return None

        md5 = hashlib.md5(url.encode('utf-8'))
        filename = md5.hexdigest()[:8] + '.' + slugify(url)[:24]

        return os.path.join(self.cache_dir, prefix, filename)

    def get(self, prefix: str, url: str, schema_version=None):
        """ Get the cached object """
        if not self.cache_dir:
            return None

        filename = self._get_cache_file(prefix, url)

        try:
            LOGGER.debug("get %s %s -> %s", prefix, url, filename)
            with open(filename, 'rb') as file:
                item = pickle.load(file)
            if schema_version and schema_version != item.schema:
                LOGGER.debug("Cache get %s %s: Wanted schema %d, got %d",
                             prefix, url,
                             schema_version, item.schema)
                return None
            return item
        except FileNotFoundError:
            LOGGER.debug("Cache get %s %s [%s]: not found", prefix, url, filename)
        except Exception:  # pylint:disable=broad-except
            _, msg, _ = sys.exc_info()
            LOGGER.warning("Cache get %s %s failed: %s", prefix, url, msg)

        return None

    def set(self, prefix: str, url: str, obj):
        """ Add an object into the cache """
        if not self.cache_dir:
            return

        filename = self._get_cache_file(prefix, url)
        LOGGER.debug("set %s %s -> %s", prefix, url, filename)

        try:
            os.makedirs(os.path.join(self.cache_dir, prefix))
        except OSError:
            pass

        with open(filename, 'wb') as file:
            pickle.dump(obj, file)


def make_headers(headers: typing.Dict) -> typing.Dict[str, str]:
    """ Make the cache control headers based on a previous request's
    response headers
    """
    out = {}
    if 'etag' in headers:
        out['if-none-match'] = headers['etag']
    if 'last-modified' in headers:
        out['if-modified-since'] = headers['last-modified']
    return out
