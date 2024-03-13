"""
DOCUMENTATION FOR THE PROJECT MODULE

Currently holds some definitions for interface classes.
"""
import gc
import logging
import traitlets as tl

from . import settings
from . import wcs_request_1_0_0
from . import wms_request_1_3_0
from . import wcs_response_1_0_0
from . import wms_response_1_3_0
from . import ogc_common

from ogc.ogc_common import WCSException

logger = logging.getLogger(__name__)

class OGC(tl.HasTraits):

    wms_capabilities = tl.Instance(klass=wms_response_1_3_0.Capabilities)
    wcs_capabilities = tl.Instance(klass=wcs_response_1_0_0.Capabilities)

    endpoint = tl.Unicode(default_value="/ogc", allow_none=True)
    service_title = tl.Unicode(default_value="OGC Server", allow_none=True)
    service_abstract = tl.Unicode(
        default_value="An example OGC Server", allow_none=True
    )
    server_address = tl.Unicode(default_value="http://127.0.0.1:5000", allow_none=True)
    service_group_title = tl.Unicode(default_value="Data Products", allow_none=True)

    @property
    def base_url(self):
        return "{}{}?".format(self.server_address, self.endpoint)

    def __init__(self, layers=[], **kwargs):
        super().__init__(**kwargs)
        coverages = [
            wcs_response_1_0_0.Coverage(
                layer=layer,
                title=layer.title,
                abstract=layer.abstract,
                identifier=layer.id_str,
            )
            for layer in layers
        ]
        self.wcs_capabilities = wcs_response_1_0_0.Capabilities(
            coverages=coverages,
            base_url=self.base_url,
            service_title=self.service_title,
            service_abstract=self.service_abstract,
        )
        self.wms_capabilities = wms_response_1_3_0.Capabilities(
            coverages=coverages,
            base_url=self.base_url,
            service_title=self.service_title,
            service_abstract=self.service_abstract,
            service_group_title=self.service_group_title,
        )
        return

    def get_coverage_from_id(self, identifier):
        for coverage in self.wcs_capabilities.coverages:
            if coverage.identifier == identifier:
                return coverage
        raise WCSException(
            exception_code="InvalidParameterValue",
            locator="COVERAGE",
            exception_text="Invalid coverage {}".format(identifier),
        )

    def handle_wcs_kv(self, args):
        if args["request"] == "GetCapabilities":
            get_capabilities = wcs_request_1_0_0.GetCapabilities()
            try:
                get_capabilities.load_from_kv(args)
                get_capabilities.validate()
            except: 
                logger.error("Failed to load and validate: ", exc_info=True)
                raise WCSException(exception_text="Invalid arguments")

            capabilities = self.wcs_capabilities

            if args["base_url"]:
                capabilities.base_url = args["base_url"]

            return capabilities.to_xml()

        if "version" in args["version"] == "1.0.0":
            wcs_response = wcs_response_1_0_0
            wcs_request = wcs_request_1_0_0
        else:
            raise WCSException(
                exception_code="InvalidParameterValue",
                locator="VERSION",
                exception_text="Unsupported version: %s" % (args["version"] if "version" in args else "None"),
            )

        if args["request"] == "DescribeCoverage":

            describe_coverage = wcs_request.DescribeCoverage()
            try:
                describe_coverage.load_from_kv(args)
                describe_coverage.validate()
            except: 
                logger.error("Failed to load and validate: ", exc_info=True)
                raise WCSException(exception_text="Invalid arguments")

            coverages = [
                self.get_coverage_from_id(identifier.value)
                for identifier in describe_coverage.identifiers
            ]
            coverage_description = wcs_response.CoverageDescription(coverages=coverages)

            return coverage_description.to_xml()

        elif args["request"] == "GetCoverage":
            get_coverage = wcs_request.GetCoverage()
            try:
                get_coverage.load_from_kv(args)
                get_coverage.validate()
            except: 
                logger.error("Failed to load and validate: ", exc_info=True)
                raise WCSException(exception_text="Invalid arguments")

            coverage = self.get_coverage_from_id(get_coverage.identifier.value)

            from dateutil.parser import parse


            if get_coverage.width == 0:
                raise WCSException(
                    exception_code="InvalidParameterValue",
                    locator="VERSION",
                    exception_text="Grid coordinates x_size must be greater than 0",
                )
            if get_coverage.height == 0:
                raise WCSException(
                    exception_code="InvalidParameterValue",
                    locator="VERSION",
                    exception_text="Grid coordinates y_size must be greater than 0",
                )
            if get_coverage.height * get_coverage.width > settings.MAX_GRID_COORDS_REQUEST_SIZE:
                raise WCSException(
                    exception_code="InvalidParameterValue",
                    locator="VERSION",
                    exception_text="Grid coordinates x_size * y_size must be less than %d" % settings.MAX_GRID_COORDS_REQUEST_SIZE,
                )


            fp = coverage.layer.get_coverage(args)

            fn = coverage.identifier.split(".")[-1] + ".tif"

            # Collect garbage
            gc.collect()

            response = {"fp": fp, "fn": fn}

            return response

        raise WCSException(
            exception_text="KV Request not handled properly: " + str(args)
        )

    def handle_wms_kv(self, args):
        if args["request"] == "GetCapabilities":
            get_capabilities = wms_request_1_3_0.GetCapabilities()
            try:
                get_capabilities.load_from_kv(args)
                get_capabilities.validate()
            except: 
                logger.error("Failed to load and validate: ", exc_info=True)
                raise WCSException(exception_text="Invalid arguments")

            wms_capabilities = self.wms_capabilities

            if args["base_url"]:
                wms_capabilities.base_url = args["base_url"]
            return wms_capabilities.to_xml()

        if args["request"] == "GetFeatureInfo":
            raise WCSException(
                exception_code="OperationNotSupported",
                locator="REQUEST",
                exception_text="Unsupported request",
            )

        if "version" in args and args["version"] == "1.3.0":
            wms_request = wms_request_1_3_0
        else:
            raise WCSException(
                exception_code="InvalidParameterValue",
                locator="VERSION",
                exception_text="Unsupported version: %s" % (args["version"] if "version" in args else "None"),
            )

        if args["request"].lower() == "getlegendgraphic":
            get_legend_graphic = wms_request.GetLegendGraphic()
            try:
                get_legend_graphic.load_from_kv(args)
                get_legend_graphic.validate()
            except: 
                logger.error("Failed to load and validate: ", exc_info=True)
                raise WCSException(exception_text="Invalid arguments")

            coverage = self.get_coverage_from_id(get_legend_graphic.layer.value)

            fp = coverage.layer.get_legend_graphic(args)

            fn = coverage.identifier.split(".")[-1] + ".png"

            response = {"fp": fp, "fn": fn}
            return response

        if args["request"].lower() == "getmap":

            get_map = wms_request.GetMap()
            try:
                get_map.load_from_kv(args)
                get_map.validate()
            except: 
                logger.error("Failed to load and validate: ", exc_info=True)
                raise WCSException(exception_text="Invalid arguments")

            coverage = self.get_coverage_from_id(get_map.layer.value)

            # Make sure the request size is correct
            if get_map.width == 0:
                raise WCSException(
                    exception_code="InvalidParameterValue",
                    locator="VERSION",
                    exception_text="Grid coordinates x_size must be greater than 0",
                )
            if get_map.height == 0:
                raise WCSException(
                    exception_code="InvalidParameterValue",
                    locator="VERSION",
                    exception_text="Grid coordinates y_size must be greater than 0",
                )
            if get_map.height * get_map.width > settings.MAX_GRID_COORDS_REQUEST_SIZE:
                raise WCSException(
                    exception_code="InvalidParameterValue",
                    locator="VERSION",
                    exception_text="Grid coordinates x_size * y_size must be less than %d" % settings.MAX_GRID_COORDS_REQUEST_SIZE,
                )

            try:
                fp = coverage.layer.get_map(args)
            except: 
                logger.error("Failed to get_map from layer: ", exc_info=True)
                raise WCSException(exception_text="Invalid arguments")

            fn = coverage.identifier.split(".")[-1] + ".png"

            # Collect garbage
            gc.collect()

            response = {"fp": fp, "fn": fn}

            return response

        raise WCSException(
            exception_text="KV Request not handled properly: " + str(args)
        )
