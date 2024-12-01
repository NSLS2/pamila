from typing import Dict, Type

import numpy as np
from ophyd import Component as Cpt

from .unit import Q_, ureg


def json_serialize_numpy_array(value):
    return {"__numpy_array__": True, "list": value.tolist()}


def json_deserialize_numpy_array(value):
    if isinstance(value, dict) and value.get("__numpy_array__"):
        return np.array(value["list"])
    else:
        return value


def json_serialize_pint_quantity(value):
    return {
        "__pint_quantity__": True,
        "magnitude": value.magnitude,
        "units": str(value.units),
    }


def json_deserialize_pint_quantity(value):
    if isinstance(value, dict) and value.get("__pint_quantity__"):
        magnitude = value["magnitude"]
        units = value["units"]
        return magnitude * ureg(units)
    elif isinstance(value, str):
        return Q_(value)
    else:
        assert isinstance(value, Q_)
        return value


def json_serialize_component(cpt_instance):
    return {
        "cls": cpt_instance.cls.__name__,  # Store the class name
        "suffix": cpt_instance.suffix,
        "lazy": cpt_instance.lazy,
        "trigger_value": cpt_instance.trigger_value,
        "add_prefix": cpt_instance.add_prefix,
        "doc": cpt_instance.doc,
        "kind": cpt_instance.kind,
        "kwargs": cpt_instance.kwargs,
    }


def json_deserialize_component(cpt_data, class_map: Dict[str, Type]):
    cpt_data_copy = cpt_data.copy()
    cls_name = cpt_data_copy.pop("cls")

    if cls_name not in class_map:
        raise ValueError(f"Unknown class name: {cls_name}")

    return Cpt(cls=class_map[cls_name], **cpt_data_copy)
