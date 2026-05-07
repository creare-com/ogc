import pytest
import struct
from typing import List, Dict, Any
from ogc import core
from ogc import podpac as pogc
from ogc.wmts.wmts_routes import WmtsRoutes
from ogc.wms_response_1_3_0 import Coverage


def make_valid_tile_arguments(coverages: List[Coverage]) -> Dict[str, Any]:
    """Create a valid arguments dictionary for a get tile request.

    Parameters
    ----------
    coverages : List[Coverage]
        Coverages to get a layer from.

    Returns
    -------
    Dict[str, Any]
        Valid dictionary for a get tile request.
    """
    return {
        "request": "GetTile",
        "service": "WMTS",
        "version": "1.0.0",
        "layer": coverages[0].layer.identifier,
        "format": "image/png",
        "tilerow": 0,
        "tilecol": 0,
        "tilematrixset": "WebMercatorQuad",
        "tilematrix": "0",
        "time": str(coverages[0].layer.get_coordinates()["time"].coordinates[0]),
    }


def test_handle_wmts_kv_get_capabilities_from_ogc_core(layers: List[pogc.Layer]):
    """Test the handle_wmts_kv method of the OGC class with a valid WMTS GetCapabilities request.

    Parameters
    ----------
    layers : List[pogc.Layer]
        Layers provided by a test fixture.
    """
    ogc = core.OGC(layers=layers)
    args = {
        "request": "GetCapabilities",
        "service": "WMTS",
        "version": "1.0.0",
        "base_url": "/",
    }
    response = ogc.handle_wmts_kv(args)
    assert isinstance(response, str)
    assert "Capabilities" in response and "wmts/1.0" in response


def test_handle_kv_get_capabilities(coverages: List[Coverage]):
    """Test the handle_wmts_kv method of the WMTS routes class with a valid GetCapabilities request.

    Parameters
    ----------
    coverages : List[Coverage]
        Coverages provided by a test fixture.
    """
    wmts_routes = WmtsRoutes(coverages=coverages)
    args = {
        "request": "GetCapabilities",
        "service": "WMTS",
        "version": "1.0.0",
        "base_url": None,
    }
    response = wmts_routes.handle_kv(args)
    assert isinstance(response, str)
    assert "Capabilities" in response and "wmts/1.0" in response


def test_handle_kv_get_capabilities_invalid_service(coverages: List[Coverage]):
    """Test the handle_kv method of the WMTS routes class with an invalid GetCapabilities request.

    Parameters
    ----------
    coverages : List[Coverage]
        Coverages provided by a test fixture.
    """
    wmts_routes = WmtsRoutes(coverages=coverages)
    args = {
        "request": "GetCapabilities",
        "service": "InvalidService",
        "version": "1.0.0",
        "base_url": None,
    }

    with pytest.raises(core.WMTSException):
        wmts_routes.handle_kv(args)


def test_handle_kv_get_feature_info_unsupported(coverages: List[Coverage]):
    """Test the handle_kv method of the WMTS routes class with an unsupported GetFeatureInfo request.

    Parameters
    ----------
    coverages : List[Coverage]
        Coverages provided by a test fixture.
    """
    wmts_routes = WmtsRoutes(coverages=coverages)
    args = {
        "request": "GetFeatureInfo",
        "service": "WMTS",
        "version": "1.0.0",
        "coverage": coverages[0].layer.identifier,
    }

    with pytest.raises(core.WMTSException):
        wmts_routes.handle_kv(args)


def test_handle_kv_get_tile(coverages: List[Coverage]):
    """Test the handle_kv method of the WMTS routes class with a GetTile request.

    Parameters
    ----------
    coverages : List[Coverage]
        Coverages provided by a test fixture.
    """
    wmts_routes = WmtsRoutes(coverages=coverages)
    args = make_valid_tile_arguments(coverages)
    response = wmts_routes.handle_kv(args)
    assert isinstance(response["fn"], str)
    assert response["fn"].endswith(".png")
    assert response["fp"] is not None

    # Check height and width without additional packages
    response["fp"].seek(16)
    chunk = response["fp"].read(8)
    assert struct.unpack(">II", chunk) == (256, 256)


def test_handle_kv_get_tile_invalid_version(coverages: List[Coverage]):
    """Test the handle_kv method of the WMTS routes class with a GetTile request with an invalid version.

    Parameters
    ----------
    coverages : List[Coverage]
        Coverages provided by a test fixture.
    """
    wmts_routes = WmtsRoutes(coverages=coverages)
    args = make_valid_tile_arguments(coverages)
    args["version"] = "invalid"

    with pytest.raises(core.WMTSException):
        wmts_routes.handle_kv(args)


def test_handle_kv_get_tile_invalid_tile_indices(coverages: List[Coverage]):
    """Test the handle_kv method of the WMTS routes class with a GetTile request with an invalid tile row.

    Parameters
    ----------
    coverages : List[Coverage]
        Coverages provided by a test fixture.
    """
    wmts_routes = WmtsRoutes(coverages=coverages)
    args = make_valid_tile_arguments(coverages)
    args["tilerow"] = "-1"

    with pytest.raises(core.WMTSException):
        wmts_routes.handle_kv(args)


def test_handle_kv_with_invalid_request(coverages: List[Coverage]):
    """Test the handle_kv method of the WMTS routes class with a GetTile request with an invalid request.

    Parameters
    ----------
    coverages : List[Coverage]
        Coverages provided by a test fixture.
    """
    wmts_routes = WmtsRoutes(coverages=coverages)
    args = make_valid_tile_arguments(coverages)
    args["request"] = "invalid"

    with pytest.raises(core.WMTSException):
        wmts_routes.handle_kv(args)
