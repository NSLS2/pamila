# %% [markdown]
# - In this notebook, we will try to add MLVs that require multiple-input,
# multiple-output (MIMO) repr. conversions. Examples for this type include
# combined function magnets with dipole and quadrupole components and an orbit
# corrector with diagonal kicks.
#
# - As an example, we consider the latter and pick the realistic hardware
# conditions that actually exist for the orbit correctors in the Cell 23
# straight section of the NSLS-II storage ring with some simplifications.
#
#   - These correctors are dedicated for the correction of the residual field
# integrals of the EPU insertion device (ID).
#   - One of these magnets have two power supply currents for control. We will
# use "channels" to refer to the control of these two currents.
#   - This magnet is unique in that each channel controls the amplitude of
# diagonal kick, while the channels of most correctors provide either horizontal
# or vertical kicks.
#   - Furthermore, the kick strength also depends on the gap value of the ID as
# the coils are attached to the ID arrays.
#   - Therefore, the actual $(x, y)$ kick angles depend on $(I_1, I_2, g)$ where
# $I_1$ and $I_2$ represent the power supply currents of Channels 1 and 2, and
# $g$ corresponds to the ID gap value.
#   - For simplicity, let us assume the following relationships:
#   $$
#   x [\mu \mathrm{rad}]= (I_1 [\mathrm{A}] + I_2 [\mathrm{A}]) \cdot G
#   \newline
#   y [\mu \mathrm{rad}]= (I_1 [\mathrm{A}] - I_2 [\mathrm{A}]) \cdot G
#
#   $$
#
#   where
#
#   $$
#   G = \frac{\max(100 - g [\mathrm{mm}], 0)}{20}.
#   $$
#
#   - The inverse relationships are then defined as:
#   $$
#   I_1 [\mathrm{A}] = \frac{(x [\mu \mathrm{rad}] + y [\mu \mathrm{rad}])}{2G}
#   \newline
#   I_2 [\mathrm{A}] = \frac{(x [\mu \mathrm{rad}] - y [\mu \mathrm{rad}])}{2G}
#   $$
#   - These custom representation conversion relations are defined in the plugin
# file `examples/conv_plugins/ID23d_repr_convs.py`.
#   - Of course, more complicated relationshipts can be used (e.g., neural
# networks), as long as they can be defined as Python functions.

# %%
from pathlib import Path

# %%
# You can ignore about the `pydantic` deprecation warning (coming from `tiled`)
import pamila as pml
from pamila import Q_

# %%
# Activate the simulator mode (i.e., neither LIVE nor DT [Digital Twin])
pml.go_offline()

# %%
facility_name = pml.machine.get_facility_name()
cwd = Path.cwd()
if cwd.name == "examples":
    examples_folder = cwd
else:
    assert cwd.name == "nb_gen"
    examples_folder = cwd.parent
FACILITY_CONFIG_FOLDER = examples_folder / "demo_generated" / facility_name
machine_name = "SR"
machine_folder = FACILITY_CONFIG_FOLDER / machine_name

# %%
# Copy the repr. conv. plugin file "ID23d_repr_convs.py" for the "ID23d"
# element from the package source to the example config folder.
import shutil

shutil.copytree(
    FACILITY_CONFIG_FOLDER.parent.parent / "conv_plugins",
    machine_folder / "conv_plugins",
    dirs_exist_ok=True,
)

# %%
import yaml


class CustomDumper(yaml.SafeDumper):
    def represent_list(self, data):
        # Force lists to be represented in flow style (inline `[]` style)
        return self.represent_sequence("tag:yaml.org,2002:seq", data, flow_style=True)


# Add the custom list representation to the dumper
CustomDumper.add_representer(list, CustomDumper.represent_list)

# %%
# Modify "sim_configs.yaml" such that PAMILA knows where to look for
# the conversion plugin folder.
sim_configs_filepath = machine_folder / "sim_configs.yaml"
sim_configs = yaml.safe_load(sim_configs_filepath.read_text())
sim_configs["conversion_plugin_folder"] = str(
    (machine_folder / "conv_plugins").resolve()
)

with open(sim_configs_filepath, "w") as f:
    yaml.dump(
        sim_configs,
        f,
        sort_keys=False,
        default_flow_style=False,
        width=70,
        indent=2,
        Dumper=CustomDumper,
    )

# %%
SR = pml.load_machine(machine_name, dirpath=FACILITY_CONFIG_FOLDER)

