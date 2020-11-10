Django-py-zipkin
================

Django middleware and tracing utilities for submitting traces to Zipkin.
py2 / py3 compatible.

Usage
~~~~~

Set the settings, if not set it'll use defaults:

*ZIPKIN_SERVICE_NAME*: ``unknown``
    The name to use when identifying the service being traced.

*ZIPKIN_TRANSPORT_HANDLER*: ``django_py_zipkin.transport.zipkin_transport``
    Transport to use to submit traces to Zipkin. The default one submits
    in the background via Celery.

*ZIPKIN_ADD_LOGGING_ANNOTATION*: ``True``
    Whether to add a 'logging_end' annotation when py_zipkin
    finishes logging spans

*ZIPKIN_TRACING_ENABLED*: ``False``
    Whether or not to enable tracing, requires explicit enabling.

*ZIPKIN_TRACING_SAMPLING*: ``1.00``
    The sampling threshold

*ZIPKIN_BLACKLISTED_PATHS*: ``[]``
    List of regular expressions to ignore from tracing.

Add the middleware:

.. code:: python

    MIDDLEWARE = [
        ...
        'django_py_zipkin.middleware.ZipkinMiddleware',
        ...
    ]

Or instrument your code with the context manager:

.. code:: python

    with trace('span-name', request.zipkin_tracer) as context:
        traced_value = do_something_that_takes_time()
        context.update({
            'some.key': traced_value,
        })

