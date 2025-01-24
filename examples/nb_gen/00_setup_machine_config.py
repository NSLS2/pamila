# %%
from copy import deepcopy
import getpass
import json
import os
from pathlib import Path
from typing import Dict, List

os.environ["PAMILA_FACILITY"]

# %%
import numpy as np
import yaml


class CustomDumper(yaml.SafeDumper):
    def represent_list(self, data):
        # Force lists to be represented in flow style (inline `[]` style)
        return self.represent_sequence("tag:yaml.org,2002:seq", data, flow_style=True)


# Add the custom list representation to the dumper
CustomDumper.add_representer(list, CustomDumper.represent_list)

# %%
# You can ignore about the `pydantic` deprecation warning (coming from `tiled`)
import pamila as pml
from pamila import Q_
from pamila.device.simple import FixedWaitTime
from pamila.device.specs import FunctionSpec
from pamila.facility_configs.generator import (
    ChannelSpec,
    FunctionSpec,
    GetPVMapping,
    MachineModeSpecContainer,
    PamilaElementDefinition,
    PutPVMapping,
    PVMapping,
)
from pamila.facility_configs.generator import (
    SetpointReadbackDiffDefinition as SP_RB_Diff_Def,
)
from pamila.facility_configs.generator import (
    StandardReadbackDeviceDefinition as standard_RB,
)
from pamila.facility_configs.generator import (
    StandardSetpointDeviceDefinition as standard_SP,
)
from pamila.sim_interface import PyATInterfaceSpec
from pamila.utils import KeyValueTag, KeyValueTagList, SPositionList

# %%
assert pml.machine.get_facility_name() == os.environ["PAMILA_FACILITY"]
print(pml.__version__)
print(pml.__file__)

# %%
machine_name = "SR"  # := NSLS-II Storage Ring

sim_configs = {
    "facility": os.environ["PAMILA_FACILITY"],
    "machine": machine_name,
    "control_system": "epics",
    "simulator_configs": {"no_simulator": None},
}

# %%
cwd = Path.cwd()
if cwd.name == "examples":
    examples_folder = cwd
else:
    assert cwd.name == "nb_gen"
    examples_folder = cwd.parent
facility_folder = examples_folder / "demo_generated" / sim_configs["facility"]

# Start from scratch
if facility_folder.exists() and facility_folder.is_dir():
    import shutil

    shutil.rmtree(facility_folder)

facility_folder.mkdir(parents=True)

# %%
machine_folder = facility_folder / machine_name
if not machine_folder.exists():
    machine_folder.mkdir()

machine_mlvs = pml.middle_layer.get_all_mlvs(machine_name)
machine_mlvs

# %%
import at

model_name = "bare_ideal"
lattice_filepath = examples_folder / "lattice_files/nsls2_girders4d_pyATv0_6_1.mat"
lattice = at.load_lattice(lattice_filepath)
bpm_uint32_inds = at.get_uint32_index(lattice, "P[HLM]*")

sim_configs["simulator_configs"]["pyat_2024_12"] = {
    "package_name": "pyat",
    "closed_orbit_uint32_indexes": bpm_uint32_inds.tolist(),
    "lattice_models": {
        model_name: {
            "lattice_filepath": str(lattice_filepath.resolve()),
            # "non_simulator_settings": "non_simulator_settings.yaml" # will contain BPM gains/rolls, initial values for DCCT, Fake ID gap, SOFB BPM exclusion PVs, etc.
        },
        # "bare_w_err_0001":
        #     {"lattice_filepath": str(lattice_filepath.resolve()),
        #     # "non_simulator_settings": "non_simulator_settings.yaml"
        # }
    },
    "default_lattice_model": "bare_ideal",
}
sim_configs["selected_config"] = "pyat_2024_12"

# %%
output_filepath = machine_folder / "sim_configs.yaml"
with open(output_filepath, "w") as f:
    yaml.dump(
        sim_configs,
        f,
        sort_keys=False,
        default_flow_style=False,
        width=70,
        indent=2,
        Dumper=CustomDumper,
    )

print(f"{output_filepath = }\n")
print(output_filepath.read_text())

# %%
sel_config_folder = machine_folder / sim_configs["selected_config"]
sel_config_folder.mkdir(parents=True, exist_ok=True)

# %%
# Check simulation interface is working
sim_conf_d = sim_configs["simulator_configs"][sim_configs["selected_config"]]

match sim_conf_d["package_name"]:
    case "pyat":
        sim_itf_spec = PyATInterfaceSpec(**sim_conf_d)
    case _:
        raise NotImplementedError

sim_itf = pml.sim_interface.create_interface(sim_itf_spec, pml.MachineMode.SIMULATOR)
at = sim_itf.package
lattice = sim_itf.get_lattice()

# %%

# %%
USERNAME = getpass.getuser()


def _get_blank_elem_def(elem_defs, elem_name):
    if elem_name not in elem_defs:
        elem_defs[elem_name] = PamilaElementDefinition()
    return elem_defs[elem_name]


pv_elem_maps = {}
simpv_elem_maps = {}
simpv_defs = {}
elem_defs = {}

# %% [markdown]
# # BPM definitions


# %%
def process_slow_acq_bpm_definition(
    pv_elem_maps: Dict,
    simpv_elem_maps: Dict,
    simpv_defs: Dict,
    elem_defs: Dict,
    at_elem_name: str,
    pml_elem_name: str,
    pvname_d: Dict,
    sim_pvsuffix_d: Dict,
    tags: KeyValueTagList | None = None,
):

    matched_indexes = at.get_uint32_index(lattice, at_elem_name)
    assert len(matched_indexes) == 1
    lattice_index = int(
        matched_indexes[0]
    )  # Avoid numpy.uint32 that prevents saving into JSON/YAML
    elem = lattice[lattice_index]
    elem_type = elem.definition[0]

    s_b_array = at.get_s_pos(lattice, matched_indexes)
    s_e_array = s_b_array + np.array([lattice[i].Length for i in matched_indexes])
    s_lists = dict(element=SPositionList(b=s_b_array.tolist(), e=s_e_array.tolist()))

    if tags is None:
        tags = KeyValueTagList()
    assert isinstance(tags, KeyValueTagList)

    if False:
        info_to_check = dict(
            elem_name=at_elem_name, elem_type=elem_type, lattice_index=lattice_index
        )

    pdev_standard_RB_def = MachineModeSpecContainer(
        LIVE=standard_RB(), DT=standard_RB(), SIM=standard_RB()
    )

    for plane, pvname in pvname_d.items():

        assert pvname not in pv_elem_maps

        sim_pvsuffix = sim_pvsuffix_d[plane]
        # sim_pvname = f"SIMPV:{sim_pvsuffix}"

        assert sim_pvsuffix not in simpv_elem_maps

        ext_pvid = f"extpv_{plane}_RB"
        int_pvid = f"intpv_{plane}_RB"

        template_map_d = dict(
            elem_names=[pml_elem_name],
            handle=None,
            pvid_in_elem=None,
            DT_pvname=None,
            DT_pvunit=None,
        )

        pv_elem_dict_RB = deepcopy(template_map_d)
        pv_elem_dict_RB["pvid_in_elem"] = ext_pvid
        pv_elem_dict_RB["handle"] = "RB"
        pv_elem_dict_RB["pvunit"] = "mm"
        pv_elem_dict_RB["DT_pvname"] = (
            f"{USERNAME}:{pvname}"  # PV name for DT (Digital Twin)
        )
        pv_elem_dict_RB["DT_pvunit"] = "mm"

        template_map_d = dict(
            elem_names=[pml_elem_name], handle=None, pvid_in_elem=None
        )

        simpv_elem_dict_RB = deepcopy(template_map_d)
        simpv_elem_dict_RB["elem_names"] = [pml_elem_name]
        simpv_elem_dict_RB["pvid_in_elem"] = int_pvid
        simpv_elem_dict_RB["handle"] = "RB"
        simpv_elem_dict_RB["pvunit"] = "m"
        # simpv_elem_dict["info_to_check"] = info_to_check

        assert sim_pvsuffix not in simpv_defs
        simpv_defs[sim_pvsuffix] = dict(
            pvclass="BPMSlowAcqSimPV", args=[lattice_index, plane]
        )

        elem_def = _get_blank_elem_def(elem_defs, pml_elem_name)

        elem_def.s_lists = s_lists
        elem_def.tags = tags

        repr_str = plane

        elem_def.repr_units[repr_str] = "mm"
        elem_def.pvid_to_repr_map.ext[ext_pvid] = repr_str
        elem_def.pvid_to_repr_map.int[int_pvid] = repr_str

        elem_def.channel_map[f"{plane}_RB"] = ChannelSpec(
            handle="RB",
            HiLv_reprs=[repr_str],
            ext=PVMapping(get=GetPVMapping(input_pvs=[ext_pvid])),
            int=PVMapping(get=GetPVMapping(input_pvs=[int_pvid])),
            pdev_def=pdev_standard_RB_def,
        )

        pv_elem_maps[pvname] = pv_elem_dict_RB

        simpv_elem_maps[sim_pvsuffix] = simpv_elem_dict_RB


# %%

