"""
Podpac implementations of needed OGC interfaces
"""

import ogc
import podpac
from podpac.core.coordinates import Coordinates
import traitlets as tl

from matplotlib import pyplot
import matplotlib as mpl
import io
from PIL import Image
import numpy as np
import xarray as xr
import json


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
    width = tl.Float(default_value=1.5)  # inches
    height = tl.Float(default_value=2.5)  # inches
    dpi = tl.Float(default_value=100)  # pixels per inch
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
        fig = pyplot.figure(
            figsize=(self.width, self.height), facecolor=self.facecolor, dpi=self.dpi
        )
        if self.units:
            ax = fig.add_axes([0.25, 0.05, 0.15, 0.80])
        else:
            ax = fig.add_axes([0.1, 0.05, 0.15, 0.9])

        if self.enumeration_colors:
            enum_values = list(self.enumeration_colors.keys())
            enum_colors = list(self.enumeration_colors.values())
            enum_labels = list(self.enumeration_legend.values())
            
            # Change legend dynamically 
            max_label_width = self.get_max_text_width(enum_labels) # Estimates the max label width assuming fontsize 10
            fig_width = 1 + max_label_width  # Base width + label-dependent width
            fig_height = max(2.5, len(enum_colors) * 0.25)  # Adjust height based on number of labels
            fig.set_size_inches(fig_width,fig_height,forward=True)
            
            self.cmap = mpl.colors.ListedColormap(enum_colors) #create categorical colomap to replace previous cmap
            bounds = np.array([val-0.5 for val in np.arange(1,len(enum_values)+1)])
            norm = mpl.colors.BoundaryNorm(bounds, self.cmap.N)
            cb = mpl.colorbar.ColorbarBase(
                ax,
                cmap=self.cmap,
                norm=norm,
                ticks=np.arange(1,len(self.enumeration_legend)+1),
            )
            if self.enumeration_legend:
                cb.ax.set_yticklabels(enum_labels)

        else:
            norm = mpl.colors.Normalize(vmin=self.clim[0], vmax=self.clim[1])
            cb = mpl.colorbar.ColorbarBase(ax, cmap=self.cmap, norm=norm)

        if self.units:
            units = "[%s]" % self.units
            units = units.replace("^2", "$^2\!$")
            units = units.replace("^-6", "$^{-6}\!$")
            fig.text(
                0.4,
                0.98,
                units,
                fontsize=13,
                horizontalalignment="center",
                verticalalignment="top",
            )

        output = io.BytesIO()
        fig.savefig(output, format=self.img_format)
        pyplot.close("all")
        output.seek(0)
        return output

    def get_max_text_width(self, labels, font_size=10):
        """Estimate max text width based on labels and font size."""
        fig, ax = pyplot.subplots()  # Create a temporary figure
        renderer = fig.canvas.get_renderer()  # Get renderer to measure text
        
        text_widths = []
        for label in labels:
            text = ax.text(0, 0, label, fontsize=font_size)  # Attach text to the figure
            text_widths.append(text.get_window_extent(renderer).width)
        
        pyplot.close(fig)  # Close temporary figure
        return max(text_widths) / 100  # Convert pixels to inches