import pytest
import numpy as np
import zipfile
import base64
import io
from shapely import Point, Polygon
from typing import Dict, List, Any
from ogc import podpac as pogc
from ogc.edr.edr_provider import EdrProvider
from pygeoapi.provider.base import ProviderInvalidQueryError


def get_provider_definition(layers: List[pogc.Layer]) -> Dict[str, Any]:
    """Define the provider definition which is typically handled by pygeoapi.

    Parameters
    ----------
    layers : List[pogc.Layer]
        Layers for the provider to use in defining available data sources.

    Returns
    -------
    Dict[str, Any]
        The provider definition which defines data sources.
    """
    return {
        "type": "edr",
        "default": True,
        "name": "ogc.edr.edr_provider.EdrProvider",
        "data": "Layers",
        "layers": layers,
        "crs": ["https://www.opengis.net/def/crs/OGC/1.3/CRS84", "https://www.opengis.net/def/crs/EPSG/0/4326"],
        "format": {"name": "GeoJSON", "mimetype": "application/json"},
    }


def test_edr_provider_resources(layers: List[pogc.Layer]):
    """Test the available resources of the EDR Provider class.

    Parameters
    ----------
    layers : List[pogc.Layer]
        Layers provided by a test fixture.
    """
    identifiers = [layer.identifier for layer in layers]

    provider = EdrProvider(provider_def=get_provider_definition(layers))

    assert len(provider.layers) == len(layers)
    assert all(layer.identifier in identifiers for layer in provider.layers)


def test_edr_provider_get_instance_valid_id(layers: List[pogc.Layer]):
    """Test the get_instance method of the EDR Provider class with a valid id.

    Parameters
    ----------
    layers : List[pogc.Layer]
        Layers provided by a test fixture.
    """
    time_instance = next(iter(layers[0].time_instances()))

    provider = EdrProvider(provider_def=get_provider_definition(layers))

    assert provider.get_instance(time_instance) == time_instance


def test_edr_provider_get_instance_invalid_id(layers: List[pogc.Layer]):
    """Test the get_instance method of the EDR Provider class with an invalid id.

    Parameters
    ----------
    layers : List[pogc.Layer]
        Layers provided by a test fixture.
    """
    provider = EdrProvider(provider_def=get_provider_definition(layers))

    assert provider.get_instance("invalid") is None


def test_edr_provider_parameter_keys(layers: List[pogc.Layer]):
    """Test the parameters property of the EDR Provider class.

    Parameters
    ----------
    layers : List[pogc.Layer]
        Layers provided by a test fixture.
    """
    identifiers = [layer.identifier for layer in layers]

    provider = EdrProvider(provider_def=get_provider_definition(layers))
    parameters = provider.parameters

    assert len(list(parameters.keys())) == len(layers)
    assert all(identifier in identifiers for identifier in parameters.keys())


def test_edr_provider_instances(layers: List[pogc.Layer]):
    """Test the instances method of the EDR Provider class.

    Parameters
    ----------
    layers : List[pogc.Layer]
        Layers provided by a test fixture.
    """
    instance_sets = [layer.time_instances() for layer in layers]
    time_instances = set().union(*instance_sets)

    provider = EdrProvider(provider_def=get_provider_definition(layers))
    instances = provider.instances()

    assert len(instances) == len(time_instances)
    assert instances == [str(t) for t in time_instances]


def test_edr_provider_get_fields(layers: List[pogc.Layer]):
    """Test the get fields method of the EDR Provider class.

    Parameters
    ----------
    layers : List[pogc.Layer]
        Layers provided by a test fixture.
    """
    identifiers = [layer.identifier for layer in layers]

    provider = EdrProvider(provider_def=get_provider_definition(layers))
    fields = provider.get_fields()

    assert len(fields.keys()) == len(layers)
    assert all(identifier in identifiers for identifier in fields.keys())


