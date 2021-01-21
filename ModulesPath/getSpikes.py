import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import os
from pathlib import Path
from dataclasses import dataclass
import scipy.signal as sg
import matplotlib.gridspec as gridspec
import matplotlib as mpl
from parsePath import Recinfo
from behavior import behavior_epochs
from ccg import correlograms
from plotUtil import pretty_plot
from scipy.ndimage import gaussian_filter


class Spikes:
    """Spike related methods

    Attributes
    ----------
    times : list
        list of arrays representing spike times of all detected clusters
    pyr : list
        Each array within list representing spike times of pyramidal neurons
    intneur : list
        list of arrays representing spike times of interneurons neurons
    mua : list
        list of arrays representing spike times of mulitunits neurons


    Methods
    ----------
    gen_instfiring()
        generates instantenous firing rate and includes all spiking events (pyr, mua, intneur)

    """

    def __init__(self, basepath):

        if isinstance(basepath, Recinfo):
            self._obj = basepath
        else:
            self._obj = Recinfo(basepath)

        self.stability = Stability(basepath)
        # self.dynamics = firingDynamics(basepath)
        filePrefix = self._obj.files.filePrefix

        @dataclass
        class files:
            spikes: str = Path(str(filePrefix) + "_spikes.npy")
            instfiring: str = Path(str(filePrefix) + "_instfiring.pkl")

        self.files = files()
        self.corr = Correlation(self._obj)

        filename = self.files.spikes
        if filename.is_file():
            self.load_spikes(filename)

    def load_spikes(self, spikes_filename):
        spikes = np.load(spikes_filename, allow_pickle=True).item()
        self.times = spikes["times"]

        if "allspikes" in spikes:
            self.alltimes = spikes["allspikes"]
            self.cluID = spikes["allcluIDs"]
        self.info = spikes["info"].reset_index()
        self.pyrid = np.where(self.info.q < 4)[0]
        self.pyr = [self.times[_] for _ in self.pyrid]
        self.intneurid = np.where(self.info.q == 8)[0]
        self.intneur = [self.times[_] for _ in self.intneurid]
        self.muaid = np.where(self.info.q == 6)[0]
        self.mua = [self.times[_] for _ in self.muaid]

    @property
    def instfiring(self):
        if self.files.instfiring.is_file():
            return pd.read_pickle(self.files.instfiring)
        else:
            print("instantenous file does not exist ")

    def gen_instfiring(self):
        spkall = np.concatenate(self.times)

        bins = np.arange(spkall.min(), spkall.max(), 0.001)

        spkcnt = np.histogram(spkall, bins=bins)[0]
        gaussKernel = self._gaussian()
        instfiring = sg.convolve(spkcnt, gaussKernel, mode="same", method="direct")

        data = pd.DataFrame({"time": bins[1:], "frate": instfiring})
        data.to_pickle(self.files.instfiring)
        return data

    def _gaussian(self):
        """Gaussian function for generating instantenous firing rate

        Returns:
            [array] -- [gaussian kernel centered at zero and spans from -1 to 1 seconds]
        """

        sigma = 0.020
        binSize = 0.001
        t_gauss = np.arange(-1, 1, binSize)
        A = 1 / np.sqrt(2 * np.pi * sigma ** 2)
        gaussian = A * np.exp(-(t_gauss ** 2) / (2 * sigma ** 2))

        return gaussian

    def plot_raster(
        self,
        spikes=None,
        ax=None,
        period=None,
        sort_by_frate=False,
        tstart=0,
        color=None,
        marker="|",
        markersize=2,
    ):
        """creates raster plot using spike times

        Parameters
        ----------
        spikes : list, optional
            Each array within list represents spike times of that unit, by default None
        ax : obj, optional
            axis to plot onto, by default None
        period : array like, optional
            only plot raster for spikes within this period, by default None
        sort_by_frate : bool, optional
            If true then sorts spikes by the number of spikes (frate), by default False
        tstart : int, optional
            positions the x-axis labels to start from this, by default 0
        color : [type], optional
            color for raster plots, by default None
        marker : str, optional
            marker style, by default "|"
        markersize : int, optional
            size of marker, by default 2
        """
        if ax is None:
            fig = plt.figure(1, figsize=(6, 10))
            gs = gridspec.GridSpec(1, 1, figure=fig)
            fig.subplots_adjust(hspace=0.4)
            ax = fig.add_subplot(gs[0])

        if spikes is None:
            pyr = self.pyr
            intneur = self.intneur
            mua = self.mua
            spikes = mua + pyr + intneur

            color = (
                ["#a9bcd0"] * len(mua)
                + ["#2d3143"] * len(pyr)
                + ["#02c59b"] * len(intneur)
            )

            # --- mimics legend for labeling unit category ---------
            ax.annotate(
                "mua", xy=(0.9, 0.5), xycoords="figure fraction", color="#a9bcd0"
            )
            ax.annotate(
                "pyr", xy=(0.9, 0.45), xycoords="figure fraction", color="#2d3143"
            )
            ax.annotate(
                "int", xy=(0.9, 0.4), xycoords="figure fraction", color="#02c59b"
            )

        else:
            assert isinstance(spikes, list), "Please provide a list of arrays"
            if color is None:
                color = ["#2d3143"] * len(spikes)
            elif isinstance(color, str):

                try:
                    cmap = mpl.cm.get_cmap(color)
                    color = [cmap(_ / len(spikes)) for _ in range(len(spikes))]
                except:
                    color = [color] * len(spikes)

        print(f"Plotting {len(spikes)} cells")
        frate = [len(cell) for cell in spikes]  # number of spikes ~= frate

        if period is not None:
            period_duration = np.diff(period)
            spikes = [
                cell[np.where((cell > period[0]) & (cell < period[1]))[0]]
                for cell in spikes
            ]
            frate = np.asarray(
                [len(cell) / period_duration for cell in spikes]
            ).squeeze()

        if sort_by_frate:
            sort_frate_indices = np.argsort(frate)
            spikes = [spikes[indx] for indx in sort_frate_indices]

        for cell, spk in enumerate(spikes):
            plt.plot(
                spk - tstart,
                (cell + 1) * np.ones(len(spk)),
                marker,
                markersize=markersize,
                color=color[cell],
            )
        ax.set_ylim([1, len(spikes)])
        ax.set_xlabel("Time (s)")
        ax.set_ylabel("Units")

    def plot_ccg(self, clus_use, type="all", bin_size=0.001, window_size=0.05, ax=None):

        """Plot CCG for clusters in clus_use (list, max length = 2). Supply only one cluster in clus_use for ACG only.
        type: 'all' or 'ccg_only'.
        ax (optional): if supplied len(ax) must be 1 for type='ccg_only' or nclus^2 for type'all'"""

        def ccg_spike_assemble(clus_use):
            """Assemble an array of sorted spike times and cluIDs for the input cluster ids the list clus_use """
            spikes_all, clus_all = [], []
            [
                (
                    spikes_all.append(self.times[idc]),
                    clus_all.append(np.ones_like(self.times[idc]) * idc),
                )
                for idc in clus_use
            ]
            spikes_all, clus_all = np.concatenate(spikes_all), np.concatenate(clus_all)
            spikes_sorted, clus_sorted = (
                spikes_all[spikes_all.argsort()],
                clus_all[spikes_all.argsort()],
            )

            return spikes_sorted, clus_sorted.astype("int")

        spikes_sorted, clus_sorted = ccg_spike_assemble(clus_use)
        ccgs = correlograms(
            spikes_sorted,
            clus_sorted,
            sample_rate=self._obj.sampfreq,
            bin_size=bin_size,
            window_size=window_size,
        )

        if type == "ccgs_only":
            ccgs = ccgs[0, 1, :].reshape(1, 1, -1)

        if ax is None:
            fig, ax = plt.subplots(ccgs.shape[0], ccgs.shape[1])

        winsize_bins = 2 * int(0.5 * window_size / bin_size) + 1
        bins = np.linspace(0, 1, winsize_bins)
        for a, ccg in zip(ax.reshape(-1), ccgs.reshape(-1, ccgs.shape[2])):
            a.bar(bins, ccg, width=1 / (winsize_bins - 1))
            a.set_xticks([0, 1])
            a.set_xticklabels(np.ones((2,)) * np.round(window_size / 2, 2))
            a.set_xlabel("Time (s)")
            a.set_ylabel("Spike Count")
            pretty_plot(a)

        return ax

    def removeDoubleSpikes(self):
        pass

    def from_Phy(self, folder=None, fileformat="diff_folder", save_allspikes=False):
        """Gets spike times from Phy (https://github.com/cortex-lab/phy) compatible files

        Parameters
        ----------
        folder : str
            folder where Phy files are present
        fileformat : str, optional
            [description], by default "diff_folder"
        """
        spktimes = None
        spkinfo = None

        if fileformat == "diff_folder":
            nShanks = self._obj.nShanks
            sRate = self._obj.sampfreq
            name = self._obj.session.name
            day = self._obj.session.day
            basePath = self._obj.basePath
            clubasePath = Path(basePath, "spykcirc")
            spkall, info, shankID = [], [], []
            for shank in range(1, nShanks + 1):

                clufolder = Path(
                    clubasePath,
                    name + day + "Shank" + str(shank),
                    name + day + "Shank" + str(shank) + ".GUI",
                )

                # datFile = np.memmap(file + "Shank" + str(i) + ".dat", dtype="int16")
                # datFiledur = len(datFile) / (16 * sRate)
                spktime = np.load(clufolder / "spike_times.npy")
                cluID = np.load(clufolder / "spike_clusters.npy")
                cluinfo = pd.read_csv(clufolder / "cluster_info.tsv", delimiter="\t")
                goodCellsID = cluinfo.id[cluinfo["q"] < 10].tolist()
                info.append(cluinfo.loc[cluinfo["q"] < 10])
                shankID.extend(shank * np.ones(len(goodCellsID)))

                for i in range(len(goodCellsID)):
                    clu_spike_location = spktime[np.where(cluID == goodCellsID[i])[0]]
                    spkall.append(clu_spike_location / sRate)

            spkinfo = pd.concat(info, ignore_index=True)
            spkinfo["shank"] = shankID
            spktimes = spkall

        if fileformat == "same_folder":
            nShanks = self._obj.nShanks
            sRate = self._obj.sampfreq
            subname = self._obj.session.subname
            basePath = self._obj.basePath
            changroup = self._obj.channelgroups
            clubasePath = Path(basePath, "spykcirc")

            clufolder = Path(
                clubasePath,
                subname,
                subname + ".GUI",
            )
            spktime = np.load(clufolder / "spike_times.npy")
            cluID = np.load(clufolder / "spike_clusters.npy")
            cluinfo = pd.read_csv(clufolder / "cluster_info.tsv", delimiter="\t")
            if "q" in cluinfo.keys():
                goodCellsID = cluinfo.id[cluinfo["q"] < 10].tolist()
                info = cluinfo.loc[cluinfo["q"] < 10]
            else:
                print(
                    'No labels "q" found in phy data - using good for now, be sure to label with ":l q #"'
                )
                goodCellsID = cluinfo.id[(cluinfo["group"] == "good")].tolist()
                info = cluinfo.loc[(cluinfo["group"] == "good")]
            peakchan = info["ch"]
            shankID = [
                sh + 1
                for chan in peakchan
                for sh, grp in enumerate(changroup)
                if chan in grp
            ]

            spkall = []
            for i in range(len(goodCellsID)):
                clu_spike_location = spktime[np.where(cluID == goodCellsID[i])[0]]
                spkall.append(clu_spike_location / sRate)

            info["shank"] = shankID
            spkinfo = info
            spktimes = spkall
            # self.shankID = np.asarray(shankID)

        if save_allspikes:
            spikes_ = {
                "times": spktimes,
                "info": spkinfo,
                "allspikes": spktime,
                "allcluIDs": cluID,
            }
        else:
            spikes_ = {"times": spktimes, "info": spkinfo}
        filename = self.files.spikes

        np.save(filename, spikes_)
        self.load_spikes(filename)  # now load these into class

    def export2neuroscope(self, spks):
        """To view spikes in neuroscope, spikes are exported to .clu.1 and .res.1 files in the basepath. You can order the spikes in a way to view sequential activity in neuroscope

        Parameters
        ----------
        spks : list
            list of spike times.
        """
        srate = self._obj.sampfreq
        nclu = len(spks)
        spk_frame = np.concatenate([(cell * srate).astype(int) for cell in spks])
        clu_id = np.concatenate([[_] * len(spks[_]) for _ in range(nclu)])

        sort_ind = np.argsort(spk_frame)
        spk_frame = spk_frame[sort_ind]
        clu_id = clu_id[sort_ind]
        clu_id = np.append(nclu, clu_id)

        file_clu = self._obj.files.filePrefix.with_suffix(".clu.1")
        file_res = self._obj.files.filePrefix.with_suffix(".res.1")
        with file_clu.open("w") as f_clu, file_res.open("w") as f_res:
            for item in clu_id:
                f_clu.write(f"{item}\n")
            for frame in spk_frame:
                f_res.write(f"{frame}\n")


