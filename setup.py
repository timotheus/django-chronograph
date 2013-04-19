from setuptools import setup, find_packages

import chronograph
import os
import urllib

def setup_distribute():
    """
    This will download and install Distribute.
    """
    try:
        import distribute_setup
    except:
        # Make sure we have Distribute
        if not os.path.exists('distribute_setup'):
            urllib.urlretrieve('http://nightly.ziade.org/distribute_setup.py',
                               './distribute_setup.py')
        distribute_setup = __import__('distribute_setup')
    distribute_setup.use_setuptools()

def get_reqs(reqs=[]):
    # optparse is included with Python <= 2.7, but has been deprecated in favor
    # of argparse.  We try to import argparse and if we can't, then we'll add
    # it to the requirements
    try:
        import argparse
    except ImportError:
        reqs.append("argparse>=1.1")
    return reqs

# Make sure we have Distribute installed
setup_distribute()

setup(
    name = "django-chronograph",
    version = ".".join([str(i) for i in chronograph.VERSION]),
    packages = find_packages(),
    scripts = ['bin/chronograph'],
    package_data = {
        '': ['docs/*.txt', 'docs/*.py'],
        'chronograph': ['templates/*.*', 'templates/*/*.*', 'templates/*/*/*.*', 'fixtures/*'],
    },
    author = "Weston Nielson",
    author_email = "wnielson@gmail.com",
    description = "",
    license = "BSD",
    url = "http://bitbucket.org/wnielson/django-chronograph",
    classifiers = [
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Framework :: Django',
    ],
    zip_safe = False,
    install_requires = get_reqs(["Django>=1.0", "python-dateutil<=1.5"]),
    dependency_links = ['http://labix.org/download/python-dateutil/python-dateutil-1.5.tar.gz']
)
