import pytest
import importlib
import podpac
import datetime
import numpy as np
from flask.testing import FlaskClient
from itertools import chain
from collections.abc import Iterator
from unittest.mock import patch
from ogc import core
from ogc import servers
from ogc import settings
from ogc import podpac as pogc
from ogc.settings import EDR_TIME_INSTANCE_DIMENSION

lat = np.linspace(90, -90, 11)
lon = np.linspace(-180, 180, 21)
time = np.array(["2025-10-24T12:00:00"], dtype="datetime64")
instance = np.array(["2025-10-24T00:00:00"], dtype="datetime64")
data_static = np.random.default_rng(1).random((11, 21))
coords_static = podpac.Coordinates([lat, lon], dims=["lat", "lon"])
data_with_time = np.random.default_rng(1).random((11, 21, 1))
coords_with_time = podpac.Coordinates([lat, lon, time], dims=["lat", "lon", "time"])
data_with_instance = np.random.default_rng(1).random((11, 21, 1, 1))
coords_with_instance = podpac.Coordinates(
    [lat, lon, time, instance], dims=["lat", "lon", "time", EDR_TIME_INSTANCE_DIMENSION]
)

# Define a layer which does not include temporal coordinates
node_static = podpac.data.Array(source=data_static, coordinates=coords_static)
layer_static = pogc.Layer(
    node=node_static,
    identifier="layerStatic",
    title="Layer Static",
    abstract="Layer Static",
    group="Layers",
)

# Define a layer which includes time coordinates
node_time = podpac.data.Array(source=data_with_time, coordinates=coords_with_time)
layer_time = pogc.Layer(
    node=node_time,
    identifier="layerTime",
    title="Layer Time",
    abstract="Layer Time",
    group="Layers",
    valid_times=[dt.astype(datetime.datetime) for dt in time],
)

# Define a layer which includes both time coordinates and instance coordinates
node_instance = podpac.data.Array(source=data_with_instance, coordinates=coords_with_instance)
layer_instance = pogc.Layer(
    node=node_instance,
    identifier="layerInstance",
    title="Layer Instance",
    abstract="Layer Instance",
    group="Layers",
    valid_times=[dt.astype(datetime.datetime) for dt in time],
)


@pytest.fixture
def enable_all_formats_in_env():
    """Test client for FlaskServer with all formats enabled."""
    with patch.dict("os.environ", {"OGC_SUPPORTED_FORMATS": "wms,wcs,wmts,edr"}):
        importlib.reload(settings)
        yield
    importlib.reload(settings)


@pytest.fixture
def client():
    """
    Create a test client for the Flask server.

    Yields
    ------
    client : FlaskClient
        A test client for the Flask server.
    """
    # Create an OGC instance with the test layers
    ogc = core.OGC(layers=[layer_static, layer_time, layer_instance])

    # Create a FlaskServer instance
    app = servers.FlaskServer(__name__, ogcs=[ogc])
    app.config.update({"TESTING": True})
    yield app.test_client()


def make_valid_ogc_wms_get_capabilities_args() -> dict:
    """Valid argument dictionary for WMS get capabilities.

    Returns
    -------
    dict
        The argument dictionary.
    """
    return {
        "SERVICE": "WMS",
        "REQUEST": "GetCapabilities",
    }


def make_valid_ogc_wms_get_feature_info_args() -> dict:
    """Valid argument dictionary for WMS get feature info.

    Returns
    -------
    dict
        The argument dictionary.
    """
    return {
        "SERVICE": "WMS",
        "REQUEST": "GetFeatureInfo",
        "VERSION": "1.3.0",
    }


def make_valid_ogc_wms_get_legend_graphic_args(layer: str) -> dict:
    """Valid argument dictionary for WMS get legend graphic.

    Parameters
    ----------
    layer : str
        Identifier for the layer.

    Returns
    -------
    dict
        The argument dictionary.
    """
    return {
        "SERVICE": "WMS",
        "REQUEST": "GetLegendGraphic",
        "VERSION": "1.3.0",
        "LAYER": layer,
    }


