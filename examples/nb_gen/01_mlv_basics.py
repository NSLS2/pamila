# %%
from pathlib import Path

# %%
# You can ignore about the `pydantic` deprecation warning (coming from `tiled`)
import pamila as pml
from pamila import Q_
from pamila.utils import KeyValueTagSearch

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
SR

# %%
mlvs = SR.get_all_mlvs()
mlvs

# %%
v_tags = SR.get_all_mlv_value_tags()
v_tags

# %%
kv_tags = SR.get_all_mlv_key_value_tags()
kv_tags

# %%
quad_mlvs = SR.get_mlvs_via_value_tag("QUAD")
quad_mlvs

# %%
tag_searches = [
    KeyValueTagSearch(key="cell_str", value="C30"),
    KeyValueTagSearch(key="family", value="QUAD"),
]

sel_quad_mlvs = SR.get_mlvs_via_key_value_tags(tag_searches)
sel_quad_mlvs

# %%
for mlv in mlvs.values():
    mlv.wait_for_connection()

# %%
# "C30_C1" refers to the first orbit corrector in Cell 30 at NSLS-II.
mlvs["C30_C1_x_I_RB"].get(), mlvs["C30_C1_x_I_SP"].get()

# %%
mlvs["C30_C1_x_angle_SP"].get(), mlvs["C30_C1_x_angle_RB"].get()

# %%
mlv = mlvs["C30_C1_x_I_SP"]

pdev = mlv.get_device()

pdev._machine_name, pdev._mode

# %%
# Switch to DT mode.
# Notice that MLV now points to the pamila device (pdev) for DT, not SIM.
pml.set_online_mode(pml.MachineMode.DIGITAL_TWIN)
pml.go_online()
pdev = mlv.get_device()

pdev._machine_name, pdev._mode

# %%
# Go back to the simulator mode
pml.go_offline()

# %%
mlv.name

# %%
mlv.get()

# %%
mlv.read()

# %%
# Should result in a TypeError
try:
    mlv.put(0.1)
except Exception as e:
    assert isinstance(e, TypeError), f"Expected TypeError, but got {type(e).__name__}"
    assert str(e) == "Wrong type: <class 'float'>"
    print("Failed as expected!")
    print("Must pass a pint.Q_ object, instead of a float object")
except:
    raise

# %%
# You must pass a pint Quantity object `Q_`.
mlv.put(Q_("0.1 A"))

# %%
# Confirm that the value for the MLV has been changed
mlv.get()

# %%
# Note that the setpoint value in "x_angle" repr. is also no longer zero radian.
mlvs["C30_C1_x_angle_SP"].get()

# %%
# Check out other MLVs
dcct_mlv = SR.get_mlv("Beam_Current_I_RB")
nux_mlv = SR.get_mlv("BxB_Tune_nux_RB")
nuy_mlv = SR.get_mlv("BxB_Tune_nuy_RB")

# %%
dcct_mlv.get()

# %%
nux_mlv.get()

# %%
nuy_mlv.get()