# %%
# Confirm that the custom conversion functions "ID23d_repr_convs.from_..."
# have been properly loaded.
#
# Without the plugin, "identity", "poly1d", and "pchip_interp" are the only
# built-in conversion functions available.

from pamila.device.conversion.plugin_manager import get_registered_functions

FUNC_MAP, IS_FACTORY_FUNC = get_registered_functions()

FUNC_MAP

# %% [markdown]
# - Now we will try to add new MLVs that can control this corrector in a variety of ways.

# %%
# First, add a fake SimPV that does not affect the simulated lattice model,
# but keeps track of the current gap value of the ID.
# (The only reason for using such a fake SimPV is because a realistic SimPV to
# emulate the ID has not been implemented yet.)
SR.add_to_simpv_definitions(
    dict(
        pvclass="FakeInsertionDeviceGapSimPV",
        pvsuffix="ID23d_GAP_SP",
        args=[],
    )
)
SR.add_to_simpv_definitions(
    dict(
        pvclass="FakeInsertionDeviceGapSimPVRO",
        pvsuffix="ID23d_GAP_RB",
        args=["ID23d_GAP_SP"],
    )
)

# %%
# Now add two SimPVs that are supposed to represent the orbit corrector dedicated
# to the ID.
#
# Note that the kicks in the simulator will be adjusted as orthogonal
# horizontal and vertical kicks, unlike the actual diagonal kicks.

sim_itf = SR.get_sim_interface()
lattice = sim_itf.get_lattice()
at = sim_itf.package

at_elem_name = "CL1XG2C23A"
matched_indexes = at.get_uint32_index(lattice, at_elem_name)
assert len(matched_indexes) == 1
lattice_index = int(
    matched_indexes[0]
)  # Avoid numpy.uint32 that prevents saving into JSON/YAML

SR.add_to_simpv_definitions(
    dict(
        pvclass="CorrectorSimPV",
        pvsuffix="ID23d_X_SP",
        args=[lattice_index, "x"],
    )
)
SR.add_to_simpv_definitions(
    dict(
        pvclass="CorrectorSimPV",
        pvsuffix="ID23d_X_RB",
        args=[lattice_index, "x"],
    )
)

SR.add_to_simpv_definitions(
    dict(
        pvclass="CorrectorSimPV",
        pvsuffix="ID23d_Y_SP",
        args=[lattice_index, "y"],
    )
)
SR.add_to_simpv_definitions(
    dict(
        pvclass="CorrectorSimPV",
        pvsuffix="ID23d_Y_RB",
        args=[lattice_index, "y"],
    )
)

# %%
# Specify the PV-element mapping for the gap and the two channels of the
# diagonal-kick corrector for the ID.
#
# Since this demo notebook is not meant to be run in the online mode, the PV
# names for LIVE and DT specified here are fake ones.

import getpass

username = getpass.getuser()

for handle in ["SP", "RB"]:
    pvname = f"Fake:SR:DiagonalCor1:Ch1:{handle}"
    SR.add_to_pv_elem_maps(
        pvname,
        dict(
            elem_names=["ID23d"],
            handle=handle,
            pvid_in_elem=f"extpv_I1_{handle}",
            DT_pvname=f"{username}:{pvname}",
            DT_pvunit="A",
            pvunit="A",
        ),
    )

    pvname = f"Fake:SR:DiagonalCor1:Ch2:{handle}"
    SR.add_to_pv_elem_maps(
        pvname,
        dict(
            elem_names=["ID23d"],
            handle=handle,
            pvid_in_elem=f"extpv_I2_{handle}",
            DT_pvname=f"{username}:{pvname}",
            DT_pvunit="A",
            pvunit="A",
        ),
    )

    pvname = f"Fake:SR:ID23d:Gap:{handle}"
    SR.add_to_pv_elem_maps(
        pvname,
        dict(
            elem_names=["ID23d"],
            handle=handle,
            pvid_in_elem=f"extpv_gap_{handle}",
            DT_pvname=f"{username}:{pvname}",
            DT_pvunit="mm",
            pvunit="mm",
        ),
    )

# %%
# Specify the SimPV-element mapping for the gap and the horizontal and vertical
# orbit corrector for the ID.

pvsuffix = "ID23d_GAP_RB"
SR.add_to_simpv_elem_maps(
    pvsuffix,
    dict(elem_names=["ID23d"], pvid_in_elem="intpv_gap_RB", handle="RB", pvunit="m"),
)
pvsuffix = "ID23d_GAP_SP"
SR.add_to_simpv_elem_maps(
    pvsuffix,
    dict(elem_names=["ID23d"], pvid_in_elem="intpv_gap_SP", handle="SP", pvunit="m"),
)

