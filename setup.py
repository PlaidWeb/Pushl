"""Setup for Publ packaging"""

# Always prefer setuptools over distutils
from setuptools import setup, find_packages
from os import path

import pushl

here = path.abspath(path.dirname(__file__))

# Get the long description from the README file
with open(path.join(here, 'README.md')) as f:
    long_description = f.read()

setup(
    name='Pushl',

    version=pushl.__version__,

    description='A conduit for pushing changes in a feed to the rest of the IndieWeb',

    long_description=long_description,

    long_description_content_type='text/markdown',

    url='https://github.com/PlaidWeb/Pushl',

    author='fluffy',
    author_email='fluffy@beesbuzz.biz',

    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Intended Audience :: End Users/Desktop',

        'License :: OSI Approved :: MIT License',

        'Natural Language :: English',

        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',

        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
        'Topic :: Internet :: WWW/HTTP :: Site Management :: Link Checking',
    ],

    keywords='publishing blog webmention websub push',

    packages=['pushl'],

    install_requires=[
        'requests',
        'feedparser',
        'beautifulsoup4',
        'awesome-slugify',
        'defusedxml'
    ],

    extras_require={
        'dev': ['pylint', 'twine'],
    },

    project_urls={
        'Bug Reports': 'https://github.com/PlaidWeb/Pushl/issues',
        'Funding': 'https://patreon.com/fluffy',
        'Source': 'https://github.com/PlaidWeb/Pushl/',
        'Discord': 'https://discord.gg/xADP3ja'
    },

    entry_points={
        'console_scripts': [
            'pushl = pushl.__main__:main'
        ]
    },

    python_requires=">=3.4",
)
