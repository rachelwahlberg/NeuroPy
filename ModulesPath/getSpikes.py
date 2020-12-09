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
        epochs = behavior_epochs(self._obj)
        spkall = np.concatenate(self.times)

        pre = epochs.pre
        post = epochs.post
        if pre is None and post is not None:
            bins = np.arange(pre[0], post[1], 0.001)
        else:
            print(
                "No pre/post behavioral epochs designated - using entire recording session"
            )
            bins = np.arange(
                spkall.min(), spkall.max(), 0.001
            )  # NRK todo: fill this in

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


class Stability:
    def __init__(self, basepath):

        if isinstance(basepath, Recinfo):
            self._obj = basepath
        else:
            self._obj = Recinfo(basepath)

        filePrefix = self._obj.files.filePrefix

        @dataclass
        class files:
            stability: str = Path(str(filePrefix) + "_stability.npy")

        self.files = files()

        if self.files.stability.is_file():
            self._load()

    def _load(self):
        data = np.load(self.files.stability, allow_pickle=True).item()
        self.info = data["stableinfo"]
        self.isStable = data["isStable"]
        self.bins = data["bins"]
        self.thresh = data["thresh"]

    def firingRate(self, bins=None, thresh=0.3):

        spks = self._obj.spikes.times
        nCells = len(spks)

        # ---- goes to default mode of PRE-POST stability --------
        if bins is None:
            pre = self._obj.epochs.pre
            pre = self._obj.utils.getinterval(period=pre, nbins=3)

            post = self._obj.epochs.post
            post = self._obj.utils.getinterval(period=post, nbins=5)
            total_dur = self._obj.epochs.totalduration
            mean_frate = self._obj.spikes.info.fr
            bins = pre + post
            nbins = len(bins)

        # --- number of spikes in each bin ------
        bin_dur = np.asarray([np.diff(window) for window in bins]).squeeze()
        total_dur = np.sum(bin_dur)
        nspks_bin = np.asarray(
            [np.histogram(cell, bins=np.concatenate(bins))[0][::2] for cell in spks]
        )
        assert nspks_bin.shape[0] == nCells

        total_spks = np.sum(nspks_bin, axis=1)

        if bins is not None:
            nbins = len(bins)
            mean_frate = total_spks / total_dur

        # --- calculate meanfr in each bin and the fraction of meanfr over all bins
        frate_bin = nspks_bin / np.tile(bin_dur, (nCells, 1))
        fraction = frate_bin / mean_frate.reshape(-1, 1)
        assert frate_bin.shape == fraction.shape

        isStable = np.where(fraction >= thresh, 1, 0)
        spkinfo = self._obj.spikes.info[["q", "shank"]].copy()
        spkinfo["stable"] = isStable.all(axis=1).astype(int)

        stbl = {
            "stableinfo": spkinfo,
            "isStable": isStable,
            "bins": bins,
            "thresh": thresh,
        }
        np.save(self.files.stability, stbl)
        self._load()

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