pvsuffix = "ID23d_X_RB"
SR.add_to_simpv_elem_maps(
    pvsuffix,
    dict(
        elem_names=["ID23d"],
        pvid_in_elem="intpv_x_angle_RB",
        handle="RB",
        pvunit="rad",
    ),
)
pvsuffix = "ID23d_X_SP"
SR.add_to_simpv_elem_maps(
    pvsuffix,
    dict(
        elem_names=["ID23d"],
        pvid_in_elem="intpv_x_angle_SP",
        handle="SP",
        pvunit="rad",
    ),
)

pvsuffix = "ID23d_Y_RB"
SR.add_to_simpv_elem_maps(
    pvsuffix,
    dict(
        elem_names=["ID23d"],
        pvid_in_elem="intpv_y_angle_RB",
        handle="RB",
        pvunit="rad",
    ),
)

pvsuffix = "ID23d_Y_SP"
SR.add_to_simpv_elem_maps(
    pvsuffix,
    dict(
        elem_names=["ID23d"],
        pvid_in_elem="intpv_y_angle_SP",
        handle="SP",
        pvunit="rad",
    ),
)

# %%
# Now specify all the MLVs for the ID element

new_elem_def = dict(
    pvid_to_repr_map={
        "ext": {
            "extpv_I1_SP": "I1",
            "extpv_I1_RB": "I1",
            "extpv_I2_SP": "I2",
            "extpv_I2_RB": "I2",
            "extpv_gap_SP": "gap",
            "extpv_gap_RB": "gap",
        },
        "int": {
            "intpv_x_angle_SP": "x_angle",
            "intpv_x_angle_RB": "x_angle",
            "intpv_y_angle_SP": "y_angle",
            "intpv_y_angle_RB": "y_angle",
            "intpv_gap_SP": "gap",
            "intpv_gap_RB": "gap",
        },
    },
    repr_units={
        "I1": "A",
        "I2": "A",
        "x_angle": "urad",
        "y_angle": "urad",
        "gap": "mm",
    },
    func_specs={
        "x_y_gap_to_I1_I2": {
            "name": "ID23d_repr_convs.from_x_y_gap_to_I1_I2",
            "in_repr_ranges": {
                "gap": [5.0, 90.0]
            },  # TO-BE-IMPLEMENTED: UnitConvSpec.src_val_ranges
        },  # for ("I1_I2_SP"/"I1_I2_RB", int, get) & ("x_y_angle_SP", ext, put)
        "I1_I2_gap_to_x_y": {
            "name": "ID23d_repr_convs.from_I1_I2_gap_to_x_y",
            "in_repr_ranges": {
                "gap": [5.0, 90.0]
            },  # TO-BE-IMPLEMENTED: UnitConvSpec.src_val_ranges
        },  # for ("I1_I2_SP", int, put) & ("x_y_angle_SP"/"x_y_angle_RB", ext, get)
        "x_y_gap_to_I1": {
            "name": "ID23d_repr_convs.from_x_y_gap_to_I1",
            "in_repr_ranges": {
                "gap": [5.0, 90.0]
            },  # TO-BE-IMPLEMENTED: UnitConvSpec.src_val_ranges
        },  # for ("I1_SP"/"I1_RB", int, get)
        "I1_x_y_gap_to_x_y_w_fixed_I2": {
            "name": "ID23d_repr_convs.from_I1_x_y_gap_to_x_y_w_fixed_I2",
            "description": """A user provides a new value for 'I1'. Given the current values
            of 'x', 'y', and 'gap', calculate new values for 'x' and 'y', assuming the user
            wants to keep the current "I2" value fixed.""",
            "in_repr_ranges": {
                "gap": [5.0, 90.0]
            },  # TO-BE-IMPLEMENTED: UnitConvSpec.src_val_ranges
        },  # for ("I1_SP", int, put)
        "x_y_gap_to_I2": {
            "name": "ID23d_repr_convs.from_x_y_gap_to_I2",
            "in_repr_ranges": {
                "gap": [5.0, 90.0]
            },  # TO-BE-IMPLEMENTED: UnitConvSpec.src_val_ranges
        },  # for ("I2_SP"/"I2_RB", int, get)
        "I2_x_y_gap_to_x_y_w_fixed_I1": {
            "name": "ID23d_repr_convs.from_I2_x_y_gap_to_x_y_w_fixed_I1",
            "description": """A user provides a new value for 'I2'. Given the current values
            of 'x', 'y', and 'gap', calculate new values for 'x' and 'y', assuming the user
            wants to keep the current "I1" value fixed.""",
            "in_repr_ranges": {
                "gap": [5.0, 90.0]
            },  # TO-BE-IMPLEMENTED: UnitConvSpec.src_val_ranges
        },  # for ("I2_SP", int, put)
        "I1_I2_gap_to_x": {
            "name": "ID23d_repr_convs.from_I1_I2_gap_to_x",
        },  # for ("x_angle_SP"/"x_angle_RB", ext, get)
        "x_I1_I2_gap_to_I1_I2_w_fixed_y": {
            "name": "ID23d_repr_convs.from_x_I1_I2_gap_to_I1_I2_w_fixed_y",
            "description": """A user provides a new value for 'x_angle'. Given the current values
             of 'I1', 'I2', and 'gap', calculate new values for 'I1' and 'I2', assuming the user
             wants to keep the current "y_angle" value fixed.""",
        },  # for ("x_angle_SP", ext, put)
        "I1_I2_gap_to_y": {
            "name": "ID23d_repr_convs.from_I1_I2_gap_to_y"
        },  # for ("y_angle_SP"/y_angle_RB, ext, get)
        "y_I1_I2_gap_to_I1_I2_w_fixed_x": {
            "name": "ID23d_repr_convs.from_y_I1_I2_gap_to_I1_I2_w_fixed_x",
            "description": """A user provides a new value for 'y_angle'. Given the current values
            of 'I1', 'I2', and 'gap', calculate new values for 'I1' and 'I2', assuming the user
            wants to keep the current "x_angle" value fixed.""",
        },  # for ("y_angle_SP", ext, put)
    },
    channel_map={
        "gap_SP": {
            "handle": "SP",
            "HiLv_reprs": ["gap"],
            "ext": dict(
                get={"input_pvs": ["extpv_gap_SP"]},
                put={"output_pvs": ["extpv_gap_SP"]},
            ),
            "int": dict(
                get={"input_pvs": ["intpv_gap_SP"]},
                put={"output_pvs": ["intpv_gap_SP"]},
            ),
            "pdev_def": dict(
                LIVE={"type": "standard_SP"},
                DT={"type": "standard_SP"},
                SIM={"type": "standard_SP"},
            ),
        },
        "gap_RB": {
            "handle": "RB",
            "HiLv_reprs": ["gap"],
            "ext": dict(get={"input_pvs": ["extpv_gap_RB"]}),
            "int": dict(get={"input_pvs": ["intpv_gap_RB"]}),
            "pdev_def": dict(
                LIVE={"type": "standard_RB"},
                DT={"type": "standard_RB"},
                SIM={"type": "standard_RB"},
            ),
        },
        "I1_I2_SP": {
            "handle": "SP",
            "HiLv_reprs": ["I1", "I2"],
            "ext": dict(
                get={"input_pvs": ["extpv_I1_SP", "extpv_I2_SP"]},
                put={"output_pvs": ["extpv_I1_SP", "extpv_I2_SP"]},
            ),
            "int": dict(
                get={
                    "input_pvs": [
                        "intpv_x_angle_SP",
                        "intpv_y_angle_SP",
                        "intpv_gap_RB",
                    ],
                    "conv_spec_name": "x_y_gap_to_I1_I2",
                },
                put={
                    "aux_input_pvs": ["intpv_gap_RB"],
                    "output_pvs": ["intpv_x_angle_SP", "intpv_y_angle_SP"],
                    "conv_spec_name": "I1_I2_gap_to_x_y",
                },
            ),
            "pdev_def": dict(
                LIVE={
                    "type": "standard_MIMO_SP",
                    "set_wait_method": "SP_RB_diff",
                },
                DT={"type": "standard_MIMO_SP"},
                SIM={"type": "standard_MIMO_SP"},
            ),
        },
        "I1_I2_RB": {
            "handle": "RB",
            "HiLv_reprs": ["I1", "I2"],
            "ext": dict(get={"input_pvs": ["extpv_I1_RB", "extpv_I2_RB"]}),
            "int": dict(
                get={
                    "input_pvs": [
                        "intpv_x_angle_RB",
                        "intpv_y_angle_RB",
                        "intpv_gap_RB",
                    ],
                    "conv_spec_name": "x_y_gap_to_I1_I2",
                }
            ),
            "pdev_def": dict(
                LIVE={"type": "standard_MIMO_RB"},
                DT={"type": "standard_MIMO_RB"},
                SIM={"type": "standard_MIMO_RB"},
            ),
        },
        "I1_SP": {
            "handle": "SP",
            "HiLv_reprs": ["I1"],
            "ext": dict(
                get={"input_pvs": ["extpv_I1_SP"]},
                put={"output_pvs": ["extpv_I1_SP"]},
            ),
            "int": dict(
                get={
                    "input_pvs": [
                        "intpv_x_angle_SP",
                        "intpv_y_angle_SP",
                        "intpv_gap_RB",
                    ],
                    "conv_spec_name": "x_y_gap_to_I1",
                },
                put={
                    "aux_input_pvs": [
                        "intpv_x_angle_SP",
                        "intpv_y_angle_SP",
                        "intpv_gap_RB",
                    ],
                    "output_pvs": ["intpv_x_angle_SP", "intpv_y_angle_SP"],
                    "conv_spec_name": "I1_x_y_gap_to_x_y_w_fixed_I2",
                },
            ),
            "pdev_def": dict(
                LIVE={
                    "type": "standard_MIMO_SP",
                    "set_wait_method": "SP_RB_diff",
                },
                DT={"type": "standard_MIMO_SP"},
                SIM={"type": "standard_MIMO_SP"},
            ),
        },
        "I1_RB": {
            "handle": "RB",
            "HiLv_reprs": ["I1"],
            "ext": dict(get={"input_pvs": ["extpv_I1_RB"]}),
            "int": dict(
                get={
                    "input_pvs": [
                        "intpv_x_angle_RB",
                        "intpv_y_angle_RB",
                        "intpv_gap_RB",
                    ],
                    "conv_spec_name": "x_y_gap_to_I1",
                }
            ),
            "pdev_def": dict(
                LIVE={"type": "standard_MIMO_RB"},
                DT={"type": "standard_MIMO_RB"},
                SIM={"type": "standard_MIMO_RB"},
            ),
        },
        "I2_SP": {
            "handle": "SP",
            "HiLv_reprs": ["I2"],
            "ext": dict(
                get={"input_pvs": ["extpv_I2_SP"]},
                put={"output_pvs": ["extpv_I2_SP"]},
            ),
            "int": dict(
                get={
                    "input_pvs": [
                        "intpv_x_angle_SP",
                        "intpv_y_angle_SP",
                        "intpv_gap_RB",
                    ],
                    "conv_spec_name": "x_y_gap_to_I2",
                },
                put={
                    "aux_input_pvs": [
                        "intpv_x_angle_SP",
                        "intpv_y_angle_SP",
                        "intpv_gap_RB",
                    ],
                    "output_pvs": ["intpv_x_angle_SP", "intpv_y_angle_SP"],
                    "conv_spec_name": "I2_x_y_gap_to_x_y_w_fixed_I1",
                },
            ),
            "pdev_def": dict(
                LIVE={
                    "type": "standard_MIMO_SP",
                    "set_wait_method": "SP_RB_diff",
                },
                DT={"type": "standard_MIMO_SP"},
                SIM={"type": "standard_MIMO_SP"},
            ),
        },
        "I2_RB": {
            "handle": "RB",
            "HiLv_reprs": ["I2"],
            "ext": dict(get={"input_pvs": ["extpv_I2_RB"]}),
            "int": dict(
                get={
                    "input_pvs": [
                        "intpv_x_angle_RB",
                        "intpv_y_angle_RB",
                        "intpv_gap_RB",
                    ],
                    "conv_spec_name": "x_y_gap_to_I2",
                }
            ),
            "pdev_def": dict(
                LIVE={"type": "standard_MIMO_RB"},
                DT={"type": "standard_MIMO_RB"},
                SIM={"type": "standard_MIMO_RB"},
            ),
        },
        "x_y_angle_SP": {
            "handle": "SP",
            "HiLv_reprs": ["x_angle", "y_angle"],
            "ext": dict(
                get={
                    "input_pvs": ["extpv_I1_SP", "extpv_I2_SP", "extpv_gap_RB"],
                    "conv_spec_name": "I1_I2_gap_to_x_y",
                },
                put={
                    "aux_input_pvs": ["extpv_gap_RB"],
                    "output_pvs": ["extpv_I1_SP", "extpv_I2_SP"],
                    "conv_spec_name": "x_y_gap_to_I1_I2",
                },
            ),
            "int": dict(
                get={"input_pvs": ["intpv_x_angle_SP", "intpv_y_angle_SP"]},
                put={"output_pvs": ["intpv_x_angle_SP", "intpv_y_angle_SP"]},
            ),
            "pdev_def": dict(
                LIVE={
                    "type": "standard_MIMO_SP",
                    "set_wait_method": "SP_RB_diff",
                },
                DT={"type": "standard_MIMO_SP"},
                SIM={"type": "standard_MIMO_SP"},
            ),
        },
        "x_y_angle_RB": {
            "handle": "RB",
            "HiLv_reprs": ["x_angle", "y_angle"],
            "ext": dict(
                get={
                    "input_pvs": ["extpv_I1_RB", "extpv_I2_RB", "extpv_gap_RB"],
                    "conv_spec_name": "I1_I2_gap_to_x_y",
                }
            ),
            "int": dict(
                get={
                    "input_pvs": ["intpv_x_angle_RB", "intpv_y_angle_RB"],
                    "conv_spec_name": "identity",
                }
            ),
            "pdev_def": dict(
                LIVE={"type": "standard_MIMO_RB"},
                DT={"type": "standard_MIMO_RB"},
                SIM={"type": "standard_MIMO_RB"},
            ),
        },
        "x_angle_SP": {
            "handle": "SP",
            "HiLv_reprs": ["x_angle"],
            "ext": dict(
                get={
                    "input_pvs": ["extpv_I1_SP", "extpv_I2_SP", "extpv_gap_RB"],
                    "conv_spec_name": "I1_I2_gap_to_x",
                },
                put={
                    "aux_input_pvs": ["extpv_I1_SP", "extpv_I2_SP", "extpv_gap_RB"],
                    "output_pvs": ["extpv_I1_SP", "extpv_I2_SP"],
                    "conv_spec_name": "x_I1_I2_gap_to_I1_I2_w_fixed_y",
                },
            ),
            "int": dict(
                get={
                    "input_pvs": ["intpv_x_angle_SP"],
                    "conv_spec_name": "identity",
                },
                put={
                    "output_pvs": ["intpv_x_angle_SP"],
                    "conv_spec_name": "identity",
                },
            ),
            "pdev_def": dict(
                LIVE={
                    "type": "standard_MIMO_SP",
                    "set_wait_method": "SP_RB_diff",
                },
                DT={"type": "standard_MIMO_SP"},
                SIM={"type": "standard_MIMO_SP"},
            ),
        },
        "x_angle_RB": {
            "handle": "RB",
            "HiLv_reprs": ["x_angle"],
            "ext": dict(
                get={
                    "input_pvs": ["extpv_I1_RB", "extpv_I2_RB", "extpv_gap_RB"],
                    "conv_spec_name": "I1_I2_gap_to_x",
                }
            ),
            "int": dict(
                get={
                    "input_pvs": ["intpv_x_angle_RB"],
                    "conv_spec_name": "identity",
                }
            ),
            "pdev_def": dict(
                LIVE={"type": "standard_MIMO_RB"},
                DT={"type": "standard_MIMO_RB"},
                SIM={"type": "standard_MIMO_RB"},
            ),
        },
        "y_angle_SP": {
            "handle": "SP",
            "HiLv_reprs": ["y_angle"],
            "ext": dict(
                get={
                    "input_pvs": ["extpv_I1_SP", "extpv_I2_SP", "extpv_gap_RB"],
                    "conv_spec_name": "I1_I2_gap_to_y",
                },
                put={
                    "aux_input_pvs": ["extpv_I1_SP", "extpv_I2_SP", "extpv_gap_RB"],
                    "output_pvs": ["extpv_I1_SP", "extpv_I2_SP"],
                    "conv_spec_name": "y_I1_I2_gap_to_I1_I2_w_fixed_x",
                },
            ),
            "int": dict(
                get={
                    "input_pvs": ["intpv_y_angle_SP"],
                    "conv_spec_name": "identity",
                },
                put={
                    "output_pvs": ["intpv_y_angle_SP"],
                    "conv_spec_name": "identity",
                },
            ),
            "pdev_def": dict(
                LIVE={
                    "type": "standard_MIMO_SP",
                    "set_wait_method": "SP_RB_diff",
                },
                DT={"type": "standard_MIMO_SP"},
                SIM={"type": "standard_MIMO_SP"},
            ),
        },
        "y_angle_RB": {
            "handle": "RB",
            "HiLv_reprs": ["y_angle"],
            "ext": dict(
                get={
                    "input_pvs": ["extpv_I1_RB", "extpv_I2_RB", "extpv_gap_RB"],
                    "conv_spec_name": "I1_I2_gap_to_y",
                }
            ),
            "int": dict(
                get={
                    "input_pvs": ["intpv_y_angle_RB"],
                    "conv_spec_name": "identity",
                }
            ),
            "pdev_def": dict(
                LIVE={"type": "standard_MIMO_RB"},
                DT={"type": "standard_MIMO_RB"},
                SIM={"type": "standard_MIMO_RB"},
            ),
        },
    },
)

