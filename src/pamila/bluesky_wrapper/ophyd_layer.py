from functools import partial
from itertools import chain
import time
from typing import Dict, List, Tuple

import bluesky.plan_stubs as bps
from bluesky.plans import count, list_scan, rel_list_scan
from bluesky.utils import Msg
import numpy as np
from ophyd import Component, Device, Signal
import pandas as pd

from .. import USERNAME
from ..tiled import TiledWriter, pint_serializable_df
from ..utils import StatisticsType
from .run_engine import RE
from .set_utils import JumpSet, RampSet, ramp_set, wait_optional_move_per_step
from .timer import TimerDict

UTIL_DEVS = {}
BS_OUTPUT = {}
CACHED_SEP_DEVS = {}


class NonTrigSignal(Signal):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def triggerable(self):
        return False


class ScanUtilDevice(Device):
    index = Component(NonTrigSignal, value=0)
    read_names = Component(NonTrigSignal, value=[])
    read_names_need_update = Component(NonTrigSignal, value=True)


def _get_scan_util_device():
    if "scan_util" not in UTIL_DEVS:
        _name = "scan_util"
        UTIL_DEVS["scan_util"] = ScanUtilDevice(
            name=_name, prefix=f"{USERNAME}:{_name}"
        )

    return UTIL_DEVS["scan_util"]


def _validate_inputs(sigs_devs_to_get, sigs_devs_to_put, vals_to_put):

    if sigs_devs_to_get is None:
        sigs_devs_to_get = []

    if sigs_devs_to_put is None:
        sigs_devs_to_put = []

    if vals_to_put is None:
        vals_to_put = []

    odevs_to_get = []
    for obj in sigs_devs_to_get:
        match obj:
            case Device() | Signal():
                odevs_to_get.append(obj)
            case _:
                raise TypeError

    odevs_to_put = []
    for obj in sigs_devs_to_put:
        match obj:
            case Device() | Signal():
                odevs_to_put.append(obj)
            case _:
                raise TypeError

    assert len(odevs_to_put) == len(vals_to_put)

    return odevs_to_get, odevs_to_put, vals_to_put


def cached_separate_devices(devices):
    """Based on bluesky.utils.separate_devices(), but this is more efficient
    to avoid repeated checking."""

    from bluesky.utils import ancestry

    tup_devices = tuple(devices)
    if tup_devices in CACHED_SEP_DEVS:
        return CACHED_SEP_DEVS[tup_devices]

    result = []
    for det in devices:
        for existing_det in result[:]:
            if existing_det in ancestry(det):
                # known issue: here we assume that det is in the read_attrs
                # of existing_det -- to be addressed after plans.py refactor
                break
            elif det in ancestry(existing_det):
                # existing_det is redundant; use det in its place
                result.remove(existing_det)
        else:
            result.append(det)

    CACHED_SEP_DEVS[tup_devices] = result

    return result


def parallel_read(devices):

    return (yield Msg("parallel_read", devices))


def pamila_trigger_and_read(devices, name="primary"):

    null = bps.null
    if False:
        separate_devices = bps.separate_devices
    else:
        separate_devices = cached_separate_devices
    all_safe_rewind = bps.all_safe_rewind
    _short_uid = bps._short_uid
    Triggerable = bps.Triggerable
    trigger = bps.trigger
    wait = bps.wait
    create = bps.create
    read = bps.read
    save = bps.save
    drop = bps.drop

    from bluesky.preprocessors import contingency_wrapper

    timer_d = TimerDict()

    timer_d.start("pamila_trigger_and_read")

    # If devices is empty, don't emit 'create'/'save' messages.
    if not devices:
        yield from null()
    timer_d.start(timer_key := "separate_devices")
    devices = separate_devices(devices)  # remove redundant entries
    timer_d[timer_key].stop()
    timer_d.start(timer_key := "all_safe_rewind")
    rewindable = all_safe_rewind(devices)  # if devices can be re-triggered
    timer_d[timer_key].stop()

    def inner_trigger_and_read():
        grp = _short_uid("trigger")
        no_wait = True
        timer_d.start(timer_key := "trigger")
        for obj in devices:
            # if isinstance(obj, Triggerable):
            if obj.triggerable():
                no_wait = False
                yield from trigger(obj, group=grp)
        timer_d[timer_key].stop()

        # Skip 'wait' if none of the devices implemented a trigger method.
        if not no_wait:
            timer_d.start(timer_key := "trigger wait")
            yield from wait(group=grp)
            timer_d[timer_key].stop()

        timer_d.start(timer_key := "create")
        yield from create(name)
        timer_d[timer_key].stop()

        def read_plan():

            timer_d.start(timer_key := "parallel_read")
            reading_list = yield from parallel_read(tuple(devices))
            timer_d[timer_key].stop()

            ret = {}  # collect and return readings to give plan access to them
            for reading in reading_list:
                if reading is not None:
                    ret.update(reading)

            return ret

        def standard_path():
            timer_d.start(timer_key := "save_or_drop")
            if True:
                yield from save()
            else:
                yield from drop()
            timer_d[timer_key].stop()

        def exception_path(exp):
            yield from drop()
            raise exp

        ret = yield from contingency_wrapper(
            read_plan(), except_plan=exception_path, else_plan=standard_path
        )
        return ret

    from bluesky.preprocessors import rewindable_wrapper

    # return (yield from rewindable_wrapper(inner_trigger_and_read(), rewindable))

    output = yield from rewindable_wrapper(inner_trigger_and_read(), rewindable)

    timer_d["pamila_trigger_and_read"].stop()

    _print_timer_results = False
    if _print_timer_results:
        for v in timer_d.values():
            v.print()

    BS_OUTPUT["pamila_trigger_and_read"] = output

    return output


