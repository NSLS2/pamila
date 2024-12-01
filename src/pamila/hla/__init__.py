from collections.abc import Sequence
from copy import deepcopy
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple, Type

from pydantic import Field, field_serializer, field_validator
import yaml

from ..machine import Machine, MultiMachine, get_facility_name, get_machine
from ..middle_layer import (
    MloName,
    MlvlName,
    MlvName,
    MlvtName,
    nested_deserialize_mlo_names,
)
from ..serialization import json_deserialize_pint_quantity, json_serialize_pint_quantity
from ..unit import Q_
from ..utils import ChainedPropertyFetcher, ChainedPropertyPusher
from ..utils import KeyIndexAccess as KIA
from ..utils import MachineDefault, RevalidatingModel, StatisticsType

HLA_DEFAULTS = {}

_REJECT_MACHINE_DEFAULT = True


def load_hla_defaults(yaml_filepath: str | Path | None = None):
    if yaml_filepath is None:
        raise NotImplementedError

    yaml_filepath = Path(yaml_filepath)
    if not yaml_filepath.exists():
        raise FileNotFoundError()

    d = yaml.safe_load(yaml_filepath.read_text())["machines"]

    HLA_DEFAULTS.clear()
    HLA_DEFAULTS.update(nested_deserialize_mlo_names(d))


def get_hla_defaults(jsonified: bool = True):
    if jsonified:
        return _jsonify_HLA_DEFAULTS(HLA_DEFAULTS)
    else:
        return HLA_DEFAULTS


def _jsonify_HLA_DEFAULTS(value: Any):
    if isinstance(value, dict):
        new_d = {}
        for k, v in value.items():
            new_d[k] = _jsonify_HLA_DEFAULTS(v)
        return new_d
    elif isinstance(value, MloName):
        return value.json_serialize()
    elif isinstance(value, HlaStageParams):
        params_d = json.loads(value.model_dump_json(exclude_unset=True))
        return params_d
    else:
        return value


def save_hla_defaults_to_file(yaml_filepath: Path):

    json_HLA_DEFAULTS = _jsonify_HLA_DEFAULTS(HLA_DEFAULTS)

    to_be_saved = {"facility": get_facility_name(), "machines": json_HLA_DEFAULTS}

    with open(yaml_filepath, "w") as f:
        yaml.dump(
            to_be_saved,
            f,
            sort_keys=False,
            default_flow_style=False,
            width=70,
            indent=2,
        )


def extract_hla_path(module_path: str):

    module_path_tokens = module_path.split(".")

    hla_name = ".".join(module_path_tokens[module_path_tokens.index("hla") + 1 :])

    return hla_name


def _get_flow_names(flow_defs: Dict):
    return list(flow_defs)


def _get_flow(hla_name: str, flow_type: str, machine: Machine, flow_defs: Dict):

    stage_classes = flow_defs.get(flow_type, None)

    if stage_classes is None:
        raise NotImplementedError

    return HlaFlow(hla_name, flow_type, machine, stage_classes)


class HlaFlow:
    def __init__(
        self,
        hla_name: str,
        flow_type: str,
        machine: Machine | MultiMachine,
        stage_classes: List[Type],
    ):
        self._hla_name = hla_name
        self._flow_type = flow_type
        self._machine = machine
        self._stages = [cl(machine) for cl in stage_classes]
        self._stage_names = [stage.__module__.split(".")[-1] for stage in self._stages]
        self._ini_output = None

    def take_output_from_prev_stage(self, output_from_prev_stage: Any):
        self._ini_output = output_from_prev_stage

    def get_stage(self, stage_name: str):
        return self._stages[self._stage_names.index(stage_name)]

    def get_stage_names(self):
        return self._stage_names

    def get_params(self, stage_key: str | int):

        if isinstance(stage_key, int):
            index = stage_key
        elif isinstance(stage_key, str):
            index = self._stage_names.index(stage_key)
        else:
            raise TypeError

        return self._stages[index].params

    def run(self):
        output = deepcopy(self._ini_output)

        for stage in self._stages:
            match stage:
                case HlaInitialStage():
                    output = stage.run()
                case HlaStage():
                    stage.take_output_from_prev_stage(output)
                    output = stage.run()
                case _:
                    raise TypeError

        return output


def json_serialize_HlaFlow(obj: HlaFlow):

    return {
        "__hla_flow__": True,
        "hla_name": obj._hla_name,
        "flow_type": obj._flow_type,
        "machine_name": obj._machine.name,
        "stage_params": {
            stage_name: stage.params
            for stage, stage_name in zip(obj._stages, obj._stage_names)
            if stage.params is not None
        },
    }


def json_deserialize_HlaFlow(value):
    if isinstance(value, dict) and value.get("__hla_flow__"):
        hla_module = _HLA_NAME_TO_MODULE[value["hla_name"]]
        flow_type = value["flow_type"]
        flow = hla_module.get_flow(flow_type, get_machine(value["machine_name"]))
        for stage_name, new_param_d in value["stage_params"].items():
            params = flow.get_params(stage_name)
            stage = flow.get_stage(stage_name)
            for k, v in new_param_d.items():
                if isinstance(v, MloName):
                    v = stage.get_mlo(v)
                setattr(params, k, v)
        return flow
    else:
        assert isinstance(value, HlaFlow)
        return value