common_tags = dict(
    cell_str=KeyValueTag(key="cell_str", values=["C30"]),
)
bpm_info_list = [
    dict(
        at_elem_name="PH1G2C30A",
        pml_elem_name="C30_P1",
        pvname_d={"x": "SR:C30-BI{BPM:1}Pos:X-I", "y": "SR:C30-BI{BPM:1}Pos:Y-I"},
        sim_pvsuffix_d={"x": "C30_P1_X", "y": "C30_P1_Y"},
        tags=KeyValueTagList(
            tags=[
                common_tags["cell_str"],
                KeyValueTag(key="family", values=["BPM", "PH"]),
            ]
        ),
    ),
    dict(
        at_elem_name="PH2G2C30A",
        pml_elem_name="C30_P2",
        pvname_d={"x": "SR:C30-BI{BPM:2}Pos:X-I", "y": "SR:C30-BI{BPM:2}Pos:Y-I"},
        sim_pvsuffix_d={"x": "C30_P2_X", "y": "C30_P2_Y"},
        tags=KeyValueTagList(
            tags=[
                common_tags["cell_str"],
                KeyValueTag(key="family", values=["BPM", "PH"]),
            ]
        ),
    ),
    dict(
        at_elem_name="PM1G4C30A",
        pml_elem_name="C30_P3",
        pvname_d={"x": "SR:C30-BI{BPM:3}Pos:X-I", "y": "SR:C30-BI{BPM:3}Pos:Y-I"},
        sim_pvsuffix_d={"x": "C30_P3_X", "y": "C30_P3_Y"},
        tags=KeyValueTagList(
            tags=[
                common_tags["cell_str"],
                KeyValueTag(key="family", values=["BPM", "PM"]),
            ]
        ),
    ),
    dict(
        at_elem_name="PM1G4C30B",
        pml_elem_name="C30_P4",
        pvname_d={"x": "SR:C30-BI{BPM:4}Pos:X-I", "y": "SR:C30-BI{BPM:4}Pos:Y-I"},
        sim_pvsuffix_d={"x": "C30_P4_X", "y": "C30_P4_Y"},
        tags=KeyValueTagList(
            tags=[
                common_tags["cell_str"],
                KeyValueTag(key="family", values=["BPM", "PM"]),
            ]
        ),
    ),
    dict(
        at_elem_name="PL2G6C30B",
        pml_elem_name="C30_P5",
        pvname_d={"x": "SR:C30-BI{BPM:5}Pos:X-I", "y": "SR:C30-BI{BPM:5}Pos:Y-I"},
        sim_pvsuffix_d={"x": "C30_P5_X", "y": "C30_P5_Y"},
        tags=KeyValueTagList(
            tags=[
                common_tags["cell_str"],
                KeyValueTag(key="family", values=["BPM", "PL"]),
            ]
        ),
    ),
    dict(
        at_elem_name="PL1G6C30B",
        pml_elem_name="C30_P6",
        pvname_d={"x": "SR:C30-BI{BPM:6}Pos:X-I", "y": "SR:C30-BI{BPM:6}Pos:Y-I"},
        sim_pvsuffix_d={"x": "C30_P6_X", "y": "C30_P6_Y"},
        tags=KeyValueTagList(
            tags=[
                common_tags["cell_str"],
                KeyValueTag(key="family", values=["BPM", "PL"]),
            ]
        ),
    ),
]


# %%
for d in bpm_info_list:
    process_slow_acq_bpm_definition(
        pv_elem_maps,
        simpv_elem_maps,
        simpv_defs,
        elem_defs,
        d["at_elem_name"],
        d["pml_elem_name"],
        d["pvname_d"],
        d["sim_pvsuffix_d"],
        d["tags"],
    )

# %% [markdown]
# # Orbit Corrector (Steerer) Definitions


# %%
def process_corrector_definition(
    pv_elem_maps: Dict,
    simpv_elem_maps: Dict,
    simpv_defs: Dict,
    elem_defs: Dict,
    at_elem_name: str,
    pml_elem_name: str,
    RB_pvname_d: Dict,
    SP_pvname_d: Dict,
    sim_RB_pvsuffix_d: Dict,
    sim_SP_pvsuffix_d: Dict,
    conv_func_specs: Dict[str, Dict],
    tags: KeyValueTagList | None = None,
):

    matched_indexes = at.get_uint32_index(lattice, at_elem_name)
    assert len(matched_indexes) == 1
    lattice_index = int(
        matched_indexes[0]
    )  # Avoid numpy.uint32 that prevents saving into JSON/YAML
    elem = lattice[lattice_index]
    elem_type = elem.definition[0]

    s_b_array = at.get_s_pos(lattice, matched_indexes)
    s_e_array = s_b_array + np.array([lattice[i].Length for i in matched_indexes])
    s_lists = dict(element=SPositionList(b=s_b_array.tolist(), e=s_e_array.tolist()))

    if tags is None:
        tags = KeyValueTagList()
    assert isinstance(tags, KeyValueTagList)

    if False:
        info_to_check = dict(
            elem_name=at_elem_name, elem_type=elem_type, lattice_index=lattice_index
        )

    pdev_standard_RB_def = MachineModeSpecContainer(
        LIVE=standard_RB(), DT=standard_RB(), SIM=standard_RB()
    )

    for plane, RB_pvname in RB_pvname_d.items():
        SP_pvname = SP_pvname_d[plane]

        assert RB_pvname not in pv_elem_maps
        assert SP_pvname not in pv_elem_maps

        # sim_pvname = f"SIMPV:{sim_pvsuffix}"

        sim_RB_pvsuffix = sim_RB_pvsuffix_d[plane]
        sim_SP_pvsuffix = sim_SP_pvsuffix_d[plane]

        assert sim_RB_pvsuffix not in simpv_elem_maps
        assert sim_SP_pvsuffix not in simpv_elem_maps

        ext_SP_pvid = f"extpv_{plane}_I_SP"
        ext_RB_pvid = f"extpv_{plane}_I_RB"
        int_SP_pvid = f"intpv_{plane}_angle_SP"
        int_RB_pvid = f"intpv_{plane}_angle_RB"

        template_map_d = dict(
            elem_names=[pml_elem_name],
            handle=None,
            pvid_in_elem=None,
            DT_pvname=None,
            DT_pvunit=None,
        )

        pv_elem_dict_SP = deepcopy(template_map_d)
        pv_elem_dict_SP["pvid_in_elem"] = ext_SP_pvid
        pv_elem_dict_SP["handle"] = "SP"
        pv_elem_dict_SP["DT_pvname"] = (
            f"{USERNAME}:{SP_pvname}"  # PV name for DT (Digital Twin)
        )
        pv_elem_dict_SP["pvunit"] = "A"
        pv_elem_dict_SP["DT_pvunit"] = "A"

        pv_elem_dict_RB = deepcopy(template_map_d)
        pv_elem_dict_RB["pvid_in_elem"] = ext_RB_pvid
        pv_elem_dict_RB["handle"] = "RB"
        pv_elem_dict_RB["DT_pvname"] = (
            f"{USERNAME}:{RB_pvname}"  # PV name for DT (Digital Twin)
        )
        pv_elem_dict_RB["pvunit"] = "A"
        pv_elem_dict_RB["DT_pvunit"] = "A"

        template_map_d = dict(
            elem_names=[pml_elem_name], handle=None, pvid_in_elem=None
        )

        simpv_elem_dict_SP = deepcopy(template_map_d)
        simpv_elem_dict_SP["pvid_in_elem"] = int_SP_pvid
        simpv_elem_dict_SP["handle"] = "SP"
        simpv_elem_dict_SP["pvunit"] = "rad"

        simpv_elem_dict_RB = deepcopy(template_map_d)
        simpv_elem_dict_RB["pvid_in_elem"] = int_RB_pvid
        simpv_elem_dict_RB["handle"] = "RB"
        simpv_elem_dict_RB["pvunit"] = "rad"

        assert sim_RB_pvsuffix not in simpv_defs
        simpv_defs[sim_RB_pvsuffix] = dict(
            dict(
                pvclass="CorrectorSimPV",
                args=[lattice_index, plane],
            )
        )
        assert sim_SP_pvsuffix not in simpv_defs
        simpv_defs[sim_SP_pvsuffix] = dict(
            dict(
                pvclass="CorrectorSimPV",
                args=[lattice_index, plane],
            )
        )

        elem_def = _get_blank_elem_def(elem_defs, pml_elem_name)

        elem_def.s_lists = s_lists
        elem_def.tags = tags

        repr_I = f"{plane}_I"
        repr_angle = f"{plane}_angle"

        elem_def.repr_units[repr_I] = "A"
        elem_def.pvid_to_repr_map.ext[ext_SP_pvid] = repr_I
        elem_def.pvid_to_repr_map.ext[ext_RB_pvid] = repr_I

        elem_def.repr_units[repr_angle] = "mrad"
        elem_def.pvid_to_repr_map.int[int_SP_pvid] = repr_angle
        elem_def.pvid_to_repr_map.int[int_RB_pvid] = repr_angle

        elem_def.channel_map[f"{repr_I}_RB"] = ChannelSpec(
            handle="RB",
            HiLv_reprs=[repr_I],
            ext=PVMapping(get=GetPVMapping(input_pvs=[ext_RB_pvid])),
            int=PVMapping(
                get=GetPVMapping(
                    input_pvs=[int_RB_pvid],
                    conv_spec_name=f"{repr_angle}_to_{repr_I}",
                )
            ),
            pdev_def=pdev_standard_RB_def,
        )
        elem_def.channel_map[f"{repr_angle}_RB"] = ChannelSpec(
            handle="RB",
            HiLv_reprs=[repr_angle],
            ext=PVMapping(
                get=GetPVMapping(
                    input_pvs=[ext_RB_pvid],
                    conv_spec_name=f"{repr_I}_to_{repr_angle}",
                )
            ),
            int=PVMapping(get=GetPVMapping(input_pvs=[int_RB_pvid])),
            pdev_def=pdev_standard_RB_def,
        )

        sp_rb_diff = SP_RB_Diff_Def(
            RB_channel=f"{repr_I}_RB",
            abs_tol=Q_("0.01 A"),
            rel_tol=None,
            timeout=Q_("10 s"),
            settle_time=Q_("2 s"),
            poll_time=Q_("0.5 s"),
        )
        pdev_SP_def = MachineModeSpecContainer(
            LIVE=standard_SP(
                set_wait_method="SP_RB_diff",
                SP_RB_diff=sp_rb_diff,
                fixed_wait_time=FixedWaitTime(dt=Q_("1.0 s")),
            ),
            DT=standard_SP(
                set_wait_method="fixed_wait_time",
                SP_RB_diff=sp_rb_diff,
                fixed_wait_time=FixedWaitTime(dt=Q_("1.0 s")),
            ),
            SIM=standard_SP(),
        )
        elem_def.channel_map[f"{repr_I}_SP"] = ChannelSpec(
            handle="SP",
            HiLv_reprs=[repr_I],
            ext=PVMapping(
                get=GetPVMapping(input_pvs=[ext_SP_pvid]),
                put=PutPVMapping(output_pvs=[ext_SP_pvid]),
            ),
            int=PVMapping(
                get=GetPVMapping(
                    input_pvs=[int_SP_pvid],
                    conv_spec_name=f"{repr_angle}_to_{repr_I}",
                ),
                put=PutPVMapping(
                    output_pvs=[int_SP_pvid],
                    conv_spec_name=f"{repr_I}_to_{repr_angle}",
                ),
            ),
            pdev_def=pdev_SP_def,
        )

        sp_rb_diff = SP_RB_Diff_Def(
            RB_channel=f"{repr_angle}_RB",
            abs_tol=Q_("2 urad"),
            rel_tol=None,
            timeout=Q_("10 s"),
            settle_time=Q_("2 s"),
            poll_time=Q_("0.5 s"),
        )
        pdev_SP_def = MachineModeSpecContainer(
            LIVE=standard_SP(
                set_wait_method="SP_RB_diff",
                SP_RB_diff=sp_rb_diff,
                fixed_wait_time=FixedWaitTime(dt=Q_("1.0 s")),
            ),
            DT=standard_SP(
                set_wait_method="fixed_wait_time",
                SP_RB_diff=sp_rb_diff,
                fixed_wait_time=FixedWaitTime(dt=Q_("1.0 s")),
            ),
            SIM=standard_SP(),
        )
        elem_def.channel_map[f"{repr_angle}_SP"] = ChannelSpec(
            handle="SP",
            HiLv_reprs=[repr_angle],
            ext=PVMapping(
                get=GetPVMapping(
                    input_pvs=[ext_SP_pvid],
                    conv_spec_name=f"{repr_I}_to_{repr_angle}",
                ),
                put=PutPVMapping(
                    output_pvs=[ext_SP_pvid],
                    conv_spec_name=f"{repr_angle}_to_{repr_I}",
                ),
            ),
            int=PVMapping(
                get=GetPVMapping(input_pvs=[int_SP_pvid]),
                put=PutPVMapping(output_pvs=[int_SP_pvid]),
            ),
            pdev_def=pdev_SP_def,
        )

        for spec_name, spec in conv_func_specs.items():
            elem_def.func_specs[spec_name] = FunctionSpec(**spec)

        pv_elem_maps[RB_pvname] = pv_elem_dict_RB
        if pv_elem_dict_SP is not None:
            pv_elem_maps[SP_pvname] = pv_elem_dict_SP

        simpv_elem_maps[sim_RB_pvsuffix] = simpv_elem_dict_RB
        if simpv_elem_dict_SP is not None:
            simpv_elem_maps[sim_SP_pvsuffix] = simpv_elem_dict_SP


