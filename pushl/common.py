""" common stuff for everyone to use """

import requests

session = requests.Session()  # pylint:disable=invalid-name


def set_pool_size(size):
    adapter = requests.adapters.HTTPAdapter(
        pool_connections=size, pool_maxsize=size)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
