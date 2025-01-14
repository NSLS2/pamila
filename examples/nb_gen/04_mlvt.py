# %%
from pathlib import Path
import time

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
cwd = Path.cwd()
if cwd.name == "examples":
    examples_folder = cwd
else:
    assert cwd.name == "nb_gen"
    examples_folder = cwd.parent
FACILITY_CONFIG_FOLDER = examples_folder / "demo_generated" / facility_name

# %%
machine_name = "SR"
SR = pml.load_machine(machine_name, dirpath=FACILITY_CONFIG_FOLDER)

# %%
all_mlvs = SR.get_all_mlvs()

# %%
# MLVT (MLV tree) requires MLVLs (not MLVs). So, we will first define MLVLs.

# Define the MLVL "scors_x" for horizontal slow orbit corrector RB MLVs (in
# "x_angle" repr.)
spec = MiddleLayerVariableListROSpec(
    name="scors_x",
    mlvs=[
        mlv
        for mlv_name, mlv in all_mlvs.items()
        if "_C" in mlv_name and "_x_angle_" in mlv_name and mlv_name.endswith("_RB")
    ],
)
mlvl_scor_x = MiddleLayerVariableListRO(spec)
mlvl_scor_x.get_mlv_names()

# %%
mlvl_scor_x.get()

# %%
# Define the MLVL "scors_y" for vertical slow orbit corrector RB MLVs (in
# "y_I" repr.)
spec = MiddleLayerVariableListROSpec(
    name="scors_y",
    mlvs=[
        mlv
        for mlv_name, mlv in all_mlvs.items()
        if "_C" in mlv_name and "_y_I_" in mlv_name and mlv_name.endswith("_RB")
    ],
)
mlvl_scor_y = MiddleLayerVariableListRO(spec)
mlvl_scor_y.get_mlv_names()

# %%
mlvl_scor_y.get()

# %%
spec = MiddleLayerVariableListROSpec(
    name="bpms_x",
    mlvs=[
        mlv
        for mlv_name, mlv in all_mlvs.items()
        if "_P" in mlv_name and "_x_" in mlv_name
    ],
)
mlvl_bpm_x = MiddleLayerVariableListRO(spec)
mlvl_bpm_x.get_mlv_names()

# %%
spec = MiddleLayerVariableListROSpec(
    name="bpms_y",
    mlvs=[
        mlv
        for mlv_name, mlv in all_mlvs.items()
        if "_P" in mlv_name and "_y_" in mlv_name
    ],
)
mlvl_bpm_y = MiddleLayerVariableListRO(spec)
mlvl_bpm_y.get_mlv_names()

# %%
# Define the MLVL "QH1_K1_K1L" for the QH1 quadrupole RB MLVs (in
# "K1" and "K1L" reprs.)
spec = MiddleLayerVariableListROSpec(
    name="QH1_K1_K1L",
    mlvs=[
        mlv
        for mlv_name, mlv in all_mlvs.items()
        if "QH1" in mlv_name
        and ("_K1_" in mlv_name or "_K1L_" in mlv_name)
        and mlv_name.endswith("_RB")
    ],
)
mlvl_QH1_K1_K1L = MiddleLayerVariableListRO(spec)
mlvl_QH1_K1_K1L.get_mlv_names()

# %%
mlvl_QH1_K1_K1L.get()

# %%
SR.get_all_mlvls()

# %%
# Define an MLVT (MLV Tree)
spec = MiddleLayerVariableTreeSpec(name="QH1", mlos={"K1_and_K1L": mlvl_QH1_K1_K1L})
mlvt_QH1_K1_K1L_RB = MiddleLayerVariableTree(spec)

# %%
mlvt_QH1_K1_K1L_RB.get_mlvl_names()

# %%
# You can also create nested MLVTs like this:
spec = MiddleLayerVariableTreeSpec(
    name="SCOR_and_QH1",
    mlos={"x": mlvl_scor_x, "y": mlvl_scor_y, "QH1": mlvt_QH1_K1_K1L_RB},
)
mlvt_scor_QH1 = MiddleLayerVariableTree(spec)

spec = MiddleLayerVariableTreeSpec(
    name="BPM_and_SCOR_and_QH1",
    mlos={"bpm_x": mlvl_bpm_x, "bpm_y": mlvl_bpm_y, "scor_and_QH1": mlvt_scor_QH1},
)
mlvt_RB = MiddleLayerVariableTree(spec)

