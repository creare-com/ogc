import json
import numpy as np
from pygeoapi.api import APIRequest
from http import HTTPStatus
from typing import Dict, List, Any
from werkzeug.test import create_environ
from werkzeug.wrappers import Request
from werkzeug.datastructures import ImmutableMultiDict
from ogc import podpac as pogc
from ogc.edr.edr_routes import EdrRoutes


def mock_request(request_args: Dict[str, Any] = {}) -> APIRequest:
    """Creates a mock request for EDR routes to use.


    Parameters
    ----------
    request_args: Dict[str, Any], optional
        The dictionary for query string arguments.

    Returns
    -------
    APIRequest
        Mock API request for route testing.
    """
    environ = create_environ(base_url="http://127.0.0.1:5000/ogc/edr")
    request = Request(environ)
    request.args = ImmutableMultiDict(request_args.items())
    return APIRequest(request, ["en"])


def test_edr_routes_static_files_valid_path():
    """Test the EDR static routes with a valid static file path."""
    request = mock_request()
    edr_routes = EdrRoutes(layers=[])

    headers, status, _ = edr_routes.static_files(request, "img/logo.png")

    assert status == HTTPStatus.OK
    assert headers["Content-Type"] == "image/png"


def test_edr_routes_static_files_invalid_path():
    """Test the EDR static routes with an invalid static file path."""
    request = mock_request()
    edr_routes = EdrRoutes(layers=[])

    _, status, _ = edr_routes.static_files(request, "invalid")

    assert status == HTTPStatus.NOT_FOUND


def test_edr_routes_landing_page():
    """Test the EDR landing page for a response."""
    request = mock_request({"f": "json"})
    edr_routes = EdrRoutes(layers=[])

    headers, status, _ = edr_routes.landing_page(request)

    assert status == HTTPStatus.OK
    assert headers["Content-Type"] == "application/json"


def test_edr_routes_landing_page_html():
    """Test the EDR landing page for a response."""
    request = mock_request({"f": "html"})
    edr_routes = EdrRoutes(layers=[])

    headers, status, _ = edr_routes.landing_page(request)

    assert status == HTTPStatus.OK
    assert headers["Content-Type"] == "text/html"


def test_edr_routes_conformance(layers: List[pogc.Layer]):
    """Test the EDR conformance for a response.

    Parameters
    ----------
    layers : List[pogc.Layer]
        Layers provided by a test fixture.
    """
    request = mock_request({"f": "json"})
    edr_routes = EdrRoutes(layers=layers)

    _, status, content = edr_routes.conformance(request)
    response = json.loads(content)

    assert status == HTTPStatus.OK
    assert len(response["conformsTo"]) > 0
    assert "https://www.opengis.net/spec/ogcapi-edr-1/1.1/conf/core" in response["conformsTo"]


def test_edr_routes_api():
    """Test the EDR api documentation for a response."""
    request = mock_request({"f": "json"})
    edr_routes = EdrRoutes(layers=[])

    _, status, content = edr_routes.openapi(request)
    response = json.loads(content)

    assert status == HTTPStatus.OK
    assert response["paths"]["/"]
    assert response["paths"]["/api"]
    assert response["paths"]["/conformance"]
    assert response["paths"]["/collections"]


def test_edr_routes_describe_collections(layers: List[pogc.Layer]):
    """Test the EDR collections description for a response.

    Parameters
    ----------
    layers : List[pogc.Layer]
        Layers provided by a test fixture.
    """
    request = mock_request({"f": "json"})
    edr_routes = EdrRoutes(layers=layers)
    collections = {layer.group for layer in layers}

    _, status, content = edr_routes.describe_collections(request, collection_id=None)
    response = json.loads(content)

    assert status == HTTPStatus.OK
    assert len(response["collections"]) == len(collections)

    response_collection_ids = [collection["id"] for collection in response["collections"]]

    assert response_collection_ids == list(collections)


def test_edr_routes_describe_collection(layers: List[pogc.Layer]):
    """Test the EDR collection description for a response.

    Parameters
    ----------
    layers : List[pogc.Layer]
        Layers provided by a test fixture.
    """
    request = mock_request({"f": "json"})
    edr_routes = EdrRoutes(layers=layers)
    collection_id = layers[0].group
    collection_layers = [layer for layer in layers if layer.group == collection_id]

    _, status, content = edr_routes.describe_collections(request, collection_id=collection_id)
    response = json.loads(content)

    assert status == HTTPStatus.OK
    assert response["id"] == collection_id
    assert list(response["parameter_names"].keys()) == [layer.identifier for layer in collection_layers]
    assert list(response["data_queries"].keys()) == ["position", "cube", "area", "instances"]


def test_edr_routes_describe_instances(layers: List[pogc.Layer]):
    """Test the EDR instances description for a response.

    Parameters
    ----------
    layers : List[pogc.Layer]
        Layers provided by a test fixture.
    """
    request = mock_request({"f": "json"})
    edr_routes = EdrRoutes(layers=layers)
    collection_id = layers[0].group
    time_instances = set()
    for layer in layers:
        if layer.group == collection_id:
            time_instances.update(layer.time_instances())

    _, status, content = edr_routes.describe_instances(request, collection_id=collection_id, instance_id=None)
    response = json.loads(content)

    assert status == HTTPStatus.OK
    assert len(response["instances"]) == len(time_instances)

    response_time_instances_ids = [instance["id"] for instance in response["instances"]]
    assert response_time_instances_ids == list(time_instances)


