import pytest
import traitlets as tl
from typing import Dict, Any
from podpac import Coordinates
from ogc import settings
from ogc.podpac import _uppercase_for_dict_keys
from ogc.wmts.wmts_request_1_0_0 import GetCapabilities, GetTile, TileMatrixSet, supported_tile_matrix_sets


def get_tile_matrix_set(name: str) -> TileMatrixSet:
    """Get a supported tile matrix set by name."""
    return next(supported for supported in supported_tile_matrix_sets() if supported.name == name)


def make_valid_tile_arguments() -> Dict[str, Any]:
    """Create a valid arguments dictionary for a get tile request.

    Returns
    -------
    Dict[str, Any]
        Valid dictionary for a get tile request.
    """
    return {
        "request": "GetTile",
        "service": "wmts",
        "version": "1.0.0",
        "layer": "layer",
        "tilematrixset": "WebMercatorQuad",
        "tilerow": "0",
        "tilecol": "0",
        "tilematrix": "0",
        "format": "image/png",
    }


def make_valid_capabilities_arguments() -> Dict[str, Any]:
    """Create a valid arguments dictionary for a get capabilities request.

    Returns
    -------
    Dict[str, Any]
        Valid dictionary for a get capabilities request.
    """
    return {
        "request": "GetCapabilities",
        "service": "wmts",
        "version": "1.0.0",
    }


def test_get_capabilities_validate_success():
    """Validate a correct GetCapabilities request."""
    capabilities = GetCapabilities()
    capabilities.load_from_kv(make_valid_capabilities_arguments())
    capabilities.validate()


def test_getcapabilities_validate_invalid_service():
    """Ensure validation fails when service is not WMTS."""
    capabilities = GetCapabilities()
    capabilities.load_from_kv(make_valid_capabilities_arguments())
    capabilities.service = "WMS"

    with pytest.raises(AssertionError):
        capabilities.validate()


def test_getcapabilities_load_from_kv_invalid_request():
    """Ensure invalid request type raises assertion."""
    capabilities = GetCapabilities()
    args = make_valid_capabilities_arguments()
    args["request"] = "invalid"

    with pytest.raises(AssertionError):
        capabilities.load_from_kv(args)


def test_get_tile_validate_success():
    """Validate a correct GetTile request."""
    tile = GetTile()
    tile.load_from_kv(make_valid_tile_arguments())
    tile.validate()


def test_get_tile_validate_missing_layer():
    """Ensure validation fails when layer is missing."""
    tile = GetTile()
    args = make_valid_tile_arguments()
    args["layer"] = None
    tile.load_from_kv(args)

    with pytest.raises(AssertionError):
        tile.validate()


def test_get_tile_validate_invalid_tile_row():
    """Ensure tile row outside valid range raises error."""
    tile = GetTile()
    args = make_valid_tile_arguments()
    args["tilerow"] = "-1"
    tile.load_from_kv(args)

    with pytest.raises(AssertionError):
        tile.validate()


@pytest.mark.parametrize(
    "input_number,expected",
    [
        (1.234567891234, "1.234567891"),
        (10, "10"),
    ],
)
def test_format_number(input_number: float | int, expected: str):
    """Validate number formatting logic.

    Parameters
    ----------
    input_number : float | int
        Input number to format.
    expected : str
        Expected string output.
    """
    result = TileMatrixSet().format_number(input_number)
    assert result == expected


def test_convert_to_map_args_structure():
    """Ensure GetTile converts correctly to map request args."""
    tile = GetTile()
    tile.load_from_kv(make_valid_tile_arguments())
    tile.params = {"time": "0"}

    result = tile.convert_to_map_args()

    assert "bbox" in result
    assert result["service"] == "WMTS"
    assert result["crs"] == tile.tile_matrix_set.crs
    assert result["height"] == settings.WMTS_TILE_SIZE
    assert result["width"] == settings.WMTS_TILE_SIZE
    assert result["format"] == "image/png"
    assert result["PARAMS"] == '{"time": "0"}'


def test_bbox_web_mercator_returns_valid_string():
    """Validate Web Mercator bounding box output format."""
    bbox = get_tile_matrix_set("WebMercatorQuad").calculate_eval_bounding_box(row=0, column=0, matrix_level=0)

    assert isinstance(bbox, str)
    assert len(bbox.split(",")) == 4


