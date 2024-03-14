"""
This holds classes integrating ogc.OGC with popular web frameworks.

Note: this should probably be seperated into sub-modules for each web
      framework so that one web framework isn't a dependency for using
      another one.
"""

import re
from flask import Flask, request, Response, make_response, send_file
import six
import traceback
import logging

from ogc.ogc_common import WCSException

logger = logging.getLogger(__name__)


def respond_xml(doc, status=200):
    # First, validate that XML can be parsed.
    from lxml import etree

    root = etree.fromstring(doc.encode("ascii"))
    # Then, return w/ proper content type
    return Response(doc, mimetype="text/xml", status=status)


def home(endpoint):
    """Example API home page. Developers should make their own page similar to this one."""
    test_layer = "testLayerName"
    test_layer_time = "12:59:59"  # HH:MM:SS
    return f"""<h2> OGC Server API </h2>
    <p>This is the API endpoint served at {endpoint}. Add example usage here for your users.</p>

    <ul>
        <li> WCS: Open Geospatial Consortium (OGC) Web Coverage Service (WCS) <i>(v1.0.0)</i>
        <ul>
            <li><a href="?SERVICE=WCS&REQUEST=GetCapabilities&VERSION=1.0.0">WCS GetCapabilities (XML)</a> <i>(v1.0.0)</i></li>
            <li><a href="?SERVICE=WCS&REQUEST=DescribeCoverage&VERSION=1.0.0&COVERAGE={test_layer}">WCS DescribeCoverage Example (XML)</a> <i>(v1.0.0)</i></li>
            <li><a href="?SERVICE=WCS&VERSION=1.0.0&REQUEST=GetCoverage&FORMAT=GeoTIFF&COVERAGE={test_layer}&BBOX=-132.90225856307210961,23.62932030249929483,-53.60509752693091912,53.75883389158821046&CRS=EPSG:4326&RESPONSE_CRS=EPSG:4326&WIDTH=346&HEIGHT=131">WCS GetCoverage Example (GeoTIFF)</a> <i>(v1.0.0)</i></li>
            <li><a href="?SERVICE=WCS&VERSION=1.0.0&REQUEST=GetCoverage&FORMAT=GeoTIFF&COVERAGE={test_layer_time}&BBOX=34.3952751159668,38.26394082159894,34.398660063743584,38.26779045113519&CRS=EPSG:4326&RESPONSE_CRS=EPSG:4326&WIDTH=631&HEIGHT=914&TIME=2021-03-01T12:00:00.000Z">WCS GetCoverage Example (GeoTIFF)</a> dynamic layer <i>(v1.0.0)</i></li>
        </ul>
        </li>
        <li> WMS: Open Geospatial Consortium (OGC) Web Map Service (WMS) <i>(v1.3.0)</i>
        <ul>
            <li><a href="?SERVICE=WMS&REQUEST=GetCapabilities&VERSION=1.3.0">WMS GetCapabilities (XML)</a> <i>(v1.3.0)</i></li>
            <li><a href="?SERVICE=WMS&REQUEST=GetMap&VERSION=1.3.0&LAYERS={test_layer}&STYLES=&FORMAT=image%2Fpng&TRANSPARENT=true&HEIGHT=256&WIDTH=256&CRS=EPSG%3A3857&BBOX=-10018754.171394622,2504688.5428486555,-7514065.628545966,5009377.08569731">WMS GetMap Example (PNG)</a> <i>(v1.3.0)</i></li>
            <li><a href="?SERVICE=WMS&REQUEST=GetMap&VERSION=1.3.0&LAYERS={test_layer_time}&STYLES=&FORMAT=image%2Fpng&TRANSPARENT=true&HEIGHT=256&WIDTH=256&CRS=EPSG%3A3857&BBOX=-10018754.171394622,2504688.5428486555,-7514065.628545966,5009377.08569731&TIME=2021-03-01T12:00:00.000Z">WMS GetMap Example (PNG)</a> dynamic layer <i>(v1.3.0)</i></li>
            <li><a href="?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetLegendGraphic&LAYER={test_layer}&STYLE=default&FORMAT=image/png">WMS GetLegend Example (PNG)</a> <i>(v1.3.0)</i></li>
        </ul>
        </li>
    </ul>
    """


