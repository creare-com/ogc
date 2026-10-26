import logging
import json
import pyproj
import traitlets as tl
from typing import Dict, Any, List, Tuple

from ogc import ogc_common
from ogc import settings
from podpac.core.utils import VALID_DIMENSION_NAMES
from ogc.wcs_request_1_0_0 import Identifier

logger = logging.getLogger(__file__)
escape_format = ogc_common.EscapeFormatter().format
WMTS_VALIDATION_ERROR = "WMTS Request validation error: service should be WMTS"


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


def supported_tile_matrix_sets() -> List[TileMatrixSet]:
    """Get the tile matrix sets supported by the WMTS service.

    Returns
    -------
    List[TileMatrixSet]
        New instances of each supported tile matrix set.
    """
    return [TileMatrixSet(name=name, **kwargs) for name, kwargs in settings.WMTS_TILE_MATRIX_SETS.items()]


class GetCapabilities(ogc_common.XMLNode):
    """
    Request to a WMTS server to perform the GetCapabilities operation.
    This operation allows a client to retrieve a Capabilities XML document providing
    metadata for the specific WMTS server. In this XML encoding, no "request" parameter
    is included, since the element name specifies the specific operation.
    """

    service = tl.Unicode(default_value=None, allow_none=True)

    accept_versions = tl.List(trait=tl.Unicode(default_value=None, allow_none=True))
    accept_formats = tl.List(trait=tl.Instance(klass=ogc_common.OutputFormat))

    def validate(self):
        """Validate the get capabilities request."""
        assert self.service == "WMTS", WMTS_VALIDATION_ERROR

        for obj in self.accept_formats:
            obj.validate()

    def _load_from_kv(self, args: Dict[str, Any]):
        """Initialize the properties of the class from a key-value argument dictionary.

        Parameters
        ----------
        args : Dict[str, Any]
            Request arguments for the get capabilities request.
        """
        assert args["request"] == "GetCapabilities", args["request"]
        self.service = args["service"].upper()


class GetTile(ogc_common.XMLNode):
    """
    Request to a WMTS to perform the GetTile operation.

    This operation allows a client to retrieve a
    subset of one coverage. In this XML encoding, no "request" parameter is
    included, since the element name specifies the specific operation.
    """

    service = tl.Unicode(default_value=None, allow_none=True)
    version = tl.Unicode(default_value=None, allow_none=True)

    layer = tl.Instance(klass=Identifier)
    tile_matrix_set = tl.Instance(klass=TileMatrixSet)
    row = tl.Int()
    column = tl.Int()
    matrix_level = tl.Int()
    output_format = tl.Enum(
        default_value=None,
        values=["image/png", "image/png; mode=8bit", "image/png;mode=8-bit"],
    )
    params = tl.Dict(tl.Unicode(), tl.Unicode(), default_value={})

    def validate(self):
        """Validate the get tile request."""
        assert self.service == "WMTS", WMTS_VALIDATION_ERROR
        assert self.output_format is not None, "WMTS Request validation error: no output format specified"
        self.layer.validate()
        self.tile_matrix_set.validate_tile(self.row, self.column, self.matrix_level)

    def _load_from_kv(self, args: Dict[str, Any]):
        """Initialize traitlet properties from a key-value argument dictionary.

        Parameters
        ----------
        args : Dict[str, Any]
            Request arguments for the get tile request.
        """
        assert args["request"].lower() == "gettile", args["request"]
        self.service = args["service"].upper()
        self.version = args["version"]
        self.layer = Identifier(value=args["layer"])

        row = args.get("tilerow")
        column = args.get("tilecol")
        matrix_level = args.get("tilematrix")
        self.row = int(row) if row is not None else None
        self.column = int(column) if column is not None else None
        self.matrix_level = int(matrix_level) if matrix_level is not None else None
        tile_matrix_set_name = args.get("tilematrixset", "")

        for tile_matrix_set in supported_tile_matrix_sets():
            if tile_matrix_set_name.lower() == tile_matrix_set.name.lower():
                self.tile_matrix_set = tile_matrix_set
                break

        if "format" in args:
            self.output_format = str(args["format"])

        # Check for dimensions and add to params
        self.params = {}
        for key, value in args.items():
            key_dimension = next((dim for dim in VALID_DIMENSION_NAMES if dim.lower() == key.lower()), None)
            if key_dimension:
                self.params[key_dimension] = value

    def _load_xml_doc(self, xml_doc: str):
        """Initialize traitlet properties from a XML document.
        Parameters
        ----------
        xml_doc : str
            The XML document to unpack.

        Raises
        ------
        NotImplementedError
            Not implemented.
        """
        raise NotImplementedError()

    def convert_to_map_args(self) -> Dict[str, Any]:
        """Converts the arguments from a get tile request into a get map request.

        Returns
        -------
        Dict[str, Any]
            The arguments which are valid for a get map request.
        """
        return {
            "PARAMS": json.dumps(self.params),  # this needs to be capitalized for podpac
            "crs": self.tile_matrix_set.crs,
            "height": settings.WMTS_TILE_SIZE,
            "width": settings.WMTS_TILE_SIZE,
            "bbox": self.tile_matrix_set.calculate_eval_bounding_box(self.row, self.column, self.matrix_level),
            "format": self.output_format,
            "version": self.version,
            "service": self.service,
        }
