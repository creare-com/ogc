from ogc import servers
from ogc import core
from ogc import podpac as pogc
from ogc import settings
from unittest.mock import patch
from typing import Callable

import importlib
import podpac
import pytest
import numpy as np


@pytest.fixture
def supported_formats() -> Callable[[str], None]:
    """Fixture used to patch OGC supported formats.

    Returns
    -------
    Callable[[str], None]
        A function which patches the OGC supported formats based on input string.
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

    return _supported_formats


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

    response = client.get("/ogc/edr")
    assert response.status_code == 404
