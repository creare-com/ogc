import logging
import json
import traitlets as tl
from typing import Dict, Any, Tuple

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
    matrix_levels = tl.List(tl.Int(), default_value=list(range(0, 21)))
    depth = tl.Int(default_value=2)
    indent = "    "

    row = tl.Int()
    column = tl.Int()
    matrix_level = tl.Int()

    def validate(self):
        """Validate the tile matrix set."""
        assert len(self.name) > 0, "WMTS Request validation error: tile matrix set name not found"
        assert len(self.crs) > 0, "WMTS Request validation error: tile matrix set crs not found"
        assert len(self.wkss) > 0, "WMTS Request validation error: tile matrix set wkss not found"
        assert len(self.bounds) > 0, "WMTS Request validation error: tile matrix set bounds not found"
        assert len(self.matrix_levels) > 0, "WMTS Request validation error: tile matrix levels not found"
        assert self.matrix_level >= 0 and self.matrix_level <= max(
            self.matrix_levels
        ), "WMTS Request validation error: tile matrix level not in range"

    def to_xml(self):
        xml = ""
        xml += self.indent * self.depth + "<TileMatrixSet>\n"
        xml += self.indent * (self.depth + 1) + escape_format("<ows:Identifier>{}</ows:Identifier>\n", self.name)
        xml += self.indent * (self.depth + 1) + escape_format("<ows:SupportedCRS>{}</ows:SupportedCRS>\n", self.crs)
        xml += self._bounding_box_tile_matrix_set() if self.crs is not None else ""
        xml += self.indent * (self.depth + 1) + escape_format("<WellKnownScaleSet>{}</WellKnownScaleSet>\n", self.wkss)
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

    def calculate_eval_bounding_box(self) -> str:
        """Determine the bounding box for evaluation."""
        raise NotImplementedError

    def _top_left_corner(self) -> str | None:
        """Get the top left corner of the bounded area defined by the tile matrix set.

        Returns
        -------
        str | None
            The top left corner as a string or None if the CRS is not valid for WMTS.
        """
        if self.bounds is not None:
            x_min = TileMatrixSet._format_number(self.bounds["minx"])
            y_max = TileMatrixSet._format_number(self.bounds["maxy"])
            return "{} {}".format(x_min, y_max)

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
                """<ows:LowerCorner>{x} {y}</ows:LowerCorner>\n""",
                x=self._format_number(self.bounds["minx"]),
                y=self._format_number(self.bounds["miny"]),
            )
            xml += self.indent * (self.depth + 2) + escape_format(
                """<ows:UpperCorner>{x} {y}</ows:UpperCorner>\n""",
                x=self._format_number(self.bounds["maxx"]),
                y=self._format_number(self.bounds["maxy"]),
            )
            xml += self.indent * (self.depth + 1) + """</ows:BoundingBox>\n"""

        return xml

    @staticmethod
    def calculate_scale_denominator(matrix_level: int) -> str:
        """Calculate the scale denominator for the zoom level."""
        raise NotImplementedError

    @staticmethod
    def calculate_matrix_sizes(matrix_level) -> Tuple[str, str]:
        """Calculate the scale denominator for the matrix level."""
        raise NotImplementedError

    @staticmethod
    def _format_number(input_number: float | int, float_decimals: int = 9) -> str:
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


class WebMercatorQuad(TileMatrixSet):
    """Tile matrix set for Web Mercator Quad format."""

    name = tl.Unicode(default_value="WebMercatorQuad")
    crs = tl.Unicode(default_value="urn:ogc:def:crs:EPSG::3857")
    wkss = tl.Unicode(default_value="urn:ogc:def:wkss:OGC:1.0:GoogleMapsCompatible")
    bounds = tl.Dict(
        key_trait=tl.Unicode(),
        value_trait=tl.Float(),
        default_value={
            "minx": -20037508.342789244,
            "miny": -20037508.342789244,
            "maxx": 20037508.342789244,
            "maxy": 20037508.342789244,
        },
    )

    def validate(self):
        """Validate the tile matrix set."""
        super().validate()
        assert self.row >= 0 and self.row < 2**self.matrix_level, "WMTS Request validation error: invalid tile row"
        assert (
            self.column >= 0 and self.column < 2**self.matrix_level
        ), "WMTS Request validation error: invalid tile column"

    def calculate_eval_bounding_box(self) -> str:
        """Determine the bounding box for evaluation.

        A zero pixel row and column corresponds to the top left corner.

        Returns
        -------
        str
            The bounding box for the provided tile indices.
        """
        resolution = settings.WMTS_INITIAL_RESOLUTION / (2**self.matrix_level)
        origin_x = self.bounds["minx"]
        origin_y = self.bounds["maxy"]
        tile_size_m = settings.WMTS_TILE_SIZE * resolution

        min_x = self.column * tile_size_m + origin_x
        max_x = (self.column + 1) * tile_size_m + origin_x
        min_y = origin_y - (self.row * tile_size_m)
        max_y = origin_y - ((self.row + 1) * tile_size_m)

        # Hack: Reverse x, y order to get around issues with Coordinates.from_url assuming lat, lon order
        min_x, min_y = min_y, min_x
        max_x, max_y = max_y, max_x

        return ",".join(str(x) for x in [min_x, min_y, max_x, max_y])

    @staticmethod
    def calculate_scale_denominator(matrix_level: int) -> str:
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
        resolution = settings.WMTS_INITIAL_RESOLUTION / (2 ** (matrix_level))
        scale_denominator = resolution / settings.WMTS_PIXEL_SIZE_METERS
        return TileMatrixSet._format_number(scale_denominator)

    @staticmethod
    def calculate_matrix_sizes(matrix_level: int) -> Tuple[str, str]:
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
        matrix_width = 2**matrix_level
        matrix_height = 2**matrix_level
        return TileMatrixSet._format_number(matrix_width), TileMatrixSet._format_number(matrix_height)


