from copy import deepcopy
import time as ttime  # as defined in ophyd.device
from typing import Dict, List, get_args

from ophyd import Component as Cpt
from ophyd import Device
from ophyd.status import DeviceStatus
from ophyd.utils import ReadOnlyError
from pydantic import BaseModel, field_serializer, field_validator

from .. import MachineMode
from ..serialization import json_deserialize_component, json_serialize_component
from ..signal import (
    ExternalPamilaSignal,
    ExternalPamilaSignalRO,
    InternalPamilaSignal,
    InternalPamilaSignalRO,
    UserPamilaSignal,
)
from ..unit import Unit
from .specs import PamilaDeviceActionSpec, UnitConvSpec

PAMILA_SIGNAL_CLASS_MAP = dict(
    InternalPamilaSignal=InternalPamilaSignal,
    InternalPamilaSignalRO=InternalPamilaSignalRO,
    ExternalPamilaSignal=ExternalPamilaSignal,
    ExternalPamilaSignalRO=ExternalPamilaSignalRO,
    UserPamilaSignal=UserPamilaSignal,
)


class PamilaDeviceBaseSpec(BaseModel):
    pdev_name: str
    machine_name: str
    machine_mode: MachineMode
    read_only: bool
    components: Dict[str, Cpt]
    get_spec: PamilaDeviceActionSpec
    put_spec: PamilaDeviceActionSpec | None = None
    iterable_get_output: bool = False

    @field_serializer("components")
    def serialize_components(self, value):
        return {
            k: json_serialize_component(cpt_instance)
            for k, cpt_instance in value.items()
        }

    @field_validator("components", mode="before")
    def deserialize_components(cls, value):
        # If the value is already a dict of Cpt instances, return it as is
        if all(isinstance(v, Cpt) for v in value.values()):
            return value

        # Otherwise, reconstruct Cpt instances
        return {
            k: json_deserialize_component(v, PAMILA_SIGNAL_CLASS_MAP)
            for k, v in value.items()
        }

    model_config = {"arbitrary_types_allowed": True, "extra": "forbid"}


def extract_other_action_specs_and_kwargs_from_spec(spec: PamilaDeviceBaseSpec):

    base_attr_names = list(PamilaDeviceBaseSpec.model_fields)

    other_action_specs = {}
    other_kwargs = {}
    for attr_name, fld_info in spec.model_fields.items():
        if attr_name in base_attr_names:
            continue

        v = getattr(spec, attr_name)
        if PamilaDeviceActionSpec in get_args(fld_info.annotation):
            other_action_specs[attr_name] = v
        else:
            other_kwargs[attr_name] = v

    return other_action_specs, other_kwargs


