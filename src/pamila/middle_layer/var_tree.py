from __future__ import annotations

import asyncio
from copy import deepcopy
from functools import partial
import itertools
import time as ttime  # as defined in ophyd.device
from typing import Dict, List, Tuple

from pydantic import field_serializer

from . import (
    MiddleLayerObject,
    MiddleLayerObjectSpec,
    _register_mlo,
    _wait_for_connection,
)
from ..machine_modes import get_machine_mode
from ..unit import Q_
from ..utils import AttributeAccess as AA
from ..utils import ChainedPropertyFetcher, ChainedPropertyPusher
from ..utils import KeyIndexAccess as KIA
from ..utils import StatisticsType, convert_stats_type_to_func_dict
from .var_list import MiddleLayerVariableList, MiddleLayerVariableListRO


async def _async_mlvl_get(mlvl: MiddleLayerVariableList | MiddleLayerVariableListRO):
    loop = asyncio.get_running_loop()
    func = partial(mlvl.get, return_flat=True)
    value = await loop.run_in_executor(None, func)
    return value


async def mlvl_parallel_get(
    mlvls: List[MiddleLayerVariableList | MiddleLayerVariableListRO],
):
    tasks = [_async_mlvl_get(mlvl) for mlvl in mlvls]
    results = await asyncio.gather(*tasks)
    return results


async def _async_mlvl_read(mlvl: MiddleLayerVariableList | MiddleLayerVariableListRO):
    loop = asyncio.get_running_loop()
    d = await loop.run_in_executor(None, mlvl.read)
    return d


async def mlvl_parallel_read(
    mlvls: List[MiddleLayerVariableList | MiddleLayerVariableListRO],
):
    tasks = [_async_mlvl_read(mlvl) for mlvl in mlvls]
    results = await asyncio.gather(*tasks)
    d = {}
    for r in results:
        d.update(r)
    return d


async def _async_mlvl_put(
    mlvl: MiddleLayerVariableList, values_w_unit, *args, **kwargs
):
    loop = asyncio.get_running_loop()
    func = partial(mlvl.put, values_w_unit, *args, **kwargs)
    await loop.run_in_executor(None, func)
    return


async def mlvl_parallel_put(
    mlvls: List[MiddleLayerVariableList], list_of_values_w_unit: List, *args, **kwargs
):
    tasks = [
        _async_mlvl_put(mlvl, vals_w_unit, *args, **kwargs)
        for mlvl, vals_w_unit in zip(mlvls, list_of_values_w_unit)
    ]
    await asyncio.gather(*tasks)
    return


async def _async_mlvl_set(
    mlvl: MiddleLayerVariableList, values_w_unit, *args, **kwargs
):
    loop = asyncio.get_running_loop()
    func = partial(mlvl.set, values_w_unit, *args, **kwargs)
    status = await loop.run_in_executor(None, func)
    return status


async def mlvl_parallel_set(
    mlvls: List[MiddleLayerVariableList], list_of_values_w_unit: List, *args, **kwargs
):
    tasks = [
        _async_mlvl_set(mlvl, vals_w_unit, *args, **kwargs)
        for mlvl, vals_w_unit in zip(mlvls, list_of_values_w_unit)
    ]
    set_states = await asyncio.gather(*tasks)
    return set_states


class MiddleLayerVariableTreeSpec(MiddleLayerObjectSpec):
    mlos: Dict[
        str,
        MiddleLayerVariableList | MiddleLayerVariableListRO | MiddleLayerVariableTree,
    ]

    model_config = {"arbitrary_types_allowed": True, "extra": "forbid"}

    @field_serializer("mlos")
    def serialize_mlos(self, value):
        d = {}
        suffix_slice = slice(len("MiddleLayerVariable"), None)
        for node_name, mlo in value.items():
            spec = mlo.get_reconstruction_spec()
            d[node_name] = {
                "class_suffix": spec["class"][suffix_slice],
                "name": mlo.name,
                "machine_name": mlo.machine_name,
            }
        return d