def test_edr_provider_position_request_valid_wkt(
    layers: List[pogc.Layer], single_layer_cube_args_internal: Dict[str, Any]
):
    """Test the position method of the EDR Provider class with a valid WKT.

    Parameters
    ----------
    layers : List[pogc.Layer]
        Layers provided by a test fixture.

    single_layer_cube_args_internal : Dict[str, Any]
        Single layer arguments with internal pygeoapi keys provided by a test fixture.
    """
    args = single_layer_cube_args_internal
    del args["bbox"]
    args["wkt"] = Point(5.2, 52.1)
    parameter_name = single_layer_cube_args_internal["select_properties"][0]

    provider = EdrProvider(provider_def=get_provider_definition(layers))

    response = provider.position(**args)

    assert set(response["domain"]["ranges"][parameter_name]["axisNames"]) == set(
        layers[0].node.find_coordinates()[0].dims
    )
    assert np.prod(np.array(response["domain"]["ranges"][parameter_name]["shape"])) == len(
        response["domain"]["ranges"][parameter_name]["values"]
    )


def test_edr_provider_position_request_invalid_wkt(
    layers: List[pogc.Layer], single_layer_cube_args_internal: Dict[str, Any]
):
    """Test the position method of the EDR Provider class with an invalid WKT.

    Parameters
    ----------
    layers : List[pogc.Layer]
        Layers provided by a test fixture.

    single_layer_cube_args_internal : Dict[str, Any]
        Single layer arguments with internal pygeoapi keys provided by a test fixture.
    """
    args = single_layer_cube_args_internal
    del args["bbox"]
    args["wkt"] = "invalid"

    provider = EdrProvider(provider_def=get_provider_definition(layers))

    with pytest.raises(ProviderInvalidQueryError):
        provider.position(**args)


def test_edr_provider_position_request_invalid_property(
    layers: List[pogc.Layer], single_layer_cube_args_internal: Dict[str, Any]
):
    """Test the position method of the EDR Provider class with an invalid property.

    Parameters
    ----------
    layers : List[pogc.Layer]
        Layers provided by a test fixture.

    single_layer_cube_args_internal : Dict[str, Any]
        Single layer arguments with internal pygeoapi keys provided by a test fixture.
    """
    args = single_layer_cube_args_internal
    args["select_properties"] = "invalid"

    provider = EdrProvider(provider_def=get_provider_definition(layers))

    with pytest.raises(ProviderInvalidQueryError):
        provider.position(**args)


def test_edr_provider_cube_request_valid_bbox(
    layers: List[pogc.Layer], single_layer_cube_args_internal: Dict[str, Any]
):
    """Test the cube method of the EDR Provider class with a valid bounding box.

    Parameters
    ----------
    layers : List[pogc.Layer]
        Layers provided by a test fixture.

    single_layer_cube_args_internal : Dict[str, Any]
        Single layer arguments with internal pygeoapi keys provided by a test fixture.
    """
    args = single_layer_cube_args_internal
    parameter_name = single_layer_cube_args_internal["select_properties"][0]

    provider = EdrProvider(provider_def=get_provider_definition(layers))

    response = provider.cube(**args)

    assert set(response["domain"]["ranges"][parameter_name]["axisNames"]) == set(
        layers[0].node.find_coordinates()[0].dims
    )
    assert np.prod(np.array(response["domain"]["ranges"][parameter_name]["shape"])) == len(
        response["domain"]["ranges"][parameter_name]["values"]
    )


def test_edr_provider_cube_request_invalid_bbox(
    layers: List[pogc.Layer], single_layer_cube_args_internal: Dict[str, Any]
):
    """Test the cube method of the EDR Provider class with an invalid bounding box.

    Parameters
    ----------
    layers : List[pogc.Layer]
        Layers provided by a test fixture.

    single_layer_cube_args_internal : Dict[str, Any]
        Single layer arguments with internal pygeoapi keys provided by a test fixture.
    """
    args = single_layer_cube_args_internal
    args["bbox"] = "invalid"

    provider = EdrProvider(provider_def=get_provider_definition(layers))

    with pytest.raises(ProviderInvalidQueryError):
        provider.cube(**args)


