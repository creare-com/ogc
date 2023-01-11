import logging
import datetime

import lxml, lxml.etree
import traitlets as tl
from ogc import GridCoordinates


from . import ogc_common
from . import settings

logger = logging.getLogger(__name__)

SERVICE_VERSION = "1.0.0"
CONSTRAINTS_ABBREVIATED = settings.CLASSIFICATION[0]
NATIVE_PROJECTION = "epsg:4326"  # WGS84

from ogc import Layer


class Coverage(ogc_common.XMLNode):
    layer = tl.Instance(klass=Layer)
    default_time = tl.Instance(klass=datetime.datetime)
    crs_extents = tl.Dict(settings.WCS_CRS[NATIVE_PROJECTION])

    grid_coordinates = tl.Instance(klass=GridCoordinates, allow_none=True)

    def _grid_coordinates_default(self):
        if self.layer:
            return self.layer.grid_coordinates
        else:
            return None

    constraints_abbreviated = tl.Unicode(default_value=None, allow_none=True)

    def _constraints_abbreviated_default(self):
        if self.layer:
            return settings.CUI_CONSTRAINT_STRING if self.layer.is_cui else ""
        else:
            return CONSTRAINTS_ABBREVIATED

    identifier = tl.Unicode(default_value=None, allow_none=True)

    def _identifer_default(self):
        if self.layer:
            return self.layer.id_str

    title = tl.Unicode(default_value=None, allow_none=True)

    def _title_default(self):
        if self.layer:
            return "({}) {}".format(
                self.constraints_abbreviated, repr(self.layer._style)
            )

    abstract = tl.Unicode(default_value=None, allow_none=True)

    def _abstract_default(self):
        if self.layer:
            abstract = "({}) OGC Layer: {}".format(
                self.constraints_abbreviated, repr(self.layer._style)
            )
            if self.layer._style.is_enumerated:
                abstract += " Layer represents an enumerated (i.e., categorical/non-scalar) quantity."
            return abstract

    # Spec: (lon, lat) with lower_corner values being mathematically lower than upper_corner.
    wgs84_bounding_box_lower_corner_lat_lon = tl.Tuple(tl.Float(), tl.Float())

    def _wgs84_bounding_box_lower_corner_lat_lon_default(self):
        try:
            return (
                self.layer.grid_coordinates.LLC.lat,
                self.layer.grid_coordinates.LLC.lon,
            )
        except:
            return (self.crs_extents["minx"], self.crs_extents["miny"])

    wgs84_bounding_box_upper_corner_lat_lon = tl.Tuple(tl.Float(), tl.Float())

    def _wgs84_bounding_box_upper_corner_lat_lon_default(self):
        try:
            return (
                self.layer.grid_coordinates.URC.lat,
                self.layer.grid_coordinates.URC.lon,
            )
        except:
            return (self.crs_extents["maxx"], self.crs_extents["maxy"])


class CoverageDescription(ogc_common.XMLNode):
    coverages = tl.List(trait=tl.Instance(klass=Coverage))

    def to_xml(self):
        xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<wcs:CoverageDescription xmlns:wcs="http://www.opengis.net/wcs"
