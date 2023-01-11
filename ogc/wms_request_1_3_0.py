import logging

import lxml, lxml.etree
import dateutil.parser
import traitlets as tl

from . import ogc_common
from .wcs_request_1_0_0 import Identifier
from . import settings

logger = logging.getLogger(__file__)


class GetCapabilities(ogc_common.XMLNode):
    """
    Request to a WMS server to perform the GetCapabilities operation.
    This operation allows a client to retrieve a Capabilities XML document providing
    metadata for the specific WMS server. In this XML encoding, no "request" parameter
    is included, since the element name specifies the specific operation.
    """

    service = tl.Unicode(default_value=None, allow_none=True)

    accept_versions = tl.List(trait=tl.Unicode(default_value=None, allow_none=True))
    accept_formats = tl.List(trait=tl.Instance(klass=ogc_common.OutputFormat))

    def validate(self):
        assert (
            self.service == "WMS"
        ), "WMS Request validation error: service should be WMS"

        for obj in self.accept_formats:
            obj.validate()

    def _load_from_kv(self, args):
        assert args["request"] == "GetCapabilities", args["request"]
        self.service = args["service"].upper()


class GetMap(ogc_common.XMLNode):
    """
    Request to a WMS to perform the GetMap operation.

    This operation allows a client to retrieve a
    subset of one coverage. In this XML encoding, no "request" parameter is
    included, since the element name specifies the specific operation.
    """

    service = tl.Unicode(default_value=None, allow_none=True)
    version = tl.Unicode(default_value=None, allow_none=True)

    layer = tl.Instance(klass=Identifier)  # Should we limit to one?
    crs = tl.Enum(values=list(settings.WMS_CRS.keys()))

    bbox = tl.Instance(klass=ogc_common.BoundingBox)
    width = tl.Int()
    height = tl.Int()
    time = tl.Unicode(default_value=None, allow_none=True)
    output_format = tl.Enum(
        default_value=None,
        values=["image/png", "image/png; mode=8bit", "image/png;mode=8-bit"],
    )

    def validate(self):
        assert (
            self.service == "WMS"
        ), "WMS Request validation error: service should be WMS"

        assert self.layer, "WMS Request validation error: no coverage specified"
        assert self.bbox, "WMS Request validation error: no bounding box specified"
        assert (
            self.output_format
        ), "WMS Request validation error: no output format specified"
        assert self.height, "WMS Request validation error: no height specified"
        assert self.width, "WMS Request validation error: no width specified"
        lons = [self.bbox.lower_corner[0], self.bbox.upper_corner[0]]
        lats = [self.bbox.lower_corner[1], self.bbox.upper_corner[1]]
        bbox = lons + lats
        if any([abs(round(x, 9)) > 20037508.342789244 for x in bbox]):
            raise ogc_common.WCSException(
                exception_code="InvalidParameterValue",
                locator="BBOX",
                exception_text="minx,miny,maxx,maxy must all be between -20037508.342789244 and +20037508.342789244",
            )

    def _load_from_kv(self, args):
        assert args["request"].lower() == "getmap", args["request"]
        self.service = args["service"].upper()
        self.version = args["version"]

        assert "," not in args["layers"], "Only one layer supported at a time."
        self.layer = Identifier(value=args["layers"])

        if "crs" in list(args.keys()):
            assert (
                args["crs"].lower() in settings.WMS_CRS
            ), "SRS not supported [CRS]: %s (%s are supported.)" % (
                args["crs"],
                str(settings.WMS_CRS),
            )
            self.crs = args["crs"].lower()

        bbox = args["bbox"].split(",")
        # BBOX = minx, miny, maxx, maxy, minz, maxz
        self.bbox = ogc_common.BoundingBox(
            lower_corner=(float(bbox[0]), float(bbox[1])),
            upper_corner=(float(bbox[2]), float(bbox[3])),
        )

        # CRS:84 (or 'crs84' in pyproj) is just epsg:4326 with the order of lat-long specification shifted
        if self.crs == "crs:84":
            self.crs = "epsg:4326"
            self.bbox = ogc_common.BoundingBox(
                lower_corner=(float(bbox[1]), float(bbox[0])),
                upper_corner=(float(bbox[3]), float(bbox[2])),
            )

        if "time" in args:
            # TIME = time1, time2,...
            # or
            # TIME = min / max / res, ...
            assert "," not in args["time"], "error loading time from request"
            self.time = args["time"]

        if "format" in args:
            self.output_format = str(args["format"])

        self.height = int(args["height"])
        self.width = int(args["width"])

    def _load_xml_doc(self, xml_doc):
        raise NotImplementedError()


class GetLegendGraphic(ogc_common.XMLNode):
    """
    Request to a WMS server to perform the GetLegendGraphic operation.
    This operation allows a client to retrieve a Legend Graphic for a particular
    layer.
    """

    service = tl.Unicode(default_value=None, allow_none=True)
    version = tl.Unicode(default_value=None, allow_none=True)

    output_format = tl.Enum(
        values=["image/png", "image/png; mode=8bit", "image/png;mode=8-bit"]
    )

    layer = tl.Instance(klass=Identifier)  # Limited to one
    crs = tl.Enum(values=list(settings.WMS_CRS.keys()))

    def validate(self):
        assert (
            self.service == "WMS"
        ), "WMS Request validation error: service should be WMS"
        assert self.layer, "WMS Request validation error: no coverage specified"

    def _load_from_kv(self, args):
        assert args["request"] == "GetLegendGraphic", args["request"]
        self.service = args["service"].upper()

        assert "," not in args["layer"], "Only one layer supported at a time."
        self.layer = Identifier(value=args["layer"])
