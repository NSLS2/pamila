import time as ttime  # as defined in ophyd.device
from typing import Dict

from ophyd.utils import ReadOnlyError

from . import (
    MiddleLayerObject,
    MiddleLayerObjectSpec,
    _register_mlo,
    _wait_for_connection,
)
from ..device import create_pamila_device_from_spec
from ..device.base import PamilaDeviceBaseSpec
from ..machine_modes import MachineMode, get_machine_mode
from ..unit import Q_, Unit, fast_convert


class MiddleLayerVariableSpec(MiddleLayerObjectSpec):
    machine_name: str
    simulator_config: str
    pdev_spec_dict: Dict[MachineMode, PamilaDeviceBaseSpec]


class MiddleLayerVariableBase(MiddleLayerObject):
    def __init__(self, spec: MiddleLayerVariableSpec):

        super().__init__(spec)

        self.read_only = None

        self.machine_name = spec.machine_name
        self.simulator_config = spec.simulator_config

        self._pdev_specs = {}
        self._pdevs = {}
        for mode, pdev_spec in spec.pdev_spec_dict.items():
            assert isinstance(mode, MachineMode)
            assert isinstance(pdev_spec, PamilaDeviceBaseSpec)
            assert self.machine_name == pdev_spec.machine_name
            assert mode not in self._pdev_specs
            self._pdev_specs[mode] = pdev_spec
            self._pdevs[mode] = None  # will be instantiated later on demand

        _register_mlo(self, spec.exist_ok)

        self._n_input = {}
        self._n_output = {}

        self._sigs_pend_funcs = {}

        self._non_serializable_attrs = ["_sigs_pend_funcs"]

    def _get_pdev(self, mode: MachineMode):
        if self._pdevs[mode] is None:
            pdev = create_pamila_device_from_spec(self._pdev_specs[mode])
            self._pdevs[mode] = pdev

            if "get" in self._n_output:
                assert pdev._n_output["get"] == self._n_output["get"]
            else:
                self._n_output["get"] = pdev._n_output["get"]

            if "put" in self._n_input:
                assert pdev._n_input["put"] == self._n_input["put"]
            else:
                try:
                    self._n_input["put"] = pdev._n_input["put"]
                except KeyError:
                    pass

        return self._pdevs[mode]

    def _get_all_pdevs(self):
        pdev_list = []
        for mode, pdev in self._pdevs.items():
            if pdev is None:
                pdev = self._get_pdev(mode)
            pdev_list.append(pdev)

        return pdev_list

    def __getstate__(self):

        state = self.__dict__.copy()

        # Exclude the non-serializable attributes
        for attr in self._non_serializable_attrs:
            del state[attr]

        return state

    def __setstate__(self, state):
        self.__dict__.update(state)

        self._sigs_pend_funcs = {}

    def get(self, return_iterable: bool | None = None):
        pdev = self.get_device()
        return pdev.get(return_iterable=return_iterable)

    def read(self):
        pdev = self.get_device()
        return pdev.read()

    def convert_get_values(self, values_w_unit, return_iterable: bool | None = None):
        pdev = self.get_device()
        return pdev.convert_get_values(values_w_unit, return_iterable=return_iterable)

    def _get_sigs_pend_funcs(self, all_modes: bool, all_signals: bool):

        if not all_modes:
            mode = get_machine_mode()
            odev_list = [self.get_ophyd_device()]
        else:
            mode = "all_machine_modes"
            odev_list = [pdev.get_ophyd_device() for pdev in self._get_all_pdevs()]

        if (mode, all_signals) not in self._sigs_pend_funcs:
            signals = []
            pending_funcs = {}
            for odev in odev_list:
                signals.extend(
                    [walk.item for walk in odev.walk_signals(include_lazy=all_signals)]
                )

                pending_funcs.update(
                    {
                        dev: getattr(dev, "_required_for_connection", {})
                        for name, dev in odev.walk_subdevices(include_lazy=all_signals)
                    }
                )
                pending_funcs[odev] = odev._required_for_connection

            self._sigs_pend_funcs[(mode, all_signals)] = signals, pending_funcs

        return self._sigs_pend_funcs[(mode, all_signals)]

    def get_connection_check_args(self, all_modes: bool = False, all_signals=False):

        if False:
            if not all_modes:
                mode = get_machine_mode()
                pdev_list = [self._get_pdev(mode)]
            else:
                mode = "all_machine_modes"
                pdev_list = self._get_all_pdevs()

            if (mode, all_signals) not in self._sigs_pend_funcs:
                self._sigs_pend_funcs[(mode, all_signals)] = self._get_sigs_pend_funcs(
                    pdev_list, all_signals=all_signals
                )

            signals, pending_funcs = self._sigs_pend_funcs[(mode, all_signals)]
        else:
            signals, pending_funcs = self._get_sigs_pend_funcs(all_modes, all_signals)

        mlv_names = [self.name] * len(signals)

        return mlv_names, signals, pending_funcs

    def wait_for_connection(
        self, all_modes: bool = False, all_signals=False, timeout: Q_ | None = Q_("2 s")
    ):

        mlv_names, signals, pending_funcs = self.get_connection_check_args(
            all_modes=all_modes, all_signals=all_signals
        )

        _wait_for_connection(mlv_names, signals, pending_funcs, timeout=timeout)

    def get_device(self):
        mode = get_machine_mode()
        return self._get_pdev(mode)

    def get_ophyd_device(self):
        return self.get_device().get_ophyd_device()

    def get_signal_attr_names(self):
        odev = self.get_ophyd_device()
        return odev.read_attrs

    def get_signals(self, attr_name: str | None = None):
        odev = self.get_ophyd_device()

        if attr_name is None:
            return [getattr(odev, _name) for _name in self.get_signal_attr_names()]
        else:
            return getattr(odev, attr_name)

    def get_setpoint_signals(self):
        return [sig for sig in self.get_signals() if not sig.read_only()]

    def get_read_only_signals(self):
        return [sig for sig in self.get_signals() if sig.read_only()]


