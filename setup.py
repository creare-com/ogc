"""
Open Geospatial Consortium (OGC) WCS and WMS Python server.

Currently Supports:
* WCS v1.0.0
* WMS v1.3.0
* PODPAC data sources
* FLASK web server
"""

import sys
import subprocess

# Always prefer setuptools over distutils
from setuptools import find_packages, setup
from setuptools.command.develop import develop

# Get version information
sys.path.insert(0, "ogc")  # Directory where actual code lives
import version

__version__ = version.version()

install_requires = [
    'podpac[datatype]',
    'flask',
    'lxml',
    'webob',
    'traitlets'
]

extras_require = {
    "dev": [
        # IDE
        "pylint>=1.0",  # Dependencies can be tagged to a version, but we recommend >= versioning
        # DOCUMENTATION
        "sphinx>=3.2",
        "sphinx-rtd-theme",
        "sphinx-autobuild",
        # TESTING
        "pytest",
        "pytest-cov",
        "pytest-html",
        "pytest-remotedata",
        "recommonmark",
        # FORMATTING
        "pre_commit",
        "black",
    ],
}

# set long description to readme
with open("README.md") as f:
    long_description = f.read()

all_reqs = []
for key, val in extras_require.items():
    if "key" == "dev":
        continue
    all_reqs += val
extras_require["all"] = all_reqs
extras_require["devall"] = all_reqs + extras_require["dev"]

# install pre-commit hooks after setup in develop mode
# This is used to automatically format the code
class PostDevelopCommand(develop):
    def run(self):
        try:
            subprocess.check_call(["pre-commit", "install"])
        except subprocess.CalledProcessError as e:
            print("Failed to install pre-commit hook")

        develop.run(self)


setup(
    # ext_modules=None,
    name="OGC",
    version=__version__,
    description="OGC WCS and WMS server",
    author="Creare",
    # url="https://Project.org",
    license="APACHE 2.0",  # Creare's preferred license
    classifiers=[
        # How mature is this project? Common values are
        # 3 - Alpha
        # 4 - Beta
        # 5 - Production/Stable
        "Development Status :: 3 - Alpha",
        # Indicate who your project is intended for
        "Intended Audience :: Developers",
        "Topic :: Scientific/Engineering :: GIS",
        # Pick your license as you wish (should match "license" above)
        "License :: OSI Approved :: Apache Software License",
        # Specify the Python versions you support here. In particular, ensure
        # that you indicate whether you support Python 2, Python 3 or both.
        "Programming Language :: Python 3",
    ],
    packages=find_packages(),
    install_requires=install_requires,
    extras_require=extras_require,
    cmdclass={"develop": PostDevelopCommand},
    long_description=long_description,
    long_description_content_type="text/markdown"
    # ADD ANY SHELL SCRIPTS HERE
    # entry_points = {
    #     'console_scripts' : []
    # }
)