SR.add_to_elem_definitions("ID23d", new_elem_def)

# %%
# Now actually construct all the MLVs specified above
SR.construct_mlvs_for_one_element("ID23d")

# %%
# This test function applies the following changes in sequence:
# - Set the gap to 50 [mm]
# - Set the Ch.1 and Ch.2 currents to +1 and +2 [A].
# - Assert that the x and y kick angles are now +7.5 and -2.5 [urad].
# - Only change Ch. 2 to +3 [A].
# - Assert that the x and y kick angles are now +10 and -5 [urad].
# - Change the gap to 60 [mm]
# - Assert the gap has been changed into 60 [mm].
# - Assert that the x and y kick angles are now +8 and -4 [urad].


def test_sequence(all_mlvs, last_test_fail_ok: bool = False):
    mlv_gap_SP = all_mlvs["ID23d_gap_SP"]
    mlv_gap_RB = all_mlvs["ID23d_gap_RB"]

    mlv_I1_SP = all_mlvs["ID23d_I1_SP"]
    mlv_I1_RB = all_mlvs["ID23d_I1_RB"]

    mlv_I2_SP = all_mlvs["ID23d_I2_SP"]
    mlv_I2_RB = all_mlvs["ID23d_I2_RB"]

    mlv_I1_I2_SP = all_mlvs["ID23d_I1_I2_SP"]
    mlv_I1_I2_RB = all_mlvs["ID23d_I1_I2_RB"]

    mlv_x_angle_SP = all_mlvs["ID23d_x_angle_SP"]
    mlv_x_angle_RB = all_mlvs["ID23d_x_angle_RB"]

    mlv_y_angle_SP = all_mlvs["ID23d_y_angle_SP"]
    mlv_y_angle_RB = all_mlvs["ID23d_y_angle_RB"]

    mlv_x_y_angle_SP = all_mlvs["ID23d_x_y_angle_SP"]
    mlv_x_y_angle_RB = all_mlvs["ID23d_x_y_angle_RB"]

    print(mlv_gap_SP.get())

    mlv_gap_SP.put(Q_("50 mm"))

    print(mlv_gap_SP.get(), mlv_gap_RB.get())

    print(mlv_I1_SP.get(), mlv_I2_SP.get())
    print(mlv_I1_RB.get(), mlv_I2_RB.get())

    print(mlv_x_angle_SP.get(), mlv_x_angle_RB.get())
    print(mlv_y_angle_SP.get(), mlv_y_angle_RB.get())

    mlv_I1_I2_SP.put([Q_("1 A"), Q_("2 A")])

    print(mlv_I1_I2_SP.get(), mlv_I1_I2_RB.get())
    print(mlv_x_y_angle_SP.get(), mlv_x_y_angle_RB.get())

    import numpy as np

    for actual, desired in zip(mlv_I1_I2_SP.get(), [Q_("1 A"), Q_("2 A")]):
        np.testing.assert_array_almost_equal(actual, desired, decimal=9)
    for actual, desired in zip(
        mlv_x_y_angle_SP.get(), [Q_("+7.5 urad"), Q_("-2.5 urad")]
    ):
        np.testing.assert_array_almost_equal(actual, desired, decimal=9)

    mlv_I2_SP.put(Q_("3 A"))

    print(mlv_I1_I2_SP.get(), mlv_I1_I2_RB.get())
    print(mlv_x_y_angle_SP.get(), mlv_x_y_angle_RB.get())

    for actual, desired in zip(mlv_I1_I2_SP.get(), [Q_("1 A"), Q_("3 A")]):
        np.testing.assert_array_almost_equal(actual, desired, decimal=9)
    for actual, desired in zip(mlv_x_y_angle_SP.get(), [Q_("+10 urad"), Q_("-5 urad")]):
        np.testing.assert_array_almost_equal(actual, desired, decimal=9)

    mlv_gap_SP.put(Q_("60 mm"))

    print(mlv_gap_SP.get(), mlv_gap_RB.get())

    np.testing.assert_array_almost_equal(mlv_gap_SP.get(), Q_("60 mm"), decimal=9)

    print(mlv_I1_I2_SP.get(), mlv_I1_I2_RB.get())
    print(mlv_x_y_angle_SP.get(), mlv_x_y_angle_RB.get())

    for actual, desired in zip(mlv_I1_I2_SP.get(), [Q_("1 A"), Q_("3 A")]):
        try:
            np.testing.assert_array_almost_equal(actual, desired, decimal=9)
        except AssertionError:
            if last_test_fail_ok:
                print(f"Assertion failed as expected: {actual} != {desired}")
            else:
                raise
    for actual, desired in zip(mlv_x_y_angle_SP.get(), [Q_("+8 urad"), Q_("-4 urad")]):
        try:
            np.testing.assert_array_almost_equal(actual, desired, decimal=9)
        except AssertionError:
            if last_test_fail_ok:
                print(f"Assertion failed as expected: {actual} != {desired}")
            else:
                raise


