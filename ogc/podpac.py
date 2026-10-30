"""
Podpac implementations of needed OGC interfaces
"""

import ogc
import podpac
from podpac.core.coordinates import Coordinates, union, merge_dims
import traitlets as tl
from typing import List, Tuple
from matplotlib import pyplot as plt
import matplotlib as mpl
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.text import Text
import io
import numpy as np
import json
import textwrap
from datetime import datetime
from ogc.settings import EDR_TIME_INSTANCE_DIMENSION
from ogc.ogc_common import (
    get_legend_graphic_extension,
    LEGEND_GRAPHIC_ORIENTATIONS,
    LEGEND_GRAPHIC_ORIENTATION_HORIZONTAL,
    LEGEND_GRAPHIC_ORIENTATION_VERTICAL,
)


def _uppercase_for_dict_keys(lower_dict):
    upper_dict = {}
    for k, v in lower_dict.items():
        if isinstance(v, dict):
            v = _uppercase_for_dict_keys(v)
        upper_dict[k.upper()] = v
    return upper_dict


def _crs84_to_epsg4326(args):
    # note: it is assumed that args has been processed by
    # _uppercase_for_dict_keys() so that the keys are upper case only
    if "CRS" in args and args["CRS"].upper() == "CRS:84".upper():
        args["CRS"] = "EPSG:4326"
        # need to swap x,y in bounding box (minx,miny,maxx,maxy)
        # as CRS:84 is lon,lat and epsg is lat,lon
        # see section 6.7.3 in WMS spec:
        # http://portal.opengeospatial.org/files/?artifact_id=14416
        if "BBOX" in args:
            bbox = args["BBOX"].split(",")
            bbox[:2] = bbox[1::-1]  # swap 0 and 1
            bbox[2:] = bbox[-1:1:-1]  # swap 3 and 4
            args["BBOX"] = ",".join(bbox)
    return args


