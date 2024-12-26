# %%
import json
from pathlib import Path

# %%
# You can ignore about the `pydantic` deprecation warning (coming from `tiled`)
import pamila as pml
from pamila import Q_
from pamila.middle_layer import (
    MiddleLayerVariableList,
    MiddleLayerVariableListRO,
    MiddleLayerVariableListROSpec,
    MiddleLayerVariableListSpec,
    MiddleLayerVariableTree,
    MiddleLayerVariableTreeSpec,
)

# %%
# Activate the simulator mode (i.e., neither LIVE nor DT [Digital Twin])
pml.go_offline()

# %%
facility_name = pml.machine.get_facility_name()
FACILITY_CONFIG_FOLDER = Path("demo_generated") / facility_name

# %%
machine_name = "SR"
SR = pml.load_machine(machine_name, dirpath=FACILITY_CONFIG_FOLDER)

# %%
all_mlvs = SR.get_all_mlvs()

# %%
# Confirm that no MLVLs have been currently defined.
# If not, call `SR.get_all_mlvls().clear()`.
SR.get_all_mlvls()

# %%
# Confirm that no MLVTs have been currently defined.
# If not, call `SR.get_all_mlvts().clear()`.
SR.get_all_mlvts()

# %% [markdown]
# # Define standard MLVLs

# %%
spec = MiddleLayerVariableListROSpec(
    name="BPM_x",
    mlvs=[
        mlv
        for mlv_name, mlv in all_mlvs.items()
        if ("_P" in mlv_name) and ("_x_" in mlv_name)
    ],
)
mlvl_bpm_x = MiddleLayerVariableListRO(spec)
mlvl_bpm_x.get_mlv_names()

# %%
spec = MiddleLayerVariableListROSpec(
    name="BPM_y",
    mlvs=[
        mlv
        for mlv_name, mlv in all_mlvs.items()
        if ("_P" in mlv_name) and ("_y_" in mlv_name)
    ],
)
mlvl_bpm_y = MiddleLayerVariableListRO(spec)
mlvl_bpm_y.get_mlv_names()

# %%
spec = MiddleLayerVariableListROSpec(
    name="BPM_xy", mlvs=mlvl_bpm_x.get_all_mlvs() + mlvl_bpm_y.get_all_mlvs()
)
mlvl_bpm_xy = MiddleLayerVariableListRO(spec)
mlvl_bpm_xy.get_mlv_names()

# %%
# All MLVL definitions for slow orbit correctors
scor_Ls = {}

# Setpoint MLVLs
for repr in ["x_I", "y_I", "x_angle", "y_angle"]:
    name = f"scor_{repr}_SP"
    sel_mlv_list = [
        mlv
        for mlv_name, mlv in all_mlvs.items()
        if "_C" in mlv_name and f"_{repr}_" in mlv_name and mlv_name.endswith("_SP")
    ]
    spec = MiddleLayerVariableListSpec(name=name, mlvs=sel_mlv_list)
    scor_Ls[name] = MiddleLayerVariableList(spec)

# Readback MLVLs
for repr in ["x_I", "y_I", "x_angle", "y_angle"]:
    name = f"scor_{repr}_RB"
    sel_mlv_list = [
        mlv
        for mlv_name, mlv in all_mlvs.items()
        if "_C" in mlv_name and f"_{repr}_" in mlv_name and mlv_name.endswith("_RB")
    ]
    spec = MiddleLayerVariableListROSpec(name=name, mlvs=sel_mlv_list)
    scor_Ls[name] = MiddleLayerVariableListRO(spec)

scor_Ls

# %%
spec = MiddleLayerVariableListROSpec(
    name="Tune_x", mlvs=[SR.get_mlv("BxB_Tune_nux_RB")]
)
mlvl_tune_x = MiddleLayerVariableListRO(spec)
mlvl_tune_x.get_mlv_names()

# %%
spec = MiddleLayerVariableListROSpec(
    name="Tune_y", mlvs=[SR.get_mlv("BxB_Tune_nuy_RB")]
)
mlvl_tune_y = MiddleLayerVariableListRO(spec)
mlvl_tune_y.get_mlv_names()

# %%
spec = MiddleLayerVariableListROSpec(
    name="DCCT", mlvs=[SR.get_mlv("Beam_Current_I_RB")]
)
mlvl_dcct = MiddleLayerVariableListRO(spec)
mlvl_dcct.get_mlv_names()

# %%
SR.get_all_mlvls()

# %% [markdown]
# # Define standard MLVTs

