#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
LASIF (LArge-scale Seismic Inversion Framework)

Data management for seismological full seismic waveform inversions using the
Salvus suite of tools.

:copyright:
    Lion Krischer (krischer@geophysik.uni-muenchen.de),
    Solvi Thrastarson (soelvi.thrastarson@erdw.ethz.ch),
    Dirk-Philip van Herwaarden (dirkphilip.vanherwaarden@erdw.ethz.ch),
    Andreas Fichtner (A.Fichtner@uu.nl) 2012-2020
:license:
    GNU General Public License, Version 3
    (http://www.gnu.org/copyleft/gpl.html)
"""
import inspect
import os
import sys
from setuptools import setup, find_packages


# Be very visible with the requires Python version!
# _v = sys.version_info
# if (_v.major, _v.minor) != (3, 7):
#    print("\n\n============================================")
#    print("============================================")
#    print("        LASIF 2 requires Python 3.7!        ")
#    print("============================================")
#    print("============================================\n\n")
#    raise Exception("LASIF 2 requires Python 3.7")


# Import the version string.
path = os.path.join(
    os.path.abspath(os.path.dirname(inspect.getfile(inspect.currentframe()))),
    "lasif",
)
sys.path.insert(0, path)
from version import get_git_version  # noqa


def get_package_data():
    """
    Returns a list of all files needed for the installation relativ to the
    "lasif" subfolder.
    """
    filenames = []
    # The lasif root dir.
    root_dir = os.path.join(
        os.path.dirname(
            os.path.abspath(inspect.getfile(inspect.currentframe()))
        ),
        "lasif",
    )
    # Recursively include all files in these folders:
    folders = [
        os.path.join(root_dir, "tests", "baseline_images"),
        os.path.join(root_dir, "tests", "data"),
    ]
    for folder in folders:
        for directory, _, files in os.walk(folder):
            for filename in files:
                # Exclude hidden files.
                if filename.startswith("."):
                    continue
                filenames.append(
                    os.path.relpath(
                        os.path.join(directory, filename), root_dir
                    )
                )
    return filenames


setup_config = dict(
    name="lasif",
    version="0.0.1",
    description="",
    author="Lion Krischer, Dirk-Philip van Herwaarden and Solvi Thrastarson",
    author_email="soelvi.thrastarson@erdw.ethz.ch",
    url="https://github.com/dirkphilip/LASIF_2.0",
    packages=find_packages(),
    python_requires="~=3.7",
    license="GNU General Public License, version 3 (GPLv3)",
    platforms="OS Independent",
    classifiers=[
        "Environment :: Console",
        "Intended Audience :: Science/Research",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3.7",
        "Topic :: Scientific/Engineering",
        "Topic :: Scientific/Engineering :: Physics",
    ],
    install_requires=[
        "scipy",
        "cmasher",
        "cartopy>=0.20.2",
        "obspy",
        "pyasdf",
        "progressbar",
        "colorama",
        "joblib",
        "pytest",
        "nose",
        "mock",
        "pip",
        "sphinx",
        "sphinx_rtd_theme",
        "seaborn",
        "numexpr",
        "ipython",
        "dill",
        "prov",
        "pandas",
        "h5py",
        "pyqtgraph",
        "ipykernel",
        "pathlib",
        "ipywidgets",
        "pyasdf",
        "pythreejs",
        "geographiclib",
        "flask-cache",
        "geojson"],
    extras_require={
        "dev": [
            "black",
        ],
    },
    package_data={
        "lasif": get_package_data()},
    entry_points={
        "console_scripts": [
            "lasif = lasif.scripts.lasif_cli:main",
            "iris2quakeml = lasif.scripts.iris2quakeml:main",
        ]
    },
)


if __name__ == "__main__":
    setup(**setup_config)
