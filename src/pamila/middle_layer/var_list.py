from __future__ import annotations

import asyncio
from collections import defaultdict
from copy import deepcopy
from enum import Enum
from functools import partial
import threading
import time as ttime  # as defined in ophyd.device
from typing import List

from ophyd.utils import ReadOnlyError
from pydantic import field_serializer, field_validator

from . import (
    MiddleLayerObject,
    MiddleLayerObjectSpec,
    _register_mlo,
    _threaded_asyncio_runner,
    _wait_for_connection,
)
from ..machine_modes import get_machine_mode
from ..unit import Q_, DimensionalityError
from .variable import MiddleLayerVariable, MiddleLayerVariableRO


async def _async_mlv_get(mlv: MiddleLayerVariable | MiddleLayerVariableRO):
    loop = asyncio.get_running_loop()
    func = partial(mlv.get, return_iterable=True)
    value = await loop.run_in_executor(None, func)
    return value


async def mlv_paralle_get(mlvs: List[MiddleLayerVariable | MiddleLayerVariableRO]):
    tasks = [_async_mlv_get(mlv) for mlv in mlvs]
    results = await asyncio.gather(*tasks)
    flat_results = [item for sublist in results for item in sublist]
    return flat_results


async def _async_mlv_read(mlv: MiddleLayerVariable | MiddleLayerVariableRO):
    loop = asyncio.get_running_loop()
    d = await loop.run_in_executor(None, mlv.read)
    return d


async def mlv_paralle_read(mlvs: List[MiddleLayerVariable | MiddleLayerVariableRO]):
    tasks = [_async_mlv_read(mlv) for mlv in mlvs]
    results = await asyncio.gather(*tasks)
    d = {}
    for r in results:
        d.update(r)
    return d


async def _async_mlv_put(mlv: MiddleLayerVariable, values_w_unit, *args, **kwargs):
    loop = asyncio.get_running_loop()
    func = partial(mlv.put, values_w_unit, *args, **kwargs)
    await loop.run_in_executor(None, func)
    return


async def mlv_paralle_put(
    mlvs: List[MiddleLayerVariable], list_of_values_w_unit: List, *args, **kwargs
):
    tasks = [
        _async_mlv_put(mlv, vals_w_unit, *args, **kwargs)
        for mlv, vals_w_unit in zip(mlvs, list_of_values_w_unit)
    ]
    await asyncio.gather(*tasks)
    return


async def _async_mlv_set(mlv: MiddleLayerVariable, values_w_unit, *args, **kwargs):
    loop = asyncio.get_running_loop()
    func = partial(mlv.set, values_w_unit, *args, **kwargs)
    status = await loop.run_in_executor(None, func)
    return status


async def mlv_paralle_set(
    mlvs: List[MiddleLayerVariable], list_of_values_w_unit: List, *args, **kwargs
):
    tasks = [
        _async_mlv_set(mlv, vals_w_unit, *args, **kwargs)
        for mlv, vals_w_unit in zip(mlvs, list_of_values_w_unit)
    ]
    set_states = await asyncio.gather(*tasks)
    return set_states


class MiddleLayerVariableListSpec(MiddleLayerObjectSpec):
    mlvs: List[MiddleLayerVariable]
    ignore_put_collision: bool = False

    model_config = {"arbitrary_types_allowed": True, "extra": "forbid"}

    @field_serializer("mlvs")
    def serialize_mlvs(self, value):
        return [dict(name=mlv.name, machine_name=mlv.machine_name) for mlv in value]


class MiddleLayerVariableListROSpec(MiddleLayerObjectSpec):
    mlvs: List[MiddleLayerVariableRO]

    model_config = {"arbitrary_types_allowed": True, "extra": "forbid"}

    @field_serializer("mlvs")
    def serialize_mlvs(self, value):
        return [dict(name=mlv.name, machine_name=mlv.machine_name) for mlv in value]


