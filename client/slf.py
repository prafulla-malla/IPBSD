"""
user defines storey-loss function parameters
"""
from scipy.interpolate import interp1d
import os
import re
import numpy as np
import pickle
import pandas as pd


class SLF:
    def __init__(self, slfDirectory, y_sls, nst, geometry=0):
        """
        initialize storey loss function definition
        :param slfDirectory: dict                   SLF data file
        :param y_sls: array                         Expected loss ratios (ELRs) associated with SLS
        :param nst: int                             Number of stories
        :param geometry: int                        0 for "2d", 1 for "3d"
        """
        self.slfDirectory = slfDirectory
        self.y_sls = y_sls
        self.nst = nst
        self.geometry = geometry
        # Keys for identifying structural and non-structural components
        self.S_KEY = 1
        self.NS_KEY = 2
        self.PERF_GROUP = ["PSD_S", "PSD_NS", "PFA_NS"]
        # Normalization, currently will do normalization regardless, whereby having summation of max values of SLFs
        # equalling to unity, however in future updates, this will become a user input
        self.NORMALIZE = True
        # Default direction of SLFs to use if "2D" Structure is being considered
        self.DIRECTION = 1

    def slfs(self):
        # Check whether a .csv or .pickle is provided
        for file in os.listdir(self.slfDirectory):
            if not os.path.isdir(self.slfDirectory / file) and (file.endswith(".csv") or file.endswith(".xlsx")):
                func = self.slfs_csv()
                return func
            elif not os.path.isdir(self.slfDirectory / file) and (file.endswith(".pickle") or file.endswith(".pkl")):
                func, SLFs = self.slfs_pickle()
                return func, SLFs
            else:
                raise ValueError("[EXCEPTION] Wrong SLF file format provided! Should be .csv or .pickle")

    def slfs_csv(self):
        """
        SLFs are read and ELRs per performance group are derived
        SLFs for both PFA- and PSD-sensitive components are lumped at storey level, and not at each floor
        :return: dict                               SLF 1d interpolation functions and ELRs as arrays within a dict
        """
        # TODO, add generation of SLFs
        for file in os.listdir(self.slfDirectory):
            if not os.path.isdir(self.slfDirectory / file):
                # Read the file (needs to be single file)
                filename = self.slfDirectory / file
                df = pd.read_excel(io=filename)

                # Get the feature names
                columns = np.array(df.columns, dtype="str")

                # Subdivide SLFs into EDPs and Losses
                testCol = np.char.startswith(columns, "E")
                lossCol = columns[testCol]
                edpCol = columns[not testCol]

                edps = df[edpCol]
                edps_array = edps.to_numpy(dtype=float)
                loss = df[lossCol].to_numpy(dtype=float)

                # EDP names
                edp_cols = np.array(edps.columns, dtype="str")

                # SLF interpolation functions and ELRs
                factor = 3 if self.nst > 2 else 2
                # Number of performance groups
                ngroups = int(len(columns) / factor / 2)

                # Get the total loss and normalize if specified
                if self.NORMALIZE:
                    # Addition
                    add = sum(loss[-1][3:6]) * (self.nst - 3) if factor == 3 else 0
                    maxCost = np.sum(loss, axis=1)[-1] + add
                    loss = loss / maxCost

                # Assumption: typical storey SLFs are the same
                func = {"y": {}, "interpolation": {}}

                for i in range(ngroups):
                    # Select group name
                    group = edp_cols[i][:-2]

                    # Initialize
                    func["y"][group] = {}
                    func["interpolation"][group] = {}
                    for st in range(self.nst):
                        if st != 0 and st != self.nst - 1:
                            st_id = 1
                        elif st == self.nst - 1:
                            st_id = 2
                        else:
                            st_id = st
                        l = loss[:, i + ngroups * st_id]
                        edp = edps_array[:, i + ngroups * st_id]
                        func["y"][group][st] = max(l) * self.y_sls
                        func["interpolation"][group][st] = interp1d(l, edp)

                return func

    def slfs_pickle(self):
        """
        SLFs are read and ELRs per performance group are derived
        :return: dict                               SLF 1d interpolation functions and ELRs as arrays within a dict
        """
        '''
        Inputs:
            EAL_limit: In % or currency
            Normalize: True or False

        If EAL is in %, then normalize should be set to True, normalization based on sum(max(SLFs))
        If EAL is in currency, normalize is an option
        If normalize is True, then normalization of SLFs will be carried out

        It is important to note, that the choice of the parameters is entirely on the user, 
        as the software will run successfully regardless.
        '''
        # SLF output file naming conversion is important (disaggregation is based on that)
        # IPBSD currently supports use of 3 distinct performance groups
        # i.e. PSD_NS, PSD_S, PFA_NS
        # Initialize
        SLFs = {"Directional": {"PSD_NS": {}, "PSD_S": {}},
                "Non-directional": {"PFA_NS": {}, "PSD_NS": {}, "PSD_S": {}}}

        # Initialize Total cost of inventory
        pfa = None
        psd = None
        maxCost = 0
        for file in os.listdir(self.slfDirectory):
            if not os.path.isdir(self.slfDirectory / file) and not file.endswith(".csv") and not file.endswith(".xlsx"):

                # Open slf file
                f = open(self.slfDirectory / file, "rb")
                df = pickle.load(f)
                f.close()

                str_list = re.split("_+", file)
                # Test if "2d" structure is being considered only
                if self.geometry == 0:
                    if str_list[0][-1] == "1" or len(str_list) == 2:
                        # Perform the loop if dir1 or non-directional components
                        pass
                    else:
                        # Skip the loop
                        continue

                if len(str_list) == 2:
                    direction = None
                    non_dir = "Non-directional"
                else:
                    direction = str_list[0][-1]
                    non_dir = "Directional"
                edp = str_list[-1][0:3]

                if edp == "pfa":
                    story = str_list[0][-1]
                    for key in df.keys():
                        if not key.startswith("SLF"):
                            loss = df[key]["slfs"]["mean"]
                            SLFs[non_dir]["PFA_NS"][str(int(story) - 1)] = {"loss": loss,
                                                                            "edp": df[key]["fragilities"]["EDP"]}
                            pfa = df[key]["fragilities"]["EDP"]
                            maxCost += max(loss)
                else:
                    story = str_list[-2][-1]
                    for key in df.keys():
                        if not key.startswith("SLF"):
                            if key == str(self.S_KEY):
                                # if key == str(s_key):
                                tag = "PSD_S"
                            elif key == str(self.NS_KEY):
                                tag = "PSD_NS"
                            else:
                                raise ValueError("[EXCEPTION] Wrong group name provided!")

                            if direction is not None:
                                if "dir" + direction not in SLFs[non_dir][tag].keys():
                                    SLFs[non_dir][tag]["dir" + direction] = {}
                                loss = df[key]["slfs"]["mean"]
                                SLFs[non_dir][tag]["dir" + direction].update({story: {"loss": loss,
                                                                                      "edp": df[key]["fragilities"][
                                                                                          "EDP"]}})
                                maxCost += max(loss)
                            else:
                                loss = df[key]["slfs"]["mean"]
                                SLFs[non_dir][tag].update({story: {"loss": loss,
                                                                   "edp": df[key]["fragilities"]["EDP"]}})
                                maxCost += max(loss)
                            psd = df[key]["fragilities"]["EDP"]

        # SLFs should be exported for use in LOSS
        # SLFs are disaggregated based on story, direction and EDP-sensitivity
        # Next, the SLFs are lumped at each storey based on EDP-sensitivity
        # EDP range should be the same for each corresponding group
        # Create SLF functions based on number of stories
        slf_functions = {}
        for group in self.PERF_GROUP:
            slf_functions[group] = {}
            # Add for zero floor for PFA sensitive group
            if group == "PFA_NS":
                slf_functions[group]["0"] = np.zeros(pfa.shape)
            for st in range(1, self.nst + 1):
                if group == "PFA_NS":
                    edp = pfa
                else:
                    edp = psd
                slf_functions[group][str(st)] = np.zeros(edp.shape)

        # Generating the SLFs for each Performance Group of interest at each storey level
        if self.NORMALIZE:
            factor = maxCost
        else:
            factor = 1.0

        for i in SLFs:
            for j in SLFs[i]:
                if i == "Directional":
                    for k in SLFs[i][j]:
                        for st in SLFs[i][j][k]:
                            loss = SLFs[i][j][k][st]["loss"]
                            slf_functions[j][st] += loss / factor
                else:
                    for st in SLFs[i][j]:
                        loss = SLFs[i][j][st]["loss"]
                        slf_functions[j][st] += loss / factor

        # SLF interpolation functions and ELRs
        func = {"y": {}, "interpolation": {}}
        for i in slf_functions:
            if i == "PFA_NS" or i == "PFA":
                edp = pfa
            else:
                # EPD range for both NS and S should be the same
                edp = psd
            func["y"][i] = {}
            func["interpolation"][i] = {}
            for st in slf_functions[i]:
                func["y"][i][st] = max(slf_functions[i][st]) * self.y_sls
                func["interpolation"][i][st] = interp1d(slf_functions[i][st], edp)

        return func, SLFs