def test_bbox_world_crs84_returns_valid_string():
    """Validate CRS84 bounding box output format."""
    bbox = get_tile_matrix_set("WorldCRS84Quad").calculate_eval_bounding_box(row=0, column=0, matrix_level=0)

    assert isinstance(bbox, str)
    assert len(bbox.split(",")) == 4


@pytest.mark.parametrize(
    "tile_matrix_set, matrix_level, expected_scale_denominator",
    [
        (get_tile_matrix_set("WebMercatorQuad"), 0, 559082264),
        (get_tile_matrix_set("WebMercatorQuad"), 1, 279541132),
        (get_tile_matrix_set("WorldCRS84Quad"), 0, 279541132),
        (get_tile_matrix_set("WorldCRS84Quad"), 1, 139770566),
        (get_tile_matrix_set("EPSG:900913"), 0, 559082264),
        (get_tile_matrix_set("EPSG:4326"), 0, 279541132),
        (get_tile_matrix_set("EPSG:3575"), 0, 117028571.4),
        (get_tile_matrix_set("EPSG:3575"), 1, 58514285.7),
        (get_tile_matrix_set("EPSG:3031"), 0, 117028571.4),
        (get_tile_matrix_set("EPSG:3031"), 1, 58514285.7),
    ],
)
def test_calculate_scale_denominator(
    tile_matrix_set: TileMatrixSet, matrix_level: int, expected_scale_denominator: float
):
    """Ensure scale denominator scales correctly by zoom level.

    Parameters
    ----------
    tile_matrix_set : TileMatrixSet
        The tile matrix set.
    matrix_level: int
        The zoom level for the calculation.
    expected_scale_denominator : float
        Expected scale denominator.
    """
    result = tile_matrix_set.calculate_scale_denominator(matrix_level)
    assert float(result) == pytest.approx(expected_scale_denominator, rel=1e-6)


@pytest.mark.parametrize(
    "tile_matrix_set, matrix_level, expected_width, expected_height",
    [
        (get_tile_matrix_set("WebMercatorQuad"), 0, "1", "1"),
        (get_tile_matrix_set("WebMercatorQuad"), 1, "2", "2"),
        (get_tile_matrix_set("WebMercatorQuad"), 2, "4", "4"),
        (get_tile_matrix_set("WorldCRS84Quad"), 0, "2", "1"),
        (get_tile_matrix_set("WorldCRS84Quad"), 1, "4", "2"),
        (get_tile_matrix_set("WorldCRS84Quad"), 2, "8", "4"),
        (get_tile_matrix_set("EPSG:900913"), 2, "4", "4"),
        (get_tile_matrix_set("EPSG:4326"), 2, "8", "4"),
        (get_tile_matrix_set("EPSG:3575"), 2, "4", "4"),
        (get_tile_matrix_set("EPSG:3031"), 2, "4", "4"),
    ],
)
def test_calculate_matrix_sizes(
    tile_matrix_set: TileMatrixSet, matrix_level: int, expected_width: str, expected_height: str
):
    """Calculate matrix sizes based on zoom level.

    Parameters
    ----------
    tile_matrix_set : TileMatrixSet
        The tile matrix set.
    matrix_level: int
        The zoom level for the calculation.
    expected_width : str
        The expected matrix width.
    expected_height : str
        The expected matrix height.
    """
    width, height = tile_matrix_set.calculate_matrix_sizes(matrix_level)

    assert width == expected_width
    assert height == expected_height


@pytest.mark.parametrize("tile_matrix_set", supported_tile_matrix_sets())
def test_get_tile_load_from_kv_tile_matrix_set(tile_matrix_set: TileMatrixSet):
    """Ensure each supported tile matrix set is selected by name, ignoring case.

    Parameters
    ----------
    tile_matrix_set : TileMatrixSet
        The tile matrix set.
    """
    tile = GetTile()
    args = make_valid_tile_arguments()
    args["tilematrixset"] = tile_matrix_set.name.lower()
    tile.load_from_kv(args)
    tile.validate()

    assert tile.tile_matrix_set.name == tile_matrix_set.name
    assert tile.convert_to_map_args()["crs"] == tile_matrix_set.crs


