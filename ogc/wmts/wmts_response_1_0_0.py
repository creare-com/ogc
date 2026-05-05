import logging
import traitlets as tl
from datetime import datetime
from xml.sax.saxutils import escape

from ogc import ogc_common
from ogc import settings
from ogc.wcs_response_1_0_0 import Coverage
from .wmts_request_1_0_0 import WebMercatorQuad, WorldCRS84Quad, TileMatrixSet

logger = logging.getLogger(__name__)
escape_format = ogc_common.EscapeFormatter().format

SERVICE_VERSION = "1.0.0"


class Capabilities(ogc_common.XMLNode):
    """
    XML encoded WMTS GetCapabilities operation response.
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
    service_type = tl.Unicode(default_value="WMTS", allow_none=True)
    service_type_version = tl.List([SERVICE_VERSION])

    coverages = tl.List(trait=tl.Instance(klass=Coverage))
    base_url = tl.Unicode(default_value=None, allow_none=True)

    version = tl.Unicode(default_value=SERVICE_VERSION)
    provider_name = tl.Unicode(default_value="Creare LLC")
    provider_site = tl.Unicode(default_value="https://github.com/creare-com")
    indent = "    "

    def to_xml(self) -> str:
        """Generate the XML response for service metadata.

        Returns
        -------
        str
            XML response as a string.
        """
        return """\
