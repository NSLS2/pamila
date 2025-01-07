# %%
from pathlib import Path

# %%
# You can ignore about the `pydantic` deprecation warning (coming from `tiled`)
import pamila as pml
from pamila import Q_
from pamila.middle_layer import sort_by_spos
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
# See all tag values (i.e., flattened tags) available for all MLVs.
v_tags = SR.get_all_mlv_value_tags()
v_tags

# %%
# See all labeled tags (i.e., key-values pairs) available for all MLVs.

kv_tags = SR.get_all_mlv_key_value_tags()
kv_tags

# %%
# Search and retrieve all MLVs with the "QUAD" tag
quad_mlvs = SR.get_mlvs_via_value_tag("QUAD")
quad_mlvs

# %%
# Search and retrieve all MLVs whose "cell_str" and "family" tags are "C30" and
# "QUAD", respectively.
tag_searches = [
    KeyValueTagSearch(key="cell_str", value="C30"),
    KeyValueTagSearch(key="family", value="QUAD"),
]

sel_quad_mlvs = SR.get_mlvs_via_key_value_tags(tag_searches)
sel_quad_mlvs

# %%
# PAMILA also has "element" objects. You can get all elements within the machine
# "SR" with the following:
SR.get_all_elems()

# %%
# Similar to MLVs, you can search and retrieve elements.
# Search and retrieve all elements within the machine "SR" like this (by the way,
# this is equivalent to `SR.get_all_elems()`):
SR.get_elems_via_name("*")

# %%
# Search and retrieve all elements whose names match the "*P[3-5]" `fnmatch`
# (i.e., `glob` like) pattern.
SR.get_elems_via_name("*P[3-5]")

# %%
# Default for `search_type` is "fnmatch", but can be changed to "exact" for
# exact matching, "regex" for case-sensitive regular expression matching, and
# "regex/i" for case-insensitive regular expression matching.
SR.get_elems_via_name("02", search_type="regex")

# %%
# Search and retrieve all elements whose names match the case-sensitive regular
# expression matching for "qh". No element should match.
SR.get_elems_via_name("qh", search_type="regex")

# %%
# Try a case-insensitive matching, which should return non-empty dict.
SR.get_elems_via_name("qh", search_type="regex/i")

# %%
# Instead of element names, you can also search and retrieve elements via
# element tag values (i.e., flattened tags).
SR.get_elems_via_value_tag("sext", search_type="regex/i")

# %%
# Similar to MLVs, you can also search and retrieve elments via labeled tags
# (i.e., key-values pairs).
tag_searches = [
    KeyValueTagSearch(key="family", value="QUAD"),
]

SR.get_elems_via_key_value_tags(tag_searches)

# %%
# You can narrow search by a sequence of filters.
tag_searches = [
    KeyValueTagSearch(key="family", value="QUAD"),
    KeyValueTagSearch(key="cell_str", value="C30"),
]

sel_quad_elems = SR.get_elems_via_key_value_tags(tag_searches)
sel_quad_elems

# %%
# Instead of searching all MLVs under a particular machine ("SR"
# in this example), you can also retrieve MLVs that belong only to a certain
# element, for example, "C30_QH1".
# You can see all available channel names for the "C30_QH1" element
quad = sel_quad_elems["C30_QH1"]

quad.get_all_channel_names()

# %%
# You can get MLV from the selected element via the channel name "K1_SP"
quad.get_mlv("K1_SP")


# %%
# You can sort the elements by s-positions in the ascending order.
# "s_c" denotes the center s-pos.
sel_elems = SR.get_elems_via_name("*")

sort_by_spos(sel_elems)

# %%
# By default, elements with "nan" s-pos are excluded when being sorted, but
# you can keep them, if you want. Those elements will appear at the end.
sort_by_spos(sel_elems, exclude_nan=False)

# %%
# You can also get neighbor elements of a given element.
#
# In this example, we are trying to find 2 BPMs upstream ("us") of "C30_QH1" quad
# and 2 BPMs downstream ("ds") of the same quad. Both upstream and downstream
# neighbor searching wraps around the ring, if needed.
quads = SR.get_elems_via_value_tag("QUAD")
bpms = SR.get_elems_via_value_tag("BPM")

quads["C30_QH1"].get_neighbors(bpms, n_ds=2, n_us=2)

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
