""" Functions for sending WebSub notifications """

import logging

from . import utils

LOGGER = logging.getLogger(__name__)


async def send(config, url, hub):
    """ Update WebSub hub to know about this URL """
    try:
        LOGGER.debug("WebSub: Notifying %s of %s", hub, url)
        request = await utils.retry_post(
            config,
            hub,
            data={
                'hub.mode': 'publish',
                'hub.url': url
            })

        if request.success:
            LOGGER.info("%s: WebSub notification sent to %s",
                        url, hub)
        else:
            LOGGER.warning("%s: Hub %s returned status code %s: %s", url, hub,
                           request.status, request.text)
    except Exception as err:  # pylint:disable=broad-except
        LOGGER.warning("WebSub %s: got %s: %s",
                       hub, err.__class__.__name__, err)
