import logging
import json
import traitlets as tl
from typing import Dict, Any

from ogc import ogc_common
from ogc import settings
from podpac.core.utils import VALID_DIMENSION_NAMES
from ogc.wcs_request_1_0_0 import Identifier
from .wmts_tile_matrix_set import TileMatrixSet, default_tile_matrix_sets

logger = logging.getLogger(__file__)
escape_format = ogc_common.EscapeFormatter().format
WMTS_VALIDATION_ERROR = "WMTS Request validation error: service should be WMTS"


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
    tile_matrix_sets = tl.List(trait=tl.Instance(klass=TileMatrixSet))
    tile_matrix_set = tl.Instance(klass=TileMatrixSet)
    row = tl.Int()
    column = tl.Int()
    matrix_level = tl.Int()
    output_format = tl.Enum(
        default_value=None,
        values=["image/png", "image/png; mode=8bit", "image/png;mode=8-bit"],
    )
    params = tl.Dict(tl.Unicode(), tl.Unicode(), default_value={})

    @tl.default("tile_matrix_sets")
    def _default_tile_matrix_sets(self):
        return default_tile_matrix_sets()

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

        for tile_matrix_set in self.tile_matrix_sets:
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
