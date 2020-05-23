"""
Classes handling the domain definition and associated functionality for LASIF.
It can handle complex domains defined by HDF5 Salvus meshes. Otherwise it
uses more simple domains which are just defined as min/max lat/lon
coordinates.


:copyright:
    Solvi Thrastarson, (soelvi.thrastarson@erdw.ethz.ch) 2019

:license:
    GNU General Public License, Version 3
    (http://www.gnu.org/copyleft/gpl.html)
"""
import pathlib
import typing
import cartopy as cp
import matplotlib


import numpy as np
import h5py
from scipy.spatial import cKDTree

from lasif.exceptions import LASIFNotFoundError, LASIFError
from lasif.rotations import lat_lon_radius_to_xyz, xyz_to_lat_lon_radius


class HDF5Domain:
    """
    A class which handles domains based on HDF5 Salvus meshes
    """

    def __init__(
        self,
        mesh_file: typing.Union[str, pathlib.Path],
        absorbing_boundary_length: float,
    ):
        self.mesh_file = str(mesh_file)
        self.absorbing_boundary_length = absorbing_boundary_length * 1000.0
        self.r_earth = 6371000
        self.m = None
        self.is_global_mesh = False
        self.domain_edge_tree = None
        self.earth_surface_tree = None
        self.approx_elem_width = None
        self.domain_edge_coords = None
        self.earth_surface_coords = None
        self.KDTrees_initialized = False
        self.min_lat = None
        self.max_lat = None
        self.min_lon = None
        self.max_lon = None
        self.max_depth = None
        self.center_lat = None
        self.center_lon = None
        self.is_read = False
        self.side_set_names = None
        self.boundary = None

    def _read(self):
        """
        Reads the HDF5 file and gathers basic information such as the
        coordinates of the edge nodes. In the case of domain that spans
        the entire earth, all points will lie inside the domain, therefore
        further processing is not necessary.
        """
        try:
            self.m = h5py.File(self.mesh_file, mode="r")
        except AssertionError:
            msg = (
                "Could not open the project's mesh file. "
                "Please ensure that the path specified "
                "in config is correct."
            )
            raise LASIFNotFoundError(msg)

        # if less than 2 side sets, this must be a global mesh.  Return
        self.side_set_names = list(self.m["SIDE_SETS"].keys())
        if (
            len(self.side_set_names) <= 2
            and "outer_boundary" not in self.side_set_names
        ):
            self.is_global_mesh = True
            self.min_lat = -90.0
            self.max_lat = 90.0
            self.min_lon = -180.0
            self.max_lon = 180.0
            return
        if "a0" in self.side_set_names:
            self.is_global_mesh = True
            self.min_lat = -90.0
            self.max_lat = 90.0
            self.min_lon = -180.0
            self.max_lon = 180.0
            return

        side_elements = []
        earth_surface_elements = []
        earth_bottom_elements = []
        for side_set in self.side_set_names:
            if side_set == "surface":
                continue
            elif side_set == "r0":
                earth_bottom_elements = self.m["SIDE_SETS"][side_set][
                    "elements"
                ][()]

            elif side_set == "r1":
                earth_surface_elements = self.m["SIDE_SETS"][side_set][
                    "elements"
                ][()]
            elif side_set == "r1_ol":
                earth_surface_elements = self.m["SIDE_SETS"][side_set][
                    "elements"
                ][()]

            else:
                side_elements.append(
                    self.m["SIDE_SETS"][side_set]["elements"][()]
                )

        side_elements_tmp = np.array([], dtype=np.int)
        for i in range(len(side_elements)):
            side_elements_tmp = np.concatenate(
                (side_elements_tmp, side_elements[i])
            )

        # Remove Duplicates
        side_elements = np.unique(side_elements_tmp)

        # Get node numbers of the nodes specifying the domain boundaries
        surface_boundaries = np.intersect1d(
            side_elements, earth_surface_elements
        )
        bottom_boundaries = np.intersect1d(
            side_elements, earth_bottom_elements
        )

        # Get coordinates
        coords = self.m["MODEL/coordinates"][()]
        self.domain_edge_coords = coords[surface_boundaries]
        self.earth_surface_coords = coords[earth_surface_elements]
        self.earth_bottom_coords = coords[earth_bottom_elements]
        self.bottom_edge_coords = coords[bottom_boundaries]

        # Get approximation of element width, take second smallest value

        # For now we will just take a random point on the surface and
        # take the maximum distance between gll points and use that
        # as the element with. It should be an overestimation
        x, y, z = self.earth_surface_coords[0, :, :].T
        r = np.sqrt(
            (max(x) - min(x)) ** 2
            + (max(y) - min(y)) ** 2
            + (max(z) - min(z)) ** 2
        )
        self.approx_elem_width = r

        # Get extent and center of domain
        x, y, z = self.domain_edge_coords.T

        # pick a random GLL point to represent the boundary
        x = x[0]
        y = y[0]
        z = z[0]
        edge_lat, edge_lon, _ = xyz_to_lat_lon_radius(x, y, z)

        # get center lat/lon
        x_cen, y_cen, z_cen = np.median(x), np.median(y), np.median(z)
        self.center_lat, self.center_lon, _ = xyz_to_lat_lon_radius(
            x_cen, y_cen, z_cen
        )

        lats, lons, _ = xyz_to_lat_lon_radius(x, y, z)
        self.min_lat = np.min(lats)
        self.max_lat = np.max(lats)
        self.min_lon = np.min(lons)
        self.max_lon = np.max(lons)

        # Get coords for the bottom edge of mesh
        x, y, z = self.bottom_edge_coords.T
        x, y, z = x[0], y[0], z[0]

        # Figure out maximum depth of mesh
        _, _, r = xyz_to_lat_lon_radius(x, y, z)
        min_r = min(r)
        self.max_depth = self.r_earth - min_r

        self.is_read = True

        # In order to create the self.edge_polygon we need to make sure that
        # the points on the boundary are arranged in a way that a proper
        # polygon will be drawn.
        sorted_indices = self.get_sorted_edge_coords()
        x, y, z = self.domain_edge_coords[np.append(sorted_indices, 0)].T
        lats, lons, _ = xyz_to_lat_lon_radius(x[0], y[0], z[0])
        self.boundary = np.array([lats, lons]).T
        self.edge_polygon = matplotlib.path.Path(self.boundary)
        # Close file
        self.m.close()

    def _initialize_kd_trees(self):
        """
        KDTrees are used to quickly access closest points.
        """
        if not self.is_read:
            self._read()

        # KDTrees not needed in the case of a global mesh
        if self.is_global_mesh:
            return

        # build KDTree that can be used for querying later
        self.earth_surface_tree = cKDTree(self.earth_surface_coords[:, 0, :])
        self.domain_edge_tree = cKDTree(self.domain_edge_coords[:, 0, :])
        self.KDTrees_initialized = True

    def get_side_set_names(self):
        if not self.is_read:
            self._read()
        return self.side_set_names

    def point_in_domain(
        self, longitude: float, latitude: float, depth: float = None
    ):
        """
        Test whether a point lies inside the domain. It is done in a step
        by step process of elimination:
            * First one checks depth and sees whether the point is too deep 
              and falls into the absorbing boundaries at depth. 
            * Second is a box check seeing whether point falls outside
              of minimum and maximum latitude.
            * Third one uses the edge polygon to see whether point is inside
              it or not.
            * Last one checks whether the point is too close to the edge
              meaning that it would fall into the absorbing boundaries.

        :param longitude: longitude in degrees
        :type longitude: float
        :param latitude: latitude in degrees
        :type latitude: float
        :param depth: depth of event in meters
        :type depth: float
        """
        if not self.is_read:
            self._read()

        if self.is_global_mesh:
            return True

        if not self.KDTrees_initialized:
            self._initialize_kd_trees()

        # Assuming a spherical Earth without topography
        point_on_surface = lat_lon_radius_to_xyz(
            latitude, longitude, self.r_earth
        )

        dist, _ = self.domain_edge_tree.query(point_on_surface, k=2)

        # First elimination:
        # Check whether domain is deep enough to include the point.
        # Multiply element width with 1.5 since they are larger at the bottom
        if depth:
            if depth > (self.max_depth - self.absorbing_boundary_length * 1.2):
                return False

        # Second elimination:
        if latitude >= self.max_lat or latitude <= self.min_lat:
            return False
        if longitude >= self.max_lon or longitude <= self.min_lon:
            return False

        # Third elimination:
        if not self.edge_polygon.contains_point((latitude, longitude)):
            return False

        # Fourth elimination
        if np.min(dist) < self.absorbing_boundary_length * 1.2:
            return False

        return True

    def plot(
        self,
        ax: matplotlib.axes.Axes = None,
        plot_inner_boundary: bool = False,
    ):
        """
        Plots the domain
        Global domain is plotted using an equal area Mollweide projection.
        Smaller domains have eihter Orthographic projections or PlateCarree.

        :param ax: matplotlib axes, defaults to None
        :type ax: matplotlib.axes.Axes, optional
        :param plot_inner_boundary: plot the convex hull of the mesh
        surface nodes that lie inside the domain. Defaults to False
        :type plot_inner_boundary: bool, optional
        :return: The created GeoAxes instance.
        """
        if not self.is_read:
            self._read()

        import matplotlib.pyplot as plt

        # if global mesh return moll
        transform = cp.crs.Geodetic()
        if self.is_global_mesh:
            projection = cp.crs.Mollweide()
            if ax is None:
                m = plt.axes(projection=projection)
            else:
                m = ax
            _plot_features(m, projection=projection)
            return m, projection

        lat_extent = self.max_lat - self.min_lat
        lon_extent = self.max_lon - self.min_lon
        max_extent = max(lat_extent, lon_extent)

        # Use a global plot for very large domains.
        if lat_extent >= 90.0 and lon_extent >= 90.0:
            projection = cp.crs.Mollweide()
            if ax is None:
                m = plt.axes(projection=projection)
            else:
                m = ax

        elif max_extent >= 75.0:
            projection = cp.crs.Orthographic(
                central_longitude=self.center_lon,
                central_latitude=self.center_lat,
            )
            if ax is None:
                m = plt.axes(projection=projection)
            else:
                m = ax

        else:
            projection = cp.crs.PlateCarree(central_longitude=self.center_lon,)
            if ax is None:
                m = plt.axes(projection=projection,)
            else:
                m = ax
            m.set_extent(
                [
                    self.min_lon - 1.0,
                    self.max_lon + 1.0,
                    self.min_lat - 1.0,
                    self.max_lat + 1.0,
                ]
            )

        try:
            _plot_lines(
                m,
                self.boundary,
                transform=transform,
                color="red",
                lw=2,
                label="Domain Edge",
            )

            if plot_inner_boundary:
                # Get surface points
                x, y, z = self.earth_surface_coords.T
                latlonrad = np.array(xyz_to_lat_lon_radius(x[0], y[0], z[0]))
                # This part is potentially slow when lots
                # of points need to be checked
                in_domain = []
                idx = 0
                for lat, lon, _ in latlonrad.T:
                    if self.point_in_domain(latitude=lat, longitude=lon,):
                        in_domain.append(idx)
                    idx += 1
                lats, lons, rad = np.array(latlonrad[:, in_domain])

                # Get the complex hull from projected (to 2D) points
                from scipy.spatial import ConvexHull

                points = np.array((lons, lats)).T
                hull = ConvexHull(points)

                # Plot the hull simplices
                for simplex in hull.simplices:
                    m.plot(
                        points[simplex, 0],
                        points[simplex, 1],
                        c="black",
                        transform=transform,
                    )
                m.plot(
                    points[simplex, 0],
                    points[simplex, 1],
                    c="black",
                    transform=transform,
                    label="Convex Hull of Inner boundary",
                )

        except LASIFError:
            # Back up plot if the other one fails, which happens for
            # very weird meshes sometimes.
            # This Scatter all edge nodes on the plotted domain
            x, y, z = self.domain_edge_coords.T
            lats, lons, _ = xyz_to_lat_lon_radius(x[0], y[0], z[0])
            plt.scatter(
                lons,
                lats,
                color="k",
                label="Edge nodes",
                zorder=3000,
                transform=transform,
            )

        _plot_features(m, projection=projection)
        m.legend(framealpha=0.5, loc="lower right")

        return m, projection

    def get_sorted_edge_coords(self):
        """
        Gets the indices of a sorted array of domain edge nodes,
        this method should work, as long as the top surfaces of the elements
        are approximately square
        """

        if not self.KDTrees_initialized:
            self._initialize_kd_trees()

        # For each point get the indices of the five nearest points, of
        # which the first one is the point itself.
        _, indices_nearest = self.domain_edge_tree.query(
            self.domain_edge_coords, k=5
        )
        indices_nearest = indices_nearest[:, 0, :]
        num_edge_points = len(self.domain_edge_coords)
        indices_sorted = np.zeros(num_edge_points, dtype=int)

        # start sorting with the first node
        indices_sorted[0] = 0
        for i in range(num_edge_points)[1:]:
            prev_idx = indices_sorted[i - 1]
            # take 4 closest points
            closest_indices = indices_nearest[prev_idx, 1:]
            if not closest_indices[0] in indices_sorted:
                indices_sorted[i] = closest_indices[0]
            elif not closest_indices[1] in indices_sorted:
                indices_sorted[i] = closest_indices[1]
            elif not closest_indices[2] in indices_sorted:
                indices_sorted[i] = closest_indices[2]
            elif not closest_indices[3] in indices_sorted:
                indices_sorted[i] = closest_indices[3]
            else:
                raise LASIFError(
                    "Edge node sort algorithm only works "
                    "for reasonably square elements"
                )
        return indices_sorted

    def __str__(self):
        return "HDF5 Domain"

    def is_global_domain(self):
        if not self.is_read:
            self._read()

        if self.is_global_mesh:
            return True
        return False