class MiddleLayerVariableListBase(MiddleLayerObject):
    def __init__(
        self, spec: MiddleLayerVariableListSpec | MiddleLayerVariableListROSpec
    ):
        super().__init__(spec)

        self.read_only = None

        assert spec.mlvs != []

        machine_names = []
        for mlv in spec.mlvs:
            machine_names.append(mlv.machine_name)
        self._all_mlvs = spec.mlvs

        machine_names = list(set(machine_names))
        match len(machine_names):
            case 1:
                self.machine_name = machine_names[0]
            case 0:
                raise RuntimeError("Zero machine specified")
            case _:
                self.machine_name = "_multi_machine"
        _register_mlo(self, spec.exist_ok)

        self._status_list = [True] * len(spec.mlvs)
        self._status_mlvl = None

        self._mlvs = []
        self._mlv_names = []
        self._slices = {"get": [], "put": []}
        self._sigs_pend_funcs = {}
        self._reinitialize_on_enabled_status_change()

        self._non_serializable_attrs = ["_sigs_pend_funcs"]

    def __getstate__(self):

        state = self.__dict__.copy()

        # Exclude the non-serializable attributes
        for attr in self._non_serializable_attrs:
            del state[attr]

        return state

    def __setstate__(self, state):
        self.__dict__.update(state)

        self._sigs_pend_funcs = {}

    def _reinitialize_on_enabled_status_change(self):

        self._mlvs.clear()
        self._mlv_names.clear()
        self._slices["get"].clear()
        self._slices["put"].clear()
        self._sigs_pend_funcs.clear()

        self._mlvs.extend(
            [mlv for mlv, enabled in zip(self._all_mlvs, self._status_list) if enabled]
        )

        self._mlv_names.extend([v.name for v in self._mlvs])

        n_mlvs = len(self._mlvs)

        get_index = 0
        put_index = 0
        for mlv in self._mlvs:
            try:
                n = mlv._n_output["get"]
            except KeyError:
                # mlv._n_output is empty because pdev not initialized yet
                mlv.get_device()  # initializing pdev
                n = mlv._n_output["get"]
            self._slices["get"].append(slice(get_index, get_index + n))
            get_index += n

            try:
                n = mlv._n_input["put"]
                self._slices["put"].append(slice(put_index, put_index + n))
                put_index += n
            except KeyError:
                continue
        assert len(self._slices["get"]) == n_mlvs
        assert len(self._slices["put"]) in (0, n_mlvs)

    def get_all_mlvs(self):
        return self._all_mlvs

    def get_enabled_mlvs(self):
        self._check_enabled_status_and_adjust()
        return self._mlvs

    def __getitem__(self, index):
        match index:
            case slice() | int():
                return self.get_enabled_mlvs()[index]
            case _:
                raise TypeError("Index must be an integer or slice")

    def __setitem__(self, index, value):
        match index:
            case slice() | int():
                self.get_enabled_mlvs()[index] = value
            case _:
                raise TypeError("Index must be an integer or slice")

    def __len__(self):
        return len(self.get_enabled_mlvs())

    def _get_sigs_pend_funcs(self, all_modes: bool, all_signals: bool):
        if not all_modes:
            mode = get_machine_mode()
        else:
            mode = "all_machine_modes"

        if (mode, all_signals) not in self._sigs_pend_funcs:
            mlv_names = []
            signals = []
            pending_funcs = {}
            for mlv in self.get_enabled_mlvs():
                _signals, _pending_funcs = mlv._get_sigs_pend_funcs(
                    all_modes, all_signals
                )
                signals.extend(_signals)
                pending_funcs.update(_pending_funcs)
                mlv_names.extend([mlv.name] * len(_signals))
            self._sigs_pend_funcs[(mode, all_signals)] = (
                mlv_names,
                signals,
                pending_funcs,
            )

        return self._sigs_pend_funcs[(mode, all_signals)]

    def wait_for_connection(
        self,
        all_modes: bool = False,
        all_signals: bool = False,
        timeout: Q_ | None = Q_("2 s"),
    ):
        mlv_names, signals, pending_funcs = self._get_sigs_pend_funcs(
            all_modes, all_signals
        )

        _wait_for_connection(mlv_names, signals, pending_funcs, timeout=timeout)

    def get_enabled_status(self):
        return deepcopy(self._status_list)

    def put_enabled_status(self, new_status_list: List):
        assert len(new_status_list) == self.get_all_mlv_count()

        if all(
            [
                v_new == v_current
                for v_new, v_current in zip(new_status_list, self._status_list)
            ]
        ):
            return

        self._status_list.clear()
        self._status_list.extend(new_status_list)

        self._reinitialize_on_enabled_status_change()

    def _check_enabled_status_and_adjust(self):
        if self._status_mlvl is not None:
            self._status_mlvl.auto_update_status()
            self.put_enabled_status(self._status_mlvl.get_enabled_status())

    def update_status_mlvl(self):
        """Force udpate"""
        if self._status_mlvl is None:
            raise RuntimeError("Status MLV list has not been specified")

        self._status_mlvl.update_enabled_status()

        self.put_enabled_status(self._status_mlvl.get_enabled_status())

    def get(self, return_flat: bool = True):

        # t0 = ttime.perf_counter()

        if True:
            results = []
            for mlv in self.get_enabled_mlvs():
                results.extend(mlv.get(return_iterable=True))
        elif False:  # Works in scripts, but not in Jupyter notebooks
            results = asyncio.run(mlv_paralle_get(self.get_enabled_mlvs()))
        else:
            # TODO: Fix crashes (if a simulator needs to re-compute orbit, etc.
            # in paralle)
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop is None:  # No running loop, safe to use asyncio.run()
                results = asyncio.run(mlv_paralle_get(self.get_enabled_mlvs()))
            else:  # An event loop is already running (e.g., Jupyter).
                # Cannot use asyncio.run() directly.

                if False:
                    new_loop = asyncio.new_event_loop()

                    # Start the event loop in a separate thread
                    def run_loop():
                        asyncio.set_event_loop(new_loop)
                        new_loop.run_forever()

                    thread = threading.Thread(target=run_loop, daemon=True)
                    thread.start()

                    future = asyncio.run_coroutine_threadsafe(
                        mlv_paralle_get(self.get_enabled_mlvs()), new_loop
                    )
                    results = future.result()

                    # Stop the loop and wait for the thread to finish
                    new_loop.call_soon_threadsafe(new_loop.stop)
                    thread.join()
                else:
                    coroutine = mlv_paralle_get(self.get_enabled_mlvs())
                    results = _threaded_asyncio_runner(coroutine)

        # print(f"MLVL async get took {ttime.perf_counter()-t0:.3f} [s]")

        try:
            results = Q_.from_list(results)
        except DimensionalityError:
            pass

        if not return_flat:
            temp = []
            for s_ in self._slices["get"]:
                temp.append(results[s_])
            results = temp

        return results

    def read(self):
        # t0 = ttime.perf_counter()

        if True:
            results = {}
            for mlv in self.get_enabled_mlvs():
                r_d = mlv.read()
                results.update(r_d)
        elif False:  # Works in scripts, but not in Jupyter notebooks
            results = asyncio.run(mlv_paralle_read(self.get_enabled_mlvs()))
        else:
            # TODO: Fix crashes (if a simulator needs to re-compute orbit, etc.
            # in paralle)
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            coroutine = mlv_paralle_read(self.get_enabled_mlvs())

            if loop is None:  # No running loop, safe to use asyncio.run()
                results = asyncio.run(coroutine)
            else:  # An event loop is already running (e.g., Jupyter).
                # Cannot use asyncio.run() directly.
                results = _threaded_asyncio_runner(coroutine)

        # print(f"MLVL async read took {ttime.perf_counter()-t0:.3f} [s]")

        return results

    def get_all_mlv_count(self):
        return len(self._all_mlvs)

    def get_all_mlv_names(self):
        return [mlv.name for mlv in self._all_mlvs]

    def get_mlv_names(self):
        return self._mlv_names.copy()

    def add_status_mlvl(self, status_mlvl: MiddleLayerVariableStatusList):

        assert isinstance(status_mlvl, MiddleLayerVariableStatusList)
        assert status_mlvl.get_all_mlv_count() == self.get_all_mlv_count()

        self._status_mlvl = status_mlvl


