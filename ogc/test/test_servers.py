import os
import tempfile
from ogc import servers
from ogc import core
from ogc import podpac as pogc
from ogc import settings
from ogc.ogc_common import EDRException
from pygeoapi.api import APIRequest
from unittest.mock import patch

import importlib
import podpac
import pytest
import numpy as np


@pytest.fixture
def client():
    """
    Create a test client for the Flask server.

    Yields
    ------
    client : FlaskClient
        A test client for the Flask server.
    """
    # Create some test OGC layers
    lat = np.linspace(90, -90, 11)
    lon = np.linspace(-180, 180, 21)
    data = np.random.default_rng(1).random((11, 21))
    coords = podpac.Coordinates([lat, lon], dims=["lat", "lon"])
    node1 = podpac.data.Array(source=data, coordinates=coords)

    layer1 = pogc.Layer(
        node=node1,
        identifier="layer1",
        title="Layer 1",
        abstract="Layer 1 Data",
        group="Layers",
    )
    # Create an OGC instance with the test layers
    ogc = core.OGC(layers=[layer1])

    # Create a FlaskServer instance
    app = servers.FlaskServer(__name__, ogcs=[ogc])
    app.config.update({"TESTING": True})
    yield app.test_client()


@pytest.fixture
def client_with_percent_and_caret_layer():
    """
    Create a test client for the Flask server whose layer identifier
    contains a % and a ^, mirroring real-world layer names such as
    "Relative_humidity_[%]" and "Total_precipitation_[kg/(m^2)]".

    Yields
    ------
    client : FlaskClient
        A test client for the Flask server.
    """
    lat = np.linspace(90, -90, 11)
    lon = np.linspace(-180, 180, 21)
    data = np.random.default_rng(1).random((11, 21))
    coords = podpac.Coordinates([lat, lon], dims=["lat", "lon"])
    node = podpac.data.Array(source=data, coordinates=coords)

    layer = pogc.Layer(
        node=node,
        identifier="Total_precipitation_[kg/(m^2)]_[%]",
        title="Total Precipitation",
        abstract="Total Precipitation Data",
        group="Layers",
    )
    ogc = core.OGC(layers=[layer])
    app = servers.FlaskServer(__name__, ogcs=[ogc])
    app.config.update({"TESTING": True})
    yield app.test_client()


@pytest.fixture
def disable_all_formats_in_env():
    """Setup the environmental variables for no supported formats."""
    with patch.dict("os.environ", {"OGC_SUPPORTED_FORMATS": ""}):
        importlib.reload(settings)
        yield
    importlib.reload(settings)


def test_server_construction(client):
    """
    Test the construction of the server.
    """
    assert isinstance(client.application, servers.FlaskServer)
    assert len(client.application.ogcs) == 1


def test_server_ogc_render_test_invalid_method(client):
    """
    Test the ogc_render method with an invalid method.
    """
    response = client.post("/ogc")
    assert response.status_code == 405


def test_server_ogc_render_base_url(client):
    """
    Test the ogc_render method with a valid base URL.
    """
    response = client.get("/ogc")
    assert response.status_code == 200


def test_server_ogc_render_wcs_service(client):
    """
    Test the ogc_render method with WCS service.
    """
    response = client.get("/ogc?service=WCS&request=GetCapabilities")
    assert response.status_code == 200
    assert "WCS_Capabilities" in response.get_data(as_text=True)


def test_server_ogc_render_wms_service(client):
    """
    Test the ogc_render method with WMS service.
    """
    response = client.get("/ogc?service=WMS&request=GetCapabilities")
    assert response.status_code == 200
    assert "WMS_Capabilities" in response.get_data(as_text=True)


def test_server_ogc_render_invalid_service(client):
    """
    Test the ogc_render method with an invalid service.
    """
    response = client.get("/ogc?service=InvalidService&request=GetCapabilities")
    assert response.status_code == 400


def test_server_ogc_render_invalid_request(client):
    """
    Test the ogc_render method with an invalid request.
    """
    response = client.get("/ogc?service=WCS&request=InvalidRequest")
    assert response.status_code == 400


