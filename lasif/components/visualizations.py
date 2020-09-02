#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import absolute_import

import math
import numpy as np
import os
import toml
from typing import List

from lasif.exceptions import LASIFError, LASIFNotFoundError

from .component import Component


class VisualizationsComponent(Component):
    """
    Component offering project visualization. Has to be initialized fairly
    late as it requires a lot of data to be present.

    :param communicator: The communicator instance.
    :param component_name: The name of this component for the communicator.
    """

    def plot_events(
        self,
        plot_type: str = "map",
        iteration: str = None,
        inner_boundary: bool = False,
    ):
        """
        Plots the domain and beachballs for all events on the map.

        :param plot_type: Determines the type of plot created.
            * ``map`` (default) - a map view of the events
            * ``depth`` - a depth distribution histogram
            * ``time`` - a time distribution histogram
        :type plot_type: str, optional
        :param iteration: Name of iteration, if given only events from that
            iteration will be plotted, defaults to None
        :type iteration: str, optional
        :param inner_boundary: Should we plot inner boundary of domain?
            defaults to False
        :type inner_boundary: bool, optional
        """
        from lasif import visualization

        if iteration:
            events_used = self.comm.events.list(iteration=iteration)
            events = {}
            for event in events_used:
                events[event] = self.comm.events.get(event)
            events = events.values()
        else:
            events = self.comm.events.get_all_events().values()

        if plot_type == "map":
            m, projection = self.plot_domain(inner_boundary=inner_boundary)
            visualization.plot_events(
                events, map_object=m,
            )
            if iteration:
                title = f"Event distribution for iteration: {iteration}"
            else:
                title = "Event distribution"
            m.set_title(title)
        elif plot_type == "depth":
            visualization.plot_event_histogram(events, "depth")
        elif plot_type == "time":
            visualization.plot_event_histogram(events, "time")
        else:
            msg = "Unknown plot_type"
            raise LASIFError(msg)

    def plot_event(
        self,
        event_name: str,
        weight_set: str = None,
        intersection_override: bool = None,
        inner_boundary: bool = False,
    ):
        """
        Plots information about one event on the map.

        :param event_name: Name of event
        :type event_name: str
        :param weight_set: Name of station weights set, defaults to None
        :type weight_set: str, optional
        :param intersection_override: boolean to require to have the same
            stations recording all events, i.e. the intersection of receiver
            sets. The intersection will consider two stations equal i.f.f. the
            station codes AND coordinates (LAT, LON, Z) are equal. If None is
            passed, the value use_only_intersection from the projects'
            configuration file is used, defaults to None
        :type intersection_override: bool, optional
        :param inner_boundary: binary whether the inner boundary should be drawn
            Only works well for convex domains, defaults to False
        :type inner_boundary: bool, optional
        """
        if not self.comm.events.has_event(event_name):
            msg = "Event '%s' not found in project." % event_name
            raise ValueError(msg)

        if weight_set:
            if not self.comm.weights.has_weight_set(weight_set):
                msg = f"Weight set {weight_set} not found in project."
                raise ValueError(msg)
            weight_set = self.comm.weights.get(weight_set)

        map_object, projection = self.plot_domain(
            inner_boundary=inner_boundary
        )

        from lasif import visualization

        # Get the event and extract information from it.
        event_info = self.comm.events.get(event_name)

        # Get a dictionary containing all stations that have data for the
        # current event.
        try:
            stations = self.comm.query.get_all_stations_for_event(
                event_name, intersection_override=intersection_override
            )
        except LASIFNotFoundError:
            pass
        else:
            # Plot the stations if it has some. This will also plot raypaths.
            visualization.plot_stations_for_event(
                map_object=map_object,
                station_dict=stations,
                event_info=event_info,
                weight_set=weight_set,
                print_title=True,
            )

        # Plot the earthquake star for one event.
        visualization.plot_events(
            events=[event_info], map_object=map_object,
        )

    def plot_domain(self, inner_boundary: bool = False):
        """
        Plots the simulation domain and the actual physical domain.

        :param inner_boundary: binary whether the inner boundary should be drawn
            Only works well for convex domains, defaults to False
        :type inner_boundary: bool, optional
        """
        return self.comm.project.domain.plot(
            plot_inner_boundary=inner_boundary
        )

    def plot_station_misfits(
        self, event_name: str, iteration: str, intersection_override=None,
    ):
        """
        Plot a map of the stations where misfit was computed for a specific
        event. The stations are colour coded by misfit.

        :param event_name: Name of event
        :type event_name: str
        :param iteration: Name of iteration
        :type iteration: str
        :param intersection_override: boolean to require to have the same
            stations recording all events, i.e. the intersection of receiver
            sets. The intersection will consider two stations equal i.f.f. the
            station codes AND coordinates (LAT, LON, Z) are equal. If None is
            passed, the value use_only_intersection from the projects'
            configuration file is used, defaults to None
        :type intersection_override: bool, optional
        """
        from lasif import visualization

        map_object, projection = self.plot_domain()
        event_info = self.comm.events.get(event_name)
        stations = self.comm.query.get_all_stations_for_event(
            event_name, intersection_override=intersection_override
        )
        long_iter = self.comm.iterations.get_long_iteration_name(iteration)
        misfit_toml = (
            self.comm.project.paths["iterations"] / long_iter / "misfits.toml"
        )
        iteration_misfits = toml.load(misfit_toml)
        station_misfits = iteration_misfits[event_info["event_name"]][
            "stations"
        ]
        misfitted_stations = {k: stations[k] for k in station_misfits.keys()}
        for k in misfitted_stations.keys():
            misfitted_stations[k]["misfit"] = station_misfits[k]

        visualization.plot_stations_for_event(
            map_object=map_object,
            station_dict=misfitted_stations,
            event_info=event_info,
            plot_misfits=True,
            raypaths=False,
            print_title=True,
        )

        visualization.plot_events(
            events=[event_info], map_object=map_object,
        )

    def plot_raydensity(
        self,
        save_plot: bool = True,
        plot_stations: bool = False,
        iteration: str = None,
        intersection_override: bool = None,
    ):
        """
        Plots the raydensity. The plot will have number of ray crossings
        indicated with a brighter colour.

        :param save_plot: Whether plot should be saved or displayed,
            defaults to True (saved)
        :type save_plot: bool, optional
        :param plot_stations: Do you want to plot stations on top of rays?
            defaults to False
        :type plot_stations: bool, optional
        :param iteration: Name of iteration that you only want events from,
            defaults to None
        :type iteration: str, optional
        :param intersection_override: boolean to require to have the same
            stations recording all events, i.e. the intersection of receiver
            sets. The intersection will consider two stations equal i.f.f. the
            station codes AND coordinates (LAT, LON, Z) are equal. If None is
            passed, the value use_only_intersection from the projects'
            configuration file is used, defaults to None
        :type intersection_override: bool, optional
        """
        from lasif import visualization
        import matplotlib.pyplot as plt

        plt.figure(figsize=(20, 12))

        map_object, projection = self.plot_domain()

        event_stations = []

        # We could just pass intersection_override to the
        # self.comm.query.get_all_stations_for_event call within the event loop
        # and get rid of the more complicated statement before it, however
        # precomputing stations when they're equal anyway saves a lot of time.

        # Determine if we should intersect or not
        use_only_intersection = self.comm.project.stacking_settings[
            "use_only_intersection"
        ]
        if intersection_override is not None:
            use_only_intersection = intersection_override

        # If we should intersect, precompute the stations for all events,
        # since the stations are equal for all events if using intersect.
        if use_only_intersection:
            intersect_with = self.comm.events.list()
            stations = self.comm.query.get_all_stations_for_event(
                intersect_with[0], intersection_override=True
            )

        for event_name, event_info in self.comm.events.get_all_events(
            iteration
        ).items():

            # If we're not intersecting, re-query all stations per event, as
            # the stations might change
            if not use_only_intersection:
                try:
                    stations = self.comm.query.get_all_stations_for_event(
                        event_name, intersection_override=use_only_intersection
                    )
                except LASIFError:
                    stations = {}
            event_stations.append((event_info, stations))

        visualization.plot_raydensity(
            map_object=map_object,
            station_events=event_stations,
            domain=self.comm.project.domain,
            projection=projection,
        )

        visualization.plot_events(
            self.comm.events.get_all_events(iteration).values(),
            map_object=map_object,
        )

        if plot_stations:
            visualization.plot_all_stations(
                map_object=map_object, event_stations=event_stations,
            )

        if save_plot:
            if iteration:
                outfile = os.path.join(
                    self.comm.project.paths["output"],
                    "raydensity_plots",
                    f"ITERATION_{iteration}",
                    "raydensity.png",
                )
                outfolder, _ = os.path.split(outfile)
                if not os.path.exists(outfolder):
                    os.makedirs(outfolder)
            else:
                outfile = os.path.join(
                    self.comm.project.get_output_folder(
                        type="raydensity_plots", tag="raydensity"
                    ),
                    "raydensity.png",
                )
            if os.path.isfile(outfile):
                os.remove(outfile)
            plt.savefig(outfile, dpi=200, transparent=False, overwrite=True)
            print("Saved picture at %s" % outfile)
        else:
            plt.show()

    def plot_all_rays(
        self,
        save_plot: bool = True,
        iteration: str = None,
        plot_stations: bool = True,
        intersection_override: bool = None,
    ):
        """
        Plot all the rays that are in the project or in a specific iteration.
        This is typically slower than the plot_raydensity function as this one
        is non-parallel

        :param save_plot: Should plot be saved, defaults to True
        :type save_plot: bool, optional
        :param iteration: Only events from an iteration, defaults to None
        :type iteration: str, optional
        :param plot_stations: Whether stations are plotted on top, defaults to
            True
        :type plot_stations: bool, optional
        :param intersection_override: boolean to require to have the same
            stations recording all events, i.e. the intersection of receiver
            sets. The intersection will consider two stations equal i.f.f. the
            station codes AND coordinates (LAT, LON, Z) are equal. If None is
            passed, the value use_only_intersection from the projects'
            configuration file is used, defaults to None
        :type intersection_override: bool, optional
        """
        from lasif import visualization
        import matplotlib.pyplot as plt

        plt.figure(figsize=(20, 12))

        map_object, projection = self.plot_domain()

        event_stations = []
        use_only_intersection = self.comm.project.stacking_settings[
            "use_only_intersection"
        ]
        if intersection_override is not None:
            use_only_intersection = intersection_override

        # If we should intersect, precompute the stations for all events,
        # since the stations are equal for all events if using intersect.
        if use_only_intersection:
            intersect_with = self.comm.events.list()
            stations = self.comm.query.get_all_stations_for_event(
                intersect_with[0], intersection_override=True
            )

        for event_name, event_info in self.comm.events.get_all_events(
            iteration
        ).items():

            # If we're not intersecting, re-query all stations per event, as
            # the stations might change
            if not use_only_intersection:
                try:
                    stations = self.comm.query.get_all_stations_for_event(
                        event_name, intersection_override=use_only_intersection
                    )
                except LASIFError:
                    stations = {}
            event_stations.append((event_info, stations))

        visualization.plot_all_rays(
            map_object=map_object, station_events=event_stations,
        )
        visualization.plot_events(
            events=self.comm.events.get_all_events(iteration).values(),
            map_object=map_object,
        )
        if plot_stations:
            visualization.plot_all_stations(
                map_object=map_object, event_stations=event_stations,
            )
        if save_plot:
            if iteration:
                outfile = os.path.join(
                    self.comm.project.paths["output"],
                    "ray_plots",
                    f"ITERATION_{iteration}",
                    "all_rays.png",
                )
                outfolder, _ = os.path.split(outfile)
                if not os.path.exists(outfolder):
                    os.makedirs(outfolder)
            else:
                outfile = os.path.join(
                    self.comm.project.get_output_folder(
                        type="ray_plots", tag="all_rays"
                    ),
                    "all_rays.png",
                )
            if os.path.isfile(outfile):
                os.remove(outfile)
            plt.savefig(outfile, dpi=200, transparent=False, overwrite=True)
            print("Saved picture at %s" % outfile)
        else:
            plt.show()

    def plot_windows(
        self,
        event: str,
        window_set_name: str,
        distance_bins: int = 500,
        ax=None,
        show: bool = True,
    ):
        """
        Plot all selected windows on a epicentral distance vs duration plot
        with the color encoding the selected channels. This gives a quick
        overview of how well selected the windows for a certain event and
        iteration are.

        :param event: The name of the event.
        :type event: str
        :param window_set_name: The window set.
        :type window_set_name: str
        :param distance_bins: The number of bins on the epicentral
            distance axis. Defaults to 500
        :type distance_bins: int, optional
        :param ax: If given, it will be plotted to this ax. Defaults to None
        :type ax: matplotlib.axes.Axes, optional
        :param show: If true, ``plt.show()`` will be called before returning.
            defaults to True
        :type show: bool, optional
        :return: The potentially created axes object.
        """
        from obspy.geodetics.base import locations2degrees

        event = self.comm.events.get(event)
        window_manager = self.comm.windows.read_all_windows(
            event=event["event_name"], window_set_name=window_set_name
        )
        starttime = event["origin_time"]
        duration = (
            self.comm.project.simulation_settings["end_time_in_s"]
            - self.comm.project.simulation_settings["start_time_in_s"]
        )

        # First step is to calculate all epicentral distances.
        stations = self.comm.query.get_all_stations_for_event(
            event["event_name"]
        )

        for s in stations.values():
            s["epicentral_distance"] = locations2degrees(
                event["latitude"],
                event["longitude"],
                s["latitude"],
                s["longitude"],
            )

        # Plot from 0 to however far it goes.
        min_epicentral_distance = 0
        max_epicentral_distance = math.ceil(
            max(_i["epicentral_distance"] for _i in stations.values())
        )
        epicentral_range = max_epicentral_distance - min_epicentral_distance

        if epicentral_range == 0:
            raise ValueError

        # Create the image that will represent the pictures in an epicentral
        # distance plot. By default everything is black.
        #
        # First dimension: Epicentral distance.
        # Second dimension: Time.
        # Third dimension: RGB tuple.
        len_time = 1000
        len_dist = distance_bins
        image = np.zeros((len_dist, len_time, 3), dtype=np.uint8)

        # Helper functions calculating the indices.
        def _time_index(value):
            frac = np.clip((value - starttime) / duration, 0, 1)
            return int(round(frac * (len_time - 1)))

        def _space_index(value):
            frac = np.clip(
                (value - min_epicentral_distance) / epicentral_range, 0, 1
            )
            return int(round(frac * (len_dist - 1)))

        def _color_index(channel):
            _map = {"Z": 2, "N": 1, "E": 0}
            channel = channel[-1].upper()
            if channel not in _map:
                raise ValueError
            return _map[channel]

        for station in window_manager:
            for channel in window_manager[station]:
                for win in window_manager[station][channel]:
                    image[
                        _space_index(stations[station]["epicentral_distance"]),
                        _time_index(win[0]) : _time_index(win[1]),
                        _color_index(channel),
                    ] = 255

        # From http://colorbrewer2.org/
        color_map = {
            (255, 0, 0): (228, 26, 28),  # red
            (0, 255, 0): (77, 175, 74),  # green
            (0, 0, 255): (55, 126, 184),  # blue
            (255, 0, 255): (152, 78, 163),  # purple
            (0, 255, 255): (255, 127, 0),  # orange
            (255, 255, 0): (255, 255, 51),  # yellow
            (255, 255, 255): (250, 250, 250),  # white
            (0, 0, 0): (50, 50, 50),  # More pleasent gray background
        }

        # Replace colors...fairly complex. Not sure if there is another way...
        red, green, blue = image[:, :, 0], image[:, :, 1], image[:, :, 2]
        for color, replacement in color_map.items():
            image[:, :, :][
                (red == color[0]) & (green == color[1]) & (blue == color[2])
            ] = replacement

        def _one(i):
            return [_i / 255.0 for _i in i]

        import matplotlib.pylab as plt

        plt.style.use("ggplot")

        artists = [
            plt.Rectangle((0, 1), 1, 1, color=_one(color_map[(0, 0, 255)])),
            plt.Rectangle((0, 1), 1, 1, color=_one(color_map[(0, 255, 0)])),
            plt.Rectangle((0, 1), 1, 1, color=_one(color_map[(255, 0, 0)])),
            plt.Rectangle((0, 1), 1, 1, color=_one(color_map[(0, 255, 255)])),
            plt.Rectangle((0, 1), 1, 1, color=_one(color_map[(255, 0, 255)])),
            plt.Rectangle((0, 1), 1, 1, color=_one(color_map[(255, 255, 0)])),
            plt.Rectangle(
                (0, 1), 1, 1, color=_one(color_map[(255, 255, 255)])
            ),
        ]
        labels = ["Z", "N", "E", "Z + N", "Z + E", "N + E", "Z + N + E"]

        if ax is None:
            plt.figure(figsize=(16, 9))
            ax = plt.gca()

        ax.imshow(
            image,
            aspect="auto",
            interpolation="nearest",
            vmin=0,
            vmax=255,
            origin="lower",
        )
        ax.grid()
        event_name = event["event_name"]
        ax.set_title(
            f"Selected windows for window set "
            f"{window_set_name} and event "
            f"{event_name}"
        )

        ax.legend(
            artists, labels, loc="lower right", title="Selected Components"
        )

        # Set the x-ticks.
        xticks = []
        for time in ax.get_xticks():
            # They are offset by -0.5.
            time += 0.5
            # Convert to actual time
            frac = time / float(len_time)
            time = frac * duration
            xticks.append("%.1f" % time)
        ax.set_xticklabels(xticks)
        ax.set_xlabel("Time since event in seconds")

        yticks = []
        for dist in ax.get_yticks():
            # They are offset by -0.5.
            dist += 0.5
            # Convert to actual epicentral distance.
            frac = dist / float(len_dist)
            dist = min_epicentral_distance + (frac * epicentral_range)
            yticks.append("%.1f" % dist)
        ax.set_yticklabels(yticks)
        ax.set_ylabel(
            "Epicentral distance in degree [Binned in %i distances]"
            % distance_bins
        )

        if show:
            plt.tight_layout()
            plt.show()
            plt.close()

        return ax

    def plot_window_statistics(
        self, window_set_name: str, events: List[str], ax=None, show=True
    ):
        """
        Plots the statistics of windows for one iteration.

        :param window_set_name: Name of window set
        :type window_set_name: str
        :param events: list of events
        :type events: List[str]
        :param ax: If given, it will be plotted to this ax. Defaults to None
        :type ax: matplotlib.axes.Axes, optional
        :param show: If true, ``plt.show()`` will be called before returning.
            defaults to True
        :type show: bool, optional

        :return: The potentially created axes object.
        """
        # Get the statistics.
        data = self.comm.windows.get_window_statistics(window_set_name, events)

        import matplotlib
        import matplotlib.pylab as plt
        import seaborn as sns

        if ax is None:
            plt.figure(figsize=(10, 6))
            ax = plt.gca()

        ax.invert_yaxis()

        pal = sns.color_palette("Set1", n_colors=4)

        total_count = []
        count_z = []
        count_n = []
        count_e = []
        event_names = []

        width = 0.2
        ind = np.arange(len(data))

        cm = matplotlib.cm.RdYlGn

        for _i, event in enumerate(sorted(data.keys())):
            d = data[event]
            event_names.append(event)
            total_count.append(d["total_station_count"])
            count_z.append(d["stations_with_vertical_windows"])
            count_n.append(d["stations_with_north_windows"])
            count_e.append(d["stations_with_east_windows"])

            if d["total_station_count"] == 0:
                frac = int(0)
            else:
                frac = int(
                    round(
                        100
                        * d["stations_with_windows"]
                        / float(d["total_station_count"])
                    )
                )

            color = cm(frac / 70.0)

            ax.text(
                -10,
                _i,
                "%i%%" % frac,
                fontdict=dict(fontsize="x-small", ha="right", va="top"),
                bbox=dict(boxstyle="round", fc=color, alpha=0.8),
            )

        ax.barh(
            ind,
            count_z,
            width,
            color=pal[0],
            label="Stations with Vertical Component Windows",
        )
        ax.barh(
            ind + 1 * width,
            count_n,
            width,
            color=pal[1],
            label="Stations with North Component Windows",
        )
        ax.barh(
            ind + 2 * width,
            count_e,
            width,
            color=pal[2],
            label="Stations with East Component Windows",
        )
        ax.barh(
            ind + 3 * width,
            total_count,
            width,
            color="0.4",
            label="Total Stations",
        )

        ax.set_xlabel("Station Count")

        ax.set_yticks(ind + 2 * width)
        ax.set_yticklabels(event_names)
        ax.yaxis.set_tick_params(pad=30)
        ax.set_ylim(len(data), -width)

        ax.legend(frameon=True)

        plt.suptitle(f"Window Statistics for window set {window_set_name}")

        plt.tight_layout()
        plt.subplots_adjust(top=0.95)

        if show:
            plt.show()

        return ax

    def plot_data_and_synthetics(
        self,
        event: str,
        iteration: str,
        channel_id: str,
        ax=None,
        show: bool = True,
    ):
        """
        Plots the data and corresponding synthetics for a given event,
        iteration, and channel.

        :param event: The event.
        :type event: str
        :param iteration: The iteration.
        :type iteration: str
        :param channel_id: The channel id.
        :type channel_id: str
        :param ax: If given, it will be plotted to this ax. Defaults to None
        :type ax: matplotlib.axes.Axes, optional
        :param show: If true, ``plt.show()`` will be called before returning.
            defaults to True
        :type show: bool, optional
        :return: The potentially created axes object.
        """
        import matplotlib.pylab as plt

        data = self.comm.query.get_matching_waveforms(
            event, iteration, channel_id
        )
        if ax is None:
            plt.figure(figsize=(15, 3))
            ax = plt.gca()

        iteration = self.comm.iterations.get(iteration)

        ax.plot(
            data.data[0].times(),
            data.data[0].data,
            color="black",
            label="observed",
        )
        ax.plot(
            data.synthetics[0].times(),
            data.synthetics[0].data,
            color="red",
            label="synthetic, iteration %s" % str(iteration.name),
        )
        ax.legend()

        ax.set_xlabel("Seconds since event")
        ax.set_ylabel("m/s")
        ax.set_title(channel_id)
        ax.grid()

        if iteration.scale_data_to_synthetics:
            ax.text(
                0.995,
                0.005,
                "data scaled to synthetics",
                horizontalalignment="right",
                verticalalignment="bottom",
                transform=ax.transAxes,
                color="0.2",
            )

        if show:
            plt.tight_layout()
            plt.show()
            plt.close()

        return ax

    def plot_section(
        self,
        event_name: str,
        data_type: str = "processed",
        component: str = "Z",
        num_bins: int = 1,
        traces_per_bin: int = 500,
    ):
        """
        Create a section plot of an event and store the plot in Output. Useful
        for quickly inspecting if an event is good for usage.

        :param event_name: Name of the event
        :type event_name: str
        :param data_type: The type of data, one of: raw, processed (default)
        :type data_type: str, optional
        :param component: Component of the data Z(default), N, E
        :type component: str, optional
        :param num_bins: number of offset bins, defaults to 1
        :type num_bins: int, optional
        :param traces_per_bin: number of traces per bin, defaults to 500
        :type traces_per_bin: int, optional
        """
        import pyasdf
        import obspy

        from pathlib import Path

        event = self.comm.events.get(event_name)
        tag = self.comm.waveforms.preprocessing_tag
        asdf_filename = self.comm.waveforms.get_asdf_filename(
            event_name=event_name, data_type=data_type, tag_or_iteration=tag
        )

        asdf_file = Path(asdf_filename)
        if not asdf_file.is_file():
            raise LASIFNotFoundError(f"Could not find {asdf_file.name}")

        ds = pyasdf.ASDFDataSet(asdf_filename)

        # get event coords
        ev_coord = [event["latitude"], event["longitude"]]

        section_st = obspy.core.stream.Stream()
        for station in ds.waveforms.list():
            sta = ds.waveforms[station]
            st = obspy.core.stream.Stream()

            tags = sta.get_waveform_tags()
            if tags:
                st = sta[tags[0]]

            st = st.select(component=component)
            if len(st) > 0:
                st[0].stats["coordinates"] = sta.coordinates
                lat = sta.coordinates["latitude"]
                lon = sta.coordinates["longitude"]
                offset = np.sqrt(
                    (ev_coord[0] - lat) ** 2 + (ev_coord[1] - lon) ** 2
                )
                st[0].stats["offset"] = offset

            section_st += st

        if num_bins > 1:
            section_st = get_binned_stream(
                section_st, num_bins=num_bins, num_bin_tr=traces_per_bin
            )
        else:
            section_st = section_st[:traces_per_bin]

        outfile = os.path.join(
            self.comm.project.get_output_folder(
                type="section_plots", tag=event_name, timestamp=False
            ),
            f"{tag}.png",
        )

        section_st.plot(
            type="section",
            dist_degree=True,
            ev_coord=ev_coord,
            scale=2.0,
            outfile=outfile,
        )
        print("Saved picture at %s" % outfile)


