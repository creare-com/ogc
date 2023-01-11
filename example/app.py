"""
Demo Flask app using PODPAC Node backed layers.
"""

from flask import Flask
from datetime import datetime
import re

from ogc import servers
from ogc import core
from ogc import podpac as pogc

import podpac
import numpy as np

# create some podpac nodes
data = np.random.rand(11, 21)
lat = np.linspace(90, -90, 11)
lon = np.linspace(-180, 180, 21)
coords = podpac.Coordinates([lat, lon], dims=["lat", "lon"])
node1 = podpac.data.Array(source=data, coordinates=coords)

data2 = np.random.rand(11, 21)
node2 = podpac.data.Array(source=data2, coordinates=coords)

# use podpac nodes to create some OGC layers
layer1 = pogc.Layer(
    node=node1,
    identifier="layer1",
    title="OGC/POPAC layer containing random data",
    abstract="This layer contains some random data",
)

layer2 = pogc.Layer(
    node=node2,
    identifier="layer2",
    title="FOUO: Another OGC/POPAC layer containing random data",
    abstract="Marked as FOUO. This layer contains some random data. Same coordinates as layer1, but different values.",
    is_fouo=True,
)

all_layers = [layer1, layer2]
non_fouo_layers = [layer for layer in all_layers if not layer.is_fouo]

# create a couple of different ogc endpoints
# in this case one for all layers and one for non fouo layers.
FouoOGC = core.OGC(endpoint="/ogc_full", layers=all_layers)
NonFouoOGC = core.OGC(endpoint="/ogc", layers=non_fouo_layers)


def api_home(endpoint):
    """Example API home page. Developers should make their own page similar to this one."""
    test_layer = "layer1"
    return f"""<h2> OGC Server API </h2>
    <p>This is the API endpoint served at {endpoint}. Add example usage here for your users.</p>

    <ul>
        <li> WCS: Open Geospatial Consortium (OGC) Web Coverage Service (WCS) <i>(v1.0.0)</i>
        <ul>
            <li><a href="?SERVICE=WCS&REQUEST=GetCapabilities&VERSION=1.0.0">WCS GetCapabilities (XML)</a> <i>(v1.0.0)</i></li>
            <li><a href="?SERVICE=WCS&REQUEST=DescribeCoverage&VERSION=1.0.0&COVERAGE={test_layer}">WCS DescribeCoverage Example (XML)</a> <i>(v1.0.0)</i></li>
            <li><a href="?SERVICE=WCS&VERSION=1.0.0&REQUEST=GetCoverage&FORMAT=GeoTIFF&COVERAGE={test_layer}&BBOX=-132.90225856307210961,23.62932030249929483,-53.60509752693091912,53.75883389158821046&CRS=EPSG:4326&RESPONSE_CRS=EPSG:4326&WIDTH=346&HEIGHT=131">WCS GetCoverage Example (GeoTIFF)</a> <i>(v1.0.0)</i></li>
        </ul>
        </li>
        <li> WMS: Open Geospatial Consortium (OGC) Web Map Service (WMS) <i>(v1.3.0)</i>
        <ul>
            <li><a href="?SERVICE=WMS&REQUEST=GetCapabilities&VERSION=1.3.0">WMS GetCapabilities (XML)</a> <i>(v1.3.0)</i></li>
            <li><a href="?SERVICE=WMS&REQUEST=GetMap&VERSION=1.3.0&LAYERS={test_layer}&STYLES=&FORMAT=image%2Fpng&TRANSPARENT=true&HEIGHT=256&WIDTH=256&CRS=EPSG%3A3857&BBOX=-10018754.171394622,2504688.5428486555,-7514065.628545966,5009377.08569731">WMS GetMap Example (PNG)</a> <i>(v1.3.0)</i></li>
            <li><a href="?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetLegendGraphic&LAYER={test_layer}&STYLE=default&FORMAT=image/png">WMS GetLegend Example (PNG)</a> <i>(v1.3.0)</i></li>
        </ul>
        </li>
    </ul>
    """


app = servers.FlaskServer(__name__, ogcs=[NonFouoOGC, FouoOGC], home_func=api_home)

# add in some other endpoints.
@app.route("/")
def home():
    return f'This is an example OGC flask app. See <a href="/ogc_full"> FULL </a> and <a href="/ogc"> PARTIAL </a> endpoints.'


@app.route("/layers/<layer>")
def check_layers(layer):
    match_object = re.match("[a-zA-Z0-9]+", layer)

    if match_object:
        clean_layer = match_object.group(0)
        if clean_layer in [l.identifier for l in all_layers]:
            return "{} is an available layer id".format(clean_layer)
        else:
            return "No layer available with that id"
    else:
        return "Please provide a valid layer id (letters and numbers)"


if __name__ == "__main__":
    app.run()