def test_server_with_default_supported_services(client):
    """
    Test the server with the default supported services.
    """
    response = client.get("/ogc?service=WMS&request=GetCapabilities")
    assert response.status_code == 200

    response = client.get("/ogc?service=WCS&request=GetCapabilities")
    assert response.status_code == 200

    response = client.get("/ogc?service=WMTS&request=GetCapabilities")
    assert response.status_code == 400

    response = client.get("/ogc/edr")
    assert response.status_code == 404


def test_server_without_wcs_supported_service(disable_all_formats_in_env, client):
    """
    Test the WCS service is unavailable when WCS is not a supported format.
    """
    response = client.get("/ogc?service=WCS&request=GetCapabilities")
    assert response.status_code == 400


def test_server_without_wms_supported_service(disable_all_formats_in_env, client):
    """
    Test the WMS service is unavailable when WMS is not a supported format.
    """
    response = client.get("/ogc?service=WMS&request=GetCapabilities")
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# edr_render tests
# ---------------------------------------------------------------------------


@pytest.fixture
def enable_edr_in_env():
    """Test client for FlaskServer with EDR enabled."""
    with patch.dict("os.environ", {"OGC_SUPPORTED_FORMATS": "edr"}):
        importlib.reload(settings)
        yield
    importlib.reload(settings)


def test_edr_render_get_landing_page(enable_edr_in_env, client):
    response = client.get("/ogc/edr?f=json")
    assert response.status_code == 200


def test_edr_render_get_conformance(enable_edr_in_env, client):
    response = client.get("/ogc/edr/conformance?f=json")
    assert response.status_code == 200


def test_edr_render_get_collections(enable_edr_in_env, client):
    response = client.get("/ogc/edr/collections?f=json")
    assert response.status_code == 200


def test_edr_render_post_returns_405(enable_edr_in_env, client):
    response = client.post("/ogc/edr")
    assert response.status_code == 405


def test_edr_render_static_file_returns_200(enable_edr_in_env, client):
    static_path = os.path.join(os.path.dirname(__file__), "..", "edr", "static")
    file_path = static_path
    with tempfile.NamedTemporaryFile(dir=file_path) as temp_file:
        relative_path = os.path.relpath(temp_file.name, static_path)
        response = client.get(f"/ogc/edr/static/{relative_path}")
        assert os.path.exists(temp_file.name)
        assert response.status_code == 200


def test_edr_render_static_file_path_traversal_returns_404(enable_edr_in_env, client):
    static_path = os.path.join(os.path.dirname(__file__), "..", "edr", "static")
    file_path = os.path.join(os.path.dirname(__file__), "..", "edr")
    with tempfile.NamedTemporaryFile(dir=file_path) as temp_file:
        relative_path = os.path.relpath(temp_file.name, static_path)
        response = client.get(f"/ogc/edr/static/{relative_path}")
        assert os.path.exists(temp_file.name)
        assert response.status_code == 404


def test_edr_render_query_string_too_long_returns_400(enable_edr_in_env, client):
    oversized = "f=json&" + "A=" + "B" * settings.MAX_QUERY_STRING_BYTES
    response = client.get("/ogc/edr", environ_overrides={"QUERY_STRING": oversized})
    assert response.status_code == 400


def test_edr_render_query_string_invalid_utf8_returns_400(enable_edr_in_env, client):
    response = client.get("/ogc/edr", environ_overrides={"QUERY_STRING": "f=json&bad=\xff\xfe"})
    assert response.status_code == 400


def test_edr_render_disallowed_chars_are_stripped(enable_edr_in_env, client):
    """Characters outside the allowlist are removed from query values before the handler is called."""
    captured_args = {}
    original_from_flask = APIRequest.from_flask

    def capturing(request, locales):
        captured_args.update(request.args)
        return original_from_flask(request, locales)

    with patch.object(APIRequest, "from_flask", new=capturing):
        response = client.get("/ogc/edr", environ_overrides={"QUERY_STRING": "f=json&foo=bar!@#$"})

    assert response.status_code == 200
    assert all(c not in captured_args.get("foo", "") for c in "!@#$")