class MiddleLayerVariableList(MiddleLayerVariableListBase):
    def __init__(self, spec: MiddleLayerVariableListSpec):
        super().__init__(spec)

        self.read_only = False

        if not spec.ignore_put_collision:
            self.assert_collisionless_put()

    def assert_collisionless_put(self):
        """ " Make sure that self.put() will NOT result in writing different
        values to an identical underlying signal."""

        output_psigs = defaultdict(list)

        for mlv in self._all_mlvs:
            for mode in mlv._pdevs.keys():
                pdev = mlv._get_pdev(mode)
                odev = pdev.get_ophyd_device()
                output_psigs[mode].extend(odev._output_psigs.get("put", []))

        for mode, psigs in output_psigs.items():
            base_signal_ids = [s.get_base_signal_id() for s in psigs]
            assert len(base_signal_ids) == len(set(base_signal_ids))

    def put(self, values_w_unit, *args, **kwargs):

        # t0 = ttime.perf_counter()

        mlvs = self.get_enabled_mlvs()

        partitioned = []
        # self.get_enabled_mlvs() can change self._slices
        for s_ in self._slices["put"]:
            partitioned.append(values_w_unit[s_])

        if True:
            for mlv, vals_w_unit in zip(mlvs, partitioned):
                mlv.put(vals_w_unit, *args, **kwargs)
        else:
            asyncio.run(mlv_paralle_put(mlvs, partitioned, *args, **kwargs))

        # print(f"MLVL async put took {ttime.perf_counter()-t0:.3f} [s]")

    def set(self, values_w_unit, *args, **kwargs):

        # t0 = ttime.perf_counter()

        mlvs = self.get_enabled_mlvs()

        partitioned = []
        # self.get_enabled_mlvs() can change self._slices
        for s_ in self._slices["put"]:
            partitioned.append(values_w_unit[s_])

        if True:
            set_states = []
            for mlv, vals_w_unit in zip(mlvs, partitioned):
                set_states.append(mlv.set(vals_w_unit, *args, **kwargs))
        else:
            set_states = asyncio.run(
                mlv_paralle_set(mlvs, partitioned, *args, **kwargs)
            )

        # print(f"MLVL async set took {ttime.perf_counter()-t0:.3f} [s]")

        return set_states

    def set_and_wait(self, values_w_unit, *args, timeout: Q_ | None = None, **kwargs):

        t0 = ttime.perf_counter()
        set_states = self.set(values_w_unit, *args, **kwargs)
        dt = None
        for state in set_states:
            if timeout is not None:
                dt = timeout.to("s").m - (ttime.perf_counter() - t0)
                if dt < 0.0:
                    raise TimeoutError
            state.wait(timeout=dt)
        # print(f"MLVL async set_and_wait took {ttime.perf_counter()-t0:.3f} [s]")

    def change_set_wait_method(self, method_name: str):
        for mlv in self.get_enabled_mlvs():
            mlv.change_set_wait_method(method_name)


