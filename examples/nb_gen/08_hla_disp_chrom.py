# %% [markdown]
# - It is assumed that you have already run the previous notebook
# `07_setup_hla_disp_chrom.ipynb`. If not, please run the notebook to have the
# default params for this HLA properly set up before you can run the HLA.

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
# Print all available flow names for this HLA
pml.hla.disp_chrom.get_flow_names()

# %%
# First get the "standalone" HLA flow
standalone = pml.hla.disp_chrom.get_flow("standalone", SR)

# %%
# Get the parameters for the "acquire" stage
params = standalone.get_params("acquire")
params

# %%
list(params)

# %%
# Before running the standalone flow, you can change parameters
params.n_freq_pts = 6

# %%
# "orbit_meas" is a flow for the `orbit.slow_acq` HLA. Print its stages.
params.orbit_meas.get_stage_names()

# %%
# You can see the nested params for the "acquire" stage of "orbit_meas" flow
orb_params = params.orbit_meas.get_params("acquire")
list(orb_params)

# %%
# Before running the standalone flow, you can also change the nested params
orb_params.n_meas = 5

# %%
# You can see the nested params for the "acquire" stage of "tune_meas" flow
tune_params = params.tune_meas.get_params("acquire")
list(tune_params)

# %%
# Before running the standalone flow, you can also change the nested params
tune_params.n_meas = 4

# %%
# Finally, you can run the standalone flow with the modified params
standalone.run()

# Note the plot shows only chromaticity, not dispersion, which is to be
# implemented in the future. Also the fitted coefficient values will be also
# added in the plot.

# %%
# Now instead of the "standalone" flow, we will test the "library" flow.
library_flow = pml.hla.disp_chrom.get_flow("library", SR)

library_flow.get_stage_names()

# %%
# "library" and "standalone" shares the same default params for the `acquire`
# stage that is common to both flows.
params = library_flow.get_params("acquire")
list(params)

# %%
# Check the default params for the `postprocess` stage
params = library_flow.get_params("postprocess")
list(params)

# %%
# Change the params, if so desired
params.chrom_max_order = 3

# %%
# Running the "library" flow will NOT generate a plot. Instead, it returns
# dispersion/chromaticity data that can be passed onto another stage of the
# `disp_chrom` HLA or as part of other HLA's stage.
disp_chrom_data = library_flow.run()

disp_chrom_data

# %%
# Print out the linear chromaticity values.
ksix = disp_chrom_data["chrom"]["x"][-2]
ksiy = disp_chrom_data["chrom"]["y"][-2]
print(f"Measured linear chromaticity = ({ksix.m:+.2f}, {ksiy.m:+.2f})")

disp_chrom_data["chrom"]

# %%
# As an example, we can pass the disp/chrom data onto the plot stage of this
# HLA to plot the measured dispersion / chromaticity.
plot_stage = pml.hla.disp_chrom.plot.Stage(SR)
plot_stage.take_output_from_prev_stage(disp_chrom_data)

# %%
# Before actually run the `plot` stage, you can change its params.
params = plot_stage.get_params()
params.export_to_file = Path("test.pdf")
params.title = "Test"

# %%
# Run the `plot` stage
plot_stage.run()

# %%
# We can also use the `plot` flow
plot_flow = pml.hla.disp_chrom.get_flow("plot", SR)
plot_flow.take_output_from_prev_stage(disp_chrom_data)

# %%
# This flow only contains the `plot` stage, so it is essentially the same as
# running the `plot` stage as we did above.
plot_flow.get_stage_names()

# %%
# Change the params and run the flow, which should produce exactly the same plot
# as before.
params = plot_flow.get_params("plot")
params.export_to_file = Path("test2.pdf")
params.title = "Test"

plot_flow.run()