# %%
common_tags = dict(
    cell_str=KeyValueTag(key="cell_str", values=["C30"]),
)

cor_info_list = [
    dict(
        at_elem_name="CH1XG2C30A",
        pml_elem_name="C30_C1",
        RB_pvname_d={"x": "SR:C30-MG{PS:CH1A}I:Ps1DCCT1-I"},
        SP_pvname_d={"x": "SR:C30-MG{PS:CH1A}I:Sp1-SP"},
        sim_RB_pvsuffix_d={"x": "C30_C1_X_RB"},
        sim_SP_pvsuffix_d={"x": "C30_C1_X_SP"},
        conv_func_specs={
            "x_I_to_x_angle": {
                "name": "poly1d",
                "args": [[-0.05528125727506806, 0.0]],
            },
            "x_angle_to_x_I": {
                "name": "poly1d",
                "args": [[-18.089313617166983, 0.0]],
            },
        },
        tags=KeyValueTagList(
            tags=[
                common_tags["cell_str"],
                KeyValueTag(key="family", values=["SCOR", "SHCOR", "CH"]),
            ]
        ),
    ),
    dict(
        at_elem_name="CH1YG2C30A",
        pml_elem_name="C30_C1",
        RB_pvname_d={"y": "SR:C30-MG{PS:CH1A}I:Ps2DCCT1-I"},
        SP_pvname_d={"y": "SR:C30-MG{PS:CH1A}I:Sp2-SP"},
        sim_RB_pvsuffix_d={"y": "C30_C1_Y_RB"},
        sim_SP_pvsuffix_d={"y": "C30_C1_Y_SP"},
        conv_func_specs={
            "y_I_to_y_angle": {
                "name": "poly1d",
                "args": [[-0.045499498547631176, 0.0]],
            },
            "y_angle_to_y_I": {
                "name": "poly1d",
                "args": [[-21.978264198959234, 0.0]],
            },
        },
        tags=KeyValueTagList(
            tags=[
                common_tags["cell_str"],
                KeyValueTag(key="family", values=["SCOR", "SVCOR", "CH"]),
            ]
        ),
    ),
    dict(
        at_elem_name="CH2XG2C30A",
        pml_elem_name="C30_C2",
        RB_pvname_d={"x": "SR:C30-MG{PS:CH2A}I:Ps1DCCT1-I"},
        SP_pvname_d={"x": "SR:C30-MG{PS:CH2A}I:Sp1-SP"},
        sim_RB_pvsuffix_d={"x": "C30_C2_X_RB"},
        sim_SP_pvsuffix_d={"x": "C30_C2_X_SP"},
        conv_func_specs={
            "x_I_to_x_angle": {
                "name": "poly1d",
                "args": [[-0.054294962028959434, 0.0]],
            },
            "x_angle_to_x_I": {
                "name": "poly1d",
                "args": [[-18.417915081451344, 0.0]],
            },
        },
        tags=KeyValueTagList(
            tags=[
                common_tags["cell_str"],
                KeyValueTag(key="family", values=["SCOR", "SHCOR", "CH"]),
            ]
        ),
    ),
    dict(
        at_elem_name="CH2YG2C30A",
        pml_elem_name="C30_C2",
        RB_pvname_d={"y": "SR:C30-MG{PS:CH2A}I:Ps2DCCT1-I"},
        SP_pvname_d={"y": "SR:C30-MG{PS:CH2A}I:Sp2-SP"},
        sim_RB_pvsuffix_d={"y": "C30_C2_Y_RB"},
        sim_SP_pvsuffix_d={"y": "C30_C2_Y_SP"},
        conv_func_specs={
            "y_I_to_y_angle": {
                "name": "poly1d",
                "args": [[-0.05076525187516862, 0.0]],
            },
            "y_angle_to_y_I": {
                "name": "poly1d",
                "args": [[-19.698513511939083, 0.0]],
            },
        },
        tags=KeyValueTagList(
            tags=[
                common_tags["cell_str"],
                KeyValueTag(key="family", values=["SCOR", "SVCOR", "CH"]),
            ]
        ),
    ),
]

# %%
for d in cor_info_list:
    process_corrector_definition(
        pv_elem_maps,
        simpv_elem_maps,
        simpv_defs,
        elem_defs,
        d["at_elem_name"],
        d["pml_elem_name"],
        d["RB_pvname_d"],
        d["SP_pvname_d"],
        d["sim_RB_pvsuffix_d"],
        d["sim_SP_pvsuffix_d"],
        d["conv_func_specs"],
        d["tags"],
    )

# %% [markdown]
# # Quad definitions