def test_edr_render_format_param_is_lowercased(enable_edr_in_env, client):
    """The f= query parameter is normalized to lowercase before the handler receives it."""
    captured_args = {}
    original_from_flask = APIRequest.from_flask

    def capturing(request, locales):
        captured_args.update(request.args)
        return original_from_flask(request, locales)

    with patch.object(APIRequest, "from_flask", new=capturing):
        client.get("/ogc/edr?f=JSON")

    assert captured_args.get("f") == "json"


def test_edr_render_edr_exception_returns_400(enable_edr_in_env, client):
    """WCSException raised by a handler is returned as a 400 XML response."""
    app = client.application

    def raises_edr_exception(api_request, *args, **kwargs):
        raise EDRException(status_code=400, exception_code="InvalidQuery", exception_text="")

    wrapper = app.edr_render(raises_edr_exception)
    app.add_url_rule("/test_edr_wcs", endpoint="test_edr_wcs", view_func=wrapper, methods=["GET"])

    response = client.get("/test_edr_wcs")
    assert response.status_code == 400
    assert "InvalidQuery" in response.get_data(as_text=True)


def test_edr_render_exception_returns_500(enable_edr_in_env, client):
    """Unexpected exceptions in a handler are returned as a 500 XML response."""
    app = client.application

    def raises_runtime_error(api_request, *args, **kwargs):
        raise RuntimeError("unexpected")

    wrapper = app.edr_render(raises_runtime_error)
    app.add_url_rule("/test_edr_exc", endpoint="test_edr_exc", view_func=wrapper, methods=["GET"])

    response = client.get("/test_edr_exc")
    assert response.status_code == 500
    assert "NoApplicableCode" in response.get_data(as_text=True)


def test_ogc_render_percent_and_caret_are_preserved(client):
    """% and ^ are legitimate characters in layer identifiers (e.g. units
    like "[%]" or "[kg/(m^2)]") and must survive the KV allowlist filter
    used by the main WMS/WCS endpoint, while characters that are genuinely
    outside the allowlist are still stripped."""
    captured_args = {}
    original_handle_wms_kv = core.OGC.handle_wms_kv

    def capturing(self, args):
        captured_args.update(args)
        return original_handle_wms_kv(self, args)

    with patch.object(core.OGC, "handle_wms_kv", new=capturing):
        client.get(
            "/ogc",
            query_string={
                "SERVICE": "WMS",
                "REQUEST": "GetLegendGraphic",
                "VERSION": "1.3.0",
                "LAYER": "Relative_humidity_[%]^unsafe!@#$",
            },
        )

    layer_value = captured_args.get("layer", "")
    # % and ^ must survive the filter...
    assert "%" in layer_value
    assert "^" in layer_value
    # ...but characters outside the allowlist must still be stripped.
    assert all(c not in layer_value for c in "!@#$")


def test_get_map_with_percent_and_caret_in_layer_name_returns_200(client_with_percent_and_caret_layer):
    """Regression test: a real GetMap request against a layer whose
    identifier contains % and ^ must succeed end-to-end, rather than
    the identifier being corrupted by the allowlist filter and failing
    the coverage lookup."""
    response = client_with_percent_and_caret_layer.get(
        "/ogc",
        query_string={
            "SERVICE": "WMS",
            "REQUEST": "GetMap",
            "VERSION": "1.3.0",
            "LAYERS": "Total_precipitation_[kg/(m^2)]_[%]",
            "CRS": "EPSG:4326",
            "BBOX": "-180,-90,180,90",
            "FORMAT": "image/png",
            "HEIGHT": 512,
            "WIDTH": 512,
        },
    )
    assert response.status_code == 200
    assert response.content_type == "image/png"


def test_get_legend_graphic_with_percent_and_caret_in_layer_name_returns_200(
    client_with_percent_and_caret_layer,
):
    """Regression test: a real GetLegendGraphic request against a layer
    whose identifier contains % and ^ must succeed end-to-end."""
    response = client_with_percent_and_caret_layer.get(
        "/ogc",
        query_string={
            "SERVICE": "WMS",
            "REQUEST": "GetLegendGraphic",
            "VERSION": "1.3.0",
            "LAYER": "Total_precipitation_[kg/(m^2)]_[%]",
            "FORMAT": "image/png",
        },
    )
    assert response.status_code == 200
    assert response.content_type == "image/png"
