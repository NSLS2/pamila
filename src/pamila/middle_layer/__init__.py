from __future__ import annotations

import asyncio
from collections import defaultdict
from fnmatch import fnmatch
from itertools import chain
import re
import threading
import time as ttime  # as defined in ophyd.device
from typing import Dict, List, Literal

import numpy as np
from pydantic import BaseModel, Field

from ..unit import Q_, fast_convert, fast_create_Q
from ..utils import MACHINE_DEFAULT, KeyValueTagList, KeyValueTagSearch, SPositionList


def default_dict_of_lists():
    return defaultdict(list)


class DatabaseDict(dict):
    def __init__(self):
        super().__init__()
        self["vars"] = {}
        self["lists"] = {}
        self["trees"] = {}
        self["vars.value_tags"] = defaultdict(list)
        self["vars.key_value_tags"] = defaultdict(default_dict_of_lists)
        self["lists.value_tags"] = defaultdict(list)
        self["lists.key_value_tags"] = defaultdict(default_dict_of_lists)
        self["trees.value_tags"] = defaultdict(list)
        self["trees.key_value_tags"] = defaultdict(default_dict_of_lists)
        self["elems"] = {}
        self["elems.value_tags"] = defaultdict(list)
        self["elems.key_value_tags"] = defaultdict(default_dict_of_lists)


_DB = defaultdict(DatabaseDict)
_DB["_multi_machine"] = DatabaseDict()


def _get_machine_db(machine_name: str):
    return _DB[machine_name]


def _set_machine_db(machine_name: str, db: DatabaseDict):
    _DB[machine_name] = db


def _register_element(
    elem: Element,
    exist_ok: bool,
):

    assert isinstance(elem, Element)

    machine_name = elem.machine_name

    d = _DB[machine_name]["elems"]
    value_tags = _DB[machine_name]["elems.value_tags"]
    key_value_tags = _DB[machine_name]["elems.key_value_tags"]

    name = elem.name

    if exist_ok:
        d[name] = elem
    else:
        if name not in d:
            d[name] = elem
        else:
            raise NameError(
                f"{elem.__class__.__name__} name `{name}` is already defined"
            )

    for tag_key, tag_values in elem.get_spec().tags.model_dump().items():
        for v in tag_values:
            value_tags[v].append(name)
            key_value_tags[tag_key][v].append(name)


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

        for tag_key, tag_values in mlo.get_spec().tags.model_dump().items():
            for v in tag_values:
                value_tags[v].append(name)
                key_value_tags[tag_key][v].append(name)


def get_all_elems(machine_name: str):
    return _DB[machine_name]["elems"]


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


def _get_objs_via_name(
    obj_type: Literal["vars", "lists", "trees", "elems"],
    machine_name: str,
    obj_name: str,
    search_type: Literal["exact", "fnmatch", "regex", "regex/i"] = "fnmatch",
):

    obj_d = _DB[machine_name][obj_type]

    obj_name_list = []

    match search_type:
        case "exact":
            if obj_name in obj_d:
                obj_name_list.append(obj_name)
        case "fnmatch":
            obj_name_list.extend([k for k in obj_d.keys() if fnmatch(k, obj_name)])
        case "regex":
            obj_name_list.extend([k for k in obj_d.keys() if re.search(obj_name, k)])
        case "regex/i":
            obj_name_list.extend(
                [k for k in obj_d.keys() if re.search(obj_name, k, re.IGNORECASE)]
            )
        case _:
            raise NotImplementedError

    return {obj_name: obj_d[obj_name] for obj_name in obj_name_list}


