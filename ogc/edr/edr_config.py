import os
import json
import numpy as np
import traitlets as tl
from datetime import datetime
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
        configuration["resources"] = resources | EdrConfig._resources_definition(layers)

        return configuration

    @staticmethod
    def _resources_definition(layers: List[pogc.Layer]) -> Dict[str, Any]:
        """Define resource related data for the configuration.

        The resources dictionary holds the information needed to generate the collections.
        Each group is mapped to a collection with the layers in the group forming the collection parameters.
        The custom provider is specified with a data value of the group name.
        This allows for the provider to generate the collection data for each group.

        Parameters
        ----------
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
        for group_name, layers in groups.items():
            resource = {
                group_name: {
                    "type": "collection",
                    "visibility": "default",
                    "title": group_name,
                    "description": f"Collection of data related to {group_name}",
                    "keywords": ["podpac"],
                    "extents": EdrConfig._generate_extents(layers),
                    "providers": [
                        {
                            "type": "edr",
                            "default": True,
                            "name": "ogc.edr.edr_provider.EdrProvider",
                            "data": group_name,
                            "crs": [
                                "https://www.opengis.net/def/crs/OGC/1.3/CRS84",
                                "https://www.opengis.net/def/crs/EPSG/0/4326",
                            ],
                            "format": {
                                "name": "geotiff",
                                "mimetype": "image/tiff",
                            },
                        }
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
        min_time, max_time = None, None
        time_range = None
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

            if hasattr(layer, "valid_times") and layer.valid_times is not tl.Undefined and len(layer.valid_times) > 0:
                layer_min_time = np.min(layer.valid_times)
                layer_max_time = np.max(layer.valid_times)
                if any(time is None for time in [min_time, max_time]):
                    min_time = layer_min_time
                    max_time = layer_max_time
                else:
                    min_time = min(min_time, layer_min_time)
                    max_time = max(max_time, layer_max_time)

                time_range = [
                    min_time.isoformat(),
                    max_time.isoformat(),
                ]

        return {
            "spatial": {
                "bbox": [llc_lon, llc_lat, urc_lon, urc_lat],  # minx, miny, maxx, maxy
                "crs": "https://www.opengis.net/def/crs/OGC/1.3/CRS84",
            },
            **(
                {
                    "temporal": {
                        "begin": datetime.fromisoformat(time_range[0]),  # start datetime in RFC3339
                        "end": datetime.fromisoformat(time_range[-1]),  # end datetime in RFC3339
                        "trs": "https://www.opengis.net/def/uom/ISO-8601/0/Gregorian",
                    }
                }
                if time_range is not None
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
            crs_extents = settings.EDR_CRS["crs:84"]
            return (crs_extents["minx"], crs_extents["miny"], crs_extents["maxx"], crs_extents["maxy"])