class WorldCRS84Quad(TileMatrixSet):
    """Tile matrix set for World CRS84 Quad format."""

    name = tl.Unicode(default_value="WorldCRS84Quad")
    crs = tl.Unicode(default_value="urn:ogc:def:crs:OGC:2:84")
    wkss = tl.Unicode(default_value="urn:ogc:def:wkss:OGC:1.0:GlobalCRS84Pixel")
    bounds = tl.Dict(
        key_trait=tl.Unicode(),
        value_trait=tl.Float(),
        default_value={"minx": -180, "miny": -90, "maxx": 180, "maxy": 90},
    )

    def validate(self):
        """Validate the tile matrix set."""
        super().validate()
        assert self.row >= 0 and self.row < 2**self.matrix_level, "WMTS Request validation error: invalid tile row"
        assert self.column >= 0 and self.column < 2 ** (
            self.matrix_level + 1
        ), "WMTS Request validation error: invalid tile column"

    def calculate_eval_bounding_box(self) -> str:
        """Determine the bounding box for evaluation.

        A zero pixel row and column corresponds to the top left corner.

        Returns
        -------
        str
            The bounding box for the provided tile indices.
        """
        tiles_per_width = 2 ** (self.matrix_level + 1)
        tiles_per_height = 2**self.matrix_level

        tile_width = abs(self.bounds["maxx"] - self.bounds["minx"]) / tiles_per_width
        tile_height = abs(self.bounds["maxy"] - self.bounds["miny"]) / tiles_per_height

        min_x = self.column * tile_width + self.bounds["minx"]
        max_x = (self.column + 1) * tile_width + self.bounds["minx"]
        min_y = self.bounds["maxy"] - (self.row * tile_height)
        max_y = self.bounds["maxy"] - ((self.row + 1) * tile_height)

        # Hack: Reverse x, y order to get around issues with Coordinates.from_url assuming lat, lon order
        min_x, min_y = min_y, min_x
        max_x, max_y = max_y, max_x

        return ",".join(str(x) for x in [min_x, min_y, max_x, max_y])

    @staticmethod
    def calculate_scale_denominator(matrix_level: int) -> str:
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
        resolution = settings.WMTS_INITIAL_RESOLUTION / (2 ** (matrix_level + 1))
        scale_denominator = resolution / settings.WMTS_PIXEL_SIZE_METERS
        return TileMatrixSet._format_number(scale_denominator)

    @staticmethod
    def calculate_matrix_sizes(matrix_level: int) -> Tuple[str, str]:
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
        matrix_width = 2 ** (matrix_level + 1)
        matrix_height = 2**matrix_level
        return TileMatrixSet._format_number(matrix_width), TileMatrixSet._format_number(matrix_height)


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
        self.tile_matrix_set.validate()

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
        row = int(row) if row is not None else None
        column = int(column) if column is not None else None
        matrix_level = int(matrix_level) if matrix_level is not None else None
        tile_matrix_set_name = args.get("tilematrixset", "")

        if tile_matrix_set_name.lower() == "webmercatorquad":
            self.tile_matrix_set = WebMercatorQuad(row=row, column=column, matrix_level=matrix_level)
        elif tile_matrix_set_name.lower() == "worldcrs84quad":
            self.tile_matrix_set = WorldCRS84Quad(row=row, column=column, matrix_level=matrix_level)

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
            "bbox": self.tile_matrix_set.calculate_eval_bounding_box(),
            "format": self.output_format,
            "version": self.version,
            "service": self.service,
        }
