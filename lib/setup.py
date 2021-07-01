"""
Template for setup.py that is symlinked in the indidivual packages
    located at the path `./lib/<package-name>`. This script dynamically
    generates values that are used in the setup.py script.
"""
import os
import sys
import time

from setuptools import find_packages, setup

# Full path to the symbolic link location (which points to setup.py)
PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
VERSION_FN = "VERSION"  # Name of file with current version
INSTALL_REQUIRES_FN = "REQUIRES"  # Name of file with dependencies


def get_name() -> str:
    """ Get package name from the directory name """
    package_name = os.path.basename(PACKAGE_DIR)
    return package_name


def get_version() -> str:
    """ Get version from the VERSION file in the directory """
    with open(os.path.join(PACKAGE_DIR, VERSION_FN)) as version_file:
        version = version_file.read().strip()
    if version:
        version = version + "rc" + str(int(time.time()))
        return version
    else:
        print("VERSION file was empty.")
        sys.exit(1)


def install_requires() -> list:
    """ Get version from the VERSION file in the directory """
    requires_fp = os.path.join(PACKAGE_DIR, INSTALL_REQUIRES_FN)
    if os.path.exists(requires_fp):
        with open(requires_fp) as requires_file:
            requires_str = requires_file.read().strip()
            return list(filter(lambda r: r.strip(), requires_str.split("\n")))
    return []


NAME = get_name()
VERSION = get_version()
INSTALL_REQUIRES = install_requires()

setup(
    name=NAME,
    version=VERSION,
    author="Summ Technologies, Inc",
    author_email="jared@goflok.com",
    packages=find_packages("src"),
    package_dir={"": "src"},
    data_files=[("", [VERSION_FN])],
    install_requires=INSTALL_REQUIRES,
    setup_requires=["wheel"],
)
