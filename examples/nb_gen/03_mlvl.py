# %%
from pathlib import Path

# %%
# You can ignore about the `pydantic` deprecation warning (coming from `tiled`)
import pamila as pml
from pamila import Q_
from pamila.middle_layer import MiddleLayerVariableListRO, MiddleLayerVariableListROSpec

# "RO" stands for read-only
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
# Collect all MLVs for BPMs
bpm_mlvs = [mlv for mlv_name, mlv in SR.get_all_mlvs().items() if "_P" in mlv_name]

[mlv.name for mlv in bpm_mlvs]

# %%
# Try to create a read-only MLVL (MLV list) for the BPMs (both x and y planes)
#
# `exist_ok` should be set to `False` (default) if you want to avoid overwriting
# an existing MLVL with the same name.
spec = MiddleLayerVariableListROSpec(name="bpms_xy", exist_ok=False, mlvs=bpm_mlvs)
mlvl = MiddleLayerVariableListRO(spec)
mlvl.wait_for_connection(all_modes=False)

# %%
# This should FAIL because "bpms_xy" has been already used for an existing MLVL
try:
    spec = MiddleLayerVariableListROSpec(name="bpms_xy", exist_ok=False, mlvs=bpm_mlvs)
    duplicate_mlvl = MiddleLayerVariableListRO(spec)
except Exception as e:
    assert isinstance(e, NameError), f"Expected NameError, but got {type(e).__name__}"
    assert str(e) == "MiddleLayerVariableListRO name `bpms_xy` is already defined"
    print("Failed as expected!")
except:
    raise

# %%
# This should NOT fail. This new MLVL definition will override.
spec = MiddleLayerVariableListROSpec(name="bpms_xy", exist_ok=True, mlvs=bpm_mlvs)
duplicate_mlvl = MiddleLayerVariableListRO(spec)

# %%
# MLVL objects are serializable.
import pickle

pickle.loads(pickle.dumps(mlvl))

# %%
# Whenever a new MLVL object is created, it will be registered to the machine
# such that it becomes searchable by the name.
SR.get_all_mlvls()

# %%
mlv = SR.get_all_mlvs()["C30_C1_x_I_SP"]

# Change the corrector strength to introduce orbit distortion (to avoid BPM
# readings being all zero)
mlv.put(Q_("0.1 A"))

# %%
# Since Q_ (pint's quantity object) is an iterable object, each MLV returns a
# non-scalar value. By default, the `get` method of MLVL will faltten all the
# Q_ objects.
bpm_readings_flat = mlvl.get()
bpm_readings_flat

# %%
# "get" can also return a list of Q_'s
bpm_readings_non_flat = mlvl.get(return_flat=False)
bpm_readings_non_flat

# %%
# An individual MLV in the MLVL can be accessed like a list
mlvl[0]

# %%
mlvl[0].get()

# %%
# The "read" method is also implemented for MLVL
read_data = mlvl.read()
read_data

# %%
# The method that returns the number of MLVs included in this MLVL
mlvl.get_all_mlv_count()

# %%
# Check which MLVs in this MLVL are currently enabled
[_mlv.name for _mlv in mlvl.get_enabled_mlvs()]

# %%
# Show all MLVs included in this MLVL (i.e., including disabled ones)
[_mlv.name for _mlv in mlvl.get_all_mlvs()]

# %%
# All 12 values are returned by the "get" method
current_vals = mlvl.get()
print(f"{len(current_vals) = }")
current_vals

# %%
enabled_list = mlvl.get_enabled_status()
enabled_list

# %%
# Disable the second MLV (but not yet applied)
enabled_list[1] = False
enabled_list

# %%
# Actually apply the enabled state change
mlvl.put_enabled_status(enabled_list)

# %%
# Confirm the enabled state change has been applied
mlvl.get_enabled_status()

# %%
# Confirm the MLV "C30_P1_y_RB" is now excluded
[_mlv.name for _mlv in mlvl.get_enabled_mlvs()]

# %%
# "C30P1_y_RB" is still included in the output of "get_all_mlvs()"
[_mlv.name for _mlv in mlvl.get_all_mlvs()]

# %%
# The "get_mlv_names" method only returns the names of the enabled MLVs.
mlvl.get_mlv_names()

# %%
# Now only 11 values are returned by "get"
current_vals = mlvl.get()
print(f"{len(current_vals) = }")
current_vals

# %%

# %%
# This should FAIL with RuntimeError because we have not specified
# "enabled status" MLVL.
# An example to specify this MLVL is to be written in the near future.
try:
    mlvl.update_status_mlvl()
except Exception as e:
    assert isinstance(
        e, RuntimeError
    ), f"Expected RuntimeError, but got {type(e).__name__}"
    assert str(e) == "Status MLV list has not been specified"
    print("Failed as expected!")
except:
    raise
