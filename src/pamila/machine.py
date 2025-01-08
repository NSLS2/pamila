import gzip
import json
import os
from pathlib import Path
import pickle
from typing import Dict, List, Literal

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
    DatabaseDict,
    MiddleLayerVariableList,
    MiddleLayerVariableListRO,
    MiddleLayerVariableListROSpec,
    MiddleLayerVariableListSpec,
    MiddleLayerVariableTree,
    MiddleLayerVariableTreeSpec,
    MlvlName,
    MlvName,
    MlvtName,
    _get_machine_db,
    _set_machine_db,
    get_all_elems,
    get_all_mlv_key_value_tags,
    get_all_mlv_value_tags,
    get_all_mlvls,
    get_all_mlvs,
    get_all_mlvts,
    get_elems_via_key_value_tags,
    get_elems_via_name,
    get_elems_via_value_tag,
    get_mlvs_via_key_value_tags,
    get_mlvs_via_name,
    get_mlvs_via_value_tag,
)
from .utils import KeyValueTagSearch

_MACHINES = {}


class Machine:
    """ """

    def __init__(
        self,
        machine_name: str,
        dirpath: str | Path | None = None,
        model_name: str = "",
        cache_filepath: str | Path | None = None,
    ):
        self.name = machine_name

        if dirpath is None:
            load_from_cache = True
            if cache_filepath is None:
                raise ValueError(
                    "Either `dirpath` or `cache_filepath` must be specified"
                )
            elif isinstance(cache_filepath, str):
                cache_filepath = Path(cache_filepath)
            else:
                assert isinstance(cache_filepath, Path)
            assert cache_filepath.exists()
        else:
            load_from_cache = False
            if isinstance(dirpath, str):
                dirpath = Path(dirpath)
            else:
                assert isinstance(dirpath, Path)
            assert dirpath.exists()

        if load_from_cache:
            if model_name:
                raise NotImplementedError

            with gzip.GzipFile(cache_filepath, "rb") as f:
                cached_machine_obj = pickle.load(f)
                cached_db = pickle.load(f)

            assert cached_machine_obj.name == self.name

            self._conf = cached_machine_obj._conf
            self._conf._update_from_cache()
            self._set_db(cached_db)
        else:
            self._conf = MachineConfig(machine_name, dirpath, model_name=model_name)

        self._control_system = self._conf.sim_configs.control_system

    def save_to_cache_file(self, cache_filepath: str | Path):

        if isinstance(cache_filepath, str):
            cache_filepath = Path(cache_filepath)

        with gzip.GzipFile(cache_filepath, "wb") as f:
            pickle.dump(self, f)
            pickle.dump(self._get_db(), f)

    def get_design_lattice_props(self):
        return self._conf.get_design_lattice_props()

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

    def _get_db(self):
        return _get_machine_db(self.name)

    def _set_db(self, db: DatabaseDict):
        return _set_machine_db(self.name, db)

    def get_all_elems(self):
        return get_all_elems(self.name)

    def get_all_mlvs(self):
        return get_all_mlvs(self.name)

    def get_all_mlvls(self):
        return get_all_mlvls(self.name)

    def get_all_mlvts(self):
        return get_all_mlvts(self.name)

    def get_all_mlv_value_tags(self):
        return get_all_mlv_value_tags(self.name)

    def get_all_mlv_key_value_tags(self):
        return get_all_mlv_key_value_tags(self.name)

    def get_mlvs_via_name(
        self,
        mlv_name: str,
        search_type: Literal["exact", "fnmatch", "regex", "regex/i"] = "fnmatch",
    ):
        return get_mlvs_via_name(self.name, mlv_name, search_type=search_type)

    def get_mlvs_via_value_tag(
        self,
        value_tag: str,
        search_type: Literal["exact", "fnmatch", "regex", "regex/i"] = "fnmatch",
    ):
        return get_mlvs_via_value_tag(self.name, value_tag, search_type=search_type)

    def get_mlvs_via_key_value_tags(self, tag_searches: List[KeyValueTagSearch]):
        return get_mlvs_via_key_value_tags(self.name, tag_searches)

    def get_elems_via_name(
        self,
        elem_name: str,
        search_type: Literal["exact", "fnmatch", "regex", "regex/i"] = "fnmatch",
    ):
        return get_elems_via_name(self.name, elem_name, search_type=search_type)

    def get_elems_via_value_tag(
        self,
        value_tag: str,
        search_type: Literal["exact", "fnmatch", "regex", "regex/i"] = "fnmatch",
    ):
        return get_elems_via_value_tag(self.name, value_tag, search_type=search_type)

    def get_elems_via_key_value_tags(self, tag_searches: List[KeyValueTagSearch]):
        return get_elems_via_key_value_tags(self.name, tag_searches)

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

    def add_to_simpv_definitions(self, new_entry: Dict):
        copy = json.loads(json.dumps(new_entry))
        self._conf.sim_pv_defs["sim_pv_definitions"].append(copy)
        self._conf._add_sim_pv_def(copy)

    def add_to_pv_elem_maps(self, pvname: str, new_entry: Dict):
        d = self._conf.pv_elem_maps["pv_elem_maps"]
        assert pvname not in d
        copy = json.loads(json.dumps(new_entry))
        d[pvname] = copy

        self._conf._update_elem_name_pvid_to_pvinfo_ext()

    def add_to_simpv_elem_maps(self, pvsuffix: str, new_entry: Dict):
        d = self._conf.simpv_elem_maps["simpv_elem_maps"]
        assert pvsuffix not in d
        copy = json.loads(json.dumps(new_entry))
        d[pvsuffix] = copy

        self._conf._update_elem_name_pvid_to_pvinfo_int()

    def add_to_elem_definitions(self, elem_name: str, new_entry: Dict):
        d = self._conf.elem_defs["elem_definitions"]
        assert elem_name not in d
        copy = json.loads(json.dumps(new_entry))
        d[elem_name] = copy

    def replace_elem_definition(self, elem_name: str, new_entry: Dict):
        d = self._conf.elem_defs["elem_definitions"]
        assert elem_name in d
        copy = json.loads(json.dumps(new_entry))
        d[elem_name] = copy

    def construct_mlvs_for_one_element(self, elem_name: str, exist_ok: bool = False):
        d = self._conf.elem_defs["elem_definitions"]
        self._conf._construct_mlvs_for_one_elem(
            elem_name, d[elem_name], exist_ok=exist_ok
        )


class MultiMachine(BaseModel):
    machines: Dict[str, Machine]

    model_config = {"arbitrary_types_allowed": True, "extra": "forbid"}


def get_machine(machine_name: str):
    return _MACHINES[machine_name]


def load_machine(
    machine_name: str, dirpath: str | Path | None = None, model_name: str = ""
):

    if dirpath is None:
        raise NotImplementedError

    get_all_elems(machine_name).clear()
    get_all_mlvs(machine_name).clear()
    get_all_mlvls(machine_name).clear()
    get_all_mlvts(machine_name).clear()

    machine = Machine(machine_name, dirpath=dirpath, model_name=model_name)

    machine._construct_mlvls()
    machine._construct_mlvts()

    _MACHINES[machine_name] = machine

    from .hla import HLA_DEFAULTS

    HLA_DEFAULTS[machine_name] = {}

    return machine


def load_cached_machine(machine_name: str, cache_filepath: str | Path):
    machine = Machine(machine_name, cache_filepath=cache_filepath)

    _MACHINES[machine_name] = machine

    from .hla import HLA_DEFAULTS

    HLA_DEFAULTS[machine_name] = {}

    return machine
