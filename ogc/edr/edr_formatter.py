from pygeoapi.formatter.base import BaseFormatter
from pygeoapi.util import to_json


class BaseEdrFormatter(BaseFormatter):
    """Base formatter for EDR data."""

    def __init__(self, formatter_def: dict):
        """Initialize the formatter.

        Parameters
        ----------
        formatter_def : dict
            The formatter definition.
        """

        super().__init__(formatter_def)
        self.mimetype = formatter_def["mimetype"]

    def write(self, options: dict | None = None, data: dict | None = None) -> str:
        """Generate data in the specified format.

        Parameters
        ----------
        options : dict, optional
            Formatting options, by default None.
        data : dict | None, optional
            Dictionary representation of the data, by default None.

        Returns
        -------
        str
            String representation of the data.
        """
        return to_json(data, True) if data is not None else ""


class GeoTiffFormatter(BaseEdrFormatter):
    """Formatter for GeoTIFF data. Defined for format link information to be populated."""

    def __init__(self, formatter_def: dict):
        """Initialize the formatter.

        Parameters
        ----------
        formatter_def : dict
            The formatter definition.
        """

        super().__init__(formatter_def)
        self.f = "geotiff"
        self.extension = "tiff"


class CoverageJsonFormatter(BaseEdrFormatter):
    """Formatter for CoverageJSON data. Defined for format link information to be populated."""

    def __init__(self, formatter_def: dict):
        """Initialize the formatter.

        Parameters
        ----------
        formatter_def : dict
            The formatter definition.
        """

        super().__init__(formatter_def)
        self.f = "coveragejson"
        self.extension = "json"
