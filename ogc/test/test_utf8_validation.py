import pytest
from unittest.mock import MagicMock

from ogc.servers import FlaskServer


@pytest.fixture
def client():
    mock_ogc = MagicMock()
    mock_ogc.endpoint = "/ogc"
    mock_ogc.handle_wcs_kv.return_value = "<?xml version='1.0'?><root/>"
    app = FlaskServer(__name__, ogcs=[mock_ogc], home_func=lambda endpoint: "home")
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_valid_utf8_passes_through(client):
    """Well-formed UTF-8 query string should not be rejected."""
    response = client.get(
        "/ogc", query_string=b"SERVICE=WCS&REQUEST=GetCapabilities&VERSION=1.0.0"
    )
    assert response.status_code == 200


def test_invalid_utf8_returns_400(client):
    """Query string containing invalid UTF-8 byte sequences should be rejected."""
    response = client.get("/ogc", query_string=b"SERVICE=WCS&COVERAGE=\xff\xfe")
    assert response.status_code == 400
    assert b"invalid UTF-8" in response.data


def test_oversized_query_string_returns_400(client):
    """Query strings exceeding 8192 bytes should be rejected."""
    response = client.get(
        "/ogc", query_string=b"SERVICE=WCS&COVERAGE=" + b"A" * 8200
    )
    assert response.status_code == 400
    assert b"maximum allowed length" in response.data


def test_valid_multibyte_utf8_is_not_rejected(client):
    """Valid multibyte UTF-8 characters pass the encoding check (stripped by allowlist)."""
    response = client.get(
        "/ogc", query_string="SERVICE=WCS&COVERAGE=café".encode("utf-8")
    )
    # UTF-8 check passes; non-ASCII chars are silently stripped by the allowlist
    assert response.status_code == 200
