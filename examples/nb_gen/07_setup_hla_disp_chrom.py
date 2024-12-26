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

# %%
machine_name = "SR"
SR = pml.load_machine(machine_name, dirpath=FACILITY_CONFIG_FOLDER)

# %%
pml.load_hla_defaults(FACILITY_CONFIG_FOLDER / "hla_defaults.yaml")

# %%
# Print the current default parameters for all HLAs, which should only have
# the params specified for the `orbit.slow_acq` HLA.
#
# In this notebook, we will set up the params associated with the `disp_chrom` HLA.
pml.hla.get_hla_defaults()

# %%
# Print all available flow names for the `disp_chrom` high-level application (HLA)
pml.hla.disp_chrom.get_flow_names()

# %%
# Select the "standalone" flow.
#
# But, as was the case with the `orbit.slow_acq` HLA, this SHOULD result in an
# error message:
#  TypeError: Machine default is requested, but it does not appear to be set up
try:
    standalone = pml.hla.disp_chrom.get_flow("standalone", SR)
except Exception as e:
    assert isinstance(e, TypeError), f"Expected TypeError, but got {type(e).__name__}"
    assert str(e) == "Machine default is requested, but it does not appear to be set up"
    print("Failed as expected!")
except:
    raise

# %%
# As before, we temporarily avoid this error by:
pml.hla.allow_machine_default_placeholder()

standalone = pml.hla.disp_chrom.get_flow("standalone", SR)

# %%
# Print all the stage names for the flow
standalone.get_stage_names()

# %%
# Get the params for the "acquire" stage
params = standalone.get_params("acquire")
params

# %%
# Note that "rf_freq_mlv_SP", "orbit_meas", and "tune_meas" are `MachineDefault`
# objects (i.e., placeholders).
# This HLA will NOT work if these parameters are not specified, which is the
# reason for the earlier error message "TypeError: Machine default is requested..."
list(params)

# %%
# Set MLV parameters
params.rf_freq_mlv_SP = SR.get_mlv("RF_Freq_freq_SP")
params.rf_freq_mlv_RB = SR.get_mlv("RF_Freq_freq_RB")

# %%
# You can also change the default values for other params, if you want.
#
# Note bluesky/tiled for HLAs have not been implemented yet.
params.n_freq_pts = 5
params.max_delta_freq = Q_("200 Hz")
params.min_delta_freq = Q_("-200 Hz")
params.extra_settle_time = Q_("3 s")

# %%
# Set "orbit_meas" `HlaFlow` object
orbit_flow = pml.hla.orbit.slow_acq.get_flow("library", SR)
orbit_flow_params = orbit_flow.get_params("acquire")
list(orbit_flow_params)

# %%
# As the default parameters for the `orbit.slow_acq`'s HlaFlow object have
# been specified and saved in the previous notebook, the default HlaFlow
# object can be used "as is".
# But, if any parameter needs to be changed for the `disp_chrom` HLA, you can
# change them here.
orbit_flow_params.n_meas = 8

# %%
# For the `tunes.via_pvs` HlaFlow object, no default parameters have been yet
# specified, as "tune_mlvt" can be seen set as `MachineDefault`, which you must
# specify to be able to run the `tunes.via_pvs` HlaFlow.
tune_flow = pml.hla.tunes.via_pvs.get_flow("library", SR)
tune_flow_params = tune_flow.get_params("acquire")
list(tune_flow_params)

# %%
tune_flow_params.tune_mlvt = SR.get_mlvt("Tunes")

# %%
# Also adjust other params for the `acquire` stage of `tunes.via_pvs` HlaFlow
tune_flow_params.n_meas = 3
tune_flow_params.wait_btw_meas = Q_("1 s")

# %%
# Update the default params for the `acquire` stage of `tunes.via_pvs` in memory.
stage = tune_flow.get_stage("acquire")
stage.update_machine_default_params(tune_flow_params)

# %%
pml.hla.get_hla_defaults()

# %%
# Now save the current params for orbit/tune flows in memory as the default for
# the `acquire` stage of the `disp_chrom` HLA
params.orbit_meas = orbit_flow
params.tune_meas = tune_flow

stage = standalone.get_stage("acquire")
stage.update_machine_default_params(params)

# %%
pml.hla.get_hla_defaults()

# %%
# For the `disp_chrom` HLA standalone flow to be run, there is one more param
# in the `postprocess` stage that needs to be specified.
params = standalone.get_params("postprocess")
list(params)

# %%
# We set the design value of momentum compaction as the default
from pamila.utils import DesignLatticeProperty

params.momentum_compaction = DesignLatticeProperty()
# If you want to manually specify a float value here, you can do so instead.

stage = standalone.get_stage("postprocess")
stage.update_machine_default_params(params)

# %%
pml.hla.get_hla_defaults()

# %%
# If you want the default param changes above to be persistent, save the changes
# in the params object into the YAML file that specifies the default HLA parameters.
hla_defaults_filepath = FACILITY_CONFIG_FOLDER / "hla_defaults.yaml"

pml.hla.save_hla_defaults_to_file(hla_defaults_filepath)

# %%
# You can now recover the default params from the saved YAML file.
pml.load_hla_defaults(hla_defaults_filepath)

pml.hla.get_hla_defaults()

# %% [markdown]
# This concludes the initial setup for the default params for the `disp_chrom` HLA.

# %%
# Before we move onto actually running the standalone HLA flow in this notebook,
# you need to undo the special setup we applied, as we did in "06_hla_orbit.ipynb".
# If you are starting a fresh run, this step is not necessary.
pml.hla.disallow_machine_default_placeholder()
