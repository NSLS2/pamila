from copy import deepcopy
import json
from pathlib import Path
import re
from typing import Dict, List, Literal

from ophyd import Component as Cpt
import yaml

from .. import MachineMode, get_machine_mode
from ..device.conversion.plugin_manager import load_plugins
from ..device.simple import (
    FixedWaitTime,
    SetpointReadbackDiff,
    SetWaitSpec,
    SimplePamilaDeviceROSpec,
    SimplePamilaDeviceSpec,
)
from ..device.specs import FunctionSpec, PamilaDeviceActionSpec, UnitConvSpec
from ..middle_layer import (
    Element,
    ElementSpec,
    MiddleLayerVariable,
    MiddleLayerVariableRO,
    MiddleLayerVariableSpec,
)
from ..signal import (
    ExternalPamilaEpicsSignal,
    ExternalPamilaEpicsSignalRO,
    InternalPamilaSignal,
    InternalPamilaSignalRO,
    UserPamilaSignal,
)
from ..sim_interface import (
    PyATInterfaceSpec,
    SimConfigs,
    SimulatorInterfacePath,
    SimulatorPvDefinition,
    _reset_sim_interface,
    get_sim_interface,
    get_sim_pvprefix,
    set_sim_interface_spec,
)
from ..utils import KeyValueTagList
from .generator import StandardSetpointDeviceDefinition

ExternalPamilaSignals = {
    "epics": {
        "Signal": ExternalPamilaEpicsSignal,
        "SignalRO": ExternalPamilaEpicsSignalRO,
    }
}
if False:
    # ExternalPamilaTangoSignal & ExternalPamilaTangoSignalRO
    # currently do not exist. To be implemented.
    ExternalPamilaSignals["tango"] = {
        "Signal": ExternalPamilaTangoSignal,
        "SignalRO": ExternalPamilaTangoSignalRO,
    }


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
    psig_name_prefix = f"{psig_prefix}_{mlv_name}"

    return pdev_name, psig_name_prefix


def get_unitconv(
    elem_def: Dict,
    in_reprs: List[str],
    out_reprs: List[str],
    conv_spec_name: str | None,
):

    if conv_spec_name in (None, "identity"):
        func_spec = dict(name="identity")  # identity unit conversion
    else:
        func_spec = elem_def["func_specs"][conv_spec_name]

    func_spec_obj = FunctionSpec(**func_spec)

    src_units = [elem_def["repr_units"][repr] for repr in in_reprs]
    dst_units = [elem_def["repr_units"][repr] for repr in out_reprs]

    unitconv_spec_obj = UnitConvSpec(
        src_units=src_units,
        dst_units=dst_units,
        func_spec=func_spec_obj,
    )

    return unitconv_spec_obj


def get_pvids_in_elem(ch_def):
    pvids_in_elem_d = {}

    for ext_or_int in ["ext", "int"]:
        if ext_or_int not in ch_def:
            continue

        pvids_in_elem_d[ext_or_int] = {}
        if "get" in ch_def[ext_or_int]:
            pvids_in_elem_d[ext_or_int]["get"] = ch_def[ext_or_int]["get"]["input_pvs"]
        if "put" in ch_def[ext_or_int]:
            pvids_in_elem_d[ext_or_int]["put"] = ch_def[ext_or_int]["put"]["output_pvs"]

    return pvids_in_elem_d


def get_aux_pvids_in_elem(ch_def):
    pvids_in_elem_d = {}

    for ext_or_int in ["ext", "int"]:
        if ext_or_int not in ch_def:
            continue

        pvids_in_elem_d[ext_or_int] = {}
        if "put" in ch_def[ext_or_int]:
            if "aux_input_pvs" in ch_def[ext_or_int]["put"]:
                pvids_in_elem_d[ext_or_int] = ch_def[ext_or_int]["put"]["aux_input_pvs"]

    return pvids_in_elem_d


def get_ext_or_int(machine_mode: MachineMode):
    if machine_mode in (MachineMode.LIVE, MachineMode.DIGITAL_TWIN):
        ext_or_int = "ext"
    else:
        ext_or_int = "int"
    return ext_or_int


def _get_pvinfo_dict(ch_def, elem_name_pvid_to_pvinfo, elem_name, machine_mode):

    ext_or_int = get_ext_or_int(machine_mode)

    pvids_in_elem_d = get_pvids_in_elem(ch_def)

    info_list_d = {}
    for get_or_put, pvid_list_in_elem in pvids_in_elem_d[ext_or_int].items():
        info_list_d[get_or_put] = [
            elem_name_pvid_to_pvinfo[ext_or_int][(elem_name, pvid_in_elem)]
            for pvid_in_elem in pvid_list_in_elem
        ]

    return ext_or_int, info_list_d


