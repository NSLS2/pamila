import json
import os
from pathlib import Path
from typing import Dict

_facility_name = os.environ.get("PAMILA_FACILITY", "")

if _facility_name == "":
    raise RuntimeError(
        "Must specify failicty name in environment variable 'PAMILA_FACILITY'"
    )


def get_facility_name():
    return _facility_name


from pydantic import BaseModel

from .facility_configs.loader import MachineConfig
from .middle_layer import (
    MiddleLayerVariableList,
    MiddleLayerVariableListRO,
    MiddleLayerVariableListROSpec,
    MiddleLayerVariableListSpec,
    MiddleLayerVariableTree,
    MiddleLayerVariableTreeSpec,
    MlvlName,
    MlvName,
    MlvtName,
    get_all_mlvls,
    get_all_mlvs,
    get_all_mlvts,
)

_MACHINES = {}


class Machine:
    """ """

    def __init__(self, machine_name: str, dirpath: Path):
        self.name = machine_name

        self._conf = MachineConfig(machine_name, dirpath)

    def get_sim_interface(self):
        # self = _MACHINES[machine_name]
        # Path to sim. itf. obj := self._conf.sim_itf_path
        # sim. itf. obj. := self._conf.sim_itfs[machine_mode]
        return self._conf.get_sim_interface()

    def _construct_mlvls(self):
        if self._conf.mlvl_defs is None:
            print(
                "MLVL definitions have not been specified. No MLVL will be instantiated."
            )
            return

        mlvl_defs = self._conf.mlvl_defs["mlvl_definitions"]
        for mlvl_name, l_def in mlvl_defs.items():
            l_def = json.loads(json.dumps(l_def))  # make a deep copy
            class_suffix = l_def.pop("class_suffix")
            match class_suffix:
                case "List":
                    class_ = MiddleLayerVariableList
                    class_spec = MiddleLayerVariableListSpec
                case "ListRO":
                    class_ = MiddleLayerVariableListRO
                    class_spec = MiddleLayerVariableListROSpec
                case _:
                    raise NotImplementedError

            mlvs = [self.get_mlv(mlv_name) for mlv_name in l_def["mlvs"]]
            l_def["mlvs"] = mlvs
            spec = class_spec(name=mlvl_name, **l_def)  # Instantiate the MLVL spec
            class_(spec)  # Instantiate the MLVL object

    def _construct_mlvts(self):
        if self._conf.mlvt_defs is None:
            print(
                "MLVT definitions have not been specified. No MLVT will be instantiated."
            )
            return

        mlvt_defs = self._conf.mlvt_defs["mlvt_definitions"]
        for mlvt_name, t_def in mlvt_defs.items():
            t_def = json.loads(json.dumps(t_def))  # make a deep copy

            mlos = {}
            for k, d in t_def["mlos"].items():
                class_suffix = d.pop("class_suffix")
                match class_suffix:
                    case "List" | "ListRO":
                        mlo = self.get_mlvl(d["name"])
                    case "Tree":
                        mlo = self.get_mlvt(d["name"])
                    case _:
                        raise NotImplementedError
                mlos[k] = mlo

            t_def["mlos"] = mlos

            # Instantiate the MLVT spec
            spec = MiddleLayerVariableTreeSpec(name=mlvt_name, **t_def)

            # Instantiate the MLVT object
            MiddleLayerVariableTree(spec)

    def get_all_mlvs(self):
        return get_all_mlvs(self.name)

    def get_all_mlvls(self):
        return get_all_mlvls(self.name)

    def get_all_mlvts(self):
        return get_all_mlvts(self.name)

    def get_mlv(self, name: str | MlvName):
        if isinstance(name, MlvName):
            return name.get_mlo(self.name)
        elif isinstance(name, str):
            return self.get_all_mlvs()[name]
        else:
            raise TypeError

    def get_mlvl(self, name: str | MlvlName):
        if isinstance(name, MlvlName):
            return name.get_mlo(self.name)
        elif isinstance(name, str):
            return self.get_all_mlvls()[name]
        else:
            raise TypeError

    def get_mlvt(self, name: str | MlvtName):
        if isinstance(name, MlvtName):
            return name.get_mlo(self.name)
        elif isinstance(name, str):
            return self.get_all_mlvts()[name]
        else:
            raise TypeError

    def get_mlo(self, name: MlvName | MlvlName | MlvtName | str):
        if isinstance(name, MlvName):
            mlo = self.get_mlv(name)
        elif isinstance(name, MlvlName):
            mlo = self.get_mlvl(name)
        elif isinstance(name, MlvtName):
            mlo = self.get_mlvt(name)
        elif isinstance(name, str):
            for method in [self.get_mlvt, self.get_mlvl, self.get_mlv]:
                try:
                    mlo = method(name)
                    break
                except KeyError:
                    pass
            else:
                raise ValueError(f"No MLO name '{name}' exists")
        else:
            raise TypeError

        return mlo


class MultiMachine(BaseModel):
    machines: Dict[str, Machine]

    model_config = {"arbitrary_types_allowed": True, "extra": "forbid"}


def get_machine(machine_name: str):
    return _MACHINES[machine_name]


def load_machine(machine_name: str, dirpath: str | Path | None = None):

    if dirpath is None:
        raise NotImplementedError

    get_all_mlvs(machine_name).clear()
    get_all_mlvls(machine_name).clear()
    get_all_mlvts(machine_name).clear()

    machine = Machine(machine_name, dirpath)

    machine._construct_mlvls()
    machine._construct_mlvts()

    _MACHINES[machine_name] = machine

    from .hla import HLA_DEFAULTS

    HLA_DEFAULTS[machine_name] = {}

    return machine