def make_valid_ogc_wms_get_map_args(layer: str, time: str) -> dict:
    """Valid argument dictionary for WMS get map.

    Parameters
    ----------
    layer : str
        Identifier for the layer.
    time : str
        Available time for the layer.

    Returns
    -------
    dict
        The argument dictionary.
    """
    return {
        "SERVICE": "WMS",
        "REQUEST": "GetMap",
        "VERSION": "1.3.0",
        "LAYERS": [layer],
        "CRS": "EPSG:4326",
        "BBOX": "-180,-90,180,90",
        "FORMAT": "image/png",
        "TIME": time,
        "HEIGHT": 512,
        "WIDTH": 512,
    }


def make_valid_ogc_wcs_describe_coverage_args(layer: str) -> dict:
    """Valid argument dictionary for WCS describe coverage.

    Parameters
    ----------
    layer : str
        Identifier for the layer.

    Returns
    -------
    dict
        The argument dictionary.
    """
    return {
        "SERVICE": "WCS",
        "REQUEST": "DescribeCoverage",
        "VERSION": "1.0.0",
        "COVERAGE": layer,
    }


def make_valid_ogc_wcs_get_capabilities_args() -> dict:
    """Valid argument dictionary for WCS get capabilities.

    Returns
    -------
    dict
        The argument dictionary.
    """
    return {
        "SERVICE": "WCS",
        "REQUEST": "GetCapabilities",
    }


def make_valid_ogc_wcs_get_coverage_args(layer: str, time: str) -> dict:
    """Valid argument dictionary for WCS get coverage.

    Parameters
    ----------
    layer : str
        Identifier for the layer.
    time : str
        Available time for the layer.

    Returns
    -------
    dict
        The argument dictionary.
    """
    return {
        "SERVICE": "WCS",
        "REQUEST": "GetCoverage",
        "VERSION": "1.0.0",
        "COVERAGE": layer,
        "REQUEST_CRS": "EPSG:4326",
        "CRS": "EPSG:4326",
        "BBOX": "-180,-90,180,90",
        "FORMAT": "geotiff",
        "TIME": time,
        "HEIGHT": 512,
        "WIDTH": 512,
    }


def make_valid_ogc_wmts_get_capabilities_args() -> dict:
    """Valid argument dictionary for WMTS get capabilities.

    Returns
    -------
    dict
        The argument dictionary.
    """
    return {
        "SERVICE": "WMTS",
        "REQUEST": "GetCapabilities",
    }


def make_valid_ogc_wmts_get_feature_info_args() -> dict:
    """Valid argument dictionary for WMTS get feature info.

    Returns
    -------
    dict
        The argument dictionary.
    """
    return {
        "SERVICE": "WMTS",
        "REQUEST": "GetFeatureInfo",
        "VERSION": "1.0.0",
    }


def make_valid_ogc_wmts_get_tile_args(layer: str, time: str) -> dict:
    """Valid argument dictionary for WMTS get tile.

    Parameters
    ----------
    layer : str
        Identifier for the layer.
    time : str
        Available time for the layer.

    Returns
    -------
    dict
        The argument dictionary.
    """
    return {
        "SERVICE": "WMTS",
        "REQUEST": "GetTile",
        "VERSION": "1.0.0",
        "LAYER": layer,
        "TILEROW": "0",
        "TILECOL": "0",
        "TILEMATRIX": "0",
        "TILEMATRIXSET": "WebMercatorQuad",
        "FORMAT": "image/png",
        "TIME": time,
    }


def make_valid_ogc_edr_format_args() -> dict:
    """Valid argument dictionary for EDR requests using only format.

    Returns
    -------
    dict
        The argument dictionary.
    """
    return {
        "f": "json",
    }


def make_valid_ogc_edr_api_args() -> dict:
    """Valid argument dictionary for EDR api requests.

    Returns
    -------
    dict
        The argument dictionary.
    """
    return {
        "f": "json",
        "ui": "redoc",
    }


def make_valid_ogc_edr_static_cube_args(layer: str) -> dict:
    """Valid argument dictionary for EDR cube query without time or instances.

    Parameters
    ----------
    layer : str
        Identifier for the layer.

    Returns
    -------
    dict
        The argument dictionary.
    """
    return {
        "f": "CoverageJSON",
        "bbox": "-180,-90,180,90",
        "crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84",
        "parameter-name": layer,
        "resolution-x": 512,
        "resolution-y": 512,
    }


