import os
import mimetypes
import json
import base64
import io
import traitlets as tl
import pygeoapi.l10n
import pygeoapi.plugin
import pygeoapi.api
from typing import Tuple, Any, Dict
from http import HTTPStatus
from copy import deepcopy
from pygeoapi.openapi import get_oas
from ogc import podpac as pogc

from .edr_api import EdrAPI
from .edr_config import EdrConfig
from .edr_provider import EdrProvider


class EdrRoutes(tl.HasTraits):
    """Class responsible for routing EDR requests to the appropriate pygeoapi API method."""

    base_url = tl.Unicode(default_value="http://127.0.0.1:5000/edr")
    layers = tl.List(trait=tl.Instance(pogc.Layer))

    def __init__(self, **kwargs):
        """Initialize the API based on the available layers."""
        super().__init__(**kwargs)
        self.api = self.create_api()

    @tl.observe("layers")
    def layers_change(self, change: Dict[str, Any]):
        """Monitor the layers and update the API when a change occurs.

        Parameters
        ----------
        change : Dict[str, Any]
            Dictionary holding type of modification and name of the attribute that triggered it.
        """
        self.api = self.create_api()

    @tl.observe("base_url")
    def base_url_change(self, change: Dict[str, Any]):
        """Monitor the base url and update the API when a change occurs.

        Parameters
        ----------
        change : Dict[str, Any]
            Dictionary holding type of modification and name of the attribute that triggered it.
        """
        self.api = self.create_api()

    def create_api(self) -> pygeoapi.api.API:
        """Create the pygeoapi API using a custom configuration.

        Returns
        -------
        pygeoapi.api.API
            The API which handles all EDR requests.
        """
        # Allow specifying GeoTiff or CoverageJSON in the format argument.
        # This is a bypass which is needed to get by a conditional check in pygeoapi.
        pygeoapi.plugin.PLUGINS["formatter"]["geotiff"] = ""
        pygeoapi.plugin.PLUGINS["formatter"]["coveragejson"] = ""
        EdrProvider.set_layers(self.base_url, self.layers)
        config = EdrConfig.get_configuration(self.base_url, self.layers)
        open_api = get_oas(config, fail_on_invalid_collection=False)
        return pygeoapi.api.API(config=deepcopy(config), openapi=open_api)

    def clean_configuration_cache(self):
        """Clean a pygeoapi internal translation cache so that multiple configurations can be used simultaneously."""
        pygeoapi.l10n._cfg_cache = {}

    def update_configuration_base_url(self, request: pygeoapi.api.APIRequest):
        """Update the EDR configuration base URL based on the provided request.
        The EDR configuration base URL does not necessarily match the full path of the request base URL.

        Parameters
        ----------
        request : pygeoapi.api.APIRequest
            The API request containing a base URL.
            The base URL should include scheme, host, and path for the request.
        """
        request_base_url = request.params.get("base_url", "")
        # Limit the base URL from the request to the EDR subdirectory
        base_url_partitioned = request_base_url.partition("/edr")
        if len(base_url_partitioned[0]) > 0:
            configuration_base_url = base_url_partitioned[0] + base_url_partitioned[1]
            if configuration_base_url != self.base_url:
                self.base_url = configuration_base_url

    def static_files(self, request: pygeoapi.api.APIRequest, file_path: str) -> Tuple[dict, int, str | bytes]:
        """Handle static file requests using the custom static file folder or the pygeoapi default folder.

        Parameters
        ----------
        file_path : str
            The file path of the requested static resource.

        Returns
        -------
        Tuple[dict, int, str | bytes]
            Headers, HTTP Status, and Content returned as a tuple to make the server response.
        """
        self.clean_configuration_cache()
        self.update_configuration_base_url(request)
        static_path = os.path.join(os.path.dirname(pygeoapi.__file__), "static")
        if "templates" in self.api.config["server"]:
            static_path = self.api.config["server"]["templates"].get("static", static_path)
        file_path = os.path.join(static_path, file_path)
        if os.path.isfile(file_path):
            mime_type, _ = mimetypes.guess_type(file_path)
            mime_type = mime_type or "application/octet-stream"
            with open(file_path, "rb") as f:
                content = f.read()
            return {"Content-Type": mime_type}, HTTPStatus.OK, content
        else:
            return {}, HTTPStatus.NOT_FOUND, b"File not found"

    def landing_page(self, request: pygeoapi.api.APIRequest) -> Tuple[dict, int, str | bytes]:
        """Handle landing page requests for the server.

        Parameters
        ----------
        request : pygeoapi.api.APIRequest
            The pygeoapi request for the server.

        Returns
        -------
        Tuple[dict, int, str | bytes]
            Headers, HTTP Status, and Content returned as a tuple to make the server response.
        """
        self.clean_configuration_cache()
        self.update_configuration_base_url(request)
        return EdrAPI.landing_page(self.api, request)

    def openapi(self, request: pygeoapi.api.APIRequest) -> Tuple[dict, int, str | bytes]:
        """Handle API documentation requests for the server.

        Parameters
        ----------
        request : pygeoapi.api.APIRequest
            The pygeoapi request for the server.

        Returns
        -------
        Tuple[dict, int, str | bytes]
            Headers, HTTP Status, and Content returned as a tuple to make the server response.
        """
        self.clean_configuration_cache()
        self.update_configuration_base_url(request)
        return EdrAPI.openapi_(self.api, request)

    def conformance(self, request: pygeoapi.api.APIRequest) -> Tuple[dict, int, str | bytes]:
        """Handle conformance requests for the server.

        Parameters
        ----------
        request : pygeoapi.api.APIRequest
            The pygeoapi request for the server.

        Returns
        -------
        Tuple[dict, int, str | bytes]
            Headers, HTTP Status, and Content returned as a tuple to make the server response.
        """
        self.clean_configuration_cache()
        self.update_configuration_base_url(request)
        return EdrAPI.conformance(self.api, request)

    def describe_collections(
        self,
        request: pygeoapi.api.APIRequest,
        collection_id: str | None,
    ) -> Tuple[dict, int, str | bytes]:
        """Handle describe collection requests for the server.

        Parameters
        ----------
        request : pygeoapi.api.APIRequest
            The pygeoapi request for the server.
        collection_id : str | None
            The collection ID to describe.

        Returns
        -------
        Tuple[dict, int, str | bytes]
            Headers, HTTP Status, and Content returned as a tuple to make the server response.
        """
        self.clean_configuration_cache()
        self.update_configuration_base_url(request)
        return EdrAPI.describe_collections(self.api, request, collection_id)

    def describe_instances(
        self,
        request: pygeoapi.api.APIRequest,
        collection_id: str,
        instance_id: str | None,
    ) -> Tuple[dict, int, str | bytes]:
        """Handle collection instances requests for the server.

        Parameters
        ----------
        request : pygeoapi.api.APIRequest
            The pygeoapi request for the server.
        collection_id : str
            The collection ID for the instances.
        instance_id: str
            The instance ID to describe.

        Returns
        -------
        Tuple[dict, int, str | bytes]
            Headers, HTTP Status, and Content returned as a tuple to make the server response.
        """
        self.clean_configuration_cache()
        self.update_configuration_base_url(request)
        return EdrAPI.get_collection_edr_instances(self.api, request, collection_id, instance_id=instance_id)

    def collection_query(
        self,
        request: pygeoapi.api.APIRequest,
        collection_id: str,
        instance_id: str | None,
        query_type: str,
    ) -> Tuple[dict, int, Any]:
        """Handle collection and instance query requests for the server.

        Parameters
        ----------
        request : pygeoapi.api.APIRequest
            The pygeoapi request for the server.
        query_type: str
            The query type for the request.
        collection_id : str
            The collection ID for the query.
        instance_id: str
            The instance ID for the query.

        Returns
        -------
        Tuple[dict, int, Any]
            Headers, HTTP Status, and Content returned as a tuple to make the server response.
        """
        self.clean_configuration_cache()
        self.update_configuration_base_url(request)
        headers, http_status, content = EdrAPI.get_collection_edr_query(
            self.api, request, collection_id, instance_id, query_type=query_type, location_id=None
        )

        if "text/html" in headers.get("Content-Type", ""):
            return headers, http_status, content

        content = json.loads(content)
        if "fn" in content and "fp" in content:
            # Return the file name in the header and the content as only the binary data
            filename = content["fn"]
            headers["Content-Type"] = "image/tiff"
            headers["Content-Disposition"] = f"attachment; filename={filename}"
            # Decode the content string which is the Base64 representation of the data
            content = io.BytesIO(base64.b64decode(content["fp"]))
        else:
            headers["Content-Type"] = "application/prs.coverage+json"

        return headers, http_status, content
