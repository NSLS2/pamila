from enum import Enum
from typing import Any, Dict, List

import numpy as np
from pydantic import BaseModel


class RevalidatingModel(BaseModel):
    def __setattr__(self, key, value):
        # self._validate_before_manual_change(key, value)
        super().__setattr__(key, value)

    def _validate_before_manual_change(self, key, value):
        # TODO: It appears this method is not needed, if we set
        # `model_config["validate_assignment"] = True`. But, it will be kept
        # in case this turns out to be false later.
        #
        # By the way, this method is not usable, if the model has more than one
        # invalid values assigned as initial values. Because you can change
        # one attribute at a time, the other invalid values will always raise
        # errors.

        temp_model = self.model_copy(update={key: value})
        values = temp_model.__dict__
        # ^ Here, you may think "values = temp_model.model_dump()" can be used.
        # But, it can cause a problem if this model uses field_serializer.
        # This is because when self.__class__() below is called, your custom
        # deserializer within a field_validator method will not be run, which
        # results in a failed validation.
        self.__class__(**values)  # Re-validate by creating a new instance


class KeyIndexAccess:
    def __init__(self, key_or_index: Any):
        self.name = key_or_index

    def __str__(self):
        return f"KeyIndexAccess(name={self.name})"

    def __repr__(self):
        return f"KeyIndexAccess(name='{self.name}')"

    def __eq__(self, other):
        if isinstance(other, KeyIndexAccess):
            return self.name == other.name
        return False

    def __hash__(self):
        return hash(f"KeyIndexAccess:{self.name}")


class AttributeAccess:
    def __init__(self, name: str):
        self.name = name

    def __str__(self):
        return f"AttributeAccess(name={self.name})"

    def __repr__(self):
        return f"AttributeAccess(name='{self.name}')"

    def __eq__(self, other):
        if isinstance(other, AttributeAccess):
            return self.name == other.name
        return False

    def __hash__(self):
        return hash(f"AttributeAccess:{self.name}")


class ChainedPropertyAccess:
    def __init__(
        self, root_obj: Any, access_list: List[KeyIndexAccess | AttributeAccess]
    ):
        self.root = root_obj

        assert len(access_list) != 0
        assert all(
            [isinstance(v, (KeyIndexAccess, AttributeAccess)) for v in access_list]
        )

        self.access_list = access_list


class ChainedPropertyFetcher(ChainedPropertyAccess):
    def get(self):

        val = self.root
        for ac in self.access_list:
            if isinstance(ac, KeyIndexAccess):
                val = val[ac.name]
            else:
                val = getattr(val, ac.name)

        return val

    def __repr__(self):
        return f"ChainedPropertyFetcher(root_class={self.root.__class__}, access_list={self.access_list})"

    def __str__(self):
        return self.__repr__()


class ChainedPropertyPusher(ChainedPropertyFetcher):
    def put(self, new_val: Any) -> bool:

        obj = self.root

        for ac in self.access_list[:-1]:
            if isinstance(ac, KeyIndexAccess):
                if ac.name not in obj:
                    obj[ac.name] = {}
                obj = obj[ac.name]
            else:
                obj = getattr(obj, ac.name)

        ac = self.access_list[-1]
        if isinstance(ac, KeyIndexAccess):
            try:
                old_val = obj[ac.name]
            except KeyError:
                old_val = None if new_val is not None else False
                # ^ This value assignment will ensure the variable "changed"
                #   will become True below.
            obj[ac.name] = new_val
        else:
            old_val = getattr(obj, ac.name)
            setattr(obj, ac.name, new_val)

        changed = new_val != old_val
        return changed

    def __repr__(self):
        return f"ChainedPropertyPusher(root_class={self.root.__class__}, access_list={self.access_list})"

    def __str__(self):
        return self.__repr__()


class StatisticsType(Enum):
    MIN = "min"
    MAX = "max"
    MEAN = "mean"
    AVG = "avg"
    AVERAGE = "average"
    MEDIAN = "median"
    STD = "std"
    IQR = "iqr"


def convert_stats_type_to_func_dict(stats_type: str | StatisticsType):
    if stats_type in (
        "mean",
        "average",
        "avg",
        StatisticsType.MEAN,
        StatisticsType.MEAN.value,
        StatisticsType.AVG,
        StatisticsType.AVG.value,
        StatisticsType.AVERAGE,
        StatisticsType.AVERAGE.value,
    ):
        return {"mean": np.mean}
    elif stats_type in (StatisticsType.STD, StatisticsType.STD.value):
        return {"std": np.std}
    elif stats_type in (StatisticsType.MIN, StatisticsType.MIN.value):
        return {"min": np.min}
    elif stats_type in (StatisticsType.MAX, StatisticsType.MAX.value):
        return {"max": np.max}
    elif stats_type in (StatisticsType.MEDIAN, StatisticsType.MEDIAN.value):
        return {"median": np.median}
    else:
        raise NotImplementedError


def get_available_enum_values(enum_obj: Enum):
    return list(type(enum_obj))


class PartiallyUpdatableDict(dict):
    def __init__(self, original_dict: Dict):
        super().__init__()

        for k, v in original_dict.items():
            if isinstance(v, dict):
                self[k] = PartiallyUpdatableDict(v)
            else:
                self[k] = v

    def partial_update(self, updates: Dict):

        for k, v in updates.items():
            if k in self:
                if isinstance(v, dict):
                    self[k].partial_update(v)
                else:
                    self[k] = v
            else:
                if isinstance(v, PartiallyUpdatableDict):
                    self[k] = v
                elif isinstance(v, dict):
                    self[k] = PartiallyUpdatableDict(v)
                else:
                    self[k] = v


class MachineDefault(BaseModel):
    value: str = "__MACHINE_DEFAULT__"

    model_config = {"frozen": True}


class DesignLatticeProperty(BaseModel):
    value: Any = "__design_lattice_prop_val__"

    model_config = {"frozen": False}


def json_serialize_design_lat_prop(obj: DesignLatticeProperty):

    return {"__design_lattice_prop_val__": True}


def json_deserialize_design_lat_prop(value):
    if isinstance(value, dict) and value.get("__design_lattice_prop_val__"):
        return DesignLatticeProperty()
    else:
        return value


MACHINE_DEFAULT = MachineDefault()
