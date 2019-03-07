""" Utility functions """

import re


def guess_encoding(request):
    """ Try to guess the encoding of a request without going through the slow chardet process"""
    ctype = request.headers.get('content-type')

    # explicit declaration
    match = re.search(r'charset=([^ ;]*)(;| |$)', ctype)
    if match:
        return match[1]

    # html default
    if ctype.startswith('text/html'):
        return 'iso-8859-1'

    # everything else's default
    return 'utf-8'
