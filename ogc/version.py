"""Project Version

Attributes
----------
VERSION : OrderedDict
    dict of project version {('MAJOR': int), ('MINOR': int), ('HOTFIX': int)}
VERSION_INFO : tuple of int
    (MAJOR, MINOR, HOTFIX)
"""

import subprocess
import os
from collections import OrderedDict

#########################
## UPDATE VERSION HERE ##
#########################
MAJOR = 0
MINOR = 4
HOTFIX = 2
#########################


VERSION_INFO = OrderedDict([("MAJOR", MAJOR), ("MINOR", MINOR), ("HOTFIX", HOTFIX)])

VERSION = (VERSION_INFO["MAJOR"], VERSION_INFO["MINOR"], VERSION_INFO["HOTFIX"])


def semver():
    """Return semantic version of current Project installation

    Returns
    -------
    str
        Semantic version of the current Project installation
    """
    return ".".join([str(v) for v in VERSION])


def version():
    """Retrieve Project semantic version as string

    Returns
    -------
    str
        Semantic version if outside git repository
        Returns `git describe --always` if inside the git repository
    """

    version_full = semver()
    CWD = os.path.dirname(__file__)
    got_git = os.path.exists(os.path.join(os.path.dirname(__file__), "..", ".git"))
    if not got_git:
        return version_full
    try:
        # determine git binary
        git = "git"
        try:
            subprocess.check_output([git, "--version"])
        except Exception:
            git = "/usr/bin/git"
            try:
                subprocess.check_output([git, "--version"])
            except Exception as e:
                return version_full

        version_full = (
            subprocess.check_output([git, "describe", "--always"], cwd=CWD)
            .strip()
            .decode("ascii")
        )
        version_full = version_full.replace("-", "+", 1).replace(
            "-", "."
        )  # Make this consistent with PEP440

    except Exception as e:
        print("Could not determine Project version from git repo.\n" + str(e))

    return version_full
