"""
OGC WMS/WCS (v1.3.0/v1.0.0) server
"""

import re
import traitlets as tl
import datetime

_default_pix_size = 1.0 / 3600
_default_geotransform = [-180, _default_pix_size, 0, -90, 0, _default_pix_size]


class Point(tl.HasTraits):
    lat = tl.Float(default_value=None, allow_none=True)
    lon = tl.Float(default_value=None, allow_none=True)


class GridCoordinates(tl.HasTraits):
    """
    Presents a grid of coordinates with interface that matches
    what is used in the wcs/wms request/response files.
    """

    x_size = tl.Integer(default_value=int(360 / _default_pix_size))
    y_size = tl.Integer(default_value=int(180 / _default_pix_size))
    geotransform = tl.List(trait=tl.Float, default_value=_default_geotransform)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.LLC = Point(lat=self.min_lat, lon=self.min_lon)
        self.URC = Point(lat=self.max_lat, lon=self.max_lon)

    @property
    def min_lat(self):
        return self.geotransform[3]

    @property
    def max_lat(self):
        return self.geotransform[3] + self.geotransform[5] * self.y_size

    @property
    def min_lon(self):
        return self.geotransform[0]

    @property
    def max_lon(self):
        return self.geotransform[0] + self.geotransform[1] * self.x_size


class Style(tl.HasTraits):
    string_repr = tl.Unicode(default_value="OGC Layer")
    is_enumerated = tl.Bool(default_value=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def __repr__(self):
        return self.string_repr


class Layer(tl.HasTraits):
    """
    Presents a single layer (coverage/map-layer) with interface that matches
    what is used in the wcs/wms request/response files.

    NOTE: this class defines functions that need to be implemented in subclasses
          Instances of specifically this class should not be used.
          see podpac.Layer for example of a concrete class.
    """

    safe_group_default = "Default"
    identifier = tl.Unicode()
    title = tl.Unicode(default_value="An OGC Layer")
    abstract = tl.Unicode(default_value="This is an example OGC Layer")
    group = tl.Unicode(default_value=safe_group_default)
    group_path = tl.List(trait=tl.Unicode(default_value=None, allow_none=True))
    is_fouo = tl.Bool(default_value=False)
    grid_coordinates = tl.Instance(klass=GridCoordinates, default_value=GridCoordinates())
    valid_times = tl.List(
        trait=tl.Instance(datetime.datetime),
        default_value=tl.Undefined,
        allow_none=True,
    )
    all_times_valid = tl.Bool(default_value=False)

    legend_graphic_width_inches = tl.Float(default_value=0.7)  # inches
    legend_graphic_height_inches = tl.Float(default_value=2.5)  # inches
    legend_graphic_dpi = tl.Float(default_value=100)

    @tl.validate("group")
    def _validate_group(self, proposal: dict) -> str:
        """Validate the group value to ensure it is URL safe, with a default fallback.

        Allow only charcters from the following list (A-Z, a-z, 0-9, -, _, .)
        Enforce a maximum length of 255 characters.

        Parameters
        ----------
        proposal: dict
            The traitlet proposal for group.

        Returns
        -------
        str
            The sanitized group string or safe default value.
        """
        validated_group = re.sub(r"[^-A-Za-z0-9_]", "-", proposal["value"])
        validated_group = re.sub(r"-+", "-", validated_group)
        validated_group = validated_group.strip("-")

        if len(validated_group) > 0 and len(validated_group) < 255:
            return validated_group

        return self.safe_group_default

    @property
    def legend_graphic_width(self):
        return int(self.legend_graphic_width_inches * self.legend_graphic_dpi)

    @property
    def legend_graphic_height(self):
        return int(self.legend_graphic_height_inches * self.legend_graphic_dpi)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        string_repr = self.identifier
        if "abstract" in kwargs:
            string_repr = kwargs["abstract"]
        elif "title" in kwargs:
            string_repr = kwargs["title"]
        if "is_enumerated" in kwargs:
            self._style = Style(string_repr=string_repr, is_enumerated=kwargs["is_enumerated"])
        else:
            self._style = Style(string_repr=string_repr)
        if self.valid_times is not tl.Undefined:
            self.valid_times = sorted(self.valid_times)

    def get_map(self, request_args):
        raise NotImplementedError

    def get_coverage(self, request_args):
        raise NotImplementedError

    def get_legend_graphic(self, request_args):
        raise NotImplementedError

    @property
    def id_str(self):
        return self.identifier
