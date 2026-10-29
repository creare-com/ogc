import pyproj
import traitlets as tl
from typing import List, Tuple

from ogc import ogc_common
from ogc import settings

escape_format = ogc_common.EscapeFormatter().format

WELL_KNOWN_SCALE_SET_PREFIX = "urn:ogc:def:wkss:OGC:1.0:"
WEB_MERCATOR_BOUNDS = {
    "minx": -20037508.342789244,
    "miny": -20037508.342789244,
    "maxx": 20037508.342789244,
    "maxy": 20037508.342789244,
}
GEOGRAPHIC_BOUNDS = {"minx": -180.0, "miny": -90.0, "maxx": 180.0, "maxy": 90.0}
LEGACY_GEOGRAPHIC_BOUNDS = {"minx": -180.0, "miny": -180.0, "maxx": 180.0, "maxy": 180.0}


class TileMatrixSet(ogc_common.XMLNode):
    """Tile matrix set defining how OGC tile data is available at different scales."""

    name = tl.Unicode()
    crs = tl.Unicode()
    wkss = tl.Unicode()
    bounds = tl.Dict(key_trait=tl.Unicode(), value_trait=tl.Float())
    matrix_levels = tl.List(tl.Int(), default_value=list(range(0, 22)))
    axis_order_yx = tl.Bool(default_value=False)  # True when the crs lists the y (northing/latitude) axis first
    level_zero_matrix_width = tl.Int(default_value=1)  # Tile columns at matrix level zero, which has a single tile row
    depth = tl.Int(default_value=2)
    indent = "    "

    def validate(self):
        """Validate the tile matrix set."""
        assert len(self.name) > 0, "WMTS Request validation error: tile matrix set name not found"
        assert len(self.crs) > 0, "WMTS Request validation error: tile matrix set crs not found"
        assert len(self.bounds) > 0, "WMTS Request validation error: tile matrix set bounds not found"
        assert len(self.matrix_levels) > 0, "WMTS Request validation error: tile matrix levels not found"

    def validate_tile(self, row: int, column: int, matrix_level: int):
        """Validate the requested tile indices against the tile matrix set.

        Parameters
        ----------
        row : int
            The tile row.
        column : int
            The tile column.
        matrix_level : int
            The tile matrix level.
        """
        assert matrix_level >= 0 and matrix_level <= max(
            self.matrix_levels
        ), "WMTS Request validation error: tile matrix level not in range"
        matrix_width, matrix_height = self.calculate_matrix_sizes(matrix_level)
        assert row >= 0 and row < int(matrix_height), "WMTS Request validation error: invalid tile row"
        assert column >= 0 and column < int(matrix_width), "WMTS Request validation error: invalid tile column"

    def to_xml(self):
        xml = ""
        xml += self.indent * self.depth + "<TileMatrixSet>\n"
        xml += self.indent * (self.depth + 1) + escape_format("<ows:Identifier>{}</ows:Identifier>\n", self.name)
        xml += self.indent * (self.depth + 1) + escape_format("<ows:SupportedCRS>{}</ows:SupportedCRS>\n", self.crs)
        xml += self._bounding_box_tile_matrix_set() if self.crs is not None else ""
        if self.wkss:
            xml += self.indent * (self.depth + 1) + escape_format(
                "<WellKnownScaleSet>{}</WellKnownScaleSet>\n", self.wkss
            )
        top_left_corner = self._top_left_corner() if self.crs is not None else ""

        for matrix_level in self.matrix_levels:
            scale_denominator = self.calculate_scale_denominator(matrix_level)
            matrix_width, matrix_height = self.calculate_matrix_sizes(matrix_level) if self.crs is not None else ""
            xml += self.indent * (self.depth + 1) + """<TileMatrix>\n"""
            xml += self.indent * (self.depth + 2) + escape_format(
                """<ows:Identifier>{}</ows:Identifier>\n""", matrix_level
            )
            xml += self.indent * (self.depth + 2) + escape_format(
                """<ScaleDenominator>{}</ScaleDenominator>\n""", scale_denominator
            )
            xml += self.indent * (self.depth + 2) + escape_format(
                """<TopLeftCorner>{}</TopLeftCorner>\n""", top_left_corner
            )
            xml += self.indent * (self.depth + 2) + escape_format(
                """<TileWidth>{}</TileWidth>\n""", settings.WMTS_TILE_SIZE
            )
            xml += self.indent * (self.depth + 2) + escape_format(
                """<TileHeight>{}</TileHeight>\n""", settings.WMTS_TILE_SIZE
            )
            xml += self.indent * (self.depth + 2) + escape_format("""<MatrixWidth>{}</MatrixWidth>\n""", matrix_width)
            xml += self.indent * (self.depth + 2) + escape_format(
                """<MatrixHeight>{}</MatrixHeight>\n""", matrix_height
            )
            xml += self.indent * (self.depth + 1) + """</TileMatrix>\n"""

        xml += self.indent * self.depth + """</TileMatrixSet>\n"""
        return xml

    def _top_left_corner(self) -> str | None:
        """Get the top left corner of the bounded area defined by the tile matrix set.

        Returns
        -------
        str | None
            The top left corner as a string or None if the CRS is not valid for WMTS.
        """
        if self.bounds is not None:
            return self._format_corner(self.bounds["minx"], self.bounds["maxy"])

        return None

    def _bounding_box_tile_matrix_set(self) -> str:
        """Metadata for the bounding box for a specific tile matrix set based on the supported CRS.

        Returns
        -------
        str
            XML data as a string.
        """
        xml = ""
        if self.bounds is not None:
            xml += self.indent * (self.depth + 1) + """<ows:BoundingBox>\n"""
            xml += self.indent * (self.depth + 2) + escape_format(
                """<ows:LowerCorner>{}</ows:LowerCorner>\n""",
                self._format_corner(self.bounds["minx"], self.bounds["miny"]),
            )
            xml += self.indent * (self.depth + 2) + escape_format(
                """<ows:UpperCorner>{}</ows:UpperCorner>\n""",
                self._format_corner(self.bounds["maxx"], self.bounds["maxy"]),
            )
            xml += self.indent * (self.depth + 1) + """</ows:BoundingBox>\n"""

        return xml

    def _format_corner(self, x: float, y: float) -> str:
        """Format a corner coordinate as a string in the axis order of the CRS.

        Parameters
        ----------
        x : float
            The x (easting/longitude) coordinate.
        y : float
            The y (northing/latitude) coordinate.

        Returns
        -------
        str
            The corner coordinate as a string.
        """
        if self.axis_order_yx:
            return "{} {}".format(self.format_number(y), self.format_number(x))
        return "{} {}".format(self.format_number(x), self.format_number(y))

    @staticmethod
    def format_number(input_number: float | int, float_decimals: int = 9) -> str:
        """Format a number into a string with specified decimal count.

        Parameters
        ----------
        input_number : float | int
            The number to convert to a string.
        float_decimals : int, optional
            The decimals to display in the string, by default 9.

        Returns
        -------
        str
            The number formatted as a string.
        """
        if isinstance(input_number, float):
            return "{number:.{decimals}f}".format(number=input_number, decimals=float_decimals)
        else:
            return "{}".format(input_number)

    def calculate_eval_bounding_box(self, row: int, column: int, matrix_level: int) -> str:
        """Determine the bounding box for evaluation.

        A zero pixel row and column corresponds to the top left corner.

        Parameters
        ----------
        row : int
            The tile row.
        column : int
            The tile column.
        matrix_level : int
            The tile matrix level.

        Returns
        -------
        str
            The bounding box for the provided tile indices.
        """
        resolution = self.calculate_resolution(matrix_level)
        origin_x = self.bounds["minx"]
        origin_y = self.bounds["maxy"]
        tile_size = settings.WMTS_TILE_SIZE * resolution

        min_x = column * tile_size + origin_x
        max_x = (column + 1) * tile_size + origin_x
        min_y = origin_y - (row * tile_size)
        max_y = origin_y - ((row + 1) * tile_size)

        # Hack: Reverse x, y order to get around issues with Coordinates.from_url assuming lat, lon order
        min_x, min_y = min_y, min_x
        max_x, max_y = max_y, max_x

        return ",".join(str(x) for x in [min_x, min_y, max_x, max_y])

    def calculate_resolution(self, matrix_level: int) -> float:
        """Calculate the resolution in crs units per pixel for the matrix level.

        Parameters
        ----------
        matrix_level : int
            The matrix level to calculate resolution for.

        Returns
        -------
        float
            The resolution in crs units per pixel.
        """
        matrix_width, _ = self.calculate_matrix_sizes(matrix_level)
        return (self.bounds["maxx"] - self.bounds["minx"]) / (settings.WMTS_TILE_SIZE * int(matrix_width))

    def calculate_scale_denominator(self, matrix_level: int) -> str:
        """Calculate the scale denominator for the matrix level.

        Parameters
        ----------
        matrix_level : int
            The matrix level to calculate scale denominator for.

        Returns
        -------
        str
            The scaled denominator as a string or empty string on failure.
        """
        meters_per_unit = settings.EARTH_CIRCUMFERENCE_METERS / 360 if pyproj.CRS(self.crs).is_geographic else 1.0
        scale_denominator = self.calculate_resolution(matrix_level) * meters_per_unit / settings.WMTS_PIXEL_SIZE_METERS
        return TileMatrixSet.format_number(scale_denominator)

    def calculate_matrix_sizes(self, matrix_level: int) -> Tuple[str, str]:
        """Calculate the matrix width and height from matrix level.

        Parameters
        ----------
        matrix_level : int
            The matrix level to calculate width and height for.

        Returns
        -------
        Tuple[str, str]
            The matrix width and height as strings or empty strings on failure.
        """
        matrix_width = self.level_zero_matrix_width * 2**matrix_level
        matrix_height = 2**matrix_level
        return TileMatrixSet.format_number(matrix_width), TileMatrixSet.format_number(matrix_height)


def default_tile_matrix_sets() -> List[TileMatrixSet]:
    """Get the default tile matrix sets supported by the WMTS service.

    Returns
    -------
    List[TileMatrixSet]
        New instances of each default tile matrix set.
    """
    return [
        TileMatrixSet(
            name="WebMercatorQuad",
            crs="urn:ogc:def:crs:EPSG::3857",
            wkss=WELL_KNOWN_SCALE_SET_PREFIX + "GoogleMapsCompatible",
            bounds=WEB_MERCATOR_BOUNDS,
        ),
        TileMatrixSet(
            name="WorldCRS84Quad",
            crs="urn:ogc:def:crs:OGC:2:84",
            wkss=WELL_KNOWN_SCALE_SET_PREFIX + "GlobalCRS84Pixel",
            bounds=GEOGRAPHIC_BOUNDS,
            level_zero_matrix_width=2,
        ),
        TileMatrixSet(
            name="GoogleCRS84Quad",
            crs="urn:ogc:def:crs:OGC:2:84",
            wkss=WELL_KNOWN_SCALE_SET_PREFIX + "GoogleCRS84Quad",
            bounds=LEGACY_GEOGRAPHIC_BOUNDS,
        ),
    ]
