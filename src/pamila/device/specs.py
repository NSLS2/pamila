from functools import partial
from typing import Any, Callable, Dict, List

import numpy as np
from pydantic import (
    BaseModel,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from ..serialization import json_deserialize_numpy_array, json_serialize_numpy_array
from .conversion.plugin_manager import FUNC_MAP, IS_FACTORY_FUNC


class FunctionSpec(BaseModel):
    name: str
    args: List[Any] = Field(default_factory=list)
    kwargs: Dict[str, Any] = Field(default_factory=dict)

    @field_serializer("args")
    def serialize_numpy_arrays_in_list(self, value):
        mod_list = []
        for v in value:
            if isinstance(v, np.ndarray):
                mod_list.append(json_serialize_numpy_array(v))
            else:
                mod_list.append(v)

        return mod_list

    @field_serializer("kwargs")
    def serialize_numpy_arrays_in_dict(self, value):
        mod_dict = {}
        for k, v in value.items():
            if isinstance(v, np.ndarray):
                mod_dict[k] = json_serialize_numpy_array(v)
            else:
                mod_dict[k] = v

        return mod_dict

    @field_validator("args", mode="before")
    def deserialize_numpy_arrays_in_list(cls, value):
        return [json_deserialize_numpy_array(v) for v in value]

    @field_validator("kwargs", mode="before")
    def deserialize_numpy_arrays_in_dict(cls, value):
        return {k: json_deserialize_numpy_array(v) for k, v in value.items()}


def _reconstruct_callable(func_spec: FunctionSpec) -> Callable:
    func_name = func_spec.name
    base_func = FUNC_MAP.get(func_name)

    if base_func is None:
        raise ValueError(f"Unknown function name: {func_name}")

    if IS_FACTORY_FUNC[func_name]:
        func = base_func(*func_spec.args, **func_spec.kwargs)
    else:
        func = partial(base_func, *func_spec.args, **func_spec.kwargs)

    return func


class UnitConvSpec(BaseModel):
    """
    uc = UnitConvSpec(...)
    d = uc.model_dump_json()
    uc_reconstructed = UnitConvSpec.model_validate_json(d)
    """

    src_units: str | List[str]
    dst_units: str | List[str]
    func_spec: FunctionSpec
    func: Callable | None = Field(
        default=None, exclude=True
    )  # Exclude func during serialization
    aux_src_units: str | List[str] = Field(default_factory=list)
    aux_dst_units: str | List[str] = Field(default_factory=list)

    @field_validator(
        "src_units", "dst_units", "aux_src_units", "aux_dst_units", mode="before"
    )
    def listify_units(cls, value):
        if isinstance(value, str):
            return [value]
        else:
            assert isinstance(value, list)
            return value

    @model_validator(mode="after")
    def reconstruct_func(self):
        if self.func is not None:
            assert callable(self.func)
            return self
        self.func = _reconstruct_callable(self.func_spec)
        return self

    model_config = {"arbitrary_types_allowed": True, "extra": "forbid"}


class PamilaDeviceActionSpec(BaseModel):
    input_cpt_attr_names: List[str]
    output_cpt_attr_names: List[str]
    aux_input_cpt_attr_names: List[str] = Field(default_factory=list)
    aux_output_cpt_attr_names: List[str] = Field(default_factory=list)
    unitconv: UnitConvSpec | None = None
