import pytest
import importlib
from unittest.mock import patch
from ogc import settings


@pytest.fixture(scope="module", autouse=True)
def set_env_vars():
    """Setup the environmental variables for the module to support WMS and WCS."""
    with patch.dict("os.environ", {"OGC_SUPPORTED_FORMATS": "wms,wcs"}):
        importlib.reload(settings)
        yield

    # Fix imports after patching for test
    importlib.reload(settings)
