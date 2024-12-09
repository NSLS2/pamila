from copy import deepcopy
import json
from pathlib import Path

from ophyd import Component as Cpt
import yaml

from .. import MachineMode, get_machine_mode
from ..device.simple import (
    FixedWaitTime,
    SetpointReadbackDiff,
    SetWaitSpec,
    SimplePamilaDeviceROSpec,
    SimplePamilaDeviceSpec,
)
from ..device.specs import FunctionSpec, PamilaDeviceActionSpec, UnitConvSpec
from ..middle_layer import (
    MiddleLayerVariable,
    MiddleLayerVariableList,
    MiddleLayerVariableListRO,
    MiddleLayerVariableListROSpec,
    MiddleLayerVariableListSpec,
    MiddleLayerVariableRO,
    MiddleLayerVariableSpec,
)
from ..signal import (
    ExternalPamilaSignal,
    ExternalPamilaSignalRO,
    InternalPamilaSignal,
    InternalPamilaSignalRO,
    UserPamilaSignal,
)
from ..sim_interface import (
    PyATInterfaceSpec,
    SimulatorInterfacePath,
    SimulatorPvDefinition,
    _reset_sim_interface,
    get_sim_interface,
    get_sim_pvprefix,
    set_sim_interface_spec,
)


def create_pdev_psig_names(mlv_name, machine_mode):
    match machine_mode:
        case MachineMode.LIVE:
            pdev_prefix = "epdL"  # external pamila device (LIVE)
            psig_prefix = "epsL"  # external pamila signal (LIVE)
        case MachineMode.DIGITAL_TWIN:
            pdev_prefix = "epdD"  # external pamila device (DT)
            psig_prefix = "epsD"  # external pamila signal (DT)
        case MachineMode.SIMULATOR:
            pdev_prefix = "ipd"  # internal pamila device
            psig_prefix = "ips"  # internal pamila signal
        case _:
            raise ValueError

    pdev_name = f"{pdev_prefix}_{mlv_name}"
    LoLv_psig_name = f"{psig_prefix}_{mlv_name}"

    return pdev_name, LoLv_psig_name


def get_unitconv(elem_def, in_reprs, out_reprs):
    if in_reprs == out_reprs:
        func_spec = None  # identity unit conversion
    else:
        func_spec = None
        for _spec in elem_def["func_specs"]:
            if _spec["out_reprs"] != out_reprs:
                continue
            if _spec["in_reprs"] != in_reprs:
                continue
            func_spec = _spec["func_spec"]
            break
        else:
            raise ValueError("Could not find unit conversion")

    if func_spec is None:
        unitconv = None
    else:
        unitconv = UnitConvSpec(
            src_units=[elem_def["repr_units"][repr] for repr in in_reprs],
            dst_units=[elem_def["repr_units"][repr] for repr in out_reprs],
            func_spec=FunctionSpec(**func_spec),
        )

    return unitconv


def get_pvids_in_elem(ch_def):
    pvids_in_elem_d = {}

    for ext_or_int in ["ext", "int"]:
        if ext_or_int in ch_def["pvs"]:
            pvids = ch_def["pvs"][ext_or_int]
            match len(pvids):
                case 0:
                    raise RuntimeError
                case _:
                    pvids_in_elem_d[ext_or_int] = pvids

    return pvids_in_elem_d


def get_defined_machine_modes(ch_def, elem_name_pvid_to_pvinfo, elem_name):

    pvids_in_elem_d = get_pvids_in_elem(ch_def)

    machine_mode_list = []

    if "ext" in pvids_in_elem_d:
        extpv_name_d_list = [
            elem_name_pvid_to_pvinfo["ext"][(elem_name, pvid_in_elem)]["pvname"]
            for pvid_in_elem in pvids_in_elem_d["ext"]
        ]
        if all([MachineMode.LIVE.value in _d for _d in extpv_name_d_list]):
            machine_mode_list.append(MachineMode.LIVE)
        if all([MachineMode.DIGITAL_TWIN.value in _d for _d in extpv_name_d_list]):
            machine_mode_list.append(MachineMode.DIGITAL_TWIN)

    if "int" in pvids_in_elem_d:
        machine_mode_list.append(MachineMode.SIMULATOR)

    return machine_mode_list