# %%
def process_quad_definition(
    pv_elem_maps: Dict,
    simpv_elem_maps: Dict,
    simpv_defs: Dict,
    elem_defs: Dict,
    at_elem_name: str,
    pml_elem_name: str,
    RB_pvname: str,
    SP_pvname: str,
    sim_RB_pvsuffix: str,
    sim_SP_pvsuffix: str,
    conv_func_specs: Dict[str, Dict],
    tags: KeyValueTagList | None = None,
):

    matched_indexes = at.get_uint32_index(lattice, at_elem_name)
    assert len(matched_indexes) == 1
    lattice_index = int(
        matched_indexes[0]
    )  # Avoid numpy.uint32 that prevents saving into JSON/YAML
    elem = lattice[lattice_index]
    elem_type = elem.definition[0]

    s_b_array = at.get_s_pos(lattice, matched_indexes)
    s_e_array = s_b_array + np.array([lattice[i].Length for i in matched_indexes])
    s_lists = dict(element=SPositionList(b=s_b_array.tolist(), e=s_e_array.tolist()))

    if tags is None:
        tags = KeyValueTagList()
    assert isinstance(tags, KeyValueTagList)

    if False:
        info_to_check = dict(
            elem_name=at_elem_name, elem_type=elem_type, lattice_index=lattice_index
        )

    pdev_standard_RB_def = MachineModeSpecContainer(
        LIVE=standard_RB(), DT=standard_RB(), SIM=standard_RB()
    )

    SP_RB_diffs = {
        repr: SP_RB_Diff_Def(
            RB_channel=f"{repr}_RB",
            abs_tol=abs_tol,
            rel_tol=None,
            timeout=Q_("10 s"),
            settle_time=Q_("2 s"),
            poll_time=Q_("0.5 s"),
        )
        for repr, abs_tol in [
            ("I", Q_("0.01 A")),
            ("K1L", Q_("5e-4 m^{-1}")),
            ("K1", Q_("1e-4 m^{-2}")),
        ]
    }
    pdev_SP_def_d = {
        repr: MachineModeSpecContainer(
            LIVE=standard_SP(
                set_wait_method="fixed_wait_time",
                SP_RB_diff=SP_RB_diffs[repr],
                fixed_wait_time=FixedWaitTime(dt=Q_("1.0 s")),
            ),
            DT=standard_SP(),
            SIM=standard_SP(),
        )
        for repr in ["I", "K1L", "K1"]
    }

    assert RB_pvname not in pv_elem_maps
    assert SP_pvname not in pv_elem_maps

    assert sim_RB_pvsuffix not in simpv_elem_maps
    assert sim_SP_pvsuffix not in simpv_elem_maps

    ext_SP_pvid = "extpv_I_SP"
    ext_RB_pvid = "extpv_I_RB"
    int_RB_pvid = "intpv_K1_RB"
    int_SP_pvid = "intpv_K1_SP"

    template_map_d = dict(
        elem_names=[pml_elem_name],
        handle=None,
        pvid_in_elem=None,
        DT_pvname=None,
        DT_pvunit=None,
    )

    pv_elem_dict_SP = deepcopy(template_map_d)
    pv_elem_dict_SP["pvid_in_elem"] = ext_SP_pvid
    pv_elem_dict_SP["handle"] = "SP"
    pv_elem_dict_SP["DT_pvname"] = (
        f"{USERNAME}:{SP_pvname}"  # PV name for DT (Digital Twin)
    )
    pv_elem_dict_SP["pvunit"] = "A"
    pv_elem_dict_SP["DT_pvunit"] = "A"

    pv_elem_dict_RB = deepcopy(template_map_d)
    pv_elem_dict_RB["pvid_in_elem"] = ext_RB_pvid
    pv_elem_dict_RB["handle"] = "RB"
    pv_elem_dict_RB["DT_pvname"] = (
        f"{USERNAME}:{RB_pvname}"  # PV name for DT (Digital Twin)
    )
    pv_elem_dict_RB["pvunit"] = "A"
    pv_elem_dict_RB["DT_pvunit"] = "A"

    template_map_d = dict(elem_names=[pml_elem_name], handle=None, pvid_in_elem=None)

    simpv_elem_dict_RB = deepcopy(template_map_d)
    simpv_elem_dict_RB["pvid_in_elem"] = int_RB_pvid
    simpv_elem_dict_RB["handle"] = "RB"
    simpv_elem_dict_RB["pvunit"] = "m^{-2}"

    simpv_elem_dict_SP = deepcopy(template_map_d)
    simpv_elem_dict_SP["pvid_in_elem"] = int_SP_pvid
    simpv_elem_dict_SP["handle"] = "SP"
    simpv_elem_dict_SP["pvunit"] = "m^{-2}"

    assert sim_RB_pvsuffix not in simpv_defs
    simpv_defs[sim_RB_pvsuffix] = dict(pvclass="QuadrupoleSimPV", args=[lattice_index])
    assert sim_SP_pvsuffix not in simpv_defs
    simpv_defs[sim_SP_pvsuffix] = dict(pvclass="QuadrupoleSimPV", args=[lattice_index])

    elem_def = _get_blank_elem_def(elem_defs, pml_elem_name)

    elem_def.s_lists = s_lists
    elem_def.tags = tags

    repr_I = "I"
    repr_K1 = "K1"
    repr_K1L = "K1L"

    elem_def.repr_units[repr_I] = "A"
    elem_def.repr_units[repr_K1] = "m^{-2}"
    elem_def.repr_units[repr_K1L] = "m^{-1}"

    elem_def.pvid_to_repr_map.ext[ext_SP_pvid] = repr_I
    elem_def.pvid_to_repr_map.ext[ext_RB_pvid] = repr_I
    elem_def.pvid_to_repr_map.int[int_SP_pvid] = repr_K1
    elem_def.pvid_to_repr_map.int[int_RB_pvid] = repr_K1

    for repr in [repr_I, repr_K1, repr_K1L]:
        ext_get_d = dict(input_pvs=[ext_RB_pvid])
        int_get_d = dict(input_pvs=[int_RB_pvid])
        if repr != repr_I:
            ext_get_d["conv_spec_name"] = f"{repr_I}_to_{repr}"
        if repr != repr_K1:
            int_get_d["conv_spec_name"] = f"{repr_K1}_to_{repr}"
        elem_def.channel_map[f"{repr}_RB"] = ChannelSpec(
            handle="RB",
            HiLv_reprs=[repr],
            ext=PVMapping(get=GetPVMapping(**ext_get_d)),
            int=PVMapping(get=GetPVMapping(**int_get_d)),
            pdev_def=pdev_standard_RB_def,
        )

        ext_get_d = dict(input_pvs=[ext_SP_pvid])
        int_get_d = dict(input_pvs=[int_SP_pvid])
        ext_put_d = dict(output_pvs=[ext_SP_pvid])
        int_put_d = dict(output_pvs=[int_SP_pvid])
        if repr != repr_I:
            ext_get_d["conv_spec_name"] = f"{repr_I}_to_{repr}"
            ext_put_d["conv_spec_name"] = f"{repr}_to_{repr_I}"
        if repr != repr_K1:
            int_get_d["conv_spec_name"] = f"{repr_K1}_to_{repr}"
            int_put_d["conv_spec_name"] = f"{repr}_to_{repr_K1}"
        elem_def.channel_map[f"{repr}_SP"] = ChannelSpec(
            handle="SP",
            HiLv_reprs=[repr],
            ext=PVMapping(get=GetPVMapping(**ext_get_d), put=PutPVMapping(**ext_put_d)),
            int=PVMapping(get=GetPVMapping(**int_get_d), put=PutPVMapping(**int_put_d)),
            pdev_def=pdev_SP_def_d[repr],
        )

    for spec_name, spec in conv_func_specs.items():
        elem_def.func_specs[spec_name] = FunctionSpec(**spec)

    pv_elem_maps[RB_pvname] = pv_elem_dict_RB
    if pv_elem_dict_SP is not None:
        pv_elem_maps[SP_pvname] = pv_elem_dict_SP

    simpv_elem_maps[sim_RB_pvsuffix] = simpv_elem_dict_RB
    if simpv_elem_dict_SP is not None:
        simpv_elem_maps[sim_SP_pvsuffix] = simpv_elem_dict_SP


# %%
quad_info_list = [
    dict(
        at_elem_name="QH1G2C30A",
        pml_elem_name="C30_QH1",
        RB_pvname="SR:C30-MG{PS:QH1A}I:Ps1DCCT1-I",
        SP_pvname="SR:C30-MG{PS:QH1A}I:Sp1-SP",
        sim_RB_pvsuffix="C30_QH1_K1_RB",
        sim_SP_pvsuffix="C30_QH1_K1_SP",
        conv_func_specs={
            "I_to_K1": {
                "name": "pchip_interp",
                # fmt: off
                "args": [
                    np.array([0.0, 9.99792, 19.99727, 29.99301, 39.99211,
                        49.99207, 59.99186, 69.98832, 79.98739, 89.98651,
                        99.98642, 109.98308, 114.98354, 119.98236, 124.98021,
                        129.98137, 134.97997, 139.97777]),
                    np.array([0.0, -0.17021670190231752, -0.3359103513970845,
                        -0.5027023487285381, -0.669967737524001, -0.8372302748609871,
                        -1.0040900996169722, -1.170136702043565, -1.3351687080419503,
                        -1.4984868443781048, -1.6591052650423832, -1.8151508328481472,
                        -1.8900354569503879, -1.9613633659609853, -2.0268947679741904,
                        -2.0849237233623508, -2.136283115476966, -2.1827279306257683])],
                # fmt: on
            },
            "K1_to_I": {
                "name": "pchip_interp",
                # fmt: off
                "args": [
                    np.array([-2.1827279306257683, -2.136283115476966, -2.0849237233623508,
                        -2.0268947679741904, -1.9613633659609853, -1.8900354569503879,
                        -1.8151508328481472, -1.6591052650423832, -1.4984868443781048,
                        -1.3351687080419503, -1.170136702043565, -1.0040900996169722,
                        -0.8372302748609871, -0.669967737524001, -0.5027023487285381,
                        -0.3359103513970845, -0.17021670190231752, -0.0]),
                    np.array([139.97777, 134.97997, 129.98137, 124.98021, 119.98236,
                        114.98354, 109.98308, 99.98642, 89.98651, 79.98739, 69.98832,
                        59.99186, 49.99207, 39.99211, 29.99301, 19.99727, 9.99792,
                        -1.003537530852583e-15])],
                # fmt: on
            },
            "I_to_K1L": {
                "name": "pchip_interp",
                # fmt: off
                "args": [
                    np.array([0.0, 9.99792, 19.99727, 29.99301, 39.99211, 49.99207,
                        59.99186, 69.98832, 79.98739, 89.98651, 99.98642, 109.98308,
                        114.98354, 119.98236, 124.98021, 129.98137, 134.97997,
                        139.97777]),
                    np.array([0.0, -0.0456180761098211, -0.09002397417441864,
                        -0.13472422945924822, -0.17955135365643227, -0.22437771366274456,
                        -0.26909614669734855, -0.3135966361476754, -0.3578252137552427,
                        -0.4015944742933321, -0.4446402110313587, -0.48646042320330346,
                        -0.506529502462704, -0.5256453820775441, -0.5432077978170831,
                        -0.5587595578611101, -0.5725238749478269, -0.5849710854077059])],
                # fmt: on
            },
            "K1L_to_I": {
                "name": "pchip_interp",
                # fmt: off
                "args": [
                    np.array([-0.5849710854077059, -0.5725238749478269,
                        -0.5587595578611101, -0.5432077978170831, -0.5256453820775441,
                        -0.506529502462704, -0.48646042320330346, -0.4446402110313587,
                        -0.4015944742933321, -0.3578252137552427, -0.3135966361476754,
                        -0.26909614669734855, -0.22437771366274456, -0.17955135365643227,
                        -0.13472422945924822, -0.09002397417441864, -0.0456180761098211,
                        -0.0]),
                    np.array(
                        [139.97777, 134.97997, 129.98137, 124.98021, 119.98236,
                        114.98354, 109.98308, 99.98642, 89.98651, 79.98739, 69.98832,
                        59.99186, 49.99207, 39.99211, 29.99301, 19.99727, 9.99792,
                        -1.003537530852583e-15])],
                # fmt: on
            },
            "K1_to_K1L": {"name": "poly1d", "args": [[0.268, 0.0]]},
            "K1L_to_K1": {"name": "poly1d", "args": [[3.731343283582089, 0.0]]},
        },
        tags=KeyValueTagList(
            tags=[
                KeyValueTag(key="cell_str", values=["C30"]),
                KeyValueTag(key="family", values=["QUAD", "QH1"]),
            ]
        ),
    ),
    dict(
        at_elem_name="QH2G2C02A",
        pml_elem_name="C02_QH2",
        RB_pvname="SR:C02-MG{PS:QH2A}I:Ps1DCCT1-I",
        SP_pvname="SR:C02-MG{PS:QH2A}I:Sp1-SP",
        sim_RB_pvsuffix="C02_QH2_K1_RB",
        sim_SP_pvsuffix="C02_QH2_K1_SP",
        conv_func_specs={
            "I_to_K1": {
                "name": "pchip_interp",
                # fmt: off
                "args": [
                    np.array([0.0, 9.99789, 19.99727, 29.99303, 39.99216, 49.99205,
                        59.99183, 69.98826, 79.98738, 89.98652, 99.98647, 109.98301,
                        114.98358, 119.98233, 124.98016, 129.98137, 134.97989,
                        139.9777]),
                    np.array([0.0, 0.16638347037914303, 0.32921320025067985,
                        0.49281725769841617, 0.6566507934398196, 0.8202534605199788,
                        0.9830685564374275, 1.1446959921631217, 1.3046984418931835,
                        1.462105537212522, 1.6154660803465917, 1.7622649948132814,
                        1.8320389805134167, 1.898193574852707, 1.959600505066804,
                        2.0149070584783697, 2.0642803848022506, 2.1089894061963905])],
                # fmt: on
            },
            "K1_to_I": {
                "name": "pchip_interp",
                # fmt: off
                "args": [
                    np.array([0.0, 0.16638347037914303, 0.32921320025067985,
                        0.49281725769841617, 0.6566507934398196, 0.8202534605199788,
                        0.9830685564374275, 1.1446959921631217, 1.3046984418931835,
                        1.462105537212522, 1.6154660803465917, 1.7622649948132814,
                        1.8320389805134167, 1.898193574852707, 1.959600505066804,
                        2.0149070584783697, 2.0642803848022506, 2.1089894061963905]),
                    np.array([0.0, 9.99789, 19.99727, 29.99303, 39.99216, 49.99205,
                        59.99183, 69.98826, 79.98738, 89.98652, 99.98647, 109.98301,
                        114.98358, 119.98233, 124.98016, 129.98137, 134.97989,
                        139.9777])],
                # fmt: on
            },
            "I_to_K1L": {
                "name": "pchip_interp",
                # fmt: off
                "args": [
                    np.array([0.0, 9.99789, 19.99727, 29.99303, 39.99216, 49.99205,
                        59.99183, 69.98826, 79.98738, 89.98652, 99.98647, 109.98301,
                        114.98358, 119.98233, 124.98016, 129.98137, 134.97989,
                        139.9777]),
                    np.array([0.0, 0.07653639637440579, 0.15143807211531274,
                        0.22669593854127146, 0.302059364982317, 0.37731659183919025,
                        0.45221153596121666, 0.526560156395036, 0.6001612832708645,
                        0.6725685471177602, 0.7431143969594322, 0.8106418976141094,
                        0.8427379310361718, 0.8731690444322453, 0.9014162323307299,
                        0.9268572469000501, 0.9495689770090353, 0.9701351268503396])],
                # fmt: on
            },
            "K1L_to_I": {
                "name": "pchip_interp",
                # fmt: off
                "args": [
                    np.array([0.0, 0.07653639637440579, 0.15143807211531274,
                        0.22669593854127146, 0.302059364982317, 0.37731659183919025,
                        0.45221153596121666, 0.526560156395036, 0.6001612832708645,
                        0.6725685471177602, 0.7431143969594322, 0.8106418976141094,
                        0.8427379310361718, 0.8731690444322453, 0.9014162323307299,
                        0.9268572469000501, 0.9495689770090353, 0.9701351268503396]),
                    np.array([0.0, 9.99789, 19.99727, 29.99303, 39.99216, 49.99205,
                        59.99183, 69.98826, 79.98738, 89.98652, 99.98647, 109.98301,
                        114.98358, 119.98233, 124.98016, 129.98137, 134.97989,
                        139.9777])],
                # fmt: on
            },
            "K1_to_K1L": {"name": "poly1d", "args": [[0.46, 0.0]]},
            "K1L_to_K1": {"name": "poly1d", "args": [[2.1739130434782608, 0.0]]},
        },
        tags=KeyValueTagList(
            tags=[
                KeyValueTag(key="cell_str", values=["C02"]),
                KeyValueTag(key="family", values=["QUAD", "QH2"]),
            ]
        ),
    ),
]