class MiddleLayerVariable(MiddleLayerVariableBase):

    def __init__(self, spec: MiddleLayerVariableSpec):

        super().__init__(spec)
        self.read_only = False

    def __repr__(self):
        # return f"MiddleLayerVariable({self._spec!r})"
        return f"MLV: {self.name}"

    def __str__(self):
        return f"MLV: {self.name}"

    def put(self, values_w_unit, *args, **kwargs):
        pdev = self.get_device()
        return pdev.put(values_w_unit, *args, **kwargs)

    def set(self, values_w_unit, *args, **kwargs):
        pdev = self.get_device()
        return pdev.set(values_w_unit, *args, **kwargs)

    def set_and_wait(self, values_w_unit, *args, timeout: Q_ | None = None, **kwargs):

        t0 = ttime.perf_counter()
        state = self.set(values_w_unit, *args, **kwargs)
        dt = None
        if timeout is not None:
            dt = fast_convert(timeout, "s").m - (ttime.perf_counter() - t0)
            if dt < 0.0:
                raise TimeoutError
        state.wait(timeout=dt)

    def convert_put_values(self, values_w_unit):
        pdev = self.get_device()
        return pdev.convert_put_values(values_w_unit)

    def change_set_wait_method(self, method_name: str):
        pdev = self.get_device()
        pdev.change_set_wait_method(method_name)


class MiddleLayerVariableRO(MiddleLayerVariableBase):

    def __init__(self, spec: MiddleLayerVariableSpec):

        super().__init__(spec)
        self.read_only = True

    def __repr__(self):
        # return f"MiddleLayerVariableRO({self._spec!r})"
        return f"MLVRO: {self.name}"

    def __str__(self):
        return f"MLVRO: {self.name}"

    def put(self, *args, **kwargs):
        raise ReadOnlyError

    def set(self, *args, **kwargs):
        raise ReadOnlyError

    def convert_put_values(self, *args, **kwargs):
        raise ReadOnlyError

    def change_set_wait_method(self, *args, **kwargs):
        raise ReadOnlyError
