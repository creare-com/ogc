import base64
import io
import numpy as np
import zipfile
import traitlets as tl
from datetime import datetime
from typing import List, Dict, Tuple, Any
from shapely.geometry.base import BaseGeometry
from pygeoapi.provider.base import ProviderConnectionError, ProviderInvalidQueryError
from pygeoapi.provider.base_edr import BaseEDRProvider
from ogc import podpac as pogc
import podpac

from .. import settings


class EdrProvider(BaseEDRProvider):
    """Custom provider to be used with layer data sources."""

    layers = []
    forecast_time_delta_units = tl.Unicode(default_value="h")

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
            Raised if the provider does not specify any data sources.
        """
        super().__init__(provider_def)
        collection_id = provider_def.get("data", None)
        if collection_id is None:
            raise ProviderConnectionError("Data not found.")

        self.collection_id = str(collection_id)

        if len(self.layers) == 0:
            raise ProviderConnectionError("Valid data sources not found.")

    @classmethod
    def set_resources(cls, layers: List[pogc.Layer]):
        """Set the layer resources which will be available to the provider.

        Parameters
        ----------
        layers : List[pogc.Layer]
            The layers which the provider will have access to.
        """
        cls.layers = layers

    @property
    def parameters(self) -> Dict[str, pogc.Layer]:
        """The parameters which are defined in a given collection.

        The parameters map to the layers which are a part of the group, with keys of the layer identifiers.

        Returns
        -------
        Dict[str, pogc.Layer]
            The parameters as a dictionary of layer identifiers and layer objects.
        """
        return {layer.identifier: layer for layer in self.layers if layer.group == self.collection_id}

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
            Raised if the parameters are invalid.
        ProviderInvalidQueryError
            Raised if a datetime string is provided but cannot be interpreted.
        ProviderInvalidQueryError
            Raised if an altitude string is provided but cannot be interpreted.
        ProviderInvalidQueryError
            Raised if no matching parameters are found in the server.
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

        if not isinstance(requested_parameters, List) or len(requested_parameters) == 0:
            raise ProviderInvalidQueryError("Invalid parameters provided.")

        available_times = self.get_datetimes(list(self.parameters.values()))
        available_altitudes = self.get_altitudes(list(self.parameters.values()))
        time_coords = self.interpret_time_coordinates(available_times, datetime_arg, requested_coordinates.crs)
        altitude_coords = self.interpret_altitude_coordinates(available_altitudes, z_arg, requested_coordinates.crs)

        if datetime_arg is not None and time_coords is None:
            raise ProviderInvalidQueryError("Invalid datetime provided.")
        if z_arg is not None and altitude_coords is None:
            raise ProviderInvalidQueryError("Invalid altitude provided.")

        if time_coords is not None:
            requested_coordinates = podpac.coordinates.merge_dims([time_coords, requested_coordinates])
        if altitude_coords is not None:
            requested_coordinates = podpac.coordinates.merge_dims([altitude_coords, requested_coordinates])

        instance_time = None
        if instance is not None:
            try:
                # Check if it can be formatted as a datetime before adding to requested coordinates
                instance_time = np.datetime64(instance)
            except ValueError:
                raise ProviderInvalidQueryError("Invalid instance time provided.")

        dataset = {}
        native_coordinates = None

        # Allow parameters without case-sensitivity
        parameters_lower = [param.lower() for param in requested_parameters]
        parameters_filtered = [key for key in self.parameters.keys() if key.lower() in parameters_lower]

        for requested_parameter in parameters_filtered:
            layer = self.parameters.get(requested_parameter, None)
            if layer is not None:
                # Handle defining native coordinates for the query, these should match between each layer
                if native_coordinates is None:
                    coordinates_list = layer.node.find_coordinates()

                    if len(coordinates_list) == 0:
                        raise ProviderInvalidQueryError("Native coordinates not found.")

                    native_coordinates = requested_coordinates

                    if (
                        len(requested_coordinates["lat"].coordinates) > 1
                        or len(requested_coordinates["lon"].coordinates) > 1
                    ):
                        native_coordinates = coordinates_list[0].intersect(requested_coordinates)
                        native_coordinates = native_coordinates.transform(requested_coordinates.crs)

                    if native_coordinates.size > settings.MAX_GRID_COORDS_REQUEST_SIZE:
                        raise ProviderInvalidQueryError(
                            "Grid coordinates x_size * y_size must be less than %d"
                            % settings.MAX_GRID_COORDS_REQUEST_SIZE
                        )

                    if (
                        "forecastOffsetHr" in coordinates_list[0].udims
                        and "time" in native_coordinates.udims
                        and instance_time is not None
                    ):
                        time_deltas = []
                        for time in native_coordinates["time"].coordinates:
                            offset = np.timedelta64(time - instance_time, self.forecast_time_delta_units)
                            time_deltas.append(offset)

                        # This modifies the time coordinates to account for the new forecast offset hour
                        new_coordinates = podpac.Coordinates(
                            [[instance_time], time_deltas],
                            ["time", "forecastOffsetHr"],
                            crs=native_coordinates.crs,
                        )
                        native_coordinates = podpac.coordinates.merge_dims(
                            [native_coordinates.drop("time"), new_coordinates]
                        )

                units_data_array = layer.node.eval(native_coordinates)
                dataset[requested_parameter] = units_data_array

        if len(dataset) == 0:
            raise ProviderInvalidQueryError("No matching parameters found.")

        # Return a coverage json if specified, else return Base64 encoded native response
        if output_format == "json" or output_format == "coveragejson":
            crs = self.interpret_crs(native_coordinates.crs if native_coordinates else None)
            return self.to_coverage_json(self.layers, dataset, crs)
        else:
            if len(dataset) == 1:
                geotiff_bytes = units_data_array.to_format("geotiff").read()
                units_data_array = next(iter(dataset.values()))
                return {
                    "fp": base64.b64encode(geotiff_bytes).decode("utf-8"),
                    "fn": f"{ next(iter(dataset.keys()))}.tif",
                }
            else:
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                    for parameter, data_array in dataset.items():
                        geotiff_memory_file = data_array.to_format("geotiff")
                        tiff_filename = f"{parameter}.tif"
                        zip_file.writestr(tiff_filename, geotiff_memory_file.read())

                zip_buffer.seek(0)
                return {"fp": base64.b64encode(zip_buffer.read()).decode("utf-8"), "fn": f"{self.collection_id}.zip"}

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
            raise ProviderInvalidQueryError("Invalid wkt provided.")
        elif wkt.geom_type == "Point":
            lon, lat = EdrProvider.crs_converter([wkt.x], [wkt.y], crs)
        else:
            raise ProviderInvalidQueryError("Unknown WKT Type (Use Point).")

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
            raise ProviderInvalidQueryError("Invalid bounding box provided.")

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
            raise ProviderInvalidQueryError("Invalid wkt provided.")
        elif wkt.geom_type == "Polygon":
            lon, lat = EdrProvider.crs_converter(wkt.exterior.xy[0], wkt.exterior.xy[1], crs)
        else:
            raise ProviderInvalidQueryError("Unknown WKT Type (Use Polygon).")

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
        for layer in self.layers:
            if layer.group == self.collection_id and layer.time_instances is not None:
                instances.update(layer.time_instances)
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
                available_altitudes.update(coordinates_list[0]["alt"])

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

        If None provided or the CRS is unknown, return the default.

        Parameters
        ----------
        crs : str
            The input CRS id string which needs to be validated/converted.

        Returns
        -------
        str
            Pyproj CRS string.
        """
        default_crs = "urn:ogc:def:crs:OGC:1.3:CRS84"  # Pyproj acceptable format
        if crs is None or crs.lower() == "crs:84" or crs.lower() not in settings.EDR_CRS.keys():
            return default_crs

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

        coverage_json = {
            "type": "Coverage",
            "domain": {
                "type": "Domain",
                "domainType": "Grid",
                "axes": {
                    "x": {
                        "start": x_arr[0],
                        "stop": x_arr[-1],
                        "num": len(x_arr),
                    },
                    "y": {
                        "start": y_arr[0],
                        "stop": y_arr[-1],
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
