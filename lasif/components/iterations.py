#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import absolute_import

import glob
import os
from typing import Union, List

from .component import Component
import shutil


class IterationsComponent(Component):
    """
    Component dealing with the iterations of the project. Mostly an
    organizational component.

    :param communicator: The communicator instance.
    :param component_name: The name of this component for the communicator.
    """

    def __init__(self, communicator, component_name):
        self.__cached_iterations = {}
        super(IterationsComponent, self).__init__(communicator, component_name)

    def get_long_iteration_name(self, iteration_name: str):
        """
        Returns the long form of an iteration from its short or long name.

        >>> comm = getfixture('iterations_comm')
        >>> comm.iterations.get_long_iteration_name("1")
        'ITERATION_1'

        :param iteration_name: Name of iteration
        :type iteration_name: str
        """
        if iteration_name[:10] == "ITERATION_":
            iteration_name = iteration_name[10:]
        return "ITERATION_%s" % iteration_name

    def write_info_toml(self, iteration_name: str, simulation_type: str):
        """
        Write a toml file to store information related to how the important
        config settings were when input files were generated. This will
        create a new file when forward input files are generated.

        :param iteration_name: The iteration for which to write into toml
        :type iteration_name: str
        :param simulation_type: The type of simulation.
        :type simulation_type: str
        """
        import toml

        info_path = os.path.join(
            self.comm.project.paths["synthetics"],
            "INFORMATION",
            self.get_long_iteration_name(iteration_name),
        )
        toml_dic = {
            "simulation_settings": self.comm.project.simulation_settings,
            "salvus_settings": self.comm.project.salvus_settings,
        }

        if simulation_type == "adjoint":
            toml_dic["misfit_type"] = self.comm.project.optimization_settings[
                "misfit_type"
            ]

        info_file = os.path.join(info_path, f"{simulation_type}.toml")

        with open(info_file, "w") as fh:
            toml.dump(toml_dic, fh)
        print(f"Information about input files stored in {info_file}")

    def setup_directories_for_iteration(
        self,
        iteration_name: str,
        events: List[str],
        remove_dirs: bool = False,
        event_specific: bool = False,
    ):
        """
        Sets up the directory structure required for the iteration

        :param iteration_name: The iteration for which to create the folders.
        :type iteration_name: str
        :param events: which events are in the iteration
        :type events: List[str]
        :param remove_dirs: Boolean if set to True the iteration is removed,
            defaults to False
        :type remove_dirs: bool, optional
        :param event_specific: Will create specific folder for each model if
            inversion uses event specific meshes, defaults to False
        :type event_specific: bool, optional
        """
        long_iter_name = self.get_long_iteration_name(iteration_name)
        self._create_synthetics_folder_for_iteration(
            long_iter_name, remove_dirs
        )
        self._create_input_files_folder_for_iteration(
            long_iter_name, remove_dirs
        )
        self._create_adjoint_sources_and_windows_folder_for_iteration(
            long_iter_name, remove_dirs
        )
        self._create_model_folder_for_iteration(
            long_iter_name, events, event_specific, remove_dirs
        )
        self._create_iteration_folder_for_iteration(
            long_iter_name, remove_dirs
        )
        self._create_gradients_folder_for_iteration(
            long_iter_name, remove_dirs
        )

    def setup_iteration_toml(self, iteration_name: str):
        """
        Sets up a toml file which can be used to keep track of needed
        information related to the iteration. It can be used to specify which
        events to use and it can remember which input parameters were used.

        :param iteration_name: The iteration for which to create the folders.
        :type iteration_name: str
        """

        long_iter_name = self.get_long_iteration_name(iteration_name)

        path = self.comm.project.paths["iterations"]
        syn_folder = self.comm.project.paths["synthetics"]
        sim_folder = os.path.join(syn_folder, "INFORMATION", long_iter_name)
        file = os.path.join(path, long_iter_name, "central_info.toml")
        event_file = os.path.join(path, long_iter_name, "events_used.toml")
        forward_file = os.path.join(sim_folder, "forward.toml")
        adjoint_file = os.path.join(sim_folder, "adjoint.toml")
        step_file = os.path.join(sim_folder, "step_length.toml")

        toml_string = (
            f"# This toml file includes information relative to "
            f"this iteration: {iteration_name}. \n"
            f"# It contains direct information as well as paths "
            f"to other toml files with other information.\n \n"
            f"[events]\n"
            f"    # In this file you can modify the used events "
            f"in the iteration. \n    # This is what your "
            f"commands will read when you don't specify events.\n"
            f'    events_used = "{event_file}"\n\n'
            f"[simulations]\n"
            f"    # These files will be created or updated every "
            f"time"
            f" you generate input files for the respective "
            f"simulations.\n"
            f'    forward = "{forward_file}"\n'
            f'    adjoint = "{adjoint_file}"\n'
            f'    step_length = "{step_file}"\n\n'
            f"    # That's it, if you need more, contact "
            f"developers.\n"
        )
        with open(file, "w") as fh:
            fh.write(toml_string)
        print(f"Information about iteration stored in {file}")

    def setup_events_toml(self, iteration_name: str, events: List[str]):
        """
        Writes all events into a toml file. User can modify this if he wishes
        to use less events for this specific iteration. Lasif should be smart
        enough to know which events were used in which iteration.

        :param iteration_name: Name of iteration
        :type iteration_name: str
        :param events: List of events to include
        :type events: List[str]
        """
        long_iter_name = self.get_long_iteration_name(iteration_name)
        path = self.comm.project.paths["iterations"]

        event_file = os.path.join(path, long_iter_name, "events_used.toml")

        toml_string = (
            "# Here we store information regarding which events "
            "are "
            "used \n# User can remove events at will and Lasif "
            "should recognise it when input files are generated.\n"
            "# Everything related to using all events, should "
            "read this file and classify that as all events for "
            "iteration.\n\n"
            "[events]\n"
            "    events_used = ["
        )
        s = 0
        for event in events:
            if s == len(events) - 1:
                toml_string += "'" + event + "']"
            else:
                toml_string += "'" + event + "',\n"
            s += 1

        with open(event_file, "w") as fh:
            fh.write(toml_string)

    def _create_iteration_folder_for_iteration(
        self, long_iteration_name: str, remove_dirs: bool = False
    ):
        """
        Create folder for this iteration in the iteration information directory

        :param long_iteration_name: ITERATION_<name of iteration>
        :type long_iteration_name: str
        :param remove_dirs: Should we delete the iteration?, defaults to False
        :type remove_dirs: bool, optional
        """

        path = self.comm.project.paths["iterations"]

        folder = os.path.join(path, long_iteration_name)
        if not os.path.exists(folder):
            os.makedirs(folder)
        if remove_dirs:
            shutil.rmtree(folder)

    def _create_synthetics_folder_for_iteration(
        self, long_iteration_name: str, remove_dirs: bool = False
    ):
        """
        Create the synthetics folder if it does not yet exist.

        :param long_iteration_name: The iteration for which to create the
            folders. ITERATION_<name of iteration>
        :type long_iteration_name: str
        :param remove_dirs: Should we delete the iteration?, defaults to False
        :type remove_dirs: bool, optional
        """

        path = self.comm.project.paths["synthetics"]

        folder_eq = os.path.join(path, "EARTHQUAKES", long_iteration_name)
        folder_info = os.path.join(path, "INFORMATION", long_iteration_name)
        if not os.path.exists(folder_eq):
            os.makedirs(folder_eq)
        if not os.path.exists(folder_info):
            os.makedirs(folder_info)
        if remove_dirs:
            shutil.rmtree(folder_eq)
            shutil.rmtree(folder_info)

    def _create_input_files_folder_for_iteration(
        self, long_iteration_name: str, remove_dirs: bool = False
    ):
        """
        Create the synthetics folder if it does not yet exist.

        :param long_iteration_name: The iteration for which to create the
            folders. ITERATION_<name of iteration>
        :type long_iteration_name: str
        :param remove_dirs: Should we delete iteration?, defaults to False
        :type remove_dirs: bool, optional
        """
        path = self.comm.project.paths["salvus_files"]

        folder = os.path.join(path, long_iteration_name)
        if not os.path.exists(folder):
            os.makedirs(folder)
        if remove_dirs:
            shutil.rmtree(folder)

    def _create_adjoint_sources_and_windows_folder_for_iteration(
        self, long_iteration_name: str, remove_dirs: bool = False
    ):
        """
        Create the adjoint_sources_and_windows folder if it does not yet exist.

        :param long_iteration_name: The iteration for which to create the
            folders. ITERATION_<name of iteration>
        :type long_iteration_name: str
        :param remove_dirs: Should we delete the iteration?, defaults to False
        :type remove_dirs: bool, optional
        """
        path = self.comm.project.paths["adjoint_sources"]

        folder = os.path.join(path, long_iteration_name)
        if not os.path.exists(folder):
            os.makedirs(folder)
        if remove_dirs:
            shutil.rmtree(folder)

    def _create_model_folder_for_iteration(
        self,
        long_iteration_name: str,
        events: Union[str, List[str]],
        event_specific: bool = False,
        remove_dirs: bool = False,
    ):
        """
        Create the model folder if it does not yet exist.

        :param long_iteration_name: The iteration for which to create the
            folders. ITERATION_<name of iteration>
        :type long_iteration_name: str
        :param events: Events to include in iteration
        :type events: Union[str, List[str]]
        :param event_specific: Specific meshes per events, defaults to False
        :type event_specific: bool, optional
        :param remove_dirs: Should we delete the iteration?, defaults to False
        :type remove_dirs: bool, optional
        """
        path = self.comm.project.paths["models"]

        folder = os.path.join(path, long_iteration_name)
        if not os.path.exists(folder):
            os.makedirs(folder)
            if event_specific:
                if isinstance(events, str):
                    events = [events]
                for event in events:
                    event_mesh_folder = os.path.join(folder, event)
                    os.makedirs(event_mesh_folder)
        if remove_dirs:
            shutil.rmtree(folder)

    def _create_gradients_folder_for_iteration(
        self, long_iteration_name: str, remove_dirs: bool = False
    ):
        """
        Create the kernel folder if it does not yet exist.

        :param long_iteration_name: The iteration for which to create the
            folders. ITERATION_<name of iteration>
        :type long_iteration_name: str
        :param remove_dirs: Should we delete the iteration?, defaults to False
        :type remove_dirs: bool, optional
        """
        path = self.comm.project.paths["gradients"]

        folder = os.path.join(path, long_iteration_name)
        if not os.path.exists(folder):
            os.makedirs(folder)
        if remove_dirs:
            shutil.rmtree(folder)

    def list(self):
        """
        Returns a list of all the iterations known to LASIF.
        """
        files = [
            os.path.abspath(_i)
            for _i in glob.iglob(
                os.path.join(
                    self.comm.project.paths["iterations"], "ITERATION_*"
                )
            )
        ]
        iterations = [os.path.basename(_i)[10:] for _i in files]
        return sorted(iterations)

    def has_iteration(self, iteration_name: str):
        """
        Checks for existance of an iteration

        :param iteration_name: Name of iteration
        :type iteration_name: str
        """
        if iteration_name[:10] == "ITERATION_":
            iteration_name = iteration_name[10:]
        if iteration_name in self.list():
            return True
        return False