def _plot_features(m, projection):
    """
    Helper function aiding in consistent plot styling.
    """
    from cartopy.mpl.gridliner import (
        LONGITUDE_FORMATTER,
        LATITUDE_FORMATTER,
    )

    m.add_feature(cp.feature.LAND)
    m.add_feature(cp.feature.OCEAN)
    m.add_feature(cp.feature.COASTLINE, zorder=13)
    m.add_feature(cp.feature.BORDERS, linestyle=":", zorder=13)
    m.add_feature(cp.feature.LAKES, alpha=0.5)
    # m.add_feature(cp.feature.RIVERS)
    # m.stock_img()
    if projection.proj4_params["proj"] == "eqc":
        grid_lines = m.gridlines(draw_labels=True)
        grid_lines.xformatter = LONGITUDE_FORMATTER
        grid_lines.yformatter = LATITUDE_FORMATTER
        grid_lines.xlabels_top = False
        grid_lines.ylabels_right = False
    else:
        m.stock_img()


def _plot_lines(
    map_object,
    lines,
    color,
    lw,
    transform,
    alpha=1.0,
    label=None,
    effects=False,
):

    lines = np.array(lines)
    lats = lines[:, 0]
    lngs = lines[:, 1]
    map_object.plot(lngs, lats, transform=transform, color=color, label=label)
