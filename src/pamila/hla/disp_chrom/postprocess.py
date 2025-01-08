import numpy as np
from pydantic import Field, field_serializer, field_validator

from .. import HlaStage, HlaStageParams, is_machine_default_allowed
from ...machine import Machine
from ...tiled import TiledUid
from ...unit import Q_, ureg
from ...utils import (
    MACHINE_DEFAULT,
    DesignLatticeProperty,
    MachineDefault,
    json_deserialize_design_lat_prop,
    json_serialize_design_lat_prop,
)


class Params(HlaStageParams):
    momentum_compaction: float | DesignLatticeProperty = Field(MACHINE_DEFAULT)
    disp_max_order: int = Field(2, ge=1, description="Max order for dispersion fitting")
    chrom_max_order: int = Field(
        2, ge=1, description="Max order for chromaticity fitting"
    )

    @field_serializer("momentum_compaction")
    def serialize_HlaFlow(self, value):
        return json_serialize_design_lat_prop(value)

    @field_validator("momentum_compaction", mode="before")
    def deserialize_design_lattice_property(cls, value):
        return json_deserialize_design_lat_prop(value)


class Stage(HlaStage):
    def __init__(self, machine: Machine):
        super().__init__(machine)

        default_params = self.get_machine_default_params(__name__)

        self.params = Params(**default_params)

        self._load_design_lat_prop_vals()

    def update_machine_default_params(self, params: Params):
        return super().update_machine_default_params(__name__, params)

    def _load_design_lat_prop_vals(self):
        params = self.params
        design_props = self._machine.get_design_lattice_props()["design_properties"]

        if isinstance(params.momentum_compaction, DesignLatticeProperty):
            design = params.momentum_compaction
            design.value = design_props["alphac"]
            self._alphac = design.value
        else:
            self._alphac = params.momentum_compaction

        if not is_machine_default_allowed():
            if isinstance(self._alphac, MachineDefault):
                raise TypeError(
                    "Machine default is requested, but it does not appear to be set up"
                )

    def run(self):
        params = self.params

        if isinstance(self._output_from_prev_stage, TiledUid):
            raise NotImplementedError
        else:
            prev_output = self._output_from_prev_stage

        delta_freq = Q_.from_list(prev_output["freq_RB"]) - prev_output["init_freq"]

        n = delta_freq.size

        dps = delta_freq / prev_output["init_freq"] / self._alphac * (-1)

        nu = {
            plane: Q_.from_list([d[plane]["mean"] for d in prev_output["tune"]])
            for plane in ["x", "y"]
        }

        orb = {
            plane: [d[plane]["mean"] for d in prev_output["orbit"]]
            for plane in ["x", "y"]
        }
        orb = {plane: np.stack(v) for plane, v in orb.items()}
        orb["s-pos"] = prev_output["orbit"][0]["s-pos"]

        n_order = params.chrom_max_order
        chrom = {}
        chrom_err = {}
        if n > n_order + 1:
            for plane in ["x", "y"]:
                chrom[plane], _cov = np.polyfit(
                    dps.m, nu[plane].m, deg=n_order, cov=True
                )
                chrom_err[plane] = np.sqrt(np.diagonal(_cov))
        else:
            for plane in ["x", "y"]:
                chrom[plane] = np.polyfit(dps.m, nu[plane].m, deg=n_order, cov=False)
                chrom_err[plane] = np.zeros(n_order + 1)

        # Add units
        for plane in ["x", "y"]:
            chrom[plane] *= ureg.dimensionless
            chrom_err[plane] *= ureg.dimensionless

        n_order = params.disp_max_order
        disp = {}
        disp_err = {}
        if n > n_order + 1:
            for plane in ["x", "y"]:
                disp[plane], _cov = np.polyfit(
                    dps.m, orb[plane].to("m").m, deg=n_order, cov=True
                )
                disp_err[plane] = np.sqrt(np.diagonal(_cov)).T
        else:
            for plane in ["x", "y"]:
                disp[plane] = np.polyfit(
                    dps.m, orb[plane].to("m").m, deg=n_order, cov=False
                )
                disp_err[plane] = np.zeros(n_order + 1)

        # Add units
        for plane in ["x", "y"]:
            disp[plane] = [
                disp[plane][i_order, :] * ureg.meter for i_order in range(n_order + 1)
            ]
            disp_err[plane] = [
                disp_err[plane][i_order, :] * ureg.meter
                for i_order in range(n_order + 1)
            ]

        output = dict(params=params)

        output["raw_data"] = {}
        output["raw_data"]["delta"] = dps
        output["raw_data"]["tune"] = nu
        output["raw_data"]["orbit"] = orb

        output["chrom"] = chrom
        output["chrom_err"] = chrom_err
        output["disp"] = disp
        output["disp_err"] = disp_err

        return output