def make_valid_ogc_edr_static_area_args(layer: str) -> dict:
    """Valid argument dictionary for EDR area query without time or instances.

    Parameters
    ----------
    layer : str
        Identifier for the layer.

    Returns
    -------
    dict
        The argument dictionary.
    """
    return {
        "f": "CoverageJSON",
        "coords": "POLYGON((-180 90, -180 -90, 180 -90, 180 90, -180 90))",
        "crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84",
        "parameter-name": layer,
        "resolution-x": 512,
        "resolution-y": 512,
    }


def make_valid_ogc_edr_static_position_args(layer: str) -> dict:
    """Valid argument dictionary for EDR position query without time or instances.

    Parameters
    ----------
    layer : str
        Identifier for the layer.

    Returns
    -------
    dict
        The argument dictionary.
    """
    return {
        "f": "CoverageJSON",
        "coords": "POINT(40 50)",
        "crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84",
        "parameter-name": layer,
    }


def make_valid_ogc_edr_instance_cube_args(layer: str, time: str) -> dict:
    """Valid argument dictionary for EDR cube query with time and instances.

    Parameters
    ----------
    layer : str
        Identifier for the layer.
    time : str
        Available time for the layer.

    Returns
    -------
    dict
        The argument dictionary.
    """
    return {
        "f": "CoverageJSON",
        "bbox": "-180,-90,180,90",
        "crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84",
        "datetime": time,
        "parameter-name": layer,
        "resolution-x": 512,
        "resolution-y": 512,
    }


def make_valid_ogc_edr_instance_area_args(layer: str, time: str) -> dict:
    """Valid argument dictionary for EDR area query with time and instances.

    Parameters
    ----------
    layer : str
        Identifier for the layer.
    time : str
        Available time for the layer.

    Returns
    -------
    dict
        The argument dictionary.
    """
    return {
        "f": "CoverageJSON",
        "coords": "POLYGON((-180 90, -180 -90, 180 -90, 180 90, -180 90))",
        "crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84",
        "datetime": time,
        "parameter-name": layer,
        "resolution-x": 512,
        "resolution-y": 512,
    }


def make_valid_ogc_edr_instance_position_args(layer: str, time: str) -> dict:
    """Valid argument dictionary for EDR position query with time and instances.

    Parameters
    ----------
    layer : str
        Identifier for the layer.
    time : str
        Available time for the layer.

    Returns
    -------
    dict
        The argument dictionary.
    """
    return {
        "f": "CoverageJSON",
        "coords": "POINT(40 50)",
        "crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84",
        "datetime": time,
        "parameter-name": layer,
    }


class BaseValidation:
    @staticmethod
    def generate_cases(url: str, params: dict) -> Iterator[tuple[str, dict, bool]]:
        """Generate cases for each argument group.
        The first case uses all valid arguments and returns true.
        The remaining cases change a single argument to "invalid" and return false.

        Parameters
        ----------
        url: str
            The URL to request from.
        params : dict
            The valid argument group.

        Yields
        ------
        Iterator[tuple[dict, bool]]
            An iterator containing the URL, updated arguments, and a boolean whether it is valid or not.
        """
        yield url, params, True

        for key in params:
            invalid = params.copy()
            invalid[key] = "invalid"
            yield url, invalid, False

    @staticmethod
    def input_validation(
        client: FlaskClient,
        url: str,
        params: dict,
        should_pass: bool,
    ):
        """Check that the application validates input properly for the provided query arguments.

        Parameters
        ----------
        client: FlaskClient
            The client used to make requests.
        url : str
            The URL to request from.
        params: dict
            The arguments for the request.
        should_pass: bool
            Whether the test should pass or fail.
        """
        response = client.get(url, query_string=params)

        if should_pass:
            assert response.status_code == 200
        else:
            assert response.status_code == 400


class TestWcsValidation:
    @pytest.mark.parametrize(
        "url, params, should_pass",
        chain(
            BaseValidation.generate_cases("/ogc?", make_valid_ogc_wcs_describe_coverage_args(layer_static.identifier)),
            BaseValidation.generate_cases("/ogc?", make_valid_ogc_wcs_get_capabilities_args()),
            BaseValidation.generate_cases(
                "/ogc?", make_valid_ogc_wcs_get_coverage_args(layer_time.identifier, str(time[0]))
            ),
        ),
    )
    def test_input_validation(
        self, enable_all_formats_in_env, client: FlaskClient, url: str, params: dict, should_pass: bool
    ):
        BaseValidation.input_validation(client, url, params, should_pass)


