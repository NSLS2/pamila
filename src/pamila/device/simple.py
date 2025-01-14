import threading
import time as ttime  # as defined in ophyd.device
from typing import Dict, List

from ophyd.status import DeviceStatus
from pydantic import BaseModel, Field, field_serializer, field_validator

SLEEP = ttime.sleep
# SLEEP = bps_sleep

from ..serialization import json_deserialize_pint_quantity, json_serialize_pint_quantity
from ..unit import Q_, fast_convert
from .base import PamilaDeviceBase, PamilaDeviceBaseSpec, PamilaOphydDeviceBase
from .specs import PamilaDeviceActionSpec, UnitConvSpec


class FixedWaitTime(BaseModel):
    dt: Q_ = Q_("0.0 s")

    model_config = {"arbitrary_types_allowed": True, "extra": "forbid"}

    @field_serializer("dt")
    def serialize_pint_quantity(self, value):
        return json_serialize_pint_quantity(value)

    @field_validator("dt", mode="before")
    def deserialize_pint_quantity(cls, value):
        return json_deserialize_pint_quantity(value)


class SetpointReadbackDiffBase(BaseModel):
    abs_tol: Q_ | None = None
    rel_tol: float | None = None
    settle_time: Q_ = Q_("0 s")
    timeout: Q_ | None = None
    poll_time: Q_ = Q_("0.2 s")

    model_config = {"arbitrary_types_allowed": True, "extra": "forbid"}

    @field_serializer("abs_tol", "settle_time", "timeout", "poll_time")
    def serialize_pint_quantity(self, value):
        if value is None:
            return None

        return json_serialize_pint_quantity(value)

    @field_validator("abs_tol", "settle_time", "timeout", "poll_time", mode="before")
    def deserialize_pint_quantity(cls, value):
        if value is None:
            return None

        return json_deserialize_pint_quantity(value)


class SetpointReadbackDiff(SetpointReadbackDiffBase):
    RB_attr_name: str


class SetWaitSpec(BaseModel):
    SP_RB_diff: SetpointReadbackDiff | None = None
    fixed_wait_time: FixedWaitTime | None = None


class SimplePamilaOphydDevice(PamilaOphydDeviceBase):
    def __init__(
        self,
        prefix="",
        *,
        name,
        input_psig_names: Dict[str, List[str]],
        output_psig_names: Dict[str, List[str]],
        unitconvs: Dict[str, UnitConvSpec | None],
        iterable_get_output: bool = False,
        set_wait_spec: SetWaitSpec | None = None,
        set_wait_method: str | None = None,
        **kwargs,
    ):
        super().__init__(
            prefix=prefix,
            name=name,
            input_psig_names=input_psig_names,
            output_psig_names=output_psig_names,
            unitconvs=unitconvs,
            iterable_get_output=iterable_get_output,
            **kwargs,
        )

        self._set_wait_spec = set_wait_spec

        self._current_set_wait_method = None
        if set_wait_spec is not None:
            for k, v in set_wait_spec.model_dump().items():
                if self._current_set_wait_method is None:
                    self._current_set_wait_method = (k, getattr(set_wait_spec, k))

                if v is not None:
                    self._current_set_wait_method = (k, getattr(set_wait_spec, k))
                    break

            self.change_set_wait_method(set_wait_method)

    def change_set_wait_method(self, method_name: str):

        self._current_set_wait_method = None
        for k, v in self._set_wait_spec.model_dump().items():
            if k == method_name:
                self._current_set_wait_method = (k, getattr(self._set_wait_spec, k))
                break
        else:
            raise ValueError(f"Invalid method name for set wait: {k}")

    def set(self, values_w_unit, **kwargs):

        if self._current_set_wait_method:
            method_name, opts = self._current_set_wait_method
        else:
            method_name = None

        match method_name:
            case None:
                dt = Q_("0 s")  # No wait
                status = _set_and_wait_for_fixed_duration(
                    self, values_w_unit, dt, **kwargs
                )

            case "fixed_wait_time":
                if opts is None:
                    raise RuntimeError("Options not set for `fixed_wait_time`")
                status = _set_and_wait_for_fixed_duration(
                    self, values_w_unit, opts.dt, **kwargs
                )

            case "SP_RB_diff":
                if opts is None:
                    raise RuntimeError("Options not set for `SP_RB_diff`")
                status = _set_and_wait_until_SP_RB_diff_small(
                    self, values_w_unit, opts, **kwargs
                )
            case _:
                raise NotImplementedError

        return status


