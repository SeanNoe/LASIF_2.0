#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import absolute_import

import lasif.visualization
from .window_region_item import WindowLinearRegionItem
from ..colors import COLORS
import sys
import random
import os
from obspy.taup import TauPyModel
from obspy.geodetics import locations2degrees
import matplotlib.patheffects as PathEffects
import inspect
import imp
from glob import iglob
from PyQt5 import QtGui
from PyQt5.QtCore import pyqtSlot
import pyqtgraph as pg
import cartopy as cp

# Default to antialiased drawing.
pg.setConfigOptions(antialias=True, foreground=(50, 50, 50), background=None)


taupy_model = TauPyModel("ak135")


def compile_and_import_ui_files():
    """
    Automatically compiles all .ui files found in the same directory as the
    application py file.
    They will have the same name as the .ui files just with a .py extension.

    Needs to be defined in the same file as function loading the gui as it
    modifies the globals to be able to automatically import the created py-ui
    files. Its just very convenient.
    """
    directory = os.path.dirname(
        os.path.abspath(inspect.getfile(inspect.currentframe()))
    )
    for filename in iglob(os.path.join(directory, "*.ui")):
        ui_file = filename
        py_ui_file = os.path.splitext(ui_file)[0] + os.path.extsep + "py"
        if not os.path.exists(py_ui_file) or (
            os.path.getmtime(ui_file) >= os.path.getmtime(py_ui_file)
        ):
            from PyQt5 import uic

            print("Compiling ui file: %s" % ui_file)
            with open(py_ui_file, "w") as open_file:
                uic.compileUi(ui_file, open_file)
        # Import the (compiled) file.
        try:
            import_name = os.path.splitext(os.path.basename(py_ui_file))[0]
            globals()[import_name] = imp.load_source(import_name, py_ui_file)
        except ImportError as e:
            print("Error importing %s" % py_ui_file)
            print(e.message)


path_effects = [PathEffects.withStroke(linewidth=5, foreground="white")]


