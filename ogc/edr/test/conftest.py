import os
import pytest
import numpy as np
import datetime
import podpac
from ogc import podpac as pogc
from typing import Dict, List, Any
from ogc.settings import EDR_TIME_INSTANCE_DIMENSION

# Setup new dimension
podpac.core.coordinates.utils.add_valid_dimension(EDR_TIME_INSTANCE_DIMENSION)

lat = np.linspace(90, -90, 11)
lon = np.linspace(-180, 180, 21)
time = np.array(["2025-10-24T12:00:00"], dtype="datetime64")
instance = np.array(["2025-10-24T00:00:00"], dtype="datetime64")
data = np.random.default_rng(1).random((11, 21, 1, 1))
coords = podpac.Coordinates([lat, lon, time, instance], dims=["lat", "lon", "time", EDR_TIME_INSTANCE_DIMENSION])
data_without_instance = np.random.default_rng(1).random((11, 21, 1))
coords_without_instance = podpac.Coordinates([lat, lon, time], dims=["lat", "lon", "time"])

# Define test layers using sample data and coordinates
node1 = podpac.data.Array(source=data, coordinates=coords)
layer1 = pogc.Layer(
    node=node1,
    identifier="layer1",
    title="Layer 1",
    abstract="Layer1 Data",
    group="Layers",
    valid_times=[dt.astype(datetime.datetime) for dt in time],
)
node2 = podpac.data.Array(source=data, coordinates=coords)
layer2 = pogc.Layer(
    node=node2,
    identifier="layer2",
    title="Layer 2",
    abstract="Layer2 Data",
    group="Layers",
    valid_times=[dt.astype(datetime.datetime) for dt in time],
)
node3 = podpac.data.Array(source=data_without_instance, coordinates=coords_without_instance)
layer3 = pogc.Layer(
    node=node3,
    identifier="layer3",
    title="Layer 3",
    abstract="Layer3 Data (No instance)",
    group="Layers",
    valid_times=[dt.astype(datetime.datetime) for dt in time],
)


@pytest.fixture(scope="session", autouse=True)
def set_env_vars():
    """Setup the environmental variables for the session to support EDR."""
    os.environ["OGC_SUPPORTED_FORMATS"] = "edr"


@pytest.fixture()
def layers() -> List[pogc.Layer]:
    """List of test layers.

    Returns
    -------
    List[pogc.Layer]
        The test layers.
    """
    return [layer1, layer2]


@pytest.fixture()
def layers_no_instance() -> List[pogc.Layer]:
    """List of test layers without instances.

    Returns
    -------
    List[pogc.Layer]
        The test layers.
    """
    return [layer3]


@pytest.fixture()
def single_layer_cube_args() -> Dict[str, Any]:
    """Dictionary of valid request arguments that align to a single test layer cube request.

    Returns
    -------
    Dict[str, Any]
        Valid cube request arguments for a single test layer.
    """

    return {
        "f": "coveragejson",
        "bbox": "-180, -90, 180, 90",
        "datetime": str(time[0]),
        "parameter-name": [layer1.identifier],
    }


@pytest.fixture()
def single_layer_cube_args_internal() -> Dict[str, Any]:
    """Dictionary of valid arguments that align to a single test layer request with internal pygeoapi keys.

    Returns
    -------
    Dict[str, Any]
        Valid internal cube arguments for a single test layer.
    """

    return {
        "format_": "coveragejson",
        "instance": str(instance[0]),
        "bbox": [-180, -90, 180, 90],
        "datetime_": str(time[0]),
        "select_properties": [layer1.identifier],
    }


@pytest.fixture()
def single_layer_cube_args_no_instance_internal() -> Dict[str, Any]:
    """Dictionary of valid arguments that align to a single non-instance test layer request with internal pygeoapi keys.

    Returns
    -------
    Dict[str, Any]
        Valid internal cube arguments for a single non-instance test layer.
    """

    return {
        "format_": "coveragejson",
        "bbox": [-180, -90, 180, 90],
        "datetime_": str(time[0]),
        "select_properties": [layer3.identifier],
    }
