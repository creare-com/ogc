import re
import sys

# Get version information
sys.path.insert(0, "ogc")  # Directory where actual code lives
import version


def test_version_semantics_match_three_number_pattern():
    """
    Test that the semantic version string matches the pattern "number.number.number".
    """
    semantic_version = version.semver()

    # Regular expression pattern for "number.number.number"
    pattern = r"^\d+\.\d+\.\d+$"

    assert re.match(pattern, semantic_version) is not None


def test_version_semantics_order_match_major_minor_hotfix():
    """
    Test that the semantic version string matches the order of major, minor, and hotfix.
    """
    semantic_version = version.semver()

    assert semantic_version == f"{version.MAJOR}.{version.MINOR}.{version.HOTFIX}"


def test_version_without_git(mocker):
    """
    Test the version function when git is not available.
    This test simulates the absence of git by mocking the path.exists function.

    Parameters
    ----------
    mocker : MockerFixture
        The mocker fixture provided by pytest-mock to mock functions and objects.
    """
    mocker.patch("os.path.exists", return_value=False)

    assert version.version() == version.semver()


def test_version_with_git(mocker):
    """
    Test the version function when git is available.
    This test simulates the presence of git by mocking the subprocess.check_output and path.exists functions.

    Parameters
    ----------
    mocker : MockerFixture
        The mocker fixture provided by pytest-mock to mock functions and objects.
    """
    expected_version_output = "v1.2.3+14.test25"

    def subprocess_command_side_effect(cmd, cwd=None):
        """
        Mock the subprocess command to simulate git versioning.

        Parameters
        ----------
        cmd : list
            The command to be executed
        cwd : str, optional
            The current working directory for the command

        Returns
        -------
        bytes
            The output of the command as bytes.

        Raises
        ------
        ValueError
            If the command is not recognized.
        """
        mock_git_describe_response = b"v1.2.3-14-test25\n"
        mock_git_version_response = b"git version 2.25.1\n"

        if cmd == ["git", "describe", "--always"]:
            return mock_git_describe_response
        if cmd == ["git", "--version"]:
            return mock_git_version_response
        raise ValueError(f"Unmocked subprocess call: {cmd} with cwd {cwd}")

    mocker.patch("subprocess.check_output", side_effect=subprocess_command_side_effect)
    mocker.patch("os.path.exists", return_value=True)

    version_full = version.version()
    assert version_full == expected_version_output
