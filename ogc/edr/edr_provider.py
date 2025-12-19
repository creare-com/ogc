import base64
import io
import numpy as np
import zipfile
import traitlets as tl
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
    def get_layers(cls, base_url: str) -> List[pogc.Layer]:
        """Get the layer resources for a specific base URL.

        Parameters
        ----------
        base_url : str
            The base URL for the layers.

        Returns
        -------
        List[pogc.Layer]
            The layers associated with the base URL.
        """
        return cls._layers_dict.get(base_url, [])

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
        collection_id = provider_def.get("data", None)
        if collection_id is None:
            raise ProviderConnectionError("Data not found.")

        self.collection_id = str(collection_id)

        self.base_url = provider_def.get("base_url", None)
        if self.base_url is None:
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
        return {
            layer.identifier: layer for layer in self.get_layers(self.base_url) if layer.group == self.collection_id
        }

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
        available_times = self.get_datetimes(list(self.parameters.values()))
        available_altitudes = self.get_altitudes(list(self.parameters.values()))
        time_coords = self.interpret_time_coordinates(available_times, datetime_arg, requested_coordinates.crs)
        altitude_coords = self.interpret_altitude_coordinates(available_altitudes, z_arg, requested_coordinates.crs)
        # Allow parameters without case-sensitivity
        parameters_lower = [param.lower() for param in requested_parameters or []]
        parameters_filtered = {
            key: value
            for key, value in self.parameters.items()
            if key.lower() in parameters_lower and value is not None
        }

        self.check_query_condition(datetime_arg is not None and time_coords is None, "Invalid datetime provided.")
        self.check_query_condition(z_arg is not None and altitude_coords is None, "Invalid altitude provided.")
        self.check_query_condition(len(parameters_filtered) == 0, "Invalid parameters provided.")
        self.check_query_condition(
            instance is not None and not self.validate_datetime(instance), "Invalid instance time provided."
        )

        if time_coords is not None:
            requested_coordinates = podpac.coordinates.merge_dims([time_coords, requested_coordinates])
        if altitude_coords is not None:
            requested_coordinates = podpac.coordinates.merge_dims([altitude_coords, requested_coordinates])

        # Handle defining native coordinates for the query, these should match between each layer
        coordinates_list = next(iter(parameters_filtered.values())).node.find_coordinates()

        self.check_query_condition(len(coordinates_list) == 0, "Native coordinates not found.")

        requested_native_coordinates = self.get_native_coordinates(
            requested_coordinates, coordinates_list[0], np.datetime64(instance)
        )

        self.check_query_condition(
            bool(requested_native_coordinates.size > settings.MAX_GRID_COORDS_REQUEST_SIZE),
            "Grid coordinates x_size * y_size must be less than %d" % settings.MAX_GRID_COORDS_REQUEST_SIZE,
        )

        dataset = {}
        for requested_parameter, layer in parameters_filtered.items():
            units_data_array = layer.node.eval(requested_native_coordinates)
            # Recombine stacked temporal dimensions if necessary.
            # The temporal output should always be stacked, based on stacked input.
            if "time_forecastOffsetHr" in units_data_array.dims:
                forecast_offsets = units_data_array.forecastOffsetHr.data.copy()
                time_data = units_data_array.time.data.copy()
                units_data_array = units_data_array.drop_vars({"time", "time_forecastOffsetHr", "forecastOffsetHr"})
                units_data_array = units_data_array.rename(time_forecastOffsetHr="time")
                units_data_array = units_data_array.assign_coords(time=time_data + forecast_offsets)
            dataset[requested_parameter] = units_data_array

        self.check_query_condition(len(dataset) == 0, "No matching parameters found.")

        # Return a coverage json if specified, else return Base64 encoded native response
        if output_format == "json" or output_format == "coveragejson":
            crs = self.interpret_crs(requested_native_coordinates.crs if requested_native_coordinates else None)
            layers = self.get_layers(self.base_url)
            return self.to_coverage_json(layers, dataset, crs)
        else:
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

        if not isinstance(bbox, List) or len(bbox) != 4:
            msg = "Invalid bounding box provided, expected bounding box of (minx, miny, maxx, maxy)."
            raise ProviderInvalidQueryError(msg, user_msg=msg)

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
        layers = self.get_layers(self.base_url)
        for layer in layers:
            if layer.group == self.collection_id:
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
            units = layer.node.units if layer.node.units is not None else layer.node.style.units
            fields[parameter_key] = {
                "type": "number",
                "title": parameter_key,
                "x-ogc-unit": units,
            }
        return fields

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
            coordinates_list = layer.node.find_coordinates()
            if len(coordinates_list) > 0 and "alt" in coordinates_list[0].udims:
                available_altitudes.update(coordinates_list[0]["alt"].coordinates)

        return list(available_altitudes)

    @staticmethod
    def get_datetimes(layers: List[pogc.Layer]) -> List[str]:
        """The list of available times for the provided layers.

        Parameters
        ----------
        layers : List[pogc.Layer]
            The list of layers to determine datetimes for.

        Returns
        -------
        List[str]
            Available time strings for the provider layers.
        """

        available_times = set()
        for layer in layers:
            if hasattr(layer, "valid_times") and layer.valid_times is not tl.Undefined and len(layer.valid_times) > 0:
                available_times.update(layer.valid_times)

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
        if crs is None or crs.lower() == "crs:84":
            return settings.crs_84_pyproj_format  # Pyproj acceptable format

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
        if crs.lower() == "epsg:4326":
            return (y, x)

        return (x, y)

    @staticmethod
    def interpret_altitude_coordinates(
        available_altitudes: List[float], altitude_string: str | None, crs: str | None
    ) -> podpac.Coordinates | None:
        """Interpret the string into altitude coordinates using known formats.

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
            Altitude coordinates for the request or None if conversion fails.
        """
        if not altitude_string or len(available_altitudes) == 0:
            return None

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
            return None

        return podpac.Coordinates([altitudes], dims=["alt"], crs=crs) if altitudes is not None else None

    @staticmethod
    def interpret_time_coordinates(
        available_times: List[str], time_string: str | None, crs: str | None
    ) -> podpac.Coordinates | None:
        """Interpret the string into a list of times using known formats.

        Specification:
        interval-closed     = date-time "/" date-time
        interval-open-start = "../" date-time
        interval-open-end   = date-time "/.."
        interval            = interval-closed / interval-open-start / interval-open-end
        datetime            = date-time / interval

        Parameters
        ----------
        available_times: List[str]
            The available times for interpretation.
        time_string : str | None
            The string representation of the requested times.
        crs : str
            The CRS that the coordinates need to match.

        Returns
        -------
        podpac.Coordinates | None
            Time coordinates for the request or None if conversion fails.
        """

        if not time_string or len(available_times) == 0:
            return None

        try:
            times = None
            np_available_times = [np.datetime64(time) for time in available_times]
            if "/" in time_string:
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
            return None

        return podpac.Coordinates([times], dims=["time"], crs=crs) if times is not None else None

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
                        "coordinates": ["lon", "lat"],
                        "system": {"type": "GeographicCRS", "id": crs},
                    },
                    {
                        "coordinates": ["t"],
                        "system": {
                            "type": "TemporalRS",
                            "calendar": "Gregorian",
                        },
                    },
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
            layer = next(layer for layer in layers if layer.identifier == param)
            units = layer.node.units if layer.node.units is not None else layer.node.style.units
            parameter_definition = {
                param: {
                    "type": "Parameter",
                    "observedProperty": {
                        "id": param,
                        "label": layer.title,
                        "description": {
                            "en": layer.abstract,
                        },
                    },
                    "unit": {
                        "label": {"en": units},
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
        source_time_instance: np.datetime64 | None,
    ) -> podpac.Coordinates:
        """Find the intersecting latitude and longitude coordinates between the source and target.
        Convert time instances to stacked time and forecast offsets for node evalutation.

        Parameters
        ----------
        source_coordinates : podpac.Coordinates
            The source coordinates to be converted.
        target_coordinates : podpac.Coordinates
            The target coordinates to find intersections on.
        source_time_instance : np.datetime64 | None
            The time instance of the source coordinates to convert to offsets.

        Returns
        -------
        podpac.Coordinates
            The converted coordinates source coordinates intersecting with the target coordinates.
        """
        # Find intersections with target keeping source crs
        source_intersection_coordinates = target_coordinates.intersect(source_coordinates, dims=["lat", "lon"])
        source_intersection_coordinates = source_intersection_coordinates.transform(source_coordinates.crs)
        # Handle conversion from times and instance to time and offsets
        if (
            "forecastOffsetHr" in target_coordinates.udims
            and "time" in target_coordinates.udims
            and "time" in source_coordinates.udims
            and source_time_instance is not None
        ):
            time_deltas = []
            for time in source_coordinates["time"].coordinates:
                offset = np.timedelta64(time - source_time_instance, "h")
                time_deltas.append(offset)

            # This modifies the time coordinates to account for the new forecast offset hour
            new_coordinates = podpac.Coordinates(
                [[[source_time_instance] * len(time_deltas), time_deltas]],
                [["time", "forecastOffsetHr"]],
                crs=source_coordinates.crs,
            )
            source_intersection_coordinates = podpac.coordinates.merge_dims(
                [source_intersection_coordinates.udrop(["time", "forecastOffsetHr"]), new_coordinates]
            )

        return source_intersection_coordinates