class Window(QtGui.QMainWindow):
    def __init__(self, comm):
        QtGui.QMainWindow.__init__(self)
        self.comm = comm
        self.ui = qt_window.Ui_MainWindow()  # NOQA
        self.ui.setupUi(self)

        # Set up the map.
        self.map_figure = self.ui.mapView.fig

        _, self.projection = self.comm.project.domain.plot()
        self.map_ax = self.map_figure.add_axes(
            [0.0, 0.0, 1.0, 1.0], projection=self.projection
        )
        self.basemap, _ = self.comm.project.domain.plot(ax=self.map_ax)
        self._draw()
        self.ui.data_only_CheckBox.stateChanged.connect(
            self.on_data_only_CheckboxChanged
        )
        self.ui.compare_iterations_CheckBox.stateChanged.connect(
            self.on_compare_iterations_CheckboxChanged
        )
        self.ui.process_on_fly_CheckBox.stateChanged.connect(
            self.on_process_on_fly_CheckBoxChanged
        )
        self.ui.raw_data_CheckBox.stateChanged.connect(
            self.on_raw_data_CheckBoxChanged
        )
        self.ui.process_on_fly_CheckBox.setVisible(False)
        self.ui.iteration_2_label.setVisible(False)
        self.ui.iteration_2_selection_comboBox.setVisible(False)
        self.ui.raw_data_CheckBox.setVisible(False)
        # State of the map objects.
        self.current_mt_patches = []

        self.current_window_manager = None

        self.ui.status_label = QtGui.QLabel("")
        self.ui.statusbar.addPermanentWidget(self.ui.status_label)
        self.ui.iteration_selection_comboBox.addItems(
            self.comm.iterations.list()
        )
        self.ui.iteration_2_selection_comboBox.addItems(
            self.comm.iterations.list()
        )
        self.ui.window_set_selection_comboBox.addItems(
            self.comm.windows.list()
        )

        for component in ["z", "n", "e"]:
            p = getattr(self.ui, "%s_graph" % component)
            # p.setBackground(None)
            # for d in ("left", "bottom", "top", "right"):
            #     p.getAxis(d).setPen("#333")
            p.setLabel("left", "Displacement", units="m")
            p.setLabel("bottom", "Time since event", units="s")

            label = {"z": "vertical", "e": "east", "n": "north"}
            p.setTitle(label[component].capitalize() + " component")

        self.add_legend()

    def add_legend(self):
        # Hack to get a proper legend.
        if self.ui.e_graph.plotItem.legend is not None:
            self.ui.e_graph.plotItem.legend.scene().removeItem(
                self.ui.e_graph.plotItem.legend
            )
        self.ui.e_graph.addLegend(offset=(-2, 2))

        self.ui.e_graph.plot([0], [0], pen=pg.mkPen("k", width=2), name="Data")
        if self.ui.data_only_CheckBox.isChecked():
            return
        self.ui.e_graph.plot(
            [0], [0], pen=pg.mkPen("r", width=2), name="Synthetics"
        )
        if self.ui.compare_iterations_CheckBox.isChecked():
            self.ui.e_graph.plot(
                [0],
                [0],
                pen=pg.mkPen("#00b300", style=pg.QtCore.Qt.DashLine, width=2),
                name="Synthetics 2",
            )

    def _draw(self):
        self.map_figure.canvas.draw()

    def _reset_map_plot(self):
        self.basemap.clear()
        self.map_figure = self.ui.mapView.fig

        self.map_ax = self.map_figure.add_axes(
            [0.0, 0.0, 1.0, 1.0], projection=self.projection
        )
        self.basemap, _ = self.comm.project.domain.plot(ax=self.map_ax)
        self._draw()

    def _reset_all_plots(self):
        for component in ["z", "n", "e"]:
            p = getattr(self.ui, "%s_graph" % component)
            p.clear()
            p.setXRange(-1, 1)
            p.setYRange(-1, 1)

    @property
    def current_iteration(self):
        return str(self.ui.iteration_selection_comboBox.currentText())

    @property
    def comparison_iteration(self):
        return str(self.ui.iteration_2_selection_comboBox.currentText())

    @property
    def current_event(self):
        return str(self.ui.event_selection_comboBox.currentText())

    @property
    def current_window_set(self):
        return str(self.ui.window_set_selection_comboBox.currentText())

    @property
    def current_station(self):
        cur_item = self.ui.stations_listWidget.currentItem()
        if cur_item is None:
            return None
        return str(cur_item.text())

    @pyqtSlot(str)
    def on_iteration_selection_comboBox_currentIndexChanged(self, value):
        value = str(value).strip()
        if not value:
            return
        events = self.comm.events.list(iteration=self.current_iteration)

        self.ui.event_selection_comboBox.setEnabled(True)
        self.ui.event_selection_comboBox.clear()
        self.ui.event_selection_comboBox.addItems(events)
        if self.comm.project.simulation_settings["scale_data_to_synthetics"]:
            self.ui.status_label.setText(
                "Data scaled to synthetics for " "this iteration"
            )
        else:
            self.ui.status_label.setText("")

    @pyqtSlot(str)
    def on_window_set_selection_comboBox_currentIndexChanged(self, value):
        value = str(value).strip()
        if not value:
            return
        self.current_window_manager = self.comm.windows.get(value)
        self._reset_all_plots()

        if self.current_station is not None:
            self.on_stations_listWidget_currentItemChanged(True, False)

        self._update_event_map()

    def _update_raypath(self, coordinates):
        if hasattr(self, "_current_raypath") and self._current_raypath:
            for _i in self._current_raypath:
                _i.remove()

        event_info = self.comm.events.get(self.current_event)
        self._current_raypath = self.basemap.plot(
            [event_info["longitude"], coordinates["longitude"]],
            [event_info["latitude"], coordinates["latitude"]],
            color=COLORS[random.randint(0, len(COLORS) - 1)],
            lw=2,
            alpha=0.8,
            zorder=10,
            path_effects=path_effects,
            transform=cp.crs.Geodetic(),
        )
        self._draw()

    def _update_event_map(self):
        # for i in self.current_mt_patches:
        #     i.remove()
        # print(f"mt patch: {self.current_mt_patches}")
        # if self.current_mt_patches is not None:
        #     self.current_mt_patches.remove()

        # if hasattr(self, "current_mt_patches") and self.current_mt_patches:
        #     for _i in self.current_mt_patches:
        #         _i.remove()
        self._reset_map_plot()

        event = self.comm.events.get(self.current_event)

        self.current_mt_patches = lasif.visualization.plot_events(
            events=[event], map_object=self.basemap,
        )

        try:
            self.current_station_scatter.remove()
        except:
            pass

        stations = self.comm.query.get_all_stations_for_event(
            self.current_event
        )

        # Plot the stations. This will not plot raypaths.
        self.current_station_scatter = lasif.visualization.plot_stations_for_event(
            map_object=self.basemap,
            color="0.2",
            alpha=0.4,
            station_dict=stations,
            event_info=event,
            raypaths=False,
            print_title=False,
        )

        if hasattr(self, "_current_raypath") and self._current_raypath:
            for _i in self._current_raypath:
                _i.remove()
            self._current_raypath = []

        self._draw()

    @pyqtSlot(str)
    def on_event_selection_comboBox_currentIndexChanged(self, value):
        value = str(value).strip()
        if not value:
            return
        self.ui.stations_listWidget.clear()
        stations = self.comm.query.get_all_stations_for_event(
            value, list_only=True
        )
        self.ui.stations_listWidget.addItems(sorted(stations))
        self._reset_all_plots()
        self._update_event_map()

    def on_raw_data_CheckBoxChanged(self, state):
        self._reset_all_plots()
        current = self.ui.stations_listWidget.currentRow()
        self.on_stations_listWidget_currentItemChanged(current, None)

    def on_data_only_CheckboxChanged(self, state):
        # if not self.current_station:
        #     return
        self._reset_all_plots()
        self.add_legend()
        if state:
            self.ui.process_on_fly_CheckBox.setVisible(True)
            self.ui.raw_data_CheckBox.setVisible(True)
            self.ui.compare_iterations_CheckBox.setVisible(False)
        else:
            self.ui.process_on_fly_CheckBox.setVisible(False)
            self.ui.raw_data_CheckBox.setVisible(False)
            self.ui.compare_iterations_CheckBox.setVisible(True)
        current = self.ui.stations_listWidget.currentRow()
        self.on_stations_listWidget_currentItemChanged(current, None)

    def on_compare_iterations_CheckboxChanged(self, state):
        if state:
            self.ui.iteration_2_label.setVisible(True)
            self.ui.iteration_2_selection_comboBox.setVisible(True)
        else:
            self.ui.iteration_2_label.setVisible(False)
            self.ui.iteration_2_selection_comboBox.setVisible(False)
        self.add_legend()
        current = self.ui.stations_listWidget.currentRow()
        self.on_stations_listWidget_currentItemChanged(current, None)

    def on_process_on_fly_CheckBoxChanged(self, state):
        self._reset_all_plots()
        current = self.ui.stations_listWidget.currentRow()
        self.on_stations_listWidget_currentItemChanged(current, None)

    def on_stations_listWidget_currentItemChanged(self, current, previous):
        if current is None:
            return

        self._reset_all_plots()

        if self.ui.data_only_CheckBox.isChecked():
            if self.ui.raw_data_CheckBox.isChecked():
                try:
                    data = self.comm.waveforms.get_waveforms_raw(
                        self.current_event, self.current_station
                    )
                except Exception as e:
                    print(e)
                    return
            else:
                tag = self.comm.waveforms.preprocessing_tag
                try:
                    if self.ui.process_on_fly_CheckBox.isChecked():
                        print("Processing...")
                        data = self.comm.waveforms.get_waveforms_processed_on_the_fly(
                            self.current_event, self.current_station
                        )
                    else:
                        data = self.comm.waveforms.get_waveforms_processed(
                            self.current_event, self.current_station, tag
                        )
                except Exception as e:
                    print(e)
                    return
            coordinates = self.comm.query.get_coordinates_for_station(
                self.current_event, self.current_station
            )

            for component in ["Z", "N", "E"]:
                plot_widget = getattr(self.ui, "%s_graph" % component.lower())
                data_tr = [
                    tr
                    for tr in data
                    if tr.stats.channel[-1].upper() == component
                ]
                if data_tr:
                    tr = data_tr[0]
                    minimum_period = self.comm.project.simulation_settings[
                        "minimum_period"
                    ]
                    max_sampling_rate = 10.0 * (1.0 / minimum_period)
                    if tr.stats.sampling_rate > max_sampling_rate:
                        tr.interpolate(max_sampling_rate)
                    plot_widget.data_id = tr.id
                    times = tr.times()
                    plot_widget.plot(
                        times, tr.data, pen=pg.mkPen("k", width=2)
                    )
                    plot_widget.autoRange()
                    self._update_raypath(coordinates)
            return

        try:
            wave = self.comm.query.get_matching_waveforms(
                self.current_event,
                self.current_iteration,
                self.current_station,
            )

            if self.ui.compare_iterations_CheckBox.isChecked():
                comparison_wave = self.comm.query.get_matching_waveforms(
                    self.current_event,
                    self.comparison_iteration,
                    self.current_station,
                )

                # Scale the synthetics if required.
                if self.comm.project.simulation_settings[
                    "scale_data_to_synthetics"
                ]:
                    for original_syn in wave.synthetics:
                        synthetic_tr = [
                            tr
                            for tr in comparison_wave.synthetics
                            if tr.stats.channel[-1].lower()
                            == original_syn.stats.channel[-1].lower()
                        ][0]
                        scaling_factor = (
                            synthetic_tr.data.ptp() / original_syn.data.ptp()
                        )
                        # Store and apply the scaling.
                        synthetic_tr.stats.scaling_factor = scaling_factor
                        synthetic_tr.data /= scaling_factor
        except Exception as e:
            for component in ["Z", "N", "E"]:
                plot_widget = getattr(self.ui, "%s_graph" % component.lower())
                plot_widget.addItem(
                    pg.TextItem(
                        text=str(e), anchor=(0.5, 0.5), color=(200, 0, 0)
                    )
                )
            return

        event = self.comm.events.get(self.current_event)

        great_circle_distance = locations2degrees(
            event["latitude"],
            event["longitude"],
            wave.coordinates["latitude"],
            wave.coordinates["longitude"],
        )
        tts = taupy_model.get_travel_times(
            source_depth_in_km=event["depth_in_km"],
            distance_in_degree=great_circle_distance,
        )

        # Try to obtain windows for a station,
        # if it fails continue plotting the data
        try:
            windows_for_station = self.current_window_manager.get_all_windows_for_event_station(
                self.current_event, self.current_station
            )
        except:
            pass

        for component in ["Z", "N", "E"]:
            plot_widget = getattr(self.ui, "%s_graph" % component.lower())
            data_tr = [
                tr
                for tr in wave.data
                if tr.stats.channel[-1].upper() == component
            ]
            if data_tr:
                tr = data_tr[0]
                minimum_period = self.comm.project.simulation_settings[
                    "minimum_period"
                ]
                max_sampling_rate = 10.0 * (1.0 / minimum_period)
                if tr.stats.sampling_rate > max_sampling_rate:
                    tr.interpolate(max_sampling_rate)
                if tr.stats.sampling_rate > max_sampling_rate:
                    tr.resample(max_sampling_rate)
                plot_widget.data_id = tr.id
                times = tr.times()
                plot_widget.plot(times, tr.data, pen=pg.mkPen("k", width=2))
            else:
                plot_widget.data_id = None
            synth_tr = [
                _i
                for _i in wave.synthetics
                if _i.stats.channel[-1].upper() == component
            ]
            if synth_tr:
                tr = synth_tr[0]
                minimum_period = self.comm.project.simulation_settings[
                    "minimum_period"
                ]
                max_sampling_rate = 10.0 * (1.0 / minimum_period)
                if tr.stats.sampling_rate > max_sampling_rate:
                    tr.interpolate(max_sampling_rate)
                times = tr.times()
                plot_widget.plot(
                    times, tr.data, pen=pg.mkPen("r", width=2),
                )

            if self.ui.compare_iterations_CheckBox.isChecked():
                compare_synth_tr = [
                    _i
                    for _i in comparison_wave.synthetics
                    if _i.stats.channel[-1].upper() == component
                ]

                if compare_synth_tr:
                    tr = compare_synth_tr[0]
                    minimum_period = self.comm.project.simulation_settings[
                        "minimum_period"
                    ]
                    max_sampling_rate = 10.0 * (1.0 / minimum_period)
                    if tr.stats.sampling_rate > max_sampling_rate:
                        tr.interpolate(max_sampling_rate)
                    times = tr.times()
                    plot_widget.plot(
                        times,
                        tr.data,
                        pen=pg.mkPen(
                            "#00b300", style=pg.QtCore.Qt.DashLine, width=2
                        ),
                    )

            if data_tr or synth_tr:
                for tt in tts:
                    if tt.time >= times[-1]:
                        continue
                    if tt.name[0].lower() == "p":
                        pen = "#008c2866"
                    else:
                        pen = "#95000066"
                    plot_widget.addLine(x=tt.time, pen=pen, z=-10)

            plot_widget.autoRange()

            channel_name = None
            windows = []
            try:
                for channel in windows_for_station:
                    if channel[-1].upper() == component:
                        windows = windows_for_station[channel]
                        channel_name = channel
                if windows:
                    plot_widget.windows = windows
                    for win in windows:
                        WindowLinearRegionItem(
                            self.current_window_manager,
                            channel_name,
                            self.current_iteration,
                            start=win[0],
                            end=win[1],
                            event=event,
                            parent=plot_widget,
                            comm=self.comm,
                        )
            except:
                print(
                    f"no windows available for {component}-component of "
                    f"station {self.current_station}"
                )
        self._update_raypath(wave.coordinates)

    def on_reset_view_Button_released(self):
        for component in ["Z", "N", "E"]:
            getattr(self.ui, "%s_graph" % component.lower()).autoRange()

    def __add_window_to_plot_widget(self, plot_widget, x_1, x_2):
        id = plot_widget.data_id
        if id is None:
            QtGui.QMessageBox.information(
                self, "", "Can only create windows if data is available."
            )
            return

        channel_name = id
        event = self.comm.events.get(self.current_event)

        self.current_window_manager.add_window_to_event_channel(
            self.current_event,
            channel_name,
            start_time=event["origin_time"] + x_1,
            end_time=event["origin_time"] + x_2,
            weight=1.0,
        )

        self.on_stations_listWidget_currentItemChanged(True, False)

    def _add_window(self, origin, min_x, max_x):
        self.__add_window_to_plot_widget(origin, min_x, max_x)

    def on_next_Button_released(self):
        st = self.ui.stations_listWidget
        idx = st.currentIndex().row() + 1
        if idx >= st.count():
            return
        st.setCurrentRow(idx)

    def on_previous_Button_released(self):
        st = self.ui.stations_listWidget
        idx = st.currentIndex().row() - 1
        if idx < 0:
            return
        st.setCurrentRow(idx)

    def on_delete_station_Button_released(self):
        curRow = self.ui.stations_listWidget.currentRow()

        self.comm.waveforms.delete_station_from_raw(
            self.current_event, self.current_station
        )
        filename = self.comm.waveforms.get_asdf_filename(
            self.current_event, data_type="raw"
        )
        print(f"{self.current_station} was deleted from {filename}")
        self.ui.stations_listWidget.takeItem(curRow)

    def on_delete_all_Button_released(self):
        for component in ["Z", "N", "E"]:
            plot_widget = getattr(self.ui, "%s_graph" % component.lower())
            id = plot_widget.data_id
            if id:
                self.current_window_manager.del_all_windows_from_event_channel(
                    event_name=self.current_event, channel_name=id
                )
        self.on_stations_listWidget_currentItemChanged(True, False)

    def on_autoselect_Button_released(self):
        windows_for_event = self.current_window_manager.get_all_windows_for_event(
            self.current_event
        )
        if self.current_station in windows_for_event:
            windows_for_station = windows_for_event[self.current_station]
        else:
            windows_for_station = False

        if windows_for_station:
            QtGui.QMessageBox.information(
                self,
                "",
                "Autoselection only works if no windows exists for "
                "the station.",
            )
            return

        self.comm.windows.select_windows_for_station(
            self.current_event,
            self.current_iteration,
            self.current_station,
            self.current_window_set,
        )
        self.on_stations_listWidget_currentItemChanged(True, False)


def launch(comm):
    # Automatically compile all ui files if they have been changed.
    compile_and_import_ui_files()
    from PyQt5 import QtWidgets

    # Launch and open the window.
    app = QtWidgets.QApplication(sys.argv)
    window = Window(comm)

    # Move window to center of screen.
    window.move(
        app.desktop().screen().rect().center() - window.rect().center()
    )
    # Show and bring window to foreground.
    window.show()
    window.raise_()
    os._exit(app.exec_())