class HlaStageParams(RevalidatingModel):
    model_config = {
        "arbitrary_types_allowed": True,
        "extra": "forbid",
        "validate_assignment": True,
    }


class RepeatMeasHlaStageParams(HlaStageParams):
    n_meas: int = Field(5, ge=1, description="Number of measurements to acquire")
    wait_btw_meas: Q_ = Field(
        Q_("0.2 s"), ge=Q_("0 s"), description="Wait time between each measurement"
    )
    stats: StatisticsType | Sequence[StatisticsType] = Field(
        (
            StatisticsType.MEAN,
            StatisticsType.STD,
            StatisticsType.MIN,
            StatisticsType.MAX,
        )
    )

    @field_serializer("wait_btw_meas")
    def serialize_pint_quantity(self, value):
        return json_serialize_pint_quantity(value)

    @field_validator("wait_btw_meas", mode="before")
    def deserialize_pint_quantity(cls, value):
        return json_deserialize_pint_quantity(value)

    @field_serializer("stats")
    def serialize_stats(self, value: Sequence[str | StatisticsType]):
        out = []
        for v in value:
            if isinstance(v, StatisticsType):
                out.append(v.value)
            elif isinstance(v, str):
                StatisticsType(v)  # Check if it's a valid str
                out.append(v)
            else:
                raise TypeError

        return out

    @field_validator("stats", mode="before")
    def deserialize_stats(
        cls, value: str | StatisticsType | Sequence[str | StatisticsType]
    ):
        if isinstance(value, str):
            return [StatisticsType(value)]
        elif isinstance(value, StatisticsType):
            return [value]
        else:
            out = []
            for v in value:
                if isinstance(v, StatisticsType):
                    out.append(v)
                elif isinstance(v, str):
                    out.append(StatisticsType(v))
                else:
                    raise TypeError
            return out


class HlaStageBase:
    def __init__(self, machine: Machine | MultiMachine):
        self._machine = machine
        self.params = None

    def run(self):
        raise NotImplementedError("Must implement this for any inherited stage class")

    def get_mlv(self, name: str | MlvName):
        return self._machine.get_mlv(name)

    def get_mlvl(self, name: str | MlvlName):
        return self._machine.get_mlvl(name)

    def get_mlvt(self, name: str | MlvtName):
        return self._machine.get_mlvt(name)

    def get_mlo(self, name: MlvName | MlvlName | MlvtName | str):
        return self._machine.get_mlo(name)

    def ensure_valid_mlo(self, obj: Any, allowed_mlo_types: Type | Tuple[Type, ...]):

        if not _REJECT_MACHINE_DEFAULT:
            return obj

        if isinstance(obj, MachineDefault):
            raise TypeError(
                "Machine default is requested, but it does not appear to be set up"
            )
        elif isinstance(obj, MloName | str):
            mlo_name = obj
            mlo_obj = self.get_mlo(mlo_name)
        elif isinstance(obj, allowed_mlo_types):
            mlo_obj = obj
        else:
            raise TypeError

        return mlo_obj

    def get_params(self):
        return self.params

    def _get_params_access_list(self, module_path: str):
        module_path_tokens = module_path.split(".")
        access_list = [
            KIA(k) for k in module_path_tokens[module_path_tokens.index("hla") + 1 :]
        ]

        return access_list

    def get_machine_default_params(self, module_path: str):

        access_list = self._get_params_access_list(module_path)

        fetcher = ChainedPropertyFetcher(HLA_DEFAULTS[self._machine.name], access_list)

        try:
            params = fetcher.get()
        except KeyError:
            params = {}

        return params

    def update_machine_default_params(self, module_path: str, params: HlaStageParams):

        access_list = self._get_params_access_list(module_path)
        pusher = ChainedPropertyPusher(HLA_DEFAULTS[self._machine.name], access_list)

        pusher.put(params)


class HlaInitialStage(HlaStageBase):
    def __init__(self, machine: Machine | MultiMachine):
        super().__init__(machine)


class HlaStage(HlaStageBase):
    def __init__(self, machine: Machine | MultiMachine):
        super().__init__(machine)
        self._output_from_prev_stage = None

    def take_output_from_prev_stage(self, output_from_prev_stage: Any):
        self._output_from_prev_stage = output_from_prev_stage


def allow_machine_default_placeholder():
    global _REJECT_MACHINE_DEFAULT
    _REJECT_MACHINE_DEFAULT = False


def disallow_machine_default_placeholder():
    global _REJECT_MACHINE_DEFAULT
    _REJECT_MACHINE_DEFAULT = True


def is_machine_default_allowed():
    return not _REJECT_MACHINE_DEFAULT


from . import disp_chrom, orbit, tunes

_HLA_NAME_TO_MODULE = {
    "orbit.slow_acq": orbit.slow_acq,
    "tunes.via_pvs": tunes.via_pvs,
    "disp_chrom": disp_chrom,
}

# from nsls2 import * # for facility override
