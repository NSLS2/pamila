from collections.abc import Iterable
import time as ttime

from ophyd import EpicsSignal, EpicsSignalRO, Signal
from ophyd.signal import DEFAULT_EPICSSIGNAL_VALUE
from ophyd.utils import ReadOnlyError
from ophyd.utils.epics_pvs import data_shape, data_type

from .machine_modes import MachineMode
from .sim_interface import SimulatorInterfacePath, get_sim_interface
from .unit import Q_, DimensionalityError, Unit


# Based on
#   ophyd.sim.SynSignal
#   ophyd.sim._SetpointSignal
#   ophyd.sim._ReadbackSignal
class InternalSignal(Signal):
    def __init__(
        self,
        simulator_interface_path: SimulatorInterfacePath,
        sim_pvname,
        **kwargs,
    ):
        super().__init__(name=sim_pvname, **kwargs)
        # Even though setting "name=sim_pvname" here, Signal.name will be
        # eventually overwritten with PamilaSignal's "name".
        # "sim_pvname" is being preserved here, as it will be necessary later
        # in self._initialize_sim_pv_attrs() to connect to the actual SimPV object.
        self._sim_pvname = sim_pvname

        self._sim_itf_path = simulator_interface_path

        self._sim_itf = None

        self._non_serializable_attrs = [
            "_sim_itf",
            "_sim_pv",
            "_read_sim_pvname",
            "precision",
            "enum_strs",
            "_metadata",
        ]

    def __getstate__(self):

        state = self.__dict__.copy()

        # Exclude the non-serializable attributes
        for attr in self._non_serializable_attrs:
            del state[attr]

        return state

    def __setstate__(self, state):
        self.__dict__.update(state)

        self._sim_itf = None

    def _get_sim_itf(self):
        if self._sim_itf is None:
            self._initialize_sim_pv_attrs()

        return self._sim_itf

    def _initialize_sim_pv_attrs(self):

        self._sim_itf = get_sim_interface(self._sim_itf_path)

        self._sim_pv = self._sim_itf.get_sim_pv(self._sim_pvname)

        assert self._sim_pv.sim_pvname == self._sim_pvname
        self._read_sim_pvname = self._sim_pvname

        # To avoid a crash in PamilaSignal.describe():
        self.precision = self._sim_pv.precision
        self.enum_strs = self._sim_pv.enum_strs

        self._metadata.update(
            connected=True,
            write_access=True,
            units=str(self._sim_pv._pint_units),
            timestamp=self._sim_pv.timestamp,
        )

    def get_sim_pv(self):
        if self._sim_itf is None:
            self._initialize_sim_pv_attrs()

        return self._sim_pv

    def get(self):
        sim_pv = self.get_sim_pv()
        self._readback = sim_pv.get()
        return self._readback

    def put(self, value, *, timestamp=None, force=False):
        sim_pv = self.get_sim_pv()
        sim_pv.put(value)
        self._metadata.update(timestamp=sim_pv.timestamp)


class InternalSignalRO(InternalSignal):
    def __init__(
        self,
        simulator_interface_path: SimulatorInterfacePath,
        sim_pvname,
        **kwargs,
    ):
        super().__init__(simulator_interface_path, sim_pvname, **kwargs)

        self._metadata.update(write_access=False)

    def get(self):
        sim_pv = self.get_sim_pv()
        self._readback = sim_pv.get()
        self._metadata.update(timestamp=sim_pv.timestamp)
        return self._readback

    def put(self, value, *, timestamp=None, force=False):
        raise ReadOnlyError("The signal {} is readonly.".format(self.name))

    def set(self, value, *, timestamp=None, force=False):
        raise ReadOnlyError("The signal {} is readonly.".format(self.name))


