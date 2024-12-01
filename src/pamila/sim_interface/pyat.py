from pathlib import Path
import time
from typing import Dict, Iterable, List

import at
from ophyd.utils import ReadOnlyError
from pydantic import BaseModel

from . import (
    IntegerPlane,
    MachineMode,
    SimCalculation,
    SimulatorPvDefinition,
    StringPlane,
    get_sim_pvprefix,
)
from ..unit import Q_, Unit
from ..utils import AttributeAccess as AA
from ..utils import ChainedPropertyFetcher, ChainedPropertyPusher
from ..utils import KeyIndexAccess as KIA


class ClosedOrbitCalcOptions(BaseModel):
    refpts: at.lattice.utils.Refpts = None

    model_config = {"arbitrary_types_allowed": True}


class ClosedOrbitCalcData(BaseModel):
    x: Iterable[float] | None = None
    y: Iterable[float] | None = None
    dp: float | None = None


class TuneCalcData(BaseModel):
    x: float | None = None
    y: float | None = None


def get_rf_frequency(ring):
    return at.get_rf_frequency(ring)  # [Hz]


def get_beam_current(ring):
    return ring.get_beam_current()  # [A]


class Interface:
    name: str = "pyat"

    def __init__(
        self, machine_mode: MachineMode, sim_pv_defs: Dict[str, SimulatorPvDefinition]
    ) -> None:
        self.package = at

        self._machine_mode = machine_mode
        self._sim_pv_defs = sim_pv_defs

        self._lattice = None

        self._sim_pvs = {}

        self._signals = {}

        # The order matters here: To compute tunes correctly, the close orbit
        # needs to be computed before that.
        self._recalc_flags = {
            k: True for k in (SimCalculation.CLOSED_ORBIT, SimCalculation.TUNE)
        }

        self._calc_opts = {SimCalculation.CLOSED_ORBIT: ClosedOrbitCalcOptions()}

        self._vars_outside_pyat = {
            "rf_freq_change": 0.0,  # [Hz]
            "closed_orbit": ClosedOrbitCalcData(),
            "tune": TuneCalcData(),
        }

    def add_signal(self, signal_id, signal):

        assert signal_id not in self._signals
        self._signals[signal_id] = signal

    def load_lattice(self, lat_file_path: Path):

        ring = at.load_lattice(lat_file_path)
        ring.disable_6d()

        ring.set_beam_current(400e-3)

        self._lattice = ring

    def get_lattice(self):
        return self._lattice

    def add_sim_pv(self, sim_pvname: str, sim_pv):
        self._sim_pvs[sim_pvname] = sim_pv

    def _instantiate_sim_pv(self, sim_pvname: str):
        sim_pvprefix = get_sim_pvprefix(self._machine_mode)
        sim_pvsuffix = sim_pvname[len(sim_pvprefix) :]
        pv_def = self._sim_pv_defs[sim_pvsuffix]
        kwargs = pv_def.kwargs
        args = pv_def.args
        match pv_def.pvclass:
            case "CorrectorSimPV":
                sel_class = CorrectorSimPV
                args = [pv_def.args[0], getattr(IntegerPlane, pv_def.args[1])]
            case "BPMSimPV":
                sel_class = BPMSimPV
                args = [pv_def.args[0], getattr(StringPlane, pv_def.args[1])]
            case "QuadrupoleSimPV":
                sel_class = QuadrupoleSimPV
            case "SextupoleSimPV":
                sel_class = SextupoleSimPV
            case "RfFreqSimPV":
                sel_class = RfFreqSimPV
            case "BeamCurrentSimPV":
                sel_class = BeamCurrentSimPV
            case "TuneSimPV":
                sel_class = TuneSimPV
                args = [getattr(StringPlane, pv_def.args[0])]
            case _:
                raise NotImplementedError
        self._sim_pvs[sim_pvname] = sel_class(self, sim_pvname, *args, **kwargs)

    def get_sim_pv(self, sim_pvname: str):
        if sim_pvname not in self._sim_pvs:
            self._instantiate_sim_pv(sim_pvname)
        return self._sim_pvs[sim_pvname]

    def request_recalcs(self, recalcs_after_put: List[SimCalculation]):
        for calc in recalcs_after_put:
            self._recalc_flags[calc] = True
            if calc == SimCalculation.TUNE:
                assert self._recalc_flags[SimCalculation.CLOSED_ORBIT] is True

    def _get_recalcs_to_perform(self, recalcs_before_get):

        return [
            calc_enum
            for calc_enum, need_recalc in self._recalc_flags.items()
            if need_recalc and (calc_enum in recalcs_before_get)
        ]

    def run_recalcs(self, recalcs_before_get):

        recalcs = self._get_recalcs_to_perform(recalcs_before_get)

        for calc_enum in recalcs:
            self._recalc(calc_enum)  # Run actual calculation
            self._recalc_flags[calc_enum] = False  # Reset the flag

        recalcs = self._get_recalcs_to_perform(recalcs_before_get)

        assert recalcs == []

    def set_closed_orbit_refpts(self, refpts: at.lattice.utils.Refpts):
        self._calc_opts[SimCalculation.CLOSED_ORBIT].refpts = refpts

    def _get_uint32refpts_for_calc(self, calc_enum: SimCalculation):

        refpts = self._calc_opts[calc_enum].refpts
        if not isinstance(refpts, at.lattice.utils.Uint32Refpts):
            if refpts is None:
                if False:
                    refpts = at.lattice.utils.All
                else:
                    refpts = at.Monitor
            uint32refpts = at.get_uint32_index(self._lattice, refpts)
            self._calc_opts[calc_enum].refpts = uint32refpts

        return self._calc_opts[calc_enum].refpts

    def _recalc(self, calc_enum: SimCalculation):

        match calc_enum:
            case SimCalculation.CLOSED_ORBIT:
                self._calc_closed_orbit()

            case SimCalculation.TUNE:
                self._calc_tune()

            case _:
                raise NotImplementedError

    def _calc_closed_orbit(self):

        storage = self._vars_outside_pyat

        uint32refpts = self._get_uint32refpts_for_calc(SimCalculation.CLOSED_ORBIT)

        df = storage["rf_freq_change"]

        CO6_b, CO6 = at.find_sync_orbit(self._lattice, df=df, refpts=uint32refpts)

        storage["closed_orbit"].x = CO6[:, 0]  # [m]
        storage["closed_orbit"].y = CO6[:, 2]  # [m]
        storage["closed_orbit"].dp = CO6_b[4]  # [dimensionless]

    def _calc_tune(self):

        storage = self._vars_outside_pyat

        dp = storage["closed_orbit"].dp

        twiss_b, globval, twiss_sel = at.get_optics(self._lattice, refpts=None, dp=dp)

        storage["tune"].x = globval.tune[0]  # [dimensionless]
        storage["tune"].y = globval.tune[1]  # [dimensionless]