# %%
for d in quad_info_list:
    process_quad_definition(
        pv_elem_maps,
        simpv_elem_maps,
        simpv_defs,
        elem_defs,
        d["at_elem_name"],
        d["pml_elem_name"],
        d["RB_pvname"],
        d["SP_pvname"],
        d["sim_RB_pvsuffix"],
        d["sim_SP_pvsuffix"],
        d["conv_func_specs"],
        d["tags"],
    )

# %% [markdown]
# # Sextupole definitions


# %%
def process_sext_definition(
    pv_elem_maps: Dict,
    simpv_elem_maps: Dict,
    simpv_defs: Dict,
    elem_defs: Dict,
    at_elem_name: str,
    pml_elem_name: str,
    RB_pvname: str,
    SP_pvname: str,
    sim_RB_pvsuffix: str,
    sim_SP_pvsuffix: str,
    conv_func_specs: List[Dict],
    tags: KeyValueTagList | None = None,
):

    matched_indexes = at.get_uint32_index(lattice, at_elem_name)
    assert len(matched_indexes) == 1
    lattice_index = int(
        matched_indexes[0]
    )  # Avoid numpy.uint32 that prevents saving into JSON/YAML
    elem = lattice[lattice_index]
    elem_type = elem.definition[0]

    s_b_array = at.get_s_pos(lattice, matched_indexes)
    s_e_array = s_b_array + np.array([lattice[i].Length for i in matched_indexes])
    s_lists = dict(element=SPositionList(b=s_b_array.tolist(), e=s_e_array.tolist()))

    if tags is None:
        tags = KeyValueTagList()
    assert isinstance(tags, KeyValueTagList)

    if False:
        info_to_check = dict(
            elem_name=at_elem_name, elem_type=elem_type, lattice_index=lattice_index
        )

    pdev_standard_RB_def = MachineModeSpecContainer(
        LIVE=standard_RB(), DT=standard_RB(), SIM=standard_RB()
    )

    SP_RB_diffs = {
        repr: SP_RB_Diff_Def(
            RB_channel=f"{repr}_RB",
            abs_tol=abs_tol,
            rel_tol=None,
            timeout=Q_("10 s"),
            settle_time=Q_("2 s"),
            poll_time=Q_("0.5 s"),
        )
        for repr, abs_tol in [
            ("I", Q_("0.01 A")),
            ("K2L", Q_("5e-4 m^{-2}")),
            ("K2", Q_("1e-4 m^{-3}")),
        ]
    }
    pdev_SP_def_d = {
        repr: MachineModeSpecContainer(
            LIVE=standard_SP(
                set_wait_method="fixed_wait_time",
                SP_RB_diff=SP_RB_diffs[repr],
                fixed_wait_time=FixedWaitTime(dt=Q_("1.0 s")),
            ),
            DT=standard_SP(),
            SIM=standard_SP(),
        )
        for repr in ["I", "K2L", "K2"]
    }

    assert RB_pvname not in pv_elem_maps
    assert SP_pvname not in pv_elem_maps

    assert sim_RB_pvsuffix not in simpv_elem_maps
    assert sim_SP_pvsuffix not in simpv_elem_maps

    ext_SP_pvid = "extpv_I_SP"
    ext_RB_pvid = "extpv_I_RB"
    int_SP_pvid = "intpv_K2_SP"
    int_RB_pvid = "intpv_K2_RB"

    template_map_d = dict(
        elem_names=[pml_elem_name],
        handle=None,
        pvid_in_elem=None,
        DT_pvname=None,
        DT_pvunit=None,
    )

    pv_elem_dict_SP = deepcopy(template_map_d)
    pv_elem_dict_SP["pvid_in_elem"] = ext_SP_pvid
    pv_elem_dict_SP["handle"] = "SP"
    pv_elem_dict_SP["DT_pvname"] = (
        f"{USERNAME}:{SP_pvname}"  # PV name for DT (Digital Twin)
    )
    pv_elem_dict_SP["pvunit"] = "A"
    pv_elem_dict_SP["DT_pvunit"] = "A"

    pv_elem_dict_RB = deepcopy(template_map_d)
    pv_elem_dict_RB["pvid_in_elem"] = ext_RB_pvid
    pv_elem_dict_RB["handle"] = "RB"
    pv_elem_dict_RB["DT_pvname"] = (
        f"{USERNAME}:{RB_pvname}"  # PV name for DT (Digital Twin)
    )
    pv_elem_dict_RB["pvunit"] = "A"
    pv_elem_dict_RB["DT_pvunit"] = "A"

    template_map_d = dict(elem_names=[pml_elem_name], handle=None, pvid_in_elem=None)

    simpv_elem_dict_RB = deepcopy(template_map_d)
    simpv_elem_dict_RB["pvid_in_elem"] = int_RB_pvid
    simpv_elem_dict_RB["handle"] = "RB"
    simpv_elem_dict_RB["pvunit"] = "m^{-3}"

    simpv_elem_dict_SP = deepcopy(template_map_d)
    simpv_elem_dict_SP["pvid_in_elem"] = int_SP_pvid
    simpv_elem_dict_SP["handle"] = "SP"
    simpv_elem_dict_SP["pvunit"] = "m^{-3}"

    assert sim_RB_pvsuffix not in simpv_defs
    simpv_defs[sim_RB_pvsuffix] = dict(pvclass="SextupoleSimPV", args=[lattice_index])

    assert sim_SP_pvsuffix not in simpv_defs
    simpv_defs[sim_SP_pvsuffix] = dict(pvclass="SextupoleSimPV", args=[lattice_index])

    elem_def = _get_blank_elem_def(elem_defs, pml_elem_name)

    elem_def.s_lists = s_lists
    elem_def.tags = tags

    repr_I = "I"
    repr_K2 = "K2"
    repr_K2L = "K2L"

    elem_def.repr_units[repr_I] = "A"
    elem_def.repr_units[repr_K2] = "m^{-3}"
    elem_def.repr_units[repr_K2L] = "m^{-2}"

    elem_def.pvid_to_repr_map.ext[ext_SP_pvid] = repr_I
    elem_def.pvid_to_repr_map.ext[ext_RB_pvid] = repr_I
    elem_def.pvid_to_repr_map.int[int_SP_pvid] = repr_K2
    elem_def.pvid_to_repr_map.int[int_RB_pvid] = repr_K2

    for repr in [repr_I, repr_K2, repr_K2L]:
        ext_get_d = dict(input_pvs=[ext_RB_pvid])
        int_get_d = dict(input_pvs=[int_RB_pvid])
        if repr != repr_I:
            ext_get_d["conv_spec_name"] = f"{repr_I}_to_{repr}"
        if repr != repr_K2:
            int_get_d["conv_spec_name"] = f"{repr_K2}_to_{repr}"
        elem_def.channel_map[f"{repr}_RB"] = ChannelSpec(
            handle="RB",
            HiLv_reprs=[repr],
            ext=PVMapping(get=GetPVMapping(**ext_get_d)),
            int=PVMapping(get=GetPVMapping(**int_get_d)),
            pdev_def=pdev_standard_RB_def,
        )

        ext_get_d = dict(input_pvs=[ext_SP_pvid])
        int_get_d = dict(input_pvs=[int_SP_pvid])
        ext_put_d = dict(output_pvs=[ext_SP_pvid])
        int_put_d = dict(output_pvs=[int_SP_pvid])
        if repr != repr_I:
            ext_get_d["conv_spec_name"] = f"{repr_I}_to_{repr}"
            ext_put_d["conv_spec_name"] = f"{repr}_to_{repr_I}"
        if repr != repr_K2:
            int_get_d["conv_spec_name"] = f"{repr_K2}_to_{repr}"
            int_put_d["conv_spec_name"] = f"{repr}_to_{repr_K2}"
        elem_def.channel_map[f"{repr}_SP"] = ChannelSpec(
            handle="SP",
            HiLv_reprs=[repr],
            ext=PVMapping(
                get=GetPVMapping(**ext_get_d),
                put=PutPVMapping(**ext_put_d),
            ),
            int=PVMapping(
                get=GetPVMapping(**int_get_d),
                put=PutPVMapping(**int_put_d),
            ),
            pdev_def=pdev_SP_def_d[repr],
        )

    for spec_name, spec in conv_func_specs.items():
        elem_def.func_specs[spec_name] = FunctionSpec(**spec)

    pv_elem_maps[RB_pvname] = pv_elem_dict_RB
    if pv_elem_dict_SP is not None:
        pv_elem_maps[SP_pvname] = pv_elem_dict_SP

    simpv_elem_maps[sim_RB_pvsuffix] = simpv_elem_dict_RB
    if simpv_elem_dict_SP is not None:
        simpv_elem_maps[sim_SP_pvsuffix] = simpv_elem_dict_SP


