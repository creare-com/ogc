from typing import Dict, List, Any
from ogc import podpac as pogc
from ogc.edr.edr_config import EdrConfig


def test_edr_default_configuration_has_required_keys():
    """Test the EDR default configuration loads the required keys."""
    configuration = EdrConfig.get_configuration("/ogc", [])

    assert configuration.keys() == {"server", "logging", "metadata", "resources"}


def test_edr_configuration_contains_layer_groups(layers: List[pogc.Layer]):
    """Test the EDR configuration contains the layer groups.

    Parameters
    ----------
    layers : List[pogc.Layer]
        Layers provided by a test fixture.
    """
    group_keys = {layer.group for layer in layers}
    configuration = EdrConfig.get_configuration("/ogc", layers)

    assert len(group_keys) > 0
    for key in group_keys:
        assert configuration["resources"].get(key) is not None


def test_edr_configuration_contains_spatial_extent(layers: List[pogc.Layer], single_layer_cube_args: Dict[str, Any]):
    """Test the EDR configuration contains the spatial extent.

    Parameters
    ----------
    layers : List[pogc.Layer]
        Layers provided by a test fixture.

    single_layer_cube_args : Dict[str, Any]
        Single layer arguments for validation checking provided by a test fixture.
    """
    group_keys = {layer.group for layer in layers}
    configuration = EdrConfig.get_configuration("/ogc", layers)

    assert len(group_keys) > 0
    for key in group_keys:
        assert configuration["resources"][key]["extents"]["spatial"]["bbox"] == list(
            map(float, single_layer_cube_args["bbox"].split(","))
        )


def test_edr_configuration_contains_custom_provider(layers: List[pogc.Layer]):
    """Test the EDR configuration contains the custom provider.

    Parameters
    ----------
    layers : List[pogc.Layer]
        Layers provided by a test fixture.
    """
    group_keys = {layer.group for layer in layers}
    configuration = EdrConfig.get_configuration("/ogc", layers)

    assert len(group_keys) > 0
    for key in group_keys:
        assert configuration["resources"][key]["providers"][0]["type"] == "edr"
        assert configuration["resources"][key]["providers"][0]["name"] == "ogc.edr.edr_provider.EdrProvider"
