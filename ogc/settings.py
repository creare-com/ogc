"""
Settings here specific to OGC server will be moved to OGC repo

However, some of these settings will serve as defaults for ogc.OGC
   e.g. WMS, WCS limits for different CRS's
        max number of pixels for a grid request
"""

import os

# Settings applied around the OGC server package.
crs_84 = "crs:84"
epsg_4326 = "epsg:4326"
crs_84_uri_format = "http://www.opengis.net/def/crs/OGC/1.3/CRS84"
crs_84h_uri_format = "http://www.opengis.net/def/crs/OGC/0/CRS84h"
epsg_4326_uri_format = "http://www.opengis.net/def/crs/EPSG/0/4326"

# Default/Supported WMS CRS/SRS
WMS_CRS = {
    "epsg:3857": {
        "minx": -20037508.342789244,
        "miny": -20037508.342789244,
        "maxx": 20037508.342789244,
        "maxy": 20037508.342789244,
    },
    # 'epsg:3785': ... <-- this is deprecated but the same as 3857
    # Apparently it lat=x lon=y from Example 2 on page 18 of the WMS version 1.3.0 spec
    # http://portal.opengeospatial.org/files/?artifact_id=14416
    epsg_4326: {"minx": -90, "miny": -180, "maxx": 90, "maxy": 180},
    crs_84: {"minx": -180, "miny": -90, "maxx": 180, "maxy": 90},
}
WCS_CRS = {
    epsg_4326: {"minx": -90, "miny": -180, "maxx": 90, "maxy": 180},
    crs_84: {"minx": -180, "miny": -90, "maxx": 180, "maxy": 90},
}
EDR_CRS = {
    epsg_4326_uri_format: {"minx": -90.0, "miny": -180.0, "maxx": 90.0, "maxy": 180.0},
    crs_84_uri_format: {"minx": -180.0, "miny": -90.0, "maxx": 180.0, "maxy": 90.0},
    crs_84h_uri_format: {"minx": -180.0, "miny": -90.0, "maxx": 180.0, "maxy": 90.0},
}

# EDR query output formats
GEOTIFF = "GeoTIFF"
JSON = "JSON"
COVERAGE_JSON = "CoverageJSON"
HTML = "HTML"
EDR_QUERY_FORMATS = {
    "cube": [GEOTIFF, COVERAGE_JSON],
    "area": [GEOTIFF, COVERAGE_JSON],
    "position": [COVERAGE_JSON],
}
EDR_QUERY_DEFAULTS = {
    "cube": GEOTIFF,
    "area": GEOTIFF,
    "position": COVERAGE_JSON,
}

# The dimension associated with time instances of a collection
EDR_TIME_INSTANCE_DIMENSION = "referenceTime"

# WMS Capabilities timestamp format
USE_TIMES_LIST = False
PAST_DAYS_INCLUDED = 7

# Max WCS/WMS response size
MAX_GRID_COORDS_REQUEST_SIZE = 1024 * 1024

# WMS Capabilities limit layers
WMS_LIMIT_LAYERS = False

# get front end web address if set
try:
    FRONT_END_ADDRESS = os.environ["FRONT_END_ADDRESS"]
    if not FRONT_END_ADDRESS.strip():
        WMS_FRONT_END_ADDRESS = None
        WCS_FRONT_END_ADDRESS = None
    else:
        WMS_FRONT_END_ADDRESS = FRONT_END_ADDRESS + "/services/GEOWCS"
        WCS_FRONT_END_ADDRESS = FRONT_END_ADDRESS + "/services/GEOWCS"
except Exception:
    WMS_FRONT_END_ADDRESS = None
    WCS_FRONT_END_ADDRESS = None

CLASSIFICATION = "NONE"  # not used any more seemingly
PUBLIC_CONSTRAINT_STRING = "PUBLIC"
CONSTRAINTS = PUBLIC_CONSTRAINT_STRING

# get EDR configuration file path
try:
    EDR_CONFIGURATION_PATH = os.environ["EDR_CONFIGURATION_PATH"]
except Exception:
    EDR_CONFIGURATION_PATH = None

# get supported formats
OGC_SUPPORTED_FORMATS = os.environ.get("OGC_SUPPORTED_FORMATS", "wms,wcs")
WMS_ENABLED = "wms" in OGC_SUPPORTED_FORMATS.lower()
WCS_ENABLED = "wcs" in OGC_SUPPORTED_FORMATS.lower()
EDR_ENABLED = "edr" in OGC_SUPPORTED_FORMATS.lower()