class PamilaSignal:
    def __init__(
        self,
        mode: MachineMode,
        name,
        unit,
        read_only,
        base_signal_id,
        triggerable=False,
    ):
        self.mode = mode
        self.name = name
        self.unit_str = unit
        self.unit = Unit(unit)
        self._read_only = read_only
        self._base_signal_id = base_signal_id
        self._triggerable = triggerable

    def read_only(self):
        return self._read_only

    def triggerable(self):
        return self._triggerable

    @staticmethod
    def get_method_then_add_unit(get_method):
        def wrapper(self, *args, **kwargs):
            values = get_method(self, *args, **kwargs)
            try:
                self._readback = values * self.unit
            except DimensionalityError:
                raise
            except:
                self._readback = [v * self.unit for v in values]

            return self._readback

        return wrapper

    @staticmethod
    def remove_unit_then_put_method(put_method):
        def wrapper(self, values, *args, **kwargs):
            if isinstance(values, Q_):  # Q_ is also Iterable.
                try:
                    values_wo_unit = values.to(self.unit_str).m
                except DimensionalityError:
                    raise
            elif isinstance(values, Iterable):
                try:
                    values_wo_unit = [v.to(self.unit_str).m for v in values]
                except:
                    raise
            else:
                raise TypeError(f"Wrong type: {type(values)}")

            put_method(self, values_wo_unit, *args, **kwargs)

        return wrapper

    def describe(self):
        """Override EpicsSignalBase.describe() to jsonify data.

        Return the description as a dictionary

        Returns
        -------
        dict
            Dictionary of name and formatted description string
        """

        if self._readback is DEFAULT_EPICSSIGNAL_VALUE:
            val = self.get()
        else:
            val = self._readback
        lower_ctrl_limit, upper_ctrl_limit = self.limits

        if hasattr(self, "_read_pvname"):
            source = f"PV:{self._read_pvname}"
        elif hasattr(self, "_sim_pvname"):
            if not hasattr(self, "_read_sim_pvname"):
                assert isinstance(self, InternalSignal)
                self._initialize_sim_pv_attrs()
            source = f"SIM_PV:{self._read_sim_pvname}"
        else:
            source = f"STORAGE_PV:{self._read_storage_pvname}"

        try:
            val_wo_unit = val.m
            val_unit_str = str(val.u)
            desc = dict(
                source=source,
                dtype=data_type(val_wo_unit),
                shape=data_shape(val_wo_unit),
                raw_units=self._metadata["units"],
                units=val_unit_str,
                lower_ctrl_limit=lower_ctrl_limit,
                upper_ctrl_limit=upper_ctrl_limit,
            )
        except AttributeError:
            desc = dict(
                source=source,
                dtype=data_type(val),
                shape=data_shape(val),
                units=self._metadata["units"],
                lower_ctrl_limit=lower_ctrl_limit,
                upper_ctrl_limit=upper_ctrl_limit,
            )

        if self.precision is not None:
            desc["precision"] = self.precision

        if self.enum_strs is not None:
            desc["enum_strs"] = tuple(self.enum_strs)

        return {self.name: desc}

    def get_base_signal_id(self):
        return self._base_signal_id


class ExternalPamilaEpicsSignal(PamilaSignal, EpicsSignal):
    def __init__(self, pvname, *, mode: MachineMode, name: str, unit: str, **kwargs):
        EpicsSignal.__init__(self, pvname, name=name, **kwargs)
        read_only = False
        base_signal_id = (mode, pvname)
        PamilaSignal.__init__(
            self,
            mode=mode,
            name=name,
            unit=unit,
            read_only=read_only,
            base_signal_id=base_signal_id,
            triggerable=kwargs.get("triggerable", False),
        )
        self._read_only = read_only

    @PamilaSignal.get_method_then_add_unit
    def get(self, *args, **kwargs):
        val_wo_unit = super().get(*args, **kwargs)
        return val_wo_unit

    @PamilaSignal.remove_unit_then_put_method
    def put(self, value_w_unit: Q_, **kwargs):
        super().put(value_w_unit, **kwargs)


