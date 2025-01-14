from functools import partial
import inspect
from pathlib import Path
import time
from typing import Literal

import click
from epics import ca
from epics.ca import withMaybeConnectedCHID
from epics.pv import _ensure_context
import numpy as np

import pamila as pml
from pamila.middle_layer import MiddleLayerVariableListRO, MiddleLayerVariableListROSpec
from pamila.timer import TimerDict


@click.group()
def cli():
    pass


def connect_online_mlvs(mlvs, mlvl=None):

    Q_ = pml.unit.Q_

    if False:  # slow (sequential) version (~20 s for production)
        for mlv in mlvs.values():
            mlv.wait_for_connection()
    elif True:  # faster (parallel) version (~2 s for production)
        args = [[], [], {}]
        for mlv in mlvs.values():
            _mlv_names, _sigs, _pend_funcs = mlv.get_connection_check_args()
            args[0].extend(_mlv_names)
            args[1].extend(_sigs)
            args[2].update(_pend_funcs)
        pml.middle_layer._wait_for_connection(*args, timeout=Q_("20 s"))
    else:  # about the same as "faster"
        mlvl.wait_for_connection(all_modes=False)


@withMaybeConnectedCHID
def modified_ca_get_with_metadata(
    chid,
    ftype=None,
    count=None,
    wait=True,
    timeout=None,
    as_string=False,
    as_numpy=True,
):
    """
    Based on epics.ca.get_with_metadata()

    Return the current value along with metadata for a Channel

    Parameters
    ----------
    chid :  ctypes.c_long
       Channel ID
    ftype : int
       field type to use (native type is default)
    count : int
       maximum element count to return (full data returned by default)
    as_string : bool
       whether to return the string representation of the value.  See notes.
    as_numpy : bool
       whether to return the Numerical Python representation for array /
       waveform data.
    wait : bool
        whether to wait for the data to be received, or return immediately.
    timeout : float
        maximum time to wait for data before returning ``None``.

    Returns
    -------
    data : dict or None
       The dictionary of data, guaranteed to at least have the 'value' key.
       Depending on ftype, other keys may also be present::

           {'precision', 'units', 'status', 'severity', 'enum_strs', 'status',
           'severity', 'timestamp', 'posixseconds', 'nanoseconds',
           'upper_disp_limit', 'lower_disp_limit', 'upper_alarm_limit',
           'upper_warning_limit', 'lower_warning_limit','lower_alarm_limit',
           'upper_ctrl_limit', 'lower_ctrl_limit'}

       Returns ``None`` if the channel is not connected, `wait=False` was used,
       or the data transfer timed out.

    See `get()` for additional usage notes.
    """

    from epics.ca import (
        _CB_GET,
        GET_PENDING,
        PySEVCHK,
        ctypes,
        element_count,
        field_type,
        get_cache,
        libca,
        name,
    )

    if ftype is None:
        ftype = field_type(chid)
    if ftype in (None, -1):
        return None
    if count is None:
        count = 0
        # count = element_count(chid)
        # don't default to the element_count here - let EPICS tell us the size
        # in the _onGetEvent callback
    else:
        count = min(count, element_count(chid))

    entry = get_cache(name(chid))
    if not entry:
        return

    # implementation note: cached value of
    #   None        implies no value, no expected callback
    #   GET_PENDING implies no value yet, callback expected.
    with entry.lock:
        (last_get,) = entry.get_results[ftype]
        if last_get is not GET_PENDING:
            entry.get_results[ftype] = [GET_PENDING]
            ret = libca.ca_array_get_callback(
                ftype, count, chid, _CB_GET, ctypes.py_object(ftype)
            )
            PySEVCHK("get", ret)

    # if wait:
    #     return get_complete_with_metadata(chid, count=count, ftype=ftype,
    #                                       timeout=timeout, as_string=as_string,
    #                                       as_numpy=as_numpy)

    return chid, dict(
        count=count,
        ftype=ftype,
        timeout=timeout,
        as_string=as_string,
        as_numpy=as_numpy,
    )


@_ensure_context
def _initiate_parallel_PV_get(
    self,
    count=None,
    as_string=False,
    as_numpy=True,
    timeout=None,
    with_ctrlvars=False,
    form=None,
    use_monitor=True,
):
    """Based on PV().get_with_metadata()"""

    if not self.wait_for_connection(timeout=timeout):
        return None

    if form is None:
        form = self.form
        ftype = self.ftype
    else:
        ftype = ca.promote_type(
            self.chid, use_ctrl=(form == "ctrl"), use_time=(form == "time")
        )

    if with_ctrlvars and getattr(self, "units", None) is None:
        if form != "ctrl":
            # ctrlvars will be updated as the get completes, since this
            # metadata comes bundled with our DBR_CTRL* request.
            pass
        else:
            self.get_ctrlvars()

    try:
        cached_length = len(self._args["value"])
    except TypeError:
        cached_length = 1

    # respect count argument on subscription also for calls to get
    if count is None and self._args["count"] != self._args["nelm"]:
        count = self._args["count"]

    # ca.get_with_metadata will handle multiple requests for the same
    # PV internally, so there is no need to change between
    # `get_with_metadata` and `get_complete_with_metadata` here.
    chid, wait_kwargs = modified_ca_get_with_metadata(
        self.chid,
        ftype=ftype,
        count=count,
        timeout=timeout,
        as_numpy=as_numpy,
        wait=False,
    )

    wait_args = (with_ctrlvars, form, chid)

    return wait_args, wait_kwargs


