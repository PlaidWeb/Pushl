""" Simple caching functions """

import pickle
import logging
import hashlib
import os

LOGGER = logging.getLogger(__name__)


class Cache:
    """ A very simple file-based object cache """

    def __init__(self, cache_dir=None):
        self.cache_dir = cache_dir

    def _get_cache_file(self, url):
        if not self.cache_dir:
            return None
        md5 = hashlib.md5(url.encode('utf-8'))
        return os.path.join(self.cache_dir, md5.hexdigest())

    def get(self, url):
        """ Get the cached object """
        if not self.cache_dir:
            return None

        filename = self._get_cache_file(url)
        try:
            return pickle.load(open(filename, "rb"))
        except IOError:
            pass
        except:  # pylint:disable=bare-except
            LOGGER.exception(
                "Error reading cache file %s for URL %s", filename, url)

        return None

    def set(self, url, obj):
        """ Add an object into the cache """
        if not self.cache_dir:
            return None

        try:
            os.makedirs(self.cache_dir)
        except OSError:
            pass

        filename = self._get_cache_file(url)
        return pickle.dump(obj, open(filename, 'wb'))