# %%
all_mlvs = SR.get_all_mlvs()

# %%
# Run the test sequence. The last test SHOULD fail.
test_sequence(all_mlvs, last_test_fail_ok=True)

# %% [markdown]
# - With the live machine, when only the gap is changed, we implicitly assume that we keep the same power supply currents. Therefore, the actual x and y kick angles should change, which is being asserted in the test function.
# - However, since we are running in the internal (simulator) mode, when we only changed the gap, the x and y kick angles actually remained fixed. This resulted in the power supply current changes, and hence the assertion failures.
# - To force the internal (simulator) mode to behave in a similar manner as the live machine would, we would need to change the definition for the gap setpoint MLV.

# %%
# We modify the gap setpoint MLV such that a change in the gap value will result
# in the adjustment of the horizontal & vertical kick values in the simulator.

new_elem_def["channel_map"]["gap_SP"] = {
    "handle": "SP",
    "HiLv_reprs": ["gap"],
    "ext": dict(
        get={"input_pvs": ["extpv_gap_SP"]}, put={"output_pvs": ["extpv_gap_SP"]}
    ),
    "int": dict(
        get={"input_pvs": ["intpv_gap_SP"], "conv_spec_name": "identity"},
        put={
            "aux_input_pvs": [
                "intpv_gap_RB",
                "intpv_x_angle_SP",
                "intpv_y_angle_SP",
            ],
            "output_pvs": ["intpv_gap_SP", "intpv_x_angle_SP", "intpv_y_angle_SP"],
            "conv_spec_name": "new_gap_cur_gap_cur_x_cur_y_to_new_gap_new_x_new_y",
        },
    ),
    "pdev_def": dict(
        LIVE={"type": "standard_MIMO_SP"},
        DT={"type": "standard_MIMO_SP"},
        SIM={"type": "standard_MIMO_SP"},
    ),
}