# %%
common_tags = dict(
    cell_str=KeyValueTag(key="cell_str", values=["C30"]),
)

sext_info_list = [
    dict(
        at_elem_name="SH1G2C30A",
        pml_elem_name="C30_SH1",
        RB_pvname="SR:C30-MG{PS:SH1-P2}I:Ps1DCCT1-I",
        SP_pvname="SR:C30-MG{PS:SH1-P2}I:Sp1-SP",
        sim_RB_pvsuffix="C30_SH1_K2_RB",
        sim_SP_pvsuffix="C30_SH1_K2_SP",
        conv_func_specs={
            "I_to_K2": {
                "name": "pchip_interp",
                # fmt: off
                "args": [
                    np.array([0.0, 9.998, 19.99731, 29.99719, 39.99452, 49.99449,
                        54.99593, 59.99394, 64.9954, 69.99395, 74.99271, 79.99358,
                        84.99239, 89.99333, 94.99182, 99.99295, 104.99144,
                        109.99045]),
                    np.array([0.0, 2.1614170368398837, 4.200404477650452,
                        6.26175199044168, 8.335026733036429, 10.413578770346678,
                        11.452735807435879, 12.490280843041559, 13.529632973245715,
                        14.568437706875974, 15.601937440853234, 16.636188988540578,
                        17.669717166091843, 18.70108779624318, 19.731011401021547,
                        20.75804814912229, 21.78539358649316, 22.811419935849624])],
                # fmt: on
            },
            "K2_to_I": {
                "name": "pchip_interp",
                # fmt: off
                "args": [
                    np.array([0.0, 2.1614170368398837, 4.200404477650452,
                        6.26175199044168, 8.335026733036429, 10.413578770346678,
                        11.452735807435879, 12.490280843041559, 13.529632973245715,
                        14.568437706875974, 15.601937440853234, 16.636188988540578,
                        17.669717166091843, 18.70108779624318, 19.731011401021547,
                        20.75804814912229, 21.78539358649316, 22.811419935849624]),
                    np.array([0.0, 9.998, 19.99731, 29.99719, 39.99452, 49.99449,
                        54.99593, 59.99394, 64.9954, 69.99395, 74.99271, 79.99358,
                        84.99239, 89.99333, 94.99182, 99.99295, 104.99144,
                        109.99045000000001])],
                # fmt: on
            },
            "I_to_K2L": {
                "name": "pchip_interp",
                # fmt: off
                "args": [
                    np.array([0.0, 9.998, 19.99731, 29.99719, 39.99452, 49.99449,
                        54.99593, 59.99394, 64.9954, 69.99395, 74.99271, 79.99358,
                        84.99239, 89.99333, 94.99182, 99.99295, 104.99144,
                        109.99045]),
                    np.array([0.0, 0.43228340736797677, 0.8400808955300905,
                        1.2523503980883361, 1.6670053466072858, 2.0827157540693357,
                        2.2905471614871757, 2.498056168608312, 2.705926594649143,
                        2.913687541375195, 3.120387488170647, 3.327237797708116,
                        3.533943433218369, 3.7402175592486357, 3.9462022802043095,
                        4.151609629824458, 4.3570787172986325, 4.562283987169925])],
                # fmt: on
            },
            "K2L_to_I": {
                "name": "pchip_interp",
                # fmt: off
                "args": [
                    np.array([0.0, 0.43228340736797677, 0.8400808955300905,
                        1.2523503980883361, 1.6670053466072858, 2.0827157540693357,
                        2.2905471614871757, 2.498056168608312, 2.705926594649143,
                        2.913687541375195, 3.120387488170647, 3.327237797708116,
                        3.533943433218369, 3.7402175592486357, 3.9462022802043095,
                        4.151609629824458, 4.3570787172986325, 4.562283987169925]),
                    np.array([0.0, 9.998, 19.99731, 29.99719, 39.99452, 49.99449,
                        54.99593, 59.99394, 64.9954, 69.99395, 74.99271, 79.99358,
                        84.99239, 89.99333, 94.99182, 99.99295, 104.99144,
                        109.99045000000001])],
                # fmt: on
            },
            "K2_to_K2L": {"name": "poly1d", "args": [[0.2, 0.0]]},
            "K2L_to_K2": {"name": "poly1d", "args": [[5.0, 0.0]]},
        },
        tags=KeyValueTagList(
            tags=[
                common_tags["cell_str"],
                KeyValueTag(key="family", values=["SEXT", "SH1"]),
            ]
        ),
    ),
    dict(
        at_elem_name="SM1G4C30B",
        pml_elem_name="C30_SM1B",
        RB_pvname="SR:C02-MG{PS:SM1B-P2}I:Ps1DCCT1-I",
        SP_pvname="SR:C02-MG{PS:SM1B-P2}I:Sp1-SP",
        sim_RB_pvsuffix="C30_SM1B_K2_RB",
        sim_SP_pvsuffix="C30_SM1B_K2_SP",
        conv_func_specs={
            "I_to_K2": {
                "name": "pchip_interp",
                # fmt: off
                "args": [
                    np.array([0.0, 9.9975, 19.99691, 29.9971, 39.99492, 49.9951,
                        54.99666, 59.99509, 64.99646, 69.9953, 74.99396, 79.99524,
                        84.99395, 89.99498, 94.99391, 99.99449, 104.99335,
                        109.99232]),
                    np.array([0.0, -2.160632407607249, -4.201669669287124,
                        -6.263552049081986, -8.337748713120195, -10.41523525511305,
                        -11.456247199207814, -12.494481364684557, -13.529840651471732,
                        -14.570094969453939, -15.60296097681778, -16.64089362080598,
                        -17.676128162800968, -18.70694582011935, -19.736285703900815,
                        -20.76437103430962, -21.794110466111498, -22.823022034156406])],
                # fmt: on
            },
            "K2_to_I": {
                "name": "pchip_interp",
                # fmt: off
                "args": [
                    np.array([-22.823022034156406, -21.794110466111498,
                        -20.76437103430962, -19.736285703900815, -18.70694582011935,
                        -17.676128162800968, -16.64089362080598, -15.60296097681778,
                        -14.570094969453939, -13.529840651471732, -12.494481364684557,
                        -11.456247199207814, -10.41523525511305, -8.337748713120195,
                        -6.263552049081986, -4.201669669287124, -2.160632407607249,
                        -0.0]),
                    np.array([109.99232, 104.99335, 99.99449, 94.99391, 89.99498,
                        84.99395, 79.99524, 74.99396, 69.9953, 64.99646, 59.99509,
                        54.99666, 49.9951, 39.99492, 29.9971, 19.99691, 9.9975,
                        -5.724587470723463e-17])],
                # fmt: on
            },
            "I_to_K2L": {
                "name": "pchip_interp",
                # fmt: off
                "args": [
                    np.array([0.0, 9.9975, 19.99691, 29.9971, 39.99492, 49.9951,
                        54.99666, 59.99509, 64.99646, 69.9953, 74.99396, 79.99524,
                        84.99395, 89.99498, 94.99391, 99.99449, 104.99335,
                        109.99232]),
                    np.array([0.0, -0.43212648152144983, -0.8403339338574248,
                        -1.2527104098163973, -1.6675497426240393, -2.0830470510226102,
                        -2.291249439841563, -2.4988962729369115, -2.7059681302943464,
                        -2.914018993890788, -3.1205921953635563, -3.3281787241611958,
                        -3.535225632560194, -3.741389164023871, -3.9472571407801635,
                        -4.152874206861924, -4.3588220932223, -4.564604406831282])],
                # fmt: on
            },
            "K2L_to_I": {
                "name": "pchip_interp",
                # fmt: off
                "args": [
                    np.array([-4.564604406831282, -4.3588220932223, -4.152874206861924,
                        -3.9472571407801635, -3.741389164023871, -3.535225632560194,
                        -3.3281787241611958, -3.1205921953635563, -2.914018993890788,
                        -2.7059681302943464, -2.4988962729369115, -2.291249439841563,
                        -2.0830470510226102, -1.6675497426240393, -1.2527104098163973,
                        -0.8403339338574248, -0.43212648152144983, -0.0]),
                    np.array([109.99232, 104.99335, 99.99449, 94.99391, 89.99498,
                        84.99395, 79.99524, 74.99396, 69.9953, 64.99646, 59.99509,
                        54.99666, 49.9951, 39.99492, 29.9971, 19.99691, 9.9975,
                        -5.724587470723463e-17])],
                # fmt: on
            },
            "K2_to_K2L": {"name": "poly1d", "args": [[0.2, 0.0]]},
            "K2L_to_K2": {"name": "poly1d", "args": [[5.0, 0.0]]},
        },
        tags=KeyValueTagList(
            tags=[
                common_tags["cell_str"],
                KeyValueTag(key="family", values=["SEXT", "SM1"]),
            ]
        ),
    ),
]

