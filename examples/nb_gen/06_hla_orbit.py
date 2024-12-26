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

# Note that the following messages shown when this cell is run in the previous
# notebooks are gone because MLVL and MLVT definition files were created in
# "05_setup_mlvl_mlvt.ipynb":
#
#   MLVL definitions have not been specified. No MLVL will be instantiated.
#   MLVT definitions have not been specified. No MLVT will be instantiated.

# %%
# Change the corrector strength to introduce orbit distortion (to avoid BPM
# readings being all zero)
mlvs = SR.get_all_mlvs()
mlv = mlvs["C30_C1_x_I_SP"]
mlv.put(Q_("0.1 A"))

# %%
# Print all available flow names for the `orbit.slow_acq` high-level
# application (HLA)
pml.hla.orbit.slow_acq.get_flow_names()

# %%
# Select the "standalone" flow.
#
# But this SHOULD result in an error message:
#  TypeError: Machine default is requested, but it does not appear to be set up
try:
    standalone = pml.hla.orbit.slow_acq.get_flow("standalone", SR)
except Exception as e:
    assert isinstance(e, TypeError), f"Expected TypeError, but got {type(e).__name__}"
    assert str(e) == "Machine default is requested, but it does not appear to be set up"
    print("Failed as expected!")
except:
    raise

# %%
# We can temporarily avoid this error by:
pml.hla.allow_machine_default_placeholder()

standalone = pml.hla.orbit.slow_acq.get_flow("standalone", SR)

# %%
# Print all the stage names for the flow
standalone.get_stage_names()

# %%
# Get the parameters for the "acquire" stage
params = standalone.get_params("acquire")
params

# %%
# Note that "bpm_mlo" is a `MachineDefault` object (i.e., a placeholder).
# This HLA will NOT work if this parameter is not specified, which is the reason
# for the earlier error message "TypeError: Machine default is requested..."
list(params)

# %%
# Set this parameter to the "BPM" MLVT
params.bpm_mlo = SR.get_mlvt("BPM")
params.bpm_mlo

# %%
# You can also change the default values for other params, if you want.
#
# Note bluesky/tiled for HLAs have not been implemented yet.
params.n_meas = 6

# %%
# Run the "standalone" flow (i.e., run the "acquire" stage, followed
# by the "plot" stage)
standalone.run()

# %%
# Print the current default parameters for all HLAs, which should be empty,
# except for the machine name "SR".
pml.hla.get_hla_defaults()

# %%
# Update the default params, if you want to set the current params as the
# default. This has been only saved in memory. If you stop the currently
# running process, this change will be lost.
stage = standalone.get_stage("acquire")
stage.update_machine_default_params(params)

# %%
# Now the HLA default dict contains the changes you applied
pml.hla.get_hla_defaults()

# %%
# If you want the default param changes above to be persistent, save the changes
# in the params object into the YAML file that specifies the default HLA parameters.
hla_defaults_filepath = FACILITY_CONFIG_FOLDER / "hla_defaults.yaml"

pml.hla.save_hla_defaults_to_file(hla_defaults_filepath)

# %%
# Now reload the machine data to wipe out the HLA default params in memory
SR = pml.load_machine(machine_name, dirpath=FACILITY_CONFIG_FOLDER)

pml.hla.get_hla_defaults()

# %%
# You can now recover the default params from the saved YAML file.
pml.load_hla_defaults(hla_defaults_filepath)

pml.hla.get_hla_defaults()

# %%
# Since the default params have been set, you no longer need to disable the
# validation process with `pml.hla.allow_machine_default_placeholder()`
# when you try to get the flow.
standalone = pml.hla.orbit.slow_acq.get_flow("standalone", SR)

params = standalone.get_params("acquire")
list(params)

# %%
# However, trying to run this flow SHOULD FAIL.
try:
    standalone.run()
except Exception as e:
    assert isinstance(
        e, AttributeError
    ), f"Expected AttributeError, but got {type(e).__name__}"
    assert str(e) == "'MlvtName' object has no attribute 'wait_for_connection'"
    print("Failed as expected!")
except:
    raise

# %%
# This error occurred because we disabled the validation process earlier with
# `pml.hla.allow_machine_default_placeholder()`.
# When getting the flow object, the default params are loaded. If the validation
# process is not disabled, the loading converts the MLVT name saved in
# the YAML file into an actual MLVT object, which is necessary to run. Thus,
# to avoid the error, we need to re-enable the validation process:
pml.hla.disallow_machine_default_placeholder()

# Note that, if you didn't disable earlier, this enabling is not necessary.
# This complication is a one-time process, as there is no HLA default params
# are specified initially.

# %%
# Repeat the steps above, and now you should get no error.
standalone = pml.hla.orbit.slow_acq.get_flow("standalone", SR)

params = standalone.get_params("acquire")

standalone.run()
# Note that the orbit is now all zero, because reloading the machine reset
# the simulator back to the initial "no kick" state.

# %% [markdown]
# Summary: After the default HLA params are saved into the default YAML file,
# the following are the minimal lines required to run the standalone HLA:
#
# ```
# SR = pml.load_machine(machine_name, dirpath=FACILITY_CONFIG_FOLDER)
# pml.load_hla_defaults(hla_defaults_filepath)
# standalone = pml.hla.orbit.slow_acq.get_flow("standalone", SR)
# standalone.run()
# ```
#
# If you want to adjust the params for each stage, retrieve them via
# "get_params()", and modify them before calling "run()".

# %%
# Now let us try a different flow "library"

# Change the corrector strength to introduce orbit distortion (to avoid BPM
# readings being all zero)
mlvs = SR.get_all_mlvs()
mlv = mlvs["C30_C1_x_I_SP"]
mlv.put(Q_("0.1 A"))

# %%
orbit_hla_lib = pml.hla.orbit.slow_acq.get_flow("library", SR)

orbit_hla_lib.get_stage_names()

# %%
# Running the "library" flow will NOT generate a plot. Instead, it returns
# orbit data that can be passed onto another stage of the orbit HLA or other
# HLA's stage.
orb_data = orbit_hla_lib.run()

orb_data

# %%
# As an example, we can pass the orbit data onto the plot stage of this orbit
# HLA to plot the measured orbit.
plot_stage = pml.hla.orbit.slow_acq.plot.Stage(SR)
plot_stage.take_output_from_prev_stage(orb_data)
plot_stage.run()
