#!/usr/bin/env python

from setuptools import setup, find_packages

setup(name='tap-ebay',
      version='0.3.0',
      description='Singer.io tap for extracting data from the Ebay API',
      author='Fishtown Analytics',
      url='http://fishtownanalytics.com',
      classifiers=['Programming Language :: Python :: 3 :: Only'],
      py_modules=['tap_ebay'],
      install_requires=[
          "singer-python==6.8.0",
          "backoff==2.2.1",
          "requests==2.34.2",
      ],
      extras_require={
        'dev': [
            'ipdb',
            'pylint',
            'pytest',
            'pytest-cov',
            'coverage',
        ]
      },
      entry_points='''
          [console_scripts]
          tap-ebay=tap_ebay:main
      ''',
      packages=find_packages(),
      package_data={
          'tap_ebay': [
              'schemas/*.json'
          ]
      })
