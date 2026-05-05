import pytest
from typing import Dict, Any
from ogc import settings
from ogc.wmts.wmts_request_1_0_0 import GetCapabilities, GetTile, WebMercatorQuad, WorldCRS84Quad, TileMatrixSet


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
    tile.tile_matrix_set = WebMercatorQuad()

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
    tile = GetTile()
    tile.load_from_kv(make_valid_tile_arguments())
    tile.tile_matrix_set = WebMercatorQuad(row=0, column=0, matrix_level=0)
    bbox = tile.tile_matrix_set.calculate_eval_bounding_box()

    assert isinstance(bbox, str)
    assert len(bbox.split(",")) == 4


def test_bbox_world_crs84_returns_valid_string():
    """Validate CRS84 bounding box output format."""
    tile = GetTile()
    tile.load_from_kv(make_valid_tile_arguments())
    tile.tile_matrix_set = WorldCRS84Quad(row=0, column=0, matrix_level=0)
    bbox = tile.tile_matrix_set.calculate_eval_bounding_box()

    assert isinstance(bbox, str)
    assert len(bbox.split(",")) == 4


@pytest.mark.parametrize(
    "tile_matrix_set, matrix_level, expected_scale_denominator",
    [
        (WebMercatorQuad(), 0, 559082264),
        (WebMercatorQuad(), 1, 279541132),
        (WorldCRS84Quad(), 0, 279541132),
        (WorldCRS84Quad(), 1, 139770566),
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
        (WebMercatorQuad(), 0, "1", "1"),
        (WebMercatorQuad(), 1, "2", "2"),
        (WebMercatorQuad(), 2, "4", "4"),
        (WorldCRS84Quad(), 0, "2", "1"),
        (WorldCRS84Quad(), 1, "4", "2"),
        (WorldCRS84Quad(), 2, "8", "4"),
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
