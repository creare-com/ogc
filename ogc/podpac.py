"""
Podpac implementations of needed OGC interfaces
"""

import ogc
import podpac
from podpac.core.coordinates import Coordinates
import traitlets as tl

from matplotlib import pyplot as plt
import matplotlib as mpl
import io
from PIL import Image
import numpy as np
import xarray as xr
import json
import textwrap
import re



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

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.node is not None and self.node.style.enumeration_legend:
            self._style.is_enumerated = True

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
                args["HEIGHT"] = max(
                    min(int(orig_h), MIN_N), int(round(int(orig_h) / rescale))
                )
                args["WIDTH"] = max(
                    min(int(orig_w), MIN_N), int(round(int(orig_w) / rescale))
                )
        else:
            rescale = 0

        if "CRS" in args and args["CRS"].upper() == "CRS:84".upper():
            args["CRS"] = "CRS84"  # for pyproj
        if self.convert_requests_to_default_crs and "DEFAULT_CRS" in podpac.settings:
            # PODPAC transforms input coords to crs of datasource recursively
            # every time eval is used in a Node included in its dependency tree.
            # This optimization can be used if most datasources are stored in the same crs.
            coords = Coordinates.from_url(args).transform(
                podpac.settings["DEFAULT_CRS"]
            )
        else:
            coords = Coordinates.from_url(args)

        node = self.get_node(args)
        output = node.eval(coords)

        # if rescaling, use nearest neighbor interpolation to restore original size
        if rescale > 1.0:
            args["HEIGHT"] = orig_h
            args["WIDTH"] = orig_w
            if (
                self.convert_requests_to_default_crs
                and "DEFAULT_CRS" in podpac.settings
            ):
                rescaledcoords = Coordinates.from_url(args).transform(
                    podpac.settings["DEFAULT_CRS"]
                )
            else:
                rescaledcoords = Coordinates.from_url(args)
            # rescaled_node = podpac.data.Array(source=output, coordinates=coords, style = node.style)
            # output = rescaled_node.eval(rescaledcoords)
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
        if "CRS" in args and args["CRS"].upper() == "CRS:84".upper():
            args["CRS"] = "CRS84"  # for pyproj
        if self.convert_requests_to_default_crs and "DEFAULT_CRS" in podpac.settings:
            # PODPAC transforms input coords to crs of datasource recursively
            # every time eval is used in a Node included in its dependency tree.
            # This optimization can be used if most datasources are stored in the same crs.
            coords = Coordinates.from_url(args).transform(
                podpac.settings["DEFAULT_CRS"]
            )
        else:
            coords = Coordinates.from_url(args)

        node = self.get_node(args)
        output = node.eval(coords)
        podpac.utils.clear_cache("ram")
        body = output.to_format("geotiff")
        return body

    def get_legend_graphic(self, request_args):
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
            cmap = mpl.cm.get_cmap(colormap)

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
        )
        return legend_graphic.legend_image()