# %%
# BPM MLV Tree
spec = MiddleLayerVariableTreeSpec(name="BPM", mlos={"x": mlvl_bpm_x, "y": mlvl_bpm_y})
mlvt_bpm = MiddleLayerVariableTree(spec)
mlvt_bpm.get_mlvl_names()

# %%
# (Slow) Orbit Corrector MLV Tree
scor_Ts = {}
for repr in ["I", "angle"]:
    for handle in ["SP", "RB"]:
        name = f"scor_{repr}_{handle}"
        spec = MiddleLayerVariableTreeSpec(
            name=name,
            mlos={
                "x": scor_Ls[f"scor_x_{repr}_{handle}"],
                "y": scor_Ls[f"scor_y_{repr}_{handle}"],
            },
        )
        scor_Ts[name] = MiddleLayerVariableTree(spec)

scor_Ts

# %%
scor_Ts["scor_I_SP"].get()

# %%
scor_Ts["scor_I_RB"].get()

# %%
scor_Ts["scor_angle_SP"].get()

# %%
scor_Ts["scor_angle_RB"].get()

# %%
spec = MiddleLayerVariableTreeSpec(
    name="Tunes", mlos={"x": mlvl_tune_x, "y": mlvl_tune_y}
)
MiddleLayerVariableTree(spec)

# %%
SR.get_all_mlvts()

# %% [markdown]
# # Save MLVL definitions

# %%
import yaml


class CustomDumper(yaml.SafeDumper):
    def represent_list(self, data):
        # Force lists to be represented in flow style (inline `[]` style)
        return self.represent_sequence("tag:yaml.org,2002:seq", data, flow_style=True)


# Add the custom list representation to the dumper
CustomDumper.add_representer(list, CustomDumper.represent_list)

# %%
machine_folder = FACILITY_CONFIG_FOLDER / machine_name
sel_config_folder = machine_folder / SR._conf.sel_config_name
sel_config_folder

# %%
mlvl_defs = {}
exclude_unset = True
for mlvl in SR.get_all_mlvls().values():
    model_d = mlvl.get_reconstruction_spec(exclude_unset=exclude_unset)

    name = model_d.pop("name")
    class_name = model_d.pop("class")
    mlvl_defs[name] = {"class_suffix": class_name[len("MiddleLayerVariable") :]}

    temp_mlvs = json.loads(json.dumps(model_d["mlvs"]))
    model_d["mlvs"] = [_mlv_d["name"] for _mlv_d in temp_mlvs]
    mlvl_defs[name].update(model_d)

# %%
mlvl_defs_for_file = {
    "facility": facility_name,
    "machine": machine_name,
    "mlvl_definitions": mlvl_defs,
}
# ^ Another key "simulator_config" was defined in all the files saved in
# "00_steup_machine_config.ipynb". However, this key is NOT included in this
# dict, because each MLV contains that information.
with open(sel_config_folder / "mlvls.yaml", "w") as f:
    yaml.dump(
        mlvl_defs_for_file,
        f,
        sort_keys=False,
        default_flow_style=False,
        width=70,
        indent=2,
        Dumper=CustomDumper,
    )
with open(sel_config_folder / "mlvls.json", "w") as f:
    json.dump(mlvl_defs_for_file, f, indent=2)

# %% [markdown]
# # Save MLVT definitions

# %%
mlvt_defs = {}
exclude_unset = True
for mlvt in SR.get_all_mlvts().values():
    model_d = mlvt.get_reconstruction_spec(exclude_unset=exclude_unset)

    name = model_d.pop("name")
    class_name = model_d.pop("class")

    temp_mlos = json.loads(json.dumps(model_d["mlos"]))
    for k, v in temp_mlos.items():
        del v["machine_name"]
        model_d["mlos"][k] = v
    mlvt_defs[name] = model_d

# %%
mlvt_defs_for_file = {
    "facility": facility_name,
    "machine": machine_name,
    "mlvt_definitions": mlvt_defs,
}
# ^ Another key "simulator_config" was defined in all the files saved in
# "00_steup_machine_config.ipynb". However, this key is NOT included in this
# dict, because each MLV contains that information.
with open(sel_config_folder / "mlvts.yaml", "w") as f:
    yaml.dump(
        mlvt_defs_for_file,
        f,
        sort_keys=False,
        default_flow_style=False,
        width=70,
        indent=2,
        Dumper=CustomDumper,
    )
with open(sel_config_folder / "mlvts.json", "w") as f:
    json.dump(mlvt_defs_for_file, f, indent=2)
