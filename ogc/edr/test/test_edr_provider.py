import pytest
import numpy as np
import zipfile
import io
import json
import os
import podpac
import pyproj
from shapely import Point, Polygon
from typing import Dict, List, Any
from ogc import settings
from ogc import podpac as pogc
from ogc.edr.edr_provider import EdrProvider
from pygeoapi.provider.base import ProviderInvalidQueryError


def get_json_with_cleanup(path: str) -> Dict[str, Any]:
    """Get JSON data from a path and remove the file after retrieval.

    Parameters
    ----------
    path : str
        The JSON file path.

    Returns
    -------
    Dict[str, Any]
        JSON data from the path.
    """
    with open(path, "r") as f:
        response = json.load(f)

    os.remove(path)
    return response


def get_bytes_with_cleanup(path: str) -> bytes:
    """Get byte data from a path and remove the file after retrieval.

    Parameters
    ----------
    path : str
        The file path.

    Returns
    -------
    bytes
        Binary data from the path.
    """
    with open(path, "rb") as f:
        response = f.read()

    os.remove(path)
    return response


def get_provider_definition(base_url: str) -> Dict[str, Any]:
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
        "base_url": base_url,
        "crs": list(settings.EDR_CRS.keys()),
        "format": {"name": "GeoJSON", "mimetype": "application/json"},
    }


def test_edr_provider_resources(layers: List[pogc.Layer]):
    """Test the available resources of the EDR Provider class.

    Parameters
    ----------
    layers : List[pogc.Layer]
        Layers provided by a test fixture.
    """
    base_url = "/"
    identifiers = [layer.identifier for layer in layers]

    provider = EdrProvider(provider_def=get_provider_definition(base_url))
    provider.set_layers(base_url, layers)

    assert len(provider.get_layers(base_url)) == len(layers)
    assert all(layer.identifier in identifiers for layer in provider.get_layers(base_url))


def test_edr_provider_resources_limited_by_url(layers: List[pogc.Layer]):
    """Test the available resources of the EDR Provider class are limited by URL.

    Parameters
    ----------
    layers : List[pogc.Layer]
        Layers provided by a test fixture.
    """
    base_url = "/"
    invalid_url = "/invalid"

    provider = EdrProvider(provider_def=get_provider_definition(invalid_url))
    provider.set_layers(base_url, layers)

    assert len(provider.get_layers(invalid_url)) == 0
    assert len(provider.get_layers(base_url)) == len(layers)


def test_edr_provider_get_instance_valid_id(layers: List[pogc.Layer]):
    """Test the get_instance method of the EDR Provider class with a valid id.

    Parameters
    ----------
    layers : List[pogc.Layer]
        Layers provided by a test fixture.
    """
    base_url = "/"
    time_instance = next(iter(layers[0].time_instances()))

    provider = EdrProvider(provider_def=get_provider_definition(base_url))
    provider.set_layers(base_url, layers)

    assert provider.get_instance(time_instance) == time_instance


def test_edr_provider_get_instance_invalid_id(layers: List[pogc.Layer]):
    """Test the get_instance method of the EDR Provider class with an invalid id.

    Parameters
    ----------
    layers : List[pogc.Layer]
        Layers provided by a test fixture.
    """
    base_url = "/"
    provider = EdrProvider(provider_def=get_provider_definition(base_url))
    provider.set_layers(base_url, layers)

    assert provider.get_instance("invalid") is None


