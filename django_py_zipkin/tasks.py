import six
from base64 import b64decode

from celery import shared_task
from celery.utils.log import get_task_logger

import requests

logger = get_task_logger(__name__)


@shared_task
def submit_to_zipkin(b64_encoded_span, endpoint=None):
    from django.conf import settings
    endpoint = endpoint or settings.ZIPKIN_HTTP_ENDPOINT
    body = six.BytesIO()
    body.write(b'\x0c\x00\x00\x00\x01')  # Thrift header
    body.write(b64decode(b64_encoded_span))
    body.seek(0)  # Rewind
    resp = requests.post(
        endpoint, data=body, headers={
            'Content-Type': 'application/x-thrift',
        })
    resp.raise_for_status()
    return resp