def get_ext_or_int(machine_mode: MachineMode):
    if machine_mode in (MachineMode.LIVE, MachineMode.DIGITAL_TWIN):
        ext_or_int = "ext"
    else:
        ext_or_int = "int"
    return ext_or_int


def _get_pvinfo_list(ch_def, elem_name_pvid_to_pvinfo, elem_name, machine_mode):

    ext_or_int = get_ext_or_int(machine_mode)

    pvids_in_elem_d = get_pvids_in_elem(ch_def)

    info_list = [
        elem_name_pvid_to_pvinfo[ext_or_int][(elem_name, pvid_in_elem)]
        for pvid_in_elem in pvids_in_elem_d[ext_or_int]
    ]

    return ext_or_int, info_list


def get_pvnames(ch_def, elem_name_pvid_to_pvinfo, elem_name, machine_mode):

    ext_or_int, info_list = _get_pvinfo_list(
        ch_def, elem_name_pvid_to_pvinfo, elem_name, machine_mode
    )

    if ext_or_int == "ext":
        pvname_list = [info["pvname"][machine_mode.value] for info in info_list]
    else:
        pvname_list = []
        for info in info_list:
            pvsuffix = info["pvsuffix"]
            pvprefix = get_sim_pvprefix(machine_mode)
            pvname = f"{pvprefix}{pvsuffix}"
            pvname_list.append(pvname)

    return pvname_list


def get_pvunits(ch_def, elem_name_pvid_to_pvinfo, elem_name, machine_mode):

    ext_or_int, info_list = _get_pvinfo_list(
        ch_def, elem_name_pvid_to_pvinfo, elem_name, machine_mode
    )

    if ext_or_int == "ext":
        pvunit_list = [info["pvunit"][machine_mode.value] for info in info_list]
    else:
        pvunit_list = [info["pvunit"] for info in info_list]

    return pvunit_list


def _get_standard_RB_components(
    machine_mode: MachineMode,
    LoLv_psig_name: str,
    HiLv_psig_name: str,
    elem_def,
    ch_def,
    elem_name_pvid_to_pvinfo,
    elem_name,
    simulator_interface_path,
):

    assert ch_def["handle"] == "RB"

    match get_ext_or_int(machine_mode):
        case "ext":
            LoLv_sig_class = ExternalPamilaSignalRO
            LoLv_cpt_kwargs = {}
        case "int":
            LoLv_sig_class = InternalPamilaSignalRO
            LoLv_cpt_kwargs = dict(simulator_interface_path=simulator_interface_path)
        case _:
            raise ValueError

    _LoLv_pv_units = get_pvunits(
        ch_def, elem_name_pvid_to_pvinfo, elem_name, machine_mode
    )
    assert len(_LoLv_pv_units) == 1
    LoLv_pv_unit = _LoLv_pv_units[0]
    # ^ Note that "LoLv_pv_unit == elem_def['repr_units'][in_reprs[0]]" may NOT
    # necessarily hold. But their dimension must be the same.
    out_reprs = ch_def["reprs"]
    mlv_unit = elem_def["repr_units"][out_reprs[0]]

    _pvnames = get_pvnames(ch_def, elem_name_pvid_to_pvinfo, elem_name, machine_mode)
    assert len(_pvnames) == 1
    pvname = _pvnames[0]

    components = {
        "RB_LoLv": Cpt(
            LoLv_sig_class,
            pvname,
            mode=machine_mode,
            name=LoLv_psig_name,
            unit=LoLv_pv_unit,
            **LoLv_cpt_kwargs,
        ),
        "RB": Cpt(
            UserPamilaSignal,
            mode=machine_mode,
            name=HiLv_psig_name,
            unit=mlv_unit,
        ),
    }

    return components


