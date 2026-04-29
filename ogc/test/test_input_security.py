"""
Tests verifying that the server rejects oversized query strings.
"""

import pytest
import numpy as np
import podpac

from ogc import servers, core, settings
from ogc import podpac as pogc
from ogc.ogc_common import WCSException
from ogc.servers import _check_query_string

# ---------------------------------------------------------------------------
# Shared fixture (mirrors test_servers.py)
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
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
    ogc_instance = core.OGC(layers=[layer])
    app = servers.FlaskServer(__name__, ogcs=[ogc_instance])
    app.config["TESTING"] = True
    yield app.test_client()


# ---------------------------------------------------------------------------
# 1. _check_query_string unit tests — exercises the real production function
# ---------------------------------------------------------------------------


def test_check_query_string_overflow():
    """Raises WCSException when byte length exceeds MAX_QUERY_STRING_BYTES."""
    oversized = b"A" * (settings.MAX_QUERY_STRING_BYTES + 1)
    with pytest.raises(WCSException, match="maximum allowed length"):
        _check_query_string(oversized)


def test_check_query_string_valid():
    """Does not raise for a normal ASCII query string."""
    _check_query_string(b"SERVICE=WCS&REQUEST=GetCapabilities&VERSION=1.0.0")


def test_check_query_string_exactly_at_limit():
    """Does not raise when the query string is exactly at the limit."""
    at_limit = b"A" * settings.MAX_QUERY_STRING_BYTES
    _check_query_string(at_limit)


def test_check_query_string_invalid_utf8():
    """Raises WCSException when the query string contains raw non-UTF-8 bytes."""
    with pytest.raises(WCSException, match="invalid UTF-8 encoding"):
        _check_query_string(b"SERVICE=WCS&COVERAGE=\xff\xfe")


def test_check_query_string_valid_percent_encoded():
    """Does not raise for percent-encoded non-ASCII (all bytes are ASCII in the raw QS)."""
    _check_query_string(b"SERVICE=WCS&COVERAGE=%C3%A9")


# ---------------------------------------------------------------------------
# 2. HTTP integration — overflow rejected via test client
# ---------------------------------------------------------------------------


def test_ogc_render_overflow_returns_400(client):
    """A query string over the limit returns a 400 WCSException response."""
    oversized = "A=" + "B" * (settings.MAX_QUERY_STRING_BYTES + 1)
    response = client.get("/ogc", environ_overrides={"QUERY_STRING": oversized})
    assert response.status_code == 400
    assert b"ExceptionReport" in response.data
    assert b"maximum allowed length" in response.data


# ---------------------------------------------------------------------------
# 3. Regression — valid WCS request still works end-to-end
# ---------------------------------------------------------------------------


def test_valid_wcs_get_capabilities_unchanged(client):
    """Normal GetCapabilities request is unaffected by the new guards."""
    response = client.get("/ogc?SERVICE=WCS&REQUEST=GetCapabilities&VERSION=1.0.0")
    assert response.status_code == 200
    assert b"WCS_Capabilities" in response.data
