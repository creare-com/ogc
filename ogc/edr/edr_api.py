import json
import pyproj
import numpy as np
import pygeoapi.api
import pygeoapi.api.environmental_data_retrieval as pygeoedr
from http import HTTPStatus
from datetime import datetime, timezone
from typing import Tuple, List, Dict, Any, Union
from ogc import podpac as pogc
from pygeoapi.plugin import load_plugin
from pygeoapi.util import filter_dict_by_key_value, to_json, get_provider_by_type
from pygeoapi.api import API, APIRequest
from pygeoapi.linked_data import jsonldify
from .edr_provider import EdrProvider
from .. import settings


class EdrAPI:
    """Used to modify the default responses before returning data to the user."""

    CONFORMANCE_CLASSES = sorted(
        {
            "https://www.opengis.net/spec/ogcapi-common-1/1.0/conf/core",
            "https://www.opengis.net/spec/ogcapi-common-2/1.0/conf/collections",
            "https://www.opengis.net/spec/ogcapi-edr-1/1.1/conf/core",
        }
    )
    SCHEMA_CLASS = "https://schemas.opengis.net/ogcapi/edr/1.1/openapi"

    @jsonldify
    @staticmethod
    def landing_page(api: API, request: APIRequest) -> Tuple[dict, int, str]:
        """Provide the API landing page.

        Parameters
        ----------
        api : API
            The API which handles the request.
        request : APIRequest
            The request object.

        Returns
        -------
        Tuple[dict, int, str]
            Headers, HTTP Status, and Content returned as a tuple.
        """
        return pygeoapi.api.landing_page(api, request)

    @staticmethod
    def openapi_(api: API, request: APIRequest) -> Tuple[dict, int, str]:
        """Provide the OpenAPI documentation.

        Parameters
        ----------
        api : API
            The API which handles the request.
        request : APIRequest
            The request object.

        Returns
        -------
        Tuple[dict, int, str]
            Headers, HTTP Status, and Content returned as a tuple.
        """
        html_path = "openapi/redoc.html" if request._args.get("ui") == "redoc" else "openapi/swagger.html"
        headers = request.get_response_headers(**api.api_headers)

        if request.format == pygeoapi.api.F_HTML:
            data = {"openapi-document-path": f"{api.base_url}/openapi"}
            content = pygeoapi.api.render_j2_template(
                api.tpl_config, api.config["server"]["templates"], html_path, data, request.locale
            )

            return headers, HTTPStatus.OK, content

        headers["Content-Type"] = "application/vnd.oai.openapi+json;version=3.0"

        if isinstance(api.openapi, dict):
            openapi = EdrAPI._openapi_update(api.openapi)
            return headers, HTTPStatus.OK, to_json(openapi, api.pretty_print)
        else:
            return headers, HTTPStatus.OK, api.openapi

    @staticmethod
    def conformance(api: API, request: APIRequest) -> Tuple[dict, int, str]:
        """Provide the conformance definition.

        Parameters
        ----------
        api : API
            The API which handles the request.
        request : APIRequest
            The request object.

        Returns
        -------
        Tuple[dict, int, str]
            Headers, HTTP Status, and Content returned as a tuple.
        """
        html_path = "conformance.html"
        conformance = {"conformsTo": list(EdrAPI.CONFORMANCE_CLASSES)}

        headers = request.get_response_headers(**api.api_headers)
        if request.format == pygeoapi.api.F_HTML:
            content = pygeoapi.api.render_j2_template(
                api.tpl_config, api.config["server"]["templates"], html_path, conformance, request.locale
            )

            return headers, HTTPStatus.OK, content

        return headers, HTTPStatus.OK, to_json(conformance, api.pretty_print)

    @jsonldify
    @staticmethod
    def describe_collections(api: API, request: APIRequest, dataset: str | None = None) -> Tuple[dict, int, str]:
        """Provide the collection/collections metadata.

        Overrides default functionality to append additional metadata to collections.

        Parameters
        ----------
        api : API
            The API which handles the request.
        request : APIRequest
            The request object.
        dataset : str | None, optional
            The dataset (collection) to be described or None for all collections, by default None.

        Returns
        -------
        Tuple[dict, int, str]
            Headers, HTTP Status, and Content returned as a tuple.
        """
        headers, status, content = pygeoapi.api.describe_collections(api, request, dataset)
        if request.format != pygeoapi.api.F_JSON or status != HTTPStatus.OK:
            return headers, status, content

        collection_description = json.loads(content)
        collection_configuration = filter_dict_by_key_value(api.config["resources"], "type", "collection")
        collections = [collection_description] if dataset is not None else collection_description.get("collections", [])

        for collection in collections:
            collection_id = collection["id"]
            provider = get_provider_by_type(collection_configuration[collection_id]["providers"], "edr")
            provider_plugin = load_plugin("provider", provider)
            provider_parameters = provider_plugin.get_fields()
            collection_layers = EdrProvider.get_layers(provider["base_url"], collection_id)
            collection["extent"] = EdrAPI._generate_extents(collection_layers, None)
            collection["output_formats"] = collection_configuration[collection_id].get("output_formats", [])

            collection_queryable = EdrProvider.is_collection_queryable(provider["base_url"], collection_id)
            collection_without_queryables = EdrAPI._remove_query_metadata(collection)
            collection["links"] = collection_without_queryables["links"]  # Always remove unnecessary query links
            if not collection_queryable:
                collection["data_queries"] = collection_without_queryables["data_queries"]

            height_units = EdrAPI._vertical_units(collection_layers)
            query_formats = collection_configuration[collection_id].get("query_formats", {})
            for query_type in collection["data_queries"]:
                data_query_additions = {
                    "query_type": query_type,
                    **(query_formats.get(query_type) if query_formats.get(query_type) is not None else {}),
                    **({"height_units": height_units} if query_type == "cube" else {}),
                }
                variables = collection["data_queries"][query_type]["link"].get("variables", {})
                collection["data_queries"][query_type]["link"]["variables"] = variables | data_query_additions

            for parameter in collection["parameter_names"]:
                collection["parameter_names"][parameter] = collection["parameter_names"][parameter] | {
                    "description": provider_parameters[parameter].get("description", "")
                }

        return headers, status, to_json(collection_description, api.pretty_print)

    @staticmethod
    def get_collection_edr_instances(
        api: API, request: APIRequest, dataset: str, instance_id: str | None = None
    ) -> Tuple[dict, int, str]:
        """Provide the instance/instances metadata.

        Overrides default functionality to append additional metadata to instances.

        Parameters
        ----------
        api : API
            The API which handles the request.
        request : APIRequest
            The request object.
        dataset : str
            The dataset (collection) to be described.
        instance_id : str | None, optional
            The instance to be described or None for all instances, by default None.

        Returns
        -------
        Tuple[dict, int, str]
            Headers, HTTP Status, and Content returned as a tuple.
        """
        headers, status, content = pygeoedr.get_collection_edr_instances(api, request, dataset, instance_id)
        if request.format != pygeoapi.api.F_JSON or status != HTTPStatus.OK:
            return headers, status, content

        instance_description = json.loads(content)
        collection_configuration = filter_dict_by_key_value(api.config["resources"], "type", "collection")
        provider = get_provider_by_type(collection_configuration[dataset]["providers"], "edr")
        provider_plugin = load_plugin("provider", provider)
        provider_parameters = provider_plugin.get_fields()
        instances = [instance_description] if instance_id is not None else instance_description.get("instances", [])
        collection_layers = EdrProvider.get_layers(provider["base_url"], dataset)

        for instance in instances:
            instance_id = instance["id"]
            instance["extent"] = EdrAPI._generate_extents(collection_layers, instance_id)
            instance["output_formats"] = collection_configuration[dataset].get("output_formats", [])

            height_units = EdrAPI._vertical_units(collection_layers)
            query_formats = collection_configuration[dataset].get("query_formats", {})
            for query_type in instance["data_queries"]:
                data_query_additions = {
                    "query_type": query_type,
                    **(query_formats.get(query_type) if query_formats.get(query_type) is not None else {}),
                    **({"height_units": height_units} if query_type == "cube" else {}),
                }
                variables = instance["data_queries"][query_type]["link"].get("variables", {})
                instance["data_queries"][query_type]["link"]["variables"] = variables | data_query_additions

            instance["parameter_names"] = EdrAPI._instance_parameters(
                collection_layers, provider_parameters, instance["id"]
            )

        return headers, status, to_json(instance_description, api.pretty_print)

    @staticmethod
    def get_collection_edr_query(
        api: API,
        request: APIRequest,
        dataset: str,
        instance: str | None,
        query_type: str,
        location_id: str | None = None,
    ) -> Tuple[dict, int, str]:
        """Query the collection or instance.

        Parameters
        ----------
        api : API
            The API which handles the request.
        request : APIRequest
            The request object.
        dataset : str
            The dataset (collection) to be queried.
        instance_id : str | None
            The instance to be queried or None if querying a collection.
        query_type : str
            The query type.
        location_id : str | None, optional
            Location identifier for location queries or None, by default None.

        Returns
        -------
        Tuple[dict, int, str]
            Headers, HTTP Status, and Content returned as a tuple.
        """
        return pygeoedr.get_collection_edr_query(api, request, dataset, instance, query_type, location_id)

    @staticmethod
    def _temporal_extents(times: List[Union[np.datetime64, datetime]], trs: str | None) -> Dict[str, Any]:
        """Get the temporal extents for the provided times and reference system.

        Parameters
        ----------
        times : List[Union[np.datetime64, datetime]]
            Times used to create the temporal extent.
        trs : str | None
            The reference system for the times.

        Returns
        -------
        Dict[str, Any]
            The temporal extent object or an empty dictionary..
        """
        iso_times = []
        for time in sorted(times):
            dt = time.astype("datetime64[ms]").astype(datetime) if isinstance(time, np.datetime64) else time
            if dt.tzinfo is None:
                time_utc = dt.replace(tzinfo=timezone.utc)
            else:
                time_utc = dt.astimezone(timezone.utc)
            iso_times.append(time_utc.isoformat().replace("+00:00", "Z"))

        return (
            {
                "temporal": {
                    "interval": [iso_times[0], iso_times[-1]],
                    "values": iso_times,
                    "trs": trs,
                }
            }
            if len(iso_times) > 0
            else {}
        )

    @staticmethod
    def _vertical_extents(vertical_levels: List[float], vrs: str | None) -> Dict[str, Any]:
        """Get the vertical extents for the provided levels and reference system.

        Parameters
        ----------
        vertical_levels : List[float]
            Vertical levels used to create the vertical extent.
        vrs : str | None
            The reference system for the vertical levels.

        Returns
        -------
        Dict[str, Any]
            The vertical extent object or an empty dictionary.
        """
        return (
            {
                "vertical": {
                    "interval": [vertical_levels[0], vertical_levels[-1]],
                    "values": vertical_levels,
                    "vrs": vrs,
                }
            }
            if len(vertical_levels) > 0
            else {}
        )

    @staticmethod
    def _spatial_extents(bbox: List[float], crs: str | None) -> Dict[str, Any]:
        """Get the spatial extents for the provided bbox and reference system.

        Parameters
        ----------
        bbox : List[float]
            Bounding box used to create the spatial extent.
        crs : str | None
            The reference system for the bounding box.

        Returns
        -------
        Dict[str, Any]
            The spatial extent object.
        """
        return {
            "spatial": {
                "bbox": bbox,
                **({"crs": crs} if crs is not None else {}),
            }
        }

    @staticmethod
    def _vertical_units(layers: List[pogc.Layer]) -> List[str]:
        """Retrieve the vertical units for the layers.

        Parameters
        ----------
        layer : List[pogc.Layer]
            The layers from which to get the vertical units.

        Returns
        -------
        List[str]
            The vertical units available for the layers.
        """
        vertical_units = set()
        for layer in layers:
            coordinates = layer.get_coordinates()
            if coordinates is not None and coordinates.alt_units:
                vertical_units.add(coordinates.alt_units)

        return list(vertical_units)

    @staticmethod
    def _crs84_bounding_box(layer: pogc.Layer) -> Tuple[float, float, float, float]:
        """Retrieve the bounding box for the layer with a default fallback.

        Parameters
        ----------
        layer : pogc.Layer
            The layer from which to get the bounding box coordinates.

        Returns
        -------
        Tuple[float, float, float, float]
            Lower-left longitude, lower-left latitude, upper-right longitude, upper-right latitude.
        """
        try:
            return (
                layer.grid_coordinates.LLC.lon,
                layer.grid_coordinates.LLC.lat,
                layer.grid_coordinates.URC.lon,
                layer.grid_coordinates.URC.lat,
            )
        except Exception:
            crs_extents = settings.EDR_CRS[settings.crs_84_uri_format]
            return (crs_extents["minx"], crs_extents["miny"], crs_extents["maxx"], crs_extents["maxy"])

    @staticmethod
    def _generate_extents(layers: List[pogc.Layer], instance: str | None) -> Dict[str, Any]:
        """Generate the extents for the provided layers.

        Parameters
        ----------
        layers : List[pogc.Layer]
            The layers for temporal and spatial extent generation.
        instance : str | None
            The instance for extent generation or None for collection extents.

        Returns
        -------
        Dict[str, Any]
            The extents dictionary for the provided layers.
        """
        bbox = []
        crs = pyproj.CRS(settings.crs_84_uri_format).to_wkt()

        time_range = set()
        vertical_range = set()

        for layer in layers:
            coordinates = layer.get_coordinates()
            if coordinates is not None:
                llc_lon_tmp, llc_lat_tmp, urc_lon_tmp, urc_lat_tmp = EdrAPI._crs84_bounding_box(layer)
                if len(bbox) != 4:
                    bbox = [llc_lon_tmp, llc_lat_tmp, urc_lon_tmp, urc_lat_tmp]
                else:
                    llc_lon = min(bbox[0], llc_lon_tmp)
                    llc_lat = min(bbox[1], llc_lat_tmp)
                    urc_lon = max(bbox[2], urc_lon_tmp)
                    urc_lat = max(bbox[3], urc_lat_tmp)
                    bbox = [llc_lon, llc_lat, urc_lon, urc_lat]

                if "alt" in coordinates.udims:
                    vertical_range.update(coordinates["alt"].coordinates)

                if "time" in coordinates.udims:
                    if instance in layer.time_instances() and settings.EDR_TIME_INSTANCE_DIMENSION in coordinates.udims:
                        instance_datetime = np.datetime64(instance)
                        instance_coordinates = coordinates.select(
                            {settings.EDR_TIME_INSTANCE_DIMENSION: [instance_datetime, instance_datetime]}
                        )
                        selected_time_coordinates = instance_coordinates["time"].coordinates
                        time_range.update(selected_time_coordinates)
                    elif not instance and settings.EDR_TIME_INSTANCE_DIMENSION not in coordinates.udims:
                        time_range.update(coordinates["time"].coordinates)

        sorted_time_range = sorted(time_range)
        sorted_vertical_range = sorted(vertical_range)

        return {
            **(EdrAPI._spatial_extents(bbox, crs)),
            **(EdrAPI._temporal_extents(sorted_time_range, "https://www.opengis.net/def/uom/ISO-8601/0/Gregorian")),
            **(EdrAPI._vertical_extents(sorted_vertical_range, "https://www.opengis.net/def/uom/EPSG/0/9001")),
        }

    @staticmethod
    def _instance_parameters(
        collection_layers: List[pogc.Layer], provider_parameters: Dict[str, Any], instance: str
    ) -> Dict[str, Any]:
        """Get the parameter metadata for the specific instance provided.

        Parameters
        ----------
        collection_layers : List[pogc.Layer]
            The layers available in the collection.
        provider_parameters: Dict[str, Any]
            The metadata for all available parameters in the collection from provider fields.
        instance: str
            The instance to determine parameters for.

        Returns
        -------
        Dict[str, Any]
            The metadata for available parameters in the instance.
        """
        instance_parameters = {}
        for key, value in provider_parameters.items():
            layer = next((layer for layer in collection_layers if layer.identifier == key), None)
            if layer is not None and instance in layer.time_instances():
                instance_parameters[key] = {
                    "id": key,
                    "type": "Parameter",
                    "name": value["title"],
                    "observedProperty": {
                        "label": {"id": key, "en": value["title"]},
                    },
                    "description": value["description"],
                    "unit": {
                        "label": {"en": value["title"]},
                        "symbol": {
                            "value": value["x-ogc-unit"],
                            "type": "http://www.opengis.net/def/uom/UCUM/",
                        },
                    },
                }
        return instance_parameters

    @staticmethod
    def _remove_query_metadata(data: Dict[str, Any]) -> Dict[str, Any]:
        """Remove metadata from the dictionary which relates to query types such as position and cube.

        Parameters
        ----------
        data : Dict[str, Any]
            The dictionary to remove query metadata from.

        Returns
        -------
        Dict[str, Any]
            The updated dictionary with metadata removed.
        """
        filtered_data = data.copy()
        data_queries = data.get("data_queries", {})
        filtered_data["data_queries"] = {"instances": data_queries.get("instances")}
        filtered_data["links"] = []
        for link in data["links"]:
            if link.get("rel") != "data" or "/instances" in link.get("href", ""):
                filtered_data["links"].append(link)

        return filtered_data

    @staticmethod
    def _openapi_update(api: Dict[str, Any]) -> Dict[str, Any]:
        """Update the default OpenAPI definition to a custom format.

        Parameters
        ----------
        api : Dict[str, Any]
            The OpenAPI definition to be updated.

        Returns
        -------
        Dict[str, Any]
            The customized OpenAPI definition.
        """
        server_tag = "Server"
        collection_tag = "Collection Information"
        instance_tag = "Instance Information"
        query_tag = "Query"

        resource_not_found_error = {"description": "Resource not found."}
        internal_application_error = {
            "description": "Internal application error",
            "content": {
                "application/xml": {
                    "schema": {
                        "type": "object",
                        "format": "xml",
                        "xml": {"name": "ExceptionReport"},
                    },
                    "example": (
                        '<?xml version="1.0"?>'
                        "<ExceptionReport>"
                        '<Exception exceptionCode="NoApplicableCode">'
                        "<ExceptionText>Internal application error</ExceptionText>"
                        "</Exception>"
                        "</ExceptionReport>"
                    ),
                }
            },
        }

        query_base_parameters = [
            {"$ref": f"{EdrAPI.SCHEMA_CLASS}/parameters/core/crs.yaml"},
            {"$ref": f"{EdrAPI.SCHEMA_CLASS}/parameters/core/datetime.yaml"},
            {"$ref": f"{EdrAPI.SCHEMA_CLASS}/parameters/core/f.yaml"},
            {"$ref": f"{EdrAPI.SCHEMA_CLASS}/parameters/core/parameter-name.yaml"},
            {"$ref": f"{EdrAPI.SCHEMA_CLASS}/parameters/core/z.yaml"},
        ]
        query_responses = {
            "200": {
                "$ref": f"{EdrAPI.SCHEMA_CLASS}/responses/queries/200.yaml",
            },
            "400": {
                "$ref": f"{EdrAPI.SCHEMA_CLASS}/responses/queries/400.yaml",
            },
            "404": resource_not_found_error,
            "default": internal_application_error,
        }

        openapi = {}
        openapi["openapi"] = api.get("openapi")
        openapi["info"] = api.get("info")
        openapi["servers"] = api.get("servers")
        openapi["tags"] = [server_tag, collection_tag, instance_tag, query_tag]
        openapi["paths"] = {
            "/": {
                "get": {
                    "summary": "Landing Page",
                    "description": "Landing page of the API.",
                    "tags": [server_tag],
                    "operationId": "getLandingPage",
                    "parameters": [
                        {"$ref": f"{EdrAPI.SCHEMA_CLASS}/parameters/core/f.yaml"},
                    ],
                    "responses": {
                        "200": {
                            "$ref": f"{EdrAPI.SCHEMA_CLASS}/responses/core/landingPage.yaml",
                        },
                        "default": internal_application_error,
                    },
                },
            },
            "/api": {
                "get": {
                    "summary": "Capabilities of the API.",
                    "description": "API",
                    "tags": [server_tag],
                    "operationId": "getApi",
                    "parameters": [
                        {"$ref": f"{EdrAPI.SCHEMA_CLASS}/parameters/core/f.yaml"},
                    ],
                    "responses": {
                        "200": {
                            "description": "API capabilities",
                        },
                        "default": internal_application_error,
                    },
                },
            },
            "/conformance": {
                "get": {
                    "summary": "Conformance classes defining standard compliance of the API.",
                    "description": "Conformance Classes",
                    "tags": [server_tag],
                    "operationId": "getConformance",
                    "parameters": [
                        {"$ref": f"{EdrAPI.SCHEMA_CLASS}/parameters/core/f.yaml"},
                    ],
                    "responses": {
                        "200": {
                            "$ref": f"{EdrAPI.SCHEMA_CLASS}/responses/core/conformance.yaml",
                        },
                        "default": internal_application_error,
                    },
                },
            },
            "/collections": {
                "get": {
                    "summary": "Collection information for all available collections.",
                    "description": "Collections",
                    "tags": [collection_tag],
                    "operationId": "getCollections",
                    "parameters": [
                        {"$ref": f"{EdrAPI.SCHEMA_CLASS}/parameters/core/f.yaml"},
                    ],
                    "responses": {
                        "200": {
                            "$ref": f"{EdrAPI.SCHEMA_CLASS}/responses/collections/collections.yaml",
                        },
                        "default": internal_application_error,
                    },
                },
            },
            "/collections/{collectionId}": {
                "get": {
                    "summary": "Collection information for a single collection.",
                    "description": "Collection",
                    "tags": [collection_tag],
                    "operationId": "getCollection",
                    "parameters": [
                        {"$ref": f"{EdrAPI.SCHEMA_CLASS}/parameters/collections/collectionId.yaml"},
                        {"$ref": f"{EdrAPI.SCHEMA_CLASS}/parameters/core/f.yaml"},
                    ],
                    "responses": {
                        "200": {
                            "$ref": f"{EdrAPI.SCHEMA_CLASS}/responses/collections/collection.yaml",
                        },
                        "404": resource_not_found_error,
                        "default": internal_application_error,
                    },
                },
            },
            "/collections/{collectionId}/area": {
                "get": {
                    "summary": "Query a collection for an area.",
                    "description": "Collection Area Query",
                    "tags": [query_tag],
                    "operationId": "getCollectionArea",
                    "parameters": [
                        {"$ref": f"{EdrAPI.SCHEMA_CLASS}/parameters/core/areaCoords.yaml"},
                        {"$ref": f"{EdrAPI.SCHEMA_CLASS}/parameters/collections/collectionId.yaml"},
                        {"$ref": f"{EdrAPI.SCHEMA_CLASS}/parameters/core/resolution-x.yaml"},
                        {"$ref": f"{EdrAPI.SCHEMA_CLASS}/parameters/core/resolution-y.yaml"},
                        *query_base_parameters,
                    ],
                    "responses": query_responses,
                },
            },
            "/collections/{collectionId}/cube": {
                "get": {
                    "summary": "Query a collection for a cube.",
                    "description": "Collection Cube Query",
                    "tags": [query_tag],
                    "operationId": "getCollectionCube",
                    "parameters": [
                        {"$ref": f"{EdrAPI.SCHEMA_CLASS}/parameters/core/bbox.yaml"},
                        {"$ref": f"{EdrAPI.SCHEMA_CLASS}/parameters/collections/collectionId.yaml"},
                        {"$ref": f"{EdrAPI.SCHEMA_CLASS}/parameters/core/resolution-x.yaml"},
                        {"$ref": f"{EdrAPI.SCHEMA_CLASS}/parameters/core/resolution-y.yaml"},
                        *query_base_parameters,
                    ],
                    "responses": query_responses,
                },
            },
            "/collections/{collectionId}/position": {
                "get": {
                    "summary": "Query a collection for a position.",
                    "description": "Collection Position Query",
                    "tags": [query_tag],
                    "operationId": "getCollectionPosition",
                    "parameters": [
                        {"$ref": f"{EdrAPI.SCHEMA_CLASS}/parameters/core/positionCoords.yaml"},
                        {"$ref": f"{EdrAPI.SCHEMA_CLASS}/parameters/collections/collectionId.yaml"},
                        *query_base_parameters,
                    ],
                    "responses": query_responses,
                },
            },
            "/collections/{collectionId}/instances/": {
                "get": {
                    "summary": "Instance information for all available instances in a collection.",
                    "description": "Collection Instances",
                    "tags": [instance_tag],
                    "operationId": "getCollectionInstances",
                    "parameters": [
                        {"$ref": f"{EdrAPI.SCHEMA_CLASS}/parameters/core/f.yaml"},
                        {"$ref": f"{EdrAPI.SCHEMA_CLASS}/parameters/collections/collectionId.yaml"},
                    ],
                    "responses": {
                        "200": {
                            "$ref": f"{EdrAPI.SCHEMA_CLASS}/responses/queries/instances.yaml",
                        },
                        "404": resource_not_found_error,
                        "default": internal_application_error,
                    },
                },
            },
            "/collections/{collectionId}/instances/{instanceId}": {
                "get": {
                    "summary": "Instance information for a single instance in a collection.",
                    "description": "Collection Instance",
                    "tags": [instance_tag],
                    "operationId": "getCollectionInstance",
                    "parameters": [
                        {"$ref": f"{EdrAPI.SCHEMA_CLASS}/parameters/core/f.yaml"},
                        {"$ref": f"{EdrAPI.SCHEMA_CLASS}/parameters/collections/collectionId.yaml"},
                        {"$ref": f"{EdrAPI.SCHEMA_CLASS}/parameters/queries/instanceId.yaml"},
                    ],
                    "responses": {
                        "200": {
                            "$ref": f"{EdrAPI.SCHEMA_CLASS}/responses/queries/instances.yaml",
                        },
                        "404": resource_not_found_error,
                        "default": internal_application_error,
                    },
                },
            },
            "/collections/{collectionId}/instances/{instanceId}/area": {
                "get": {
                    "summary": "Query a collection instance for an area.",
                    "description": "Instance Area Query",
                    "tags": [query_tag],
                    "operationId": "getCollectionInstanceArea",
                    "parameters": [
                        {"$ref": f"{EdrAPI.SCHEMA_CLASS}/parameters/core/areaCoords.yaml"},
                        {"$ref": f"{EdrAPI.SCHEMA_CLASS}/parameters/collections/collectionId.yaml"},
                        {"$ref": f"{EdrAPI.SCHEMA_CLASS}/parameters/queries/instanceId.yaml"},
                        {"$ref": f"{EdrAPI.SCHEMA_CLASS}/parameters/core/resolution-x.yaml"},
                        {"$ref": f"{EdrAPI.SCHEMA_CLASS}/parameters/core/resolution-y.yaml"},
                        *query_base_parameters,
                    ],
                    "responses": query_responses,
                },
            },
            "/collections/{collectionId}/instances/{instanceId}/cube": {
                "get": {
                    "summary": "Query a collection instance for a cube.",
                    "description": "Instance Cube Query",
                    "tags": [query_tag],
                    "operationId": "getCollectionInstanceCube",
                    "parameters": [
                        {"$ref": f"{EdrAPI.SCHEMA_CLASS}/parameters/core/bbox.yaml"},
                        {"$ref": f"{EdrAPI.SCHEMA_CLASS}/parameters/collections/collectionId.yaml"},
                        {"$ref": f"{EdrAPI.SCHEMA_CLASS}/parameters/queries/instanceId.yaml"},
                        {"$ref": f"{EdrAPI.SCHEMA_CLASS}/parameters/core/resolution-x.yaml"},
                        {"$ref": f"{EdrAPI.SCHEMA_CLASS}/parameters/core/resolution-y.yaml"},
                        *query_base_parameters,
                    ],
                    "responses": query_responses,
                },
            },
            "/collections/{collectionId}/instances/{instanceId}/position": {
                "get": {
                    "summary": "Query a collection instance for a position.",
                    "description": "Instance Position Query",
                    "tags": [query_tag],
                    "operationId": "getCollectionInstancePosition",
                    "parameters": [
                        {"$ref": f"{EdrAPI.SCHEMA_CLASS}/parameters/core/positionCoords.yaml"},
                        {"$ref": f"{EdrAPI.SCHEMA_CLASS}/parameters/collections/collectionId.yaml"},
                        {"$ref": f"{EdrAPI.SCHEMA_CLASS}/parameters/queries/instanceId.yaml"},
                        *query_base_parameters,
                    ],
                    "responses": query_responses,
                },
            },
        }

        return openapi