class PamilaOphydDeviceBase(Device):
    def __init__(
        self,
        prefix="",
        *,
        name,
        input_psig_names: Dict[str, List[str]],
        output_psig_names: Dict[str, List[str]],
        unitconvs: Dict[str, UnitConvSpec | None],
        iterable_get_output: bool = False,
        **kwargs,
    ):
        super().__init__(prefix=prefix, name=name, **kwargs)

        self._input_psig_names = input_psig_names
        self._output_psig_names = output_psig_names
        self._unitconvs = unitconvs

        self._input_psigs = {}
        self._output_psigs = {}

        for action_type in self._input_psig_names.keys():
            self._input_psigs[action_type] = [
                getattr(self, name) for name in self._input_psig_names[action_type]
            ]
            self._output_psigs[action_type] = [
                getattr(self, name) for name in self._output_psig_names[action_type]
            ]

        if len(self._output_psigs["get"]) == 1:
            self._return_iterable_for_get = iterable_get_output
        elif len(self._output_psigs["get"]) == 0:
            raise RuntimeError
        else:
            self._return_iterable_for_get = True

    @staticmethod
    def _return_scalar_or_list(values: List, return_iterable: bool = False):
        if (len(values) == 1) and (not return_iterable):
            return values[0]
        else:
            return values

    def _convert_values(self, values_w_unit: List, action_type: str) -> List:

        uc = self._unitconvs[action_type]

        if uc:
            assert len(values_w_unit) == len(uc.src_units)
            values_wo_unit = [
                v.to(src_unit).m for v, src_unit in zip(values_w_unit, uc.src_units)
            ]

            outputs_wo_unit = uc.func(*values_wo_unit)

            try:
                len(outputs_wo_unit)
            except TypeError:
                output = outputs_wo_unit * Unit(uc.dst_units[0])
                return [output]

            assert len(outputs_wo_unit) == len(uc.dst_units)
            return [
                v_wo_unit * Unit(dst_unit)
                for v_wo_unit, dst_unit in zip(outputs_wo_unit, uc.dst_units)
            ]

        else:
            return values_w_unit

    def convert_values(
        self,
        values_w_unit: List | float,
        action_type: str,
        return_iterable: bool = False,
    ):

        match values_w_unit:
            case list():
                pass
            case float():
                values_w_unit = [values_w_unit]
            case _:
                raise TypeError

        conv_vals_w_unit = self._convert_values(values_w_unit, action_type)

        return self._return_scalar_or_list(conv_vals_w_unit, return_iterable)

    def get(self, return_iterable: bool | None = None):

        LoLv_vals = [psig.get() for psig in self._input_psigs["get"]]

        HiLv_vals = self._convert_values(LoLv_vals, "get")
        ts = ttime.time()
        for psig, v in zip(self._output_psigs["get"], HiLv_vals):
            psig.put(v, timestamp=ts)

        if return_iterable is None:
            return_iterable = self._return_iterable_for_get

        self._readback = self._return_scalar_or_list(
            HiLv_vals, return_iterable=return_iterable
        )

        return self._readback

    def read(self):
        res = super().read()
        ts = ttime.time()

        LoLv_vals = [
            res[f"{self.root.name}_{cpt_attr_name}"]["value"]
            for cpt_attr_name in self._input_psig_names["get"]
        ]
        HiLv_vals = self._convert_values(LoLv_vals, "get")

        for cpt_attr_name, v in zip(self._output_psig_names["get"], HiLv_vals):
            k = f"{self.root.name}_{cpt_attr_name}"
            res[k]["value"] = v
            res[k]["timestamp"] = ts

        return res

    def put(self, new_values_w_unit, **kwargs):

        if not isinstance(new_values_w_unit, list):
            new_values_w_unit = [new_values_w_unit]

        for psig, v in zip(self._input_psigs["put"], new_values_w_unit):
            psig.put(v, **kwargs)

        LoLv_vals = self._convert_values(new_values_w_unit, "put")

        for psig, v in zip(self._output_psigs["put"], LoLv_vals):
            psig.put(v, **kwargs)

    def set(self, values_w_unit, **kwargs):

        status = DeviceStatus(self.get_ophyd_device())
        self.put(values_w_unit, **kwargs)
        status.set_finished()

        return status

    def triggerable(self):
        return len(self.trigger_signals) != 0


