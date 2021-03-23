"""Required packages for install and tests."""

import os
import re

from setuptools import setup, find_packages


install_requires = [
    'boto3>=1.9.66',
    'pandas>=1.2.0',
    'numpy>=1.19.4',
    'r-uuid>=0.1_4',
    'flask>=1.1.2'
]


tests_require = [
    'nose'
]


extras_require = {
    'tests': tests_require
}

# Get long project description text from the README.md file
with open('readme.md', 'rt') as f:
    readme = f.read()


setup(
    name='pie-flask',
    description='Library for ...',
    long_description=readme,
    long_description_content_type='text/markdown',
    keywords='...',
    url='https://github.com/CoraJung/pie-flask',
    author='Cora Hyun Jung',
    license='New BSD',
    license_file='LICENSE',
    packages=find_packages(),
    include_package_data=True,
    test_suite='nose.collector',
    extras_require=extras_require,
    tests_require=tests_require,
    install_requires=install_requires
    },
    classifiers=[
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python'
    ]
)