def test_edr_provider_parameter_keys(layers: List[pogc.Layer]):
    """Test the parameters property of the EDR Provider class.

    Parameters
    ----------
    layers : List[pogc.Layer]
        Layers provided by a test fixture.
    """
    base_url = "/"
    identifiers = [layer.identifier for layer in layers]

    provider = EdrProvider(provider_def=get_provider_definition(base_url))
    provider.set_layers(base_url, layers)
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
    base_url = "/"
    instance_sets = [layer.time_instances() for layer in layers]
    time_instances = set().union(*instance_sets)

    provider = EdrProvider(provider_def=get_provider_definition(base_url))
    provider.set_layers(base_url, layers)
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
    base_url = "/"
    identifiers = [layer.identifier for layer in layers]

    provider = EdrProvider(provider_def=get_provider_definition(base_url))
    provider.set_layers(base_url, layers)
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
    base_url = "/"
    args = single_layer_cube_args_internal
    del args["bbox"]
    args["wkt"] = Point(5.2, 52.1)
    parameter_name = single_layer_cube_args_internal["select_properties"][0]

    provider = EdrProvider(provider_def=get_provider_definition(base_url))
    provider.set_layers(base_url, layers)

    response = provider.position(**args)
    response = get_json_with_cleanup(response["fp"])

    assert set(response["domain"]["ranges"][parameter_name]["axisNames"]) == {"lat", "lon", "time"}
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
    base_url = "/"
    args = single_layer_cube_args_internal
    del args["bbox"]
    args["wkt"] = "invalid"

    provider = EdrProvider(provider_def=get_provider_definition(base_url))
    provider.set_layers(base_url, layers)

    with pytest.raises(ProviderInvalidQueryError):
        provider.position(**args)


def test_edr_provider_position_request_invalid_format(
    layers: List[pogc.Layer], single_layer_cube_args_internal: Dict[str, Any]
):
    """Test the position method of the EDR Provider class with an invalid format.

    Parameters
    ----------
    layers : List[pogc.Layer]
        Layers provided by a test fixture.

    single_layer_cube_args_internal : Dict[str, Any]
        Single layer arguments with internal pygeoapi keys provided by a test fixture.
    """
    base_url = "/"
    args = single_layer_cube_args_internal
    del args["bbox"]
    args["wkt"] = Point(5.2, 52.1)
    args["format_"] = settings.GEOTIFF

    provider = EdrProvider(provider_def=get_provider_definition(base_url))
    provider.set_layers(base_url, layers)

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
    base_url = "/"
    args = single_layer_cube_args_internal
    del args["bbox"]
    args["wkt"] = Point(5.2, 52.1)
    args["select_properties"] = "invalid"

    provider = EdrProvider(provider_def=get_provider_definition(base_url))
    provider.set_layers(base_url, layers)

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
    base_url = "/"
    args = single_layer_cube_args_internal
    parameter_name = single_layer_cube_args_internal["select_properties"][0]

    provider = EdrProvider(provider_def=get_provider_definition(base_url))
    provider.set_layers(base_url, layers)

    response = provider.cube(**args)
    response = get_json_with_cleanup(response["fp"])

    assert set(response["domain"]["ranges"][parameter_name]["axisNames"]) == {"lat", "lon", "time"}
    assert np.prod(np.array(response["domain"]["ranges"][parameter_name]["shape"])) == len(
        response["domain"]["ranges"][parameter_name]["values"]
    )


def test_edr_provider_cube_request_valid_bbox_with_resolution(
    layers: List[pogc.Layer], single_layer_cube_args_internal: Dict[str, Any]
):
    """Test the cube method of the EDR Provider class with a valid bounding box and a specific resolution.

    The tested node is adjusted to ensure interpolation is used.

    Parameters
    ----------
    layers : List[pogc.Layer]
        Layers provided by a test fixture.

    single_layer_cube_args_internal : Dict[str, Any]
        Single layer arguments with internal pygeoapi keys provided by a test fixture.
    """
    base_url = "/"
    args = single_layer_cube_args_internal
    parameter_name = single_layer_cube_args_internal["select_properties"][0]
    resolution_x = 15
    resolution_y = 20

    provider = EdrProvider(provider_def=get_provider_definition(base_url))
    layers[0].node = layers[0].node.interpolate()
    provider.set_layers(base_url, layers)
    provider.set_extra_query_args({"resolution-x": resolution_x, "resolution-y": resolution_y})

    response = provider.cube(**args)
    response = get_json_with_cleanup(response["fp"])

    assert set(response["domain"]["ranges"][parameter_name]["axisNames"]) == {"lat", "lon", "time"}
    assert np.prod(np.array(response["domain"]["ranges"][parameter_name]["shape"])) == resolution_x * resolution_y
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
    base_url = "/"
    args = single_layer_cube_args_internal
    args["bbox"] = "invalid"

    provider = EdrProvider(provider_def=get_provider_definition(base_url))
    provider.set_layers(base_url, layers)

    with pytest.raises(ProviderInvalidQueryError):
        provider.cube(**args)


