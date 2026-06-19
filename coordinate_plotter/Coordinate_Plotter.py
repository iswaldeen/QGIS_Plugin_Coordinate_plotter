# -*- coding: utf-8 -*-
"""
/***************************************************************************
 CoordinatePlotter
                                 A QGIS plugin
 This plugin plots coordinates from user-inputted values.
 ***************************************************************************/
"""

import os.path

from qgis.PyQt.QtCore import QCoreApplication, QSettings, QTranslator, QUrl
from qgis.PyQt.QtGui import QIcon, QDesktopServices
from qgis.PyQt.QtWidgets import QAction, QMessageBox, QDialog, QDialogButtonBox, QButtonGroup

from qgis.core import (
    QgsCoordinateTransform,
    QgsFeature,
    QgsGeometry,
    QgsMapLayerProxyModel,
    QgsPointXY,
    QgsProject,
    QgsRectangle,
    QgsVectorLayer,
    QgsWkbTypes,
    QgsUnitTypes,
    edit
)

import math
import re
from . import resources
from .Coordinate_Plotter_dialog import CoordinatePlotterDialog


class CoordinatePlotter:
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        """Constructor."""
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)

        locale = QSettings().value("locale/userLocale", "")[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            "i18n",
            "CoordinatePlotter_{}.qm".format(locale)
        )

        self.translator = None

        if os.path.exists(locale_path):
            translator = QTranslator()

            if translator.load(locale_path):
                QCoreApplication.installTranslator(translator)
                self.translator = translator

        self.actions = []
        self.menu = self.tr("&Coordinate Plotter")
        self.dlg = CoordinatePlotterDialog()

        self.dlg.helppushButton.clicked.connect(self.open_help)

        # Limit the layer combo box to point layers only.
        self.dlg.mMapLayerComboBox.setFilters(QgsMapLayerProxyModel.PointLayer)

        # Set the CRS selector default to the current project CRS.
        self.dlg.crscheckBox.setChecked(True)
        self.dlg.mQgsProjectionSelectionWidget.setCrs(QgsProject.instance().crs())
        self.dlg.mQgsProjectionSelectionWidget.setEnabled(False)

        # Group the destination checkboxes so only one plotting option can be selected.
        self.button_group = QButtonGroup(self.dlg)
        self.button_group.addButton(self.dlg.layercheckBox)
        self.button_group.addButton(self.dlg.templayercheckBox)
        self.button_group.setExclusive(True)

        # Set the initial dialog state.
        self.clean_dialogue()

        # Update dialog controls when the plotting destination changes.
        self.dlg.templayercheckBox.stateChanged.connect(self.layer_type_check)
        self.dlg.layercheckBox.stateChanged.connect(self.layer_type_check)

        # Update CRS selector availability when "Use project CRS" changes.
        self.dlg.crscheckBox.stateChanged.connect(self.layer_type_check)

        # Update dialog controls when the selected layer changes.
        self.dlg.mMapLayerComboBox.layerChanged.connect(self.layer_type_check)
        
        self.dlg.coordinateLineEdit.textEdited.connect(
            self.apply_pasted_coordinate_text
        )

        self.dlg.mQgsProjectionSelectionWidget.crsChanged.connect(
            self.update_coordinate_labels
        )

        QgsProject.instance().crsChanged.connect(
            self.update_coordinate_labels
        )

        # Connect once only. Do not connect this in run().
        self.dlg.finished.connect(self.on_dialog_finished)
        self.first_start = None

    def tr(self, message):
        """Translate a string using the Qt translation API."""
        return QCoreApplication.translate("CoordinatePlotter", message)

    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None
    ):
        """Add a toolbar icon and/or menu item for the plugin action."""
        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            self.iface.addToolBarIcon(action)

        if add_to_menu:
            self.iface.addPluginToMenu(self.menu, action)

        self.actions.append(action)

        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""
        icon_path = ":/plugins/Coordinate_Plotter/icons/coordinate_plotter_icon.png"

        self.add_action(
            icon_path,
            text=self.tr("Plot coordinates"),
            callback=self.run,
            parent=self.iface.mainWindow()
        )

        self.first_start = True

    def unload(self):
        """Remove plugin actions and translators from the QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginMenu(self.menu, action)
            self.iface.removeToolBarIcon(action)

        self.actions.clear()

        if self.translator is not None:
            QCoreApplication.removeTranslator(self.translator)
            self.translator = None

    def run(self):
        """Open the dialog and plot the entered coordinates if accepted."""
        if self.first_start:
            self.first_start = False

        self.set_ok_button_enabled(False)
        self.layer_type_check()

        result = self.exec_dialog()

        if result != self.dialog_accepted_code():
            return

        if self.dlg.layercheckBox.isChecked():
            layer = self.dlg.mMapLayerComboBox.currentLayer()
            self.plot(layer)
            return

        if self.dlg.templayercheckBox.isChecked():
            selected_crs = self.selected_output_crs()

            if not selected_crs.isValid():
                QMessageBox.warning(
                    self.iface.mainWindow(),
                    self.tr("Coordinate plotting"),
                    self.tr("The selected CRS is not valid.")
                )
                return

            layer = QgsVectorLayer(
                "Point",
                self.next_temporary_layer_name(),
                "memory"
            )

            if layer.isValid():
                layer.setCrs(selected_crs)

            if not layer.isValid():
                QMessageBox.critical(
                    self.iface.mainWindow(),
                    self.tr("Coordinate plotting"),
                    self.tr("Failed to create the temporary point layer.")
                )
                return

            QgsProject.instance().addMapLayer(layer)
            self.plot(layer)
    
    def exec_dialog(self):
        """Execute the dialog in a QGIS 3 / QGIS 4 compatible way."""
        if hasattr(self.dlg, "exec"):
            return self.dlg.exec()

        return self.dlg.exec_()

    def selected_output_crs(self):
        """Return the CRS to use for a newly created temporary layer."""
        if self.dlg.crscheckBox.isChecked():
            return QgsProject.instance().crs()

        return self.dlg.mQgsProjectionSelectionWidget.crs()
    
    def ensure_layer_visible(self, layer):
        """Switch on layer visibility if the plotted layer is currently hidden."""
        layer_tree_layer = QgsProject.instance().layerTreeRoot().findLayer(layer.id())

        if layer_tree_layer is None:
            return False

        if layer_tree_layer.isVisible():
            return False

        layer_tree_layer.setItemVisibilityChecked(True)
        return True
    
    def next_temporary_layer_name(self):
        """Return the next available sequential temporary layer name."""
        base_name = self.tr("Plotted Coordinate Layer")
        existing_names = {
            layer.name()
            for layer in QgsProject.instance().mapLayers().values()
        }

        if base_name not in existing_names:
            return base_name

        index = 2

        while f"{base_name} {index}" in existing_names:
            index += 1

        return f"{base_name} {index}"

    def plot(self, layer):
        """Plot a point feature using the coordinates entered in the dialog."""
        if layer is None:
            QMessageBox.warning(
                self.iface.mainWindow(),
                self.tr("Coordinate plotting"),
                self.tr("No valid point layer was selected.")
            )
            return

        if not isinstance(layer, QgsVectorLayer) or not layer.isValid():
            QMessageBox.warning(
                self.iface.mainWindow(),
                self.tr("Coordinate plotting"),
                self.tr("The selected layer is not a valid vector layer.")
            )
            return

        if QgsWkbTypes.geometryType(layer.wkbType()) != QgsWkbTypes.PointGeometry:
            QMessageBox.warning(
                self.iface.mainWindow(),
                self.tr("Coordinate plotting"),
                self.tr("The selected layer is not a point layer.")
            )
            return

        if not layer.isSpatial():
            QMessageBox.warning(
                self.iface.mainWindow(),
                self.tr("Coordinate plotting"),
                self.tr("The selected layer does not support geometry.")
            )
            return

        if self.dlg.coordinateLineEdit.text().strip():
            if not self.apply_pasted_coordinate_text(show_warning=True):
                return

        x = self.dlg.doubleSpinBox.value()
        y = self.dlg.doubleSpinBox_2.value()

        if not math.isfinite(x) or not math.isfinite(y):
            QMessageBox.warning(
                self.iface.mainWindow(),
                self.tr("Coordinate plotting"),
                self.tr("Invalid coordinate values.")
            )
            return

        new_feature = QgsFeature(layer.fields())
        new_feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
        
        was_editing = layer.isEditable()

        try:
            if was_editing:
                if not layer.addFeature(new_feature):
                    raise RuntimeError(self.tr("Failed to add feature."))
            else:
                with edit(layer):
                    if not layer.addFeature(new_feature):
                        raise RuntimeError(self.tr("Failed to add feature."))

        except Exception as exc:
            QMessageBox.critical(
                self.iface.mainWindow(),
                self.tr("Coordinate plotting"),
                self.tr("Failed to add the coordinate.") + f"\n\n{exc}"
            )
            return

        layer.updateExtents()
        layer.triggerRepaint()
        
        layer_visibility_enabled = self.ensure_layer_visible(layer)

        canvas = self.iface.mapCanvas()

        source_crs = layer.crs()
        destination_crs = canvas.mapSettings().destinationCrs()
        center = QgsPointXY(x, y)

        if source_crs.isValid() and destination_crs.isValid() and source_crs != destination_crs:
            transform = QgsCoordinateTransform(
                source_crs,
                destination_crs,
                QgsProject.instance()
            )
            center = transform.transform(center)

        current_extent = canvas.extent()
        width = current_extent.width() * 0.1
        height = current_extent.height() * 0.1

        rect = QgsRectangle(
            center.x() - width,
            center.y() - height,
            center.x() + width,
            center.y() + height
        )

        canvas.setExtent(rect)
        canvas.refresh()

        message = self.tr("Coordinates successfully plotted:\nX = {} Y = {}").format(x, y)

        if layer_visibility_enabled:
            message += (
                self.tr("\n\nThe selected layer was hidden, so its visibility "
                "has been turned on.")
            )

        # If the layer was already in edit mode before plotting,
        # the new feature has not yet been permanently saved.
        if was_editing:
            message += (
                self.tr("\n\nThe layer is still in edit mode. "
                "Save edits to permanently store the new point.")
            )

        QMessageBox.information(
            self.iface.mainWindow(),
            self.tr("Coordinate plotting"),
            message
        )

        self.clean_dialogue()

    def layer_type_check(self):
        """Update dialog controls based on the selected plotting destination and CRS option."""
        create_temp_layer = self.dlg.templayercheckBox.isChecked()
        use_existing_layer = self.dlg.layercheckBox.isChecked()
        selected_layer = self.dlg.mMapLayerComboBox.currentLayer()

        # CRS selection only applies when creating a new temporary layer.
        # Existing layers already have their own CRS, so the CRS option must not remain unchecked.
        if use_existing_layer:
            self.dlg.crscheckBox.blockSignals(True)
            self.dlg.crscheckBox.setChecked(True)
            self.dlg.crscheckBox.blockSignals(False)

        use_project_crs = self.dlg.crscheckBox.isChecked()

        enable_layer_combo = use_existing_layer
        enable_coordinates = create_temp_layer or (
            use_existing_layer and selected_layer is not None
        )

        self.dlg.crscheckBox.setEnabled(create_temp_layer)
        self.dlg.mQgsProjectionSelectionWidget.setEnabled(
            create_temp_layer and not use_project_crs
        )

        self.dlg.mMapLayerComboBox.setEnabled(enable_layer_combo)
        self.dlg.doubleSpinBox.setEnabled(enable_coordinates)
        self.dlg.doubleSpinBox_2.setEnabled(enable_coordinates)
        self.set_ok_button_enabled(enable_coordinates)
        
        self.dlg.coordinateLineEdit.setEnabled(enable_coordinates)
        self.update_coordinate_labels()
     
    def active_coordinate_crs(self):
        """Return the CRS expected by the coordinate input fields."""
        if self.dlg.layercheckBox.isChecked():
            layer = self.dlg.mMapLayerComboBox.currentLayer()

            if isinstance(layer, QgsVectorLayer) and layer.isValid():
                return layer.crs()

        return self.selected_output_crs()

    def update_coordinate_labels(self):
        """Update coordinate labels to match the active plotting CRS."""
        crs = self.active_coordinate_crs()

        if crs.isValid():
            unit_name = QgsUnitTypes.toString(crs.mapUnits())
        else:
            unit_name = self.tr("map units")

        if crs.isValid() and crs.isGeographic():
            self.dlg.label_2.setText(self.tr("Longitude / X (degrees)"))
            self.dlg.label_3.setText(self.tr("Latitude / Y (degrees)"))
            self.dlg.coordinateHintLabel.setText(
                self.tr(
                    "Paste a longitude/latitude or latitude/longitude pair. "
                    "Google Maps style latitude, longitude values are detected where possible."
                )
            )
        else:
            self.dlg.label_2.setText(
                self.tr("Easting / X ({})").format(unit_name)
            )
            self.dlg.label_3.setText(
                self.tr("Northing / Y ({})").format(unit_name)
            )
            self.dlg.coordinateHintLabel.setText(
                self.tr(
                    "Paste two coordinate values separated by a comma, space, tab, slash or semicolon."
                )
            )

    def apply_pasted_coordinate_text(self, show_warning=False):
        """Parse a pasted coordinate pair and copy it into the coordinate fields."""
        text = self.dlg.coordinateLineEdit.text().strip()

        if not text:
            return True

        values = re.findall(
            r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?",
            text
        )

        if len(values) != 2:
            if show_warning:
                QMessageBox.warning(
                    self.iface.mainWindow(),
                    self.tr("Coordinate plotting"),
                    self.tr("Please paste exactly two coordinate values.")
                )

            return False

        first_value = float(values[0])
        second_value = float(values[1])

        crs = self.active_coordinate_crs()

        if crs.isValid() and crs.isGeographic():
            # Google Maps commonly copies coordinates as latitude, longitude.
            # QGIS coordinate fields still expect X/Y, i.e. longitude/latitude.
            if (
                -90 <= first_value <= 90
                and -180 <= second_value <= 180
                and abs(first_value) > abs(second_value)
            ):
                x = second_value
                y = first_value
            else:
                x = first_value
                y = second_value

            if not (-180 <= x <= 180 and -90 <= y <= 90):
                if show_warning:
                    QMessageBox.warning(
                        self.iface.mainWindow(),
                        self.tr("Coordinate plotting"),
                        self.tr(
                            "The pasted longitude/latitude values are outside "
                            "the valid range for a geographic CRS."
                        )
                    )

                return False
        else:
            x = first_value
            y = second_value

        self.dlg.doubleSpinBox.setValue(x)
        self.dlg.doubleSpinBox_2.setValue(y)

        return True
        
    def dialog_accepted_code(self):
        """Return QDialog accepted result code for Qt5/Qt6 compatibility."""
        return getattr(QDialog, "DialogCode", QDialog).Accepted

    def dialog_rejected_code(self):
        """Return QDialog rejected result code for Qt5/Qt6 compatibility."""
        return getattr(QDialog, "DialogCode", QDialog).Rejected

    def clean_dialogue(self):
        """Reset dialog controls to their default state."""
        self.dlg.doubleSpinBox.setValue(0)
        self.dlg.doubleSpinBox_2.setValue(0)
        
        self.dlg.coordinateLineEdit.clear()
        self.dlg.coordinateLineEdit.setEnabled(False)

        self.button_group.setExclusive(False)
        self.dlg.layercheckBox.setChecked(False)
        self.dlg.templayercheckBox.setChecked(False)
        self.button_group.setExclusive(True)

        # Default CRS behaviour: use current project CRS.
        self.dlg.crscheckBox.setChecked(True)
        self.dlg.crscheckBox.setEnabled(False)
        self.dlg.mQgsProjectionSelectionWidget.setCrs(QgsProject.instance().crs())
        self.dlg.mQgsProjectionSelectionWidget.setEnabled(False)

        self.dlg.mMapLayerComboBox.setEnabled(False)
        self.dlg.doubleSpinBox.setEnabled(False)
        self.dlg.doubleSpinBox_2.setEnabled(False)
        self.set_ok_button_enabled(False)
        self.dlg.templayercheckBox.setChecked(True)
    
    def open_help(self):
        """Open the plugin help documentation in the default web browser."""
        help_path = os.path.join(
            self.plugin_dir,
            "help",
            "help.html"
        )

        if not os.path.exists(help_path):
            QMessageBox.warning(
                self.iface.mainWindow(),
                "Coordinate Plotter",
                "Help file could not be found."
            )
            return

        if not QDesktopServices.openUrl(QUrl.fromLocalFile(help_path)):
            QMessageBox.warning(
                self.iface.mainWindow(),
                "Coordinate Plotter",
                "The help file exists, but could not be opened."
            )
    
    def ok_button(self):
        """Return the dialog OK button in a QGIS 3 / QGIS 4 compatible way."""
        ok_role = getattr(QDialogButtonBox, "StandardButton", QDialogButtonBox).Ok
        return self.dlg.buttonBox.button(ok_role)


    def set_ok_button_enabled(self, enabled):
        """Enable or disable the OK button if it exists."""
        button = self.ok_button()

        if button is not None:
            button.setEnabled(enabled)

    def on_dialog_finished(self, result):
        """Reset the dialog if it is closed using Cancel or the window close button."""
        if result == self.dialog_rejected_code():
            self.clean_dialogue()