from dataclasses import dataclass

import ipywidgets as widgets
import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.gridspec import GridSpec
from scipy.ndimage import gaussian_filter, gaussian_filter1d

from .. import core
from ..utils.signal_process import ThetaParams
from .. import plotting


class Pf1D(core.Ratemap):
    def __init__(
        self,
        neurons: core.Neurons,
        position: core.Position,
        epochs: core.Epoch = None,
        frate_thresh=1.0,
        speed_thresh=3,
        grid_bin=1,
        sigma=1,
    ):
        """computes 1d place field using linearized coordinates. It always computes two place maps with and
        without speed thresholds.
        Parameters
        ----------
        neurons : core.Neurons
            neurons obj containing spiketrains and related info
        position: core.Position
            1D position
        grid_bin : int
            bin size of position bining, by default 5 cm
        epochs : core.Epoch,
            restrict calculation to these epochs, default None
        frate_thresh : float,
            peak firing rate should be above this value, default 1 Hz
        speed_thresh : float
            speed threshold for calculating place field, by default None
        sigma : float
            standard deviation for smoothing occupancy and spikecounts in each position bin, in units of cm, default 1 cm
<<<<<<< HEAD
=======

>>>>>>> neuropy_orig/main
        NOTE: speed_thresh is ignored if epochs is provided
        """

        assert position.ndim == 1, "Only 1 dimensional position are acceptable"
        neuron_ids = neurons.neuron_ids
        position_srate = position.sampling_rate
        x = position.x
        speed = position.speed
        t = position.time
        t_start = position.t_start
        t_stop = position.t_stop

        smooth_ = lambda f: gaussian_filter1d(
            f, sigma / grid_bin, axis=-1
        )  # divide by grid_bin to account for discrete spacing

        xbin = np.arange(np.min(x), np.max(x) + grid_bin, grid_bin)

        if epochs is not None:
            assert isinstance(epochs, core.Epoch), "epochs should be core.Epoch object"

            spiketrains = [
                np.concatenate(
                    [
                        spktrn[(spktrn >= epc.start) & (spktrn <= epc.stop)]
                        for epc in epochs.to_dataframe().itertuples()
                    ]
                )
                for spktrn in neurons.spiketrains
            ]
            # changing x, speed, time to only run epochs so occupancy map is consistent
            indx = np.concatenate(
                [
                    np.where((t >= epc.start) & (t <= epc.stop))[0]
                    for epc in epochs.to_dataframe().itertuples()
                ]
            )

            speed_thresh = None
            print("Note: speed_thresh is ignored when epochs is provided")
        else:
            spiketrains = neurons.time_slice(t_start, t_stop).spiketrains
            indx = np.where(speed >= speed_thresh)[0]

        # to avoid interpolation error, speed and position estimation for spiketrains should use time and speed of entire position (not only on threshold crossing time points)
        x_thresh = x[indx]

        spk_pos, spk_t, spkcounts = [], [], []
        for spktrn in spiketrains:
            spk_spd = np.interp(spktrn, t, speed)
            spk_x = np.interp(spktrn, t, x)
            if speed_thresh is not None:
                indices = np.where(spk_spd >= speed_thresh)[0]
                spk_x = spk_x[indices]
                spktrn = spktrn[indices]

            spk_pos.append(spk_x)
            spk_t.append(spktrn)
            spkcounts.append(np.histogram(spk_x, bins=xbin)[0])

        spkcounts = smooth_(np.asarray(spkcounts))
        occupancy = np.histogram(x_thresh, bins=xbin)[0] / position_srate + 1e-16
        occupancy = smooth_(occupancy)
        tuning_curve = spkcounts / occupancy.reshape(1, -1)

        # ---- neurons with peak firing rate above thresh ------
        frate_thresh_indx = np.where(np.max(tuning_curve, axis=1) >= frate_thresh)[0]
        tuning_curve = tuning_curve[frate_thresh_indx, :]
        neuron_ids = neuron_ids[frate_thresh_indx]
        spk_t = [spk_t[_] for _ in frate_thresh_indx]
        spk_pos = [spk_pos[_] for _ in frate_thresh_indx]

        super().__init__(tuning_curves=tuning_curve, xbin=xbin, neuron_ids=neuron_ids)
        self.ratemap_spiketrains = spk_t
        self.ratemap_spiketrains_pos = spk_pos
        self.occupancy = occupancy
        self.frate_thresh = frate_thresh
        self.speed_thresh = speed_thresh

    def estimate_theta_phases(self, signal: core.Signal):
        """Calculates phase of spikes computed for placefields
        Parameters
        ----------
        theta_chan : int
            lfp channel to use for calculating theta phases
        """
        assert signal.n_channels == 1, "signal should have only a single trace"
        sig_t = signal.time
        thetaparam = ThetaParams(signal.traces, fs=signal.sampling_rate)

        phase = []
        for spiketrain in self.ratemap_spkitrains:
            phase.append(np.interp(spiketrain, sig_t, thetaparam.angle))

        self.ratemap_spiketrains_phases = phase

    def plot_with_phase(
        self, ax=None, normalize=True, stack=True, cmap="tab20b", subplots=(5, 8)
    ):
        cmap = mpl.cm.get_cmap(cmap)

        mapinfo = self.ratemaps

        ratemaps = mapinfo["ratemaps"]
        if normalize:
            ratemaps = [map_ / np.max(map_) for map_ in ratemaps]
        phases = mapinfo["phases"]
        position = mapinfo["pos"]
        nCells = len(ratemaps)
        bin_cntr = self.bin[:-1] + np.diff(self.bin).mean() / 2

        def plot_(cell, ax, axphase):
            color = cmap(cell / nCells)
            if subplots is None:
                ax.clear()
                axphase.clear()
            ax.fill_between(bin_cntr, 0, ratemaps[cell], color=color, alpha=0.3)
            ax.plot(bin_cntr, ratemaps[cell], color=color, alpha=0.2)
            ax.set_xlabel("Position (cm)")
            ax.set_ylabel("Normalized frate")
            ax.set_title(
                " ".join(filter(None, ("Cell", str(cell), self.run_dir.capitalize())))
            )
            if normalize:
                ax.set_ylim([0, 1])
            axphase.scatter(position[cell], phases[cell], c="k", s=0.6)
            if stack:  # double up y-axis as is convention for phase precession plots
                axphase.scatter(position[cell], phases[cell] + 360, c="k", s=0.6)
            axphase.set_ylabel(r"$\theta$ Phase")

        if ax is None:

            if subplots is None:
                _, gs = plotting.Fig().draw(grid=(1, 1), size=(10, 5))
                ax = plt.subplot(gs[0])
                ax.spines["right"].set_visible(True)
                axphase = ax.twinx()
                widgets.interact(
                    plot_,
                    cell=widgets.IntSlider(
                        min=0,
                        max=nCells - 1,
                        step=1,
                        description="Cell ID:",
                    ),
                    ax=widgets.fixed(ax),
                    axphase=widgets.fixed(axphase),
                )
            else:
                _, gs = plotting.Fig().draw(grid=subplots, size=(15, 10))
                for cell in range(nCells):
                    ax = plt.subplot(gs[cell])
                    axphase = ax.twinx()
                    plot_(cell, ax, axphase)

        return ax

    def plot_ratemaps(
        self, ax=None, pad=2, normalize=False, sortby=None, cmap="tab20b"
    ):
        return plotting.plot_ratemaps()

    def plot_ratemaps_raster(self):

        _, ax = plt.subplots()
        order = self.get_sort_order(by="index")
        spiketrains_pos = [self.ratemap_spiketrains_pos[i] for i in order]
        for i, pos in enumerate(spiketrains_pos):
            ax.plot(pos, i * np.ones_like(pos), "k.", markersize=2)

    def plot_raw_ratemaps_laps(self, ax=None, subplots=(8, 9)):
        return plotting.plot_raw_ratemaps()


