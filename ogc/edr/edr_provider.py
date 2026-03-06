import json
import tempfile
import numpy as np
import zipfile
import pyproj
from datetime import datetime
from collections import defaultdict
from typing import List, Dict, Tuple, Any
from pyproj.exceptions import CRSError
from shapely.geometry.base import BaseGeometry
from pygeoapi.provider.base import ProviderConnectionError, ProviderInvalidQueryError
from pygeoapi.provider.base_edr import BaseEDRProvider
from ogc import podpac as pogc
import podpac

from .. import settings


class EdrProvider(BaseEDRProvider):
    """Custom provider to be used with layer data sources."""

    _layers_dict = defaultdict(list)
    _extra_args = defaultdict()

    @classmethod
    def set_extra_query_args(cls, args: Dict[str, Any]):
        """Set the extra arguments which will be available to the provider on a request.

        Parameters
        ----------
        args : Dict[str, Any]
            The extra arguments which are not included in the default requests.
        """
        cls._extra_args = args

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

    @classmethod
    def is_collection_queryable(cls, base_url: str, group: str) -> bool:
        """Determine whether a collection contains directly queryable data or is only queryable through instances.

        Parameters
        ----------
        base_url : str
            The base URL for the layers.
        group : str
            Collection to check if direct querying is possible.

        Returns
        -------
        bool
            True if the collection can be queried directly, false otherwise.
        """
        layers = cls.get_layers(base_url, group)
        for layer in layers:
            coordinates = layer.get_coordinates()
            if coordinates is not None and "forecastOffsetHr" not in coordinates.udims:
                return True
        return False

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
        resolution-x : str
            The number of requested data points, as a string, in the x-direction.
        resolution-y : str
            The number of requested data points, as a string, in the y-direction.

        Returns
        -------
        Any
            Coverage data as a dictionary of CoverageJSON or native format.

        Raises
        ------
        ProviderInvalidQueryError
            Raised if an invalid instance is provided.
        ProviderInvalidQueryError
            Raised if an invalid parameter is provided.
        ProviderInvalidQueryError
            Raised if a datetime string is provided but cannot be interpreted.
        ProviderInvalidQueryError
            Raised if an altitude string is provided but cannot be interpreted.
        ProviderInvalidQueryError
            Raised if a GeoTIFF request includes multiple time bands.
        ProviderInvalidQueryError
            Raised if a GeoTIFF request includes multiple vertical bands.
        ProviderInvalidQueryError
            Raised if native coordinates could not be found.
        ProviderInvalidQueryError
            Raised if the request queries for native coordinates exceeding the max allowable size.
        ProviderInvalidQueryError
            Raised if no parameters could not be evaluated.
        """
        instance = kwargs.get("instance")
        requested_parameters = kwargs.get("select_properties")
        output_format = kwargs.get("format_")
        datetime_arg = kwargs.get("datetime_")
        z_arg = kwargs.get("z")
        resolution_x = kwargs.get("resolution-x")
        resolution_y = kwargs.get("resolution-y")

        instance = self.validate_instance(instance)
        requested_parameters = self.validate_parameters(requested_parameters)
        resolution_x, resolution_y = self.validate_resolution(resolution_x, resolution_y)

        crs = self.interpret_crs(requested_coordinates.crs)
        available_times = self.get_datetimes(list(self.parameters.values()), instance)
        available_altitudes = self.get_altitudes(list(self.parameters.values()))
        time_coords = self.interpret_time_coordinates(
            available_times, datetime_arg, instance, requested_coordinates.crs
        )
        altitude_coords = self.interpret_altitude_coordinates(available_altitudes, z_arg, requested_coordinates.crs)

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
            requested_coordinates = podpac.coordinates.merge_dims([altitude_coords, requested_coordinates])

        # Handle defining native coordinates for the query, these should match between each layer
        coordinates = next(iter(requested_parameters.values())).get_coordinates()
        self.check_query_condition(coordinates is None, "Native coordinates not found.")
        resolution_lon, resolution_lat = self.crs_converter(resolution_x, resolution_y, crs)
        requested_native_coordinates = self.get_native_coordinates(
            requested_coordinates, coordinates, resolution_lat, resolution_lon
        )

        self.check_query_condition(
            bool(requested_native_coordinates.size > settings.MAX_GRID_COORDS_REQUEST_SIZE),
            "Coordinates size must be less than %d" % settings.MAX_GRID_COORDS_REQUEST_SIZE,
        )

        dataset = {}
        for requested_parameter, layer in requested_parameters.items():
            units_data_array = EdrProvider.evaluate_layer(requested_native_coordinates, layer)
            if units_data_array is not None:
                dataset[requested_parameter] = units_data_array

        self.check_query_condition(len(dataset) == 0, "No matching parameters found.")

        if (
            output_format == settings.COVERAGE_JSON.lower()
            or output_format == settings.JSON.lower()
            or output_format == settings.HTML.lower()
        ):
            layers = self.get_layers(self.base_url, self.collection_id)
            return self.to_coverage_json(layers, dataset, self.collection_id, crs)

        return self.to_geotiff_response(dataset, self.collection_id)

    def position(self, **kwargs):
        """Handles requests for the position query type.

        Parameters
        ----------
        wkt : shapely.geometry
            WKT geometry
        format_ : str
            The requested output format of the data.

        Returns
        -------
        Any
            Coverage data as a dictionary of CoverageJSON or native format.

        Raises
        ------
        ProviderInvalidQueryError
            Raised if an invalid output format is provided.
        ProviderInvalidQueryError
            Raised if the wkt string is not provided.
        ProviderInvalidQueryError
            Raised if the wkt string is an unknown type.
        """
        lat, lon = [], []
        wkt = kwargs.get("wkt")
        crs = self._extra_args.get("crs")
        crs = EdrProvider.interpret_crs(crs)
        kwargs["format_"] = self.validate_output_format(kwargs["format_"], "position")

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
        format_ : str
            The requested output format of the data.

        Returns
        -------
        Any
            Coverage data as a dictionary of CoverageJSON or native format.

        Raises
        ------
        ProviderInvalidQueryError
            Raised if an invalid output format is provided.
        ProviderInvalidQueryError
            Raised if the bounding box is invalid.
        """
        bbox = kwargs.get("bbox")
        crs = self._extra_args.get("crs")
        crs = EdrProvider.interpret_crs(crs)
        kwargs["format_"] = self.validate_output_format(kwargs["format_"], "cube")
        kwargs["resolution-x"] = self._extra_args.get("resolution-x")
        kwargs["resolution-y"] = self._extra_args.get("resolution-y")

        if not isinstance(bbox, List) or (len(bbox) != 4 and len(bbox) != 6):
            msg = (
                "Invalid bounding box provided, "
                "expected bounding box of (minx, miny, maxx, maxy) or (minx, miny, minz, maxx, maxy, maxz)."
            )
            raise ProviderInvalidQueryError(msg, user_msg=msg)

        if len(bbox) == 6:
            xmin, ymin, zmin, xmax, ymax, zmax = bbox
            # Set the z argument if not specified using a closed interval from the bounding box data
            if kwargs.get("z") is None:
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
        format_ : str
            The requested output format of the data.

        Returns
        -------
        Any
            Coverage data as a dictionary of CoverageJSON or native format.

        Raises
        ------
        ProviderInvalidQueryError
            Raised if an invalid output format is provided.
        ProviderInvalidQueryError
            Raised if the wkt string is not provided.
        ProviderInvalidQueryError
            Raised if the wkt string is an unknown type.
        """
        lat, lon = [], []
        wkt = kwargs.get("wkt")
        crs = self._extra_args.get("crs")
        crs = EdrProvider.interpret_crs(crs)
        kwargs["format_"] = self.validate_output_format(kwargs["format_"], "area")
        kwargs["resolution-x"] = self._extra_args.get("resolution-x")
        kwargs["resolution-y"] = self._extra_args.get("resolution-y")

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

    def validate_output_format(self, output_format: str | None, query_type: str) -> str:
        """Validate the output format for a query.

        If None provided, return the default.
        If the provided output format is invalid, raise an error.

        Parameters
        ----------
        output_format : str | None
            The specified output format which needs to be validated.
        query_type: str
            The query type to validate output formats against.

        Returns
        -------
        str
            Output format string.

        Raises
        ------
        ProviderInvalidQueryError
            Raised if the provided output format is invalid.
        """
        if output_format is None:
            return settings.EDR_QUERY_DEFAULTS.get(query_type, "")

        if output_format.lower() not in [key.lower() for key in settings.EDR_QUERY_FORMATS.get(query_type, [])]:
            msg = (
                f"Invalid format provided, expected one of {', '.join(settings.EDR_QUERY_FORMATS.get(query_type, []))}"
            )
            raise ProviderInvalidQueryError(msg, user_msg=msg)

        return output_format.lower()

    def validate_resolution(self, resolution_x: str | None, resolution_y: str | None) -> Tuple[int, int]:
        """Validate the resolutions and return the values as integers.

        If no resolution is provided in a specific direction a zero value should be used to indicate native resolution.

        Parameters
        ----------
        resolution_x : str | None
            The resolution in the x-direction or None.
        resolution_y : str | None
            The resolution in the y-direction or None.

        Returns
        -------
        Tuple[int, int]
            Resolution x and y as integers.

        Raises
        ------
        ProviderInvalidQueryError
            Raised if either of the provided resolutions is invalid.
        """
        valid_resolutions = True
        validated_resolution_x = 0
        validated_resolution_y = 0
        try:
            validated_resolution_x = int(0 if resolution_x is None else resolution_x)
            validated_resolution_y = int(0 if resolution_y is None else resolution_y)
            valid_resolutions = validated_resolution_x >= 0 and validated_resolution_y >= 0
        except ValueError:
            valid_resolutions = False

        if not valid_resolutions:
            msg = "Invalid resolution provided, expected positive integer."
            raise ProviderInvalidQueryError(msg, user_msg=msg)

        return validated_resolution_x, validated_resolution_y

    def validate_instance(self, instance: str | None) -> str | None:
        """Validate the instance for a query.

        If None provided, the collection is being queried.
        If the instance is invalid, raise an error.

        Parameters
        ----------
        instance : str | None
            The instance which needs to be validated.

        Returns
        -------
        str | None
            The validated instance or None if the collection is being queried.

        Raises
        ------
        ProviderInvalidQueryError
            Raised if the provided instance is invalid.
        """
        if instance is None:
            return None

        if instance not in self.instances():
            msg = "Invalid instance provided."
            raise ProviderInvalidQueryError(msg, user_msg=msg)

        return instance

    def validate_parameters(self, parameters: List[str] | None) -> Dict[str, pogc.Layer]:
        """Validate the parameters for a query.

        If None provided or an list is empty, return all parameters.
        If the provided parameter list is invalid, raise an error.

        Parameters
        ----------
        parameters : List[str] | None
            The specified parameters for a query.

        Returns
        -------
        Dict[str, pogc.Layer]
            The validated parameters dictionary containing associated layers.

        Raises
        ------
        ProviderInvalidQueryError
            Raised if the provided parameters are invalid.
        """
        if parameters is None or len(parameters) == 0:
            return self.parameters

        parameters_lower = [param.lower() for param in parameters]
        parameters_filtered = {
            key: value
            for key, value in self.parameters.items()
            if key.lower() in parameters_lower and value is not None
        }
        if len(parameters_filtered) != len(parameters):
            msg = "Invalid parameters provided."
            raise ProviderInvalidQueryError(msg, user_msg=msg)

        return parameters_filtered

    @staticmethod
    def evaluate_layer(requested_coordinates: podpac.Coordinates, layer: pogc.Layer) -> podpac.UnitsDataArray | None:
        """Evaluate a layer using the requested coordinates.

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
        coordinates = layer.get_coordinates()
        layer_requested_coordinates = requested_coordinates
        units_data_array = None
        if coordinates is None:
            return units_data_array

        layer_has_instances = "forecastOffsetHr" in coordinates.udims
        request_has_instances = "forecastOffsetHr" in requested_coordinates.udims
        if layer_has_instances ^ request_has_instances:
            return units_data_array

        if "time" not in coordinates[0].udims:
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
                if units_data_array.attrs.get("bounds", None):
                    filtered_bounds = {
                        coord: bnd
                        for coord, bnd in units_data_array.attrs["bounds"].items()
                        if coord in units_data_array.coords.dims
                    }
                    units_data_array.attrs["bounds"] = filtered_bounds

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
            coordinates = layer.get_coordinates()
            if coordinates is not None and "alt" in coordinates.udims:
                available_altitudes.update(coordinates["alt"].coordinates)

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
            coordinates = layer.get_coordinates()
            if coordinates is not None and "time" in coordinates.udims:
                if instance_time in layer.time_instances() and "forecastOffsetHr" in coordinates.udims:
                    # Retrieve available forecastOffSetHr and instance time combinations
                    instance_datetime = np.datetime64(instance_time)
                    instance_coordinates = coordinates.select({"time": [instance_datetime, instance_datetime]})
                    selected_offset_coordinates = instance_coordinates["forecastOffsetHr"].coordinates
                    available_times.update(
                        [np.datetime64(instance_time) + offset for offset in selected_offset_coordinates]
                    )
                elif not instance_time and "forecastOffsetHr" not in coordinates.udims:
                    # Retrieve layer times for non-instance requests
                    available_times.update(coordinates["time"].coordinates)

        return list(available_times)

    @staticmethod
    def interpret_crs(crs: str | None) -> str:
        """Interpret the CRS id string into a valid WKT CRS format.

        If None provided, return the default.
        If the provided CRS is invalid, raise an error.

        Parameters
        ----------
        crs : str | None
            The input CRS id string which needs to be validated/converted.

        Returns
        -------
        str
            WKT CRS string.

        Raises
        ------
        ProviderInvalidQueryError
            Raised if the provided CRS string is unknown.
        """
        if crs is None:
            return pyproj.CRS(settings.crs_84_uri_format).to_wkt()  # Pyproj acceptable format

        try:
            wkt_crs = pyproj.CRS(crs).to_wkt()
            wkt_options = [pyproj.CRS(key).to_wkt() for key in settings.EDR_CRS.keys()]
        except CRSError:
            wkt_crs = None
            wkt_options = []

        if wkt_crs is None or wkt_crs not in wkt_options:
            error_msg = msg = f"Invalid CRS provided, expected one of {', '.join(settings.EDR_CRS.keys())}"
            raise ProviderInvalidQueryError(msg, user_msg=error_msg)

        return wkt_crs

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
        wkt_crs = pyproj.CRS(crs).to_wkt()
        wkt_epsg_4326 = pyproj.CRS(settings.epsg_4326_uri_format).to_wkt()
        if wkt_crs == wkt_epsg_4326:
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

        if not altitude_string and len(available_altitudes) == 0:
            return None

        try:
            altitudes = None
            if not altitude_string:
                altitudes = available_altitudes
            elif "/" in altitude_string:
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

        if altitudes is None:
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

        if not time_string and len(available_times) == 0:
            return None

        try:
            times = None
            if not time_string:
                times = available_times
            elif "/" in time_string:
                times_split = time_string.split("/")
                if len(times_split) == 2:
                    minimum = times_split[0]
                    maximum = times_split[1]
                    if minimum == "..":
                        times = [time for time in available_times if time <= np.datetime64(maximum)]
                    elif maximum == "..":
                        times = [time for time in available_times if time >= np.datetime64(minimum)]
                    else:
                        times = [
                            time for time in available_times if np.datetime64(minimum) <= time <= np.datetime64(maximum)
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
        layers: List[pogc.Layer], dataset: Dict[str, podpac.UnitsDataArray], collection_id: str, crs: str
    ) -> Dict[str, Any]:
        """Generate a CoverageJSON of the data for the provided parameters.

        The returned object must be serializable, so a temporary file is returned to reference the data.

        Parameters
        ----------
        layers : List[pogc.Layer]
            Layers which were used in the dataset creation for metadata information.
        dataset : Dict[str, podpac.UnitsDataArray]
            Data in an units data array format with matching parameter key.
        collection_id : str
            The collection id of the data used in naming the output file.
        crs : str
            The CRS associated with the requested coordinates and data response.

        Returns
        -------
        Dict[str, Any]
            A dictionary of the desired output file name and data path.
        """

        # Determine the bounding coordinates, assume they all are the same
        coordinates = next(iter(dataset.values())).coords
        x_arr, y_arr = EdrProvider.crs_converter(coordinates["lon"].values, coordinates["lat"].values, crs)

        # Convert numpy array coordinates to a flattened list.
        x_arr = list(x_arr.flatten())
        y_arr = list(y_arr.flatten())

        lon_map_value, lat_map_value = EdrProvider.crs_converter("x", "y", crs)
        dimension_map = {"time": "t", "alt": "z", "lon": lon_map_value, "lat": lat_map_value}

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

            data = [x if np.isfinite(x) else None for x in data_array.values.flatten()]
            coverage_json["domain"]["ranges"].update(
                {
                    param: {
                        "type": "NdArray",
                        "dataType": "float",
                        "axisNames": [dimension_map.get(str(key), str(key)) for key in data_array.coords.keys()],
                        "shape": data_array.shape,
                        "values": data,  # Row Major Order
                    }
                }
            )

        encoder = json.JSONEncoder()
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".json", delete=False) as named_file:
            for chunk in encoder.iterencode(coverage_json):
                named_file.write(chunk)

        return {"fp": named_file.name, "fn": f"{collection_id}.json"}

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
    def to_geotiff_response(dataset: Dict[str, podpac.UnitsDataArray], collection_id: str) -> Dict[str, Any]:
        """Generate a geotiff of the data for the provided parameters.

        The returned object must be serializable, so a temporary file is returned to reference the data.

        Parameters
        ----------
        dataset : Dict[str, podpac.UnitsDataArray]
            Data in an units data array format with matching parameter key.
        collection_id : str
            The collection id of the data used in naming the zip file if needed.

        Returns
        -------
        Dict[str, Any]
            A dictionary of the desired output file name and data path.
        """
        if len(dataset) == 1:
            units_data_array = next(iter(dataset.values()))
            geotiff_bytes = units_data_array.to_format("geotiff").read()
            with tempfile.NamedTemporaryFile(mode="wb+", suffix=".tif", delete=False) as named_file:
                named_file.write(geotiff_bytes)
            return {
                "fp": named_file.name,
                "fn": f"{next(iter(dataset.keys()))}.tif",
            }
        else:
            with tempfile.NamedTemporaryFile(mode="wb+", suffix=".zip", delete=False) as named_file:
                with zipfile.ZipFile(named_file, "w", zipfile.ZIP_DEFLATED) as zip_file:
                    for parameter, data_array in dataset.items():
                        geotiff_memory_file = data_array.to_format("geotiff")
                        tiff_filename = f"{parameter}.tif"
                        zip_file.writestr(tiff_filename, geotiff_memory_file.read())

            return {"fp": named_file.name, "fn": f"{collection_id}.zip"}

    @staticmethod
    def get_native_coordinates(
        source_coordinates: podpac.Coordinates,
        target_coordinates: podpac.Coordinates,
        resolution_lat: int,
        resolution_lon: int,
    ) -> podpac.Coordinates:
        """Find the intersecting latitude and longitude coordinates between the source and target.

        Parameters
        ----------
        source_coordinates : podpac.Coordinates
            The source coordinates to be converted.
        target_coordinates : podpac.Coordinates
            The target coordinates to find intersections on.
        resolution_lat: int
            The desired resolution in the latitudinal direction, with a zero value using native resolution.
        resolution_lon: int
            The desired resolution in the longitudinal direction, with a zero value using native resolution.

        Returns
        -------
        podpac.Coordinates
            The converted coordinates source coordinates intersecting with the target coordinates.
        """
        if len(source_coordinates["lat"].coordinates) == 1 and len(source_coordinates["lon"].coordinates) == 1:
            return source_coordinates

        latitudes = (
            target_coordinates["lat"].coordinates
            if resolution_lat == 0
            else np.linspace(
                np.min(source_coordinates["lat"].coordinates),
                np.max(source_coordinates["lat"].coordinates),
                resolution_lat,
            )
        )
        longitudes = (
            target_coordinates["lon"].coordinates
            if resolution_lon == 0
            else np.linspace(
                np.min(source_coordinates["lon"].coordinates),
                np.max(source_coordinates["lon"].coordinates),
                resolution_lon,
            )
        )

        # Find intersections with target keeping source crs
        target_spatial_coordinates = podpac.Coordinates(
            [latitudes, longitudes], dims=["lat", "lon"], crs=target_coordinates.crs
        )
        source_intersection_coordinates = target_spatial_coordinates.intersect(source_coordinates, dims=["lat", "lon"])
        source_intersection_coordinates = source_intersection_coordinates.transform(source_coordinates.crs)
        return podpac.coordinates.merge_dims(
            [source_intersection_coordinates, source_coordinates.udrop(["lat", "lon"], ignore_missing=True)]
        )
