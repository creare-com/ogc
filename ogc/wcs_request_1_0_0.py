import logging

import lxml, lxml.etree
import dateutil.parser
import traitlets as tl

from . import ogc_common
from . import settings

logger = logging.getLogger(__file__)


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

    def load_from_xml(self, xml_txt):
        xml_doc = lxml.etree.fromstring(xml_txt)
        self._load_xml_doc(xml_doc)


class Identifier(ogc_common.XMLNode):
    """
    Unambiguous identifier. Although there is no formal restriction on characters included, these identifiers shall be directly usable in GetCoverage operation requests for the specific server, whether those requests are encoded in KVP or XML. Each of these encodings requires that certain characters be avoided, encoded, or escaped (TBR).
    """

    value = tl.Unicode(default_value=None, allow_none=True)

    def validate(self):
        assert bool(self.value) is True, "WCS Coverage identifier validation error"

    def to_xml(self):
        return "<Identifier>%s</Identifier>" % self.value


class DescribeCoverage(ogc_common.XMLNode):
    """
    Request to a WCS to perform the DescribeCoverage operation.
    """

    service = tl.Unicode(default_value=None, allow_none=True)  # 'WCS')
    version = tl.Unicode(default_value=None, allow_none=True)

    identifiers = tl.List(trait=tl.Instance(klass=Identifier))

    def validate(self):
        assert (
            self.service == "WCS"
        ), "WCS Request validation error: service should be WCS"
        assert self.version.startswith(
            "1.0.0"
        ), "WCS Request validation error: version should be 1.0.0"

        for obj in self.identifiers:
            obj.validate()

    def _load_from_kv(self, args):
        assert args["request"] == "DescribeCoverage", args["request"]
        self.service = args["service"].upper()
        self.version = args["version"]

        identifiers = [
            Identifier(value=identifier.strip())
            for identifier in args["coverage"].split(",")
        ]
        # assert len(identifiers) == 1, 'Multiple identifiers not yet supported: ' + repr(identifiers)
        self.identifiers = identifiers


class GetCapabilities(ogc_common.XMLNode):
    """
    Request to a WCS server to perform the GetCapabilities operation. This operation allows a client to retrieve a Capabilities XML document providing metadata for the specific WCS server. In this XML encoding, no "request" parameter is included, since the element name specifies the specific operation.
    """

    service = tl.Unicode(default_value=None, allow_none=True)  # 'WCS')

    accept_versions = tl.List(trait=tl.Unicode(default_value=None, allow_none=True))
    accept_formats = tl.List(trait=tl.Instance(klass=ogc_common.OutputFormat))

    def validate(self):
        assert (
            self.service == "WCS"
        ), "WCS Request validation error: service should be WCS"

        for obj in self.accept_formats:
            obj.validate()

    def _load_from_kv(self, args):
        assert args["request"] == "GetCapabilities", args["request"]
        self.service = args["service"].upper()

    def _load_xml_doc(self, xml_doc):
        assert lxml.etree.QName(xml_doc.tag).localname == "GetCapabilities"

        self.service = xml_doc.attrib.pop("service")

        for element in xml_doc:

            if isinstance(element, lxml.etree._Comment):
                logger.debug("Skipping comment: %s" % element.text)
                continue

            tag = lxml.etree.QName(element.tag).localname
            if tag == "AcceptVersions":
                for eelement in element:
                    assert lxml.etree.QName(eelement.tag).localname == "Version"
                    self.accept_versions.append(eelement.text)
            if tag == "AcceptFormats":
                for eelement in element:
                    assert lxml.etree.QName(eelement.tag).localname == "OutputFormat"
                    self.accept_formats.append(
                        ogc_common.OutputFormat(value=eelement.text)
                    )
            else:
                logger.warn("Tag %s not known." % tag)

        logger.debug("Unused attributes in %s: %s" % (xml_doc, xml_doc.attrib))


#########