def test_edr_provider_cube_request_invalid_instance(
    layers: List[pogc.Layer], single_layer_cube_args_internal: Dict[str, Any]
):
    """Test the cube method of the EDR Provider class with an invalid instance.

    Parameters
    ----------
    layers : List[pogc.Layer]
        Layers provided by a test fixture.

    single_layer_cube_args_internal : Dict[str, Any]
        Single layer arguments with internal pygeoapi keys provided by a test fixture.
    """
    base_url = "/"
    args = single_layer_cube_args_internal
    args["instance"] = "invalid"

    provider = EdrProvider(provider_def=get_provider_definition(base_url))
    provider.set_layers(base_url, layers)

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
    base_url = "/"
    args = single_layer_cube_args_internal
    args["z"] = "invalid"

    provider = EdrProvider(provider_def=get_provider_definition(base_url))
    provider.set_layers(base_url, layers)

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
    base_url = "/"
    args = single_layer_cube_args_internal
    del args["bbox"]
    args["wkt"] = Polygon(((-180.0, -90.0), (-180.0, 90.0), (180.0, -90.0), (180.0, 90.0)))
    parameter_name = single_layer_cube_args_internal["select_properties"][0]

    provider = EdrProvider(provider_def=get_provider_definition(base_url))
    provider.set_layers(base_url, layers)

    response = provider.area(**args)
    response = get_json_with_cleanup(response["fp"])

    assert set(response["domain"]["ranges"][parameter_name]["axisNames"]) == {"lat", "lon", "time"}
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
    base_url = "/"
    args = single_layer_cube_args_internal
    del args["bbox"]
    args["wkt"] = "invalid"

    provider = EdrProvider(provider_def=get_provider_definition(base_url))
    provider.set_layers(base_url, layers)

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
    base_url = "/"
    args = single_layer_cube_args_internal
    args["datetime_"] = "10_24/2025"

    provider = EdrProvider(provider_def=get_provider_definition(base_url))
    provider.set_layers(base_url, layers)

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
    base_url = "/"
    args = single_layer_cube_args_internal
    args["format_"] = "geotiff"
    parameter_name = single_layer_cube_args_internal["select_properties"][0]

    provider = EdrProvider(provider_def=get_provider_definition(base_url))
    provider.set_layers(base_url, layers)

    response = provider.cube(**args)
    data = get_bytes_with_cleanup(response["fp"])

    assert response["fn"] == f"{parameter_name}.tif"
    assert len(data) > 0


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
    base_url = "/"
    args = single_layer_cube_args_internal
    args["format_"] = "geotiff"

    # Set the properties argument as multiple layers from the same group/collection
    group = layers[0].group
    selected_layers = [layer.identifier for layer in layers if layer.group == group]
    args["select_properties"] = selected_layers

    provider = EdrProvider(provider_def=get_provider_definition(base_url))
    provider.set_layers(base_url, layers)

    response = provider.cube(**args)
    buffer = io.BytesIO(get_bytes_with_cleanup(response["fp"]))
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
    available_times = [np.datetime64(time) for time in available_times]
    expected_times = available_times[0]

    time_coords = EdrProvider.interpret_time_coordinates(available_times, time_string, None, None)

    assert time_coords is not None
    np.testing.assert_array_equal(time_coords["time"].coordinates, expected_times)