def _wait_for_parallel_PV_get_complete(
    self, with_ctrlvars, form, chid, as_string=False, as_numpy=True, **wait_kwawrgs
):
    """Based on PV().get_with_metadata()"""

    metad = ca.get_complete_with_metadata(chid, **wait_kwawrgs)

    if metad is None:
        # Get failed. Indicate with a `None` as the return value
        return

    # Update value and all included metadata. Depending on the PV
    # form, this could include timestamp, alarm information,
    # ctrlvars, and so on.
    self._args.update(**metad)

    if with_ctrlvars and form != "ctrl":
        # If the user requested ctrlvars and they were not included in
        # the request, return all metadata.
        metad = self._args.copy()

    val = metad["value"]

    if as_string:
        char_value = self._set_charval(val, force_long_string=as_string)
        metad["value"] = char_value
    elif self.nelm <= 1 or val is None:
        pass
    else:
        # After this point:
        #   * self.nelm is > 1
        #   * val should be set and a sequence
        try:
            len(val)
        except TypeError:
            # Edge case where a scalar value leaks through ca.unpack()
            val = [val]

        if count is None:
            count = len(val)

        if as_numpy and ca.HAS_NUMPY and not isinstance(val, ca.numpy.ndarray):
            val = ca.numpy.asarray(val)
        elif not as_numpy and ca.HAS_NUMPY and isinstance(val, ca.numpy.ndarray):
            val = val.tolist()

        # allow asking for less data than actually exists in the cached value
        if count < len(val):
            val = val[:count]

        # Update based on the requested type:
        metad["value"] = val

    # if as_namespace:
    #     return SimpleNamespace(**metad)
    return metad


def for_loop_pv_get(
    timer_d,
    timer_label_prefix,
    bpm_mlv_list,
    n=3,
    auto_monitor=False,
    use_monitor=True,
    mode=Literal["normal", "frozen", "parallel"],
    one_time_update_in_frozen_mode=True,
):

    pyepics_pvlist = [mlv.get_signals()[0]._read_pv for mlv in bpm_mlv_list]

    match mode:
        case "normal":
            for pv in pyepics_pvlist:
                pv.auto_monitor = auto_monitor

        case "frozen":
            for pv in pyepics_pvlist:
                if not any(
                    cb == _on_value_change_callback for cb in pv.callbacks.values()
                ):
                    orig_auto_monitor = pv.auto_monitor
                    if not orig_auto_monitor:
                        # This should come before "add_callback". Otherwise,
                        # pv.auto_monitor value becomes an integer, instead of bool.
                        pv.auto_monitor = True
                    pv.add_callback(_on_value_change_callback)
                    if not orig_auto_monitor:
                        pv.auto_monitor = orig_auto_monitor
            # "use_monitor" is ignored in this mode

        case "parallel":
            for pv in pyepics_pvlist:
                pv.auto_monitor = False
                pv._initiate_parallel_PV_get = partial(_initiate_parallel_PV_get, pv)
                pv._wait_for_parallel_PV_get_complete = partial(
                    _wait_for_parallel_PV_get_complete, pv
                )
        case _:
            raise ValueError

    time.sleep(1.0)

    data_list = []
    for i_meas in range(n):
        match mode:
            case "normal":
                with timer_d.timeit(f"{timer_label_prefix} #{i_meas+1}"):
                    data = [pv.get(use_monitor=use_monitor) for pv in pyepics_pvlist]
            case "frozen":
                with timer_d.timeit(
                    f"{timer_label_prefix} (whole process) #{i_meas+1}"
                ):
                    if one_time_update_in_frozen_mode:
                        with timer_d.timeit(
                            f"{timer_label_prefix} (set val to None) #{i_meas+1}"
                        ):
                            for pv in pyepics_pvlist:
                                pv._args["value"] = None

                        with timer_d.timeit(
                            f"{timer_label_prefix} (initiate update) #{i_meas+1}"
                        ):
                            for pv in pyepics_pvlist:
                                pv.auto_monitor = True

                        with timer_d.timeit(
                            f"{timer_label_prefix} (wait for update) #{i_meas+1}"
                        ):
                            if False:
                                pvs_to_be_updated = pyepics_pvlist[:]
                                while len(pvs_to_be_updated) != 0:
                                    inds_to_keep = []
                                    for i, pv in enumerate(pvs_to_be_updated):
                                        if pv._args["value"] is None:
                                            inds_to_keep.append(i)
                                    pvs_to_be_updated = [
                                        pv
                                        for i, pv in enumerate(pvs_to_be_updated)
                                        if i in inds_to_keep
                                    ]
                            else:
                                inds_to_keep = list(range(len(pyepics_pvlist)))
                                while len(inds_to_keep) != 0:
                                    new_inds_to_keep = []
                                    for i in inds_to_keep:
                                        pv = pyepics_pvlist[i]
                                        if pv._args["value"] is None:
                                            new_inds_to_keep.append(i)
                                    inds_to_keep = new_inds_to_keep

                    with timer_d.timeit(f"{timer_label_prefix} (gather) #{i_meas+1}"):
                        data = [pv.get(use_monitor=True) for pv in pyepics_pvlist]

            case "parallel":
                with timer_d.timeit(
                    f"{timer_label_prefix} (whole process) #{i_meas+1}"
                ):
                    with timer_d.timeit(
                        f"{timer_label_prefix} (initiate parallel get) #{i_meas+1}"
                    ):
                        wait_args_kwargs_list = [
                            pv._initiate_parallel_PV_get() for pv in pyepics_pvlist
                        ]

                    with timer_d.timeit(
                        f"{timer_label_prefix} (wait & gather) #{i_meas+1}"
                    ):
                        data_w_metad = [
                            pv._wait_for_parallel_PV_get_complete(
                                *wait_args, **wait_kwargs
                            )
                            for pv, (wait_args, wait_kwargs) in zip(
                                pyepics_pvlist, wait_args_kwargs_list
                            )
                        ]
                        data = [
                            d["value"] if d is not None else None for d in data_w_metad
                        ]
            case _:
                raise NotImplementedError

        data_list.append(data)

    ref_data = data_list[0]
    diff_list = [[v1 - v2 for v1, v2 in zip(data, ref_data)] for data in data_list[1:]]

    return data_list, diff_list


