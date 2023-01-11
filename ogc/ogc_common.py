import logging

import lxml, lxml.etree
import numpy as np
import traitlets as tl

logger = logging.getLogger(__file__)

ALLOWED_SRS_VALUES = (
    "urn:ogc:def:crs:OGC:2:84",  # wgs84
    "urn:ogc:def:crs:EPSG:6.6:32618",  # used in an example
    "urn:ogc:def:crs:EPSG::26910",  # used in an example,
    "urn:ogc:def:crs:EPSG::4326",  # used in an example,
)


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
        """ Override this method with code that unpacks contents of XML into the traits object."""
        raise NotImplementedError("XML Parsing not implemented.")
        return self

    def load_from_kv(self, args):
        self._load_from_kv(args)

    def load_from_xml(self, xml_txt):
        xml_doc = lxml.etree.fromstring(xml_txt)
        self._load_xml_doc(xml_doc)


class OutputFormat(XMLNode):
    """"""

    value = tl.Unicode(default_value=None, allow_none=True)

    def validate(self):
        assert bool(self.value) is True, "error validating output format"
        # Can check here for specific allowed formats if desired, prob. not necessary.

    def to_xml(self):
        return "<OutputFormat>%s</OutputFormat>" % self.value


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
        return "<OutputFormat>%s</OutputFormat>" % self.value


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
        for val in (
            self.lower_corner[0],
            self.lower_corner[1],
            self.upper_corner[0],
            self.upper_corner[1],
        ):
            assert np.isfinite(val), "error: time values must be finite"

    def to_xml(self):
        raise NotImplementedError()
        return "<OutputFormat>%s</OutputFormat>" % self.value


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
        super(WCSException, self).__init__(exception_text)

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
""".format(
            self=self, exception_text=exception_text
        )
        return xml