class SimPV:
    def __init__(
        self,
        sim_itf: Interface,
        sim_pvname: str,
        units: str = "",
        recalcs_before_get: List[SimCalculation] | None = None,
        recalcs_after_put: List[SimCalculation] | None = None,
    ):

        self._interface = sim_itf

        self.sim_pvname = sim_pvname
        self._interface.add_sim_pv(sim_pvname, self)

        self._pint_units = Unit(units)

        # To avoid a crash in MachineSignal.describe():
        self.precision = None
        self.enum_strs = None

        self._getter = None
        self._recalcs_before_get = (
            [] if recalcs_before_get is None else recalcs_before_get
        )

        self._setter = None
        self._recalcs_after_put = [] if recalcs_after_put is None else recalcs_after_put

        self._timestamp = time.time()

        self.read_only = False

    def get(self):
        self._interface.run_recalcs(self._recalcs_before_get)
        return self._getter()

    def put(self, new_value):
        changed = self._setter(new_value)
        self._timestamp = time.time()
        if changed:
            self._request_recalcs()

    def _request_recalcs(self):
        self._interface.request_recalcs(self._recalcs_after_put)

    @property
    def timestamp(self):
        return self._timestamp


class SimPVRO(SimPV):
    def __init__(
        self,
        sim_itf: Interface,
        sim_pvname: str,
        units: str = "",
        recalcs_before_get: List[SimCalculation] | None = None,
    ):

        super().__init__(
            sim_itf, sim_pvname, units=units, recalcs_before_get=recalcs_before_get
        )

        self.read_only = True

    def get(self):
        value = super().get()
        self._timestamp = time.time()
        return value

    def put(self, new_value):
        raise ReadOnlyError


