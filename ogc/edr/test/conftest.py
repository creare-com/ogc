import pytest
import numpy as np
import datetime
import podpac
from ogc import podpac as pogc
from typing import Dict, List, Any

lat = np.linspace(90, -90, 11)
lon = np.linspace(-180, 180, 21)
time = np.array(["2025-10-24T12:00:00"], dtype="datetime64")
data = np.random.default_rng(1).random((11, 21, 1))
coords = podpac.Coordinates([lat, lon, time], dims=["lat", "lon", "time"])

# Define test layers using sample data and coordinates
node1 = podpac.data.Array(source=data, coordinates=coords)
layer1 = pogc.Layer(
    node=node1,
    identifier="layer1",
    title="Layer 1",
    abstract="Layer1 Data",
    group="Layers",
    time_instances=[str(t) for t in coords["time"].coordinates],
    valid_times=[dt.astype(datetime.datetime) for dt in time],
)
node2 = podpac.data.Array(source=data, coordinates=coords)
layer2 = pogc.Layer(
    node=node2,
    identifier="layer2",
    title="Layer 2",
    abstract="Layer2 Data",
    group="Layers",
    time_instances=[str(t) for t in coords["time"].coordinates],
    valid_times=[dt.astype(datetime.datetime) for dt in time],
)


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
def single_layer_cube_args() -> Dict[str, Any]:
    """Dictionary of valid request arguments that align to a single test layer cube request.

    Returns
    -------
    Dict[str, Any]
        Valid cube request arguments for a single test layer.
    """

    return {
        "f": "json",
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
        "format_": "json",
        "bbox": [-180, -90, 180, 90],
        "datetime_": str(time[0]),
        "select_properties": [layer1.identifier],
    }