class Pf2D:
    def __init__(
        self,
        neurons: core.Neurons,
        position: core.Position,
        epochs: core.Epoch = None,
        frate_thresh=1.0,
        speed_thresh=3,
        grid_bin=1,
        sigma=1,
    ):

        """Calculates 2D placefields
        Parameters
        ----------
        period : list/array
            in seconds, time period between which placefields are calculated
        gridbin : int, optional
            bin size of grid in centimeters, by default 10
        speed_thresh : int, optional
            speed threshold in cm/s, by default 10 cm/s
        Returns
        -------
        [type]
            [description]
        """
        assert position.ndim > 1, "Position is not 2D"
        period = [position.t_start, position.t_stop]
        smooth_ = lambda f: gaussian_filter1d(
            f, sigma / grid_bin, axis=-1
        )  # divide by grid_bin to account for discrete spacing

        spikes = neurons.time_slice(*period).spiketrains
        cell_ids = neurons.neuron_ids
        nCells = len(spikes)

        # ----- Position---------
        xcoord = position.x
        ycoord = position.y
        time = position.time
        trackingRate = position.sampling_rate

        ind_maze = np.where((time > period[0]) & (time < period[1]))
        x = xcoord[ind_maze]
        y = ycoord[ind_maze]
        t = time[ind_maze]

        x_grid = np.arange(min(x), max(x) + grid_bin, grid_bin)
        y_grid = np.arange(min(y), max(y) + grid_bin, grid_bin)
        # x_, y_ = np.meshgrid(x_grid, y_grid)

        diff_posx = np.diff(x)
        diff_posy = np.diff(y)

        speed = np.sqrt(diff_posx**2 + diff_posy**2) / (1 / trackingRate)
        speed = smooth_(speed)

        dt = t[1] - t[0]
        running = np.where(speed / dt > speed_thresh)[0]

        x_thresh = x[running]
        y_thresh = y[running]
        t_thresh = t[running]

        def make_pfs(
            t_, x_, y_, spkAll_, occupancy_, speed_thresh_, maze_, x_grid_, y_grid_
        ):
            maps, spk_pos, spk_t = [], [], []
            for cell in spkAll_:
                # assemble spikes and position data
                spk_maze = cell[np.where((cell > maze_[0]) & (cell < maze_[1]))]
                spk_speed = np.interp(spk_maze, t_[1:], speed)
                spk_y = np.interp(spk_maze, t_, y_)
                spk_x = np.interp(spk_maze, t_, x_)

                # speed threshold
                spd_ind = np.where(spk_speed > speed_thresh_)
                # spk_spd = spk_speed[spd_ind]
                spk_x = spk_x[spd_ind]
                spk_y = spk_y[spd_ind]

                # Calculate maps
                spk_map = np.histogram2d(spk_x, spk_y, bins=(x_grid_, y_grid_))[0]
                spk_map = smooth_(spk_map)
                maps.append(spk_map / occupancy_)

                spk_t.append(spk_maze[spd_ind])
                spk_pos.append([spk_x, spk_y])

            return maps, spk_pos, spk_t

        # --- occupancy map calculation -----------
        # NRK todo: might need to normalize occupancy so sum adds up to 1
        occupancy = np.histogram2d(x_thresh, y_thresh, bins=(x_grid, y_grid))[0]
        occupancy = occupancy / trackingRate + 10e-16  # converting to seconds
        occupancy = smooth_(occupancy)

        maps, spk_pos, spk_t = make_pfs(
            t, x, y, spikes, occupancy, speed_thresh, period, x_grid, y_grid
        )

        # ---- cells with peak frate abouve thresh ------
        good_cells_indx = [
            cell_indx
            for cell_indx in range(nCells)
            if np.max(maps[cell_indx]) > frate_thresh
        ]

        get_elem = lambda list_: [list_[_] for _ in good_cells_indx]

        self.spk_pos = get_elem(spk_pos)
        self.spk_t = get_elem(spk_t)
        self.ratemaps = get_elem(maps)
        self.cell_ids = cell_ids[good_cells_indx]
        self.occupancy = occupancy
        self.speed = speed
        self.x = x
        self.y = y
        self.t = t
        self.xgrid = x_grid
        self.ygrid = y_grid
        self.gridbin = grid_bin
        self.speed_thresh = speed_thresh
        self.period = period
        self.frate_thresh = frate_thresh
        self.mesh = np.meshgrid(
            self.xgrid[:-1] + self.gridbin / 2,
            self.ygrid[:-1] + self.gridbin / 2,
        )
        ngrid_centers_x = self.mesh[0].size
        ngrid_centers_y = self.mesh[1].size
        x_center = np.reshape(self.mesh[0], [ngrid_centers_x, 1], order="F")
        y_center = np.reshape(self.mesh[1], [ngrid_centers_y, 1], order="F")
        xy_center = np.hstack((x_center, y_center))
        self.gridcenter = xy_center.T

    def plotMap(self, subplots=(7, 4), fignum=None):
        """Plots heatmaps of placefields with peak firing rate
        Parameters
        ----------
        speed_thresh : bool, optional
            [description], by default False
        subplots : tuple, optional
            number of cells within each figure window. If cells exceed the number of subplots, then cells are plotted in successive figure windows of same size, by default (10, 8)
        fignum : int, optional
            figure number to start from, by default None
        """

        map_use, thresh = self.ratemaps, self.speed_thresh

        nCells = len(map_use)
        nfigures = nCells // np.prod(subplots) + 1

        if fignum is None:
            if f := plt.get_fignums():
                fignum = f[-1] + 1
            else:
                fignum = 1

        figures, gs = [], []
        for fig_ind in range(nfigures):
            fig = plt.figure(fignum + fig_ind, figsize=(6, 10), clear=True)
            gs.append(GridSpec(subplots[0], subplots[1], figure=fig))
            fig.subplots_adjust(hspace=0.4)
            fig.suptitle(
                "Place maps with peak firing rate (speed_threshold = "
                + str(thresh)
                + ")"
            )
            figures.append(fig)

        for cell, pfmap in enumerate(map_use):
            ind = cell // np.prod(subplots)
            subplot_ind = cell % np.prod(subplots)
            ax1 = figures[ind].add_subplot(gs[ind][subplot_ind])
            im = ax1.pcolorfast(
                self.xgrid,
                self.ygrid,
                np.rot90(np.fliplr(pfmap)) / np.max(pfmap),
                cmap="jet",
                vmin=0,
            )  # rot90(flipud... is necessary to match plotRaw configuration.
            # max_frate =
            ax1.axis("off")
            ax1.set_title(
                f"Cell {self.cell_ids[cell]} \n{round(np.nanmax(pfmap),2)} Hz"
            )

            # cbar_ax = fig.add_axes([0.9, 0.3, 0.01, 0.3])
            # cbar = fig.colorbar(im, cax=cbar_ax)
            # cbar.set_label("firing rate (Hz)")

    def plotRaw(
        self,
        subplots=(10, 8),
        fignum=None,
        alpha=0.5,
        label_cells=False,
        ax=None,
        clus_use=None,
    ):
        if ax is None:
            fig = plt.figure(fignum, figsize=(6, 10))
            gs = GridSpec(subplots[0], subplots[1], figure=fig)
            # fig.subplots_adjust(hspace=0.4)
        else:
            assert len(ax) == len(
                clus_use
            ), "Number of axes must match number of clusters to plot"
            fig = ax[0].get_figure()

        spk_pos_use = self.spk_pos

        if clus_use is not None:
            spk_pos_tmp = spk_pos_use
            spk_pos_use = []
            [spk_pos_use.append(spk_pos_tmp[a]) for a in clus_use]

        for cell, (spk_x, spk_y) in enumerate(spk_pos_use):
            if ax is None:
                ax1 = fig.add_subplot(gs[cell])
            else:
                ax1 = ax[cell]
            ax1.plot(self.x, self.y, color="#d3c5c5")
            ax1.plot(spk_x, spk_y, ".r", markersize=0.8, color=[1, 0, 0, alpha])
            ax1.axis("off")
            if label_cells:
                # Put info on title
                info = self.cell_ids[cell]
                ax1.set_title(f"Cell {info}")

        fig.suptitle(
            f"Place maps for cells with their peak firing rate (frate thresh={self.frate_thresh},speed_thresh={self.speed_thresh})"
        )

    def plotRaw_v_time(self, cellind, speed_thresh=False, alpha=0.5, ax=None):
        if ax is None:
            fig, ax = plt.subplots(2, 1, sharex=True)
            fig.set_size_inches([23, 9.7])

        # plot trajectories
        for a, pos, ylabel in zip(
            ax, [self.x, self.y], ["X position (cm)", "Y position (cm)"]
        ):
            a.plot(self.t, pos)
            a.set_xlabel("Time (seconds)")
            a.set_ylabel(ylabel)
            # pretty_plot(a)

        # Grab correct spike times/positions
        if speed_thresh:
            spk_pos_, spk_t_ = self.run_spk_pos, self.run_spk_t
        else:
            spk_pos_, spk_t_ = self.spk_pos, self.spk_t

        # plot spikes on trajectory
        for a, pos in zip(ax, spk_pos_[cellind]):
            a.plot(spk_t_[cellind], pos, "r.", color=[1, 0, 0, alpha])

        # Put info on title
        ipbool = self._obj.spikes.pyrid[cellind] == self._obj.spikes.info.index
        info = self._obj.spikes.info.iloc[ipbool]
        ax[0].set_title(
            "Cell "
            + str(info["id"])
            + ": q = "
            + str(info["q"])
            + ", speed_thresh="
            + str(self.speed_thresh)
        )

    def plot_all(self, cellind, speed_thresh=True, alpha=0.4, fig=None):
        if fig is None:
            fig_use = plt.figure(figsize=[28.25, 11.75])
        else:
            fig_use = fig
        gs = GridSpec(2, 4, figure=fig_use)
        ax2d = fig_use.add_subplot(gs[0, 0])
        axccg = np.asarray(fig_use.add_subplot(gs[1, 0]))
        axx = fig_use.add_subplot(gs[0, 1:])
        axy = fig_use.add_subplot(gs[1, 1:], sharex=axx)

        self.plotRaw(speed_thresh=speed_thresh, clus_use=[cellind], ax=[ax2d])
        self.plotRaw_v_time(
            cellind, speed_thresh=speed_thresh, ax=[axx, axy], alpha=alpha
        )
        self._obj.spikes.plot_ccg(clus_use=[cellind], type="acg", ax=axccg)

        return fig_use
