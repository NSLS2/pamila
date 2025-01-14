import atexit
import logging

import epics
from epics import ca, caget, caput
from epics.ca import withMaybeConnectedCHID
from epics.pv import _ensure_context

# from ._dispatch import EventDispatcher, _CallbackThread, wrap_callback
from ophyd._dispatch import EventDispatcher, _CallbackThread, wrap_callback
from packaging.version import parse

_min_pyepics = "3.4.2"

if parse(epics.__version__) < parse(_min_pyepics):
    raise ImportError(
        "Version of pyepics too old. "
        f"Ophyd requires at least {_min_pyepics}"
        f"but {epics.__version__} is installed"
    )

try:
    ca.find_libca()
except ca.ChannelAccessException:
    raise ImportError("libca not found; pyepics is unavailable")
else:
    thread_class = ca.CAThread


module_logger = logging.getLogger(__name__)
name = "pyepics"
_dispatcher = None
get_pv = epics.get_pv


def get_dispatcher():
    "The event dispatcher for the pyepics control layer"
    return _dispatcher


class PyepicsCallbackThread(_CallbackThread):
    def attach_context(self):
        super().attach_context()
        ca.attach_context(self.context)

    def detach_context(self):
        super().detach_context()
        if ca.current_context() is not None:
            ca.detach_context()


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


class ParallelEnabledPyepicsShimPV(epics.PV):
    def __init__(
        self,
        pvname,
        callback=None,
        form="time",
        verbose=False,
        auto_monitor=None,
        count=None,
        connection_callback=None,
        connection_timeout=None,
        access_callback=None,
    ):
        connection_callback = wrap_callback(
            _dispatcher, "metadata", connection_callback
        )
        callback = wrap_callback(_dispatcher, "monitor", callback)
        access_callback = wrap_callback(_dispatcher, "metadata", access_callback)

        super().__init__(
            pvname,
            form=form,
            verbose=verbose,
            auto_monitor=auto_monitor,
            count=count,
            connection_timeout=connection_timeout,
            connection_callback=connection_callback,
            callback=callback,
            access_callback=access_callback,
        )

        self._cache_key = (pvname, form, self.context)
        self._reference_count = 0

        self._parallel_get_enabled = False
        self._parallel_wait_args = None
        self._parallel_wait_kwargs = None

    def add_callback(
        self, callback=None, index=None, run_now=False, with_ctrlvars=True, **kw
    ):
        if not self.auto_monitor:
            self.auto_monitor = ca.DEFAULT_SUBSCRIPTION_MASK
        callback = wrap_callback(_dispatcher, "monitor", callback)
        return super().add_callback(
            callback=callback,
            index=index,
            run_now=run_now,
            with_ctrlvars=with_ctrlvars,
            **kw,
        )

    def put(
        self,
        value,
        wait=False,
        timeout=None,
        use_complete=False,
        callback=None,
        callback_data=None,
    ):
        callback = wrap_callback(_dispatcher, "get_put", callback)
        # pyepics does not accept an indefinite timeout
        if timeout is None:
            timeout = 315569520  # ten years
        return super().put(
            value,
            wait=wait,
            timeout=timeout,
            use_complete=use_complete,
            callback=callback,
            callback_data=callback_data,
        )

    def _getarg(self, arg):
        "wrapper for property retrieval"
        # NOTE: replaces epics.PV._getarg: does not call get() when value unset
        if self._args[arg] is None:
            if arg in (
                "status",
                "severity",
                "timestamp",
                "posixseconds",
                "nanoseconds",
            ):
                self.get_timevars(timeout=1, warn=False)
            else:
                self.get_ctrlvars(timeout=1, warn=False)
        return self._args.get(arg, None)

    def get_all_metadata_blocking(self, timeout):
        if self._args["status"] is None:
            self.get_timevars(timeout=timeout)
        self.get_ctrlvars(timeout=timeout)
        md = self._args.copy()
        md.pop("value", None)
        return md

    def get_all_metadata_callback(self, callback, *, timeout):
        def get_metadata_thread(pvname):
            md = self.get_all_metadata_blocking(timeout=timeout)
            callback(pvname, md)

        _dispatcher.schedule_utility_task(get_metadata_thread, pvname=self.pvname)

    def clear_callbacks(self):
        super().clear_callbacks()
        self.access_callbacks.clear()
        self.connection_callbacks.clear()

    @_ensure_context
    def _initiate_PV_get_new_wo_wait(
        self,
        count=None,
        as_string=False,
        as_numpy=True,
        timeout=None,
        with_ctrlvars=False,
        form=None,
        use_monitor=True,
    ):
        """Based on epics.PV().get_with_metadata()"""

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

        self._parallel_wait_args = (with_ctrlvars, form, chid)
        self._parallel_wait_kwargs = wait_kwargs

    def _wait_for_PV_get_complete(self):
        """Based on PV().get_with_metadata()"""

        with_ctrlvars, form, chid = self._parallel_wait_args
        as_string = self._parallel_wait_kwargs.pop("as_string", False)
        as_numpy = self._parallel_wait_kwargs.pop("as_numpy", True)
        wait_kwawrgs = self._parallel_wait_kwargs

        self._parallel_wait_args = None

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

    def _get_with_frozen_metadata(self):
        metad = self._args.copy()
        val = self._args["value"]

        as_string = self._parallel_wait_kwargs.pop("as_string", False)
        as_numpy = self._parallel_wait_kwargs.pop("as_numpy", True)

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

    def _get_with_metadata_for_parallel(self):

        if self._parallel_wait_args is None:
            metad = self._get_with_frozen_metadata()
        else:
            metad = self._wait_for_PV_get_complete()

        return metad

    def get_with_metadata(self, *args, **kwargs):
        if self._parallel_get_enabled:
            return self._get_with_metadata_for_parallel()
        else:
            return super().get_with_metadata(*args, **kwargs)


def release_pvs(*pvs):
    for pv in pvs:
        pv._reference_count -= 1
        if pv._reference_count == 0:
            pv.clear_callbacks()
            pv.clear_auto_monitor()
            if pv.chid is not None:
                # Clear the channel on the CA-level
                epics.ca.clear_channel(pv.chid)

            pv.chid = None
            pv.context = None

            # Ensure we don't get this same PV back again
            epics.pv._PVcache_.pop(pv._cache_key, None)


def setup(logger):
    """Setup ophyd for use

    Must be called once per session using ophyd
    """
    # It's important to use the same context in the callback _dispatcher
    # as the main thread, otherwise not-so-savvy users will be very
    # confused
    global _dispatcher

    if _dispatcher is not None:
        logger.debug("ophyd already setup")
        return

    # epics.pv.default_pv_class = PyepicsShimPV
    epics.pv.default_pv_class = ParallelEnabledPyepicsShimPV

    def _cleanup():
        """Clean up the ophyd session"""
        global _dispatcher
        if _dispatcher is None:
            return
        epics.pv.default_pv_class = epics.PV

        if _dispatcher.is_alive():
            _dispatcher.stop()

        _dispatcher = None

    logger.debug("Installing event dispatcher")
    _dispatcher = EventDispatcher(
        thread_class=PyepicsCallbackThread, context=ca.current_context(), logger=logger
    )
    atexit.register(_cleanup)
    return _dispatcher


__all__ = (
    "setup",
    "caput",
    "caget",
    "get_pv",
    "thread_class",
    "name",
    "release_pvs",
    "get_dispatcher",
)
