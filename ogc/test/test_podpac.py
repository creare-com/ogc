import pytest
import podpac
from ogc import podpac as pogc

LAT = [0.0, 1.0, 2.0]
LON = [10.0, 20.0, 30.0]
TIME = ["2020-01-01", "2020-01-02"]
TIME2 = ["2020-01-02", "2020-01-03"]
ALT = [1.0, 2.0]
CRS_LATLON = "EPSG:4326"
CRS_OTHER = "EPSG:2193"


class MockNode(podpac.Node):
    """A mock node for layer coordinate testing."""

    def __init__(self, coordinates_list):
        self._coordinates_list = coordinates_list

    def find_coordinates(self):
        return self._coordinates_list


class TestLayerGetCoordinates:
    def test_node_is_none(self):
        """Return value should be None when underlying node is None."""
        layer = pogc.Layer()
        assert layer.get_coordinates() is None

    def test_no_coordinates_found(self):
        """Return value should be None when no underlying coordinates exist."""
        layer = pogc.Layer(node=MockNode([]))
        assert layer.get_coordinates() is None

    def test_unstacked_lat_lon(self):
        """Test that unstacked latitude and longitude is valid."""
        source = pogc.Coordinates([LAT, LON, TIME], dims=["lat", "lon", "time"], crs=CRS_LATLON)
        layer = pogc.Layer(node=MockNode([source]))

        coordinates = layer.get_coordinates()

        assert coordinates is not None
        assert set(coordinates.udims) == {"lat", "lon", "time"}
        assert "lat" in coordinates.dims and "lon" in coordinates.dims
        assert coordinates.crs == CRS_LATLON

    def test_stacked_lat_lon(self):
        """Test that stacked latitude and longitude is invalid."""
        source = pogc.Coordinates([[LAT, LON], TIME], dims=["lat_lon", "time"], crs=CRS_LATLON)
        layer = pogc.Layer(node=MockNode([source]))

        with pytest.raises(ValueError, match="Invalid dimensions for coordinate retrieval."):
            layer.get_coordinates()

    def test_no_spatial_dims(self):
        """Test that base spatial dimensions are required."""
        source1 = pogc.Coordinates([TIME], dims=["time"], crs=CRS_LATLON)
        source2 = pogc.Coordinates([TIME2], dims=["time"], crs=CRS_LATLON)
        layer = pogc.Layer(node=MockNode([source1, source2]))

        with pytest.raises(ValueError, match="Invalid dimensions for coordinate retrieval."):
            layer.get_coordinates()

    def test_mixed_stacked_and_unstacked_sources(self):
        """Test that stacked and unstacked coordinates cannot be mixed together."""
        stacked_source = pogc.Coordinates([[LAT, LON], TIME], dims=["lat_lon", "time"], crs=CRS_LATLON)
        unstacked_source = pogc.Coordinates([LAT, LON, TIME2], dims=["lat", "lon", "time"], crs=CRS_LATLON)
        layer = pogc.Layer(node=MockNode([stacked_source, unstacked_source]))

        with pytest.raises(ValueError, match="Invalid dimensions for coordinate retrieval."):
            layer.get_coordinates()

    def test_crs_mismatch_is_reprojected(self):
        """Test that CRS mismatch is transformed to the coordinates which spatial dimensions were pulled from."""
        source1 = pogc.Coordinates([LAT, LON, TIME], dims=["lat", "lon", "time"], crs=CRS_LATLON)
        source2 = pogc.Coordinates([LAT, LON, TIME2], dims=["lat", "lon", "time"], crs=CRS_OTHER)
        layer = pogc.Layer(node=MockNode([source1, source2]))

        coordinates = layer.get_coordinates()

        assert coordinates is not None
        assert coordinates.crs == CRS_LATLON

    def test_duplicate_dims_are_deduped(self):
        """Test that duplicate values are removed."""
        source1 = pogc.Coordinates([LAT, LON, TIME], dims=["lat", "lon", "time"], crs=CRS_LATLON)
        source2 = pogc.Coordinates([LAT, LON, TIME], dims=["lat", "lon", "time"], crs=CRS_LATLON)
        layer = pogc.Layer(node=MockNode([source1, source2]))

        coordinates = layer.get_coordinates()

        assert coordinates is not None
        assert coordinates["time"].size == len(TIME)

    def test_dims_are_combined(self):
        """Test that dimension values are combined."""
        source1 = pogc.Coordinates([LAT, LON, TIME], dims=["lat", "lon", "time"], crs=CRS_LATLON)
        source2 = pogc.Coordinates([LAT, LON], dims=["lat", "lon"], crs=CRS_LATLON)
        layer = pogc.Layer(node=MockNode([source1, source2]))

        coordinates = layer.get_coordinates()

        assert coordinates is not None
        assert coordinates["time"].size == len(TIME)