class ExternalPamilaEpicsSignalRO(PamilaSignal, EpicsSignalRO):
    def __init__(self, pvname, *, mode: MachineMode, name: str, unit: str, **kwargs):
        EpicsSignalRO.__init__(self, pvname, name=name, **kwargs)
        read_only = True
        base_signal_id = (mode, pvname)
        PamilaSignal.__init__(
            self,
            mode=mode,
            name=name,
            unit=unit,
            read_only=read_only,
            base_signal_id=base_signal_id,
            triggerable=kwargs.get("triggerable", False),
        )
        self._read_only = read_only

    @PamilaSignal.get_method_then_add_unit
    def get(self, *args, **kwargs):
        val_wo_unit = super().get(*args, **kwargs)
        return val_wo_unit


class InternalPamilaSignal(PamilaSignal, InternalSignal):
    def __init__(
        self,
        sim_pvname,
        *,
        mode: MachineMode,
        simulator_interface_path: SimulatorInterfacePath,
        name: str,
        unit: str,
        **kwargs,
    ):
        triggerable = kwargs.pop("triggerable", False)
        InternalSignal.__init__(self, simulator_interface_path, sim_pvname, **kwargs)
        read_only = False
        base_signal_id = (mode, sim_pvname)
        PamilaSignal.__init__(
            self,
            mode=mode,
            name=name,
            unit=unit,
            read_only=read_only,
            base_signal_id=base_signal_id,
            triggerable=triggerable,
        )
        self._read_only = read_only

    @PamilaSignal.get_method_then_add_unit
    def get(self, *args, **kwargs):
        val_wo_unit = super().get(*args, **kwargs)
        return val_wo_unit

    @PamilaSignal.remove_unit_then_put_method
    def put(self, value_w_unit: Q_, **kwargs):
        super().put(value_w_unit, **kwargs)


class InternalPamilaSignalRO(PamilaSignal, InternalSignalRO):
    def __init__(
        self,
        sim_pvname,
        *,
        mode: MachineMode,
        simulator_interface_path: SimulatorInterfacePath,
        name: str,
        unit: str,
        **kwargs,
    ):
        triggerable = kwargs.pop("triggerable", False)
        InternalSignalRO.__init__(self, simulator_interface_path, sim_pvname, **kwargs)
        read_only = True
        base_signal_id = (mode, sim_pvname)
        PamilaSignal.__init__(
            self,
            mode=mode,
            name=name,
            unit=unit,
            read_only=read_only,
            base_signal_id=base_signal_id,
            triggerable=triggerable,
        )
        self._read_only = read_only

    @PamilaSignal.get_method_then_add_unit
    def get(self, *args, **kwargs):
        val_wo_unit = super().get(*args, **kwargs)
        return val_wo_unit


class StorageSignal(Signal):
    def __init__(
        self,
        storage_pvname,
        units: str = "",
        value=0.0,
        **kwargs,
    ):

        super().__init__(name=storage_pvname, value=value, **kwargs)

        self._read_storage_pvname = storage_pvname

        self._value_wo_unit = value

        # To avoid a crash in PamilaSignal.describe():
        self.precision = None
        self.enum_strs = None

        self._metadata.update(
            connected=True, write_access=True, units=units, timestamp=ttime.time()
        )

    def get(self):
        return self._value_wo_unit

    def put(self, value, *, timestamp=None, force=False):
        self._value_wo_unit = value
        self._metadata.update(timestamp=ttime.time())


class UserPamilaSignal(PamilaSignal, StorageSignal):
    def __init__(self, *, mode: MachineMode, name: str, unit: str, **kwargs):
        triggerable = kwargs.pop("triggerable", False)
        StorageSignal.__init__(self, name, units=unit, **kwargs)
        read_only = False
        base_signal_id = (mode, name)
        PamilaSignal.__init__(
            self,
            mode=mode,
            name=name,
            unit=unit,
            read_only=read_only,
            base_signal_id=base_signal_id,
            triggerable=triggerable,
        )
        self._read_only = read_only

    @PamilaSignal.get_method_then_add_unit
    def get(self, *args, **kwargs):
        val_wo_unit = super().get(*args, **kwargs)
        return val_wo_unit

    @PamilaSignal.remove_unit_then_put_method
    def put(self, value_w_unit: Q_, **kwargs):
        super().put(value_w_unit, **kwargs)