def test_edr_routes_describe_instance(layers: List[pogc.Layer]):
    """Test the EDR instance description for a response.

    Parameters
    ----------
    layers : List[pogc.Layer]
        Layers provided by a test fixture.
    """
    request = mock_request({"f": "json"})
    edr_routes = EdrRoutes(layers=layers)
    collection_id = layers[0].group
    instance_id = next(iter(layers[0].time_instances()))

    _, status, content = edr_routes.describe_instances(request, collection_id=collection_id, instance_id=instance_id)
    response = json.loads(content)

    assert status == HTTPStatus.OK
    assert response["id"] == instance_id
    assert list(response["data_queries"].keys()) == ["position", "cube", "area"]


def test_edr_routes_collection_query(layers: List[pogc.Layer], single_layer_cube_args: Dict[str, Any]):
    """Test the EDR collection query for a reponse.

    Parameters
    ----------
    layers : List[pogc.Layer]
        Layers provided by a test fixture.

    single_layer_cube_args : Dict[str, Any]
        Single layer arguments provided by a test fixture.
    """
    collection_id = layers[0].group
    instance_id = next(iter(layers[0].time_instances()))
    parameter_name = single_layer_cube_args["parameter-name"][0]
    request = mock_request(single_layer_cube_args)
    edr_routes = EdrRoutes(layers=layers)

    _, status, content = edr_routes.collection_query(
        request,
        collection_id=collection_id,
        instance_id=instance_id,
        query_type="cube",
    )

    assert status == HTTPStatus.OK

    assert set(content["domain"]["ranges"][parameter_name]["axisNames"]) == {"lat", "lon", "time"}
    assert np.prod(np.array(content["domain"]["ranges"][parameter_name]["shape"])) == len(
        content["domain"]["ranges"][parameter_name]["values"]
    )


def test_edr_routes_collection_query_geotiff_format(layers: List[pogc.Layer], single_layer_cube_args: Dict[str, Any]):
    """Test the EDR collection query for a GeoTiff formatted reponse.

    Parameters
    ----------
    layers : List[pogc.Layer]
        Layers provided by a test fixture.

    single_layer_cube_args : Dict[str, Any]
        Single layer arguments provided by a test fixture.
    """
    collection_id = layers[0].group
    instance_id = next(iter(layers[0].time_instances()))
    single_layer_cube_args["f"] = "geotiff"
    request = mock_request(single_layer_cube_args)
    edr_routes = EdrRoutes(layers=layers)

    headers, status, _ = edr_routes.collection_query(
        request,
        collection_id=collection_id,
        instance_id=instance_id,
        query_type="cube",
    )

    assert status == HTTPStatus.OK
    assert headers["Content-Disposition"] == f"attachment; filename={layers[0].identifier}.tif"


def test_edr_routes_collection_query_invalid_type(layers: List[pogc.Layer], single_layer_cube_args: Dict[str, Any]):
    """Test the EDR collection query with an invalid query type.

    Parameters
    ----------
    layers : List[pogc.Layer]
        Layers provided by a test fixture.

    single_layer_cube_args : Dict[str, Any]
        Single layer arguments provided by a test fixture.
    """
    collection_id = layers[0].group
    instance_id = next(iter(layers[0].time_instances()))
    request = mock_request(single_layer_cube_args)
    edr_routes = EdrRoutes(layers=layers)

    _, status, _ = edr_routes.collection_query(
        request,
        collection_id=collection_id,
        instance_id=instance_id,
        query_type="corridor",
    )

    assert status == HTTPStatus.BAD_REQUEST


def test_edr_routes_collection_query_invalid_bbox(layers: List[pogc.Layer], single_layer_cube_args: Dict[str, Any]):
    """Test the EDR collection query with an invalid bounding box.

    Parameters
    ----------
    layers : List[pogc.Layer]
        Layers provided by a test fixture.

    single_layer_cube_args : Dict[str, Any]
        Single layer arguments provided by a test fixture.
    """
    single_layer_cube_args["bbox"] = "invalid"
    request = mock_request(single_layer_cube_args)
    edr_routes = EdrRoutes(layers=layers)

    _, status, _ = edr_routes.collection_query(
        request,
        collection_id=layers[0].group,
        instance_id=next(iter(layers[0].time_instances())),
        query_type="cube",
    )

    assert status == HTTPStatus.BAD_REQUEST


def test_edr_routes_collection_query_missing_parameter(
    layers: List[pogc.Layer], single_layer_cube_args: Dict[str, Any]
):
    """Test the EDR colletion query with a missing parameter. All parameters are expected to be returned.

    Parameters
    ----------
    layers : List[pogc.Layer]
        Layers provided by a test fixture.

    single_layer_cube_args : Dict[str, Any]
        Single layer arguments provided by a test fixture.
    """
    del single_layer_cube_args["parameter-name"]
    request = mock_request(single_layer_cube_args)
    edr_routes = EdrRoutes(layers=layers)

    _, status, content = edr_routes.collection_query(
        request,
        collection_id=layers[0].group,
        instance_id=next(iter(layers[0].time_instances())),
        query_type="cube",
    )

    assert status == HTTPStatus.OK
    assert content["domain"]["ranges"].keys() == {layer.identifier for layer in layers}


def test_edr_routes_request_url_updates_configuration_url():
    """Test the EDR routes request base URL updates the configuration URL."""
    request_url = "http://test:5000/ogc/edr/static/img/logo.png"
    expected_config_url = "http://test:5000/ogc/edr"
    request = mock_request({"base_url": request_url})
    edr_routes = EdrRoutes(layers=[])

    _, status, _ = edr_routes.static_files(request, "img/logo.png")

    assert status == HTTPStatus.OK
    assert edr_routes.api.config["server"]["url"] == expected_config_url