def test_edr_provider_cube_request_invalid_altitude(
    layers: List[pogc.Layer], single_layer_cube_args_internal: Dict[str, Any]
):
    """Test the cube method of the EDR Provider class with an invalid altitude.

    Parameters
    ----------
    layers : List[pogc.Layer]
        Layers provided by a test fixture.

    single_layer_cube_args_internal : Dict[str, Any]
        Single layer arguments with internal pygeoapi keys provided by a test fixture.
    """
    args = single_layer_cube_args_internal
    args["z"] = "invalid"

    provider = EdrProvider(provider_def=get_provider_definition(layers))

    with pytest.raises(ProviderInvalidQueryError):
        provider.position(**args)


def test_edr_provider_area_request_valid_wkt(layers: List[pogc.Layer], single_layer_cube_args_internal: Dict[str, Any]):
    """Test the area method of the EDR Provider class with a valid wkt.

    Parameters
    ----------
    layers : List[pogc.Layer]
        Layers provided by a test fixture.

    single_layer_cube_args_internal : Dict[str, Any]
        Single layer arguments with internal pygeoapi keys provided by a test fixture.
    """
    args = single_layer_cube_args_internal
    del args["bbox"]
    args["wkt"] = Polygon(((-180.0, -90.0), (-180.0, 90.0), (180.0, -90.0), (180.0, 90.0)))
    parameter_name = single_layer_cube_args_internal["select_properties"][0]

    provider = EdrProvider(provider_def=get_provider_definition(layers))

    response = provider.area(**args)

    assert set(response["domain"]["ranges"][parameter_name]["axisNames"]) == set(
        layers[0].node.find_coordinates()[0].dims
    )
    assert np.prod(np.array(response["domain"]["ranges"][parameter_name]["shape"])) == len(
        response["domain"]["ranges"][parameter_name]["values"]
    )


def test_edr_provider_area_request_invalid_wkt(
    layers: List[pogc.Layer], single_layer_cube_args_internal: Dict[str, Any]
):
    """Test the area method of the EDR Provider class with an invalid wkt.

    Parameters
    ----------
    layers : List[pogc.Layer]
        Layers provided by a test fixture.

    single_layer_cube_args_internal : Dict[str, Any]
        Single layer arguments with internal pygeoapi keys provided by a test fixture.
    """
    args = single_layer_cube_args_internal
    del args["bbox"]
    args["wkt"] = "invalid"

    provider = EdrProvider(provider_def=get_provider_definition(layers))

    with pytest.raises(ProviderInvalidQueryError):
        provider.area(**args)


def test_edr_provider_cube_request_invalid_datetime(
    layers: List[pogc.Layer], single_layer_cube_args_internal: Dict[str, Any]
):
    """Test the area method of the EDR Provider class with an invalid datetime.

    Parameters
    ----------
    layers : List[pogc.Layer]
        Layers provided by a test fixture.

    single_layer_cube_args_internal : Dict[str, Any]
        Single layer arguments with internal pygeoapi keys provided by a test fixture.
    """
    args = single_layer_cube_args_internal
    args["datetime_"] = "10_24/2025"

    provider = EdrProvider(provider_def=get_provider_definition(layers))

    with pytest.raises(ProviderInvalidQueryError):
        provider.cube(**args)


def test_edr_provider_cube_request_valid_geotiff_format(
    layers: List[pogc.Layer], single_layer_cube_args_internal: Dict[str, Any]
):
    """Test the query method of the EDR Provider class with a valid geotiff request.

    Parameters
    ----------
    layers : List[pogc.Layer]
        Layers provided by a test fixture.

    single_layer_cube_args_internal : Dict[str, Any]
        Single layer arguments with internal pygeoapi keys provided by a test fixture.
    """
    args = single_layer_cube_args_internal
    args["format_"] = "geotiff"
    parameter_name = single_layer_cube_args_internal["select_properties"][0]

    provider = EdrProvider(provider_def=get_provider_definition(layers))

    response = provider.cube(**args)

    assert response["fn"] == f"{parameter_name}.tif"
    assert len(base64.b64decode(response["fp"])) > 0