new_elem_def["func_specs"]["new_gap_cur_gap_cur_x_cur_y_to_new_gap_new_x_new_y"] = {
    "name": "ID23d_repr_convs.from_new_gap_cur_gap_cur_x_cur_y_to_new_gap_new_x_new_y",
    "description": """A user provides a new value for 'gap'. Given the current values
      of 'gap', 'x', and 'y', first calculate the current "I1" and "I2" values. Then, assuming
      these "I1" and "I2" values are fixed, calculate the new values for "x" and "y", based on
       the new "gap" value, as the gap motion changes the kick strengths "x" and "y".""",
}  # for ("gap_SP", int, put)

SR.replace_elem_definition("ID23d", new_elem_def)

# %%
# Re-construct all the MLVs associated with the ID with the modifications
SR.construct_mlvs_for_one_element("ID23d", exist_ok=True)

# %%
# Now repeat the same test sequence, but this time all the tests should pass.
test_sequence(all_mlvs, last_test_fail_ok=False)

# %%
# We can see how the `elements.ymal` file would look like after adding the
# MIMO example.
with open(examples_folder / "demo_generated/elements_w_MIMO.yaml", "w") as f:
    yaml.dump(
        SR._conf.elem_defs,
        f,
        sort_keys=False,
        default_flow_style=False,
        width=70,
        indent=2,
        Dumper=CustomDumper,
    )
