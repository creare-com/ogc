import pytest
import podpac
import PIL.Image
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
        assert set(coordinates.dims) == {"lat", "lon", "time"}

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
        source2 = pogc.Coordinates([LAT, LON, TIME2], dims=["lat", "lon", "time"], crs=CRS_LATLON)
        source3 = pogc.Coordinates([LAT, LON], dims=["lat", "lon"], crs=CRS_LATLON)
        layer = pogc.Layer(node=MockNode([source1, source2, source3]))

        coordinates = layer.get_coordinates()

        assert coordinates is not None
        assert coordinates["time"].size == 3


@pytest.mark.parametrize("orientation", ["vertical", "horizontal"])
@pytest.mark.parametrize(
    "legend_kwargs",
    [
        {},
        {"units": "m"},
        {"units": "kilograms per square meter per second"},
        {"units": "kilograms_per_square_meter_per_second"},
        {"units": "very long units " * 20},
        {"units": "kg m^-2 s^-1 $"},
        {"clim": [-1234567.5, 9876543.25]},
        {"enumeration_colors": {1: "blue"}, "enumeration_legend": {1: "Water"}},
        {"enumeration_colors": {5: "red", 9: "blue"}},
        {
            "enumeration_colors": {i: "C%d" % (i % 10) for i in range(100)},
            "enumeration_legend": {i: "Category number %d" % i for i in range(100)},
        },
        {
            "enumeration_colors": {1: "red", 2: "blue"},
            "enumeration_legend": {1: "A long category label" * 20, 2: "b"},
        },
    ],
)
def test_legend_graphic_image(orientation, legend_kwargs):
    """
    Test the legend graphic image is drawn for units, colorbars and enumerations of any size, within the max size.
    """
    legend = pogc.LegendGraphic(orientation=orientation, **legend_kwargs)
    width, height = PIL.Image.open(legend.legend_image()).size

    assert width > 0
    assert height > 0
    assert width <= legend.max_width * legend.dpi + 1
    assert height <= legend.max_height * legend.dpi + 1


@pytest.mark.parametrize("orientation", ["vertical", "horizontal"])
@pytest.mark.parametrize("units", ["m", "kilograms per square meter per second"])
def test_legend_graphic_image_enumeration_ignores_units(orientation, units):
    """
    Test the units are ignored for enumerations, which are categories without units, so the legend is not reshaped.
    """
    enumeration = {"enumeration_colors": {1: "red", 2: "blue"}, "enumeration_legend": {1: "Water", 2: "Forest"}}
    without_units = pogc.LegendGraphic(orientation=orientation, **enumeration)
    with_units = pogc.LegendGraphic(orientation=orientation, units=units, **enumeration)

    assert PIL.Image.open(with_units.legend_image()).size == PIL.Image.open(without_units.legend_image()).size


@pytest.mark.parametrize(
    "orientation, sizes",
    [
        (
            "vertical",
            {"width": 0.7, "height": 2.5, "min_width": 0.0, "min_height": 0.0, "max_width": 1.5, "max_height": 5.5},
        ),
        (
            "horizontal",
            {"width": 2.5, "height": 0.7, "min_width": 0.0, "min_height": 0.0, "max_width": 5.5, "max_height": 1.5},
        ),
    ],
)
def test_legend_graphic_sizes_default_to_orientation(orientation, sizes):
    """
    Test the legend graphic sizes default to narrow and tall for vertical and wide and short for horizontal.
    """
    legend = pogc.LegendGraphic(orientation=orientation)

    assert {name: getattr(legend, name) for name in sizes} == sizes


@pytest.mark.parametrize("orientation", ["vertical", "horizontal"])
@pytest.mark.parametrize("legend_kwargs", [{}, {"units": "m"}, {"enumeration_colors": {1: "red", 2: "blue"}}])
def test_legend_graphic_image_min_size(orientation, legend_kwargs):
    """
    Test the min width and height apply to the legend graphic image in either orientation.
    """
    sizes = {"min_width": 3.0, "min_height": 3.0, "max_width": 6.0, "max_height": 6.0}
    legend = pogc.LegendGraphic(orientation=orientation, **sizes, **legend_kwargs)

    assert PIL.Image.open(legend.legend_image()).size == (300, 300)


@pytest.mark.parametrize("orientation, size", [("vertical", "height"), ("horizontal", "width")])
def test_legend_graphic_image_length(orientation, size):
    """
    Test the legend graphic image is the legend height long along a vertical colorbar and width along a horizontal
    colorbar, with or without units.
    """
    for units in [None, "m"]:
        legend = pogc.LegendGraphic(orientation=orientation, units=units, **{size: 3.0})
        width, height = PIL.Image.open(legend.legend_image()).size

        assert (height if orientation == "vertical" else width) == 300


@pytest.mark.parametrize("orientation", ["vertical", "horizontal"])
@pytest.mark.parametrize("request_args", [{}, {"units": "m", "params": '{"colormap": "magma", "vmin": 0, "vmax": 10}'}])
def test_layer_get_legend_graphic(orientation, request_args):
    """
    Test the layer draws its legend graphic from the request when it has no node.
    """
    layer = pogc.Layer(legend_graphic_orientation=orientation)
    width, height = PIL.Image.open(layer.get_legend_graphic({"format": "image/png", **request_args})).size

    assert (height > width) == (orientation == "vertical")