class Layer(ogc.Layer):

    node = tl.Instance(klass=podpac.Node, allow_none=True)
    convert_requests_to_default_crs = tl.Bool(default_value=True)
    crs84_colon_format = "CRS:84"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.node is not None and self.node.style.enumeration_legend:
            self._style.is_enumerated = True

    def time_instances(self) -> List[str]:
        """Retrieve the time instances available for the layer.

        Returns
        -------
        List[str]
            List of available time instances as a strings.
        """
        time_instances = set()
        coordinates = self.get_coordinates()

        # Time instances are created if a node has a time instance dimension.
        if coordinates is not None and EDR_TIME_INSTANCE_DIMENSION in coordinates.udims:
            time_instances.update(
                [
                    time.astype("datetime64[ms]").astype(datetime).isoformat()
                    for time in coordinates[EDR_TIME_INSTANCE_DIMENSION].coordinates
                ]
            )

        return list(time_instances)

    def get_coordinates(self) -> Coordinates | None:
        """Retrieve the coordinates from the node.

        This enforces that all coordinates implement unstacked latitude and longitude dimensions.

        Returns
        -------
        Coordinates | None
            Coordinates from the node or None if not found.

        Raises
        ------
        ValueError
            If any coordinates do not have unstacked latitude and longitude dimensions.
        """
        if self.node is None:
            return None

        output_coordinates_list = []
        shared_dims = ["lat", "lon"]
        coordinates_list = self.node.find_coordinates()

        if len(coordinates_list) == 0:
            return None

        # Verify all coordinates define unstacked latitude and longitude
        if not all(dim in coordinates.dims for coordinates in coordinates_list for dim in shared_dims):
            raise ValueError("Invalid dimensions for coordinate retrieval.")

        # Only use one source for shared coordinates
        shared_coordinates_source = coordinates_list[0]
        for dim in shared_dims:
            output_coordinates_list.append(
                Coordinates(
                    [shared_coordinates_source[dim].coordinates],
                    dims=[dim],
                    crs=shared_coordinates_source.crs,
                )
            )

        # Use all sources for remaining dimensions, removing duplicates and enforce matching CRS
        remaining_coords = union(
            [coords.drop(shared_dims).transform(shared_coordinates_source.crs) for coords in coordinates_list]
        )
        output_coordinates_list.append(remaining_coords)

        return merge_dims(output_coordinates_list)

    def get_units(self) -> str | None:
        """Retrieve the units from the node.

        Returns
        -------
        str | None
            The units from the node.
        """
        units = None
        if self.node is not None and self.node.units is not None:
            units = self.node.units
        elif self.node is not None and self.node.style is not None:
            units = self.node.style.units

        return units

    def get_node(self, args):
        return self.node

    def get_map(self, args):
        args = _uppercase_for_dict_keys(args)

        # check if we are rescaling image (coarsening for faster generation)
        if "RESCALE" in args:
            # print('####### RESCALE = %g #########' % rescale)
            rescale = float(args["RESCALE"])
            if rescale > 1.0:
                orig_h = args["HEIGHT"]
                orig_w = args["WIDTH"]
                # don't reduce # pixels to less than MIN_N (unless orig request was smaller)
                MIN_N = 8
                args["HEIGHT"] = max(min(int(orig_h), MIN_N), int(round(int(orig_h) / rescale)))
                args["WIDTH"] = max(min(int(orig_w), MIN_N), int(round(int(orig_w) / rescale)))
        else:
            rescale = 0

        if "CRS" in args and args["CRS"].upper() == self.crs84_colon_format.upper():
            args["CRS"] = "CRS84"  # for pyproj
        if self.convert_requests_to_default_crs and "DEFAULT_CRS" in podpac.settings:
            # PODPAC transforms input coords to crs of datasource recursively
            # every time eval is used in a Node included in its dependency tree.
            # This optimization can be used if most datasources are stored in the same crs.
            coords = Coordinates.from_url(args).transform(podpac.settings["DEFAULT_CRS"])
        else:
            coords = Coordinates.from_url(args)

        node = self.get_node(args)
        output = node.eval(coords)

        # if rescaling, use nearest neighbor interpolation to restore original size
        if rescale > 1.0:
            args["HEIGHT"] = orig_h
            args["WIDTH"] = orig_w
            if self.convert_requests_to_default_crs and "DEFAULT_CRS" in podpac.settings:
                rescaledcoords = Coordinates.from_url(args).transform(podpac.settings["DEFAULT_CRS"])
            else:
                rescaledcoords = Coordinates.from_url(args)
            output = output.interp(
                lat=rescaledcoords["lat"].coordinates + 1e-6,
                lon=rescaledcoords["lon"].coordinates + 1e-6,
                method="nearest",
                kwargs={"fill_value": "extrapolate"},
            )

        podpac.utils.clear_cache("ram")
        body = output.to_format("png")
        return body

    def get_coverage(self, args):
        args = _uppercase_for_dict_keys(args)
        if "CRS" in args and args["CRS"].upper() == self.crs84_colon_format.upper():
            args["CRS"] = "CRS84"  # for pyproj
        if self.convert_requests_to_default_crs and "DEFAULT_CRS" in podpac.settings:
            # PODPAC transforms input coords to crs of datasource recursively
            # every time eval is used in a Node included in its dependency tree.
            # This optimization can be used if most datasources are stored in the same crs.
            coords = Coordinates.from_url(args).transform(podpac.settings["DEFAULT_CRS"])
        else:
            coords = Coordinates.from_url(args)

        node = self.get_node(args)
        output = node.eval(coords)
        podpac.utils.clear_cache("ram")
        body = output.to_format("geotiff")
        return body

    def get_legend_graphic(self, request_args):
        legend_graphic_extension = get_legend_graphic_extension(request_args.get("format"))
        if self.node is not None:
            units = self.node.style.units
            cmap = self.node.style.cmap
            enumeration_legend = self.node.style.enumeration_legend
            enumeration_colors = self.node.style.enumeration_colors
            clim = self.node.style.clim
        else:
            # cmap
            params = json.loads(request_args.get("params", r"{}"))
            colormap = params.get("colormap", "viridis")
            cmap = mpl.colormaps[colormap]

            # clim
            clim = [None, None]
            if "vmin" in params:
                clim[0] = float(params["vmin"])
            if "vmax" in params:
                clim[1] = float(params["vmax"])

            # units
            units = request_args.get("units")

            # not used
            enumeration_legend = None
            enumeration_colors = None

        legend_graphic = LegendGraphic(
            width=self.legend_graphic_width_inches,
            height=self.legend_graphic_height_inches,
            dpi=self.legend_graphic_dpi,
            units=units,
            cmap=cmap,
            enumeration_legend=enumeration_legend,
            enumeration_colors=enumeration_colors,
            clim=clim,
            img_format=legend_graphic_extension,
            orientation=self.legend_graphic_orientation,
        )
        return legend_graphic.legend_image()