# %%
# MLVT's "get_mlvl_names" method returns a flat anme list of all MLVLs.
mlvt_RB.get_mlvl_names()

# %%
# MLVT's "get_enabled_mlvs" method returns a flat list of all enabled MLVs.
[_mlv.name for _mlv in mlvt_RB.get_enabled_mlvs()]

# %%
# MLVT's "get" method retains the nested structure
mlvt_RB.get()

# %%
# MLVT's "read" method does NOT have the nested structure. Instead, it
# obtains the flat data for all the underlying pamila signal objects.
mlvt_RB.read()

# %%
# Until now, only read-only MLVLs were used to define MLVTs, but
# MLVTs can take writable MLVLs as well.
spec = MiddleLayerVariableListSpec(
    name="scors_x_SP",
    mlvs=[
        mlv
        for mlv_name, mlv in all_mlvs.items()
        if "_C" in mlv_name and "_x_angle_" in mlv_name and mlv_name.endswith("_SP")
    ],
)
mlvl_scor_x_SP = MiddleLayerVariableList(spec)

spec = MiddleLayerVariableListSpec(
    name="scors_y_SP",
    mlvs=[
        mlv
        for mlv_name, mlv in all_mlvs.items()
        if "_C" in mlv_name and "_y_I_" in mlv_name and mlv_name.endswith("_SP")
    ],
)
mlvl_scor_y_SP = MiddleLayerVariableList(spec)

spec = MiddleLayerVariableTreeSpec(
    name="scor", mlos={"x": mlvl_scor_x_SP, "y": mlvl_scor_y_SP}
)
mlvt_scor_SP = MiddleLayerVariableTree(spec)

spec = MiddleLayerVariableListSpec(
    name="QH1_K1_SP",
    mlvs=[
        mlv
        for mlv_name, mlv in all_mlvs.items()
        if "QH1" in mlv_name and "_K1_" in mlv_name and mlv_name.endswith("_SP")
    ],
)
mlvl_QH1_K1_SP = MiddleLayerVariableList(spec)

spec = MiddleLayerVariableTreeSpec(
    name="scor_xy_and_QH1_K1_SP",
    mlos={"scor": mlvt_scor_SP, "QH1_K1": mlvl_QH1_K1_SP},
)
mlvt_SP = MiddleLayerVariableTree(spec)

mlvt_SP.wait_for_connection(all_modes=False)

# %%
cur_SP_val_d = mlvt_SP.get()
RB_before_put = mlvt_RB.get()

cur_SP_val_d

# %%
# Note that you can partially modify the setpoints of MLVT.
# Here, the vertical orbit corrector has been removed to demonstrate this.
del cur_SP_val_d["scor"]["y"]
cur_SP_val_d

# %%
# Change the orbit corrector & quad slightly
cur_SP_val_d["scor"]["x"] += Q_("5 urad")
cur_SP_val_d["QH1_K1"] -= Q_("1e-3 m^{-2}")
mlvt_SP.put(cur_SP_val_d)

# %%
# Check the adjustments took place
new_SP_val_d = mlvt_SP.get()
RB_after_put = mlvt_RB.get()

new_SP_val_d

# %%
# Revert to the original
cur_SP_val_d["scor"]["x"] -= Q_("5 urad")
cur_SP_val_d["QH1_K1"] += Q_("1e-3 m^{-2}")
mlvt_SP.put(cur_SP_val_d)

# %%
# Check the adjustments took place
restored_val_d = mlvt_SP.get()
RB_after_restore = mlvt_RB.get()

# %%
RB_before_put

# %%
RB_after_put

# %%
RB_after_restore

# %%
# The "set" method returns device status objects, but does not wait
# for the status change.
mlvt_SP.set(new_SP_val_d)

# %%
# The "set_and_wait" method will change the setpoints and then wait
# for the status objects to become all "done".
t0 = time.perf_counter()
mlvt_SP.set_and_wait(cur_SP_val_d)
print(f"set_and_wait took {time.perf_counter()-t0:.3f} [s]")

# %%
# MLVT objects are serializable.
import pickle

print(pickle.loads(pickle.dumps(mlvt_RB)))
print(pickle.loads(pickle.dumps(mlvt_SP)))