def _get_standard_RB_pdev_action_specs(elem_def, ch_def, ext_or_int):

    in_reprs = [
        elem_def["pvid_to_repr_map"][ext_or_int][pvid]
        for pvid in ch_def["pvs"][ext_or_int]
    ]
    out_reprs = ch_def["reprs"]
    unitconv = get_unitconv(elem_def, in_reprs, out_reprs)

    get_spec = PamilaDeviceActionSpec(
        input_cpt_attr_names=["RB_LoLv"],
        output_cpt_attr_names=["RB"],
        unitconv=unitconv,
    )

    return dict(get=get_spec)


def get_standard_RB_pdev_spec(
    mlv_name: str,
    machine_name: str,
    machine_mode: MachineMode,
    elem_def,
    ch_def,
    elem_name_pvid_to_pvinfo,
    elem_name,
    simulator_interface_path,
):

    pdev_name, LoLv_psig_name = create_pdev_psig_names(mlv_name, machine_mode)

    HiLv_psig_name = f"{LoLv_psig_name}_HiLv"

    components = _get_standard_RB_components(
        machine_mode,
        LoLv_psig_name,
        HiLv_psig_name,
        elem_def,
        ch_def,
        elem_name_pvid_to_pvinfo,
        elem_name,
        simulator_interface_path,
    )

    ext_or_int = get_ext_or_int(machine_mode)
    action_specs = _get_standard_RB_pdev_action_specs(elem_def, ch_def, ext_or_int)

    simple_pdev_spec = SimplePamilaDeviceROSpec(
        pdev_name=pdev_name,
        machine_name=machine_name,
        machine_mode=machine_mode,
        read_only=True,
        components=components,
        get_spec=action_specs["get"],
    )

    return simple_pdev_spec


def _get_standard_SP_components(
    machine_mode: MachineMode,
    LoLv_psig_name: str,
    elem_def,
    ch_def,
    elem_name_pvid_to_pvinfo,
    elem_name,
    simulator_interface_path,
    mode_pdev_def,
):
    assert ch_def["handle"] == "SP"

    match get_ext_or_int(machine_mode):
        case "ext":
            LoLv_sig_class = ExternalPamilaSignal
            LoLv_cpt_kwargs = {}
        case "int":
            LoLv_sig_class = InternalPamilaSignal
            LoLv_cpt_kwargs = dict(simulator_interface_path=simulator_interface_path)
        case _:
            raise ValueError

    _LoLv_pv_units = get_pvunits(
        ch_def, elem_name_pvid_to_pvinfo, elem_name, machine_mode
    )
    assert len(_LoLv_pv_units) == 1
    LoLv_pv_unit = _LoLv_pv_units[0]
    # ^ Note that "LoLv_pv_unit == elem_def['repr_units'][in_reprs[0]]" may NOT
    # necessarily hold. But their dimension must be the same.
    out_reprs = ch_def["reprs"]
    mlv_unit = elem_def["repr_units"][out_reprs[0]]

    _SP_pvnames = get_pvnames(ch_def, elem_name_pvid_to_pvinfo, elem_name, machine_mode)
    assert len(_SP_pvnames) == 1
    SP_pvname = _SP_pvnames[0]

    components = {
        "SP_LoLv": Cpt(
            LoLv_sig_class,
            SP_pvname,
            mode=machine_mode,
            name=LoLv_psig_name,
            unit=LoLv_pv_unit,
            **LoLv_cpt_kwargs,
        ),
        "SP": Cpt(
            UserPamilaSignal,
            mode=machine_mode,
            name=f"{LoLv_psig_name}_get_HiLv",
            unit=mlv_unit,
        ),
        "SP_put_input": Cpt(
            UserPamilaSignal,
            mode=machine_mode,
            name=f"{LoLv_psig_name}_put_HiLv",
            unit=mlv_unit,
        ),
    }

    SP_RB_diff = mode_pdev_def.get("SP_RB_diff", {})

    if SP_RB_diff:
        RB_ch_def = elem_def["channel_map"][SP_RB_diff["RB_channel"]]
        RB_LoLv_psig_name = f"{LoLv_psig_name}_RB"
        RB_HiLv_psig_name = f"{RB_LoLv_psig_name}_HiLv"
        RB_components = _get_standard_RB_components(
            machine_mode,
            RB_LoLv_psig_name,
            RB_HiLv_psig_name,
            elem_def,
            RB_ch_def,
            elem_name_pvid_to_pvinfo,
            elem_name,
            simulator_interface_path,
        )

        components["RB_LoLv"] = RB_components["RB_LoLv"]
        components["RB"] = RB_components["RB"]

    return components