class FlaskServer(Flask):
    """
    This class will use ogc.OGC objects to define flask based ogc servers
    text (xml) and binary (BytesIO) i/o from ogc.OGC will be converted
    to flask responses.
    """

    home_func = None

    def __init__(self, *args, ogcs=[], home_func=None):
        """
        Parameters
        -----------
        *args: args
            List of arguments passed to the Flask class
        ogcs: list
            List of OGC endpoints
        home_func: function(ogc.OGC)
            Function that returns the site at the root of the api
            This function should take 1 input, an instance of the ogc.OGC class.
        """
        super().__init__(*args)

        self.home_func = home_func
        if self.home_func is None:
            self.home_func = home

        self.ogcs = ogcs
        for idx, ogc in enumerate(ogcs):
            endpoint = ogc.endpoint  # should be a string, e.g. "/ogc"
            method_name = "render" + endpoint.replace("/", "_")  # e.g. "render_ogc"

            def make_method(idx):
                def method():
                    return self.ogc_render(idx)

                return method

            method = make_method(idx)
            setattr(self, method_name, method)
            method = getattr(self, method_name)
            method.__name__ = method_name
            self.add_url_rule(
                endpoint, view_func=method, methods=["GET", "POST"]
            )  # add render method as flask route
            setattr(
                self, method_name, method
            )  # bind route function call to instance method

    def ogc_render(self, ogc_idx):
        logger.info("OGC server.ogc_render %i", ogc_idx)
        if request.method != "GET":
            return respond_xml("<p>Only GET supported</p>", status=405)

        ogc = self.ogcs[ogc_idx]
        if not request.args:
            return self.home_func(ogc.endpoint)
        try:
            # We'll filter out any characters from URl parameter values that
            # are not in the allowlist.
            # Note the parameter with key "params" has a serialized JSON value,
            # so we allow braces, brackets, and quotes.
            # Allowed chars are:
            #   -, A through Z, a through z, 0 through 9,
            #   and the characters + . , _ / : * { } ( ) [ ] "
            allowed_chars = r'-A-Za-z0-9+.,_/:*\{\}\(\)\[\]"'
            match_one_unallowed_char = "[^%s]" % allowed_chars
            args = {
                # WCS standard says argument keys can come in with any
                #    capitalization; convert keys to lower-case.
                # Find every unallowed char in the value and replace it
                #    with nothing (remove it).
                k.lower(): re.sub(match_one_unallowed_char, "", str(v))
                for (k, v) in request.args.items()
            }

            if request.base_url:
                args["base_url"] = request.base_url + "?"
            else:
                args["base_url"] = None
            ogc_response = None
            if args["service"].lower() == "wcs":
                ogc_response = ogc.handle_wcs_kv(args)
            elif args["service"].lower() == "wms":
                ogc_response = ogc.handle_wms_kv(args)
            if ogc_response is not None:
                if isinstance(ogc_response, six.string_types):
                    return respond_xml(ogc_response, status=200)
                else:
                    fp = ogc_response["fp"]
                    fn = ogc_response["fn"]
                    as_attach = True if fn.endswith("tif") else False
                    try:
                        return send_file(
                            fp, as_attachment=as_attach, attachment_filename=fn
                        )
                    except (
                        TypeError
                    ):  # attachment_filename was renamed to download_name in newer versions of flask
                        return send_file(fp, as_attachment=as_attach, download_name=fn)

            logger.warning(
                "Could not handle this combination of arguments: %r", dict(request.args)
            )
            raise WCSException("No response for this combination of arguments.")

        except WCSException as e:
            logger.error(
                "OGC: server.ogc_render WCSException: %s", str(e), exc_info=True
            )
            # WCSException is raised when the client sends an invalid set of parameters.
            # Therefore it should result in a client error, in the 400 range.
            # Security scans have flagged a security concern when returning a 500 error,
            # since it might imply successful command injection.
            return respond_xml(e.to_xml(), status=400)
        except Exception as e:
            logger.error("OGC: server.ogc_render Exception: %s", str(e), exc_info=True)
            ee = WCSException()
            return respond_xml(ee.to_xml(), status=500)


class FastAPI(object):
    """
    FastAPI is a flask-like Python web server using python3 concurrecy.
    It uses ASGI (Asycnhronous Standard Gateway Interface).
    It seems to be replacing Flask.
    However, it is built on Pydantic which depends on python3 type hinting
    in a way that may get broken in the near future python releases.

    Also, because it is compatible with ASGI
    we can use FastAPI with Magnum for easy integration with
    AWS lambda and api-gateway
    https://towardsdatascience.com/fastapi-aws-robust-api-part-1-f67ae47390f9
    https://mangum.io/asgi-frameworks/
    """

    def __init__(self, *args, ogcs=[]):
        super().__init__(*args)
        raise NotImplementedError