class LegendGraphic(tl.HasTraits):
    """
    A class for generating legend graphics with adjustable properties such as width, height, fonts, and color mappings.
    """

    width = tl.Float()  # inches
    height = tl.Float()  # inches
    min_width = tl.Float(default_value=0.0)  # inches
    min_height = tl.Float(default_value=0.0)  # inches
    max_width = tl.Float()  # inches
    max_height = tl.Float()  # inches
    colorbar_thickness = tl.Float(default_value=0.15)  # inches across the colorbar
    dpi = tl.Float(default_value=100)  # pixels per inch
    units_fontsize = tl.Float(default_value=13)  # used for units text
    colorbar_fontsize = tl.Float(default_value=10)  # used for tick marks of colorbar
    enumeration_fontsize = tl.Float(default_value=16)  # used for labels of categorical legends
    enumeration_min_fontsize = tl.Float(default_value=5)  # minimum fontsize for categorical legends with lots of labels
    max_unit_chars = tl.Int(default_value=16)  # maximum characters allowed in a line for units
    units = tl.Unicode(default_value=tl.Undefined, allow_none=True)
    img_format = tl.Enum(values=["png", "pdf", "ps", "eps", "svg"], default_value="png")
    cmap = tl.Instance(klass=mpl.colors.Colormap, default_value=mpl.cm.viridis)
    facecolor = tl.Unicode(default_value="white")
    enumeration_legend = tl.Dict(
        key_trait=tl.Int(),
        value_trait=tl.Unicode(),
        default_value=None,
        allow_none=True,
    )
    enumeration_colors = tl.Dict(key_trait=tl.Int(), default_value=None, allow_none=True)
    clim = tl.List(default_value=[None, None])
    orientation = tl.Enum(values=list(LEGEND_GRAPHIC_ORIENTATIONS), default_value=LEGEND_GRAPHIC_ORIENTATION_VERTICAL)
    pad = tl.Float(default_value=0.05)  # inches around the legend and between the labels and units
    enumeration_label_height = tl.Float(default_value=0.25)  # inches along a vertical colorbar for each category

    @property
    def _horizontal(self) -> bool:
        return self.orientation == LEGEND_GRAPHIC_ORIENTATION_HORIZONTAL

    @tl.default("width")
    def _default_width(self) -> float:
        return 2.5 if self._horizontal else 0.7

    @tl.default("height")
    def _default_height(self) -> float:
        return 0.7 if self._horizontal else 2.5

    @tl.default("max_width")
    def _default_max_width(self) -> float:
        return 5.5 if self._horizontal else 1.5

    @tl.default("max_height")
    def _default_max_height(self) -> float:
        return 1.5 if self._horizontal else 5.5

    def legend_image(self) -> io.BytesIO:
        """Generate the legend image.

        A vertical legend has the units above the colorbar and the labels to its right.
        A horizontal legend has the labels below the colorbar and the units below the labels.

        Returns
        -------
        io.BytesIO
            A byte stream containing the legend image in the specified format.
        """
        fig = plt.figure(figsize=(self.width, self.height), facecolor=self.facecolor, dpi=self.dpi)

        # set axis for colorbar, positioned once the fig is fit to the legend
        ax = fig.add_axes([0, 0, 1, 1])
        length = self.create_colorbar(ax)

        # fit fig to the colorbar, labels and units, enumerations have no units
        units_str = self.wrap_units() if self.units and not self.enumeration_colors else None
        fig = self.fit_fig_to_legend(fig, ax, length, units_str)

        output = io.BytesIO()
        fig.savefig(output, format=self.img_format)
        plt.close(fig)
        output.seek(0)
        return output

    def create_colorbar(self, ax: Axes) -> float | None:
        """Add the colorbar with its labels.

        Categorical data has a color for each category, from the bottom or left, with labels shortened to fit within
        the max width.

        Parameters
        ----------
        ax : Axes
            The axis object.

        Returns
        -------
        float | None
            The colorbar length in inches for categorical data, or None to fill the legend width or height.
        """
        if not self.enumeration_colors:
            norm = mpl.colors.Normalize(vmin=self.clim[0], vmax=self.clim[1])
            mpl.colorbar.ColorbarBase(ax, cmap=self.cmap, norm=norm, orientation=self.orientation)
            ax.tick_params(labelsize=self.colorbar_fontsize)
            return None

        enum_values = list(self.enumeration_colors.keys())
        enum_colors = [self.enumeration_colors[k] for k in enum_values]
        enum_labels = [(self.enumeration_legend or {}).get(k, str(k)) for k in enum_values]

        # smaller font for lots of labels
        font_size = max(self.enumeration_min_fontsize, self.enumeration_fontsize - (len(enum_values) * 0.35))

        cmap = mpl.colors.ListedColormap(enum_colors)
        norm = mpl.colors.BoundaryNorm(np.arange(len(enum_colors) + 1) - 0.5, cmap.N)
        ticks = np.arange(len(enum_colors))
        mpl.colorbar.ColorbarBase(ax, cmap=cmap, norm=norm, ticks=ticks, orientation=self.orientation)

        if self._horizontal:
            # each label gets the room it needs under its color, within the max width
            label_width = self.get_max_text_width(enum_labels, font_size) + 0.1
            length = len(enum_colors) * label_width
        else:
            # each label gets enumeration_label_height next to its color, leaving room for the tick marks and margins
            length = len(enum_colors) * self.enumeration_label_height

        (ax.xaxis if self._horizontal else ax.yaxis).set_ticklabels(enum_labels)
        ax.tick_params(labelsize=font_size)
        return length

    def fit_fig_to_legend(
        self,
        fig: Figure,
        ax: Axes,
        length: float | None = None,
        units_str: str | None = None,
    ) -> Figure:
        """Size the figure to the legend, within the min and max width and height, and place the colorbar and units.

        Along the colorbar the figure is the legend width or height, or fits the colorbar length when given. Across
        the colorbar it fits the labels and units. The units are centered above a vertical colorbar and below the
        labels of a horizontal colorbar.

        Parameters
        ----------
        fig : Figure
            The figure object.
        ax : Axes
            The axis object, with the colorbar drawn.
        length : float | None, optional
            The colorbar length in inches.
        units_str : str | None, optional
            The wrapped unit string.

        Returns
        -------
        Figure
            The updated figure.
        """
        units = None
        if units_str:
            units = fig.text(
                0.5,
                0.5,
                units_str,
                fontsize=self.units_fontsize,
                horizontalalignment="center",
                verticalalignment="bottom" if self._horizontal else "top",
            )

        # resize the colorbar to find the length that fills the figure along it
        legend_length = self.width if self._horizontal else self.height
        start_length = length if length is not None else legend_length
        edges = self.resize_legend(fig, ax, units, start_length)
        fig_width, fig_height = self.get_legend_size(edges, length)
        left, right, bottom, top, _, units_height = edges
        if self._horizontal:
            length = max(0.1, fig_width - left - right - 2 * self.pad)
        else:
            length = max(0.1, fig_height - bottom - top - units_height - 2 * self.pad)

        # resize to apply the new tick labels, matplotlib picks them to fit the colorbar length
        edges = self.resize_legend(fig, ax, units, length)
        fig_width, fig_height = self.get_legend_size(edges, length)
        left, right, bottom, top, _, units_height = edges

        # center the colorbar and labels across the figure, at the top below the vertical units
        bar_width, bar_height = self.get_colorbar_size(length)
        x0 = (fig_width - left - bar_width - right) / 2 + left
        y0 = fig_height - self.pad - top - bar_height - (0.0 if self._horizontal else units_height)
        fig.set_size_inches(fig_width, fig_height, forward=True)
        ax.set_position((x0 / fig_width, y0 / fig_height, bar_width / fig_width, bar_height / fig_height))
        if units is not None:
            units.set_position((0.5, self.pad / fig_height if self._horizontal else 1 - self.pad / fig_height))

        return fig

    def resize_legend(
        self,
        fig: Figure,
        ax: Axes,
        units: Text | None,
        length: float,
    ) -> Tuple[float, float, float, float, float, float]:
        """Resize the figure and colorbar to the given length.

        To measure, the figure is enlarged to leave room around the colorbar so no labels are cut off, and the
        colorbar is moved to its center. This layout is not restored, so the caller must set the final figure size,
        colorbar position and units position before saving.

        Parameters
        ----------
        fig : Figure
            The figure object.
        ax : Axes
            The axis object, with the colorbar drawn.
        units : Text | None
            The units text, or None.
        length : float
            The colorbar length in inches.

        Returns
        -------
        Tuple[float, float, float, float, float, float]
            The labels past the left, right, bottom and top of the colorbar, and the units width and height
            including the pad to the labels, in inches.
        """
        bar_width, bar_height = self.get_colorbar_size(length)
        room = 2.0  # inches around the colorbar while measuring, more than its labels need
        fig.set_size_inches(bar_width + 2 * room, bar_height + 2 * room, forward=True)
        ax.set_position(
            (
                room / (bar_width + 2 * room),
                room / (bar_height + 2 * room),
                bar_width / (bar_width + 2 * room),
                bar_height / (bar_height + 2 * room),
            )
        )
        renderer = fig.canvas.get_renderer()
        bbox = ax.get_tightbbox(renderer)
        left = room - bbox.x0 / fig.dpi
        right = bbox.x1 / fig.dpi - room - bar_width
        bottom = room - bbox.y0 / fig.dpi
        top = bbox.y1 / fig.dpi - room - bar_height

        units_width, units_height = 0.0, 0.0
        if units is not None:
            units_bbox = units.get_window_extent(renderer)
            units_width = units_bbox.width / fig.dpi
            units_height = units_bbox.height / fig.dpi + self.pad
        return left, right, bottom, top, units_width, units_height

    def get_colorbar_size(self, length: float) -> Tuple[float, float]:
        """Get the colorbar width and height in inches for its length along the orientation.

        Parameters
        ----------
        length : float
            The colorbar length in inches.

        Returns
        -------
        Tuple[float, float]
            The colorbar width and height in inches.
        """
        if self._horizontal:
            return length, self.colorbar_thickness
        return self.colorbar_thickness, length

    def get_legend_size(
        self, edges: Tuple[float, float, float, float, float, float], length: float | None = None
    ) -> Tuple[float, float]:
        """Get the figure width and height in inches to fit the colorbar, its labels and the units.

        The size stays within the min and max width and height. Along the colorbar, it is the legend width or height
        when the length is not given, growing so the colorbar keeps at least half of it.

        Parameters
        ----------
        edges : Tuple[float, float, float, float, float, float]
            The measurements from resize_legend.
        length : float | None, optional
            The colorbar length in inches.

        Returns
        -------
        Tuple[float, float]
            The figure width and height in inches.
        """
        left, right, bottom, top, units_width, units_height = edges
        size = self.width if self._horizontal else self.height
        bar_width, bar_height = self.get_colorbar_size(size / 2 if length is None else length)
        fig_width = max(left + bar_width + right, units_width) + 2 * self.pad
        fig_height = bottom + bar_height + top + units_height + 2 * self.pad
        if length is None and self._horizontal:
            fig_width = max(fig_width, self.width)
        elif length is None:
            fig_height = max(fig_height, self.height)
        fig_width = max(fig_width, self.min_width)

        # do not limit width of enumerated legends
        if not self.enumeration_legend:
            fig_width = min(fig_width, self.max_width)

        fig_height = min(max(fig_height, self.min_height), self.max_height)
        return fig_width, fig_height

    def wrap_units(self) -> str:
        """Wrap the units into lines of up to max_unit_chars that fit within the max width.

        Keeps as many lines as fit within half the max height, ending the last with an ellipsis.

        Returns
        -------
        str
            The wrapped unit string.
        """
        units = "[%s]" % self.units
        max_chars = self.max_unit_chars
        units_lines = self.wrap_text(units, max_chars).split("\n")
        while (
            max_chars > 1 and self.get_max_text_width(units_lines, self.units_fontsize) > self.max_width - 2 * self.pad
        ):
            max_chars -= 1
            units_lines = self.wrap_text(units, max_chars).split("\n")

        line_height = self.units_fontsize / 72 * 1.2  # inches, matplotlib spaces lines 1.2 times the font size
        max_lines = max(1, int(self.max_height / 2 / line_height))
        if len(units_lines) > max_lines:
            units_lines = units_lines[:max_lines]
            units_lines[-1] = units_lines[-1][:-1] + "…"
        return "\n".join(units_lines)

    def get_max_text_width(self, labels, font_size=10):
        """
        Estimates the maximum width of given text labels in inches.

        Args:
            labels (list of str): List of text labels.
            font_size (int): Font size used for labels.

        Returns:
            float: The maximum width of the labels in inches.
        """
        fig, ax = plt.subplots(dpi=self.dpi)  # Create a temporary figure
        renderer = fig.canvas.get_renderer()  # Get renderer to measure text

        text_widths = []
        for label in labels:
            text = ax.text(0, 0, label, fontsize=font_size)  # Attach text to the figure
            text_widths.append(text.get_window_extent(renderer).width)

        plt.close(fig)  # Close temporary figure
        return max(text_widths) / self.dpi  # Convert pixels to inches

    def wrap_text(self, text, max_width_chars=16):
        """
        Split string into sections of length max_width_chars
        """
        return "\n".join(textwrap.wrap(text, width=max_width_chars))