def _get_SP_pdev_action_specs(elem_def, ch_def, ext_or_int, mode_pdev_def):

    LoLv_reprs = [
        elem_def["pvid_to_repr_map"][ext_or_int][pvid]
        for pvid in ch_def["pvs"][ext_or_int]
    ]
    HiLv_reprs = ch_def["reprs"]

    in_reprs = LoLv_reprs
    out_reprs = HiLv_reprs

    get_spec = PamilaDeviceActionSpec(
        input_cpt_attr_names=["SP_LoLv"],
        output_cpt_attr_names=["SP"],
        unitconv=get_unitconv(elem_def, in_reprs, out_reprs),
    )

    in_reprs = HiLv_reprs
    out_reprs = LoLv_reprs

    put_spec = PamilaDeviceActionSpec(
        input_cpt_attr_names=["SP_put_input"],
        output_cpt_attr_names=["SP_LoLv"],
        unitconv=get_unitconv(elem_def, in_reprs, out_reprs),
    )

    specs = dict(get=get_spec, put=put_spec)

    SP_RB_diff = mode_pdev_def.get("SP_RB_diff", {})
    if SP_RB_diff:
        RB_ch_def = elem_def["channel_map"][SP_RB_diff["RB_channel"]]

        LoLv_reprs = [
            elem_def["pvid_to_repr_map"][ext_or_int][pvid]
            for pvid in RB_ch_def["pvs"][ext_or_int]
        ]
        HiLv_reprs = RB_ch_def["reprs"]

        in_reprs = LoLv_reprs
        out_reprs = HiLv_reprs

        specs["readback_in_set"] = PamilaDeviceActionSpec(
            input_cpt_attr_names=["RB_LoLv"],
            output_cpt_attr_names=["RB"],
            unitconv=get_unitconv(elem_def, in_reprs, out_reprs),
        )

    return specs


def get_standard_SP_pdev_spec(
    mlv_name: str,
    machine_name: str,
    machine_mode: MachineMode,
    elem_def,
    ch_def,
    elem_name_pvid_to_pvinfo,
    elem_name,
    simulator_interface_path,
    mode_pdev_def,
):

    pdev_name, LoLv_psig_name = create_pdev_psig_names(mlv_name, machine_mode)

    components = _get_standard_SP_components(
        machine_mode,
        LoLv_psig_name,
        elem_def,
        ch_def,
        elem_name_pvid_to_pvinfo,
        elem_name,
        simulator_interface_path,
        mode_pdev_def,
    )

    ext_or_int = get_ext_or_int(machine_mode)
    action_specs = _get_SP_pdev_action_specs(
        elem_def, ch_def, ext_or_int, mode_pdev_def
    )

    fixed_wait_time_d = mode_pdev_def.get("fixed_wait_time", None)
    if fixed_wait_time_d:
        fixed_wait_time = FixedWaitTime(**fixed_wait_time_d)
    else:
        fixed_wait_time = None

    SP_RB_diff_d = mode_pdev_def.get("SP_RB_diff", None)
    if SP_RB_diff_d:
        SP_RB_diff_d["RB_attr_name"] = "RB"
        del SP_RB_diff_d["RB_channel"]
        SP_RB_diff = SetpointReadbackDiff(**SP_RB_diff_d)
    else:
        SP_RB_diff = None

    simple_pdev_spec = SimplePamilaDeviceSpec(
        pdev_name=pdev_name,
        machine_name=machine_name,
        machine_mode=machine_mode,
        read_only=False,
        components=components,
        get_spec=action_specs["get"],
        put_spec=action_specs["put"],
        readback_in_set=action_specs.get("readback_in_set", None),
        set_wait_spec=SetWaitSpec(
            fixed_wait_time=fixed_wait_time, SP_RB_diff=SP_RB_diff
        ),
        set_wait_method=mode_pdev_def.get("set_wait_method", "fixed_wait_time"),
    )

    return simple_pdev_spec


