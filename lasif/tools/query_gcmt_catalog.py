#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
:copyright:
    Lion Krischer (krischer@geophysik.uni-muenchen.de), 2014
:license:
    GNU General Public License, Version 3
    (http://www.gnu.org/copyleft/gpl.html)
"""
from lasif.utils import get_event_filename
import glob
import inspect
import numpy as np
import obspy
from obspy.core.event import Catalog
import os
import random
import pyasdf
import datetime
import shutil
from scipy.spatial import cKDTree

from lasif.exceptions import LASIFNotFoundError, LASIFError

EARTH_RADIUS = 6371.00


class SphericalNearestNeighbour(object):
    """
    Spherical nearest neighbour queries using scipy's fast
    kd-tree implementation.
    """

    def __init__(self, data):
        cart_data = self.spherical2cartesian(data)
        self.data = data
        self.kd_tree = cKDTree(data=cart_data, leafsize=10)

    def query(self, points, k=10):
        points = self.spherical2cartesian(points)
        d, i = self.kd_tree.query(points, k=k)
        return d, i

    @staticmethod
    def spherical2cartesian(data):
        """
        Converts an array of shape (x, 2) containing latitude/longitude
        pairs into an array of shape (x, 3) containing x/y/z assuming a
        radius of one for points on the surface of a sphere.
        """
        lat = data[:, 0]
        lng = data[:, 1]
        # Convert data from lat/lng to x/y/z, assume radius of 1
        colat = 90 - lat
        cart_data = np.empty((lat.shape[0], 3))

        cart_data[:, 0] = np.sin(np.deg2rad(colat)) * np.cos(np.deg2rad(lng))
        cart_data[:, 1] = np.sin(np.deg2rad(colat)) * np.sin(np.deg2rad(lng))
        cart_data[:, 2] = np.cos(np.deg2rad(colat))

        return cart_data


def _read_GCMT_catalog(min_year=None, max_year=None):
    """
    Helper function reading the GCMT data shipping with LASIF.

    :param min_year: The minimum year to read.
    :type min_year: int, optional
    :param max_year: The maximum year to read.
    :type max_year: int, optional
    """
    # easier tests
    if min_year is None:
        min_year = 0
    else:
        min_year = int(min_year)
    if max_year is None:
        max_year = 3000
    else:
        max_year = int(max_year)

    data_dir = os.path.join(
        os.path.dirname(
            os.path.dirname(
                os.path.abspath(inspect.getfile(inspect.currentframe()))
            )
        ),
        "data",
        "GCMT_Catalog",
    )
    available_years = [_i for _i in os.listdir(data_dir) if _i.isdigit()]
    available_years.sort()
    print(
        "LASIF currently contains GCMT data from %s to %s/%i."
        % (
            available_years[0],
            available_years[-1],
            len(
                glob.glob(
                    os.path.join(data_dir, available_years[-1], "*.ndk*")
                )
            ),
        )
    )

    available_years = [
        _i
        for _i in os.listdir(data_dir)
        if _i.isdigit() and (min_year <= int(_i) <= max_year)
    ]
    available_years.sort()

    print("Parsing the GCMT catalog. This might take a while...")
    cat = Catalog()
    for year in available_years:
        print("\tReading year %s ..." % year)
        for filename in glob.glob(os.path.join(data_dir, str(year), "*.ndk*")):
            cat += obspy.read_events(filename, format="ndk")

    return cat


def update_GCMT_catalog():
    """
    Helper function updating the GCMT data shipped with LASIF.
    """
    data_dir = os.path.join(
        os.path.dirname(
            os.path.dirname(
                os.path.abspath(inspect.getfile(inspect.currentframe()))
            )
        ),
        "data",
        "GCMT_Catalog",
    )

    start_year = 2005
    end_year = datetime.datetime.now().year
    years = np.arange(
        start_year, end_year + 1
    )  # begin and end year, does not include end
    months = [
        "jan",
        "feb",
        "mar",
        "apr",
        "may",
        "jun",
        "jul",
        "aug",
        "sep",
        "oct",
        "nov",
        "dec",
    ]

    web_address = "https://www.ldeo.columbia.edu/"
    web_address += "~gcmt/projects/CMT/catalog/NEW_MONTHLY"
    os.chdir(data_dir)
    for year in years:
        year_str = str(year)
        os.chdir(data_dir)
        web_address_year = web_address + f"/{year_str}/"

        if not os.path.exists(year_str):
            # check if january exists
            january = web_address_year + "jan" + year_str[-2:] + ".ndk"
            if os.system(f"wget -q --spider {january}") == 0:
                os.makedirs(year_str)
            else:
                print(f"Could not find anything yet for year: {year_str}")
                # nothing from this year, skip it
                continue

        os.chdir(year_str)
        for month in months:
            month_name = month + year_str[-2:] + ".ndk"
            filename = web_address_year + month_name
            if (
                not os.path.exists(month_name + ".tar.bz2")
                and os.system(f"wget -q --spider {filename}") == 0
            ):
                if (
                    os.system(f"wget -q {filename}") == 0
                    and os.system(
                        f"tar -cjf {month_name}.tar.bz2 {month_name}"
                    )
                    == 0
                ):
                    os.remove(month_name)
                    print(f"Successfully retrieved: {month_name}")


def add_new_events(
    comm,
    count,
    min_magnitude,
    max_magnitude,
    min_year=None,
    max_year=None,
    threshold_distance_in_km=50.0,
    return_events=False,
):
    min_magnitude = float(min_magnitude)
    max_magnitude = float(max_magnitude)

    # Get the catalog.
    cat = _read_GCMT_catalog(min_year=min_year, max_year=max_year)
    # Filter with the magnitudes
    cat = cat.filter(
        "magnitude >= %.2f" % min_magnitude,
        "magnitude <= %.2f" % max_magnitude,
    )

    # Filtering catalog to only contain events in the domain.
    print("Filtering to only include events inside domain...")
    # Coordinates and the Catalog will have the same order!
    temp_cat = Catalog()
    coordinates = []
    for event in cat:
        org = event.preferred_origin() or event.origins[0]
        if not comm.query.point_in_domain(
            org.latitude, org.longitude, org.depth
        ):
            continue
        temp_cat.events.append(event)
        coordinates.append((org.latitude, org.longitude))
    cat = temp_cat

    chosen_events = []
    if len(cat) == 0:
        print(
            "No valid events were found. Consider your query parameters "
            "and domain size and try again. Events might be inside"
            " your buffer elements as well."
        )
        return

    print("%i valid events remain. Starting selection process..." % len(cat))

    existing_events = comm.events.get_all_events().values()
    # Get the coordinates of all existing events.
    existing_coordinates = [
        (_i["latitude"], _i["longitude"]) for _i in existing_events
    ]
    existing_origin_times = [_i["origin_time"] for _i in existing_events]

    # Special case handling in case there are no preexisting events.
    if not existing_coordinates:
        idx = random.randint(0, len(cat) - 1)

        chosen_events.append(cat[idx])
        del cat.events[idx]
        existing_coordinates.append(coordinates[idx])
        del coordinates[idx]

        _t = cat[idx].preferred_origin() or cat[idx].origins[0]
        existing_origin_times.append(_t.time)

        count -= 1

    while count > 0:
        if not coordinates:
            print("\tNo events left to select from. Stopping here.")
            break
        # Build kdtree and query for the point furthest away from any other
        # point.
        kdtree = SphericalNearestNeighbour(np.array(existing_coordinates))
        distances = kdtree.query(np.array(coordinates), k=1)[0]
        idx = np.argmax(distances)

        event = cat[idx]
        coords = coordinates[idx]
        del cat.events[idx]
        del coordinates[idx]

        # Actual distance.
        distance = EARTH_RADIUS * distances[idx]

        if distance < threshold_distance_in_km:
            print(
                "\tNo events left with distance to the next closest event "
                "of more than %.1f km. Stopping here."
                % threshold_distance_in_km
            )
            break

        # Make sure it did not happen within one day of an existing event.
        # This should also filter out duplicates.
        _t = event.preferred_origin() or event.origins[0]
        origin_time = _t.time

        if (
            min([abs(origin_time - _i) for _i in existing_origin_times])
            < 86400
        ):
            print(
                "\tSelected event temporally to close to existing event. "
                "Will not be chosen. Skipping to next event."
            )
            continue

        print(
            "\tSelected event with the next closest event being %.1f km "
            "away." % distance
        )

        chosen_events.append(event)
        existing_coordinates.append(coords)
        count -= 1
    print("Selected %i events." % len(chosen_events))
    folder = os.path.join(comm.project.paths["root"], "tmp")
    os.mkdir(folder)
    data_dir = comm.project.paths["eq_data"]
    event_paths = []
    for event in chosen_events:
        filename = os.path.join(folder, get_event_filename(event, "GCMT"))
        Catalog(events=[event]).write(
            filename, format="quakeml", validate=True
        )
        asdf_filename = os.path.join(
            data_dir,
            get_event_filename(event, "GCMT").rsplit(".", 1)[0] + ".h5",
        )
        ds = pyasdf.ASDFDataSet(asdf_filename, compression="gzip-3")
        ds.add_quakeml(filename)
        event_paths.append(asdf_filename)
        print("Written %s" % (os.path.relpath(asdf_filename)))
    shutil.rmtree(folder)
    if return_events:
        return event_paths


def get_subset_of_events(comm, count, events, existing_events=None):
    """
    This function gets an optimally distributed set of events,
    NO QA.
    :param comm: LASIF communicator
    :param count: number of events to choose.
    :param events: list of event_names, from which to choose from. These
    events must be known to LASIF
    :param existing_events: list of events, that have been chosen already
    and should thus be excluded from the selected options, but are also
    taken into account when ensuring a good spatial distribution. The
    function assumes that there are no common occurences between
    events and existing events
    :return: a list of chosen events.
    """
    available_events = comm.events.list()

    if len(events) < count:
        raise LASIFError("Insufficient amount of events specified.")
    if not type(count) == int:
        raise ValueError("count should be an integer value.")
    if count < 1:
        raise ValueError("count should be at least 1.")
    for event in events:
        if event not in available_events:
            raise LASIFNotFoundError(f"event : {event} not known to LASIF.")

    if existing_events is None:
        existing_events = []
    else:
        for event in events:
            if event in existing_events:
                raise LASIFError(
                    f"event: {event} was existing already,"
                    f"but still supplied to choose from."
                )

    cat = obspy.Catalog()
    for event in events:
        event_file_name = comm.waveforms.get_asdf_filename(
            event, data_type="raw"
        )
        with pyasdf.ASDFDataSet(event_file_name, mode="r") as ds:
            ev = ds.events[0]
            # append event_name to comments, such that it can later be
            # retrieved
            ev.comments.append(event)
            cat += ev

    # Coordinates and the Catalog will have the same order!
    coordinates = []
    for event in cat:
        org = event.preferred_origin() or event.origins[0]
        coordinates.append((org.latitude, org.longitude))

    chosen_events = []
    existing_coordinates = []
    for event in existing_events:
        ev = comm.events.get(event)
        existing_coordinates.append((ev["latitude"], ev["longitude"]))

    # randomly start with one of the specified events
    if not existing_coordinates:
        idx = random.randint(0, len(cat) - 1)
        chosen_events.append(cat[idx])
        del cat.events[idx]
        existing_coordinates.append(coordinates[idx])
        del coordinates[idx]
        count -= 1

    while count:
        if not coordinates:
            print("\tNo events left to select from. Stopping here.")
            break
        # Build kdtree and query for the point furthest away from any other
        # point.
        kdtree = SphericalNearestNeighbour(np.array(existing_coordinates))
        distances = kdtree.query(np.array(coordinates), k=1)[0]
        idx = np.argmax(distances)

        event = cat[idx]
        coods = coordinates[idx]
        del cat.events[idx]
        del coordinates[idx]

        chosen_events.append(event)
        existing_coordinates.append(coods)
        count -= 1

    list_of_chosen_events = []
    for ev in chosen_events:
        list_of_chosen_events.append(ev.comments.pop())
    if len(list_of_chosen_events) < count:
        raise ValueError("Could not select a sufficient amount of events")

    return list_of_chosen_events
