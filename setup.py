import sys
import subprocess

# Always prefer setuptools over distutils
from setuptools import setup
from setuptools.command.develop import develop

# Get version information
sys.path.insert(0, "ogc")  # Directory where actual code lives
import version

__version__ = version.version()


# install pre-commit hooks after setup in develop mode
# This is used to automatically format the code
class PostDevelopCommand(develop):
    def run(self):
        try:
            subprocess.check_call(["pre-commit", "install"])
        except subprocess.CalledProcessError:
            print("Failed to install pre-commit hook")

        develop.run(self)


setup(
    version=__version__,
    cmdclass={"develop": PostDevelopCommand},
    # ADD ANY SHELL SCRIPTS HERE
    # entry_points = {
    #     'console_scripts' : []
    # }
)