class PamilaDeviceBase:
    def __init__(
        self,
        pdev_spec: PamilaDeviceBaseSpec,
        **kwargs,  # kwargs for base ophyd device instantiation
    ):
        self._machine_name = pdev_spec.machine_name
        self._mode = pdev_spec.machine_mode  # mode
        self._read_only = pdev_spec.read_only
        self._components = pdev_spec.components  # components
        self._iterable_get_output = pdev_spec.iterable_get_output
        self._podev_kwargs = {}
        self._odev_kwargs = dict(prefix="", name=pdev_spec.pdev_name, **kwargs)

        self._init_action_specs(pdev_spec)

        self._input_psig_names = {}
        self._output_psig_names = {}
        self._n_input = {}
        self._n_output = {}
        self._unitconvs = {}
        for action_type, spec in self._action_specs.items():

            if spec is None:
                continue

            self._input_psig_names[action_type] = spec.input_cpt_attr_names
            self._output_psig_names[action_type] = spec.output_cpt_attr_names

            self._n_input[action_type] = len(self._input_psig_names[action_type])
            self._n_output[action_type] = len(self._output_psig_names[action_type])

            self._unitconvs[action_type] = self._process_unitconv(
                spec.unitconv, action_type
            )

        self._ophyd_device_classes = None
        self._ophyd_device = None

        self._non_serializable_attrs = ["_ophyd_device_classes", "_ophyd_device"]

    def __getstate__(self):

        state = self.__dict__.copy()

        # Exclude the non-serializable attributes
        for attr in self._non_serializable_attrs:
            del state[attr]

        return state

    def __setstate__(self, state):
        self.__dict__.update(state)

        self._ophyd_device = None
        self._ophyd_device_classes = None
        # Not calling `self._init_ophyd_device()` here to re-initialize the
        # non-serializable attribute, but only setting `self._ophyd_device` and
        # `self._ophyd_device_classes` to `None`.
        #
        # When `self.get_ophyd_device()` is called, it'll be
        # initialized, which allows lazy loading.

    def _init_action_specs(self, spec: PamilaDeviceBaseSpec):

        self._action_specs = dict(get=spec.get_spec)

        if not self._read_only:
            self._action_specs["put"] = spec.put_spec

        other_action_specs, _ = extract_other_action_specs_and_kwargs_from_spec(spec)
        self._action_specs.update(other_action_specs)

    def get_ophyd_device(self) -> PamilaOphydDeviceBase:
        if self._ophyd_device is None:
            self._init_ophyd_device()

        return self._ophyd_device

    def _init_ophyd_device_classes(self):
        """Most likely this and self.__init__ are the only methods of this
        class that needs to be overwritten when customizing. Of course, you
        can add new methods as many as you want."""
        self._ophyd_device_classes = (PamilaOphydDeviceBase,)

    def _init_ophyd_device(self):

        self._init_ophyd_device_classes()

        class_name = "PamilaOphydDeviceWithDynamicCpts"
        parent_classes = self._ophyd_device_classes
        class_attrs = self._components
        dynamic_class = type(class_name, parent_classes, class_attrs)

        kwargs = deepcopy(self._podev_kwargs) | deepcopy(self._odev_kwargs)

        self._ophyd_device = dynamic_class(
            input_psig_names=self._input_psig_names,
            output_psig_names=self._output_psig_names,
            unitconvs=self._unitconvs,
            iterable_get_output=self._iterable_get_output,
            **kwargs,
        )

    def _process_unitconv(self, unitconv: UnitConvSpec | None, action_type: str):

        if unitconv is None:
            return None

        else:
            uc = unitconv
            if isinstance(uc.src_units, str):
                uc.src_units = [uc.src_units]
            if isinstance(uc.dst_units, str):
                uc.dst_units = [uc.dst_units]

            assert isinstance(uc.src_units, list)
            assert len(uc.src_units) == self._n_input[action_type]

            assert isinstance(uc.dst_units, list)
            assert len(uc.dst_units) == self._n_output[action_type]

            return uc

    def _convert_values(self, values_w_unit: List, action_type: str) -> List:
        odev = self.get_ophyd_device()
        return odev._convert_values(values_w_unit, action_type)

    def convert_values(
        self,
        values_w_unit: List | float,
        action_type: str,
        return_iterable: bool = False,
    ):
        odev = self.get_ophyd_device()
        return odev.convert_values(
            values_w_unit, action_type, return_iterable=return_iterable
        )

    def wait_for_connection(self, all_signals=False, timeout=2.0):
        odev = self.get_ophyd_device()
        return odev.wait_for_connection(all_signals=all_signals, timeout=timeout)

    def get(self, return_iterable: bool | None = None):

        odev = self.get_ophyd_device()
        return odev.get(return_iterable=return_iterable)

    def read(self):
        odev = self.get_ophyd_device()
        return odev.read()

    def put(self, values_w_unit, **kwargs):
        if self._read_only:
            raise ReadOnlyError

        odev = self.get_ophyd_device()
        odev.put(values_w_unit, **kwargs)

    def set(self, values_w_unit, **kwargs):
        if self._read_only:
            raise ReadOnlyError

        odev = self.get_ophyd_device()
        return odev.set(values_w_unit, **kwargs)
