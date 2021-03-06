#!/usr/bin/env python
# -*- coding: utf-8 -*-
# File              : Ampel-plots/ampel/plot/utils.py
# License           : BSD-3-Clause
# Author            : vb <vbrinnel@physik.hu-berlin.de>
# Date              : 17.05.2019
# Last Modified Date: 29.06.2021
# Last Modified By  : vb <vbrinnel@physik.hu-berlin.de>

import warnings
import io, base64
import matplotlib as plt
from cairosvg import svg2png
from IPython.display import Image
from matplotlib.figure import Figure
from typing import Optional, List, Dict, Any

from ampel.content.SVGRecord import SVGRecord
from ampel.protocol.LoggerProtocol import LoggerProtocol
from ampel.model.PlotProperties import PlotProperties
from ampel.util.compression import decompress_str, compress as fcompress


# catch SyntaxWarning: "is not" with a literal. Did you mean "!="?
with warnings.catch_warnings():
	warnings.filterwarnings(
		action="ignore",
		category=SyntaxWarning,
		module=r"svgutils\.transform"
	)
	import svgutils as su


def mplfig_to_svg_dict(
	mpl_fig, file_name: str, title: Optional[str] = None, tags: Optional[List[str]] = None,
	compress: int = 1, width: Optional[int] = None, height: Optional[int] = None,
	close: bool = True, fig_include_title: Optional[bool] = False, logger: Optional[LoggerProtocol] = None
) -> SVGRecord:
	"""
	:param mpl_fig: matplotlib figure
	:param tags: list of plot tags
	:param compress:
		0: no compression, 'svg' value will be a string
		1: compress svg, 'svg' value will be compressed bytes (usage: store plots into db)
		2: compress svg and include uncompressed string into key 'sgv_str'
		(useful for saving plots into db and additionaly to disk for offline analysis)
	:param width: figure width, for example 10 inches
	:param height: figure height, for example 10 inches
	:returns: svg dict instance
	"""

	if logger:
		logger.info("Saving plot %s" % file_name)

	imgdata = io.StringIO()

	if width is not None and height is not None:
		mpl_fig.set_size_inches(width, height)

	if title and fig_include_title:
		mpl_fig.suptitle(title)

	mpl_fig.savefig(
		imgdata, format='svg', bbox_inches='tight'
	)

	if close:
		plt.pyplot.close(mpl_fig)

	ret: SVGRecord = {'name': file_name}

	if tags:
		ret['tag'] = tags

	if title:
		ret['title'] = title

	if compress == 0:
		ret['svg'] = imgdata.getvalue()
		return ret

	ret['svg'] = fcompress(imgdata.getvalue().encode('utf8'), file_name)

	if compress == 2:
		ret['svg_str'] = imgdata.getvalue()

	return ret


def mplfig_to_svg_dict1(
	mpl_fig: Figure, props: PlotProperties, extra: Optional[Dict[str, Any]] = None,
	close: bool = True, logger: Optional[LoggerProtocol] = None
) -> SVGRecord:
	"""
	:param extra: required if file_name of title in PlotProperties use a format string ("such_%s_this")
	"""

	svg_doc = mplfig_to_svg_dict(
		mpl_fig,
		file_name = props.get_file_name(extra=extra),
		title = props.get_title(extra=extra),
		fig_include_title = props.fig_include_title,
		width = props.width,
		height = props.height,
		tags = props.tags,
		compress = props.get_compress(),
		logger = logger,
		close = close
	)

	if props.disk_save:
		file_name = props.get_file_name(extra=extra)
		if logger and getattr(logger, "verbose", 0) > 1:
			logger.debug("Saving %s/%s" % (props.disk_save, file_name))
		with open("%s/%s" % (props.disk_save, file_name), "w") as f:
			f.write(
				svg_doc.pop("svg_str") # type: ignore
				if props.get_compress() == 2
				else svg_doc['svg']
			)

	return svg_doc


def decompress_svg_dict(svg_dict: SVGRecord) -> SVGRecord:
	"""
	Modifies input dict by potentionaly decompressing compressed 'svg' value
	"""

	if not isinstance(svg_dict, dict):
		raise ValueError("Parameter svg_dict must be an instance of dict")

	if isinstance(svg_dict['svg'], bytes):
		svg_dict['svg'] = decompress_str(svg_dict['svg'])

	return svg_dict


def stack_svg(svg1: str, svg2: str, horizontally: bool = False, separator: bool = True) -> bytes:

	fig1 = su.transform.fromstring(svg1)
	fig2 = su.transform.fromstring(svg2)

	str_w1, str_h1 = fig1.get_size()
	str_w2, str_h2 = fig2.get_size()

	w1 = float(str_w1.replace("pt", ""))
	h1 = float(str_h1.replace("pt", ""))
	w2 = float(str_w2.replace("pt", ""))
	h2 = float(str_h2.replace("pt", ""))

	el1 = su.compose.Element(fig1.getroot().root)
	el2 = su.compose.Element(fig2.getroot().root)

	fig = su.transform.SVGFigure()

	if horizontally:
		el2.moveto(x=w1, y=0)
		fig.root.set("height", str_h1 if h1 > h2 else str_h2)
		fig.root.set("width", str(w1 + w2) + "pt")
	else:
		el2.moveto(x=0, y=h1)
		fig.root.set("height", str(h1 + h2) + "pt")
		fig.root.set("width", str_w1 if w1 > w2 else str_w2)

	fig.root.set("viewBox", "0 0 %s %s" % (fig.root.get("width"), fig.root.get("height")))
	fig.append(el1)
	fig.append(el2)

	if separator:
		if horizontally:
			fig.append(su.compose.Line(((w1, 0), (w1, h1 if h1 > h2 else h2))))
		else:
			fig.append(su.compose.Line(((0, h1), (w1 if w1 > w2 else w2, h1))))

	return fig.to_str()


def rescale(svg: str, scale: float = 1.0) -> str:

	# Get SVGFigure from file
	original = su.transform.fromstring(svg)

	# Original size is represetnted as string (examle: '600px'); convert to float
	original_width = float(original.width.split('.')[0])
	original_height = float(original.height.split('.')[0])

	scaled = su.transform.SVGFigure(
		original_width * scale,
		original_height * scale
	)

	# Get the root element
	svg_st = original.getroot()

	# Scale the root element
	svg_st.scale_xy(scale, scale)

	# Add scaled svg element to figure
	scaled.append(svg_st)

	return str(scaled.to_str(), "utf-8")
	# return scaled.to_str()


def to_png(content: str, dpi: int = 96) -> str:

	return '<img src="data:image/png;base64,' + str(
		base64.b64encode(
			Image(
				svg2png(
					bytestring=content,
					dpi=dpi
				),
			).data
		),
		"utf-8"
	) + '">'
