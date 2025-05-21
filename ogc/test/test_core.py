from ogc import core
from ogc import podpac as pogc

import podpac
import numpy as np
from ogc.wcs_response_1_0_0 import Coverage

# Create some podpac nodes
data = np.random.rand(11, 21)
lat = np.linspace(90, -90, 11)
lon = np.linspace(-180, 180, 21)
coords = podpac.Coordinates([lat, lon], dims=["lat", "lon"])
node1 = podpac.data.Array(source=data, coordinates=coords)

data2 = np.random.rand(11, 21)
node2 = podpac.data.Array(source=data2, coordinates=coords)

# Use podpac nodes to create some test OGC layers
layer1 = pogc.Layer(
    node=node1,
    identifier="layer1",
    title="OGC/POPAC layer containing random data",
    abstract="This layer contains some random data",
)

layer2 = pogc.Layer(
    node=node2,
    identifier="layer2",
    title="FOUO: Another OGC/POPAC layer containing random data",
    abstract="Marked as FOUO. This layer contains some random data. Same coordinates as layer1, but different values.",
    is_fouo=True,
)


def test_ogc_core_get_coverage_from_id():
    """
    Test the get_coverage_from_id method of the OGC class with a valid ID.
    """
    ogc = core.OGC(layers=[layer1, layer2])
    coverage = ogc.get_coverage_from_id(layer1.identifier)

    assert isinstance(coverage, Coverage)
    assert coverage.identifier == layer1.identifier
    assert coverage.title == layer1.title
    assert coverage.abstract == layer1.abstract


def test_ogc_core_get_coverage_from_invalid_id():
    """
    Test the get_coverage_from_id method of the OGC class with an invalid ID.
    """
    ogc = core.OGC(layers=[layer1, layer2])
    try:
        ogc.get_coverage_from_id("invalid_id")
    except core.WCSException:
        pass
    else:
        assert False, "Expected WCSException not raised."


def test_ogc_core_handle_wcs_kv_get_capabilities():
    """
    Test the handle_wcs_kv method of the OGC class with a valid GetCapabilities request.
    """
    ogc = core.OGC(layers=[layer1, layer2])
    args = {
        "request": "GetCapabilities",
        "service": "WCS",
        "version": "1.0.0",
        "base_url": "http://example.com/wcs",
    }
    response = ogc.handle_wcs_kv(args)
    assert isinstance(response, str)
    assert "WCS_Capabilities" in response


def test_ogc_core_handle_wcs_kv_get_capabilities_invalid_service():
    """
    Test the handle_wcs_kv method of the OGC class with an invalid GetCapabilities request.
    """
    ogc = core.OGC(layers=[layer1, layer2])
    args = {
        "request": "GetCapabilities",
        "service": "InvalidService",
        "version": "1.0.0",
        "base_url": "http://example.com/wcs",
    }
    try:
        ogc.handle_wcs_kv(args)
    except core.WCSException:
        pass
    else:
        assert False, "Expected WCSException not raised."


def test_ogc_core_handle_wcs_kv_describe_coverage():
    """
    Test the handle_wcs_kv method of the OGC class with a valid DescribeCoverage request.
    """
    ogc = core.OGC(layers=[layer1, layer2])
    args = {
        "request": "DescribeCoverage",
        "service": "WCS",
        "version": "1.0.0",
        "coverage": layer1.identifier,
    }
    response = ogc.handle_wcs_kv(args)
    assert isinstance(response, str)
    assert "CoverageDescription" in response


def test_ogc_core_handle_wcs_kv_describe_coverage_invalid_version():
    """
    Test the handle_wcs_kv method of the OGC class with an invalid DescribeCoverage request.
    """
    ogc = core.OGC(layers=[layer1, layer2])
    args = {
        "request": "DescribeCoverage",
        "service": "WCS",
        "version": "InvalidVersion",
        "coverage": layer1.identifier,
    }
    try:
        ogc.handle_wcs_kv(args)
    except core.WCSException:
        pass
    else:
        assert False, "Expected WCSException not raised."