class Stability:
    def __init__(self, basepath):

        if isinstance(basepath, Recinfo):
            self._obj = basepath
        else:
            self._obj = Recinfo(basepath)

        filePrefix = self._obj.files.filePrefix

        @dataclass
        class files:
            stability: str = filePrefix.with_suffix(".stability.npy")

        self.files = files()

        if self.files.stability.is_file():
            self._load()

    def _load(self):
        data = np.load(self.files.stability, allow_pickle=True).item()
        self.info = data["stableinfo"]
        self.isStable = data["isStable"]
        self.bins = data["bins"]
        self.thresh = data["thresh"]

    def firingRate(self, periods, thresh=0.3):

        spikes = Spikes(self._obj)
        spks = spikes.times
        nCells = len(spks)

        # --- number of spikes in each bin ------
        bin_dur = np.asarray([np.diff(window) for window in periods]).squeeze()
        total_dur = np.sum(bin_dur)
        nspks_period = np.asarray(
            [np.histogram(cell, bins=np.concatenate(periods))[0][::2] for cell in spks]
        )
        assert nspks_period.shape[0] == nCells

        total_spks = np.sum(nspks_period, axis=1)

        nperiods = len(periods)
        mean_frate = total_spks / total_dur

        # --- calculate meanfr in each bin and the fraction of meanfr over all bins
        frate_period = nspks_period / np.tile(bin_dur, (nCells, 1))
        fraction = frate_period / mean_frate.reshape(-1, 1)
        assert frate_period.shape == fraction.shape

        isStable = np.where(fraction >= thresh, 1, 0)
        spkinfo = spikes.info[["q", "shank"]].copy()
        spkinfo["stable"] = isStable.all(axis=1).astype(int)

        stbl = {
            "stableinfo": spkinfo,
            "isStable": isStable,
            "bins": periods,
            "thresh": thresh,
        }
        np.save(self.files.stability, stbl)
        self._load()

    def waveform_similarity(self):
        pass

    def refPeriodViolation(self):

        spks = self._obj.spikes.times

        fp = 0.05  # accepted contamination level
        T = self._obj.epochs.totalduration
        taur = 2e-3
        tauc = 1e-3
        nbadspikes = lambda N: 2 * (taur - tauc) * (N ** 2) * (1 - fp) * fp / T

        nSpks = [len(_) for _ in spks]
        expected_violations = [nbadspikes(_) for _ in nSpks]

        self.expected_violations = np.asarray(expected_violations)

        isi = [np.diff(_) for _ in spks]
        ref = np.array([0, 0.002])
        zerolag_spks = [np.histogram(_, bins=ref)[0] for _ in isi]

        self.violations = np.asarray(zerolag_spks)

    def isolationDistance(self):
        pass