def get_pvnames(ch_def, elem_name_pvid_to_pvinfo, elem_name, machine_mode):

    ext_or_int, info_dict = _get_pvinfo_dict(
        ch_def, elem_name_pvid_to_pvinfo, elem_name, machine_mode
    )

    if ext_or_int == "ext":
        pvname_d = {
            get_or_put: [info["pvname"][machine_mode.value] for info in info_list]
            for get_or_put, info_list in info_dict.items()
        }
    else:
        pvprefix = get_sim_pvprefix(machine_mode)
        pvname_d = {}
        for get_or_put, info_list in info_dict.items():
            pvname_list = []
            for info in info_list:
                pvsuffix = info["pvsuffix"]
                pvname = f"{pvprefix}{pvsuffix}"
                pvname_list.append(pvname)
            pvname_d[get_or_put] = pvname_list

    return pvname_d


def get_aux_input_pvnames_pvunits(
    ch_def, elem_name_pvid_to_pvinfo, elem_name, machine_mode, ext_or_int
):

    pvid_in_elem_list = get_aux_pvids_in_elem(ch_def)[ext_or_int]

    info_list = [
        elem_name_pvid_to_pvinfo[ext_or_int][(elem_name, pvid_in_elem)]
        for pvid_in_elem in pvid_in_elem_list
    ]

    if ext_or_int == "ext":
        pvname_list = [info["pvname"][machine_mode.value] for info in info_list]
        pvunit_list = [info["pvunit"][machine_mode.value] for info in info_list]
    else:
        pvprefix = get_sim_pvprefix(machine_mode)
        pvname_list = []
        for info in info_list:
            pvsuffix = info["pvsuffix"]
            pvname = f"{pvprefix}{pvsuffix}"
            pvname_list.append(pvname)

        pvunit_list = [info["pvunit"] for info in info_list]

    return pvname_list, pvunit_list


def get_pvunits(ch_def, elem_name_pvid_to_pvinfo, elem_name, machine_mode):

    ext_or_int, info_dict = _get_pvinfo_dict(
        ch_def, elem_name_pvid_to_pvinfo, elem_name, machine_mode
    )

    if ext_or_int == "ext":
        pvunit_d = {
            get_or_put: [info["pvunit"][machine_mode.value] for info in info_list]
            for get_or_put, info_list in info_dict.items()
        }
    else:
        pvunit_d = {
            get_or_put: [info["pvunit"] for info in info_list]
            for get_or_put, info_list in info_dict.items()
        }

    return pvunit_d


def get_reprs(elem_def, ext_or_int: Literal["ext", "int"], pvid_list: List[str]):

    return [elem_def["pvid_to_repr_map"][ext_or_int][pvid] for pvid in pvid_list]


def _get_standard_RB_components(
    machine_mode: MachineMode,
    LoLv_psig_name: str,
    HiLv_psig_name: str,
    elem_def,
    ch_def,
    elem_name_pvid_to_pvinfo,
    elem_name,
    simulator_interface_path,
    control_system: Literal["epics", "tango"],
):

    assert ch_def["handle"] == "RB"

    match get_ext_or_int(machine_mode):
        case "ext":
            LoLv_sig_class = ExternalPamilaSignals[control_system]["SignalRO"]
            LoLv_cpt_kwargs = {}
        case "int":
            LoLv_sig_class = InternalPamilaSignalRO
            LoLv_cpt_kwargs = dict(simulator_interface_path=simulator_interface_path)
        case _:
            raise ValueError

    _LoLv_pv_units_d = get_pvunits(
        ch_def, elem_name_pvid_to_pvinfo, elem_name, machine_mode
    )
    assert list(_LoLv_pv_units_d) == ["get"]
    _LoLv_pv_units = _LoLv_pv_units_d["get"]
    assert len(_LoLv_pv_units) == 1
    LoLv_pv_unit = _LoLv_pv_units[0]
    out_reprs = ch_def["HiLv_reprs"]
    assert len(out_reprs) == 1
    mlv_unit = elem_def["repr_units"][out_reprs[0]]

    _pvnames_d = get_pvnames(ch_def, elem_name_pvid_to_pvinfo, elem_name, machine_mode)
    assert list(_pvnames_d) == ["get"]
    _pvnames = _pvnames_d["get"]
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

    in_reprs = get_reprs(elem_def, ext_or_int, ch_def[ext_or_int]["get"]["input_pvs"])
    out_reprs = ch_def["HiLv_reprs"]
    conv_spec_name = ch_def[ext_or_int]["get"].get("conv_spec_name", None)
    unitconv = get_unitconv(elem_def, in_reprs, out_reprs, conv_spec_name)

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
    control_system: Literal["epics", "tango"],
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
        control_system,
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


