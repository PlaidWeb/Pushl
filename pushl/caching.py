""" Simple caching functions """

import pickle
import logging
import hashlib
import os
import threading

from slugify import slugify

LOGGER = logging.getLogger(__name__)


class Cache:
    """ A very simple file-based object cache """

    def __init__(self, cache_dir=None):
        self.cache_dir = cache_dir
        self.lock = threading.Lock()

    def _get_cache_file(self, prefix, url):
        if not self.cache_dir:
            return None

        md5 = hashlib.md5(url.encode('utf-8'))
        filename = md5.hexdigest()[:8] + '.' + slugify(url)[:24]

        return os.path.join(self.cache_dir, prefix, filename)

    def get(self, prefix, url, schema_version=None):
        """ Get the cached object """
        if not self.cache_dir:
            return None

        filename = self._get_cache_file(prefix, url)

        with self.lock:
            try:
                item = pickle.load(open(filename, "rb"))
                if schema_version and schema_version != item.schema:
                    LOGGER.debug("Wanted schema %d, got %d",
                                 schema_version, item.schema)
                    return None
                return item
            except:  # pylint:disable=bare-except
                pass

        return None

    def set(self, prefix, url, obj):
        """ Add an object into the cache """
        if not self.cache_dir:
            return None

        filename = self._get_cache_file(prefix, url)

        with self.lock:
            try:
                os.makedirs(os.path.join(self.cache_dir, prefix))
            except OSError:
                pass

            return pickle.dump(obj, open(filename, 'wb'))


def make_headers(headers):
    """ Make the cache control headers based on a previous request's
    response headers
    """
    out = {}
    if 'etag' in headers:
        out['if-none-match'] = headers['etag']
    if 'last-modified' in headers:
        out['if-modified-since'] = headers['last-modified']
    return out