# %%
for d in sext_info_list:
    process_sext_definition(
        pv_elem_maps,
        simpv_elem_maps,
        simpv_defs,
        elem_defs,
        d["at_elem_name"],
        d["pml_elem_name"],
        d["RB_pvname"],
        d["SP_pvname"],
        d["sim_RB_pvsuffix"],
        d["sim_SP_pvsuffix"],
        d["conv_func_specs"],
        d["tags"],
    )

# %% [markdown]
# # RF frequency element definition


# %%
def process_rf_freq_definition(
    pv_elem_maps: Dict,
    simpv_elem_maps: Dict,
    simpv_defs: Dict,
    elem_defs: Dict,
    pml_elem_name: str,
    RB_pvname: str,
    SP_pvname: str,
    sim_RB_pvsuffix: str,
    sim_SP_pvsuffix: str,
):
    s_lists = dict(element=None)

    if False:
        info_to_check = {}

    pdev_standard_RB_def = MachineModeSpecContainer(
        LIVE=standard_RB(), DT=standard_RB(), SIM=standard_RB()
    )

    assert RB_pvname not in pv_elem_maps
    assert SP_pvname not in pv_elem_maps

    assert sim_RB_pvsuffix not in simpv_elem_maps
    assert sim_SP_pvsuffix not in simpv_elem_maps

    ext_SP_pvid = "extpv_rf_freq_SP"
    ext_RB_pvid = "extpv_rf_freq_RB"
    int_SP_pvid = "intpv_rf_freq_SP"
    int_RB_pvid = "intpv_rf_freq_RB"

    template_map_d = dict(
        elem_names=[pml_elem_name],
        handle=None,
        pvid_in_elem=None,
        DT_pvname=None,
        DT_pvunit=None,
    )

    pv_elem_dict_SP = deepcopy(template_map_d)
    pv_elem_dict_SP["pvid_in_elem"] = ext_SP_pvid
    pv_elem_dict_SP["handle"] = "SP"
    pv_elem_dict_SP["DT_pvname"] = (
        f"{USERNAME}:{SP_pvname}"  # PV name for DT (Digital Twin)
    )
    pv_elem_dict_SP["pvunit"] = "GHz"
    pv_elem_dict_SP["DT_pvunit"] = "GHz"

    pv_elem_dict_RB = deepcopy(template_map_d)
    pv_elem_dict_RB["pvid_in_elem"] = ext_RB_pvid
    pv_elem_dict_RB["handle"] = "RB"
    pv_elem_dict_RB["DT_pvname"] = (
        f"{USERNAME}:{RB_pvname}"  # PV name for DT (Digital Twin)
    )
    pv_elem_dict_RB["pvunit"] = "Hz"
    pv_elem_dict_RB["DT_pvunit"] = "Hz"

    template_map_d = dict(elem_names=[pml_elem_name], handle=None, pvid_in_elem=None)

    simpv_elem_dict_RB = deepcopy(template_map_d)
    simpv_elem_dict_RB["pvid_in_elem"] = int_RB_pvid
    simpv_elem_dict_RB["handle"] = "RB"
    simpv_elem_dict_RB["pvunit"] = "Hz"

    simpv_elem_dict_SP = deepcopy(template_map_d)
    simpv_elem_dict_SP["pvid_in_elem"] = int_SP_pvid
    simpv_elem_dict_SP["handle"] = "SP"
    simpv_elem_dict_SP["pvunit"] = "Hz"

    assert sim_RB_pvsuffix not in simpv_defs
    simpv_defs[sim_RB_pvsuffix] = dict(pvclass="RfFreqSimPV")

    assert sim_SP_pvsuffix not in simpv_defs
    simpv_defs[sim_SP_pvsuffix] = dict(pvclass="RfFreqSimPV")

    elem_def = _get_blank_elem_def(elem_defs, pml_elem_name)

    elem_def.s_lists = s_lists

    repr = "freq"

    elem_def.repr_units[repr] = "Hz"

    elem_def.pvid_to_repr_map.ext[ext_SP_pvid] = repr
    elem_def.pvid_to_repr_map.ext[ext_RB_pvid] = repr
    elem_def.pvid_to_repr_map.int[int_SP_pvid] = repr
    elem_def.pvid_to_repr_map.int[int_RB_pvid] = repr

    ext_get_d = dict(input_pvs=[ext_RB_pvid])
    int_get_d = dict(input_pvs=[int_RB_pvid])
    elem_def.channel_map[f"{repr}_RB"] = ChannelSpec(
        handle="RB",
        HiLv_reprs=[repr],
        ext=PVMapping(get=GetPVMapping(**ext_get_d)),
        int=PVMapping(get=GetPVMapping(**int_get_d)),
        pdev_def=pdev_standard_RB_def,
    )

    ext_get_d = dict(input_pvs=[ext_SP_pvid])
    int_get_d = dict(input_pvs=[int_SP_pvid])
    ext_put_d = dict(output_pvs=[ext_SP_pvid])
    int_put_d = dict(output_pvs=[int_SP_pvid])
    elem_def.channel_map[f"{repr}_SP"] = ChannelSpec(
        handle="SP",
        HiLv_reprs=[repr],
        ext=PVMapping(
            get=GetPVMapping(**ext_get_d),
            put=PutPVMapping(**ext_put_d),
        ),
        int=PVMapping(
            get=GetPVMapping(**int_get_d),
            put=PutPVMapping(**int_put_d),
        ),
        pdev_def=MachineModeSpecContainer(
            LIVE=standard_SP(
                set_wait_method="SP_RB_diff",
                fixed_wait_time=FixedWaitTime(dt=Q_("5 s")),
                SP_RB_diff=SP_RB_Diff_Def(
                    RB_channel=f"{repr}_RB",
                    abs_tol=Q_("0.1 Hz"),
                    rel_tol=None,
                    timeout=Q_("10 s"),
                    settle_time=Q_("2 s"),
                    poll_time=Q_("0.5 s"),
                ),
            ),
            DT=standard_SP(),
            SIM=standard_SP(),
        ),
    )

    pv_elem_maps[RB_pvname] = pv_elem_dict_RB
    if pv_elem_dict_SP is not None:
        pv_elem_maps[SP_pvname] = pv_elem_dict_SP

    simpv_elem_maps[sim_RB_pvsuffix] = simpv_elem_dict_RB
    if simpv_elem_dict_SP is not None:
        simpv_elem_maps[sim_SP_pvsuffix] = simpv_elem_dict_SP


# %%
rf_freq_info = dict(
    pml_elem_name="RF_Freq",
    RB_pvname="RF{FCnt:1}Freq:I",
    SP_pvname="RF{Osc:1}Freq:SP",
    sim_RB_pvsuffix="rf_freq_RB",
    sim_SP_pvsuffix="rf_freq_SP",
)

# %%
d = rf_freq_info
process_rf_freq_definition(
    pv_elem_maps,
    simpv_elem_maps,
    simpv_defs,
    elem_defs,
    d["pml_elem_name"],
    d["RB_pvname"],
    d["SP_pvname"],
    d["sim_RB_pvsuffix"],
    d["sim_SP_pvsuffix"],
)

# %% [markdown]
# # DCCT (i.e., beam current) element definition


# %%
def process_dcct_definition(
    pv_elem_maps: Dict,
    simpv_elem_maps: Dict,
    simpv_defs: Dict,
    elem_defs: Dict,
    pml_elem_name: str,
    RB_pvname: str,
    sim_RB_pvsuffix: str,
    tags: KeyValueTagList | None = None,
):

    s_lists = dict(element=None)

    if tags is None:
        tags = KeyValueTagList()
    assert isinstance(tags, KeyValueTagList)

    if False:
        info_to_check = {}

    pdev_standard_RB_def = MachineModeSpecContainer(
        LIVE=standard_RB(), DT=standard_RB(), SIM=standard_RB()
    )

    assert RB_pvname not in pv_elem_maps

    assert sim_RB_pvsuffix not in simpv_elem_maps

    ext_pvid = "extpv_beam_current_RB"
    int_pvid = "intpv_beam_current_RB"

    template_map_d = dict(
        elem_names=[pml_elem_name],
        handle=None,
        pvid_in_elem=None,
        DT_pvname=None,
        DT_pvunit=None,
    )

    pv_elem_dict_RB = deepcopy(template_map_d)
    pv_elem_dict_RB["pvid_in_elem"] = ext_pvid
    pv_elem_dict_RB["handle"] = "RB"
    pv_elem_dict_RB["DT_pvname"] = (
        f"{USERNAME}:{RB_pvname}"  # PV name for DT (Digital Twin)
    )
    pv_elem_dict_RB["pvunit"] = "mA"
    pv_elem_dict_RB["DT_pvunit"] = "mA"

    template_map_d = dict(elem_names=[pml_elem_name], handle=None, pvid_in_elem=None)

    simpv_elem_dict_RB = deepcopy(template_map_d)
    simpv_elem_dict_RB["pvid_in_elem"] = int_pvid
    simpv_elem_dict_RB["handle"] = "RB"
    simpv_elem_dict_RB["pvunit"] = "A"

    assert sim_RB_pvsuffix not in simpv_defs
    simpv_defs[sim_RB_pvsuffix] = dict(pvclass="BeamCurrentSimPV")

    elem_def = _get_blank_elem_def(elem_defs, pml_elem_name)

    elem_def.s_lists = s_lists
    elem_def.tags = tags

    repr = "I"

    elem_def.repr_units[repr] = "mA"

    elem_def.pvid_to_repr_map.ext[ext_pvid] = repr
    elem_def.pvid_to_repr_map.int[int_pvid] = repr

    ext_get_d = dict(input_pvs=[ext_pvid])
    int_get_d = dict(input_pvs=[int_pvid])

    elem_def.channel_map[f"{repr}_RB"] = ChannelSpec(
        handle="RB",
        HiLv_reprs=[repr],
        ext=PVMapping(get=GetPVMapping(**ext_get_d)),
        int=PVMapping(get=GetPVMapping(**int_get_d)),
        pdev_def=pdev_standard_RB_def,
    )

    pv_elem_maps[RB_pvname] = pv_elem_dict_RB

    simpv_elem_maps[sim_RB_pvsuffix] = simpv_elem_dict_RB


