""" Functions for sending webmentions """


class Target:
    """ A target of a webmention """

    def __init__(self, url, previous=None):
        r = requests.get(url, headers=caching.make_headers(previous))

        md5 = hashlib.md5(r.text.encode('utf-8'))
        self.digest = md5.digest()

        self.url = r.url  # the canonical, final URL
        self.status_code = r.status_code
        self.headers = r.headers

        if 200 <= r.status_code < 300:
            self.endpoint = self._get_endpoint(r)
        else:
            self.endpoint = None

    @staticmethod
    def _get_endpoint(r)
        if 'webmention' in r.links:
            return r.links['webmention']['url']

        # Don't try to get a link tag out of a non-text document
        ctype = r.headers.get('content-type')
        if 'html' not in ctype and 'xml' not in ctype:
            return None

        soup = BeautifulSoup(r.text, 'html.parser')
        for link in soup.find_all('link'):
            if 'rel' in link.attrs and 'webmention' in link.attrs['rel']:
                return urllib.parse.urljoin(target, link.attrs['href'])

        return None

    def send(self, entry):
        """ Send a webmention to this target from the specified entry """
        if self.endpoint:
            LOGGER.debug("%s -> %s", entry.url, self.url)
            r = requests.post(self.endpoint, data={
                'source': entry.url,
                'target': self.url
            })
            if 200 <= r.status_code < 300:
                LOGGER.info("%s: ping of %s successful (%s)",
                            self.endpoint, self.url, r.status_code)
            else:
                LOGGER.warning("%s: ping of %s failed (%s)",
                               self.endpoint, self.url, r.status_code)


def get_target(url, cache):
    """ Given a URL, get the webmention endpoint """

    previous = cache.get('target', url) if cache else None
    current = Target(url)

    # cache hit
    if current.status_code == 304:
        return previous

    cache.set('target', url, current)
    return current