class GetCoverage(ogc_common.XMLNode):
    """
    Request to a WCS to perform the GetCoverage operation.

    This operation allows a client to retrieve a
    subset of one coverage. In this XML encoding, no "request" parameter is included, since
    the element name specifies the specific operation.
    """

    service = tl.Unicode(default_value=None, allow_none=True)  # 'WCS')
    version = tl.Unicode(default_value=None, allow_none=True)

    identifier = tl.Instance(klass=Identifier)  # Should we limit to one?
    crs = tl.Enum(list(settings.WCS_CRS.keys()))
    domain_subset_bbox = tl.Instance(klass=ogc_common.BoundingBox)
    domain_subset_temporal = tl.Instance(klass=ogc_common.TemporalSubset)
    range_subset = tl.Any()
    output_format = tl.Instance(klass=ogc_common.OutputFormat)

    width = tl.Int()
    height = tl.Int()

    def validate(self):
        assert (
            self.service == "WCS"
        ), "WCS Request validation error: service should be WCS"

        assert self.identifier, "WCS Request validation error: no coverage specified"
        assert (
            self.domain_subset_bbox
        ), "WCS Request validation error: no bounding box specified"
        self.output_format.validate(), "WCS Request validation error: output format"
        assert self.height, "WCS Request validation error: no height specified"
        assert self.width, "WCS Request validation error: no width specified"
        lons = [
            self.domain_subset_bbox.lower_corner[0],
            self.domain_subset_bbox.upper_corner[0],
        ]
        lats = [
            self.domain_subset_bbox.lower_corner[1],
            self.domain_subset_bbox.upper_corner[1],
        ]
        if any([abs(l) > 361.000 for l in lons]) or any(
            [abs(l) > 91.000 for l in lats]
        ):
            raise ogc_common.WCSException(
                exception_code="InvalidParameterValue",
                locator="BBOX",
                exception_text="longitude must be between -180 and +180, latitude must be between -90 and +90",
            )

    def _load_from_kv(self, args):
        assert args["request"] == "GetCoverage", args["request"]
        self.service = args["service"].upper()
        self.version = args["version"]

        self.identifier = Identifier(value=args["coverage"])

        if "request_crs" in list(args.keys()):
            assert (
                args["request_crs"].lower() in settings.WCS_CRS
            ), "SRS not supported [CRS]: %s (%s are supported.)" % (
                args["request_crs"],
                str(settings.WCS_CRS),
            )
            self.crs = args["request_crs"].lower()

        if "crs" in list(args.keys()):
            assert (
                args["crs"].lower() in settings.WCS_CRS
            ), "SRS not supported [CRS]: %s (%s are supported.)" % (
                args["crs"],
                str(settings.WCS_CRS),
            )
            self.crs = args["crs"].lower()

        bbox = args["bbox"].replace(" ", "").split(",")
        # BBOX = minx, miny, maxx, maxy, minz, maxz
        self.domain_subset_bbox = ogc_common.BoundingBox(
            lower_corner=(float(bbox[0]), float(bbox[1])),
            upper_corner=(float(bbox[2]), float(bbox[3])),
        )

        # CRS:84 (or 'CRS84' in pyproj) is just epsg:4326 with the order of lat-long specification switched
        if self.crs == "crs:84":
            self.crs = "epsg:4326"
            self.domain_subset_bbox = ogc_common.BoundingBox(
                lower_corner=(float(bbox[1]), float(bbox[0])),
                upper_corner=(float(bbox[3]), float(bbox[2])),
            )

        self.output_format = ogc_common.OutputFormat(value=args["format"])
        if "time" in args:
            # TIME = time1, time2,...
            # or
            # TIME = min / max / res, ...
            if "," in args["time"]:
                raise ogc_common.WCSException(
                    exception_code="InvalidParameterValue",
                    locator="TIME",
                    exception_text="Only one time value per request is supported. Please specify a single timestamp (e.g. TIME=2016-01-31T00:00:00.000Z)",
                )
            dt = dateutil.parser.parse(args["time"]).isoformat()
            self.domain_subset_temporal = ogc_common.TemporalSubset(time_position=dt)

        self.height = int(args["height"])
        self.width = int(args["width"])

    def _load_xml_doc(self, xml_doc):
        raise NotImplementedError()