# %%
dcct_info = dict(
    pml_elem_name="Beam_Current",
    RB_pvname="SR:C03-BI{DCCT:1}I:Real-I",
    sim_RB_pvsuffix="beam_current",
    tags=KeyValueTagList(tags=[KeyValueTag(key="family", values=["DCCT"])]),
)

# %%
d = dcct_info
process_dcct_definition(
    pv_elem_maps,
    simpv_elem_maps,
    simpv_defs,
    elem_defs,
    d["pml_elem_name"],
    d["RB_pvname"],
    d["sim_RB_pvsuffix"],
    d["tags"],
)

# %% [markdown]
# # Tune element definition


# %%
def process_tune_diag_definition(
    pv_elem_maps: Dict,
    simpv_elem_maps: Dict,
    simpv_defs: Dict,
    elem_defs: Dict,
    pml_elem_name: str,
    RB_pvname_d: Dict,
    sim_RB_pvsuffix_d: Dict,
    tags: KeyValueTagList | None = None,
):
    if tags is None:
        tags = KeyValueTagList()
    assert isinstance(tags, KeyValueTagList)

    if False:
        info_to_check = {}

    pdev_standard_RB_def = MachineModeSpecContainer(
        LIVE=standard_RB(), DT=standard_RB(), SIM=standard_RB()
    )

    for plane, RB_pvname in RB_pvname_d.items():

        assert RB_pvname not in pv_elem_maps

        sim_RB_pvsuffix = sim_RB_pvsuffix_d[plane]

        assert sim_RB_pvsuffix not in simpv_elem_maps

        ext_pvid = f"extpv_bxb_tune_{plane}_RB"
        int_pvid = f"intpv_bxb_tune_{plane}_RB"

        template_map_d = dict(
            elem_names=[pml_elem_name],
            handle=None,
            pvid_in_elem=None,
            DT_pvname=None,
            DT_pvunit=None,
        )

        pv_elem_dict_RB = deepcopy(template_map_d)
        pv_elem_dict_RB["pvid_in_elem"] = ext_pvid
        pv_elem_dict_RB["handle"] = "RB"
        pv_elem_dict_RB["DT_pvname"] = (
            f"{USERNAME}:{RB_pvname}"  # PV name for DT (Digital Twin)
        )
        pv_elem_dict_RB["pvunit"] = ""
        pv_elem_dict_RB["DT_pvunit"] = ""

        template_map_d = dict(
            elem_names=[pml_elem_name],
            handle=None,
            pvid_in_elem=None,
        )

        simpv_elem_dict_RB = deepcopy(template_map_d)
        simpv_elem_dict_RB["pvid_in_elem"] = int_pvid
        simpv_elem_dict_RB["handle"] = "RB"
        simpv_elem_dict_RB["pvunit"] = ""

        assert sim_RB_pvsuffix not in simpv_defs
        simpv_defs[sim_RB_pvsuffix] = dict(pvclass="TuneSimPV", args=[plane])

        elem_def = _get_blank_elem_def(elem_defs, pml_elem_name)

        elem_def.tags = tags

        repr = f"nu{plane}"

        elem_def.repr_units[repr] = ""

        elem_def.pvid_to_repr_map.ext[ext_pvid] = repr
        elem_def.pvid_to_repr_map.int[int_pvid] = repr

        ext_get_d = dict(input_pvs=[ext_pvid])
        int_get_d = dict(input_pvs=[int_pvid])

        elem_def.channel_map[f"{repr}_RB"] = ChannelSpec(
            handle="RB",
            HiLv_reprs=[repr],
            ext=PVMapping(get=GetPVMapping(**ext_get_d)),
            int=PVMapping(get=GetPVMapping(**int_get_d)),
            pdev_def=pdev_standard_RB_def,
            s_list_key="element",
        )

        pv_elem_maps[RB_pvname] = pv_elem_dict_RB

        simpv_elem_maps[sim_RB_pvsuffix] = simpv_elem_dict_RB


# %%
tune_diag_info = dict(
    pml_elem_name="BxB_Tune",
    RB_pvname_d={
        "x": "SR:OPS-BI{IGPF}FBX:Tune-I",
        "y": "SR:OPS-BI{IGPF}FBY:Tune-I",
    },
    sim_RB_pvsuffix_d={"x": "tune_x", "y": "tune_y"},
    tags=KeyValueTagList(tags=[KeyValueTag(key="family", values=["TUNE"])]),
)

# %%
d = tune_diag_info
process_tune_diag_definition(
    pv_elem_maps,
    simpv_elem_maps,
    simpv_defs,
    elem_defs,
    d["pml_elem_name"],
    d["RB_pvname_d"],
    d["sim_RB_pvsuffix_d"],
    d["tags"],
)

# %% [markdown]
# # Save these configuration data to files
#
# Note that both JSON and YAML files are being saved here. YAML is typically more human readable, but in some cases, JSON is easier to read. So, both formats are being used at this stage. In the future, most likely only YAML will be used after more formatting options are explored such that all YAML files become easy to read.

# %% [markdown]
# # Save the mapping between PVs (for online modes) and elements

# %%
pv_elem_maps_for_file = {
    "facility": sim_configs["facility"],
    "machine": sim_configs["machine"],
    "simulator_config": sim_configs["selected_config"],
    "pv_elem_maps": pv_elem_maps,
}

with open(sel_config_folder / "pv_elem_maps.yaml", "w") as f:
    yaml.dump(
        pv_elem_maps_for_file,
        f,
        sort_keys=False,
        default_flow_style=False,
        width=70,
        indent=2,
        Dumper=CustomDumper,
    )
with open(sel_config_folder / "pv_elem_maps.json", "w") as f:
    json.dump(pv_elem_maps_for_file, f, indent=2)

# %% [markdown]
# # Save the mapping between SimPVs (for offline modes) and elements

# %%
simpv_elem_maps_for_file = {
    "facility": sim_configs["facility"],
    "machine": sim_configs["machine"],
    "simulator_config": sim_configs["selected_config"],
    "simpv_elem_maps": simpv_elem_maps,
}

with open(sel_config_folder / "simpv_elem_maps.yaml", "w") as f:
    yaml.dump(
        simpv_elem_maps_for_file,
        f,
        sort_keys=False,
        default_flow_style=False,
        width=70,
        indent=2,
        Dumper=CustomDumper,
    )
with open(sel_config_folder / "simpv_elem_maps.json", "w") as f:
    json.dump(simpv_elem_maps_for_file, f, indent=2)

# %% [markdown]
# # Save SimPV definitions

# %%
sim_pv_defs_for_file = {
    "facility": sim_configs["facility"],
    "machine": sim_configs["machine"],
    "simulator_config": sim_configs["selected_config"],
    "sim_pv_definitions": simpv_defs,
}

with open(sel_config_folder / "sim_pvs.yaml", "w") as f:
    yaml.dump(
        sim_pv_defs_for_file,
        f,
        sort_keys=False,
        default_flow_style=False,
        width=70,
        indent=2,
        Dumper=CustomDumper,
    )
with open(sel_config_folder / "sim_pvs.json", "w") as f:
    json.dump(sim_pv_defs_for_file, f, indent=2)

# %% [markdown]
# # Save element (MLV := Middle Layer Variable) definitions

# %%
elem_defs_for_file = {
    "facility": sim_configs["facility"],
    "machine": sim_configs["machine"],
    "simulator_config": sim_configs["selected_config"],
    "elem_definitions": elem_defs,
}

json_safe_elem_defs = {}
for k, v in elem_defs_for_file.items():
    if k != "elem_definitions":
        json_safe_elem_defs[k] = v
    else:
        e_defs = json_safe_elem_defs["elem_definitions"] = {}
        for elem_name, pamila_elem_def in v.items():
            e_defs[elem_name] = json.loads(
                pamila_elem_def.model_dump_json(exclude_defaults=True)
            )

with open(sel_config_folder / "elements.yaml", "w") as f:
    yaml.dump(
        json_safe_elem_defs,
        f,
        sort_keys=False,
        default_flow_style=False,
        width=70,
        indent=2,
        Dumper=CustomDumper,
    )
with open(sel_config_folder / "elements.json", "w") as f:
    json.dump(json_safe_elem_defs, f, indent=2)

# %% [markdown]
# # Compute design lattice properties

# %%
design_props = {}

rad_params = at.physics.ring_parameters.radiation_parameters(lattice)

for prop_name in dir(rad_params):
    if prop_name.startswith("_"):
        continue
    val = getattr(rad_params, prop_name)
    if isinstance(val, np.ndarray):
        design_props[prop_name] = val.tolist()
    else:
        design_props[prop_name] = val

# Force numpy scalar objects to python objects so that they can be
# saved to JSON/YAML files.
design_props = json.loads(json.dumps(design_props))
design_props

# %% [markdown]
# # Save design lattice property definitions to files

# %%
design_props_for_file = {
    "facility": sim_configs["facility"],
    "machine": sim_configs["machine"],
    "simulator_config": sim_configs["selected_config"],
    "model_name": model_name,
    "design_properties": design_props,
}

model_folder = sel_config_folder / model_name
model_folder.mkdir(exist_ok=True)

with open(model_folder / "design_props.yaml", "w") as f:
    yaml.dump(
        design_props_for_file,
        f,
        sort_keys=False,
        default_flow_style=False,
        width=70,
        indent=2,
        Dumper=CustomDumper,
    )
with open(model_folder / "design_props.json", "w") as f:
    json.dump(design_props_for_file, f, indent=2)

# %% [markdown]

# # Check if the created config files are loadable

# %%
print(f"{facility_folder = }")
print(f"{machine_name = }")
machine_obj = pml.load_machine(machine_name, dirpath=facility_folder)

# %% [markdown]
# # For faster loading, we can save the machine object into a cache file, and load from that file.

# %%
# Save the machine object and other necessary data to a cache file
cache_filepath = Path("SR_cache.pgz")
machine_obj.save_to_cache_file(cache_filepath)

# %%
# Reload the machine object from the cache file
reloaded_machine_obj = pml.load_cached_machine(sim_configs["machine"], cache_filepath)

# %% [markdown]
# # MLVLs (MLV lists) and MLVTs (MLV trees) will be defined in a separate notebook.
