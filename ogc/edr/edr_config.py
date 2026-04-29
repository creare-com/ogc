import os
import json
import logging
from typing import List, Dict, Any
from ogc import podpac as pogc
from .. import settings


class EdrConfig:
    """Defines the configuration for the pygeoapi based server.

    This configuration is used to replace the typical YAML based configurations in order to provide dynamic properties.
    """

    @staticmethod
    def get_configuration(base_url: str, layers: List[pogc.Layer]) -> Dict[str, Any]:
        """Generate the configuration for the API.

        Parameters
        ----------
        base_url : str
            The base URL for the EDR endpoints.
        layers : List[pogc.Layer]
            The layers which define the data sources for the EDR server.

        Returns
        -------
        Dict[str, Any]
            The configuration for the API as a dictionary.
        """
        configuration_path = settings.EDR_CONFIGURATION_PATH
        if configuration_path is None:
            configuration_path = os.path.abspath(os.path.join(os.path.dirname(__file__) + "/config/default.json"))

        configuration = {}
        with open(configuration_path) as f:
            configuration = json.load(f)

        # Add default static files with an absolute path
        server = configuration.get("server", {})
        configuration["server"] = server | {
            "templates": {
                "path": os.path.abspath(os.path.join(os.path.dirname(__file__) + "/templates/")),
                "static": os.path.abspath(os.path.join(os.path.dirname(__file__) + "/static/")),
            }
        }
        configuration["server"]["url"] = base_url

        # Add the data resources and provider information
        resources = configuration.get("resources", {})
        configuration["resources"] = resources | EdrConfig._resources_definition(base_url, layers)

        # Force the log level based on the configuration as it is loaded, otherwise it is ignored
        if configuration.get("logging", {}).get("level"):
            api_logger = logging.getLogger("pygeoapi")
            api_logger.setLevel(configuration["logging"]["level"])

        return configuration

    @staticmethod
    def _resources_definition(base_url: str, layers: List[pogc.Layer]) -> Dict[str, Any]:
        """Define resource related data for the configuration.

        The resources dictionary holds the information needed to generate the collections.
        Each group is mapped to a collection with the layers in the group forming the collection parameters.
        The custom provider is specified with a data value of the group name.
        This allows for the provider to generate the collection data for each group.

        Parameters
        ----------
        base_url : str
            The base URL used as an identifier for the given layers.
        layers : List[pogc.Layer]
            The layers which define the data sources for the EDR server.

        Returns
        -------
        Dict[str, Any]
            The resources configuration for the API as a dictionary.
        """

        resources = {}
        groups = {layer.group for layer in layers}

        # Generate collection resources based on groups
        for group_name in groups:
            resource = {
                group_name: {
                    "type": "collection",
                    "visibility": "default",
                    "title": group_name,
                    "description": f"Collection of data related to {group_name}",
                    "keywords": ["podpac"],
                    "extents": {
                        "spatial": {
                            "bbox": [-180, -90, 180, 90],  # Placeholder extents
                            "crs": settings.crs_84_uri_format,
                        }
                    },
                    "output_formats": list({item for values in settings.EDR_QUERY_FORMATS.values() for item in values}),
                    "query_formats": EdrConfig.data_query_formats(),
                    "providers": [
                        {
                            "type": "edr",
                            "default": True,
                            "name": "ogc.edr.edr_provider.EdrProvider",
                            "data": group_name,
                            "base_url": base_url,
                            "crs": list(settings.EDR_CRS.keys()),
                            "format": {
                                "name": settings.GEOTIFF,
                                "mimetype": "image/tiff",
                            },
                        }
                    ],
                    "formatters": [
                        {
                            "name": "ogc.edr.edr_formatter.GeoTiffFormatter",
                            "mimetype": "image/tiff",
                        },
                        {
                            "name": "ogc.edr.edr_formatter.CoverageJsonFormatter",
                            "mimetype": "application/prs.coverage+json",
                        },
                    ],
                }
            }
            resources.update(resource)

        return resources

    @staticmethod
    def data_query_formats() -> Dict[str, Any]:
        """Get data related to the available query output formats and the default format.

        Returns
        -------
        Dict[str, Any]
            Query format data for each query type.
        """
        query_formats = {}
        for query_type, formats in settings.EDR_QUERY_FORMATS.items():
            query_formats[query_type] = {
                "output_formats": formats,
                "default_output_format": settings.EDR_QUERY_DEFAULTS.get(query_type),
            }
        return query_formats