def _get_MIMO_RB_components(
    machine_mode: MachineMode,
    psig_name_prefix: str,
    elem_def,
    ch_def,
    elem_name_pvid_to_pvinfo,
    elem_name,
    simulator_interface_path,
    control_system: Literal["epics", "tango"],
):

    assert ch_def["handle"] == "RB"

    match ext_or_int := get_ext_or_int(machine_mode):
        case "ext":
            LoLv_sig_class = ExternalPamilaSignals[control_system]["SignalRO"]
            LoLv_cpt_kwargs = {}
        case "int":
            LoLv_sig_class = InternalPamilaSignalRO
            LoLv_cpt_kwargs = dict(simulator_interface_path=simulator_interface_path)
        case _:
            raise ValueError

    _pvnames = get_pvnames(ch_def, elem_name_pvid_to_pvinfo, elem_name, machine_mode)
    input_pvnames = _pvnames["get"]

    _pv_units = get_pvunits(ch_def, elem_name_pvid_to_pvinfo, elem_name, machine_mode)
    input_pv_units = _pv_units["get"]

    components = {}
    assert len(input_pvnames) == len(input_pv_units)
    for i, (LoLv_pvname, LoLv_pv_unit) in enumerate(zip(input_pvnames, input_pv_units)):
        components[f"LoLv_RB_get_input_{i}"] = Cpt(
            LoLv_sig_class,
            LoLv_pvname,
            mode=machine_mode,
            name=f"{psig_name_prefix}_get_input_{i}",  # signal name
            unit=LoLv_pv_unit,
            **LoLv_cpt_kwargs,
        )

    out_reprs = ch_def["HiLv_reprs"]

    # High-level or user-level units
    mlv_units = [elem_def["repr_units"][_repr] for _repr in out_reprs]

    for i, mlv_unit in enumerate(mlv_units):
        components[f"RB_get_output_{i}"] = Cpt(
            UserPamilaSignal,
            mode=machine_mode,
            name=f"{psig_name_prefix}_get_output_{i}",
            unit=mlv_unit,
        )

    return components


def _get_MIMO_RB_pdev_action_specs(elem_def, ch_def, ext_or_int, components_keys):

    HiLv_reprs = ch_def["HiLv_reprs"]

    ch_pvs = ch_def[ext_or_int]

    in_reprs = get_reprs(elem_def, ext_or_int, ch_pvs["get"]["input_pvs"])
    # There should be no "aux_input" for "get"
    out_reprs = HiLv_reprs

    conv_spec_name = ch_pvs["get"].get("conv_spec_name", None)
    unitconv = get_unitconv(elem_def, in_reprs, out_reprs, conv_spec_name)

    get_spec = PamilaDeviceActionSpec(
        input_cpt_attr_names=[
            k for k in components_keys if re.match("^LoLv_RB_get_input_\d+$", k)
        ],
        output_cpt_attr_names=[
            k for k in components_keys if re.match("^RB_get_output_\d+$", k)
        ],
        unitconv=unitconv,
    )

    specs = dict(get=get_spec)

    return specs