xmlns:xlink="http://www.w3.org/1999/xlink"
xmlns:ogc="http://www.opengis.net/ogc"
xmlns:ows="http://www.opengis.net/ows/1.1"
xmlns:gml="http://www.opengis.net/gml"
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
xsi:schemaLocation="http://www.opengis.net/wcs http://schemas.opengis.net/wcs/1.0.0/describeCoverage.xsd"
version="1.0.0">
"""

        for coverage in self.coverages:
            xml += """    <wcs:CoverageOffering>"""
            if coverage.identifier:
                xml += "        <wcs:name>{coverage.identifier}</wcs:name>\n".format(
                    coverage=coverage
                )
            if coverage.title:
                xml += "        <wcs:label>{coverage.title}</wcs:label>\n".format(
                    coverage=coverage
                )
            if coverage.abstract:
                xml += "        <wcs:description>{coverage.abstract}</wcs:description>\n".format(
                    coverage=coverage
                )
            temporal_domain = ""
            if hasattr(coverage.layer, "valid_times"):
                if coverage.layer.all_times_valid:
                    temporal_domain += "            <wcs:temporalDomain>\n"
                    temporal_domain += "                <gml:timePeriod>\n"
                    temporal_domain += "                    <gml:beginPosition>{}</gml:beginPosition>".format(
                        datetime.datetime.min
                    )
                    temporal_domain += "                    <gml:endPosition>{}</gml:endPosition>".format(
                        datetime.datetime.max
                    )
                    temporal_domain += "                </gml:timePeriod>\n"
                    temporal_domain += "            </wcs:temporalDomain>\n"

                elif (
                    coverage.layer.valid_times
                    and coverage.layer.valid_times is not tl.Undefined
                ):
                    temporal_domain += "            <wcs:temporalDomain>\n"
                    temporal_domain += "".join(
                        [
                            "                <gml:timePosition>{}</gml:timePosition>\n".format(
                                dt.isoformat()
                            )
                            for dt in coverage.layer.valid_times
                        ]
                    )
                    temporal_domain += "            </wcs:temporalDomain>\n"

            if (
                coverage.wgs84_bounding_box_lower_corner_lat_lon
                or coverage.wgs84_bounding_box_upper_corner_lat_lon
            ):
                xml += """            <wcs:lonLatEnvelope srsName="urn:ogc:def:crs:OGC:1.3:CRS84">
                <gml:pos>{coverage.wgs84_bounding_box_lower_corner_lat_lon[1]} {coverage.wgs84_bounding_box_lower_corner_lat_lon[0]}</gml:pos>
                <gml:pos>{coverage.wgs84_bounding_box_upper_corner_lat_lon[1]} {coverage.wgs84_bounding_box_upper_corner_lat_lon[0]}</gml:pos>
            </wcs:lonLatEnvelope>""".format(
                    coverage=coverage
                )

            xml += """\
        <wcs:domainSet>
            <wcs:spatialDomain>
                <gml:Envelope srsName="{epsg}">
                    <gml:pos>{coverage.wgs84_bounding_box_lower_corner_lat_lon[1]} {coverage.wgs84_bounding_box_lower_corner_lat_lon[0]}</gml:pos>
            <gml:pos>{coverage.wgs84_bounding_box_upper_corner_lat_lon[1]} {coverage.wgs84_bounding_box_upper_corner_lat_lon[0]}</gml:pos>
                </gml:Envelope>
                <gml:RectifiedGrid dimension="2" srsName="{epsg}">
                  <gml:limits>
                    <gml:GridEnvelope>
                      <gml:low>0 0</gml:low>
                      <gml:high>{coverage.grid_coordinates.x_size} {coverage.grid_coordinates.y_size}</gml:high>
                    </gml:GridEnvelope>
                  </gml:limits>
                  <gml:axisName>x</gml:axisName>
                  <gml:axisName>y</gml:axisName>
                  <gml:origin>
                    <gml:pos>{coverage.grid_coordinates.geotransform[0]} {coverage.grid_coordinates.geotransform[3]}</gml:pos>
                  </gml:origin>
                  <gml:offsetVector>{coverage.grid_coordinates.geotransform[1]} {coverage.grid_coordinates.geotransform[2]}</gml:offsetVector>
                  <gml:offsetVector>{coverage.grid_coordinates.geotransform[4]} {coverage.grid_coordinates.geotransform[5]}</gml:offsetVector>
                </gml:RectifiedGrid>
            </wcs:spatialDomain>
            {temporal_domain}
        </wcs:domainSet>
        <wcs:rangeSet>
          <wcs:RangeSet>
            <wcs:name>{coverage.identifier}</wcs:name>
            <wcs:label>{coverage.title}</wcs:label>
            <wcs:axisDescription>
              <wcs:AxisDescription>
                <wcs:name>Band</wcs:name>
                <wcs:label>Band</wcs:label>
                <wcs:values>
                  <wcs:singleValue>1</wcs:singleValue>
                </wcs:values>
              </wcs:AxisDescription>
            </wcs:axisDescription>
          </wcs:RangeSet>
        </wcs:rangeSet>
        <wcs:supportedCRSs>
""".format(
                coverage=coverage,
                temporal_domain=temporal_domain,
                epsg=NATIVE_PROJECTION.upper(),
            )
            xml += "\n".join(
                [
                    "            <wcs:requestResponseCRSs>{epsg}</wcs:requestResponseCRSs>".format(
                        epsg=epsg.upper()
                    )
                    for epsg in list(settings.WCS_CRS.keys())
                ]
            )
            xml += """
        </wcs:supportedCRSs>

""".format(
                coverage=coverage, temporal_domain=temporal_domain
            )  #
            xml += """\
        <wcs:supportedFormats nativeFormat="GeoTIFF">
          <wcs:formats>GeoTIFF</wcs:formats>
        </wcs:supportedFormats>
  </wcs:CoverageOffering>
"""
        xml += """\
</wcs:CoverageDescription>
"""
        return xml


class Capabilities(ogc_common.XMLNode):
    """
    XML encoded WCS GetCapabilities operation response. The Capabilities document provides clients with service metadata about a specific service instance, including metadata about the coverages served. If the server does not implement the updateSequence parameter, the server shall always return the Capabilities document, without the updateSequence parameter. When the server implements the updateSequence parameter and the GetCapabilities operation request included the updateSequence parameter with the current value, the server shall return this element with only the "version" and "updateSequence" attributes. Otherwise, all optional sections shall be included or not depending on the actual value of the Contents parameter in the GetCapabilities operation request.
    """

    # Description Part
    service_title = tl.Unicode(default_value=None, allow_none=True)
    service_abstract = tl.Unicode(default_value=None, allow_none=True)
    service_keywords = tl.List(trait=tl.Unicode(default_value=None, allow_none=True))

    # Service Identification Part
    service_type = tl.Unicode(default_value="WCS", allow_none=True)
    service_type_version = tl.List(default_value=[SERVICE_VERSION])

    version = tl.Unicode(default_value=SERVICE_VERSION)

    def service(self):
        return """\
    <wcs:Service>
        <wcs:name>{self.service_title}</wcs:name>
        <wcs:label>{self.service_title}</wcs:label>
        <wcs:fees>UNAVAILABLE</wcs:fees>
        <wcs:accessConstraints>{constraints}</wcs:accessConstraints>
    </wcs:Service>