def test_get_tile_load_from_kv_unknown_tile_matrix_set():
    """Ensure an unknown tile matrix set fails validation."""
    tile = GetTile()
    args = make_valid_tile_arguments()
    args["tilematrixset"] = "EPSG:9999"
    tile.load_from_kv(args)

    with pytest.raises(tl.TraitError):
        tile.validate()


@pytest.mark.parametrize("tile_matrix_set", supported_tile_matrix_sets())
def test_get_tile_validate_invalid_tile_column(tile_matrix_set: TileMatrixSet):
    """Ensure tile column just past the matrix width raises error for each tile matrix set.

    Parameters
    ----------
    tile_matrix_set : TileMatrixSet
        The tile matrix set.
    """
    matrix_width, _ = tile_matrix_set.calculate_matrix_sizes(1)
    tile_matrix_set.validate_tile(row=0, column=int(matrix_width) - 1, matrix_level=1)

    with pytest.raises(AssertionError):
        tile_matrix_set.validate_tile(row=0, column=int(matrix_width), matrix_level=1)


@pytest.mark.parametrize(
    "tile_matrix_set, row, column, expected_bbox",
    [
        (get_tile_matrix_set("WebMercatorQuad"), 0, 1, [20037508.342789244, 0.0, 0.0, 20037508.342789244]),
        (get_tile_matrix_set("EPSG:900913"), 1, 0, [0.0, -20037508.342789244, -20037508.342789244, 0.0]),
        (get_tile_matrix_set("WorldCRS84Quad"), 0, 3, [90.0, 90.0, 0.0, 180.0]),
        (get_tile_matrix_set("EPSG:4326"), 1, 0, [0.0, -180.0, -90.0, -90.0]),
        (get_tile_matrix_set("EPSG:3575"), 0, 0, [4194304.0, -4194304.0, 0.0, 0.0]),
        (get_tile_matrix_set("EPSG:3031"), 1, 1, [0.0, 0.0, -4194304.0, 4194304.0]),
    ],
)
def test_bbox_tile(tile_matrix_set: TileMatrixSet, row: int, column: int, expected_bbox: list):
    """Validate bounding boxes are in y, x order for the requested matrix level one tile."""
    bbox = [float(value) for value in tile_matrix_set.calculate_eval_bounding_box(row, column, 1).split(",")]
    assert bbox == pytest.approx(expected_bbox)


def test_epsg4326_corners_use_lat_lon_axis_order():
    """Ensure EPSG:4326 corners are written in latitude, longitude order."""
    xml = get_tile_matrix_set("EPSG:4326").to_xml()

    assert "<TopLeftCorner>90.000000000 -180.000000000</TopLeftCorner>" in xml
    assert "<ows:LowerCorner>-90.000000000 -180.000000000</ows:LowerCorner>" in xml
    assert "<ows:UpperCorner>90.000000000 180.000000000</ows:UpperCorner>" in xml


def test_projected_quad_omits_well_known_scale_set():
    """Ensure tile matrix sets without a well known scale set omit the element."""
    xml = get_tile_matrix_set("EPSG:3031").to_xml()

    assert "<WellKnownScaleSet>" not in xml
    assert "<TopLeftCorner>-4194304.000000000 4194304.000000000</TopLeftCorner>" in xml


@pytest.mark.parametrize("tile_matrix_set", supported_tile_matrix_sets())
def test_get_tile_podpac_lat_lon_order(tile_matrix_set: TileMatrixSet):
    """Ensure podpac reads the tile with lat as the crs y axis and lon as the crs x axis.

    Tile row 0, column 1 at matrix level 2 is north (y > 0) and west (x < 0) of the origin in every tile matrix set.
    """
    args = make_valid_tile_arguments()
    args.update(tilematrixset=tile_matrix_set.name, tilematrix="2", tilerow="0", tilecol="1")
    tile = GetTile()
    tile.load_from_kv(args)

    coordinates = Coordinates.from_url(_uppercase_for_dict_keys(tile.convert_to_map_args()))

    assert coordinates["lat"].coordinates.min() > 0
    assert coordinates["lon"].coordinates.max() < 0
