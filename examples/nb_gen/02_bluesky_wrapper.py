# %%
import os
from pathlib import Path

# %%
import numpy as np

# %%
# You can ignore about the `pydantic` deprecation warning (coming from `tiled`)
import pamila as pml
from pamila import Unit

# %%
# Activate the simulator mode (i.e., neither LIVE nor DT [Digital Twin])
pml.go_offline()

# %%
# Imports related to bluesky/tiled

from pamila import bluesky_wrapper, bsw

assert bsw == bluesky_wrapper

from bluesky.callbacks import LiveTable
import tiled.utils

from pamila.tiled import (  # This `TiledWriter` is a modified version
    TiledWriter,
    get_client,
)

assert tiled.utils.safe_json_dump.__name__ == "_modified_safe_json_dump"

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

for mlv in all_mlvs.values():
    mlv.wait_for_connection()

# %%
use_Ampere = True
# use_Ampere = False

if use_Ampere:
    cor_name_list = ["C30_C1_x_I_SP", "C30_C2_x_I_SP"]
else:
    cor_name_list = ["C30_C1_x_angle_SP", "C30_C2_x_angle_SP"]

bpm_name_list = ["C30_P1_x_RB", "C30_P1_y_RB"]

bpm_list = [all_mlvs[name] for name in bpm_name_list]
cor_list = [all_mlvs[name] for name in cor_name_list]

# %%
if use_Ampere:
    dI_start = -0.2
    dI_stop = +0.2
    dI_array = np.linspace(dI_start, dI_stop, 3)
    dI_array *= Unit("A")
else:
    dI_start = -4
    dI_stop = +4
    dI_array = np.linspace(dI_start, dI_stop, 3)
    dI_array *= Unit("urad")
dI_array_1 = (
    dI_array.tolist()
)  # Must convert to a list due to a bug in TiledWriter metadata updating

if use_Ampere:
    dI_start = -0.3
    dI_stop = +0.3
    dI_array = np.linspace(dI_start, dI_stop, 3)
    dI_array *= Unit("A")
else:
    dI_start = -6
    dI_stop = +6
    dI_array = np.linspace(dI_start, dI_stop, 3)
    dI_array *= Unit("urad")
dI_array_2 = (
    dI_array.tolist()
)  # Must convert to a list due to a bug in TiledWriter metadata updating

assert len(dI_array_1) == len(dI_array_2)

# %%
case = "A"

if case == "A":
    set_mode = bsw.JumpSet()
elif case == "B":
    set_mode = bsw.RampSet(
        num_steps=None,
        interval=None,
        current_val_signals=None,
        wait_at_each_step=True,
    )
elif case == "C":
    set_mode = bsw.RampSet(
        num_steps=5, interval=4.0, current_val_signals=None, wait_at_each_step=True
    )
else:
    raise ValueError

# %% [markdown]
# To initialize a SQLite server file, first `cd` into a folder where
# you want to create the database file, and then run in a terminal:
#
# `(env) $ tiled catalog init catalog.db`
#
# To start the SQLite server, `cd` into the folder where the database file is,
# and then run:
#
# `(env) $ tiled catalog serve catalog.db -w data/ --api-key=secret`
#
# (This will create a "data" folder in `cwd`, if it does not exist.)
#
# Look for a line in the output of this command like this:
#
# `[-] INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)`
#
# If you encounter an error like the following instead:
#
# `[-] ERROR:    [Errno 98] error while attempting to bind on address ('127.0.0.1',
# 8000): address already in use`
#
# then change the port number manually to, e.g., 8001, by adding "--port 8001",
# to the `tiled` command above.

# %%
# If you had to change the default port number of 8000, you must change
# `_tiled_port` to the actual port number.
_tiled_port = 8000
os.environ["PAMILA_TILED_URI"] = f"http://localhost:{_tiled_port}"
os.environ["PAMILA_TILED_API_KEY"] = "secret"

# %%
# Make a connection to the `tiled` database
client = get_client()
tw = TiledWriter(client)

# %%
# MLVs that will be monitored by `LiveTable` during the bluesky scan
sel_mlvs = bpm_list + cor_list
sel_mlvs

# %%
# bluesky's `LiveTable` only accepts `ophyd` device objects, not MLVs.
sel_odevs = [mlv.get_ophyd_device() for mlv in sel_mlvs]

output = bsw.rel_put_then_get(
    obj_list_to_get=bpm_list,
    obj_list_to_put=cor_list,
    vals_to_put=[dI_array_1, dI_array_2],
    set_mode=set_mode,
    extra_settle_time=2.0,
    n_repeat=3,
    wait_time_btw_read=0.2,
    subs={"all": [tw, LiveTable(sel_odevs)]},
    ret_raw=True,
    stats_types=("mean", "std", "min", "max"),
)

# %%
list(output)

# %%
# `uid` for the experiment run saved in the `tiled` database
output["uids"]

# %%
output["metadata"]

# %%
output["raw_data"]

# %%
# The unit strings for the columns of the `pandas` DataFrame "output['raw_data']"
output["units"]

# %%
list(output["stats"])

# %%
output["stats"]["mean"]

# %%
output["stats"]["std"]