def per_shot_with_mult_reads_and_delay(
    detectors, n_repeat: int = 1, wait_time_btw_read: float = 0.0
):

    scan_util_dev = _get_scan_util_device()
    scan_util_dev.index.put(scan_util_dev.index.get() + 1)  # increment scan index
    read_names_need_update = scan_util_dev.read_names_need_update.get()

    # trigger_and_read = bps.trigger_and_read
    trigger_and_read = pamila_trigger_and_read

    trig_read = partial(trigger_and_read, [scan_util_dev.index] + detectors)
    BS_OUTPUT["per_shot_with_mult_reads_and_delay"] = []
    for _i in range(n_repeat):
        t_start = time.perf_counter()
        t0 = time.perf_counter()
        reading = yield from trig_read()
        BS_OUTPUT["per_shot_with_mult_reads_and_delay"].append(reading)
        print(f"Reading inside 'per_shot' took {time.perf_counter()-t0:.3g} [s]")
        if read_names_need_update:
            read_names = list(reading.keys())
            scan_util_dev.read_names.put(read_names)
            read_names_need_update = False
            scan_util_dev.read_names_need_update.put(read_names_need_update)
        if _i + 1 != n_repeat:
            dt = time.perf_counter() - t_start
            yield from bps.sleep(max([wait_time_btw_read - dt, 0.0]))


def per_step_nd_with_mult_reads_and_delay(
    detectors,
    step,
    pos_cache,
    set_mode: JumpSet | RampSet | None = None,
    extra_settle_time: float = 0.0,
    n_repeat: int = 1,
    wait_time_btw_read: float = 0.0,
    initial_positions: Dict | None = None,
):

    motors = list(step)

    if set_mode is None:
        set_mode = JumpSet()

    if set_mode.jump:  # jump to the target position
        yield from wait_optional_move_per_step(step, pos_cache, wait=True)
    else:  # ramp to the target position
        yield from ramp_set(step, pos_cache, set_mode, initial_positions, wait=True)

    yield from bps.sleep(extra_settle_time)

    # Fast enough for 0.2-sec wait
    scan_util_dev = _get_scan_util_device()
    scan_util_dev.index.put(scan_util_dev.index.get() + 1)  # increment scan index
    read_names_need_update = scan_util_dev.read_names_need_update.get()

    trig_read = partial(
        bps.trigger_and_read, [scan_util_dev.index] + detectors + motors
    )

    for i in range(n_repeat):
        t_start = time.perf_counter()

        reading = yield from trig_read()
        if read_names_need_update:
            read_names = list(reading.keys())
            scan_util_dev.read_names.put(read_names)
            read_names_need_update = False
            scan_util_dev.read_names_need_update.put(read_names_need_update)

        if i + 1 != n_repeat:
            dt = time.perf_counter() - t_start
            yield from bps.sleep(max([wait_time_btw_read - dt, 0.0]))


