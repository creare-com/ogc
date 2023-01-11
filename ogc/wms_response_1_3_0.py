import logging

import lxml, lxml.etree
import traitlets as tl

from ogc import ogc_common
from ogc import settings

logger = logging.getLogger(__name__)

SERVICE_VERSION = "1.3.0"

from ogc.wcs_response_1_0_0 import Coverage


class Capabilities(ogc_common.XMLNode):
    """
    XML encoded WMS GetCapabilities operation response.
    The Capabilities document provides clients with service
    metadata about a specific service instance, including metadata
    about the coverages served. If the server does not
    implement the updateSequence parameter, the server shall always
    return the Capabilities document, without the updateSequence
    parameter. When the server implements the updateSequence
    parameter and the GetCapabilities operation request included
    the updateSequence parameter with the current value, the server
    shall return this element with only the "version" and
    "updateSequence" attributes. Otherwise, all optional sections
    shall be included or not depending on the actual value of the
    Contents parameter in the GetCapabilities operation request.
    """

    # Description Part
    service_title = tl.Unicode(default_value=None, allow_none=True)
    service_abstract = tl.Unicode(default_value=None, allow_none=True)
    service_keywords = tl.List(trait=tl.Unicode(default_value=None, allow_none=True))
    service_group_title = tl.Unicode(default_value=None, allow_none=True)

    # Service Identification Part
    service_type = tl.Unicode(default_value="WMS", allow_none=True)
    service_type_version = tl.List([SERVICE_VERSION])

    version = tl.Unicode(default_value=SERVICE_VERSION)

    def service(self):
        return """\
    <Service>
        <Name>WMS</Name>
        <Title>{self.service_title}</Title>
        <OnlineResource xlink:href="{self.base_url}"/>
        <AccessConstraints>{constraints}</AccessConstraints>
        <LayerLimit>1</LayerLimit>
        <MaxWidth>1024</MaxWidth>
        <MaxHeight>1024</MaxHeight>
    </Service>
""".format(
            self=self, constraints=settings.CONSTRAINTS
        )

    base_url = tl.Unicode(
        default_value=None, allow_none=True
    )  # e.g., http://hostname:port/path?

    def request(self):
        return """\
    <Request>
      <GetCapabilities>
        <Format>text/xml</Format>
        <DCPType>
          <HTTP>
            <Get>
              <OnlineResource xlink:href="{self.base_url}"/>
            </Get>
          </HTTP>
        </DCPType>
      </GetCapabilities>
      <GetMap>
        <Format>image/png</Format>
        <DCPType>
          <HTTP>
            <Get>
              <OnlineResource xlink:href="{self.base_url}"/>
            </Get>
          </HTTP>
        </DCPType>
      </GetMap>
    </Request>
  """.format(
            self=self
        )

    def exception(self):
        return """\
    <Exception>
      <Format>application/vnd.ogc.se_xml</Format>
    </Exception>
  """

    coverages = tl.List(
        trait=tl.Instance(klass=Coverage)
    )  # is populated via Traits in constructor

    # Check if list of layers available should be trimmed
    layer_subset = []
    limit_layers = False
    try:
        limit_layers = settings.WMS_LIMIT_LAYERS
        layer_subset = settings.WMS_LAYERS
    except Exception as e:
        logger.info("Layer limiting settings not enabled: {}".format(e))

    def layers(self):
        xml = "    <Layer>\n"
        xml += "        <Title>{}</Title>\n".format(self.service_group_title)
        xml += self._get_CRS_and_BoundingBox(depth=2)

        # If configured, trim layers list to layers specified in settings
        if self.limit_layers:
            self.coverages = [
                layer
                for layer in self.coverages
                if layer.identifier in self.layer_subset
            ]

        for coverage in self.coverages:
            xml += """       <Layer queryable="0" opaque="0" cascaded="1">\n"""
            if coverage.identifier:
                xml += "            <Name>{coverage.identifier}</Name>\n".format(
                    coverage=coverage
                )
            if coverage.title:
                xml += "            <Title>{coverage.title}</Title>\n".format(
                    coverage=coverage, self=self
                )
            else:
                logger.info("Invalid layer. Missing title.")
            if coverage.abstract:
                xml += "            <Abstract>{coverage.abstract}</Abstract>\n".format(
                    coverage=coverage, self=self
                )

            xml += self._get_CRS_and_BoundingBox()

            if (
                hasattr(coverage.layer, "valid_times")
                and coverage.layer.valid_times is not tl.Undefined
                and len(coverage.layer.valid_times) > 0
            ):
                min_time = coverage.layer.valid_times[0]
                max_time = coverage.layer.valid_times[-1]
                time_dimension_str = """            <Dimension name="TIME" units="ISO8601" default="{default_time}">{times}</Dimension>\n"""

                # Find last time with seconds == 0
                try:
                    latest_LIS_time = next(
                        (
                            t
                            for t in reversed(coverage.layer.valid_times)
                            if t.second == 0
                        ),
                        None,
                    )
                except AttributeError:
                    latest_LIS_time = next(
                        (t for t in reversed(coverage.layer.valid_times)), None
                    )

                if latest_LIS_time is not None:
                    # default to latest LIS time, if available
                    default_time = latest_LIS_time
                else:
                    # otherwise default to first available time
                    default_time = min_time

                if settings.USE_TIMES_LIST:
                    # Build list of times to display
                    display_times = []
                    for time in reversed(coverage.layer.valid_times):
                        if (default_time - time).days < settings.PAST_DAYS_INCLUDED:
                            display_times.append(time)
                        else:
                            # Stop looking once the list has reached too far in the past
                            break

                    times_available_str = ",".join(
                        [time.isoformat() + "Z" for time in reversed(display_times)]
                    )

                else:
                    times_available_str = "{min_time}/{max_time}/P3H".format(
                        min_time=min_time.isoformat() + "Z",
                        max_time=max_time.isoformat() + "Z",
                    )

                xml += time_dimension_str.format(
                    times=times_available_str,
                    default_time=default_time.isoformat() + "Z",
                )

            legend_graphic_width = coverage.layer.legend_graphic_width
            legend_graphic_height = coverage.layer.legend_graphic_height

            legend_link = "{base}SERVICE={service}&amp;VERSION={version}&amp;REQUEST=GetLegendGraphic&amp;LAYER={layer}&amp;STYLE=default&amp;FORMAT=image/png; mode=8bit".format(
                base=self.base_url
                if self.base_url.endswith("?")
                else self.base_url + "?",
                service=self.service_type,
                version=self.version,
                layer=coverage.identifier,
            )

            # Write the style section
            xml += """            <Style>\n"""
            xml += """                <Name>{}</Name>\n""".format(coverage.identifier)
            xml += """                <Title>{}</Title>\n""".format(coverage.title)
            xml += """                <LegendURL width="{width}" height="{height}">\n""".format(
                height=legend_graphic_height, width=legend_graphic_width
            )
            xml += """                    <Format>image/png</Format>\n"""
            xml += """                    <OnlineResource xlink:type="simple" xlink:href="{}"/>\n""".format(
                legend_link
            )
            xml += """                </LegendURL>\n"""
            xml += """            </Style>\n"""
            xml += """        </Layer>\n"""
        # end layers list
        xml += """    </Layer>"""

        return xml

    def to_xml(self):
        return """\
<?xml version="1.0" encoding="UTF-8"?>
<WMS_Capabilities
xmlns="http://www.opengis.net/wms"
xmlns:xlink="http://www.w3.org/1999/xlink"
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
xsi:schemaLocation="http://www.opengis.net/wms http://schemas.opengis.net/wms/1.3.0/capabilities_1_3_0.xsd"
version="{capabilities.version}">
{service}
  <Capability>
{request}
{exception}
{layers}
  </Capability>
</WMS_Capabilities>
        """.format(
            capabilities=self,
            service=self.service(),
            request=self.request(),
            exception=self.exception(),
            layers=self.layers(),
        )

    @staticmethod
    def _format_number(input, float_decimals=9):
        if type(input) == float:
            return "{number:.{decimals}f}".format(number=input, decimals=float_decimals)
        else:
            return "{}".format(input)

    def _get_CRS_and_BoundingBox(self, depth=3):
        indent = "    "

        output_text = (
            "\n".join(
                [
                    indent * depth + """<CRS>{epsg}</CRS>""".format(epsg=epsg.upper())
                    for epsg, bbox in list(settings.WMS_CRS.items())
                ]
            )
            + "\n"
        )

        output_text += "\n".join(
            [
                indent * depth + "<EX_GeographicBoundingBox>",
                indent * (depth + 1) + "<westBoundLongitude>-180</westBoundLongitude>",
                indent * (depth + 1) + "<eastBoundLongitude>180</eastBoundLongitude>",
                indent * (depth + 1) + "<southBoundLatitude>-90</southBoundLatitude>",
                indent * (depth + 1) + "<northBoundLatitude>90</northBoundLatitude>",
                indent * (depth) + "</EX_GeographicBoundingBox>",
            ]
        )
        output_text += "\n".join(
            [
                indent * depth
                + """<BoundingBox CRS="{epsg}"  minx="{minx}" miny="{miny}" maxx="{maxx}" maxy="{maxy}"/>""".format(
                    epsg=epsg.upper(),
                    minx=Capabilities._format_number(bbox["minx"]),
                    miny=Capabilities._format_number(bbox["miny"]),
                    maxx=Capabilities._format_number(bbox["maxx"]),
                    maxy=Capabilities._format_number(bbox["maxy"]),
                )
                for epsg, bbox in list(settings.WMS_CRS.items())
            ]
        )
        return output_text
