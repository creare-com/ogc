import re
import pytest
from ogc.wmts.wmts_response_1_0_0 import Capabilities, SERVICE_VERSION


def contains_text(xml_str: str, expected: str) -> bool:
    """Check if a string is contained in XML data.
    Uses the entire XML string in single search without extra whitespace.

    Parameters
    ----------
    xml_str : str
        The XML data as a string.
    expected : str
        The string to check in the XML data.

    Returns
    -------
    bool
        True if contained, False otherwise.
    """
    return expected in re.sub(r"\s+", " ", xml_str).strip()


def make_capabilities() -> Capabilities:
    """Create a valid Capabilities object.

    Returns
    -------
    Capabilities
        Initialized capabilities instance.
    """
    capabilities = Capabilities(service_title="Test Service", service_abstract="Abstract", service_keywords=["Keyword"])
    capabilities.coverages = []
    return capabilities


def test_to_xml_contains_required_sections():
    """Ensure main XML output contains required top-level sections."""
    capabilities = make_capabilities()
    xml = capabilities.to_xml()
    assert contains_text(xml, "<?xml")
    assert contains_text(xml, "<Capabilities")
    assert contains_text(xml, "<ows:ServiceIdentification")
    assert contains_text(xml, "<ows:ServiceProvider")
    assert contains_text(xml, "<ows:OperationsMetadata")
    assert contains_text(xml, "<Contents")
    assert contains_text(xml, "<ServiceMetadataURL")


def test_service_identification_contains_service_and_version_information():
    """Ensure service type and version are properly defined in service identification."""
    capabilities = make_capabilities()
    xml = capabilities._service_identification()

    assert contains_text(xml, "<ows:ServiceIdentification>")
    assert contains_text(xml, f"<ows:ServiceType>{capabilities.service_type}</ows:ServiceType>")
    assert contains_text(xml, f"<ows:ServiceTypeVersion>{SERVICE_VERSION}</ows:ServiceTypeVersion>")


def test_operations_metadata_contains_supported_requests():
    """Ensure supported requests are properly defined in operations metadata."""
    capabilities = make_capabilities()
    xml = capabilities._operations_metadata()

    assert contains_text(xml, '<ows:Operation name="GetCapabilities">')
    assert contains_text(xml, '<ows:Operation name="GetTile">')
    assert not contains_text(xml, '<ows:Operation name="GetFeatureInfo">')


@pytest.mark.parametrize(
    "input_number,expected",
    [
        (1.234567891234, "1.234567891"),
        (10, "10"),
    ],
)
def test_format_number(input_number: float | int, expected: str):
    """Validate number formatting logic.

    Parameters
    ----------
    input_number : float | int
        Input number to format.
    expected : str
        Expected string output.
    """
    result = Capabilities._format_number(input_number)
    assert result == expected


def test_bounding_box_tile_matrix_set():
    """Validate tile matrix set bounding box generation."""
    capabilities = make_capabilities()
    xml = capabilities._tile_matrix_sets()

    assert contains_text(xml, "<ows:BoundingBox>")
    assert contains_text(xml, "<ows:LowerCorner>")
    assert contains_text(xml, "<ows:UpperCorner>")


@pytest.mark.parametrize(
    "value,expected",
    [
        ("2026-05-01 11:28:45", True),
        ("2026-05-01T11:28:45", True),
        ("2026-05-01", True),
        ("invalid", False),
        ("10", False),
    ],
)
def test_is_iso_datetime(value: str, expected: bool):
    """Validate datetime detection.

    Parameters
    ----------
    value : str
        Input string.
    expected : bool
        Expected result.
    """
    assert Capabilities._is_iso_datetime(value) == expected