class LegendGraphic(tl.HasTraits):
    width = tl.Float(default_value=0.7)  # inches
    max_width = tl.Float(default_value=1.5)  # inches
    min_width = tl.Float(default_value=0.8) # inches
    height = tl.Float(default_value=2.5)  # inches
    max_heigth = tl.Float(default_value=5.5)  # inches
    dpi = tl.Float(default_value=100)  # pixels per inch
    units_fontsize = tl.Float(default_value=13) # used for units text at top of legend
    colorbar_fontsize = tl.Float(default_value=10) # used for tick marks of colorbar
    enumeration_fontsize = tl.Float(default_value=16) # used for labels of categorical legends 
    enumeration_min_fontsize = tl.Float(default_value=5)# minimum fontsize for categorical legends with lots of labels
    max_unit_chars = tl.Float(default_value=16) # maximum characters allowed in a line for units
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
    enumeration_colors = tl.Dict(
        key_trait=tl.Int(), default_value=None, allow_none=True
    )
    clim = tl.List(default_value=[None, None])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def legend_image(self):
        fig = plt.figure(
            figsize=(self.width, self.height), facecolor=self.facecolor, dpi=self.dpi
        )
        # check if there are units and see if they are longer than self.max_unit_chars
        if self.units:
            fig, needs_wrap, units_str = self.check_if_units_need_to_be_wrapped(fig)

        # add axis to figure, reshape figures if units. Do not reshape for enumerations or just colorbar
        if self.units and needs_wrap:
            fig, ax = self.adjust_fig_width_for_wrapped_units(fig, units_str)
            # add color bars
            norm = mpl.colors.Normalize(vmin=self.clim[0], vmax=self.clim[1])
            mpl.colorbar.ColorbarBase(ax, cmap=self.cmap, norm=norm)
        elif self.units:
            fig, ax = self.adjust_fig_width_for_unwrapped_units(fig, units_str)
            # add color bars
            norm = mpl.colors.Normalize(vmin=self.clim[0], vmax=self.clim[1])
            mpl.colorbar.ColorbarBase(ax, cmap=self.cmap, norm=norm)
        elif self.enumeration_colors:
            # set axis for enumeration
            ax = fig.add_axes([0.05, 0.0125, 0.1, 0.975])
            # changes fig size in based on # of labels, add colorbar
            fig = self.create_enumeration_legend(fig, ax)
        else:
            # set axis for enumeration for colorbar and tick marks only
            ax = fig.add_axes([0.1, 0.05, 0.25, 0.9])
            # adjust fig size for colorbar and tick mark text length, add colorbar
            fig = self.adjust_fig_width_for_long_tick_marks(fig, ax)

        output = io.BytesIO()
        fig.savefig(output, format=self.img_format)
        plt.close("all")
        output.seek(0)
        return output

    def check_if_units_need_to_be_wrapped(self, fig):
        units = "[%s]" % self.units
        needs_wrap = len(units) > self.max_unit_chars  # if characters are greater than 16 then wrap text and shrink colorbar
        # currently only allows for 2 lines
        wrapped_units = self.wrap_text(units, self.max_unit_chars)
        # format exponents
        units = re.sub(r"\^(\d+)", r"$^{\1}\!$", units)            
        units = re.sub(r"\^-(\d+)", r"$^{-\1}\!$", units)
        # add units to figure
        fig.text(
            0.5,
            0.98,
            wrapped_units,
            fontsize=self.units_fontsize,
            horizontalalignment="center",
            verticalalignment="top",
            wrap=True
        )
        return fig, needs_wrap, wrapped_units
    
    def adjust_fig_width_for_wrapped_units(self, fig, wrapped_units):
        # wrap text and increase height of figure
        added_lines = wrapped_units.count("\n")
        added_height = self.additional_height_for_wrapped_text(self, added_lines, self.units_fontsize)
        fig_height = min(self.max_heigth, added_height + self.height) # add extra height to figure ensure it is less than 6.5 in
        # adjust fig size to fit units            
        fig.set_size_inches(self.max_width, fig_height, forward=True)

        # Standard height ratio (before adjustments)
        base_figure_height = self.height  # Original figure height in inches
        base_ax_height_ratio = 0.75  # Initial height of ax as a fraction of fig height
        # Compute the new height ratio based on the updated figure height
        adjusted_ax_height_ratio = base_ax_height_ratio * (base_figure_height / fig_height)
        # make axes smaller to fix units
        ax = fig.add_axes([0.35, 0.05, 0.15, adjusted_ax_height_ratio])


        return fig, ax

    def adjust_fig_width_for_unwrapped_units(self, fig, units_str):
        # adjust figure width based on unit length
        # add space for units
        ax = fig.add_axes([0.3, 0.05, 0.15, 0.80])
        # adjust fig size to fit units
        max_label_width = self.get_max_text_width([units_str], self.units_fontsize) # Estimates the max label width assuming fontsize 10
        fig_width = max(self.min_width, max_label_width + 0.2) #define minimum width need or max_label width + some extra margin
        fig.set_size_inches(fig_width, self.height, forward=True)
        return fig, ax
        
    def create_enumeration_legend(self, fig, ax):
        enum_values = list(self.enumeration_colors.keys())
        enum_colors = list(self.enumeration_colors.values())
        enum_labels = list(self.enumeration_legend.values())
        
        # Dynamically adjust font size based on the number of ticks
        font_size = max(self.enumeration_min_fontsize, self.enumeration_fontsize - (len(enum_values) * 0.35))  # Scale font size

        # Change legend dynamically 
        max_label_width = self.get_max_text_width(enum_labels, font_size) # Estimates the max label width assuming fontsize 10
        fig_width = 0.5 + max_label_width  # Base width + label-dependent width
        fig_height = min(self.max_heigth, len(enum_colors) * 0.25)  # Adjust height based on number of labels
        fig.set_size_inches(fig_width, fig_height, forward=True)
        
        self.cmap = mpl.colors.ListedColormap(enum_colors) #create categorical colomap to replace previous cmap
        bounds = np.array([val-0.5 for val in np.arange(1,len(enum_values)+2)])
        norm = mpl.colors.BoundaryNorm(bounds, self.cmap.N)

        cb = mpl.colorbar.ColorbarBase(
            ax,
            cmap=self.cmap,
            norm=norm,
            ticks=np.arange(1,len(self.enumeration_legend)+1),
        )
        if self.enumeration_legend:
            cb.ax.set_yticklabels(enum_labels, fontsize=font_size)

        return fig
    
    def adjust_fig_width_for_long_tick_marks(self, fig, ax):
        # adjust figure width based on tick labels
        norm = mpl.colors.Normalize(vmin=self.clim[0], vmax=self.clim[1])
        cb = mpl.colorbar.ColorbarBase(ax, cmap=self.cmap, norm=norm)
        tick_labels = [str(t) for t in cb.ax.get_yticks()]  # Convert ticks to strings
        font_size = 10
        max_label_width = self.get_max_text_width(tick_labels, self.colorbar_fontsize)
        fig_width = max_label_width + 0.4
        fig.set_size_inches(fig_width, self.height,forward=True)

        return fig

    def get_max_text_width(self, labels, font_size=10):
        """Estimate max text width based on labels and font size."""
        fig, ax = plt.subplots()  # Create a temporary figure
        renderer = fig.canvas.get_renderer()  # Get renderer to measure text
        
        text_widths = []
        for label in labels:
            text = ax.text(0, 0, label, fontsize=font_size)  # Attach text to the figure
            text_widths.append(text.get_window_extent(renderer).width)
        
        plt.close(fig)  # Close temporary figure
        return max(text_widths) / self.dpi  # Convert pixels to inches
    
    def wrap_text(self, text, max_width_chars=20):
        return "\n".join(textwrap.wrap(text, width=max_width_chars))

    def additional_height_for_wrapped_text(self, added_lines_num, font_size):
        font_height_px = font_size * (self.dpi / 72)  # Convert to pixels
        font_height_in = font_height_px / self.dpi  # Convert pixels to inches
        additional_height = font_height_in*added_lines_num

        return additional_height