# class firingDynamics:
#     def __init__(self, obj):
#         self._obj = obj

#     def fRate(self):
#         pass

#     def plotfrate(self):
#         pass

#     def plotRaster(self):
#         pass
class Correlation:
    """Class for calculating pairwise correlations

    Attributes
    ----------
    corr : matrix
        correlation between time windows across a period of time
    time : array
        time points
    """

    def __init__(self, basepath):
        if isinstance(basepath, Recinfo):
            self._obj = basepath
        else:
            self._obj = Recinfo(basepath)

    def across_time_window(self, spikes, period, window=300, binsize=0.25, **kwargs):
        """Correlation of pairwise correlation across a period by dividing into window size epochs

        Parameters
        ----------
        period: array like
            time period where the pairwise correlations are calculated, in seconds
        window : int, optional
            dividing the period into this size window, by default 900
        binsize : float, optional
            [description], by default 0.25
        """

        # spikes = Spikes(self._obj)

        # # ----- choosing cells ----------------
        # spks = spikes.times
        # stability = spikes.stability.info
        # stable_pyr = np.where((stability.q < 4) & (stability.stable == 1))[0]
        # print(f"Calculating EV for {len(stable_pyr)} stable cells")
        # spks = [spks[_] for _ in stable_pyr]

        epochs = np.arange(period[0], period[1], window)

        pair_corr_epoch = []
        for i in range(len(epochs) - 1):
            epoch_bins = np.arange(epochs[i], epochs[i + 1], binsize)
            spkcnt = np.asarray([np.histogram(x, bins=epoch_bins)[0] for x in spikes])
            epoch_corr = np.corrcoef(spkcnt)
            pair_corr_epoch.append(epoch_corr[np.tril_indices_from(epoch_corr, k=-1)])
        pair_corr_epoch = np.asarray(pair_corr_epoch)

        # masking nan values in the array
        pair_corr_epoch = np.ma.array(pair_corr_epoch, mask=np.isnan(pair_corr_epoch))
        self.corr = np.ma.corrcoef(pair_corr_epoch)  # correlation across windows
        self.time = epochs[:-1] + window / 2

    def pairwise(self, spikes, period, binsize=0.25):
        """Calculates pairwise correlation between given spikes within given period

        Parameters
        ----------
        spikes : list
            list of spike times
        period : list
            time period within which it is calculated , in seconds
        binsize : float, optional
            binning of the time period, by default 0.25 seconds

        Returns
        -------
        N-pairs
            pairwise correlations
        """
        bins = np.arange(period[0], period[1], binsize)
        spk_cnts = np.asarray([np.histogram(cell, bins=bins)[0] for cell in spikes])
        corr = np.corrcoef(spk_cnts)
        return corr[np.tril_indices_from(corr, k=-1)]

    def plot_across_time(self, ax=None, tstart=0, smooth=None, cmap="Spectral_r"):
        """Plots heatmap of correlation matrix calculated in self.across_time_window()

        Parameters
        ----------
        ax : [type], optional
            axis to plot into, by default None
        tstart : int, optional
            if you want to start the time axis at some other time points, by default 0
        cmap : str, optional
            colormap used for heatmap, by default "Spectral_r"
        """

        corr_mat = self.corr.copy()
        np.fill_diagonal(corr_mat, 0)

        if smooth is not None:
            corr_mat = gaussian_filter(corr_mat, sigma=smooth)

        if ax is None:
            _, ax = plt.subplots()

        ax.pcolormesh(self.time - tstart, self.time - tstart, corr_mat, cmap=cmap)
        ax.set_xlabel("Time")
        ax.set_ylabel("Time")