class MachineConfig:
    def __init__(self, machine_name: str, dirpath: Path):

        self.dirpath = dirpath
        self.machine_name = machine_name

        machine_folder = dirpath / machine_name

        self.sim_configs = yaml.safe_load(
            (machine_folder / "sim_configs.yaml").read_text()
        )
        self.sel_config = self.sim_configs["selected_config"]
        self.sim_conf_d = self.sim_configs["simulator_configs"][self.sel_config]

        self.config_folder = machine_folder / self.sel_config

        self._load_definitions_from_files()
        self._load_lattice_design_props_from_files()

        self._set_sim_interface_spec()

        _reset_sim_interface(machine_name)  # Necessary when reloading the machine
        # to clear out previously loaded simulators.

        self._construct_mlvs()
        # MLVLs and MLVTs will be constructed once Machine() initialization is
        # completed.

        self._non_serializable_attrs = []

    def __getstate__(self):

        state = self.__dict__.copy()

        # Exclude the non-serializable attributes
        for attr in self._non_serializable_attrs:
            del state[attr]

        return state

    def __setstate__(self, state):
        self.__dict__.update(state)

    def _load_definitions_from_files(self):
        self.sim_pv_defs = json.loads((self.config_folder / "sim_pvs.json").read_text())

        self.simpv_elem_maps = json.loads(
            (self.config_folder / "simpv_elem_maps.json").read_text()
        )

        self.pv_elem_maps = json.loads(
            (self.config_folder / "pv_elem_maps.json").read_text()
        )

        self.elem_defs = json.loads((self.config_folder / "elements.json").read_text())

        fp = self.config_folder / "mlvls.yaml"
        if fp.exists():
            self.mlvl_defs = yaml.safe_load(fp.read_text())
        else:
            self.mlvl_defs = None

        fp = self.config_folder / "mlvts.yaml"
        if fp.exists():
            self.mlvt_defs = yaml.safe_load(fp.read_text())
        else:
            self.mlvt_defs = None

        self.elem_name_pvid_to_pvinfo = dict(ext={}, int={})

        pv_elem_maps = self.pv_elem_maps["pv_elem_maps"]
        elem_name_pvid_to_pvinfo = self.elem_name_pvid_to_pvinfo["ext"]

        for pvname, d in pv_elem_maps.items():
            for elem_name in d["elem_names"]:
                k = (elem_name, d["pvid_in_elem"])
                assert k not in elem_name_pvid_to_pvinfo
                elem_name_pvid_to_pvinfo[k] = {
                    "handle": d["handle"],
                    "pvname": dict(LIVE=pvname, DT=d.get("DT_pvname", None)),
                    "pvunit": dict(LIVE=d["pvunit"], DT=d.get("DT_pvunit", None)),
                }

        simpv_elem_maps = self.simpv_elem_maps["simpv_elem_maps"]
        elem_name_pvid_to_pvinfo = self.elem_name_pvid_to_pvinfo["int"]

        for pvsuffix, d in simpv_elem_maps.items():

            k = (d["elem_name"], d["pvid_in_elem"])
            assert k not in elem_name_pvid_to_pvinfo
            elem_name_pvid_to_pvinfo[k] = {
                "handles": d["handles"],
                "pvsuffix": pvsuffix,
                "pvunit": d["pvunit"],
            }

    def _load_lattice_design_props_from_files(self):

        self.design_lat_props = json.loads(
            (self.config_folder / "design_props.json").read_text()
        )

    def _set_sim_interface_spec(self):

        match self.sim_conf_d["package_name"]:
            case "pyat":
                sim_pv_defs = {}
                for d in self.sim_pv_defs["sim_pv_definitions"]:
                    pvsuffix = d["pvsuffix"]
                    assert pvsuffix not in sim_pv_defs
                    sim_pv_defs[pvsuffix] = SimulatorPvDefinition(
                        **{k: v for k, v in d.items() if k != "pvsuffix"}
                    )
                self.sim_itf_spec = PyATInterfaceSpec(
                    sim_pv_defs=sim_pv_defs, **self.sim_conf_d
                )
            case "no_simulator":
                self.sim_itf_spec = None
            case _:
                raise NotImplementedError

        set_sim_interface_spec(self.machine_name, self.sim_itf_spec)

        self.sim_itf_paths = {}

    def _get_sim_interface_path(self, machine_mode: MachineMode):

        itf_path = self.sim_itf_paths.get(machine_mode, None)
        if itf_path is None:
            itf_path = SimulatorInterfacePath(
                machine_name=self.machine_name, machine_mode=machine_mode
            )
            self.sim_itf_paths[machine_mode] = itf_path

        return itf_path

    def get_sim_interface(self):

        machine_mode = get_machine_mode()

        itf_path = self._get_sim_interface_path(machine_mode)

        return get_sim_interface(itf_path)

    def _construct_mlvs(self):

        elem_name_pvid_to_pvinfo = self.elem_name_pvid_to_pvinfo

        for elem_name, e_def in self.elem_defs["elem_definitions"].items():
            for ch_name, ch_def in e_def["channel_map"].items():
                mlv_name = f"{elem_name}_{ch_name}"

                match ch_def["handle"]:
                    case "RB":
                        read_only = True
                        mlv_class = MiddleLayerVariableRO
                    case "SP":
                        read_only = False
                        mlv_class = MiddleLayerVariable
                    case _:
                        raise ValueError

                pdev_def = ch_def["pdev_def"]

                pdev_specs = {}

                for machine_mode in get_defined_machine_modes(
                    ch_def, elem_name_pvid_to_pvinfo, elem_name
                ):

                    if get_ext_or_int(machine_mode) == "int":
                        sim_itf_path = self._get_sim_interface_path(machine_mode)
                    else:
                        sim_itf_path = None

                    mode_pdev_def = deepcopy(pdev_def.get(machine_mode.value, {}))
                    mode_pdev_def_type = mode_pdev_def.pop("type", "standard_RB")

                    if read_only:
                        match mode_pdev_def_type:
                            case "standard_RB":
                                pdev_spec = get_standard_RB_pdev_spec(
                                    mlv_name,
                                    self.machine_name,
                                    machine_mode,
                                    e_def,
                                    ch_def,
                                    elem_name_pvid_to_pvinfo,
                                    elem_name,
                                    sim_itf_path,
                                )
                            case "plugin":
                                raise NotImplementedError

                            case _:
                                raise NotImplementedError

                    else:
                        match mode_pdev_def_type:
                            case "standard_SP":
                                pdev_spec = get_standard_SP_pdev_spec(
                                    mlv_name,
                                    self.machine_name,
                                    machine_mode,
                                    e_def,
                                    ch_def,
                                    elem_name_pvid_to_pvinfo,
                                    elem_name,
                                    sim_itf_path,
                                    mode_pdev_def,
                                )
                            case _:
                                raise NotImplementedError

                    pdev_specs[machine_mode] = pdev_spec

                mlv_spec = MiddleLayerVariableSpec(
                    name=mlv_name,
                    machine_name=self.machine_name,
                    simulator_config=self.sel_config,
                    pdev_spec_dict=pdev_specs,
                )
                mlv_class(mlv_spec)
