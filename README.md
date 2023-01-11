

# Organization
The list below lists some relevant classes. It is not exhaustive.

* `ogc/core.py`: defines interface and to some extent implements:
  * `ogc.OGC` class: necessary functions to support an ogc server, but not specific to any WSGI/ASGI server (e.g. Flask). Return values are native python objects (strings for xml, io.BytesIO for binary) when possible rather than something specific to a web framework like Flask
* `ogc/__init__.py`
  * `ogc.GridCoordinates` class: Used to represent footprint of WMS/WCS coverages/layers in relevant CRS.
  * `ogc.Layer` class: Necesary properties/functions for a single WMS/WCS coverage/layer offering
  * `ogc.Style` class: Used for styling  or coloring WMS layers and storing metadata
* `ogc/podpac.py`: PODPAC implementations of:
  * `podpac.OGC` class:
  * `podpac.GridCoordinates`  class:
  * `podpac.Layer` class:
* `ogc/servers.py`: implementations of OGC server in specific WSGI/ASGI web frameworks (e.g. Flask, FastAPI). These will all wrap `ogc.OGC` class.
* `ogc/app.py`: An example server app.

# Installation
* Check out this repository, then from the commandline:

```bash
pip install podpac[datatype]
pip install -e .
```

# Example
An example app is located in the `example` directory. To run it:

```bash
cd <root of repository>
cd example
python app.py
# Go to URL displayed on console
```