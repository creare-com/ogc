import pytest
import podpac
import numpy as np
import importlib
from typing import List
from ogc import settings
from unittest.mock import patch
from ogc import podpac as pogc
from ogc.wms_response_1_3_0 import Coverage

# Create some podpac nodes
lat = np.linspace(90, -90, 11)
lon = np.linspace(-180, 180, 21)
time = np.array(["2025-10-24T12:00:00"], dtype="datetime64")
data = np.random.default_rng(1).random((11, 21, 1))
coords = podpac.Coordinates([lat, lon, time], dims=["lat", "lon", "time"])
node1 = podpac.data.Array(source=data, coordinates=coords).interpolate()
node2 = podpac.data.Array(source=data, coordinates=coords).interpolate()

# Use podpac nodes to create some test OGC layers
layer1 = pogc.Layer(
    node=node1,
    identifier="layer1",
    title="Layer 1",
    abstract="Layer1 Data",
    group="Layers",
)

layer2 = pogc.Layer(
    node=node2,
    identifier="layer2",
    title="Layer 2",
    abstract="Layer2 Data",
    group="Layers",
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
def coverages() -> List[Coverage]:
    """List of coverages based on layers.

    Returns
    -------
    List[Coverage]
        The test coverages.
    """
    return [
        Coverage(
            layer=layer,
            title=layer.title,
            abstract=layer.abstract,
            identifier=layer.id_str,
        )
        for layer in [layer1, layer2]
    ]


@pytest.fixture(scope="module", autouse=True)
def set_env_vars():
    """Setup the environmental variables for the module to support WMTS."""
    with patch.dict("os.environ", {"OGC_SUPPORTED_FORMATS": "wmts"}):
        importlib.reload(settings)
        yield

    # Fix imports after patching for test
    importlib.reload(settings)