<?xml version="1.0" encoding="UTF-8"?>
<Capabilities
xmlns="http://www.opengis.net/wmts/1.0"
xmlns:ows="http://www.opengis.net/ows/1.1"
xmlns:xlink="http://www.w3.org/1999/xlink"
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
xmlns:gml="http://www.opengis.net/gml"
xsi:schemaLocation="http://www.opengis.net/wmts/1.0 http://schemas.opengis.net/wmts/1.0/wmtsGetCapabilities_response.xsd"
version="{version}">
{service_identification}
{service_provider}
{operations_metadata}
{contents}
<ServiceMetadataURL xlink:href="{base_url}SERVICE=WMTS&amp;REQUEST=GetCapabilities&amp;VERSION={version}"/>
</Capabilities>
        """.format(
            version=escape(self.version),
            base_url=escape(self.base_url if self.base_url else "?"),
            service_identification=self._service_identification(),
            service_provider=self._service_provider(),
            operations_metadata=self._operations_metadata(),
            contents=self._contents(),
        )

    def _service_identification(self) -> str:
        """Metadata about the specific service.

        Returns
        -------
        str
            XML data as a string.
        """
        keywords = ""
        if self.service_keywords:
            for service_keyword in self.service_keywords:
                keywords += escape_format("""<Keyword>{}</Keyword>\n""", service_keyword)

        return escape_format(
            """\
    <ows:ServiceIdentification>
        <ows:Title>{self.service_title}</ows:Title>
        <ows:Abstract>{self.service_abstract}</ows:Abstract>
        <ows:Keywords>{keywords}</ows:Keywords>
        <ows:ServiceType>{self.service_type}</ows:ServiceType>
        <ows:ServiceTypeVersion>{self.version}</ows:ServiceTypeVersion>
        <OnlineResource xlink:href="{self.base_url}"/>
        <ows:AccessConstraints>{constraints}</ows:AccessConstraints>
    </ows:ServiceIdentification>""",
            self=self,
            keywords=keywords,
            constraints=settings.CONSTRAINTS,
        )

    def _service_provider(self) -> str:
        """Metadata about the organization providing the service.

        Returns
        -------
        str
            XML data as a string.
        """
        return escape_format(
            """\
    <ows:ServiceProvider>
        <ows:ProviderName>{self.provider_name}</ows:ProviderName>
        <ows:ProviderSite xlink:href="{self.provider_site}"/>
    </ows:ServiceProvider>""",
            self=self,
        )

    def _operations_metadata(self) -> str:
        """Metadata about the operations specified by the service.

        Returns
        -------
        str
            XML data as a string.
        """
        return escape_format(
            """\
    <ows:OperationsMetadata>
        <ows:Operation name="GetCapabilities">
            <ows:DCP>
                <ows:HTTP>
                    <ows:Get xlink:href="{self.base_url}">
                        <ows:Constraint name="GetEncoding">
                            <ows:AllowedValues>
                                <ows:Value>KVP</ows:Value>
                            </ows:AllowedValues>
                        </ows:Constraint>
                    </ows:Get>
                </ows:HTTP>
            </ows:DCP>
        </ows:Operation>
        <ows:Operation name="GetTile">
            <ows:DCP>
                <ows:HTTP>
                    <ows:Get xlink:href="{self.base_url}">
                        <ows:Constraint name="GetEncoding">
                            <ows:AllowedValues>
                                <ows:Value>KVP</ows:Value>
                            </ows:AllowedValues>
                        </ows:Constraint>
                    </ows:Get>
                </ows:HTTP>
            </ows:DCP>
        </ows:Operation>
    </ows:OperationsMetadata>""",
            self=self,
        )

    def _contents(self) -> str:
        """Metadata about the data provided by the service.

        Returns
        -------
        str
            XML data as a string.
        """
        return """\
    <Contents>\n{layers}{tile_matrix_sets}</Contents>""".format(
            layers=self._layers(), tile_matrix_sets=self._tile_matrix_sets()
        )

    def _coverage_layer(self, coverage: Coverage, depth: int = 2) -> str:
        """Metadata about an individual coverage layer.

        Parameters
        ----------
        coverage : Coverage
            The coverage used to define layer metadata.
        depth : int
            The indentation depth for the XML data, by default 2.

        Returns
        -------
        str
            XML data as a string.
        """
        xml = ""
        xml = self.indent * depth + """<Layer>\n"""
        if coverage.identifier:
            xml += self.indent * (depth + 1) + escape_format(
                "<ows:Identifier>{identifier}</ows:Identifier>\n", identifier=coverage.identifier
            )
        if coverage.title:
            xml += self.indent * (depth + 1) + escape_format("<ows:Title>{}</ows:Title>\n", coverage.title)
        else:
            logger.info("Invalid layer. Missing title.")
        if coverage.abstract:
            xml += self.indent * (depth + 1) + escape_format("<ows:Abstract>{}</ows:Abstract>\n", coverage.abstract)

        xml += self._bounding_box_layer(coverage)

        coordinates = coverage.layer.get_coordinates()
        extra_dims = [dim for dim in coordinates.udims if dim not in ["lat", "lon"]]
        for extra_dim in extra_dims:
            if coordinates[extra_dim].coordinates.size > 0:
                units = "number"
                if extra_dim == "alt":
                    units = coordinates.alt_units if coordinates.alt_units is not None else units
                elif self._is_iso_datetime(str(coordinates[extra_dim].coordinates[-1])):
                    units = "ISO8601"

                xml += self.indent * (depth + 1) + """<Dimension>\n"""
                xml += self.indent * (depth + 2) + escape_format("""<ows:Identifier>{}</ows:Identifier>\n""", extra_dim)
                xml += self.indent * (depth + 2) + escape_format("""<UOM>{}</UOM>\n""", units)
                xml += self.indent * (depth + 2) + escape_format(
                    """<Default>{}</Default>\n""", coordinates[extra_dim].coordinates[-1]
                )
                for value in coordinates[extra_dim].coordinates:
                    xml += self.indent * (depth + 2) + escape_format("""<Value>{}</Value>\n""", value)
                xml += self.indent * (depth + 1) + """</Dimension>\n"""

        # Write the style section and format
        xml += self.indent * (depth + 1) + """<Style isDefault="true">\n"""
        xml += self.indent * (depth + 2) + escape_format(
            """<ows:Identifier>{}</ows:Identifier>\n""", coverage.identifier
        )
        xml += self.indent * (depth + 1) + """</Style>\n"""
        xml += self.indent * (depth + 1) + """<Format>image/png</Format>\n"""

        # Tile matrix set links
        matrix_sets = [WebMercatorQuad(), WorldCRS84Quad()]
        for matrix_set in matrix_sets:
            xml += self.indent * (depth + 1) + """<TileMatrixSetLink>\n"""
            xml += self.indent * (depth + 2) + escape_format("""<TileMatrixSet>{}</TileMatrixSet>\n""", matrix_set.name)
            xml += self.indent * (depth + 1) + """</TileMatrixSetLink>\n"""

        xml += self.indent * depth + """</Layer>\n"""

        return xml

    def _layers(self) -> str:
        """Metadata for all layers in the service.

        Returns
        -------
        str
            XML data as a string.
        """
        xml = ""
        for coverage in self.coverages:
            xml += self._coverage_layer(coverage)

        return xml

    def _tile_matrix_sets(self, depth: int = 2) -> str:
        """Metadata about the supported tile matrix sets.

        Parameters
        ----------
        depth : int
            The indentation depth for the XML data, by default 2.

        Returns
        -------
        str
            XML data as a string.
        """
        matrix_sets = [WebMercatorQuad(), WorldCRS84Quad()]
        xml = ""
        for matrix_set in matrix_sets:
            xml += matrix_set.to_xml()

        return xml

    def _bounding_box_layer(self, coverage: Coverage, depth: int = 3) -> str:
        """Metadata for the WGS84 bounding box for a specific coverage layer.

        Parameters
        ----------
        coverage : Coverage
            The coverage used to define layer metadata.
        depth : int
            The indentation depth for the XML data, by default 3.

        Returns
        -------
        str
            XML data as a string.
        """
        xml = ""
        xml += self.indent * (depth) + """<ows:WGS84BoundingBox>\n"""
        xml += self.indent * (depth + 1) + escape_format(
            """<ows:LowerCorner>{x} {y}</ows:LowerCorner>\n""",
            x=TileMatrixSet.format_number(coverage.wgs84_bounding_box_lower_corner_lat_lon[1]),
            y=TileMatrixSet.format_number(coverage.wgs84_bounding_box_lower_corner_lat_lon[0]),
        )
        xml += self.indent * (depth + 1) + escape_format(
            """<ows:UpperCorner>{x} {y}</ows:UpperCorner>\n""",
            x=TileMatrixSet.format_number(coverage.wgs84_bounding_box_upper_corner_lat_lon[1]),
            y=TileMatrixSet.format_number(coverage.wgs84_bounding_box_upper_corner_lat_lon[0]),
        )
        xml += self.indent * (depth) + """</ows:WGS84BoundingBox>\n"""

        return xml

    @staticmethod
    def _is_iso_datetime(datetime_string: str) -> bool:
        """Determine whether a string is a valid datetime.

        Parameters
        ----------
        datetime_string : str
            The datetime string to validate.

        Returns
        -------
        bool
            True if the provided string is a valid datetime, False otherwise.
        """
        try:
            datetime.fromisoformat(datetime_string)
            return True
        except ValueError:
            return False
