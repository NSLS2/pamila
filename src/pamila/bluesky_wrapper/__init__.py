from typing import List, Tuple

from ophyd import Device, Signal

from . import ophyd_layer
from ..device.base import PamilaDeviceBase
from ..middle_layer.var_list import MiddleLayerVariableListBase
from ..middle_layer.var_tree import MiddleLayerVariableTree
from ..middle_layer.variable import MiddleLayerVariableBase
from ..utils import StatisticsType
from .set_utils import JumpSet, RampSet


def _get_pamila_ophyd_obj_map(
    obj_list_to_get: List | None, obj_list_to_put: List | None
):

    odevs = dict(get=[], put=[])

    if obj_list_to_get is None:
        obj_list_to_get = []

    if obj_list_to_put is None:
        obj_list_to_put = []

    p_to_o = dict(get=[], put=[])
    for k, obj_list in [("get", obj_list_to_get), ("put", obj_list_to_put)]:
        index = 0
        for obj in obj_list:
            if isinstance(obj, PamilaDeviceBase | MiddleLayerVariableBase):
                odevs[k].append(obj.get_ophyd_device())
                n = 1
            elif isinstance(obj, MiddleLayerVariableListBase):
                _devs = [mlv.get_ophyd_device() for mlv in obj.get_enabled_mlvs()]
                n = len(_devs)
                odevs[k].extend(_devs)
            elif isinstance(obj, MiddleLayerVariableTree):
                _map_d = {}
                for mlvl, mlvl_name in zip(obj.get_mlvls(), obj.get_mlvl_names()):
                    _devs = [mlv.get_ophyd_device() for mlv in mlvl.get_enabled_mlvs()]
                    n = len(_devs)
                    odevs[k].extend(_devs)
                    _map_d[mlvl_name] = slice(index, index + n)
                    index += n
                p_to_o[k].append(_map_d)
            elif isinstance(obj, Device | Signal):
                odevs[k].append(obj)
                n = 1
            else:
                raise TypeError

            if not isinstance(obj, MiddleLayerVariableTree):
                p_to_o[k].append(slice(index, index + n))
                index += n

    return dict(
        sigs_devs_to_get=odevs["get"], sigs_devs_to_put=odevs["put"], p_to_o=p_to_o
    )


def abs_put_then_get(
    obj_list_to_get: List | None = None,
    obj_list_to_put: List | None = None,
    vals_to_put=None,
    set_mode: JumpSet | RampSet | None = None,
    extra_settle_time: float = 0.0,
    n_repeat: int = 1,
    wait_time_btw_read: float = 0.0,
    ret_raw: bool = True,
    stats_types: (
        List[str | StatisticsType] | Tuple[str | StatisticsType, ...] | None
    ) = ("mean", "std", "min", "max"),
    subs=None,
    **metadata_kw,
):
    m = _get_pamila_ophyd_obj_map(obj_list_to_get, obj_list_to_put)

    return ophyd_layer.abs_put_then_get(
        sigs_devs_to_get=m["sigs_devs_to_get"],
        sigs_devs_to_put=m["sigs_devs_to_put"],
        vals_to_put=vals_to_put,
        set_mode=set_mode,
        extra_settle_time=extra_settle_time,
        n_repeat=n_repeat,
        wait_time_btw_read=wait_time_btw_read,
        ret_raw=ret_raw,
        stats_types=stats_types,
        subs=subs,
        **metadata_kw,
    )


def rel_put_then_get(
    obj_list_to_get=None,
    obj_list_to_put=None,
    vals_to_put=None,
    set_mode: JumpSet | RampSet | None = None,
    extra_settle_time: float = 0.0,
    n_repeat: int = 1,
    wait_time_btw_read: float = 0.0,
    ret_raw: bool = True,
    stats_types: (
        List[str | StatisticsType] | Tuple[str | StatisticsType, ...] | None
    ) = ("mean", "std", "min", "max"),
    subs=None,
    **metadata_kw,
):
    m = _get_pamila_ophyd_obj_map(obj_list_to_get, obj_list_to_put)

    return ophyd_layer.rel_put_then_get(
        sigs_devs_to_get=m["sigs_devs_to_get"],
        sigs_devs_to_put=m["sigs_devs_to_put"],
        vals_to_put=vals_to_put,
        set_mode=set_mode,
        extra_settle_time=extra_settle_time,
        n_repeat=n_repeat,
        wait_time_btw_read=wait_time_btw_read,
        ret_raw=ret_raw,
        stats_types=stats_types,
        subs=subs,
        **metadata_kw,
    )


def get(
    obj_list_to_get,
    n_repeat: int = 1,
    wait_time_btw_read: float = 0.0,
    ret_raw: bool = True,
    stats_types: (
        List[str | StatisticsType] | Tuple[str | StatisticsType, ...] | None
    ) = ("mean", "std", "min", "max"),
    subs=None,
    **metadata_kw,
):
    m = _get_pamila_ophyd_obj_map(obj_list_to_get, None)

    return ophyd_layer.get(
        m["sigs_devs_to_get"],
        n_repeat=n_repeat,
        wait_time_btw_read=wait_time_btw_read,
        ret_raw=ret_raw,
        stats_types=stats_types,
        subs=subs,
        **metadata_kw,
    )


def abs_put(
    obj_list_to_put,
    vals,
    set_mode: JumpSet | RampSet | None = None,
    extra_settle_time: float = 0.0,
    subs=None,
    **metadata_kw,
):
    m = _get_pamila_ophyd_obj_map(None, obj_list_to_put)

    return ophyd_layer.abs_put(
        m["sigs_devs_to_put"],
        vals,
        set_mode=set_mode,
        extra_settle_time=extra_settle_time,
        subs=subs,
        **metadata_kw,
    )


def rel_put(
    obj_list_to_put,
    vals,
    set_mode: JumpSet | RampSet | None = None,
    extra_settle_time: float = 0.0,
    subs=None,
    **metadata_kw,
):
    m = _get_pamila_ophyd_obj_map(None, obj_list_to_put)

    rel_put(
        m["sigs_devs_to_put"],
        vals,
        set_mode=set_mode,
        extra_settle_time=extra_settle_time,
        subs=subs,
        **metadata_kw,
    )
