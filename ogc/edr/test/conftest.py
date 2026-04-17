import os
import pytest
import numpy as np
import datetime
import podpac
from ogc import podpac as pogc
from typing import Dict, List, Any

# Setup new dimension
podpac.core.coordinates.utils.add_valid_dimension("forecastOffsetHr")

lat = np.linspace(90, -90, 11)
lon = np.linspace(-180, 180, 21)
time = np.array(["2025-10-24T12:00:00"], dtype="datetime64")
offsets = [np.timedelta64(0, "h")]
data = np.random.default_rng(1).random((11, 21, 1, 1))
coords = podpac.Coordinates([lat, lon, time, offsets], dims=["lat", "lon", "time", "forecastOffsetHr"])

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


@pytest.fixture(scope="session", autouse=True)
def set_env_vars():
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
        "instance": str(time[0]),
        "bbox": [-180, -90, 180, 90],
        "datetime_": str(time[0]),
        "select_properties": [layer1.identifier],
    }