def test_ogc_core_handle_wcs_kv_get_coverage():
    """
    Test the handle_wcs_kv method of the OGC class with a valid GetCoverage request.
    """
    ogc = core.OGC(layers=[layer1, layer2])
    args = {
        "request": "GetCoverage",
        "service": "WCS",
        "version": "1.0.0",
        "coverage": layer1.identifier,
        "format": "GeoTIFF",
        "bbox": "-132.90225856307210961,23.62932030249929483,-53.60509752693091912,53.75883389158821046",
        "crs": "EPSG:4326",
        "response_crs": "EPSG:4326",
        "width": 346,
        "height": 131,
    }
    response = ogc.handle_wcs_kv(args)
    assert isinstance(response["fn"], str)
    assert response["fn"].endswith(".tif")
    assert response["fp"] is not None


def test_ogc_core_handle_wms_kv_get_capabilities():
    """
    Test the handle_wms_kv method of the OGC class with a valid GetCapabilities request.
    """
    ogc = core.OGC(layers=[layer1, layer2])
    args = {
        "request": "GetCapabilities",
        "service": "WMS",
        "version": "1.3.0",
        "base_url": "http://example.com/wms",
    }
    response = ogc.handle_wms_kv(args)
    assert isinstance(response, str)
    assert "WMS_Capabilities" in response


def test_ogc_core_handle_wms_kv_get_capabilities_invalid_service():
    """
    Test the handle_wms_kv method of the OGC class with an invalid GetCapabilities request.
    """
    ogc = core.OGC(layers=[layer1, layer2])
    args = {
        "request": "GetCapabilities",
        "service": "InvalidService",
        "version": "1.3.0",
        "base_url": "http://example.com/wms",
    }
    try:
        ogc.handle_wms_kv(args)
    except core.WCSException:
        pass
    else:
        assert False, "Expected WCSException not raised."


def test_ogc_core_handle_wms_kv_get_feature_info_unsupported():
    """
    Test the handle_wms_kv method of the OGC class with an unsupported GetFeatureInfo request.
    """
    ogc = core.OGC(layers=[layer1, layer2])
    args = {
        "request": "GetFeatureInfo",
        "service": "WMS",
        "version": "1.3.0",
        "coverage": layer1.identifier,
    }
    try:
        ogc.handle_wms_kv(args)
    except core.WCSException:
        pass
    else:
        assert False, "Expected WCSException not raised."


def test_ogc_core_handle_wms_kv_get_legend_graphic():
    """
    Test the handle_wms_kv method of the OGC class with a valid GetLegendGraphic request.
    """
    ogc = core.OGC(layers=[layer1, layer2])
    args = {
        "request": "GetLegendGraphic",
        "service": "WMS",
        "version": "1.3.0",
        "layer": layer1.identifier,
        "style": "default",
        "format": "image/png",
    }
    response = ogc.handle_wms_kv(args)
    assert isinstance(response["fn"], str)
    assert response["fn"].endswith(".png")
    assert response["fp"] is not None


def test_ogc_core_handle_wms_kv_get_legend_graphic_invalid_version():
    """
    Test the handle_wms_kv method of the OGC class with an invalid GetLegendGraphic request.
    """
    ogc = core.OGC(layers=[layer1, layer2])
    args = {
        "request": "GetLegendGraphic",
        "service": "WMS",
        "version": "InvalidVersion",
        "layers": layer1.identifier,
        "style": "default",
        "format": "image/png",
    }
    try:
        ogc.handle_wms_kv(args)
    except core.WCSException:
        pass
    else:
        assert False, "Expected WCSException not raised."


def test_ogc_core_handle_wms_kv_get_map():
    """
    Test the handle_wms_kv method of the OGC class with a GetMap request.
    """
    ogc = core.OGC(layers=[layer1, layer2])
    args = {
        "request": "GetMap",
        "service": "WMS",
        "version": "1.3.0",
        "layers": layer1.identifier,
        "format": "image/png",
        "transparent": "true",
        "height": 256,
        "width": 256,
        "crs": "EPSG:3857",
        "bbox": "-10018754.171394622,2504688.5428486555,-7514065.628545966,5009377.08569731",
    }
    response = ogc.handle_wms_kv(args)
    assert isinstance(response["fn"], str)
    assert response["fn"].endswith(".png")
    assert response["fp"] is not None
