#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import absolute_import

import inspect
import re
import shutil
import pathlib
import obspy
import os
import io
import pytest
from unittest import mock

from lasif import LASIFNotFoundError, LASIFWarning

from lasif.components.events import EventsComponent
from lasif.components.project import Project
from lasif.components.communicator import Communicator


@pytest.fixture
# def comm():
#     """
#     Returns a communicator with an initialized events component.
#     """
#     data_dir = os.path.join(
#         os.path.dirname(
#             os.path.dirname(
#                 os.path.abspath(inspect.getfile(inspect.currentframe()))
#             )
#         ),
#         "data",
#         "example_project",
#         "DATA/EARTHQUAKES",
#     )
#     comm = Communicator()
#     # Add project comm with paths to this fake component.
#     comm.project = mock.MagicMock()
#     comm.project.paths = {"root": data_dir}
#     EventsComponent(data_dir, comm, "events")
#     return comm
def comm(tmpdir):
    proj_dir = os.path.join(
        os.path.dirname(
            os.path.dirname(
                os.path.abspath(inspect.getfile(inspect.currentframe()))
            )
        ),
        "data",
        "example_project",
    )
    tmpdir = str(tmpdir)
    shutil.copytree(proj_dir, os.path.join(tmpdir, "proj"))
    proj_dir = os.path.join(tmpdir, "proj")

    folder_path = pathlib.Path(proj_dir).absolute()
    project = Project(project_root_path=folder_path, init_project=False)

    return project.comm


def test_event_list(comm):
    assert sorted(comm.events.list()) == sorted(
        [
            "GCMT_event_TURKEY_Mag_5.1_2010-3-24-14-11",
            "GCMT_event_TURKEY_Mag_5.9_2011-5-19-20-15",
        ]
    )
    assert sorted(comm.events.list(iteration="2")) == sorted(
        ["GCMT_event_TURKEY_Mag_5.9_2011-5-19-20-15",]
    )


def test_event_count(comm):
    assert comm.events.count() == 2
    assert comm.events.count(iteration="2") == 1


def test_has_event(comm):
    assert comm.events.has_event("GCMT_event_TURKEY_Mag_5.1_2010-3-24-14-11")
    assert comm.events.has_event("GCMT_event_TURKEY_Mag_5.9_2011-5-19-20-15")
    assert not comm.events.has_event("random")


def test_get_event(comm):
    ev = comm.events.get("GCMT_event_TURKEY_Mag_5.1_2010-3-24-14-11")
    print(ev)
    ev["filename"] = os.path.basename(ev["filename"])
    assert ev == {
        "depth_in_km": 4.5,
        "event_name": "GCMT_event_TURKEY_Mag_5.1_2010-3-24-14-11",
        "filename": "GCMT_event_TURKEY_Mag_5.1_2010-3-24-14-11.h5",
        "latitude": 38.82,
        "longitude": 40.14,
        "m_pp": 3.56e16,
        "m_rp": -2.25e16,
        "m_rr": 5470000000000000.0,
        "m_rt": 2.26e16,
        "m_tp": 1.92e16,
        "m_tt": -4.11e16,
        "magnitude": 5.1,
        "magnitude_type": "Mwc",
        "origin_time": obspy.UTCDateTime(2010, 3, 24, 14, 11, 31),
        "region": u"TURKEY",
    }

    ev = comm.events.get("GCMT_event_TURKEY_Mag_5.9_2011-5-19-20-15")
    ev["filename"] = os.path.basename(ev["filename"])
    assert ev == {
        "depth_in_km": 7.0,
        "event_name": "GCMT_event_TURKEY_Mag_5.9_2011-5-19-20-15",
        "filename": "GCMT_event_TURKEY_Mag_5.9_2011-5-19-20-15.h5",
        "latitude": 39.15,
        "longitude": 29.1,
        "m_pp": -8.5e16,
        "m_rp": -5.3e16,
        "m_rr": -8.07e17,
        "m_rt": 2.8e16,
        "m_tp": -2.17e17,
        "m_tt": 8.92e17,
        "magnitude": 5.9,
        "magnitude_type": "Mwc",
        "origin_time": obspy.UTCDateTime(2011, 5, 19, 20, 15, 22, 900000),
        "region": u"TURKEY",
    }

    with pytest.raises(LASIFNotFoundError):
        comm.events.get("random")


def test_get_all_events(comm):
    events = {
        "GCMT_event_TURKEY_Mag_5.1_2010-3-24-14-11": comm.events.get(
            "GCMT_event_TURKEY_Mag_5.1_2010-3-24-14-11"
        ),
        "GCMT_event_TURKEY_Mag_5.9_2011-5-19-20-15": comm.events.get(
            "GCMT_event_TURKEY_Mag_5.9_2011-5-19-20-15"
        ),
    }
    assert events == comm.events.get_all_events()
    events = {
        "GCMT_event_TURKEY_Mag_5.9_2011-5-19-20-15": comm.events.get(
            "GCMT_event_TURKEY_Mag_5.9_2011-5-19-20-15"
        ),
    }
    assert events == comm.events.get_all_events(iteration="2")


def test_faulty_events(tmpdir, recwarn):
    import pyasdf

    tmpdir = str(tmpdir)
    file_1 = os.path.join(
        os.path.dirname(
            os.path.dirname(
                os.path.abspath(inspect.getfile(inspect.currentframe()))
            )
        ),
        "data",
        "example_project",
        "DATA",
        "EARTHQUAKES",
        "GCMT_event_TURKEY_Mag_5.1_2010-3-24-14-11.h5",
    )
    file_2 = os.path.join(
        os.path.dirname(
            os.path.dirname(
                os.path.abspath(inspect.getfile(inspect.currentframe()))
            )
        ),
        "data",
        "example_project",
        "DATA",
        "EARTHQUAKES",
        "GCMT_event_TURKEY_Mag_5.9_2011-5-19-20-15.h5",
    )
    with pyasdf.ASDFDataSet(file_1) as ds:
        cat = ds.events
    with pyasdf.ASDFDataSet(file_2) as ds:
        cat += ds.events[0]

    # Modify it to trigger all problems.
    temp = io.BytesIO()
    cat.write(temp, format="quakeml")
    temp.seek(0, 0)
    temp = temp.read()
    pattern = re.compile(r"<depth>.*?</depth>", re.DOTALL)
    temp = re.sub(pattern, "<depth></depth>", temp.decode())
    temp = re.sub(r"<type>.*?</type>", "<type></type>", temp)
    with open(os.path.join(tmpdir, "random.xml"), "wb") as fh:
        fh.write(temp.encode())

    with pyasdf.ASDFDataSet(os.path.join(tmpdir, "random.h5")) as ds:
        ds.add_quakeml(os.path.join(tmpdir, "random.xml"))

    comm = Communicator()
    comm.project = mock.MagicMock()
    comm.project.read_only_caches = False
    comm.project.paths = {"cache": tmpdir, "root": tmpdir}
    EventsComponent(tmpdir, comm, "events")

    event = comm.events.get("random")
    assert "contains no depth" in str(recwarn.pop(LASIFWarning).message)
    assert "Magnitude has no specified type" in str(
        recwarn.pop(LASIFWarning).message
    )

    # Assert the default values it will then take.
    assert event["depth_in_km"] == 0.0
    assert event["magnitude_type"] == "Mw"
