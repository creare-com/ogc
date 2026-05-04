import traitlets as tl
import logging
import gc
from typing import Dict, Any

from ogc.ogc_common import WMTSException
from ogc.wcs_response_1_0_0 import Coverage

from . import wmts_response_1_0_0
from . import wmts_request_1_0_0

LOAD_FAILURE = "Failed to load and validate: "
INVALID_ARGUMENTS = "Invalid arguments"

logger = logging.getLogger(__name__)


class WmtsRoutes(tl.HasTraits):
    """Class responsible for WMTS requests."""

    coverages = tl.List(trait=tl.Instance(klass=Coverage))
    base_url = tl.Unicode(default_value=None, allow_none=True)
    service_title = tl.Unicode(default_value=None, allow_none=True)
    service_abstract = tl.Unicode(default_value=None, allow_none=True)
    service_group_title = tl.Unicode(default_value=None, allow_none=True)

    def __init__(self, **kwargs):
        """Initialize the capabilities for the WMTS endpoints."""
        super().__init__(**kwargs)
        self.capabilities = wmts_response_1_0_0.Capabilities(
            coverages=self.coverages,
            base_url=self.base_url,
            service_title=self.service_title,
            service_abstract=self.service_abstract,
            service_group_title=self.service_group_title,
        )

    def handle_kv(self, args: Dict[str, Any]) -> Dict[str, Any] | str:
        """Handle WMTS key value requests.

        Parameters
        ----------
        args : Dict[str, Any]
            The filtered request arguments.

        Returns
        -------
        Dict[str, Any] | str
            A dictionary containing the tile response or a string of service metadata.

        Raises
        ------
        WMTSException
            Exception for unsupported get feature info request.
        WMTSException
            Exception for invalid parameter value in the request arguments.
        WMTSException
            Exception for unsupported request argument.
        """
        if args["request"] == "GetCapabilities":
            return self.get_capabilities(args)

        if args["request"] == "GetFeatureInfo":
            raise WMTSException(
                exception_code="OperationNotSupported",
                locator="REQUEST",
                exception_text="Unsupported request",
            )

        if "version" in args and args["version"] == "1.0.0":
            wmts_request = wmts_request_1_0_0
        else:
            raise WMTSException(
                exception_code="InvalidParameterValue",
                locator="VERSION",
                exception_text="Unsupported version: %s" % (args["version"] if "version" in args else "None"),
            )

        if args["request"].lower() == "gettile":
            return self.get_tile(args, wmts_request)

        raise WMTSException(exception_text="KV Request not handled properly: " + str(args))

    def get_coverage_from_id(self, identifier: str) -> Coverage:
        """Find the coverage for a given identifier.

        Parameters
        ----------
        identifier : str
            The coverage identifier.

        Returns
        -------
        Coverage
            The coverage matching the provided identifier.

        Raises
        ------
        WMTSException
            Exception for an invalid coverage identifier.
        """
        for coverage in self.coverages:
            if coverage.identifier == identifier:
                return coverage
        raise WMTSException(
            exception_code="InvalidParameterValue",
            locator="COVERAGE",
            exception_text="Invalid coverage {}".format(identifier),
        )

    def get_capabilities(self, args: Dict[str, Any]) -> str:
        """Get capabilities for the WMTS server.

        Parameters
        ----------
        args : Dict[str, Any]
           The filtered request arguments.

        Returns
        -------
        str
            The xml response as a string.

        Raises
        ------
        WMTSException
            Exception for invalid arguments found during validation.
        """
        get_capabilities = wmts_request_1_0_0.GetCapabilities()
        try:
            get_capabilities.load_from_kv(args)
            get_capabilities.validate()
        except AssertionError:
            logger.error(LOAD_FAILURE, exc_info=True)
            raise WMTSException(exception_text=INVALID_ARGUMENTS)

        if args["base_url"]:
            self.base_url = args["base_url"]
            self.capabilities.base_url = args["base_url"]

        return self.capabilities.to_xml()

    def get_tile(self, args: Dict[str, Any], wmts_request: Any) -> Dict[str, Any]:
        """Retrieve a tile using the requested arguments.

        Parameters
        ----------
        args : Dict[str, Any]
            The filtered request arguments.
        wmts_request : Any
            The request module used to retrieve the tile for a specific WMTS version.

        Returns
        -------
        Dict[str, Any]
            A dictionary containing the tile response.

        Raises
        ------
        WMTSException
            Exception for invalid arguments found during validation.
        WMTSException
            Exception for errors found during the layer evaluation.
        """
        get_tile = wmts_request.GetTile()
        try:
            get_tile.load_from_kv(args)
            get_tile.validate()
        except AssertionError:
            logger.error(LOAD_FAILURE, exc_info=True)
            raise WMTSException(exception_text=INVALID_ARGUMENTS)

        coverage = self.get_coverage_from_id(get_tile.layer.value)
        map_args = get_tile.convert_to_map_args()

        try:
            fp = coverage.layer.get_map(map_args)
        except Exception:
            logger.error("Failed to get_tile from layer: ", exc_info=True)
            raise WMTSException(exception_text=INVALID_ARGUMENTS)

        fn = coverage.identifier.split(".")[-1] + ".png"

        # Collect garbage
        gc.collect()

        response = {"fp": fp, "fn": fn}

        return response