class MiddleLayerVariableTree(MiddleLayerObject):
    def __init__(self, spec: MiddleLayerVariableTreeSpec):
        super().__init__(spec)

        self._all_mlvs = []
        self._status_list = []
        self._all_mlvls = []
        self._output_dict_template = {}
        self._mlvls_to_output_map = []
        self._input_to_mlvls_map = {}
        self._mlo_attrs = []
        machine_names = []
        for k, mlo in spec.mlos.items():
            assert isinstance(
                mlo,
                (
                    MiddleLayerVariableList,
                    MiddleLayerVariableListRO,
                    MiddleLayerVariableTree,
                ),
            )

            self._all_mlvs.extend(mlo._all_mlvs)
            self._status_list.extend(mlo._status_list)

            if isinstance(mlo, MiddleLayerVariableTree):
                mlvls = mlo.get_mlvls()
                self._all_mlvls.extend(mlvls)
                self._output_dict_template[k] = mlo._get_output_dict_template()
                assert len(mlo._mlvls_to_output_map) == len(mlvls)
                for sub_access_list, mlvl in zip(mlo._mlvls_to_output_map, mlvls):
                    full_access_list = [KIA(k)] + sub_access_list
                    self._mlvls_to_output_map.append(full_access_list)
                    self._input_to_mlvls_map[tuple(full_access_list)] = mlvl
            else:
                self._all_mlvls.append(mlo)
                self._output_dict_template[k] = None

                access_list = [KIA(k)]
                self._mlvls_to_output_map.append(access_list)
                self._input_to_mlvls_map[tuple(access_list)] = mlo

            setattr(self, k, mlo)

            machine_names.append(mlo.machine_name)

            self._mlo_attrs.append(k)

        self._attr_access_list = [
            [AA(kia.name) for kia in KIA_list] for KIA_list in self._mlvls_to_output_map
        ]

        self._all_mlvl_names = [mlvl.name for mlvl in self._all_mlvls]

        machine_names = list(set(machine_names))
        match len(machine_names):
            case 1:
                self.machine_name = machine_names[0]
            case 0:
                raise RuntimeError("Zero machine specified")
            case _:
                self.machine_name = "_multi_machine"
        _register_mlo(self, spec.exist_ok)

        self._mlvs = []
        self._mlv_names = []
        self._sigs_pend_funcs = {}
        self._reinitialize_on_enabled_status_change()

        self._non_serializable_attrs = ["_sigs_pend_funcs"]

    def __repr__(self):
        return f"MLVTree: {self.name}"

    def __str__(self):
        return f"MLVTree: {self.name}"

    def __getstate__(self):

        state = self.__dict__.copy()

        # Exclude the non-serializable attributes
        for attr in self._non_serializable_attrs:
            del state[attr]

        return state

    def __setstate__(self, state):
        self.__dict__.update(state)

        self._sigs_pend_funcs = {}

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

    def _reinitialize_on_enabled_status_change(self):

        self._mlvs.clear()
        self._mlv_names.clear()
        self._sigs_pend_funcs.clear()

        for mlvl in self._all_mlvls:
            self._mlvs.extend(mlvl.get_enabled_mlvs())

        self._mlv_names.extend([v.name for v in self._mlvs])

    def get_enabled_mlvs(self, refresh: bool = False):

        if refresh:
            self._reinitialize_on_enabled_status_change()

        return self._mlvs

    def get_mlvls(self):
        return self._all_mlvls

    def get_mlvl_names(self):
        return self._all_mlvl_names

    def _get_output_dict_template(self):
        return deepcopy(self._output_dict_template)

    def get(self):

        # t0 = ttime.perf_counter()

        if False:  # TO-FIX: seg fault
            results = asyncio.run(mlvl_parallel_get(self.get_mlvls()))
        else:
            results = [mlvl.get(return_flat=True) for mlvl in self.get_mlvls()]

        # print(f"MLVT async get took {ttime.perf_counter()-t0:.3f} [s]")

        output_d = self._get_output_dict_template()

        assert len(results) == len(self._mlvls_to_output_map)
        for r, access_list in zip(results, self._mlvls_to_output_map):
            ChainedPropertyPusher(output_d, access_list).put(r)

        return output_d

    def compute_stats(
        self,
        get_results: List,
        stats_types: (
            List[str | StatisticsType] | Tuple[str | StatisticsType, ...] | None
        ) = ("mean", "std", "min", "max"),
    ):

        stats_funcs = {}
        for v in stats_types:
            stats_funcs.update(convert_stats_type_to_func_dict(v))

        output_d = self._get_output_dict_template()

        for kia in self._mlvls_to_output_map:
            storage = []
            units = None
            for r in get_results:
                v = ChainedPropertyFetcher(r, kia).get()
                if units is None:
                    units = v.units
                storage.append(v.m)

            stats = {"raw": Q_(storage) * units}
            for _type, _func in stats_funcs.items():
                stats[_type] = _func(storage, axis=0) * units

            ChainedPropertyPusher(output_d, kia).put(stats)

        return output_d

    def read(self):
        # t0 = ttime.perf_counter()

        if False:  # TO-FIX
            results = asyncio.run(mlvl_parallel_read(self._all_mlvls))
        else:
            results = [mlvl.read() for mlvl in self._all_mlvls]

        # print(f"MLVT async read took {ttime.perf_counter()-t0:.3f} [s]")

        return results

    def _get_access_list_to_vals_map(self, val_dict_w_unit):
        m = {}
        for k, v in val_dict_w_unit.items():
            if isinstance(v, dict):
                for KIA_tup, vals in self._get_access_list_to_vals_map(v).items():
                    full_KIAs = [KIA(k)] + list(KIA_tup)
                    m[tuple(full_KIAs)] = vals
            else:
                m[tuple([KIA(k)])] = v

        return m

    def _prepare_put_input(self, val_dict_w_unit: Dict):

        access_list_to_vals = self._get_access_list_to_vals_map(val_dict_w_unit)
        mlvls = []
        list_of_vals_w_unit = []
        for access_list_key, vals_w_unit in access_list_to_vals.items():
            mlvls.append(self._input_to_mlvls_map[access_list_key])
            list_of_vals_w_unit.append(vals_w_unit)

        return mlvls, list_of_vals_w_unit

    def put(self, val_dict_w_unit: Dict, *args, **kwargs):

        # t0 = ttime.perf_counter()

        mlvls, list_of_vals_w_unit = self._prepare_put_input(val_dict_w_unit)

        if False:  # TO-FIX
            asyncio.run(mlvl_parallel_put(mlvls, list_of_vals_w_unit, *args, **kwargs))
        else:
            for mlvl, vals_w_unit in zip(mlvls, list_of_vals_w_unit):
                mlvl.put(vals_w_unit, *args, **kwargs)

        # print(f"MLVT async put took {ttime.perf_counter()-t0:.3f} [s]")

    def set(self, val_dict_w_unit: Dict, *args, **kwargs):

        # t0 = ttime.perf_counter()

        mlvls, list_of_vals_w_unit = self._prepare_put_input(val_dict_w_unit)

        if False:  # TO-FIX
            list_of_set_states = asyncio.run(
                mlvl_parallel_set(mlvls, list_of_vals_w_unit, *args, **kwargs)
            )
        else:
            list_of_set_states = []
            for mlvl, vals_w_unit in zip(mlvls, list_of_vals_w_unit):
                state = mlvl.set(vals_w_unit, *args, **kwargs)
                list_of_set_states.append(state)

        # print(f"MLVT async set took {ttime.perf_counter()-t0:.3f} [s]")

        return list_of_set_states

    def set_and_wait(self, val_dict_w_unit, *args, timeout: Q_ | None = None, **kwargs):

        t0 = ttime.perf_counter()
        list_of_set_states = self.set(val_dict_w_unit, *args, **kwargs)
        flat_set_states = list(itertools.chain(*list_of_set_states))
        dt = None
        for state in flat_set_states:
            if timeout is not None:
                dt = timeout.to("s").m - (ttime.perf_counter() - t0)
                if dt < 0.0:
                    raise TimeoutError
            state.wait(timeout=dt)
        # print(f"MLVT async set_and_wait took {ttime.perf_counter()-t0:.3f} [s]")
