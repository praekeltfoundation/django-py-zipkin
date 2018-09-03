import logging

from contextlib import contextmanager, suppress
from base64 import b64encode

from django.conf import settings
from django.utils.module_loading import import_string

from py_zipkin.util import generate_random_64bit_string
from py_zipkin.zipkin import ZipkinAttrs, zipkin_span


logger = logging.getLogger(__name__)


def zipkin_transport(encoded_span, endpoint=None):
    from django_py_zipkin.tasks import submit_to_zipkin
    submit_to_zipkin.delay(
        b64encode(encoded_span).decode('utf-8'),
        endpoint=endpoint)


@contextmanager
def trace(span_name, tracer, span_id=None, service_name=None):
    span_id = span_id or generate_random_64bit_string()
    service_name = service_name or settings.ZIPKIN_SERVICE_NAME
    if len(span_id) > 16:
        logger.warning('Span id %s for %s should be max 16 chars.' % (
            span_id, span_name))
    trace_id = (
        tracer.get('trace_id') or generate_random_64bit_string())
    parent_span_id = (
        tracer.get('span_id') or generate_random_64bit_string())
    flags = tracer.get('flags') or ''
    is_sampled = (True if tracer.get('is_tracing') else False)
    transport_handler = import_string(
        getattr(
            settings,
            'ZIPKIN_TRANSPORT_HANDLER',
            'django_py_zipkin.transport.zipkin_transport'))

    zipkin_enabled = getattr(settings, 'ZIPKIN_TRACING_ENABLED', False)

    span = zipkin_span(
        service_name=service_name,
        span_name=span_name,
        transport_handler=transport_handler,
        zipkin_attrs=ZipkinAttrs(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            flags=flags,
            is_sampled=is_sampled))

    ctx_mgr = span if zipkin_enabled else suppress()

    with ctx_mgr as zipkin_context:
        dict_context = {}
        yield dict_context
        if zipkin_enabled:
            zipkin_context.update_binary_annotations(dict_context)
