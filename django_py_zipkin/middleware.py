import struct
import re
import random

from django.conf import settings
from django.utils.module_loading import import_string

from py_zipkin.util import generate_random_64bit_string
from py_zipkin.zipkin import ZipkinAttrs, zipkin_span


# NOTE: this is largely ported from
#       https://github.com/Yelp/pyramid_zipkin/blob/master
#           /pyramid_zipkin/request_helper.py

def get_trace_id(request):
    """Gets the trace id based on a request. If not present with the request,
    create a completely random trace id.
    :param: current active Django request
    :returns: a 64-bit hex string
    """
    if 'HTTP_X_B3_TRACEID' in request.META:
        trace_id = _convert_signed_hex(request.META['HTTP_X_B3_TRACEID'])
        # Tolerates 128 bit X-B3-TraceId by reading the right-most 16 hex
        # characters (as opposed to overflowing a U64 and starting a new
        # trace).
        trace_id = trace_id[-16:]
    else:
        trace_id = generate_random_64bit_string()

    return trace_id


def _convert_signed_hex(s):
    """Takes a signed hex string that begins with '0x' and converts it to
    a 16-character string representing an unsigned hex value.
    Examples:
        '0xd68adf75f4cfd13' => 'd68adf75f4cfd13'
        '-0x3ab5151d76fb85e1' => 'c54aeae289047a1f'
    """
    if s.startswith('0x') or s.startswith('-0x'):
        s = '{0:x}'.format(struct.unpack('Q', struct.pack('q', int(s, 16)))[0])
    return s.zfill(16)


def get_binary_annotations(request, response):
    """Helper method for getting all binary annotations from the request.
    :param request: the Pyramid request object
    :param response: the Pyramid response object
    :returns: binary annotation dict of {str: str}
    """
    return {
        # These are tracked by opentracing
        'http.uri': request.path,
        'http.uri.qs': request.META['QUERY_STRING'],
        'response.status_code': str(response.status_code),

        # These are tracked by Google Tracing
        '/http/url': request.path,
        '/http/user_agent': request.META.get('HTTP_USER_AGENT', ''),
        '/http/status_code': str(response.status_code),
        '/http/method': request.method,
    }


class ZipkinMiddleware(object):

    def __init__(self, get_response=None):
        self.get_response = get_response
        self.transport_handler = import_string(
            getattr(
                settings,
                'ZIPKIN_TRANSPORT_HANDLER',
                'django_py_zipkin.transport.zipkin_transport'))
        self.service_name = getattr(
            settings, 'ZIPKIN_SERVICE_NAME', 'unknown')
        self.add_logging_annotation = getattr(
            settings, 'ZIPKIN_ADD_LOGGING_ANNOTATION', True)
        self.enable_tracing = getattr(
            settings, 'ZIPKIN_TRACING_ENABLED', False)
        self.sampling_treshold = float(getattr(
            settings, 'ZIPKIN_TRACING_SAMPLING', 1.00))
        self.blacklisted_paths = [
            re.compile(path) for path in
            getattr(settings, 'ZIPKIN_BLACKLISTED_PATHS', [])]

    def should_not_sample_path(self, request):
        return any([
            r.match(request.path) for r in self.blacklisted_paths])

    def is_tracing(self, request):
        if getattr(request, 'zipkin_is_tracing', None) is not None:
            return request.zipkin_is_tracing
        if self.should_not_sample_path(request):
            return False
        elif 'HTTP_X_B3_SAMPLED' in request.META:
            return request.META.get('HTTP_X_B3_SAMPLED') == '1'
        else:
            zipkin_is_tracing = random.random() < self.sampling_treshold
            setattr(request, 'zipkin_is_tracing', zipkin_is_tracing)
            return zipkin_is_tracing

    def add_zipkin_to_request(self, request):
        if not (self.enable_tracing and self.is_tracing(request)):
            setattr(request, 'zipkin_is_tracing', False)
            setattr(request, 'zipkin_trace_id', None)
            setattr(request, 'zipkin_span_id', None)
            setattr(request, 'zipkin_parent_span_id', None)
            setattr(request, 'zipkin_flags', None)
            setattr(request, 'zipkin_tracer', {
                'is_tracing': request.zipkin_is_tracing,
            })
            return

        span_id = request.META.get(
            'HTTP_X_B3_SPANID', generate_random_64bit_string())
        parent_span_id = request.META.get('HTTP_X_B3_PARENTSPANID', None)
        flags = request.META.get('HTTP_X_B3_FLAGS', '0')

        setattr(request, 'zipkin_is_tracing', True)
        setattr(request, 'zipkin_trace_id', get_trace_id(request))
        setattr(request, 'zipkin_span_id', span_id)
        setattr(request, 'zipkin_parent_span_id', parent_span_id)
        setattr(request, 'zipkin_flags', flags)
        setattr(request, 'zipkin_tracer', {
            'is_tracing': request.zipkin_is_tracing,
            'trace_id': request.zipkin_trace_id,
            'span_id': request.zipkin_span_id,
            'parent_span_id': request.zipkin_parent_span_id,
            'flags': request.zipkin_flags
        })

    def get_zipkin_context(self, request):
        span_name = '{0} {1}'.format(request.method, request.path)

        # If the incoming request doesn't have Zipkin headers, this request is
        # assumed to be the root span of a trace.
        report_root_timestamp = 'HTTP_X_B3_TRACEID' not in request.META

        return zipkin_span(
            service_name=self.service_name,
            span_name=span_name,
            zipkin_attrs=ZipkinAttrs(
                trace_id=request.zipkin_trace_id,
                span_id=request.zipkin_span_id,
                parent_span_id=request.zipkin_parent_span_id,
                flags=request.zipkin_flags,
                is_sampled=True,
            ),
            transport_handler=self.transport_handler,
            add_logging_annotation=self.add_logging_annotation,
            report_root_timestamp=report_root_timestamp,
        )

    def __call__(self, request):
        self.add_zipkin_to_request(request)

        if not (self.enable_tracing and self.is_tracing(request)):
            return self.get_response(request)

        with self.get_zipkin_context(request) as zipkin_context:
            response = self.get_response(request)
            response["X-Cloud-Trace-Context"] = "%s/%s;o=1" % (
                request.zipkin_trace_id, request.zipkin_parent_span_id or 0)
            zipkin_context.update_binary_annotations(
                get_binary_annotations(request, response),
            )
            return response

    def process_request(self, request):
        """
        Compatibility for older versions of Django.
        """
        if not (self.enable_tracing and self.is_tracing(request)):
            return

        self.add_zipkin_to_request(request)
        zipkin_context = self.get_zipkin_context(request)
        setattr(request, 'zipkin_context', zipkin_context)
        zipkin_context.start()

    def process_response(self, request, response):
        """
        Compatibility for older versions of Django.
        """
        zipkin_context = getattr(request, 'zipkin_context', None)
        if zipkin_context is None:
            return response

        response["X-Cloud-Trace-Context"] = "%s/%s;o=1" % (
            request.zipkin_trace_id, request.zipkin_parent_span_id or 0)
        zipkin_context.update_binary_annotations(
            get_binary_annotations(request, response),
        )
        zipkin_context.stop()
        return response