def get_binned_stream(section_st, num_bins, num_bin_tr):
    from obspy.core.stream import Stream

    # build array
    offsets = []
    idx = 0
    for tr in section_st:
        offsets += [[tr.stats.offset, idx]]
        idx += 1
    offsets = np.array(offsets)

    # define bins
    min_offset = np.min(offsets[:, 0])
    max_offset = np.max(offsets[:, 0])
    bins = np.linspace(min_offset, max_offset, num_bins + 1)

    # first bin
    extr_offsets = offsets[
        np.where(
            np.logical_and(offsets[:, 0] >= bins[0], offsets[:, 0] <= bins[1])
        )
    ][:num_bin_tr]

    # rest of bins
    for i in range(num_bins)[1:]:
        bin_start = bins[i]
        bin_end = bins[i + 1]

        offsets_bin = offsets[
            np.where(
                np.logical_and(
                    offsets[:, 0] > bin_start, offsets[:, 0] <= bin_end
                )
            )
        ][:num_bin_tr]
        extr_offsets = np.concatenate((extr_offsets, offsets_bin), axis=0)

    # write selected traces to new stream object
    selected_st = Stream()
    indices = extr_offsets[:, 1]

    for tr_idx in indices:
        selected_st += section_st[int(tr_idx)]
    return selected_st