def _get_objs_via_value_tag(
    obj_type: Literal["vars", "lists", "trees", "elems"],
    machine_name: str,
    value_tag: str,
    search_type: Literal["exact", "fnmatch", "regex", "regex/i"] = "fnmatch",
):

    obj_d = _DB[machine_name][obj_type]
    value_tags_d = _DB[machine_name][f"{obj_type}.value_tags"]

    match search_type:
        case "exact":
            if value_tag not in value_tags_d:
                obj_name_list = []
            else:
                obj_name_list = value_tags_d[value_tag]
        case "fnmatch":
            obj_name_LoL = [
                obj_name_list
                for k, obj_name_list in value_tags_d.items()
                if fnmatch(k, value_tag)
            ]
            obj_name_list = list(chain.from_iterable(obj_name_LoL))
        case "regex":
            obj_name_LoL = [
                obj_name_list
                for k, obj_name_list in value_tags_d.items()
                if re.search(value_tag, k)
            ]
            obj_name_list = list(chain.from_iterable(obj_name_LoL))
        case "regex/i":
            obj_name_LoL = [
                obj_name_list
                for k, obj_name_list in value_tags_d.items()
                if re.search(value_tag, k, re.IGNORECASE)
            ]
            obj_name_list = list(chain.from_iterable(obj_name_LoL))
        case _:
            raise NotImplementedError

    return {obj_name: obj_d[obj_name] for obj_name in obj_name_list}


def _get_objs_via_key_value_tags(
    obj_type: Literal["vars", "lists", "trees", "elems"],
    machine_name: str,
    tag_searches: List[KeyValueTagSearch],
):
    obj_d = _DB[machine_name][obj_type]
    kv_tags_d = _DB[machine_name][f"{obj_type}.key_value_tags"]

    cum_sel = None
    for s in tag_searches:

        if s.key in kv_tags_d:

            avail_vals = kv_tags_d[s.key]

            match s.type:
                case "exact":
                    if s.value in avail_vals:
                        this_sel = set(kv_tags_d[s.key][s.value])
                    else:
                        this_sel = set()
                case "fnmatch":
                    cum_obj_name_list = []
                    for k, obj_name_list in avail_vals.items():
                        if fnmatch(k, s.value):
                            cum_obj_name_list.extend(obj_name_list)
                    this_sel = set(cum_obj_name_list)
                case "regex":
                    cum_obj_name_list = []
                    for k, obj_name_list in avail_vals.items():
                        if re.search(s.value, k):
                            cum_obj_name_list.extend(obj_name_list)
                    this_sel = set(cum_obj_name_list)
                case "regex/i":
                    cum_obj_name_list = []
                    for k, obj_name_list in avail_vals.items():
                        if re.search(s.value, k, re.IGNORECASE):
                            cum_obj_name_list.extend(obj_name_list)
                    this_sel = set(cum_obj_name_list)
                case _:
                    raise NotImplementedError
        else:
            this_sel = set()

        if cum_sel is None:
            cum_sel = this_sel
        else:
            cum_sel = cum_sel.intersection(this_sel)

        if len(cum_sel) == 0:
            break

    return {obj_name: obj_d[obj_name] for obj_name in cum_sel}


def get_mlvs_via_name(
    machine_name: str,
    mlv_name: str,
    search_type: Literal["exact", "fnmatch", "regex", "regex/i"] = "fnmatch",
):
    return _get_objs_via_name("vars", machine_name, mlv_name, search_type=search_type)


def get_mlvs_via_value_tag(
    machine_name: str,
    value_tag: str,
    search_type: Literal["exact", "fnmatch", "regex", "regex/i"] = "fnmatch",
):
    return _get_objs_via_value_tag(
        "vars", machine_name, value_tag, search_type=search_type
    )


def get_mlvs_via_key_value_tags(
    machine_name: str, tag_searches: List[KeyValueTagSearch]
):
    return _get_objs_via_key_value_tags("vars", machine_name, tag_searches)


def get_elems_via_name(
    machine_name: str,
    elem_name: str,
    search_type: Literal["exact", "fnmatch", "regex", "regex/i"] = "fnmatch",
):
    return _get_objs_via_name("elems", machine_name, elem_name, search_type=search_type)


def get_elems_via_value_tag(
    machine_name: str,
    value_tag: str,
    search_type: Literal["exact", "fnmatch", "regex", "regex/i"] = "fnmatch",
):
    return _get_objs_via_value_tag(
        "elems", machine_name, value_tag, search_type=search_type
    )


