from ogc import servers
from ogc import core
from ogc import podpac as pogc
from ogc import settings
from ogc.ogc_common import WCSException
from pygeoapi.api import APIRequest
from unittest.mock import patch
from typing import Callable, Generator

import importlib
import podpac
import pytest
import numpy as np


@pytest.fixture
def supported_formats() -> Generator[Callable[[str], None], None, None]:
    """Fixture used to patch OGC supported formats.

    Returns
    -------
    Generator[Callable[[str], None], None, None]
        A generator which yields a function which patches the OGC supported formats based on input string.
    """

    def _supported_formats(formats: str):
        """Patch the supported formats setting.

        Parameters
        ----------
        formats : str
            The formats which should be supported by the server as a string.
        """
        with patch.dict("os.environ", {"OGC_SUPPORTED_FORMATS": formats}):
            importlib.reload(settings)

    yield _supported_formats

    # Fix imports after patching for test
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


def test_server_without_wcs_supported_service(supported_formats, client):
    """
    Test the WCS service is unavailable when WCS is not a supported format.
    """
    supported_formats("wms")

    response = client.get("/ogc?service=WMS&request=GetCapabilities")
    assert response.status_code == 200

    response = client.get("/ogc?service=WCS&request=GetCapabilities")
    assert response.status_code == 400

    response = client.get("/ogc?service=WMTS&request=GetCapabilities")
    assert response.status_code == 400

    response = client.get("/ogc/edr")
    assert response.status_code == 404


def test_server_without_wms_supported_service(supported_formats, client):
    """
    Test the WMS service is unavailable when WMS is not a supported format.
    """
    supported_formats("wcs")

    response = client.get("/ogc?service=WCS&request=GetCapabilities")
    assert response.status_code == 200

    response = client.get("/ogc?service=WMS&request=GetCapabilities")
    assert response.status_code == 400

    response = client.get("/ogc?service=WMTS&request=GetCapabilities")
    assert response.status_code == 400

    response = client.get("/ogc/edr")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# edr_render tests
# ---------------------------------------------------------------------------


@pytest.fixture
def client_edr():
    """Test client for FlaskServer with EDR enabled."""
    with patch.dict("os.environ", {"OGC_SUPPORTED_FORMATS": "edr"}):
        importlib.reload(settings)
        lat = np.linspace(90, -90, 11)
        lon = np.linspace(-180, 180, 21)
        data = np.random.default_rng(1).random((11, 21))
        coords = podpac.Coordinates([lat, lon], dims=["lat", "lon"])
        node = podpac.data.Array(source=data, coordinates=coords)
        layer = pogc.Layer(
            node=node,
            identifier="layer1",
            title="Layer 1",
            abstract="Layer 1 Data",
            group="Layers",
        )
        ogc = core.OGC(layers=[layer])
        app = servers.FlaskServer(__name__, ogcs=[ogc])
        app.config.update({"TESTING": True})
        yield app.test_client()
    importlib.reload(settings)


def test_edr_render_get_landing_page(client_edr):
    response = client_edr.get("/ogc/edr?f=json")
    assert response.status_code == 200


def test_edr_render_get_conformance(client_edr):
    response = client_edr.get("/ogc/edr/conformance?f=json")
    assert response.status_code == 200


def test_edr_render_get_collections(client_edr):
    response = client_edr.get("/ogc/edr/collections?f=json")
    assert response.status_code == 200


def test_edr_render_post_returns_405(client_edr):
    response = client_edr.post("/ogc/edr")
    assert response.status_code == 405


def test_edr_render_query_string_too_long_returns_400(client_edr):
    oversized = "f=json&" + "A=" + "B" * settings.MAX_QUERY_STRING_BYTES
    response = client_edr.get("/ogc/edr", environ_overrides={"QUERY_STRING": oversized})
    assert response.status_code == 400


def test_edr_render_query_string_invalid_utf8_returns_400(client_edr):
    response = client_edr.get("/ogc/edr", environ_overrides={"QUERY_STRING": "f=json&bad=\xff\xfe"})
    assert response.status_code == 400


def test_edr_render_disallowed_chars_are_stripped(client_edr):
    """Characters outside the allowlist are removed from query values before the handler is called."""
    captured_args = {}
    original_from_flask = APIRequest.from_flask

    def capturing(request, locales):
        captured_args.update(request.args)
        return original_from_flask(request, locales)

    with patch.object(APIRequest, "from_flask", new=capturing):
        response = client_edr.get("/ogc/edr", environ_overrides={"QUERY_STRING": "f=json&foo=bar!@#$"})

    assert response.status_code == 200
    assert all(c not in captured_args.get("foo", "") for c in "!@#$")


def test_edr_render_format_param_is_lowercased(client_edr):
    """The f= query parameter is normalized to lowercase before the handler receives it."""
    captured_args = {}
    original_from_flask = APIRequest.from_flask

    def capturing(request, locales):
        captured_args.update(request.args)
        return original_from_flask(request, locales)

    with patch.object(APIRequest, "from_flask", new=capturing):
        client_edr.get("/ogc/edr?f=JSON")

    assert captured_args.get("f") == "json"


def test_edr_render_wcs_exception_returns_400(client_edr):
    """WCSException raised by a handler is returned as a 400 XML response."""
    app = client_edr.application

    def raises_wcs_exception(api_request, *args, **kwargs):
        raise WCSException("test error")

    wrapper = app.edr_render(raises_wcs_exception)
    app.add_url_rule("/test_edr_wcs", endpoint="test_edr_wcs", view_func=wrapper, methods=["GET"])

    response = client_edr.get("/test_edr_wcs")
    assert response.status_code == 400
    assert "ExceptionReport" in response.get_data(as_text=True)


def test_edr_render_exception_returns_500(client_edr):
    """Unexpected exceptions in a handler are returned as a 500 XML response."""
    app = client_edr.application

    def raises_runtime_error(api_request, *args, **kwargs):
        raise RuntimeError("unexpected")

    wrapper = app.edr_render(raises_runtime_error)
    app.add_url_rule("/test_edr_exc", endpoint="test_edr_exc", view_func=wrapper, methods=["GET"])

    response = client_edr.get("/test_edr_exc")
    assert response.status_code == 500
    assert "ExceptionReport" in response.get_data(as_text=True)