def _put_then_get(
    relative,
    sigs_devs_to_get=None,
    sigs_devs_to_put=None,
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
    initial_positions: Dict | None = None,
    **metadata_kw,
):

    output = {}

    sigs_devs_to_get, sigs_devs_to_put, vals_to_put = _validate_inputs(
        sigs_devs_to_get, sigs_devs_to_put, vals_to_put
    )

    for dev in sigs_devs_to_put:
        dev.position = dev.get()

    if stats_types is None:
        stats_types = ()

    if n_repeat == 1:  # No point to calculate stats if only one data point
        stats_types = ()

    scan_util_dev = _get_scan_util_device()
    scan_util_dev.index.put(0)  # Reset the scan index as statistics calc. indentifier
    scan_util_dev.read_names_need_update.put(True)
    scan_util_dev.read_names.put([])

    if len(sigs_devs_to_put) == 0:
        custom_per_shot = partial(
            per_shot_with_mult_reads_and_delay,
            n_repeat=n_repeat,
            wait_time_btw_read=wait_time_btw_read,
        )
        actual_plan = count(sigs_devs_to_get, per_shot=custom_per_shot)
    else:
        if relative:
            _scan_func = rel_list_scan
            assert initial_positions == {}

            if (set_mode is None) or isinstance(set_mode, JumpSet):
                pass
            else:
                # Since bluesky will automatically go back to the initial
                # settings after the scan in a single jump, we add the
                # initialization step to force ramping for the final
                # restoration step as well.
                if not all([vals[-1] == 0.0 for vals in vals_to_put]):
                    print("Adding the initial settings restoration step for ramping")
                    for vals in vals_to_put:
                        vals.append(0.0)
        else:
            _scan_func = list_scan
            assert initial_positions is None

            # Since bluesky will NOT automatically go back to the initial
            # settings after the scan for the "absolute" change functions,
            # we add the initialization step.
            cur_abs_vals = []
            for motor in sigs_devs_to_put:
                try:
                    cur_sig = motor.current_val_sginal
                except AttributeError:
                    cur_sig = motor
                cur_abs_vals.append(cur_sig.get())

            last_vals = [vals[-1] for vals in vals_to_put]
            if last_vals != cur_abs_vals:
                print("Adding the initial settings restoration step for ramping")
                for _i, vals in enumerate(vals_to_put):
                    vals.append(cur_abs_vals[_i])

        paired = zip(sigs_devs_to_put, vals_to_put)
        _list_scan_args = list(chain.from_iterable(paired))

        actual_plan = _scan_func(
            sigs_devs_to_get,
            *_list_scan_args,
            # per_step=None,
            per_step=partial(
                per_step_nd_with_mult_reads_and_delay,
                set_mode=set_mode,
                extra_settle_time=extra_settle_time,
                n_repeat=n_repeat,
                wait_time_btw_read=wait_time_btw_read,
                initial_positions=initial_positions,
            ),
        )

    tw = None
    if subs is None:
        flat_subs = []
    else:
        flat_subs = [_sub for sub_type, _sub_list in subs.items() for _sub in _sub_list]
    for _sub in flat_subs:
        if isinstance(_sub, TiledWriter):
            tw = _sub
            break

    uids = RE(actual_plan, subs, **metadata_kw)

    if tw is None:
        col_names = None
        rows = []
        for table in BS_OUTPUT["per_shot_with_mult_reads_and_delay"]:
            df = pd.DataFrame.from_dict(table)
            values = df.loc["value"]
            timestamps = df.loc["timestamp"]
            rows.append(np.append(values.values, timestamps.values))
            if col_names is None:
                col_names = df.columns.to_list()
                col_names = col_names + [f"ts_{_name}" for _name in col_names]
        df = pd.DataFrame(rows, columns=col_names)
        _df_d = pint_serializable_df(df)
        df = _df_d["df_wo_unit"]
        output["units"] = _df_d["units"]
    else:
        output["uids"] = uids

        assert len(uids) == 1
        uid = uids[0]

        client = tw.client
        node = client[uid]

        output["metadata"] = node.metadata_copy()

        primary = node["primary"]
        events = primary["internal"]["events"]

        if False:
            import pickle

            with open("temp.pkl", "wb") as f:
                pickle.dump(output, f)
            with open("temp.pkl", "rb") as f:
                test = pickle.load(f)

        df = events.read()
        # df_sel = events.read(['bpm_1_x_RB', 'cor_1_x_SP'])

        configs = {}
        for k, v in primary["config"].items():
            configs[k] = v.read()

        output["units"] = {}
        for k, v in events.metadata.items():
            if "converted_units" in v:
                output["units"][k] = v["converted_units"]
            elif "units" in v:
                output["units"][k] = v["units"]

    if ret_raw:
        output["raw_data"] = df

    if len(stats_types) != 0:
        read_names = [
            _name
            for _name in scan_util_dev.read_names.get()
            if _name != scan_util_dev.index.name
        ]

        filtered_df = df.groupby(scan_util_dev.index.name)[read_names]

        stats = {}
        for _stats_type in stats_types:
            if True:
                if isinstance(_stats_type, StatisticsType):
                    _stats_type = _stats_type.value
                else:
                    assert isinstance(_stats_type, str)

                if _stats_type in ("avg", "average"):
                    _stats_type = "mean"

                if _stats_type != "iqr":
                    stats[_stats_type] = getattr(filtered_df, _stats_type)()
                else:
                    q1 = getattr(filtered_df, "quantile")(0.25)
                    q3 = getattr(filtered_df, "quantile")(0.75)
                    stats[_stats_type] = q3 - q1
            else:
                wo_unit = getattr(
                    filtered_df.apply(lambda _df: _df.map(lambda x: x.magnitude)),
                    _stats_type,
                )()
                units = df[read_names].iloc[0].apply(lambda x: x.units)
                stats[_stats_type] = wo_unit * units

        output["stats"] = stats

    return output


