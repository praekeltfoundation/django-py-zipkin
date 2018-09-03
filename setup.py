#!/usr/bin/env python
# -*- coding: utf-8 -*-


try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup


with open('README.rst') as readme_file:
    readme = readme_file.read()

with open('requirements.txt') as req_file:
    requirements = req_file.read().split('\n')

with open('requirements-dev.txt') as req_file:
    requirements_dev = req_file.read().split('\n')

with open('VERSION') as fp:
    version = fp.read().strip()

setup(
    name='django-py-zipkin',
    version=version,
    description="py3 compatible zipkin for Django",
    long_description=readme,
    author="Simon de Haan",
    author_email='simon@praekelt.org',
    url='https://github.com/praekeltfoundation/django-py-zipkin',
    packages=[
        'django_py_zipkin',
    ],
    package_dir={'django_py_zipkin':
                 'django_py_zipkin'},
    extras_require={
        'dev': requirements_dev,
    },
    include_package_data=True,
    install_requires=requirements,
    entry_points={},
    zip_safe=False,
    keywords='zipkin',
    classifiers=[
        'Intended Audience :: Developers',
        'Natural Language :: English',
        'Programming Language :: Python :: 3.6',
    ]
)