def get_MIMO_RB_pdev_spec(
    mlv_name: str,
    machine_name: str,
    machine_mode: MachineMode,
    elem_def,
    ch_def,
    elem_name_pvid_to_pvinfo,
    elem_name,
    simulator_interface_path,
    control_system: Literal["epics", "tango"],
):

    pdev_name, psig_name_prefix = create_pdev_psig_names(mlv_name, machine_mode)

    components = _get_MIMO_RB_components(
        machine_mode,
        psig_name_prefix,
        elem_def,
        ch_def,
        elem_name_pvid_to_pvinfo,
        elem_name,
        simulator_interface_path,
        control_system,
    )

    ext_or_int = get_ext_or_int(machine_mode)
    action_specs = _get_MIMO_RB_pdev_action_specs(
        elem_def, ch_def, ext_or_int, list(components)
    )

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
    control_system: Literal["epics", "tango"],
):
    assert ch_def["handle"] == "SP"

    match get_ext_or_int(machine_mode):
        case "ext":
            LoLv_sig_class = ExternalPamilaSignals[control_system]["Signal"]
            LoLv_cpt_kwargs = {}
        case "int":
            LoLv_sig_class = InternalPamilaSignal
            LoLv_cpt_kwargs = dict(simulator_interface_path=simulator_interface_path)
        case _:
            raise ValueError

    _LoLv_pv_units_d = get_pvunits(
        ch_def, elem_name_pvid_to_pvinfo, elem_name, machine_mode
    )
    assert _LoLv_pv_units_d["get"] == _LoLv_pv_units_d["put"]
    _LoLv_pv_units = _LoLv_pv_units_d["get"]
    assert len(_LoLv_pv_units) == 1
    LoLv_pv_unit = _LoLv_pv_units[0]

    out_reprs = ch_def["HiLv_reprs"]
    assert len(out_reprs) == 1
    mlv_unit = elem_def["repr_units"][out_reprs[0]]

    _SP_pvnames_d = get_pvnames(
        ch_def, elem_name_pvid_to_pvinfo, elem_name, machine_mode
    )
    assert _SP_pvnames_d["get"] == _SP_pvnames_d["put"]
    _SP_pvnames = _SP_pvnames_d["get"]
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
            control_system,
        )

        components["RB_LoLv"] = RB_components["RB_LoLv"]
        components["RB"] = RB_components["RB"]

    return components