""".format(
            self=self, constraints=settings.CONSTRAINTS
        )

    base_url = tl.Unicode(
        default_value=None, allow_none=True
    )  # e.g., http://hostname:port/path?

    def capability(self):
        return """\
<wcs:Capability>
    <wcs:Request>
      <wcs:GetCapabilities>
        <wcs:DCPType>
          <wcs:HTTP>
            <wcs:Get>
              <wcs:OnlineResource xlink:href="{self.base_url}"/>
            </wcs:Get>
          </wcs:HTTP>
        </wcs:DCPType>
      </wcs:GetCapabilities>
      <wcs:DescribeCoverage>
        <wcs:DCPType>
          <wcs:HTTP>
            <wcs:Get>
              <wcs:OnlineResource xlink:href="{self.base_url}"/>
            </wcs:Get>
          </wcs:HTTP>
        </wcs:DCPType>
      </wcs:DescribeCoverage>
      <wcs:GetCoverage>
        <wcs:DCPType>
          <wcs:HTTP>
            <wcs:Get>
              <wcs:OnlineResource xlink:href="{self.base_url}"/>
            </wcs:Get>
          </wcs:HTTP>
        </wcs:DCPType>
      </wcs:GetCoverage>
    </wcs:Request>
    <wcs:Exception>
      <wcs:Format>application/vnd.ogc.se_xml</wcs:Format>
    </wcs:Exception>
  </wcs:Capability>
  """.format(
            self=self
        )

    coverages = tl.List(
        tl.Instance(klass=Coverage)
    )  # is populated via Traits in constructor

    # Check if list of layers available should be trimmed
    layer_subset = []
    limit_layers = False
    try:
        limit_layers = settings.WMS_LIMIT_LAYERS
        layer_subset = settings.WMS_LAYERS
    except Exception as e:
        logger.info("Layer limiting settings not enabled: {}".format(e))

    def contents(self):
        xml = "  <wcs:ContentMetadata>\n"

        # If configured, trim layers list to layers specified in settings
        if self.limit_layers:
            self.coverages = [
                layer
                for layer in self.coverages
                if layer.identifier in self.layer_subset
            ]

        for coverage in self.coverages:
            xml += "        <wcs:CoverageOfferingBrief>\n"
            if coverage.abstract:
                xml += "            <wcs:description>{coverage.abstract}</wcs:description>\n".format(
                    coverage=coverage
                )
            if coverage.identifier:  # required
                xml += (
                    "            <wcs:name>{coverage.identifier}</wcs:name>\n".format(
                        coverage=coverage
                    )
                )
            else:
                logger.info("Invalid layer. Missing name.")
            if coverage.title:  # required
                xml += "            <wcs:label>{coverage.title}</wcs:label>\n".format(
                    coverage=coverage
                )
            else:
                logger.info("Invalid layer. Missing label.")
            if (
                coverage.wgs84_bounding_box_lower_corner_lat_lon
                or coverage.wgs84_bounding_box_upper_corner_lat_lon
            ):
                xml += """            <wcs:lonLatEnvelope srsName="urn:ogc:def:crs:OGC:1.3:CRS84">
                <gml:pos>{coverage.wgs84_bounding_box_lower_corner_lat_lon[1]} {coverage.wgs84_bounding_box_lower_corner_lat_lon[0]}</gml:pos>
                <gml:pos>{coverage.wgs84_bounding_box_upper_corner_lat_lon[1]} {coverage.wgs84_bounding_box_upper_corner_lat_lon[0]}</gml:pos>
            </wcs:lonLatEnvelope>
""".format(
                    coverage=coverage
                )
            xml += "        </wcs:CoverageOfferingBrief>\n"
        xml += "    </wcs:ContentMetadata>\n"

        return xml

    def to_xml(self):
        return """\
<?xml version="1.0" encoding="UTF-8"?>
<wcs:WCS_Capabilities
xmlns:wcs="http://www.opengis.net/wcs"
xmlns:xlink="http://www.w3.org/1999/xlink"
xmlns:ogc="http://www.opengis.net/ogc"
xmlns:ows="http://www.opengis.net/ows/1.1"
xmlns:gml="http://www.opengis.net/gml"
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
xsi:schemaLocation="http://www.opengis.net/wcs http://schemas.opengis.net/wcs/1.0.0/wcsCapabilities.xsd"
version="{capabilities.version}">
{service}
{capability}
{contents}
</wcs:WCS_Capabilities>
        """.format(
            capabilities=self,
            service=self.service(),
            capability=self.capability(),
            contents=self.contents(),
        )
