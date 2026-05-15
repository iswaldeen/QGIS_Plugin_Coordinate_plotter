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
    QgsFeature,
    QgsGeometry,
    QgsMapLayerProxyModel,
    QgsPointXY,
    QgsProject,
    QgsRectangle,
    QgsVectorLayer,
    QgsWkbTypes,
)

from .resources import *
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

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        self.actions = []
        self.menu = self.tr("&Coordinate Plotter")
        self.dlg = CoordinatePlotterDialog()
        
        # Style the help button as a circular help icon button.
        self.dlg.helppushButton.setFixedSize(32, 32)
        self.dlg.helppushButton.setToolTip("Open Coordinate Plotter help")

        self.dlg.helppushButton.setStyleSheet("""
            QPushButton {
                border-radius: 16px;
                border: 1px solid palette(mid);
                font-weight: bold;
                font-size: 16px;
                padding: 0px;
                background-color: palette(button);
            }

            QPushButton:hover {
                background-color: palette(light);
            }

            QPushButton:pressed {
                background-color: palette(midlight);
            }
        """)

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
        """Remove the plugin menu item and icon from the QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginMenu(self.menu, action)
            self.iface.removeToolBarIcon(action)

    def run(self):
        """Open the dialog and plot the entered coordinates if accepted."""
        if self.first_start:
            self.first_start = False

        self.dlg.buttonBox.button(QDialogButtonBox.Ok).setEnabled(False)
        self.layer_type_check()

        result = self.dlg.exec_()

        if result != QDialog.Accepted:
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
                    "Coordinate plotting",
                    "The selected CRS is not valid."
                )
                return

            crs_definition = selected_crs.authid() if selected_crs.authid() else selected_crs.toWkt()

            layer = QgsVectorLayer(
                "Point?crs={}".format(crs_definition),
                "Plotted Coordinate Layer",
                "memory"
            )

            if not layer.isValid():
                QMessageBox.critical(
                    self.iface.mainWindow(),
                    "Coordinate plotting",
                    "Failed to create the temporary point layer."
                )
                return

            QgsProject.instance().addMapLayer(layer)
            self.plot(layer)

    def selected_output_crs(self):
        """Return the CRS to use for a newly created temporary layer."""
        if self.dlg.crscheckBox.isChecked():
            return QgsProject.instance().crs()

        return self.dlg.mQgsProjectionSelectionWidget.crs()

    def plot(self, layer):
        """Plot a point feature using the coordinates entered in the dialog."""
        if layer is None:
            QMessageBox.warning(
                self.iface.mainWindow(),
                "Coordinate plotting",
                "No valid point layer was selected."
            )
            return

        if not isinstance(layer, QgsVectorLayer) or not layer.isValid():
            QMessageBox.warning(
                self.iface.mainWindow(),
                "Coordinate plotting",
                "The selected layer is not a valid vector layer."
            )
            return

        if QgsWkbTypes.geometryType(layer.wkbType()) != QgsWkbTypes.PointGeometry:
            QMessageBox.warning(
                self.iface.mainWindow(),
                "Coordinate plotting",
                "The selected layer is not a point layer."
            )
            return

        if not layer.isSpatial():
            QMessageBox.warning(
                self.iface.mainWindow(),
                "Coordinate plotting",
                "The selected layer does not support geometry."
            )
            return

        x = self.dlg.doubleSpinBox.value()
        y = self.dlg.doubleSpinBox_2.value()

        new_feature = QgsFeature(layer.fields())
        new_feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))

        was_editing = layer.isEditable()

        if not was_editing and not layer.startEditing():
            QMessageBox.critical(
                self.iface.mainWindow(),
                "Coordinate plotting",
                "Could not start editing on the selected layer."
            )
            return

        if not layer.addFeature(new_feature):
            if not was_editing:
                layer.rollBack()

            QMessageBox.critical(
                self.iface.mainWindow(),
                "Coordinate plotting",
                "Failed to add the coordinate to the selected layer."
            )
            return

        if not was_editing:
            if not layer.commitChanges():
                errors = "\n".join(layer.commitErrors())
                layer.rollBack()

                QMessageBox.critical(
                    self.iface.mainWindow(),
                    "Coordinate plotting",
                    "Failed to save the new coordinate.\n\n{}".format(errors)
                )
                return

        layer.updateExtents()
        layer.triggerRepaint()

        canvas = self.iface.mapCanvas()

        # Zoom around the plotted point using map units.
        scale = 50
        rect = QgsRectangle(
            x - scale,
            y - scale,
            x + scale,
            y + scale
        )

        canvas.setExtent(rect)
        canvas.refresh()

        QMessageBox.information(
            self.iface.mainWindow(),
            "Coordinate plotting",
            "Coordinates successfully plotted:\nX = {} Y = {}".format(x, y)
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
        self.dlg.buttonBox.button(QDialogButtonBox.Ok).setEnabled(enable_coordinates)

    def clean_dialogue(self):
        """Reset dialog controls to their default state."""
        self.dlg.doubleSpinBox.setValue(0)
        self.dlg.doubleSpinBox_2.setValue(0)

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
        self.dlg.buttonBox.button(QDialogButtonBox.Ok).setEnabled(False)
    
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

    def on_dialog_finished(self, result):
        """Reset the dialog if it is closed using Cancel or the window close button."""
        if result == QDialog.Rejected:
            self.clean_dialogue()