class RfFreqSimPV(SimPV):
    def __init__(self, sim_itf: Interface, sim_pvname: str):

        recalcs_after_put = [SimCalculation.CLOSED_ORBIT, SimCalculation.TUNE]

        units = "Hz"

        super().__init__(
            sim_itf, sim_pvname, units=units, recalcs_after_put=recalcs_after_put
        )

        self._lattice = self._interface.get_lattice()

    def get(self):
        f0 = get_rf_frequency(self._lattice)
        df = self._interface._vars_outside_pyat["rf_freq_change"]
        return f0 + df

    def put(self, new_value):
        old_df = self._interface._vars_outside_pyat["rf_freq_change"]
        f0 = get_rf_frequency(self._lattice)
        new_df = new_value - f0
        self._interface._vars_outside_pyat["rf_freq_change"] = new_df

        if new_df != old_df:
            self._request_recalcs()


class CorrectorSimPV(SimPV):
    def __init__(
        self,
        sim_itf: Interface,
        sim_pvname: str,
        uint32_index: int,
        plane: IntegerPlane,
    ):

        recalcs_after_put = [SimCalculation.CLOSED_ORBIT, SimCalculation.TUNE]

        units = "rad"

        super().__init__(
            sim_itf, sim_pvname, units=units, recalcs_after_put=recalcs_after_put
        )

        self._uint32_index = uint32_index
        self.plane = plane

        lattice = self._interface.get_lattice()
        element = lattice[uint32_index]
        access_list = [AA("KickAngle"), KIA(plane.value)]
        self._getter = ChainedPropertyFetcher(element, access_list).get
        self._setter = ChainedPropertyPusher(element, access_list).put


class AbstractQuadSextSimPV(SimPV):
    def __init__(
        self, sim_itf: Interface, sim_pvname: str, uint32_index: int, units: str = ""
    ):

        recalcs_after_put = [SimCalculation.CLOSED_ORBIT, SimCalculation.TUNE]

        super().__init__(
            sim_itf, sim_pvname, units=units, recalcs_after_put=recalcs_after_put
        )

        self._uint32_index = uint32_index
        lattice = self._interface.get_lattice()
        self._element = lattice[uint32_index]


class QuadrupoleSimPV(AbstractQuadSextSimPV):
    def __init__(self, sim_itf: Interface, sim_pvname: str, uint32_index: int):
        units = "m^{-2}"  # for "K"
        super().__init__(sim_itf, sim_pvname, uint32_index, units=units)

        access_list = [AA("K")]
        self._getter = ChainedPropertyFetcher(self._element, access_list).get
        self._setter = ChainedPropertyPusher(self._element, access_list).put


class SextupoleSimPV(AbstractQuadSextSimPV):
    def __init__(self, sim_itf: Interface, sim_pvname: str, uint32_index: int):
        units = "m^{-3}"  # for "H"
        super().__init__(sim_itf, sim_pvname, uint32_index, units=units)

        access_list = [AA("H")]
        self._getter = ChainedPropertyFetcher(self._element, access_list).get
        self._setter = ChainedPropertyPusher(self._element, access_list).put


class BPMSimPV(SimPVRO):
    def __init__(
        self, sim_itf: Interface, sim_pvname: str, uint32_index: int, plane: StringPlane
    ):

        recalcs_before_get = [SimCalculation.CLOSED_ORBIT]

        units = "m"

        super().__init__(
            sim_itf, sim_pvname, units=units, recalcs_before_get=recalcs_before_get
        )

        storage = self._interface._vars_outside_pyat

        uint32refpts = self._interface._get_uint32refpts_for_calc(
            SimCalculation.CLOSED_ORBIT
        )
        sub_index = uint32refpts.tolist().index(uint32_index)
        access_list = [AA(plane.value), KIA(sub_index)]

        self._getter = ChainedPropertyFetcher(storage["closed_orbit"], access_list).get


class TuneSimPV(SimPVRO):
    def __init__(self, sim_itf: Interface, sim_pvname: str, plane: StringPlane):

        recalcs_before_get = [SimCalculation.CLOSED_ORBIT, SimCalculation.TUNE]

        units = ""

        super().__init__(
            sim_itf, sim_pvname, units=units, recalcs_before_get=recalcs_before_get
        )

        storage = self._interface._vars_outside_pyat

        access_list = [AA(plane.value)]

        self._getter = ChainedPropertyFetcher(storage["tune"], access_list).get


class BeamCurrentSimPV(SimPVRO):
    def __init__(self, sim_itf: Interface, sim_pvname: str):

        recalcs_before_get = []

        units = "A"

        super().__init__(
            sim_itf, sim_pvname, units=units, recalcs_before_get=recalcs_before_get
        )

        lattice = self._interface.get_lattice()

        self._getter = lattice.get_beam_current
