from django.http import HttpResponse

try:
    from django.shortcuts import reverse
except ImportError:
    from django.core.urlresolvers import reverse

from django.test import TestCase, RequestFactory, override_settings
from django_py_zipkin.middleware import ZipkinMiddleware
from django_py_zipkin.tasks import submit_to_zipkin
from base64 import b64encode
from mock import Mock, patch
import responses
import six


class ZipkinMiddlewareTest(TestCase):

    def setUp(self):
        self.factory = RequestFactory()

    @override_settings(
        ZIPKIN_TRACING_ENABLED=True,
        ZIPKIN_HTTP_ENDPOINT='http://127.0.0.1:9411/api/v1/spans',
        ZIPKIN_SERVICE_NAME='zipkin-test',
        ZIPKIN_TRACING_SAMPLING=1.00)
    @patch('django_py_zipkin.tasks.submit_to_zipkin')
    def test_zipkin_headers(self, patched_transport):
        response = HttpResponse()

        request = self.factory.get(
            '/', HTTP_X_B3_TRACEID='C0FF33', SERVER_NAME='127.0.0.1')
        mock_callback = Mock()
        mock_callback.return_value = response
        middleware = ZipkinMiddleware(mock_callback)
        middleware(request)
        mock_callback.assert_called_with(request)
        self.assertEqual(request.zipkin_trace_id, '0000000000C0FF33')
        self.assertTrue('x-cloud-trace-context' in response._headers)

    @override_settings(
        ZIPKIN_TRACING_ENABLED=True,
        ZIPKIN_HTTP_ENDPOINT='http://127.0.0.1:9411/api/v1/spans',
        ZIPKIN_SERVICE_NAME='zipkin-test',
        ZIPKIN_BLACKLISTED_PATHS=['^/$', '^/login/$'],
        ZIPKIN_TRACING_SAMPLING=1.00)
    @patch('django_py_zipkin.tasks.submit_to_zipkin')
    def test_zipkin_blacklist(self, patched_transport):
        response = HttpResponse()
        mock_callback = Mock()
        mock_callback.return_value = response

        middleware = ZipkinMiddleware(mock_callback)

        blacklisted = self.factory.get(
            '/', HTTP_X_B3_TRACEID='C0FF33', SERVER_NAME='127.0.0.1')
        middleware(blacklisted)
        not_blacklisted = self.factory.get(
            '/foo', HTTP_X_B3_TRACEID='C0FF33', SERVER_NAME='127.0.0.1')
        middleware(not_blacklisted)

        self.assertEqual(not_blacklisted.zipkin_is_tracing, True)
        self.assertEqual(blacklisted.zipkin_is_tracing, False)

        patched_transport.delay.assert_called()
        self.assertTrue('x-cloud-trace-context' in response._headers)

    @override_settings(
        ZIPKIN_TRACING_ENABLED=True,
        ZIPKIN_HTTP_ENDPOINT='http://127.0.0.1:9411/api/v1/spans',
        ZIPKIN_SERVICE_NAME='zipkin-test',
        ZIPKIN_BLACKLISTED_PATHS=['^/$', '^/login/$'],
        ZIPKIN_TRACING_SAMPLING=1.00)
    @responses.activate
    def test_zipkin_celery_submission(self):

        def cb(request):
            # This test could be better but I'm not sure I want to
            # invest the time to decode the encoded span any better
            self.assertTrue(six.b('foo') in request.body.read())
            return (200, {}, '')

        responses.add_callback(
            responses.POST, 'http://127.0.0.1:9411/api/v1/spans', cb,
            'application/x-thrift')

        submit_to_zipkin(b64encode(six.b('foo')))
        self.assertEqual(len(responses.calls), 1)

    @override_settings(
        ZIPKIN_TRACING_ENABLED=True,
        ZIPKIN_HTTP_ENDPOINT='http://127.0.0.1:9411/api/v1/spans',
        ZIPKIN_SERVICE_NAME='zipkin-test',
        ZIPKIN_BLACKLISTED_PATHS=['^/$', '^/login/$'],
        ZIPKIN_TRACING_SAMPLING=1.00)
    @responses.activate
    def test_integration(self):
        def cb(request):
            # This test could be better but I'm not sure I want to
            # invest the time to decode the encoded span any better
            self.assertTrue(six.b('foo') in request.body.read())
            return (200, {}, '')

        responses.add_callback(
            responses.POST, 'http://127.0.0.1:9411/api/v1/spans', cb,
            'application/x-thrift')

        response = self.client.get(reverse('testing-view'))
        self.assertTrue(response.has_header('X-Cloud-Trace-Context'))
