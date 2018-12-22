""" common stuff for everyone to use """

import requests

session = requests.Session()  # pylint:disable=invalid-name


def set_pool_size(size):
    """ Set the maximum connection size of the shared requests session """
    adapter = requests.adapters.HTTPAdapter(
        pool_connections=size, pool_maxsize=size)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
