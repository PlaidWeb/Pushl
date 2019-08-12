"""Setup for Pushl packaging"""

from distutils.util import convert_path
from os import path

# Always prefer setuptools over distutils
from setuptools import setup

here = path.abspath(path.dirname(__file__))

# Get the long description from the README file
with open(path.join(here, 'README.md')) as f:
    long_description = f.read()

main_ns = {}
ver_path = convert_path('pushl/__version__.py')
with open(ver_path) as ver_file:
    exec(ver_file.read(), main_ns)

setup(
    name='Pushl',

    version=main_ns['__version__'],

    description='A conduit for pushing changes in a feed to the rest of the IndieWeb',

    long_description=long_description,

    long_description_content_type='text/markdown',

    url='https://github.com/PlaidWeb/Pushl',

    author='fluffy',
    author_email='fluffy@beesbuzz.biz',

    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Intended Audience :: End Users/Desktop',

        'License :: OSI Approved :: MIT License',

        'Natural Language :: English',

        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',

        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
        'Topic :: Internet :: WWW/HTTP :: Site Management :: Link Checking',
    ],

    keywords='publishing blog webmention websub push',

    packages=['pushl'],

    install_requires=[
        'feedparser',
        'beautifulsoup4',
        'awesome-slugify',
        'aiohttp',
        'lxml',
        'async_lru'
    ],

    extras_require={
        'dev': ['pylint', 'twine', 'flake8', 'isort', 'autopep8'],
    },

    project_urls={
        'Bug Reports': 'https://github.com/PlaidWeb/Pushl/issues',
        'Source': 'https://github.com/PlaidWeb/Pushl/',
        'Discord': 'https://beesbuzz.biz/discord',
        'Funding': 'https://liberapay.com/fluffy',
    },

    entry_points={
        'console_scripts': [
            'pushl = pushl.__main__:main'
        ]
    },

    python_requires=">=3.4",
)