def get_elems_via_key_value_tags(
    machine_name: str, tag_searches: List[KeyValueTagSearch]
):
    return _get_objs_via_key_value_tags("elems", machine_name, tag_searches)


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
        timeout = fast_convert(timeout, "s").m

    if False:
        t0 = ttime.perf_counter()
        while timeout is None or (ttime.perf_counter() - t0) < timeout:
            connected = all(sig.connected for sig in signals)
            if connected and not any(pending_funcs.values()):
                return
            ttime.sleep(min((0.05, timeout / 10.0)))
    else:
        inds_to_keep = list(range(len(signals)))
        t0 = ttime.perf_counter()
        while timeout is None or (ttime.perf_counter() - t0) < timeout:
            new_inds_to_keep = [i for i in inds_to_keep if not signals[i].connected]
            if (new_inds_to_keep == []) and not any(pending_funcs.values()):
                return

            # For some reason, the PV access rights change callback does not
            # get called. So, here this callback is manually being invoked.
            # Otherwise, this signal never gets connected even if the associated
            # PV object is connected.
            for i in new_inds_to_keep:
                sig = signals[i]
                for attr_name in ["_read_pv", "_write_pv"]:
                    pv = getattr(sig, attr_name, None)
                    if pv and pv.connected:
                        if not all([*sig._received_first_metadata.values()]):
                            sig._pv_connected(pv.pvname, pv.connected, pv)
                            if not all([*sig._received_first_metadata.values()]):
                                _md = pv.get_all_metadata_blocking(timeout=5.0)  # 10)
                                sig._initial_metadata_callback(pv.pvname, _md)
                            assert all([*sig._received_first_metadata.values()])

                        orig_read_access = sig.read_access
                        orig_wirte_access = sig.write_access
                        sig._pv_access_callback(sig.read_access, sig.write_access, pv)
                        assert sig.read_access == orig_read_access
                        assert sig.write_access == orig_wirte_access
                        assert sig.connected

            inds_to_keep = new_inds_to_keep
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


def get_spos(s_list: SPositionList, loc: Literal["b", "e", "c"] = "c"):
    if (s_list is None) or (s_list.b is None) or (s_list.e is None):
        spos = float("nan")
    else:
        if len(s_list.b) == 1 and len(s_list.e) == 1:
            match loc:
                case "c":  # center
                    spos = (s_list.b[0] + s_list.e[0]) / 2.0
                case "b":  # beginning
                    spos = s_list.b[0]
                case "e":  # end
                    spos = s_list.e[0]
        else:
            raise NotImplementedError("Multiple s-pos case not handled yet")

    return fast_create_Q(spos, "meter")


def get_phys_length(s_list: SPositionList):
    if s_list.b is None or s_list.e is None:
        L = float("nan")
    else:
        if len(s_list.b) == 1 and len(s_list.e) == 1:
            L = s_list.e[0] - s_list.b[0]
        else:
            raise NotImplementedError("Multiple s-pos case not handled yet")

    return fast_create_Q(L, "meter")


def sort_by_spos(
    objs: List[MiddleLayerObject | Element] | Dict[str, MiddleLayerObject | Element],
    loc: Literal["b", "e", "c"] = "c",
    exclude_nan: bool = True,
):

    if isinstance(objs, list):
        spos_list = [fast_convert(o.get_spos(loc=loc), "meter").m for o in objs]
        if exclude_nan:
            sorted_objs = [
                objs[i] for i in np.argsort(spos_list) if not np.isnan(spos_list[i])
            ]
        else:
            sorted_objs = [objs[i] for i in np.argsort(spos_list)]
    elif isinstance(objs, dict):
        keys = list(objs)
        spos_list = np.array(
            [fast_convert(o.get_spos(loc=loc), "meter").m for o in objs.values()]
        )
        if exclude_nan:
            sorted_objs = [
                objs[keys[i]]
                for i in np.argsort(spos_list)
                if not np.isnan(spos_list[i])
            ]
        else:
            sorted_objs = [objs[keys[i]] for i in np.argsort(spos_list)]
    else:
        raise NotImplementedError

    return sorted_objs


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

    def get_spos(self, loc: Literal["b", "e", "c"] = "c"):
        s_list = self._spec.s_list
        return get_spos(s_list, loc=loc)

    def get_phys_length(self):
        s_list = self._spec.s_list
        return get_phys_length(s_list)


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
from .element import Element, ElementSpec, PvIdToReprMap
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