def test_edr_provider_cube_request_valid_geotiff_format_multiple_parameters(
    layers: List[pogc.Layer], single_layer_cube_args_internal: Dict[str, Any]
):
    """Test the query method of the EDR Provider class with a valid geotiff request.

    Parameters
    ----------
    layers : List[pogc.Layer]
        Layers provided by a test fixture.

    single_layer_cube_args_internal : Dict[str, Any]
        Single layer arguments with internal pygeoapi keys provided by a test fixture.
    """
    args = single_layer_cube_args_internal
    args["format_"] = "geotiff"

    # Set the properties argument as multiple layers from the same group/collection
    group = layers[0].group
    selected_layers = [layer.identifier for layer in layers if layer.group == group]
    args["select_properties"] = selected_layers

    provider = EdrProvider(provider_def=get_provider_definition(layers))

    response = provider.cube(**args)
    buffer = io.BytesIO(base64.b64decode(response["fp"]))

    assert response["fn"] == f"{group}.zip"
    assert zipfile.is_zipfile(buffer)
    with zipfile.ZipFile(buffer, "r") as zf:
        namelist = zf.namelist()
        assert len(namelist) > 0
        assert all(f"{layer}.tif" in namelist for layer in selected_layers)


def test_edr_provider_datetime_single_value():
    """Test the datetime interpreter method of the EDR Provider class with a single datetime value."""
    time_string = "2025-10-24"
    available_times = ["2025-10-24", "2025-10-25", "2025-10-26", "2025-10-27", "2025-10-28"]
    expected_times = [np.datetime64(available_times[0])]

    time_coords = EdrProvider.interpret_time_coordinates(available_times, time_string, None)

    assert time_coords is not None
    np.testing.assert_array_equal(time_coords["time"].coordinates, expected_times)


def test_edr_provider_datetime_range_closed():
    """Test the datetime interpreter method of the EDR Provider class with a closed datetime range."""
    time_string = "2025-10-24/2025-10-26"
    available_times = ["2025-10-24", "2025-10-25", "2025-10-26", "2025-10-27", "2025-10-28"]
    expected_times = [np.datetime64(time) for time in available_times[0:3]]

    time_coords = EdrProvider.interpret_time_coordinates(available_times, time_string, None)

    assert time_coords is not None
    np.testing.assert_array_equal(time_coords["time"].coordinates, expected_times)


def test_edr_provider_datetime_open_start():
    """Test the datetime interpreter method of the EDR Provider class with a open datetime start."""
    time_string = "../2025-10-27"
    available_times = ["2025-10-24", "2025-10-25", "2025-10-26", "2025-10-27", "2025-10-28"]
    expected_times = [np.datetime64(time) for time in available_times[0:4]]

    time_coords = EdrProvider.interpret_time_coordinates(available_times, time_string, None)

    assert time_coords is not None
    np.testing.assert_array_equal(time_coords["time"].coordinates, expected_times)


def test_edr_provider_datetime_open_end():
    """Test the datetime interpreter method of the EDR Provider class with a open datetime end."""
    time_string = "2025-10-25/.."
    available_times = ["2025-10-24", "2025-10-25", "2025-10-26", "2025-10-27", "2025-10-28"]
    expected_times = [np.datetime64(time) for time in available_times[1:]]

    time_coords = EdrProvider.interpret_time_coordinates(available_times, time_string, None)

    assert time_coords is not None
    np.testing.assert_array_equal(time_coords["time"].coordinates, expected_times)


