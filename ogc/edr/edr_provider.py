import base64
import io
import numpy as np
import zipfile
from datetime import datetime
from collections import defaultdict
from typing import List, Dict, Tuple, Any
from shapely.geometry.base import BaseGeometry
from pygeoapi.provider.base import ProviderConnectionError, ProviderInvalidQueryError
from pygeoapi.provider.base_edr import BaseEDRProvider
from ogc import podpac as pogc
import podpac

from .. import settings


class EdrProvider(BaseEDRProvider):
    """Custom provider to be used with layer data sources."""

    _layers_dict = defaultdict(list)

    @classmethod
    def set_layers(cls, base_url: str, layers: List[pogc.Layer]):
        """Set the layer resources which will be available to the provider.

        Parameters
        ----------
        base_url : str
            The base URL that the layers are available on.
        layers : List[pogc.Layer]
            The layers which the provider will have access to.
        """
        cls._layers_dict[base_url] = layers

    @classmethod
    def get_layers(cls, base_url: str, group: str | None = None) -> List[pogc.Layer]:
        """Get the layer resources for a specific base URL and group.

        Parameters
        ----------
        base_url : str
            The base URL for the layers.
        group : str | None, optional
            Optional group to filter layers, by default None.


        Returns
        -------
        List[pogc.Layer]
            The layers associated with the base URL.
        """
        layers = cls._layers_dict.get(base_url, [])
        if group is not None:
            return [layer for layer in layers if layer.group.lower() == group.lower()]
        else:
            return layers

    def __init__(self, provider_def: Dict[str, Any]):
        """Construct the provider using the provider definition.

        Parameters
        ----------
        provider_def : Dict[str, Any]
            The provider configuration definition.

        Raises
        ------
        ProviderConnectionError
            Raised if the specified collection is not found within any layers.
        ProviderConnectionError
            Raised if the provider does not specify any base URL.
        """
        super().__init__(provider_def)
        collection_id = provider_def.get("data")
        if collection_id is None:
            raise ProviderConnectionError("Data not found.")

        self.collection_id = str(collection_id)
        self.native_format = provider_def["format"]["name"]

        self.base_url = provider_def.get("base_url", "")
        if not self.base_url:
            raise ProviderConnectionError("Valid URL identifier not found for the data.")

    @property
    def parameters(self) -> Dict[str, pogc.Layer]:
        """The parameters which are defined in a given collection.

        The parameters map to the layers which are a part of the group, with keys of the layer identifiers.

        Returns
        -------
        Dict[str, pogc.Layer]
            The parameters as a dictionary of layer identifiers and layer objects.
        """
        return {layer.identifier: layer for layer in self.get_layers(self.base_url, self.collection_id)}

    def handle_query(self, requested_coordinates: podpac.Coordinates, **kwargs):
        """Handle the requests to the EDR server at the specified requested coordinates.
        The coordinates are expected to be latitude and longitude values determined by the specific query function.

        Parameters
        ----------
        requested_coordinates : podpac.Coordinates
            The coordinates for evaluation, it is expected that the coordinates passed in only hold lat and lon.
        instance : str
            The time instance for the request.
        select_properties : List[str]
            The selected properties (parameters) for the request.
        format_ : str
            The requested output format of the data.
        datetime_ : str
            The requested datetime/datetimes for data retrieval.
        z : str
            The requested vertical level/levels for data retrieval.

        Returns
        -------
        Any
            Coverage data as a dictionary of CoverageJSON or native format.

        Raises
        ------
        ProviderInvalidQueryError
            Raised if a datetime string is provided but cannot be interpreted.
        ProviderInvalidQueryError
            Raised if an altitude string is provided but cannot be interpreted.
        ProviderInvalidQueryError
            Raised if the parameters are invalid.
        ProviderInvalidQueryError
            Raised if an instance is provided and it is invalid.
        ProviderInvalidQueryError
            Raised if native coordinates could not be found.
        ProviderInvalidQueryError
            Raised if the request queries for native coordinates exceeding the max allowable size.
        """
        instance = kwargs.get("instance")
        requested_parameters = kwargs.get("select_properties")
        output_format = kwargs.get("format_")
        datetime_arg = kwargs.get("datetime_")
        z_arg = kwargs.get("z")

        output_format = str(output_format).lower()
        self.check_query_condition(
            not any(output_format == query_format.lower() for query_format in settings.EDR_QUERY_FORMATS),
            "Invalid output format provided.",
        )

        available_times = self.get_datetimes(list(self.parameters.values()), instance)
        available_altitudes = self.get_altitudes(list(self.parameters.values()))
        time_coords = self.interpret_time_coordinates(
            available_times, datetime_arg, instance, requested_coordinates.crs
        )
        altitude_coords = self.interpret_altitude_coordinates(available_altitudes, z_arg, requested_coordinates.crs)
        # Allow parameters without case-sensitivity, default to using all parameters
        parameters_filtered = self.parameters
        if requested_parameters is not None and len(requested_parameters) > 0:
            parameters_lower = [param.lower() for param in requested_parameters or []]
            parameters_filtered = {
                key: value
                for key, value in self.parameters.items()
                if key.lower() in parameters_lower and value is not None
            }
        self.check_query_condition(len(parameters_filtered) == 0, "Invalid parameters provided.")
        self.check_query_condition(
            instance is not None and instance not in self.instances(), "Invalid instance provided."
        )

        if time_coords is not None:
            self.check_query_condition(
                len(time_coords["time"].coordinates) > 1 and output_format == settings.GEOTIFF.lower(),
                "GeoTIFF output currently only supports single time requests.",
            )
            requested_coordinates = podpac.coordinates.merge_dims([time_coords, requested_coordinates])
        if altitude_coords is not None:
            self.check_query_condition(
                len(altitude_coords["alt"].coordinates) > 1 and output_format == settings.GEOTIFF.lower(),
                "GeoTIFF output currently only supports single altitude requests.",
            )
            self.check_query_condition(len(parameters_filtered) == 0, "Invalid parameters provided.")
            requested_coordinates = podpac.coordinates.merge_dims([altitude_coords, requested_coordinates])

        # Handle defining native coordinates for the query, these should match between each layer
        coordinates_list = next(iter(parameters_filtered.values())).get_coordinates_list()

        self.check_query_condition(len(coordinates_list) == 0, "Native coordinates not found.")

        requested_native_coordinates = self.get_native_coordinates(requested_coordinates, coordinates_list[0])

        self.check_query_condition(
            bool(requested_native_coordinates.size > settings.MAX_GRID_COORDS_REQUEST_SIZE),
            "Grid coordinates x_size * y_size must be less than %d" % settings.MAX_GRID_COORDS_REQUEST_SIZE,
        )

        dataset = {}
        for requested_parameter, layer in parameters_filtered.items():
            units_data_array = EdrProvider.evaluate_layer(requested_native_coordinates, layer)
            if units_data_array is not None:
                dataset[requested_parameter] = units_data_array

        self.check_query_condition(len(dataset) == 0, "No matching parameters found.")

        if (
            output_format == settings.COVERAGE_JSON.lower()
            or output_format == settings.JSON.lower()
            or output_format == settings.HTML.lower()
        ):
            crs = self.interpret_crs(requested_native_coordinates.crs if requested_native_coordinates else None)
            layers = self.get_layers(self.base_url, self.collection_id)
            return self.to_coverage_json(layers, dataset, crs)

        return self.to_geotiff_response(dataset, self.collection_id)

    def position(self, **kwargs):
        """Handles requests for the position query type.

        Parameters
        ----------
        wkt : shapely.geometry
            WKT geometry
        crs : str
            The requested CRS for the return coordinates and data.

        Returns
        -------
        Any
            Coverage data as a dictionary of CoverageJSON or native format.

        Raises
        ------
        ProviderInvalidQueryError
            Raised if the wkt string is not provided.
        ProviderInvalidQueryError
            Raised if the wkt string is an unknown type.
        """
        lat, lon = [], []
        wkt = kwargs.get("wkt")
        crs = kwargs.get("crs")
        crs = EdrProvider.interpret_crs(crs)

        if not isinstance(wkt, BaseGeometry):
            msg = "Invalid WKT string provided for the position query."
            raise ProviderInvalidQueryError(msg, user_msg=msg)
        elif wkt.geom_type == "Point":
            lon, lat = EdrProvider.crs_converter([wkt.x], [wkt.y], crs)
        else:
            msg = "Unknown WKT string type for the position query (use Point)."
            raise ProviderInvalidQueryError(msg, user_msg=msg)

        requested_coordinates = podpac.Coordinates([lat, lon], dims=["lat", "lon"], crs=crs)

        return self.handle_query(requested_coordinates, **kwargs)

    def cube(self, **kwargs):
        """Handles requests for the cube query type.

        Parameters
        ----------
        bbox : List[float]
            Bbox geometry (for cube queries)
        crs : str
            The requested CRS for the return coordinates and data.

        Returns
        -------
        Any
            Coverage data as a dictionary of CoverageJSON or native format.

        Raises
        ------
        ProviderInvalidQueryError
            Raised if the bounding box is invalid.
        """
        bbox = kwargs.get("bbox")
        crs = kwargs.get("crs")
        crs = EdrProvider.interpret_crs(crs)

        if not isinstance(bbox, List) or (len(bbox) != 4 and len(bbox) != 6):
            msg = (
                "Invalid bounding box provided, "
                "expected bounding box of (minx, miny, maxx, maxy) or (minx, miny, minz, maxx, maxy, maxz)."
            )
            raise ProviderInvalidQueryError(msg, user_msg=msg)

        if len(bbox) == 6:
            xmin, ymin, zmin, xmax, ymax, zmax = bbox
            # Set the z argument if not specified using a closed interval from the bounding box data
            if kwargs["z"] is None:
                kwargs["z"] = f"{zmin}/{zmax}"
        else:
            xmin, ymin, xmax, ymax = bbox

        lon, lat = EdrProvider.crs_converter([xmin, xmax], [ymin, ymax], crs)
        requested_coordinates = podpac.Coordinates([lat, lon], dims=["lat", "lon"], crs=crs)
        return self.handle_query(requested_coordinates, **kwargs)

    def area(self, **kwargs):
        """Handles requests for the area query type.

        Parameters
        ----------
        wkt : shapely.geometry
            WKT geometry
        crs : str
            The requested CRS for the return coordinates and data.

        Returns
        -------
        Any
            Coverage data as a dictionary of CoverageJSON or native format.

        Raises
        ------
        ProviderInvalidQueryError
            Raised if the wkt string is not provided.
        ProviderInvalidQueryError
            Raised if the wkt string is an unknown type.
        """
        lat, lon = [], []
        wkt = kwargs.get("wkt")
        crs = kwargs.get("crs")
        crs = EdrProvider.interpret_crs(crs)

        if not isinstance(wkt, BaseGeometry):
            msg = "Invalid WKT string provided for the area query."
            raise ProviderInvalidQueryError(msg, user_msg=msg)
        elif wkt.geom_type == "Polygon":
            lon, lat = EdrProvider.crs_converter(wkt.exterior.xy[0], wkt.exterior.xy[1], crs)
        else:
            msg = "Unknown WKT string type for the area query (use Polygon)."
            raise ProviderInvalidQueryError(msg, user_msg=msg)

        requested_coordinates = podpac.Coordinates([lat, lon], dims=["lat", "lon"], crs=crs)

        return self.handle_query(requested_coordinates, **kwargs)

    def get_instance(self, instance: str) -> str | None:
        """Validate instance identifier.

        Parameters
        ----------
        instance : str
            The instance identifier to validate.

        Returns
        -------
        str
            The instance identifier if valid, otherwise returns None.
        """
        return instance if instance in self.instances() else None

    def instances(self, **kwargs) -> List[str]:
        """The instances in the collection.

        Returns
        -------
        List[str]
            The instances available in the collection.
        """
        instances = set()
        collection_layers = self.get_layers(self.base_url, self.collection_id)
        for layer in collection_layers:
            instances.update(layer.time_instances())
        return list(instances)

    def get_fields(self) -> Dict[str, Any]:
        """The observed property fields (parameters) in the collection.

        Returns
        -------
        Dict[str, Any]
            The fields based on the available parameters.
        """
        fields = {}
        for parameter_key, layer in self.parameters.items():
            fields[parameter_key] = {
                "type": "number",
                "title": parameter_key,
                "description": layer.abstract,
                "x-ogc-unit": layer.get_units(),
            }
        return fields

    @staticmethod
    def evaluate_layer(requested_coordinates: podpac.Coordinates, layer: pogc.Layer) -> podpac.UnitsDataArray | None:
        """Evaluate a layer using the requested coordinates.

        Temporal coordinates are ignored if the layer does not include them.

        Parameters
        ----------
        requested_coordinates : podpac.Coordinates
            The requested coordinates for the evaluation.
        layer : pogc.Layer
            The layer to evaluate.

        Returns
        -------
        podpac.UnitsDataArray
            The units data array returned from evaluation or None if the node was not found.
        """
        coordinates = layer.get_coordinates_list()
        layer_requested_coordinates = requested_coordinates
        units_data_array = None
        if len(coordinates) > 0 and "time" not in coordinates[0].udims:
            layer_requested_coordinates = layer_requested_coordinates.udrop(
                ["time", "forecastOffsetHr"], ignore_missing=True
            )
        if layer.node is not None:
            units_data_array = layer.node.eval(layer_requested_coordinates)
            if "forecastOffsetHr" in units_data_array.dims or "time_forecastOffsetHr" in units_data_array.dims:
                if "time_forecastOffsetHr" not in units_data_array.dims:
                    units_data_array = units_data_array.stack(time_forecastOffsetHr=("time", "forecastOffsetHr"))
                forecast_offsets = units_data_array.forecastOffsetHr.data.copy()
                time_data = units_data_array.time.data.copy()
                units_data_array = units_data_array.drop_vars({"time", "time_forecastOffsetHr", "forecastOffsetHr"})
                units_data_array = units_data_array.rename(time_forecastOffsetHr="time")
                units_data_array = units_data_array.assign_coords(time=time_data + forecast_offsets)

        return units_data_array

    @staticmethod
    def get_altitudes(layers: List[pogc.Layer]) -> List[float]:
        """The list of available altitudes for the provided layers.

        Parameters
        ----------
        layers : List[pogc.Layer]
            The list of layers to determine altitudes for.

        Returns
        -------
        List[float]
            Available altitudes for the providers layers.
        """

        available_altitudes = set()
        for layer in layers:
            coordinates_list = layer.get_coordinates_list()
            if len(coordinates_list) > 0 and "alt" in coordinates_list[0].udims:
                available_altitudes.update(coordinates_list[0]["alt"].coordinates)

        return list(available_altitudes)

    @staticmethod
    def get_datetimes(layers: List[pogc.Layer], instance_time: str | None) -> List[np.datetime64]:
        """The list of available times for the provided layers.

        Parameters
        ----------
        layers : List[pogc.Layer]
            The list of layers to determine datetimes for.
        instance_time: str | None
            The optional instance time which forecast datetimes are being requested for.
        Returns
        -------
        List[np.datetime64]
            Available time values for the provider layers.
        """

        available_times = set()
        for layer in layers:
            coordinates_list = layer.get_coordinates_list()
            if len(coordinates_list) > 0 and "time" in coordinates_list[0].udims:
                if instance_time in layer.time_instances() and "forecastOffsetHr" in coordinates_list[0].udims:
                    # Retrieve available forecastOffSetHr and instance time combinations
                    instance_datetime = np.datetime64(instance_time)
                    instance_coordinates = coordinates_list[0].select({"time": [instance_datetime, instance_datetime]})
                    selected_offset_coordinates = instance_coordinates["forecastOffsetHr"].coordinates
                    available_times.update(
                        [np.datetime64(instance_time) + offset for offset in selected_offset_coordinates]
                    )
                elif not instance_time and "forecastOffsetHr" not in coordinates_list[0].udims:
                    # Retrieve layer times for non-instance requests
                    available_times.update(coordinates_list[0]["time"].coordinates)

        return list(available_times)

    @staticmethod
    def interpret_crs(crs: str | None) -> str:
        """Interpret the CRS id string into a valid PyProj CRS format.

        If None provided, return the default.
        If the provided CRS is invalid, raise an error.

        Parameters
        ----------
        crs : str
            The input CRS id string which needs to be validated/converted.

        Returns
        -------
        str
            Pyproj CRS string.

        Raises
        ------
        ProviderInvalidQueryError
            Raised if the provided CRS string is unknown.
        """
        if crs is None:
            return settings.crs_84_uri_format  # Pyproj acceptable format

        if crs.lower() not in [key.lower() for key in settings.EDR_CRS.keys()]:
            msg = f"Invalid CRS provided, expected one of {', '.join(settings.EDR_CRS.keys())}"
            raise ProviderInvalidQueryError(msg, user_msg=msg)

        return crs

    @staticmethod
    def crs_converter(x: Any, y: Any, crs: str) -> Tuple[Any, Any]:
        """Convert the X, Y data to Longitude, Latitude data with the provided crs.

        Parameters
        ----------
        x : Any
            X data in any form.
        y: Any
            Y data in any form.
        crs : str
            The input CRS id string to apply to convert the X,Y data.

        Returns
        -------
        Tuple[Any, Any]
            The X,Y as Longitude/Latitude data.
        """
        if crs.lower() == settings.epsg_4326_uri_format.lower():
            return (y, x)

        return (x, y)

    @staticmethod
    def interpret_altitude_coordinates(
        available_altitudes: List[float], altitude_string: str | None, crs: str | None
    ) -> podpac.Coordinates | None:
        """Interpret the altitude string into altitude coordinates using known formats.

        Specification:
        single-level          = level
        interval-closed       = min-level "/" max-level
        repeating-interval    = "R"number of intervals "/" min-level "/" height to increment by
        level-list            = level1 "," level2 "," level3

        Parameters
        ----------
        available_altitudes: List[float]
            The available altitudes for interpretation.
        altitude_string : str | None
            The string representation of the requested altitudes.
        crs : str
            The CRS that the coordinates need to match.

        Returns
        -------
        podpac.Coordinates | None
            Altitude coordinates for the request or None if no matching altitudes were found.

        Raises
        ------
        ProviderInvalidQueryError
            Raised if the provided altitude string is invalid.
        """

        if len(available_altitudes) == 0:
            return None
        if not altitude_string:
            return podpac.Coordinates([available_altitudes], dims=["alt"], crs=crs)

        try:
            altitudes = None
            if "/" in altitude_string:
                altitudes_split = altitude_string.split("/")
                if len(altitudes_split) == 2:
                    minimum = float(altitudes_split[0])
                    maximum = float(altitudes_split[1])
                    altitudes = [alt for alt in available_altitudes if minimum <= alt <= maximum]
                if len(altitudes_split) == 3:
                    if altitudes_split[0].startswith("R"):
                        altitudes = float(altitudes_split[1]) + np.arange(float(altitudes_split[0][1:])) * float(
                            altitudes_split[2]
                        )
            else:
                altitudes = [float(alt) for alt in altitude_string.split(",")]
        except ValueError:
            msg = "Invalid vertical level requested."
            raise ProviderInvalidQueryError(msg, user_msg=msg)

        return podpac.Coordinates([altitudes], dims=["alt"], crs=crs) if altitudes is not None else None

    @staticmethod
    def interpret_time_coordinates(
        available_times: List[np.datetime64], time_string: str | None, instance_time: str | None, crs: str | None
    ) -> podpac.Coordinates | None:
        """Interpret the time string and instance into time coordinates using known formats.

        Specification:
        interval-closed     = date-time "/" date-time
        interval-open-start = "../" date-time
        interval-open-end   = date-time "/.."
        interval            = interval-closed / interval-open-start / interval-open-end
        datetime            = date-time / interval

        Parameters
        ----------
        available_times: List[np.datetime64]
            The available times for interpretation.
        time_string : str | None
            The string representation of the requested times.
        instance_time: str | None
            The string representation of the requested instance time.
        crs : str
            The CRS that the coordinates need to match.

        Returns
        -------
        podpac.Coordinates | None
            Time coordinates for the request or None if no matching times were found.

        Raises
        ------
        ProviderInvalidQueryError
            Raised if the provided time string is invalid.
        """

        if len(available_times) == 0:
            return None

        try:
            times = None
            np_available_times = np.array(available_times)
            if not time_string:
                times = np_available_times
            elif "/" in time_string:
                times_split = time_string.split("/")
                if len(times_split) == 2:
                    minimum = times_split[0]
                    maximum = times_split[1]
                    if minimum == "..":
                        times = [time for time in np_available_times if time <= np.datetime64(maximum)]
                    elif maximum == "..":
                        times = [time for time in np_available_times if time >= np.datetime64(minimum)]
                    else:
                        times = [
                            time
                            for time in np_available_times
                            if np.datetime64(minimum) <= time <= np.datetime64(maximum)
                        ]
            else:
                times = [np.datetime64(time_string)]
        except ValueError:
            msg = "Invalid datetime requested."
            raise ProviderInvalidQueryError(msg, user_msg=msg)

        if times is None:
            msg = "Invalid datetime requested."
            raise ProviderInvalidQueryError(msg, user_msg=msg)

        if instance_time:
            offsets = [np.timedelta64(time - np.datetime64(instance_time), "h") for time in times]
            return podpac.Coordinates(
                [[[instance_time] * len(offsets), offsets]], dims=[["time", "forecastOffsetHr"]], crs=crs
            )

        return podpac.Coordinates([times], dims=["time"], crs=crs)

    @staticmethod
    def to_coverage_json(
        layers: List[pogc.Layer], dataset: Dict[str, podpac.UnitsDataArray], crs: str
    ) -> Dict[str, Any]:
        """Generate a CoverageJSON of the data for the provided parameters.

        Parameters
        ----------
        layers : List[pogc.Layer]
            Layers which were used in the dataset creation for metadata information.
        dataset : Dict[str, podpac.UnitsDataArray]
            Data in an units data array format with matching parameter key.
        crs : str
            The CRS associated with the requested coordinates and data response.

        Returns
        -------
        Dict[str, Any]
            A dictionary of the CoverageJSON data.
        """

        # Determine the bounding coordinates, assume they all are the same
        coordinates = next(iter(dataset.values())).coords
        x_arr, y_arr = EdrProvider.crs_converter(coordinates["lon"].values, coordinates["lat"].values, crs)

        # Convert numpy array coordinates to a flattened list.
        x_arr = list(x_arr.flatten())
        y_arr = list(y_arr.flatten())

        coverage_json = {
            "type": "Coverage",
            "domain": {
                "type": "Domain",
                "domainType": "Grid",
                "axes": {
                    "x": {
                        "start": x_arr[0] if len(x_arr) > 0 else None,
                        "stop": x_arr[-1] if len(x_arr) > 0 else None,
                        "num": len(x_arr),
                    },
                    "y": {
                        "start": y_arr[0] if len(y_arr) > 0 else None,
                        "stop": y_arr[-1] if len(y_arr) > 0 else None,
                        "num": len(y_arr),
                    },
                },
                "referencing": [
                    {
                        "coordinates": ["x", "y"],
                        "system": {"type": "GeographicCRS", "id": crs},
                    },
                    *(
                        [
                            {
                                "coordinates": ["t"],
                                "system": {
                                    "type": "TemporalRS",
                                    "calendar": "Gregorian",
                                },
                            }
                        ]
                        if "time" in coordinates.dims
                        else []
                    ),
                    *(
                        [
                            {
                                "coordinates": ["z"],
                                "system": {"type": "VerticalCRS"},
                            }
                        ]
                        if "alt" in coordinates.dims
                        else []
                    ),
                ],
                "parameters": {},
                "ranges": {},
            },
        }
        if "time" in coordinates.dims:
            coverage_json["domain"]["axes"]["t"] = {
                "values": [
                    time.astype("datetime64[ms]").astype(datetime).isoformat() + "Z"
                    for time in coordinates["time"].values
                ]
            }

        for param, data_array in dataset.items():
            layer = next((layer for layer in layers if layer.identifier == param), None)
            if layer is not None:
                units = layer.get_units()
                parameter_definition = {
                    param: {
                        "type": "Parameter",
                        "observedProperty": {
                            "label": {
                                "id": param,
                                "en": param,
                            }
                        },
                        "description": layer.abstract,
                        "unit": {
                            "label": {"en": param},
                            "symbol": {
                                "value": units,
                                "type": None,
                            },
                        },
                    }
                }
                coverage_json["domain"]["parameters"].update(parameter_definition)
            coverage_json["domain"]["ranges"].update(
                {
                    param: {
                        "type": "NdArray",
                        "dataType": "float",
                        "axisNames": list(data_array.coords.keys()),
                        "shape": data_array.shape,
                        "values": list(data_array.values.flatten()),  # Row Major Order
                    }
                }
            )

        return coverage_json

    @staticmethod
    def check_query_condition(conditional: bool, message: str):
        """Check the provided conditional and raise a ProviderInvalidQueryError if true.

        Parameters
        ----------
        conditional : bool
            The conditional value to check for raising a query error.
        message : str
            The message to include if the query error is raised.

        Raises
        ------
        ProviderInvalidQueryError
            Raised if the conditional provided is true.
        """
        if conditional:
            raise ProviderInvalidQueryError(message, user_msg=message)

    @staticmethod
    def validate_datetime(datetime_string: str) -> bool:
        """Validate whether a string can be converted to a numpy datetime.

        Parameters
        ----------
        date_string : str
            The datetime string to be validated.

        Returns
        -------
        bool
            Whether the datetime string can be converted to a numpy datetime.
        """
        try:
            np.datetime64(datetime_string)
            return True
        except ValueError:
            return False

    @staticmethod
    def to_geotiff_response(dataset: Dict[str, podpac.UnitsDataArray], collection_id: str) -> Dict[str, Any]:
        """Generate a geotiff of the data for the provided parameters.

        Parameters
        ----------
        dataset : Dict[str, podpac.UnitsDataArray]
            Data in an units data array format with matching parameter key.
        collection_id : str
            The collection id of the data used in naming the zip file if needed.

        Returns
        -------
        Dict[str, Any]
            A dictionary the file name and data with a Base64 encoding.
        """
        if len(dataset) == 1:
            units_data_array = next(iter(dataset.values()))
            geotiff_bytes = units_data_array.to_format("geotiff").read()
            return {
                "fp": base64.b64encode(geotiff_bytes).decode("utf-8"),
                "fn": f"{next(iter(dataset.keys()))}.tif",
            }
        else:
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for parameter, data_array in dataset.items():
                    geotiff_memory_file = data_array.to_format("geotiff")
                    tiff_filename = f"{parameter}.tif"
                    zip_file.writestr(tiff_filename, geotiff_memory_file.read())

            zip_buffer.seek(0)
            return {"fp": base64.b64encode(zip_buffer.read()).decode("utf-8"), "fn": f"{collection_id}.zip"}

    @staticmethod
    def get_native_coordinates(
        source_coordinates: podpac.Coordinates,
        target_coordinates: podpac.Coordinates,
    ) -> podpac.Coordinates:
        """Find the intersecting latitude and longitude coordinates between the source and target.

        Parameters
        ----------
        source_coordinates : podpac.Coordinates
            The source coordinates to be converted.
        target_coordinates : podpac.Coordinates
            The target coordinates to find intersections on.

        Returns
        -------
        podpac.Coordinates
            The converted coordinates source coordinates intersecting with the target coordinates.
        """
        # Find intersections with target keeping source crs
        target_spatial_coordinates = podpac.Coordinates(
            [target_coordinates["lat"], target_coordinates["lon"]], dims=["lat", "lon"]
        )
        source_intersection_coordinates = target_spatial_coordinates.intersect(source_coordinates, dims=["lat", "lon"])
        source_intersection_coordinates = source_intersection_coordinates.transform(source_coordinates.crs)
        return podpac.coordinates.merge_dims(
            [source_intersection_coordinates, source_coordinates.udrop(["lat", "lon"], ignore_missing=True)]
        )
