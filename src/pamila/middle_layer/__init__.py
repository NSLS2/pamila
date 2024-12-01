from __future__ import annotations

import asyncio
from collections import defaultdict
import threading
import time as ttime  # as defined in ophyd.device

from pydantic import BaseModel

from ..unit import Q_
from ..utils import MACHINE_DEFAULT


class DatabaseDict(dict):
    def __init__(self):
        super().__init__()
        self["vars"] = {}
        self["lists"] = {}
        self["trees"] = {}


_DB = defaultdict(DatabaseDict)
_DB["_multi_machine"] = DatabaseDict()


def _register_mlo(
    mlo: (
        MiddleLayerVariable
        | MiddleLayerVariableRO
        | MiddleLayerVariableList
        | MiddleLayerVariableListRO
        | MiddleLayerVariableStatusList
        | MiddleLayerVariableTree
    ),
    exist_ok: bool,
):
    """mlo := Middle Layer Object"""

    machine_name = mlo.machine_name

    if isinstance(mlo, (MiddleLayerVariable, MiddleLayerVariableRO)):
        d = _DB[machine_name]["vars"]
    elif isinstance(
        mlo,
        (
            MiddleLayerVariableList,
            MiddleLayerVariableListRO,
            MiddleLayerVariableStatusList,
        ),
    ):
        d = _DB[machine_name]["lists"]
    elif isinstance(mlo, MiddleLayerVariableTree):
        d = _DB[machine_name]["trees"]
    else:
        raise TypeError

    if mlo.alias:
        name_list = [mlo.name, mlo.alias]
    else:
        name_list = [mlo.name]

    for name in name_list:
        if exist_ok:
            d[name] = mlo
        else:
            if name not in d:
                d[name] = mlo
            else:
                raise NameError(
                    f"{mlo.__class__.__name__} name `{name}` is already defined"
                )


def get_all_mlvs(machine_name: str):
    return _DB[machine_name]["vars"]


def get_all_mlvls(machine_name: str):
    return _DB[machine_name]["lists"]


def get_all_mlvts(machine_name: str):
    return _DB[machine_name]["trees"]


def get_all_multi_machine_mlvls():
    return _DB["_multi_machine"]["lists"]


def get_all_multi_machine_mlvts():
    return _DB["_multi_machine"]["trees"]


def _threaded_asyncio_runner(coroutine):

    new_loop = asyncio.new_event_loop()

    # Start the event loop in a separate thread
    def run_loop():
        asyncio.set_event_loop(new_loop)
        new_loop.run_forever()

    thread = threading.Thread(target=run_loop, daemon=True)
    thread.start()

    future = asyncio.run_coroutine_threadsafe(coroutine, new_loop)
    results = future.result()

    # Stop the loop and wait for the thread to finish
    new_loop.call_soon_threadsafe(new_loop.stop)
    thread.join()

    return results


def _wait_for_connection(
    mlo_names, signals, pending_funcs, timeout: Q_ | None = Q_("2 s")
):
    """Wait for signals to connect

    Parameters
    ----------
    all_signals : bool, optional
        Wait for all signals to connect (including lazy ones)
    timeout : float or None
        Overall timeout
    """

    if timeout is not None:
        timeout = timeout.to("s").m

    t0 = ttime.perf_counter()
    while timeout is None or (ttime.perf_counter() - t0) < timeout:
        connected = all(sig.connected for sig in signals)
        if connected and not any(pending_funcs.values()):
            return
        ttime.sleep(min((0.05, timeout / 10.0)))

    def get_name(mlo_name, sig):
        sig_name = f"{mlo_name}.{sig.dotted_name}"
        return f"{sig_name} ({sig.pvname})" if hasattr(sig, "pvname") else sig_name

    reasons = []
    unconnected = ", ".join(
        get_name(mlo_name, sig)
        for sig, mlo_name in zip(signals, mlo_names)
        if not sig.connected
    )
    if unconnected:
        reasons.append(f"Failed to connect to all signals: {unconnected}")
    if any(pending_funcs.values()):
        pending = ", ".join(
            description.format(device=dev)
            for dev, funcs in pending_funcs.items()
            for obj, description in funcs.items()
        )
        reasons.append(f"Pending operations: {pending}")
    raise TimeoutError("; ".join(reasons))


class MiddleLayerObjectSpec(BaseModel):
    name: str
    alias: str = ""
    description: str = ""
    exist_ok: bool = False


class MiddleLayerObject:
    def __init__(self, spec: MiddleLayerObjectSpec):
        assert isinstance(spec, MiddleLayerObjectSpec)

        self._spec = spec

        self.name = spec.name
        self.alias = spec.alias
        self.description = spec.description

    def get_spec(self):
        return self._spec

    def get_reconstruction_spec(self, exclude_unset: bool = True):
        model_d = {"class": self.__class__.__name__}
        model_d.update(self._spec.model_dump(exclude_unset=exclude_unset))
        return model_d


class MloName(BaseModel):
    name: str

    def __init__(self, name: str):
        super().__init__(name=name)

    def get_mlo(self):
        raise NotImplementedError

    def json_serialize(self):
        raise NotImplementedError


class MlvName(MloName):
    def get_mlo(self, machine_name: str):
        return get_all_mlvs(machine_name)[self.name]

    def json_serialize(self):
        return {"__mlv_name__": True, "name": self.name}


class MlvlName(MloName):
    def get_mlo(self, machine_name: str):
        return get_all_mlvls(machine_name)[self.name]

    def json_serialize(self):
        return {"__mlvl_name__": True, "name": self.name}


class MlvtName(MloName):
    def get_mlo(self, machine_name: str):
        return get_all_mlvts(machine_name)[self.name]

    def json_serialize(self):
        return {"__mlvt_name__": True, "name": self.name}


def json_deserialize_mlo_name(value):
    if isinstance(value, dict):
        if value.get("__mlvt_name__", False):
            return MlvtName(value["name"])
        elif value.get("__mlvl_name__", False):
            return MlvlName(value["name"])
        elif value.get("__mlv_name__", False):
            return MlvName(value["name"])
        else:
            raise TypeError
    elif isinstance(value, MloName):
        return value
    elif isinstance(value, str):
        if value == MACHINE_DEFAULT.value:
            return MACHINE_DEFAULT
        else:
            return value
    else:
        raise TypeError


def nested_deserialize_mlo_names(value):
    if isinstance(value, dict):
        try:
            return json_deserialize_mlo_name(value)
        except TypeError:
            for k, v in value.items():
                try:
                    mlo_name = json_deserialize_mlo_name(v)
                    value[k] = mlo_name
                except TypeError:
                    if isinstance(v, dict):
                        value[k] = nested_deserialize_mlo_names(v)
                    else:
                        pass  # No change needed

    return value


from . import var_list, var_tree, variable
from .var_list import (
    AutoUpdateOption,
    MiddleLayerVariableList,
    MiddleLayerVariableListRO,
    MiddleLayerVariableListROSpec,
    MiddleLayerVariableListSpec,
    MiddleLayerVariableStatusList,
    MiddleLayerVariableStatusListSpec,
)
from .var_tree import MiddleLayerVariableTree, MiddleLayerVariableTreeSpec
from .variable import (
    MiddleLayerVariable,
    MiddleLayerVariableRO,
    MiddleLayerVariableSpec,
)