class MiddleLayerVariableListRO(MiddleLayerVariableListBase):

    def __init__(self, spec: MiddleLayerVariableListROSpec):
        super().__init__(spec)

        self.read_only = True

    def put(self, *args, **kwargs):
        raise ReadOnlyError

    def set(self, *args, **kwargs):
        raise ReadOnlyError

    def set_and_wait(self, *args, **kwargs):
        raise ReadOnlyError

    def change_set_wait_method(self, *args, **kwargs):
        raise ReadOnlyError


class AutoUpdateOption(Enum):
    NEVER = "Never"
    INITIAL = "Only initially"
    EVERY = "Every time"


class MiddleLayerVariableStatusListSpec(MiddleLayerVariableListSpec):
    enabled_value: int
    auto_update: AutoUpdateOption = AutoUpdateOption.INITIAL

    @field_serializer("auto_update")
    def serialize_auto_update(self, value: AutoUpdateOption):
        return value.value

    @field_validator("auto_update", mode="before")
    def deserialize_auto_update(cls, value):
        return AutoUpdateOption(value)


class MiddleLayerVariableStatusList(MiddleLayerVariableList):

    def __init__(self, spec: MiddleLayerVariableStatusListSpec):
        super().__init__(spec)

        self._enabled_value = spec.enabled_value
        self._auto_update = spec.auto_update
        self._n_updates = 0

        # TODO: self._n_updates need to be reset to zero, when it's re-loaded
        # via a cached file.

    def add_status_mlvl(self, status_mlvl: MiddleLayerVariableStatusList):
        raise RuntimeError("This method is not allowed to run in this class")

    def auto_update_enabled_status(self):
        match self._auto_update:
            case AutoUpdateOption.NEVER:
                return
            case AutoUpdateOption.INITIAL:
                if self._n_updates == 0:
                    self.update_enabled_status()
            case AutoUpdateOption.EVERY:
                self.update_enabled_status()
            case _:
                raise ValueError

    def update_enabled_status(self):

        status_vals = self.get(return_flat=True)

        enabled_status = status_vals == self._enabled_value

        self._n_updates += 1

        self.put_enabled_status(enabled_status)