def test_edr_provider_datetime_range_closed():
    """Test the datetime interpreter method of the EDR Provider class with a closed datetime range."""
    time_string = "2025-10-24/2025-10-26"
    available_times = ["2025-10-24", "2025-10-25", "2025-10-26", "2025-10-27", "2025-10-28"]
    available_times = [np.datetime64(time) for time in available_times]
    expected_times = available_times[0:3]

    time_coords = EdrProvider.interpret_time_coordinates(available_times, time_string, None, None)

    assert time_coords is not None
    np.testing.assert_array_equal(time_coords["time"].coordinates, expected_times)


def test_edr_provider_datetime_open_start():
    """Test the datetime interpreter method of the EDR Provider class with a open datetime start."""
    time_string = "../2025-10-27"
    available_times = ["2025-10-24", "2025-10-25", "2025-10-26", "2025-10-27", "2025-10-28"]
    available_times = [np.datetime64(time) for time in available_times]
    expected_times = available_times[0:4]

    time_coords = EdrProvider.interpret_time_coordinates(available_times, time_string, None, None)

    assert time_coords is not None
    np.testing.assert_array_equal(time_coords["time"].coordinates, expected_times)


def test_edr_provider_datetime_open_end():
    """Test the datetime interpreter method of the EDR Provider class with a open datetime end."""
    time_string = "2025-10-25/.."
    available_times = ["2025-10-24", "2025-10-25", "2025-10-26", "2025-10-27", "2025-10-28"]
    available_times = [np.datetime64(time) for time in available_times]
    expected_times = available_times[1:]

    time_coords = EdrProvider.interpret_time_coordinates(available_times, time_string, None, None)

    assert time_coords is not None
    np.testing.assert_array_equal(time_coords["time"].coordinates, expected_times)


def test_edr_provider_datetime_invalid_string():
    """Test the datetime interpreter method of the EDR Provider class with an invalid string."""
    time_string = "2025-10-25/../../.."
    available_times = ["2025-10-24", "2025-10-25", "2025-10-26", "2025-10-27", "2025-10-28"]
    available_times = [np.datetime64(time) for time in available_times]

    with pytest.raises(ProviderInvalidQueryError):
        EdrProvider.interpret_time_coordinates(available_times, time_string, None, None)


def test_edr_provider_get_altitudes():
    """Test the get altitudes method of the EDR Provider class with a layer containing altitude data."""
    latitude = np.arange(1, 5)
    longitude = np.arange(1, 5)
    altitude = np.arange(1, 10)
    data = np.random.default_rng(1).random((len(latitude), len(longitude), len(altitude)))
    coords = podpac.Coordinates([latitude, longitude, altitude], dims=["lat", "lon", "alt"])
    node = podpac.data.Array(source=data, coordinates=coords)
    layer = pogc.Layer(node=node, identifier="Test")

    np.testing.assert_array_equal(EdrProvider.get_altitudes([layer]), altitude)


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

    with pytest.raises(ProviderInvalidQueryError):
        EdrProvider.interpret_altitude_coordinates(available_altitudes, altitude_string, None)


def test_edr_provider_crs_interpreter_default_value():
    """Test the CRS interpretation returns a default value when the argument is None."""

    assert EdrProvider.interpret_crs(None) == pyproj.CRS(settings.crs_84_uri_format).to_wkt()


def test_edr_provider_crs_interpreter_valid_value():
    """Test the CRS interpretation returns a valid value when the argument is acceptable."""
    assert (
        EdrProvider.interpret_crs(settings.epsg_4326_uri_format) == pyproj.CRS(settings.epsg_4326_uri_format).to_wkt()
    )


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

    assert EdrProvider.crs_converter(x, y, crs=settings.epsg_4326_uri_format) == (lon, lat)