def abs_put_then_get(
    sigs_devs_to_get=None,
    sigs_devs_to_put=None,
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

    relative = False

    return _put_then_get(
        relative,
        sigs_devs_to_get=sigs_devs_to_get,
        sigs_devs_to_put=sigs_devs_to_put,
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
    sigs_devs_to_get=None,
    sigs_devs_to_put=None,
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

    relative = True

    initial_positions = {}  # Only relevant when using RampSet

    return _put_then_get(
        relative,
        sigs_devs_to_get=sigs_devs_to_get,
        sigs_devs_to_put=sigs_devs_to_put,
        vals_to_put=vals_to_put,
        set_mode=set_mode,
        extra_settle_time=extra_settle_time,
        n_repeat=n_repeat,
        wait_time_btw_read=wait_time_btw_read,
        ret_raw=ret_raw,
        stats_types=stats_types,
        subs=subs,
        initial_positions=initial_positions,
        **metadata_kw,
    )


def get(
    sigs_devs,
    n_repeat: int = 1,
    wait_time_btw_read: float = 0.0,
    ret_raw: bool = True,
    stats_types: (
        List[str | StatisticsType] | Tuple[str | StatisticsType, ...] | None
    ) = ("mean", "std", "min", "max"),
    subs=None,
    **metadata_kw,
):

    relative = False  # This value doesn't matter

    return _put_then_get(
        relative,
        sigs_devs_to_get=sigs_devs,
        n_repeat=n_repeat,
        wait_time_btw_read=wait_time_btw_read,
        ret_raw=ret_raw,
        stats_types=stats_types,
        subs=subs,
        **metadata_kw,
    )


def _put(
    relative,
    sigs,
    vals,
    set_mode: JumpSet | RampSet | None = None,
    extra_settle_time: float = 0.0,
    subs=None,
    **metadata_kw,
):

    if relative:
        func = rel_put_then_get
    else:
        func = abs_put_then_get

    output = func(
        sigs_devs_to_get=[],
        sigs_devs_to_put=sigs,
        vals_to_put=vals,
        set_mode=set_mode,
        extra_settle_time=extra_settle_time,
        stats_types=(),
        subs=subs,
        **metadata_kw,
    )

    return output


def abs_put(
    sigs,
    vals,
    set_mode: JumpSet | RampSet | None = None,
    extra_settle_time: float = 0.0,
    subs=None,
    **metadata_kw,
):

    relative = False
    return _put(
        relative,
        sigs,
        vals,
        set_mode=set_mode,
        extra_settle_time=extra_settle_time,
        subs=subs,
        **metadata_kw,
    )


def rel_put(
    sigs,
    vals,
    set_mode: JumpSet | RampSet | None = None,
    extra_settle_time: float = 0.0,
    subs=None,
    **metadata_kw,
):

    relative = True
    return _put(
        relative,
        sigs,
        vals,
        set_mode=set_mode,
        extra_settle_time=extra_settle_time,
        subs=subs,
        **metadata_kw,
    )