def _on_value_change_callback(pvname=None, value=None, **kwargs):
    # In the callback: pv = cb_info[1]; pv._clear_auto_monitor_subscription()
    #    Cannot use "pv.clear_auto_monitor(), as it will do "pv.auto_monitor = False"
    #
    # Immediately stop auto-monitor. You cannot do this with
    # "pv.auto_monitor = False", as we need "pv.auto_monitor"
    # to be always True in order to allow frozen cached value
    # for faster parallel get.

    pv_obj = kwargs["cb_info"][1]

    # Stop auto monitor (Here I intentially chose not to use
    # "pv_obj.auto_monitor = False" because this value has to stay True.)
    pv_obj._clear_auto_monitor_subscription()


@cli.command(name="test_PV_forLoop_get")
def cli_test_PV_forLoop_get():
    test_PV_forLoop_get()


def test_PV_forLoop_get():

    func_name = inspect.currentframe().f_code.co_name
    output_filepath = Path(f"{func_name}_result.txt")

    timer_d = TimerDict()

    lines = ["# Online PV for-loop get", ""]

    machine_name = "SR"
    cache_filepath = Path("test_SR_obj_production.pgz")

    with timer_d.timeit("Cached loading"):
        SR = pml.load_cached_machine(machine_name, cache_filepath)

    bpm_mlvs = SR.get_mlvs_via_value_tag("BPM")
    bpm_mlv_list = list(bpm_mlvs.values())

    spec = MiddleLayerVariableListROSpec(
        name="bpms_xy", exist_ok=False, mlvs=bpm_mlv_list
    )
    mlvl = MiddleLayerVariableListRO(spec)

    pml.go_online()

    with timer_d.timeit("Connection"):
        connect_online_mlvs(bpm_mlvs, mlvl=mlvl)

    for auto_monitor, use_monitor, expected_to_be_updated in [
        (False, True, True),
        (False, False, True),
        (True, True, True),
        (True, False, True),
    ]:
        data_list, diff_list = for_loop_pv_get(
            timer_d,
            f"{auto_monitor=}, {use_monitor=}",
            bpm_mlv_list,
            n=3,
            auto_monitor=auto_monitor,
            use_monitor=use_monitor,
            mode="normal",
        )

        assert np.any(np.array(diff_list) != 0.0) == expected_to_be_updated

    data_list, diff_list = for_loop_pv_get(
        timer_d, "parallel", bpm_mlv_list, n=3, mode="parallel"
    )

    assert np.any(np.array(diff_list) != 0.0) == expected_to_be_updated

    for update_once, expected_to_be_updated in [(True, True), (False, False)]:
        data_list, diff_list = for_loop_pv_get(
            timer_d,
            "frozen_updated" if update_once else "frozen_not_updated",
            bpm_mlv_list,
            n=3,
            mode="frozen",
            one_time_update_in_frozen_mode=update_once,
        )

        assert np.any(np.array(diff_list) != 0.0) == expected_to_be_updated

    timer_d.print(decimal=3)

    lines.extend(timer_d.get_print_lines(decimal=3))
    lines.append("")
    output_filepath.write_text("\n".join(lines))

    print("Finished")


if __name__ == "__main__":
    cli()
