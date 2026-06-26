import logging
import string
import json
import lxml
import lxml.etree
import numpy as np
import traitlets as tl
from xml.sax.saxutils import escape
from typing import Any

logger = logging.getLogger(__file__)

ALLOWED_SRS_VALUES = (
    "urn:ogc:def:crs:OGC:2:84",  # wgs84
    "urn:ogc:def:crs:EPSG:6.6:32618",  # used in an example
    "urn:ogc:def:crs:EPSG::26910",  # used in an example,
    "urn:ogc:def:crs:EPSG::4326",  # used in an example,
)


class EscapeFormatter(string.Formatter):
    """Formatter that escapes all values before formatting."""

    def format_field(self, value: Any, format_spec: str) -> str:
        """Format a single field with escaping applied.

        Parameters
        ----------
        value : Any
            The value to be escaped and formatted.
        format_spec : str
            The format specification.

        Returns
        -------
        str
            The escaped and formatted string representation of the value.
        """
        escaped_value = escape(str(value))
        return format(escaped_value, format_spec)


class XMLNode(tl.HasTraits):
    """Base class for all Traits objects that correspond to XML schemas."""

    def validate(self):
        """Validate that values are valid, required fields are present, and values
        and are conceivable values for our system. Does not mean, for instance,
        that a request will necessarily be successful."""
        raise NotImplementedError("Validation not implemented.")

    def to_xml(self):
        raise NotImplementedError("XML Serialization not implemented.")

    def _load_xml_doc(self, xml_doc):
        """Override this method with code that unpacks contents of XML into the traits object."""
        raise NotImplementedError("XML Parsing not implemented.")

    def load_from_kv(self, args):
        self._load_from_kv(args)

    def load_from_xml(self, xml_txt):
        xml_doc = lxml.etree.fromstring(xml_txt)
        self._load_xml_doc(xml_doc)


class OutputFormat(XMLNode):
    """"""

    value = tl.Unicode(default_value=None, allow_none=True)

    # Allowed values of None mean that all values are allowed, an empty list means no values allowed
    allowed_values = tl.List(tl.Unicode(), default_value=None, allow_none=True)

    def validate(self):
        assert bool(self.value) is True, "error validating output format"

        if self.allowed_values is not None:
            assert self.value is not None and self.value.lower() in [
                allowed_value.lower() for allowed_value in self.allowed_values
            ], "error validating output format, value not in allowed values"


class BoundingBox(XMLNode):
    """
    A bounding box (or envelope) defining the spatial domain of this object.
    """

    crs = tl.Enum(values=ALLOWED_SRS_VALUES, default_value=tl.Undefined)
    lower_corner = tl.Tuple(tl.Float(), tl.Float())
    upper_corner = tl.Tuple(tl.Float(), tl.Float())

    def validate(self):
        for val in (
            self.lower_corner[0],
            self.lower_corner[1],
            self.upper_corner[0],
            self.upper_corner[1],
        ):
            assert np.isfinite(val), "error: bounding box must be all finite values"

    def to_xml(self):
        raise NotImplementedError()


class TemporalSubset(XMLNode):
    """
    Definition of subset of coverage temporal domain.
    """

    begin_position = tl.Unicode(default_value=None, allow_none=True)
    end_position = tl.Unicode(default_value=None, allow_none=True)

    time_resolution = tl.Enum(values=["", "P1D"])  # e.g., per 1 day

    time_position = tl.Unicode(default_value=None, allow_none=True)

    def validate(self):
        raise NotImplementedError()

    def to_xml(self):
        raise NotImplementedError()


class WCSException(Exception):
    def __init__(
        self,
        exception_text="Internal application error.",
        exception_code="NoApplicableCode",
        locator="",
    ):
        """
        exception_code: 'NoApplicableCode', 'InvalidFormat', 'CoverageNotDefined', 'MissingParameterValue', 'InvalidParameterValue'
        """
        super().__init__(exception_text, exception_code, locator)

        self.exception_text = exception_text
        self.exception_code = exception_code
        self.locator = locator

    def to_xml(self):
        import xml.sax.saxutils

        exception_text = xml.sax.saxutils.escape(self.exception_text)
        xml = """\
<?xml version="1.0" encoding="UTF-8" ?>
<ExceptionReport version="1.0.0"
            xmlns="http://www.opengis.net/ows/1.1"
            xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
            xsi:schemaLocation="http://www.opengis.net/ows/1.1 owsExceptionReport.xsd">
    <Exception exceptionCode="{self.exception_code}" locator="{self.locator}"/>
    <ExceptionText>
        {exception_text}
    </ExceptionText>
</ExceptionReport>
""".format(self=self, exception_text=exception_text)
        return xml


class WMTSException(WCSException):
    """
    WMTS Exception based on the WCS Exception.
    This ensures it can still be caught as a WCS Exception which is the baseline handled server exception.
    """

    def __init__(
        self,
        exception_text="Internal application error.",
        exception_code="NoApplicableCode",
        locator="",
    ):
        """
        exception_code: 'NoApplicableCode', 'VersionNegotiationFailed',
        'InvalidUpdateSequence', 'MissingParameterValue', 'InvalidParameterValue',
        'OperationNotSupported', 'TileOutOfRange'
        """
        super().__init__(exception_text, exception_code, locator)


class EDRException(Exception):
    def __init__(
        self,
        status_code=500,
        exception_code="NoApplicableCode",
        exception_text="Internal application error.",
    ):
        """
        exception_code: 'NoApplicableCode', 'NotFound', 'InvalidParameterValue', 'InvalidQuery'
        """
        super().__init__(status_code, exception_text, exception_code)

        self.status_code = status_code
        self.exception_code = exception_code
        self.exception_text = exception_text

    def to_json(self) -> str:
        """Return JSON string for the exception.

        Returns
        -------
        str
            The exception in JSON string format.
        """
        return json.dumps(
            {
                "code": self.status_code,
                "type": self.exception_code,
                "description": self.exception_text,
            }
        )
