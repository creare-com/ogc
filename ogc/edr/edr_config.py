import os
import json
import logging
import traitlets as tl
from collections import defaultdict
from typing import List, Dict, Tuple, Any
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
        groups = defaultdict(list)

        # Organize the data into groups
        for layer in layers:
            groups[layer.group].append(layer)

        # Generate collection resources based on groups
        for group_name, group_layers in groups.items():
            resource = {
                group_name: {
                    "type": "collection",
                    "visibility": "default",
                    "title": group_name,
                    "description": f"Collection of data related to {group_name}",
                    "keywords": ["podpac"],
                    "extents": EdrConfig._generate_extents(group_layers),
                    "height_units": EdrConfig._vertical_units(group_layers),
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
    def _generate_extents(layers: List[pogc.Layer]) -> Dict[str, Any]:
        """Generate the extents dictionary for provided layers.

        Parameters
        ----------
        layers : List[pogc.Layer]
            The layers to create the temporal and spatial extents for.

        Returns
        -------
        Dict[str, Any]
            The extents dictionary for the layers.
        """
        llc_lon, llc_lat, urc_lon, urc_lat = None, None, None, None
        time_range = set()
        vertical_range = set()
        # Determine bounding box which holds all layers
        for layer in layers:
            llc_lon_tmp, llc_lat_tmp, urc_lon_tmp, urc_lat_tmp = EdrConfig._wgs84_bounding_box(layer)
            if any(coord is None for coord in [llc_lon, llc_lat, urc_lon, urc_lat]):
                llc_lon, llc_lat, urc_lon, urc_lat = llc_lon_tmp, llc_lat_tmp, urc_lon_tmp, urc_lat_tmp
            else:
                llc_lon = min(llc_lon, llc_lon_tmp)
                llc_lat = min(llc_lat, llc_lat_tmp)
                urc_lon = max(urc_lon, urc_lon_tmp)
                urc_lat = max(urc_lat, urc_lat_tmp)

            coordinates_list = layer.get_coordinates_list()
            if len(coordinates_list) > 0 and "alt" in coordinates_list[0].udims:
                vertical_range.update(coordinates_list[0]["alt"].coordinates)

            if hasattr(layer, "valid_times") and layer.valid_times is not tl.Undefined and len(layer.valid_times) > 0:
                time_range.update(layer.valid_times)

        sorted_time_range = sorted(time_range)
        sorted_vertical_range = sorted(vertical_range)

        return {
            "spatial": {
                "bbox": [llc_lon, llc_lat, urc_lon, urc_lat],  # minx, miny, maxx, maxy
                "crs": settings.crs_84_uri_format,
            },
            **(
                {
                    "temporal": {
                        "begin": sorted_time_range[0],  # start datetime in RFC3339
                        "end": sorted_time_range[-1],  # end datetime in RFC3339
                        "values": sorted_time_range,
                        "trs": "http://www.opengis.net/def/uom/ISO-8601/0/Gregorian",
                    }
                }
                if len(sorted_time_range) > 0
                else {}
            ),
            **(
                {
                    "vertical": {
                        "interval": [sorted_vertical_range[0], sorted_vertical_range[-1]],
                        "values": sorted_vertical_range,
                        "vrs": "http://www.opengis.net/def/uom/EPSG/0/9001",
                    }
                }
                if len(sorted_vertical_range) > 0
                else {}
            ),
        }

    @staticmethod
    def _wgs84_bounding_box(layer: pogc.Layer) -> Tuple[float, float, float, float]:
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
    def _vertical_units(layers: List[pogc.Layer]) -> List[str]:
        """Retrieve the vertical units for the layers.

        Parameters
        ----------
        layer : List[pogc.Layer]
            The layers from which to get the vertical units.

        Returns
        -------
        str | None
            The vertical units available for the layers.
        """
        vertical_units = set()
        for layer in layers:
            coordinates_list = layer.get_coordinates_list()
            if len(coordinates_list) > 0 and coordinates_list[0].alt_units:
                vertical_units.add(coordinates_list[0].alt_units)

        return list(vertical_units)

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
