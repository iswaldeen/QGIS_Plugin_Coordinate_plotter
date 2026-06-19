# QGIS Plugin - Coordinate Plotter

Coordinate Plotter allows users to quickly plot point coordinates. The plugin supports adding coordinates to existing point layers or creating temporary memory layers, with optional CRS selection and automatic map zooming to the plotted location.

<img src="coordinate_plotter/icons/coordinate_plotter_icon.png" width="100" height="100">

## Features
* Plotting coordinates to an existing point layer
* Creating and plotting to a temporary memory layer
* Using either the current project CRS or a custom CRS for temporary layers
* Automatic map zooming to plotted coordinates
* Automatic coordinate detection and parsing from pasted text
* Forward-compatible design for:

  * QGIS 3.x
  * QGIS 4.x
  * Qt5
  * Qt6

## Compatibility

Coordinate Plotter is actively developed and tested for:

* QGIS 3.28+
* PyQt5 / Qt5
* Forward compatibility with Qt6 and QGIS 4.x APIs where possible

The plugin avoids deprecated Qt and QGIS API usage where practical to support long-term maintainability.

## License

All content is licensed under the <a href="https://creativecommons.org/licenses/by-sa/3.0/">Creative Commons Attribution-ShareAlike 3.0 licence (CC BY-SA)</a>.