SimplePamilaDeviceROSpec = PamilaDeviceBaseSpec


class SimplePamilaDeviceSpec(PamilaDeviceBaseSpec):
    readback_in_set: PamilaDeviceActionSpec | None = None
    set_wait_spec: SetWaitSpec | None = None
    set_wait_method: str | None = None


class SimplePamilaDevice(PamilaDeviceBase):
    def __init__(
        self,
        pdev_spec: SimplePamilaDeviceSpec | None = Field(
            default_factory=SimplePamilaDeviceSpec
        ),
        **kwargs,
    ):
        super().__init__(pdev_spec, **kwargs)

        self._podev_kwargs["set_wait_method"] = pdev_spec.set_wait_method
        self._podev_kwargs["set_wait_spec"] = pdev_spec.set_wait_spec

    def _init_ophyd_device_classes(self):
        self._ophyd_device_classes = (SimplePamilaOphydDevice,)

    def change_set_wait_method(self, method_name: str):
        odev = self.get_ophyd_device()
        odev.change_set_wait_method(method_name)


class SimplePamilaDeviceRO(PamilaDeviceBase):

    def __init__(
        self,
        pdev_spec: SimplePamilaDeviceROSpec | None = Field(
            default_factory=SimplePamilaDeviceROSpec
        ),
        **kwargs,
    ):
        super().__init__(pdev_spec, **kwargs)

    def _init_ophyd_device_classes(self):
        self._ophyd_device_classes = (SimplePamilaOphydDevice,)


def _set_and_wait_for_fixed_duration(
    odev: SimplePamilaOphydDevice, values_w_unit, dt: Q_, **kwargs
):

    status = DeviceStatus(odev)

    def put_and_complete():
        odev.put(values_w_unit, **kwargs)
        status.set_finished()

    timer = threading.Timer(fast_convert(dt, "s").m, put_and_complete)
    timer.start()

    return status


def _set_and_wait_until_SP_RB_diff_small(
    odev: SimplePamilaOphydDevice, values_w_unit, opts, **kwargs
):

    if opts.timeout is None:
        timeout = None
    else:
        timeout = fast_convert(opts.timeout, "s").m

    poll_time = fast_convert(opts.poll_time, "s").m
    settle_time = fast_convert(opts.settle_time, "s").m

    match values_w_unit:
        case list():
            if len(values_w_unit) != 1:
                raise NotImplementedError
            target_val = values_w_unit[0]
        case Q_():
            target_val = values_w_unit
        case _:
            raise TypeError

    atol = None if opts.abs_tol is None else opts.abs_tol
    rtol = None if opts.rel_tol is None else opts.rel_tol

    def target_reached(current_val):
        # Based on np.allclose():
        #   absolute(`a` - `b`) <= (`atol` + `rtol` * absolute(`b`))
        a = current_val
        b = target_val

        _rtol = rtol if rtol is not None else 0.0
        _atol = atol if atol is not None else a * 0.0

        close = abs(a - b) <= _atol + _rtol * abs(b)

        return close

    status = DeviceStatus(odev, timeout=timeout)

    def check_readback():

        # First check setpoints have been successfully changed
        current_SP_val = odev.get(return_iterable=False)
        assert target_reached(current_SP_val)

        # Wait until RB gets close to SP
        while True:
            LoLv_RB_vals = [psig.get() for psig in odev._input_psigs["readback_in_set"]]
            HiLv_RB_vals = odev._convert_values(LoLv_RB_vals, "readback_in_set")
            ts = ttime.time()
            for psig, v in zip(odev._output_psigs["readback_in_set"], HiLv_RB_vals):
                psig.put(v, timestamp=ts)

            current_RB_val = HiLv_RB_vals[0]

            if target_reached(current_RB_val):
                break

            SLEEP(poll_time)

        SLEEP(settle_time)
        status.set_finished()

    odev.put(target_val, **kwargs)

    threading.Thread(target=check_readback, daemon=True).start()

    return status
