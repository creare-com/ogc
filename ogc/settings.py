"""
Settings here specific to OGC server will be moved to OGC repo

However, some of these settings will serve as defaults for ogc.OGC
   e.g. WMS, WCS limits for different CRS's
        max number of pixels for a grid request
"""

import os

# Settings applied around the OGC server package.

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
    "epsg:4326": {"minx": -90, "miny": -180, "maxx": 90, "maxy": 180},
    "crs:84": {"minx": -180, "miny": -90, "maxx": 180, "maxy": 90},
}
WCS_CRS = {
    "epsg:4326": {"minx": -90, "miny": -180, "maxx": 90, "maxy": 180},
    "crs:84": {"minx": -180, "miny": -90, "maxx": 180, "maxy": 90},
}

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
except:
    WMS_FRONT_END_ADDRESS = None
    WCS_FRONT_END_ADDRESS = None

CLASSIFICATION = "NONE"  # not used any more seemingly
PUBLIC_CONSTRAINT_STRING = "PUBLIC"
CONSTRAINTS = PUBLIC_CONSTRAINT_STRING
