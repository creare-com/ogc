# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common commands

Install for development (Python >= 3.10; CI uses 3.12):

```bash
pip install --upgrade pip setuptools
pip install .[dev]
```

Run the example app (binds Flask to 127.0.0.1:5000):

```bash
cd example && python app.py
```

Tests, lint, format (commands match what CI runs in `.github/workflows/github-python-workflow.yml`):

```bash
pytest                                              # all tests; testpaths=["ogc"]
pytest ogc/test/test_core.py                        # one file
pytest ogc/test/test_core.py::test_function_name    # one test
pytest -k "substring"                               # filter by name

flake8 . --ignore=E,W,D,I,N806,N815,N818,Q000,Q001,Q002,S001,B008,B028 --max-line-length=120
black --check --diff -l 120 ogc example             # check
black -l 120 ogc example                            # apply
```

Coverage (mirrors CI):

```bash
coverage run --data-file=coverage.bin --branch -m pytest --continue-on-collection-errors
coverage xml --data-file=coverage.bin -o coverage.xml
```

## Architecture

This package is a Python OGC server library (WCS 1.0.0, WMS 1.3.0, WMTS 1.0.0, EDR 1.1.0). It cleanly separates three layers:

1. **Protocol layer** — `ogc/wcs_request_1_0_0.py`, `wcs_response_1_0_0.py`, `wms_request_1_3_0.py`, `wms_response_1_3_0.py`, `wmts/wmts_request_1_0_0.py`, `wmts/wmts_response_1_0_0.py`. Each `*_request_*.py` parses/validates incoming KV (or XML) args; each `*_response_*.py` builds capability/coverage XML. They are pure Python — no web framework. The shared base `XMLNode` and `WCSException`/`WMTSException` live in `ogc/ogc_common.py`.

2. **Service core** — `ogc/core.py` exposes `OGC`, the framework-agnostic dispatcher. Its `handle_wcs_kv`, `handle_wms_kv`, `handle_wmts_kv` methods take a dict of (lowercased) request args and return either a string (XML) or a dict `{"fp": <BytesIO>, "fn": <filename>}` for binary responses. EDR is handled separately via `ogc/edr/EdrRoutes` (built on `pygeoapi`); WMTS via `ogc/wmts/WmtsRoutes`. Each subsystem is constructed only if the corresponding flag in `ogc/settings.py` is enabled.

3. **Web framework adapters** — `ogc/servers.py` wraps `OGC` for Flask (`FlaskServer`). It is the *only* place that knows about Flask. `FastAPI` is stubbed (`NotImplementedError`). When adding a new framework, model it after `FlaskServer`: convert framework request → arg dict, call `ogc.handle_*_kv`, convert return value back to a framework response. `_check_query_string` and the regex-based arg sanitizer in `ogc_render`/`edr_render` enforce input limits (`MAX_QUERY_STRING_BYTES`) and allowlist characters — keep these guards in any new adapter.

**Data source plug-ins** — `ogc/Layer` (in `ogc/__init__.py`) is an abstract `traitlets.HasTraits` interface (`get_map`, `get_coverage`, `get_legend_graphic`, plus a `GridCoordinates` footprint). `ogc/podpac.py` provides the concrete PODPAC-backed implementation (`podpac.Layer` subclasses `ogc.Layer`). Other backends should subclass `ogc.Layer` similarly; do not add backend-specific code into `core.py`.

**Configuration via env vars** (`ogc/settings.py`): `OGC_SUPPORTED_FORMATS` (comma list of `wms,wcs,wmts,edr`) controls which subsystems light up at `OGC.__init__` time; `EDR_CONFIGURATION_PATH` and `FRONT_END_ADDRESS` are also read from env. Limits like `MAX_GRID_COORDS_REQUEST_SIZE` and `MAX_QUERY_STRING_BYTES` are enforced here.

**Exception flow** — anywhere inside `core.py` or layer implementations, raise `WCSException` (or `WMTSException` for WMTS paths) with a proper `exception_code` and `locator`. The Flask adapter renders these as 400 responses; any other exception becomes a generic 500 with a sanitized XML body. Do not let raw exceptions propagate out of `handle_*_kv` for security reasons (a 500 can be misread as evidence of injection success — see comments in `servers.py:ogc_render`).

## Conventions specific to this repo

- Black with `line-length = 120`. The pre-commit hook installs automatically via `setup.py develop`'s `PostDevelopCommand`.
- `traitlets.HasTraits` is used heavily for typed data classes throughout the protocol and core layers — follow that pattern instead of dataclasses or pydantic.
- Bare `except Exception` blocks that intentionally swallow/translate errors at the API boundary are tagged with `# noqa: B902` (flake8-blind-except). Do not remove these unless replacing with a specific exception type.
- `pytest.ini_options.testpaths = ["ogc"]` — tests live alongside code in `ogc/test/`, `ogc/wmts/test/`, `ogc/edr/test/`. Put new tests next to the module they exercise.
- Version is bumped manually in `ogc/version.py` (MAJOR/MINOR/HOTFIX constants); `version.version()` augments with `git describe` when in a checkout.
