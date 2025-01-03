from __future__ import annotations

import asyncio
from collections import defaultdict
import threading
import time as ttime  # as defined in ophyd.device
from typing import List, Literal

from pydantic import BaseModel, Field

from ..unit import Q_, Unit
from ..utils import MACHINE_DEFAULT, KeyValueTagList, KeyValueTagSearch, SPositionList


class DatabaseDict(dict):
    def __init__(self):
        super().__init__()
        self["vars"] = {}
        self["lists"] = {}
        self["trees"] = {}
        self["vars.value_tags"] = defaultdict(list)
        self["vars.key_value_tags"] = defaultdict(lambda: defaultdict(list))
        self["lists.value_tags"] = defaultdict(list)
        self["lists.key_value_tags"] = defaultdict(lambda: defaultdict(list))
        self["trees.value_tags"] = defaultdict(list)
        self["trees.key_value_tags"] = defaultdict(lambda: defaultdict(list))


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
        value_tags = _DB[machine_name]["vars.value_tags"]
        key_value_tags = _DB[machine_name]["vars.key_value_tags"]
    elif isinstance(
        mlo,
        (
            MiddleLayerVariableList,
            MiddleLayerVariableListRO,
            MiddleLayerVariableStatusList,
        ),
    ):
        d = _DB[machine_name]["lists"]
        value_tags = _DB[machine_name]["lists.value_tags"]
        key_value_tags = _DB[machine_name]["lists.key_value_tags"]
    elif isinstance(mlo, MiddleLayerVariableTree):
        d = _DB[machine_name]["trees"]
        value_tags = _DB[machine_name]["trees.value_tags"]
        key_value_tags = _DB[machine_name]["trees.key_value_tags"]
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

        for tag_key, tag_values in mlo._spec.tags.model_dump().items():
            for v in tag_values:
                value_tags[v].append(name)
                key_value_tags[tag_key][v].append(name)


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


def get_all_mlv_value_tags(machine_name: str):
    return list(_DB[machine_name]["vars.value_tags"])


def get_all_mlv_key_value_tags(machine_name: str):
    result = {}
    for k, v in _DB[machine_name]["vars.key_value_tags"].items():
        result[k] = list(v)
    return result


def get_mlvs_via_value_tag(machine_name: str, value_tag: int | str):
    value_tags_d = _DB[machine_name]["vars.value_tags"]
    assert value_tag in value_tags_d
    return {
        mlv_name: _DB[machine_name]["vars"][mlv_name]
        for mlv_name in value_tags_d[value_tag]
    }


def get_mlvs_via_key_value_tags(
    machine_name: str, tag_searches: List[KeyValueTagSearch]
):
    d = _DB[machine_name]["vars.key_value_tags"]

    cum_sel = None
    for s in tag_searches:
        if s.key in d:
            if s.value in d[s.key]:
                this_sel = set(d[s.key][s.value])
            else:
                this_sel = set()
        else:
            this_sel = set()

        if cum_sel is None:
            cum_sel = this_sel
        else:
            cum_sel = cum_sel.intersection(this_sel)

        if len(cum_sel) == 0:
            break

    return {mlv_name: _DB[machine_name]["vars"][mlv_name] for mlv_name in cum_sel}


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
    s_list: SPositionList | None = None
    tags: KeyValueTagList = Field(default_factory=KeyValueTagList)


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

    def get_spos(self, loc: Literal["b", "e", "m"] = "m"):
        s_list = self._spec.s_list
        if s_list.b is None or s_list.e is None:
            spos = float("nan")
        else:
            if len(s_list.b) == 1 and len(s_list.e) == 1:
                match loc:
                    case "m":  # middle
                        spos = (s_list.b[0] + s_list.e[0]) / 2.0
                    case "b":  # beginning
                        spos = s_list.b[0] * Unit("m")
                    case "e":  # end
                        spos = s_list.e[0] * Unit("m")
            else:
                raise NotImplementedError("Multiple s-pos case not handled yet")

        return spos * Unit("m")

    def get_phys_length(self):
        s_list = self._spec.s_list
        if s_list.b is None or s_list.e is None:
            L = float("nan")
        else:
            if len(s_list.b) == 1 and len(s_list.e) == 1:
                L = s_list.e[0] - s_list.b[0]
            else:
                raise NotImplementedError("Multiple s-pos case not handled yet")

        return L * Unit("m")


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
