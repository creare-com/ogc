import json
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


class EdrAPI:
    """Used to modify the default responses before returning data to the user."""

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
        return pygeoapi.api.openapi_(api, request)

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
        return pygeoapi.api.conformance(api, request)

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

        if dataset is not None:
            collections = [collection_description]
        else:
            collections = collection_description.get("collections", [])

        for collection in collections:
            collection_id = collection["id"]
            provider = get_provider_by_type(collection_configuration[collection_id]["providers"], "edr")
            provider_plugin = load_plugin("provider", provider)
            provider_parameters = provider_plugin.get_fields()

            extents = collection.get("extent", {})
            if "vertical" in collection_configuration[collection_id]["extents"]:
                extents = extents | {"vertical": collection_configuration[collection_id]["extents"]["vertical"]}
            if "temporal" in collection_configuration[collection_id]["extents"]:
                times = collection_configuration[collection_id]["extents"]["temporal"].get("values", [])
                trs = collection_configuration[collection_id]["extents"]["temporal"].get("trs")
                temporal_extents = EdrAPI._temporal_extents(times, trs)
                extents = extents | temporal_extents
            collection["extent"] = extents

            collection["output_formats"] = collection_configuration[collection_id].get("output_formats", [])

            height_units = collection_configuration[collection_id].get("height_units", [])
            for query_type in collection["data_queries"]:
                data_query_additions = {
                    "query_type": query_type,
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
        base_url = provider["base_url"]

        if instance_id is not None:
            instances = [instance_description]
        else:
            instances = instance_description.get("instances", [])

        collection_layers = EdrProvider.get_layers(base_url, dataset)

        for instance in instances:
            collection_id = dataset

            extents = instance.get("extent", {})
            if "vertical" in collection_configuration[collection_id]["extents"]:
                extents = extents | {"vertical": collection_configuration[collection_id]["extents"]["vertical"]}

            times = EdrProvider.get_datetimes(collection_layers, instance["id"])
            if len(times) > 0:
                trs = collection_configuration[collection_id]["extents"]["temporal"].get("trs")
                temporal_extents = EdrAPI._temporal_extents(times, trs)
                extents = extents | temporal_extents

            bbox = collection_configuration[dataset]["extents"]["spatial"]["bbox"]
            if not isinstance(bbox[0], list):
                bbox = [bbox]
            crs = collection_configuration[dataset]["extents"]["spatial"].get("crs")
            spatial_extents = EdrAPI._spatial_extents(bbox, crs)
            extents = extents | spatial_extents
            instance["extent"] = extents

            instance["output_formats"] = collection_configuration[collection_id].get("output_formats", [])

            height_units = collection_configuration[collection_id].get("height_units")
            for query_type in instance["data_queries"]:
                data_query_additions = {
                    "query_type": query_type,
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
            The temporal extent object.
        """
        iso_times = []
        for time in sorted(times):
            dt = time.astype("datetime64[ms]").astype(datetime) if isinstance(time, np.datetime64) else time
            if dt.tzinfo is None:
                time_utc = dt.replace(tzinfo=timezone.utc)
            else:
                time_utc = dt.astimezone(timezone.utc)
            iso_times.append(time_utc.isoformat().replace("+00:00", "Z"))

        return {
            "temporal": {
                "interval": [iso_times[0], iso_times[-1]] if len(iso_times) > 0 else [],
                "values": iso_times,
                "trs": trs,
            }
        }

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
        instance_parameters = {"parameter_names": {}}
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