def _get_standard_SP_pdev_action_specs(elem_def, ch_def, ext_or_int, mode_pdev_def):

    LoLv_reprs = get_reprs(elem_def, ext_or_int, ch_def[ext_or_int]["get"]["input_pvs"])
    HiLv_reprs = ch_def["HiLv_reprs"]

    in_reprs = LoLv_reprs
    out_reprs = HiLv_reprs
    conv_spec_name = ch_def[ext_or_int]["get"].get("conv_spec_name", None)
    unitconv = get_unitconv(elem_def, in_reprs, out_reprs, conv_spec_name)

    get_spec = PamilaDeviceActionSpec(
        input_cpt_attr_names=["SP_LoLv"],
        output_cpt_attr_names=["SP"],
        unitconv=unitconv,
    )

    in_reprs = HiLv_reprs
    put_LoLv_reprs = get_reprs(
        elem_def, ext_or_int, ch_def[ext_or_int]["put"]["output_pvs"]
    )
    assert LoLv_reprs == put_LoLv_reprs

    out_reprs = LoLv_reprs

    conv_spec_name = ch_def[ext_or_int]["put"].get("conv_spec_name", None)
    unitconv = get_unitconv(elem_def, in_reprs, out_reprs, conv_spec_name)

    put_spec = PamilaDeviceActionSpec(
        input_cpt_attr_names=["SP_put_input"],
        output_cpt_attr_names=["SP_LoLv"],
        unitconv=unitconv,
    )

    specs = dict(get=get_spec, put=put_spec)

    SP_RB_diff = mode_pdev_def.get("SP_RB_diff", {})
    if SP_RB_diff:
        RB_ch_def = elem_def["channel_map"][SP_RB_diff["RB_channel"]]

        LoLv_reprs = get_reprs(
            elem_def, ext_or_int, RB_ch_def[ext_or_int]["get"]["input_pvs"]
        )
        HiLv_reprs = RB_ch_def["HiLv_reprs"]

        in_reprs = LoLv_reprs
        out_reprs = HiLv_reprs
        conv_spec_name = RB_ch_def[ext_or_int]["get"].get("conv_spec_name", None)
        unitconv = get_unitconv(elem_def, in_reprs, out_reprs, conv_spec_name)

        specs["readback_in_set"] = PamilaDeviceActionSpec(
            input_cpt_attr_names=["RB_LoLv"],
            output_cpt_attr_names=["RB"],
            unitconv=unitconv,
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
    control_system: Literal["epics", "tango"],
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
        control_system,
    )

    ext_or_int = get_ext_or_int(machine_mode)
    action_specs = _get_standard_SP_pdev_action_specs(
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


def _get_MIMO_SP_components(
    machine_mode: MachineMode,
    psig_name_prefix: str,
    elem_def,
    ch_def,
    elem_name_pvid_to_pvinfo,
    elem_name,
    simulator_interface_path,
    mode_pdev_def,
    control_system: Literal["epics", "tango"],
):
    assert ch_def["handle"] == "SP"

    match ext_or_int := get_ext_or_int(machine_mode):
        case "ext":
            LoLv_sig_class = ExternalPamilaSignals[control_system]["Signal"]
            LoLv_cpt_kwargs = {}
        case "int":
            LoLv_sig_class = InternalPamilaSignal
            LoLv_cpt_kwargs = dict(simulator_interface_path=simulator_interface_path)
        case _:
            raise ValueError

    _SP_pvnames = get_pvnames(ch_def, elem_name_pvid_to_pvinfo, elem_name, machine_mode)
    SP_get_input_pvnames = _SP_pvnames["get"]
    SP_put_output_pvnames = _SP_pvnames["put"]

    _SP_pv_units = get_pvunits(
        ch_def, elem_name_pvid_to_pvinfo, elem_name, machine_mode
    )
    SP_get_input_pvunits = _SP_pv_units["get"]
    SP_put_output_pvunits = _SP_pv_units["put"]

    components = {}
    assert len(SP_get_input_pvnames) == len(SP_get_input_pvunits)
    for i, (LoLv_pvname, LoLv_pv_unit) in enumerate(
        zip(SP_get_input_pvnames, SP_get_input_pvunits)
    ):
        components[f"LoLv_SP_get_input_{i}"] = Cpt(
            LoLv_sig_class,
            LoLv_pvname,
            mode=machine_mode,
            name=f"{psig_name_prefix}_get_input_{i}",  # signal name
            unit=LoLv_pv_unit,
            **LoLv_cpt_kwargs,
        )

    out_reprs = ch_def["HiLv_reprs"]

    # High-level or user-level units
    mlv_units = [elem_def["repr_units"][_repr] for _repr in out_reprs]

    for i, mlv_unit in enumerate(mlv_units):
        components[f"SP_get_output_{i}"] = Cpt(
            UserPamilaSignal,
            mode=machine_mode,
            name=f"{psig_name_prefix}_get_output_{i}",
            unit=mlv_unit,
        )

    for i, mlv_unit in enumerate(mlv_units):
        components[f"SP_put_input_{i}"] = Cpt(
            UserPamilaSignal,
            mode=machine_mode,
            name=f"{psig_name_prefix}_put_input_{i}",
            unit=mlv_unit,
        )

    # Auxiliary input PVs should exist, if any, only for "put" (not for "get")
    aux_input_pvnames, aux_input_pvunits = get_aux_input_pvnames_pvunits(
        ch_def, elem_name_pvid_to_pvinfo, elem_name, machine_mode, ext_or_int
    )
    for i, (LoLv_pvname, LoLv_pv_unit) in enumerate(
        zip(aux_input_pvnames, aux_input_pvunits)
    ):
        components[f"LoLv_SP_put_aux_input_{i}"] = Cpt(
            LoLv_sig_class,
            LoLv_pvname,
            mode=machine_mode,
            name=f"{psig_name_prefix}_put_aux_input_{i}",  # signal name
            unit=LoLv_pv_unit,
            **LoLv_cpt_kwargs,
        )

    for i, (LoLv_pvname, LoLv_pv_unit) in enumerate(
        zip(SP_put_output_pvnames, SP_put_output_pvunits)
    ):
        components[f"LoLv_SP_put_output_{i}"] = Cpt(
            LoLv_sig_class,
            LoLv_pvname,
            mode=machine_mode,
            name=f"{psig_name_prefix}_put_output_{i}",  # signal name
            unit=LoLv_pv_unit,
            **LoLv_cpt_kwargs,
        )

    SP_RB_diff = mode_pdev_def.get("SP_RB_diff", {})

    if SP_RB_diff:
        RB_ch_def = elem_def["channel_map"][SP_RB_diff["RB_channel"]]
        RB_LoLv_psig_name = f"{psig_name_prefix}_RB"
        RB_HiLv_psig_name = f"{RB_LoLv_psig_name}_HiLv"
        RB_components = _get_MIMO_RB_components(
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


def _get_MIMO_SP_pdev_action_specs(
    elem_def, ch_def, ext_or_int, components_keys, mode_pdev_def
):

    HiLv_reprs = ch_def["HiLv_reprs"]

    ch_pvs = ch_def[ext_or_int]

    in_reprs = get_reprs(elem_def, ext_or_int, ch_pvs["get"]["input_pvs"])
    aux_in_reprs = get_reprs(
        elem_def, ext_or_int, ch_pvs["get"].get("aux_input_pvs", [])
    )
    assert aux_in_reprs == []  # There should be no "aux_input" for "get"
    out_reprs = HiLv_reprs

    conv_spec_name = ch_pvs["get"].get("conv_spec_name", None)
    unitconv = get_unitconv(elem_def, in_reprs, out_reprs, conv_spec_name)

    get_spec = PamilaDeviceActionSpec(
        input_cpt_attr_names=[
            k for k in components_keys if re.match("^LoLv_SP_get_input_\d+$", k)
        ],
        output_cpt_attr_names=[
            k for k in components_keys if re.match("^SP_get_output_\d+$", k)
        ],
        unitconv=unitconv,
    )

    aux_in_reprs = get_reprs(
        elem_def, ext_or_int, ch_pvs["put"].get("aux_input_pvs", [])
    )
    in_reprs = HiLv_reprs + aux_in_reprs
    out_reprs = get_reprs(elem_def, ext_or_int, ch_pvs["put"]["output_pvs"])

    conv_spec_name = ch_pvs["put"].get("conv_spec_name", None)
    unitconv = get_unitconv(elem_def, in_reprs, out_reprs, conv_spec_name)

    put_spec = PamilaDeviceActionSpec(
        input_cpt_attr_names=[
            k for k in components_keys if re.match("^SP_put_input_\d+$", k)
        ],
        aux_input_cpt_attr_names=[
            k for k in components_keys if re.match("^LoLv_SP_put_aux_input_\d+$", k)
        ],
        output_cpt_attr_names=[
            k for k in components_keys if re.match("^LoLv_SP_put_output_\d+$", k)
        ],
        unitconv=unitconv,
    )

    specs = dict(get=get_spec, put=put_spec)

    SP_RB_diff = mode_pdev_def.get("SP_RB_diff", {})
    if SP_RB_diff:
        RB_ch_def = elem_def["channel_map"][SP_RB_diff["RB_channel"]]

        RB_ch_pvs = RB_ch_def[ext_or_int]

        in_reprs = get_reprs(elem_def, ext_or_int, RB_ch_pvs["get"]["input_pvs"])
        aux_in_reprs = get_reprs(
            elem_def, ext_or_int, RB_ch_pvs["get"].get("aux_input_pvs", [])
        )
        assert aux_in_reprs == []  # There should be no "aux_input" for "get"
        out_reprs = RB_ch_def["HiLv_reprs"]

        conv_spec_name = RB_ch_pvs["get"].get("conv_spec_name", None)
        unitconv = get_unitconv(elem_def, in_reprs, out_reprs, conv_spec_name)

        specs["readback_in_set"] = PamilaDeviceActionSpec(
            input_cpt_attr_names=["RB_LoLv"],
            output_cpt_attr_names=["RB"],
            unitconv=unitconv,
        )

    return specs


def get_MIMO_SP_pdev_spec(
    mlv_name: str,
    machine_name: str,
    machine_mode: MachineMode,
    elem_def,
    ch_def,
    elem_name_pvid_to_pvinfo,
    elem_name,
    simulator_interface_path,
    mode_pdev_def,
    control_system: Literal["epics", "tango"],
):

    pdev_name, psig_name_prefix = create_pdev_psig_names(mlv_name, machine_mode)

    components = _get_MIMO_SP_components(
        machine_mode,
        psig_name_prefix,
        elem_def,
        ch_def,
        elem_name_pvid_to_pvinfo,
        elem_name,
        simulator_interface_path,
        mode_pdev_def,
        control_system,
    )

    ext_or_int = get_ext_or_int(machine_mode)
    action_specs = _get_MIMO_SP_pdev_action_specs(
        elem_def, ch_def, ext_or_int, list(components), mode_pdev_def
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
    def __init__(self, machine_name: str, dirpath: Path, model_name: str = ""):

        self.machine_name = machine_name

        self.dirpath = dirpath
        self.model_name = model_name

        self._noncache_load()

        self._non_serializable_attrs = []

    def _noncache_load(self):

        machine_folder = self.dirpath / self.machine_name

        sim_configs_yaml_d = yaml.safe_load(
            (machine_folder / "sim_configs.yaml").read_text()
        )
        sim_configs_d = sim_configs_yaml_d["simulator_configs"]
        for k, v in sim_configs_d.items():
            if v is None:
                continue
            match v["package_name"]:
                case "pyat":
                    sim_configs_d[k] = PyATInterfaceSpec(**v)
                case _:
                    raise NotImplementedError

        self.sim_configs = SimConfigs(**sim_configs_yaml_d)
        self.sel_config_name = self.sim_configs.selected_config
        self.sim_conf = self.sim_configs.simulator_configs[self.sel_config_name]

        if self.model_name:
            self._lattice_model_name = self.model_name
        else:
            self._lattice_model_name = self.sim_conf.default_lattice_model

        self.config_folder = machine_folder / self.sel_config_name

        self._load_device_conversion_plugins()

        self._load_definitions_from_files()
        self._load_lattice_design_props_from_files()

        self._set_sim_interface_spec()

        _reset_sim_interface(self.machine_name)  # Necessary when reloading the machine
        # to clear out previously loaded simulators.

        self._construct_mlvs()
        # MLVLs and MLVTs will be constructed once Machine() initialization is
        # completed.

    def _update_from_cache(self):

        self._load_device_conversion_plugins()

        self._set_sim_interface_spec()

        _reset_sim_interface(self.machine_name)  # Necessary when reloading the machine
        # to clear out previously loaded simulators.

    def __getstate__(self):

        state = self.__dict__.copy()

        # Exclude the non-serializable attributes
        for attr in self._non_serializable_attrs:
            del state[attr]

        return state

    def __setstate__(self, state):
        self.__dict__.update(state)

    def _load_device_conversion_plugins(self):

        if self.sim_configs.conversion_plugin_folder:
            load_plugins(Path(self.sim_configs.conversion_plugin_folder))

        if self.sim_conf.conversion_plugin_folder:
            load_plugins(Path(self.sim_conf.conversion_plugin_folder))

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

        self._update_elem_name_pvid_to_pvinfo_ext()
        self._update_elem_name_pvid_to_pvinfo_int()

    def _update_elem_name_pvid_to_pvinfo_ext(self):

        pv_elem_maps = self.pv_elem_maps["pv_elem_maps"]
        elem_name_pvid_to_pvinfo = self.elem_name_pvid_to_pvinfo["ext"]
        elem_name_pvid_to_pvinfo.clear()

        for pvname, d in pv_elem_maps.items():
            for elem_name in d["elem_names"]:
                k = (elem_name, d["pvid_in_elem"])
                assert k not in elem_name_pvid_to_pvinfo
                elem_name_pvid_to_pvinfo[k] = {
                    "handle": d["handle"],
                    "pvname": dict(LIVE=pvname, DT=d.get("DT_pvname", None)),
                    "pvunit": dict(LIVE=d["pvunit"], DT=d.get("DT_pvunit", None)),
                }

    def _update_elem_name_pvid_to_pvinfo_int(self):

        simpv_elem_maps = self.simpv_elem_maps["simpv_elem_maps"]
        elem_name_pvid_to_pvinfo = self.elem_name_pvid_to_pvinfo["int"]
        elem_name_pvid_to_pvinfo.clear()

        for pvsuffix, d in simpv_elem_maps.items():

            for elem_name in d["elem_names"]:
                k = (elem_name, d["pvid_in_elem"])
                assert k not in elem_name_pvid_to_pvinfo
                elem_name_pvid_to_pvinfo[k] = {
                    "handle": d["handle"],
                    "pvsuffix": pvsuffix,
                    "pvunit": d["pvunit"],
                }

    def _load_lattice_design_props_from_files(self):

        d = self.design_lat_props = {}
        for model_name in self.sim_conf.lattice_models.keys():
            folder = self.config_folder / model_name
            d[model_name] = json.loads((folder / "design_props.json").read_text())

    def get_design_lattice_props(self):
        return self.design_lat_props[self._lattice_model_name]

    def _set_sim_interface_spec(self):

        match self.sim_conf.package_name:
            case "pyat":
                sim_pv_defs = {}
                for d in self.sim_pv_defs["sim_pv_definitions"]:
                    pvsuffix = d["pvsuffix"]
                    assert pvsuffix not in sim_pv_defs
                    sim_pv_defs[pvsuffix] = SimulatorPvDefinition(
                        **{k: v for k, v in d.items() if k != "pvsuffix"}
                    )
                sim_conf_d = self.sim_conf.model_dump()
                sim_conf_d["sim_pv_defs"] = sim_pv_defs
                self.sim_itf_spec = PyATInterfaceSpec(**sim_conf_d)
            case "no_simulator":
                self.sim_itf_spec = None
            case _:
                raise NotImplementedError

        set_sim_interface_spec(self.machine_name, self.sim_itf_spec)

        self.sim_itf_paths = {}

    def _add_sim_pv_def(self, new_entry: Dict):
        d = new_entry
        pvsuffix = d["pvsuffix"]
        sim_itf = self.get_sim_interface()
        sim_itf._sim_pv_defs[pvsuffix] = SimulatorPvDefinition(
            **{k: v for k, v in d.items() if k != "pvsuffix"}
        )

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

        for elem_name, e_def in self.elem_defs["elem_definitions"].items():
            self._construct_mlvs_for_one_elem(elem_name, e_def, exist_ok=False)

    def _construct_mlvs_for_one_elem(
        self, elem_name: str, elem_def: Dict, exist_ok: bool = False
    ):

        elem_name_pvid_to_pvinfo = self.elem_name_pvid_to_pvinfo

        if "s_lists" in elem_def:
            elem_s_list = elem_def["s_lists"].get("element", None)
        else:
            elem_s_list = None

        elem_spec = ElementSpec(
            name=elem_name,
            machine_name=self.machine_name,
            pvid_to_repr_map=elem_def["pvid_to_repr_map"],
            repr_units=elem_def["repr_units"],
            channel_names=list(elem_def["channel_map"]),
            description=elem_def.get("description", ""),
            s_list=elem_s_list,
            tags=KeyValueTagList(tags=elem_def.get("tags", {})),
            exist_ok=exist_ok,
        )
        Element(elem_spec)

        for ch_name, ch_def in elem_def["channel_map"].items():
            mlv_name = f"{elem_name}_{ch_name}"

            if "s_lists" in elem_def:
                s_list_key = ch_def.get("s_list_key")
                if not s_list_key:
                    s_list_key = "element"

                s_list = elem_def["s_lists"].get(s_list_key, None)
            else:
                s_list = None

            tags_d = elem_def.get("tags", {})

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

            for machine_mode_value, orig_mode_pdev_def in pdev_def.items():
                machine_mode = MachineMode(machine_mode_value)

                if get_ext_or_int(machine_mode) == "int":
                    sim_itf_path = self._get_sim_interface_path(machine_mode)
                else:
                    sim_itf_path = None

                mode_pdev_def = deepcopy(orig_mode_pdev_def)

                if read_only:
                    mode_pdev_def_type = mode_pdev_def.pop("type", "standard_RB")

                    match mode_pdev_def_type:
                        case "standard_RB":
                            pdev_spec = get_standard_RB_pdev_spec(
                                mlv_name,
                                self.machine_name,
                                machine_mode,
                                elem_def,
                                ch_def,
                                elem_name_pvid_to_pvinfo,
                                elem_name,
                                sim_itf_path,
                                self.sim_configs.control_system,
                            )
                        case "plugin":
                            raise NotImplementedError
                        case "standard_MIMO_RB":
                            pdev_spec = get_MIMO_RB_pdev_spec(
                                mlv_name,
                                self.machine_name,
                                machine_mode,
                                elem_def,
                                ch_def,
                                elem_name_pvid_to_pvinfo,
                                elem_name,
                                sim_itf_path,
                                self.sim_configs.control_system,
                            )

                        case _:
                            raise NotImplementedError

                else:
                    mode_pdev_def_type = mode_pdev_def.get("type", "standard_SP")

                    match mode_pdev_def_type:

                        case "standard_SP":
                            _mode_pdev_def = json.loads(
                                StandardSetpointDeviceDefinition(
                                    **mode_pdev_def
                                ).model_dump_json()
                            )
                            _mode_pdev_def.pop("type")
                            pdev_spec = get_standard_SP_pdev_spec(
                                mlv_name,
                                self.machine_name,
                                machine_mode,
                                elem_def,
                                ch_def,
                                elem_name_pvid_to_pvinfo,
                                elem_name,
                                sim_itf_path,
                                _mode_pdev_def,
                                self.sim_configs.control_system,
                            )
                        case "standard_MIMO_SP":
                            _mode_pdev_def = json.loads(
                                StandardSetpointDeviceDefinition(
                                    **mode_pdev_def
                                ).model_dump_json()
                            )
                            _mode_pdev_def.pop("type")
                            pdev_spec = get_MIMO_SP_pdev_spec(
                                mlv_name,
                                self.machine_name,
                                machine_mode,
                                elem_def,
                                ch_def,
                                elem_name_pvid_to_pvinfo,
                                elem_name,
                                sim_itf_path,
                                _mode_pdev_def,
                                self.sim_configs.control_system,
                            )

                        case _:
                            raise NotImplementedError

                pdev_specs[machine_mode] = pdev_spec

            mlv_spec = MiddleLayerVariableSpec(
                name=mlv_name,
                machine_name=self.machine_name,
                simulator_config=self.sel_config_name,
                pdev_spec_dict=pdev_specs,
                exist_ok=exist_ok,
                s_list=s_list,
                tags=KeyValueTagList(tags=tags_d),
            )
            mlv_class(mlv_spec)