class TestWmsValidation:
    # Ignore the following until implemented
    # BaseValidation.generate_cases("/ogc?", make_valid_ogc_wms_get_feature_info_args())
    @pytest.mark.parametrize(
        "url, params, should_pass",
        chain(
            BaseValidation.generate_cases("/ogc?", make_valid_ogc_wms_get_capabilities_args()),
            BaseValidation.generate_cases("/ogc?", make_valid_ogc_wms_get_legend_graphic_args(layer_static.identifier)),
            BaseValidation.generate_cases(
                "/ogc?", make_valid_ogc_wms_get_map_args(layer_time.identifier, str(time[0]))
            ),
        ),
    )
    def test_input_validation(
        self, enable_all_formats_in_env, client: FlaskClient, url: str, params: dict, should_pass: bool
    ):
        BaseValidation.input_validation(client, url, params, should_pass)


class TestWmtsValidation:
    # Ignore the following until implemented
    # BaseValidation.generate_cases("/ogc?", make_valid_ogc_wmts_get_feature_info_args())
    @pytest.mark.parametrize(
        "url, params, should_pass",
        chain(
            BaseValidation.generate_cases("/ogc?", make_valid_ogc_wmts_get_capabilities_args()),
            BaseValidation.generate_cases(
                "/ogc?", make_valid_ogc_wmts_get_tile_args(layer_time.identifier, str(time[0]))
            ),
        ),
    )
    def test_input_validation(
        self, enable_all_formats_in_env, client: FlaskClient, url: str, params: dict, should_pass: bool
    ):
        BaseValidation.input_validation(client, url, params, should_pass)


class TestEdrValidation:
    @pytest.mark.parametrize(
        "url, params, should_pass",
        chain(
            BaseValidation.generate_cases("/ogc/edr?", make_valid_ogc_edr_format_args()),
            BaseValidation.generate_cases("/ogc/edr/api?", make_valid_ogc_edr_api_args()),
            BaseValidation.generate_cases("/ogc/edr/openapi?", make_valid_ogc_edr_api_args()),
            BaseValidation.generate_cases("/ogc/edr/conformance?", make_valid_ogc_edr_format_args()),
            BaseValidation.generate_cases("/ogc/edr/collections?", make_valid_ogc_edr_format_args()),
            BaseValidation.generate_cases(
                f"/ogc/edr/collections/{layer_static.group}?", make_valid_ogc_edr_format_args()
            ),
            BaseValidation.generate_cases(
                f"/ogc/edr/collections/{layer_static.group}/instances?", make_valid_ogc_edr_format_args()
            ),
            BaseValidation.generate_cases(
                f"/ogc/edr/collections/{layer_static.group}/cube?",
                make_valid_ogc_edr_static_cube_args(layer_static.identifier),
            ),
            BaseValidation.generate_cases(
                f"/ogc/edr/collections/{layer_static.group}/area?",
                make_valid_ogc_edr_static_area_args(layer_static.identifier),
            ),
            BaseValidation.generate_cases(
                f"/ogc/edr/collections/{layer_static.group}/position?",
                make_valid_ogc_edr_static_position_args(layer_static.identifier),
            ),
            BaseValidation.generate_cases(
                f"/ogc/edr/collections/{layer_instance.group}/instances/{instance[0]}/cube?",
                make_valid_ogc_edr_instance_cube_args(layer_instance.identifier, str(time[0])),
            ),
            BaseValidation.generate_cases(
                f"/ogc/edr/collections/{layer_instance.group}/instances/{instance[0]}/area?",
                make_valid_ogc_edr_instance_area_args(layer_instance.identifier, str(time[0])),
            ),
            BaseValidation.generate_cases(
                f"/ogc/edr/collections/{layer_instance.group}/instances/{instance[0]}/position?",
                make_valid_ogc_edr_instance_position_args(layer_instance.identifier, str(time[0])),
            ),
        ),
    )
    def test_input_validation(
        self, enable_all_formats_in_env, client: FlaskClient, url: str, params: dict, should_pass: bool
    ):
        BaseValidation.input_validation(client, url, params, should_pass)