def test_edr_provider_datetime_invalid_string():
    """Test the datetime interpreter method of the EDR Provider class with an invalid string."""
    time_string = "2025-10-25/../../.."
    available_times = ["2025-10-24", "2025-10-25", "2025-10-26", "2025-10-27", "2025-10-28"]

    time_coords = EdrProvider.interpret_time_coordinates(available_times, time_string, None)

    assert time_coords is None


def test_edr_provider_altitude_single_value():
    """Test the altitude interpreter method of the EDR Provider class with a single datetime value."""
    altitude_string = "10"
    available_altitudes = [0.0, 5.0, 10.0, 15.0, 20.0]
    expected_altitudes = [10.0]

    altitude_coords = EdrProvider.interpret_altitude_coordinates(available_altitudes, altitude_string, None)

    assert altitude_coords is not None
    np.testing.assert_array_equal(altitude_coords["alt"].coordinates, expected_altitudes)


def test_edr_provider_altitude_range_closed():
    """Test the altitude interpreter method of the EDR Provider class with a closed datetime range."""
    altitude_string = "10/20"
    available_altitudes = [0.0, 5.0, 10.0, 15.0, 20.0]
    expected_altitudes = [10.0, 15.0, 20.0]

    altitude_coords = EdrProvider.interpret_altitude_coordinates(available_altitudes, altitude_string, None)

    assert altitude_coords is not None
    np.testing.assert_array_equal(altitude_coords["alt"].coordinates, expected_altitudes)


def test_edr_provider_altitude_repeating_interval():
    """Test the altitude interpreter method of the EDR Provider class with a repeating interval."""
    altitude_string = "R2/5/5"
    available_altitudes = [0.0, 5.0, 10.0, 15.0, 20.0]
    expected_altitudes = [5.0, 10.0]

    altitude_coords = EdrProvider.interpret_altitude_coordinates(available_altitudes, altitude_string, None)

    assert altitude_coords is not None
    np.testing.assert_array_equal(altitude_coords["alt"].coordinates, expected_altitudes)


def test_edr_provider_altitude_list():
    """Test the altitude interpreter method of the EDR Provider class with a list."""
    altitude_string = "5,10,15"
    available_altitudes = [0.0, 5.0, 10.0, 15.0, 20.0]
    expected_altitudes = [5.0, 10.0, 15.0]

    altitude_coords = EdrProvider.interpret_altitude_coordinates(available_altitudes, altitude_string, None)

    assert altitude_coords is not None
    np.testing.assert_array_equal(altitude_coords["alt"].coordinates, expected_altitudes)


def test_edr_provider_altitude_invalid_string():
    """Test the altitude interpreter method of the EDR Provider class with an invalid string."""
    altitude_string = "../20"
    available_altitudes = [0.0, 5.0, 10.0, 15.0, 20.0]

    altitude_coords = EdrProvider.interpret_altitude_coordinates(available_altitudes, altitude_string, None)

    assert altitude_coords is None


def test_edr_provider_crs_interpreter_default_value():
    """Test the CRS interpretation returns a default value when the argument is None."""
    assert EdrProvider.interpret_crs(None) == "urn:ogc:def:crs:OGC:1.3:CRS84"


def test_edr_provider_crs_interpreter_valid_value():
    """Test the CRS interpretation returns a valid value when the argument is acceptable."""
    assert EdrProvider.interpret_crs("epsg:4326") == "epsg:4326"


def test_edr_provider_crs_interpreter_invalid_value():
    """Test the CRS interpretation raises an exception when an invalid argument is provided."""
    with pytest.raises(ProviderInvalidQueryError):
        EdrProvider.interpret_crs("epsp:4444")


def test_edr_provider_crs_converter():
    """Test the CRS converter returns latitude and longitude data properly."""
    x = [1, 2, 3]
    y = [3, 4, 5]

    # EPSG:4326 specifies x (latitude) and y (longitude)
    lon = y
    lat = x

    assert EdrProvider.crs_converter(x, y, "epsg:4326") == (lon, lat)
