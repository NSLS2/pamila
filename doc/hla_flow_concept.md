# Function-based High-Level Applications (HLA)

High-level applications such as orbit response matrix measurements and dispersion / chromaticity measurements are implemented as functions in MML. Problems arise when we try to reuse these HLAs in other HLAs (i.e., functions).

Let us use the dispersion / chromaticity measurement HLA as an example to illustrate the problems. We need to measure orbits for dispersion, while we need to measure tunes for chromaticity. For both, we may want to take multiple measurements and use averaged or median values. Though we usually do not consider simple repeated measurements as an HLA, we can implement orbit and tune measurements as HLAs, for the purpose of testing HLA reusability. Let us suppose these HLAs can be used as follows:

```
orb_result = orb_meas(
    sel_bpm_mlvs,
    n_meas=5,
    wait_btw_meas=Q_("0.2 s"),
    stats_type="mean")

tune_result = tune_meas_via_pvs(
    sel_tune_mlvs,
    n_meas=3,
    wait_btw_meas=Q_("2 s"),
    stats_type="median")
```

Assume that `sel_bpm_mlvs` and `sel_tune_mlvs` are some objects from which we can get relevant data via a control system. `Q_` denotes quantity objects from the unit-handling package `pint`.

We could implement the dispersion / chromaticity measurement HLA function with all potential options exposed like this:

```
result = disp_chrom_meas(
    # Options related to RF frequency changes
    rf_freq_mlv,
    n_freq_pts=5,
    max_delta_freq=Q_("200 Hz"),
    min_delta_freq=Q("-200 Hz"),
    extra_settle_time=Q_("1 s),
    #
    # Options related to orbit measurements
    orb_bpm_mlvs=sel_bpm_mlvs,
    orb_n_meas=5,
    orb_wait_btw_meas=Q_("0.2 s"),
    orb_stats_type="mean",
    #
    # Options related to tune measurements
    tune_via_pv_mlvs=sel_tune_mlvs,
    tune_via_pv_n_meas=3,
    tune_via_pv_wait_btw_meas=Q("2 s"),
    tune_via_pv_stats_type="median",
    #
    # Options related to postprocessing
    momentum_compaction="default",
    disp_max_order=1, # Max order for dispersion fitting
    chrom_max_order=2, # Max order for chromaticity fitting
    #
    # Options related to plotting
    show_plot=True,
    title='Some title',
    export_to_file='result.pdf',
    )
```

## Problem: Option name collision

Both the `orb_meas` and `tune_meas_via_pvs` HLAs reused in this HLA have the same option names: `n_meas`, `wait_btw_meas`, and `stats_type`. When a name collision occurs, the upper-level HLA option names must be changed to distinguish them. In this example, the prefixes `orb_` and `tune_via_pv_` were added, respectively. With more nested HLA reuse, the option names for upper-level HLAs can become significantly long.

## Problem: Cluttering and maintainability of docstrings

There are so many options even for such a simple HLA. This clutters the functions's docstring, and makes it hard to find the option of interest and read its explanation. We could simply provide links to the docstrings of the reused HLAs `orb_meas` and `tune_meas_via_pvs` to reduce the clutter. However, the option names may differ slightly (e.g., `orb_n_meas` here vs. `n_meas` in the `orb_meas` HLA, due to the name collision discussed above), which may lead to confusion. If we decide not to use links, then whenever we change those underlying docstrings, we must remember to update the upper-level HLA docstring as well.

## Problem: Making available multiple HLAs for the same purpose

The list of options becomes longer, if we want to make another method of tune measurements available. In the example above, it was assumed that we can measure tunes by simply reading the PVs that are periodically updated by a bunch-by-bunch feedback system. However, we can also measure tunes from turn-by-turn (TbT) data, using another HLA:

```
tune_result = tune_meas_via_tbt(
    sel_bpm_tbt_mlvs,
    n_turn=512,
    tune_extraction_method='naff',
    n_meas=3,
    stats_type="median")
```

Here, `sel_bpm_tbt_mlvs` is an object from which BPM TbT data can be acquired. In reality, the list of options could be likely longer, for example, if we also allow specifications of the kicker strength, timing, etc.

To support this HLA in `disp_chrom_meas`, we need to add the following five options to the existing 19:

```
...
    # Options related to TbT tune measurements
    tune_via_tbt_mlvs=sel_bpm_tbt_mlvs,
    tune_via_tbt_n_turn=512,
    tune_via_tbt_tune_extraction_method='naff',
    tune_via_tbt_n_meas=3,
    tune_via_tbt_stats_type="median"
...
```

This way of adding new methods is clearly not sustainable, as the number of options becomes too large. Furthermore, if a facility cannot use a particular HLA method, these extra options are irrelevant to those users, and simply distract from the documentation.

## Problem: Impossible to redo post-processing and plotting on already acquired data

This function-based implementation does not allow re-processing or re-plotting with different options. For example, we may later want to fit the dispersion up to second order, instead of first. To do this, we must re-acquire the data. The same applies to plotting.

# Object-oriented HLAs

The Python package `pyacal-test`, developed by SIRIUS, implements HLAs as classes. For the example of the dispersion / chromaticity measurement, this HLA corresponds to the `DispChrom` class in `pyacal-test/pyacal/experiments/disp_chrom.py`, with most of its options defined in a separate class `DispChromParams` in the same file.

(While this section raises several critical points, they are not intended to diminish the value of the package. On the contrary, it served as a valuable and concrete learning example that helped guide the development of solutions to the issues discussed.)

This implementation can address the issue of not being able to redo post-processing and plotting in function-based HLAs. We can re-process raw data by calling its `process_data` method, and re-plot the processed data by using its `make_figure_chrom` and `make_figure_disp` methods. However, this approach still suffers from all the problems caused by the flat structure of the HLA options.

The plotting methods can be called at any time, as long as the acquired and processed data have been saved and can be retrieved later. However, to do this, we must first instantiate a `DispChrom` object, during which a default `DispChromParams` object is created and assigned to `self.params`. These default parameters may differ from the actual parameter values used for the saved data. It does not logically make sense that we need to assign these acquisition-related options to the main object even when we are only interested in plotting the result. This issue may appear harmless, but this is true only if the plotting method does not depend on these parameters. If it does, however, it may accidentally use values different from those actually used, leading to bugs. In such cases, these acquisition-related parameters should have been saved as part of the acquired data, and those saved parameters must be used during plotting.

Integrating the different stages involved in an HLA into a single class is the root cause of these complications. Therefore, a new concept, stages and flows for HLAs, is proposed, although other approaches might also address these problems.

# Stages and Flows for HLAs

We can always decompose an HLA into multiple "stages". Typical stages for an HLA consist of "acquire", "postprocess", and "plot". The "acquire" stage can even be subdivided into "setup", "acquire", and "cleanup", if necessary. Other stages can be created as needed.

Parameters (or options) are defined for each stage as a separate class, not for the HLA as a whole. This allows each stage to be invoked independently, without requiring assignments of irrelevant or potentially conflicting parameters.

A "flow" specifies a sequence of stages to run. Calling the `run` method of a flow object starts execution from the first stage, passes the output to the next stage as its input, runs the next stage, and continues until the final stage is executed. A flow can enter or exit at any stage, as long as the sequence logically makes sense and satisfies the required input data formats.

When we want to reuse an existing HLA in another HLA stage, we pass a flow from the existing HLA as one of the parameters for the new HLA stage.

As a concrete example, the `disp_chrom` HLA can be implemented with the following structure:

![HLA Folder Structure](images/hla_folder_structure.png)

In this case, there are three stages (`acquire`, `postprocess`, and `plot`). Another stage `library_output` can be ignored for now, and will be discussed later. Each stage is implemented as a module. Within each stage module, `Params` and `Stage` classes must be defined. The `Params` class defines all available options, while the `Stage` class defines the `run` method of that stage.

All flows are defined in `disp_chrom/__init__.py` as follows, along with other boilerplate code:

```
FLOW_DEFS = {
    "library": [acquire.Stage, postprocess.Stage, library_output.Stage],
    "standalone": [acquire.Stage, postprocess.Stage, plot.Stage],
    "acquire": [acquire.Stage],
    "postprocess": [postprocess.Stage],
    "plot": [plot.Stage],
}
```

Let us first look at the `standalone` flow. As the name suggests, this flow is used when the HLA is intended to run as a standalone program. In the simplest case, where we accept all default options, we can run this standalone HLA as follows:

```
import pyaml as pal

machine_name = "SR"
SR_CT = pal.set_control_target(pal.load_machine(machine_name), pal.CT.LIVE)

standalone_flow = pal.hla.disp_chrom.get_flow("standalone", SR_CT)

standalone_flow.run()
```

When the final line is executed, it begins by running the `acquire` stage. The output from this stage is automatically passed to the next stage, `postprocess`. Then the output is passed to the final `plot` stage, which generates dispersion and chromaticity figures.

The `Params` classes for these stages are:

```
# Stage "acquire"
class Params(HlaStageParams):
    rf_freq_mlv: MiddleLayerVariable
    n_freq_pts: int
    max_delta_freq: Q_
    min_delta_freq: Q_
    extra_settle_time: Q_
    orbit_meas: HlaFlow
    tune_meas: HlaFlow
```
```
# Stage "postprocess"
class Params(HlaStageParams):
    momentum_compaction: float | DesignLatticeProperty
    disp_max_order: int
    chrom_max_order: int
```
```
# Stage "plot"
class Params(HlaStageParams):
    show_plot: bool
    title: str
    export_to_file: str
```

None of these detailed options are visible in the example main script above. They are only accesses when we want to check or modify the default options:

```
stage_name = "acquire"
acq_params = standalone_flow.get_params(stage_name)
```

Printing `acq_params` will show all the property values, as would be expected from a Pydantic BaseModel.

We can change an option like this:

```
acq_params.n_freq_pts = 10
```

Similar modifications can be made to other stages, by first calling the `get_params` method on the flow, and then modifying individual properties. After making all necessary changes, we can call `run()` to execute the flow with the updated options.

## Problem Solved:
- Impossible to redo post-processing and plotting on already acquired data.

Instead of using the `standalone` flow, we can use the `plot` flow, if we are only interested in re-plotting an old result. Assuming we have the postprocessed data or a UID to a database from which the data can be loaded, as a variable (here named `disp_chrom_data`), we can re-plot the data as follows:

```
plot_flow = pal.hla.disp_chrom.get_flow("plot", SR_CT)
plot_flow.take_output_from_prev_stage(disp_chrom_data)
plot_flow.run()
```

Here, we did not have to re-acquire new data.

Also, when retrieving this flow object, it does not define completely irrelevant acquisition-related parameters such as `extra_settle_time`.

On the other hand, some acquisition-related parameters may actually be important for plotting. For example, `n_freq_pts`, `max_delta_freq`, and `min_delta_freq` are needed to create the array for frequency changes in the chromaticity plot. However, because these parameters are not accessible in this flow object, the developer is forced to realize that the relevant acquisition parameters must be saved as part of the output from the `acquire` stage. This also prevents accidental use of default values that differ from those used in the original data, thereby avoiding potential bugs. Thus, encapsulating parameters within each stage is both conceptually sound and practically advantageous.

## Problems Solved:
- Making available multiple HLAs for the same purpose
- Cluttering and maintainability of the docstring
- Option name collision

Note that the `acquire` stage options, `orbit_meas` and `tune_meas`, are specified as type `HlaFlow`. This is how we can reuse existing HLAs within the stage/flow architecture. We simply pass HLA flow objects as parameters to other HLAs.

Even though the passed flow object only occupies a single parameter slot, it encapsulates all the necessary information (which stages to run, their execution order, and most importantly, all the associated options). This eliminates the need to expose numerous individual parameters, keeping the interface clean and minimal.

Furthermore, when we want to use a different method for tune measurements, we can simply pass a different flow. For example, one could use a flow from either `pal.hla.tunes.via_pvs` or `pal.hla.tune.via_tbt`:

```
acq_params.tune_meas = pal.hla.tunes.via_pvs.get_flow("library")
```

or

```
acq_params.tune_meas = pal.hla.tunes.via_tbt.get_flow("library")
```

This is all that is needed to switch the tune measurement method. None of the internal options appear at the top level. However, if needed, we can still dig into those flows and inspect or modify their parameters. This approach essentially follows a "need-to-know" principle: if a certain method is not available at a facility, users never need to concern themselves with the parameters, stages, or flows related to it.

With this architecture, we can add as many methods as needed (within reason) to a given HLA stage, without worrying about cluttering the argument list.

For the top-level docstring, we only need to specify what kind of output data is expected from the passed-in flows. Each user decides which flow to pass on, and can refer to that flow's own docstring.

Option name collisions are also entirely avoided with this approach, since each HLA stage defines its own separate namespace.

## Library flows

The stage/flow concept also facilitates reuse of HLAs in another important way.

Normally, we begin with a `standalone` flow when developing a new HLA. We acquire raw data, postprocess it if needed, and plot the relevant results to verify that the HLA has been implemented correctly. Once that is done, we may want to reuse the HLA in another HLA, which may not need a certain stage within this `standalone` flow.

For example, a dispersion measurement is needed for LOCO. But LOCO does not need the `plot` stage; it only requires the postprocessed dispersion data. In such cases, instead of passing the `standalone` flow (which includes the `plot` stage), we can define and pass a separate flow called `library`.

As defined earlier in `FLOW_DEFS`, this `library` flow includes the following stages:
```
"library": [acquire.Stage, postprocess.Stage, library_output.Stage],
```

This flow is identical to the `standalone` flow, up to the `postprocess` stage, but then diverges to the `library_output` stage, instead of proceeding to the `plot` stage. The `library_output` stage is essentially a pass-through stage for the postprocessed data, but its name signifies that the flow is intended for use as a reusable component within another application.

If we had implemented the `disp_chrom` HLA as an integrated, monolithic class and passed that object to a LOCO HLA, it would inevitably carry along irrelevant parameters related to plotting. While this might seem harmless, it introduces the potential for unintended side effects, as discussed earlier. Following the "need to know" principle, it is better to provide only what is required.

## Miscellaneous comments

- A flow can consist of only a single stage.

- A stage can also be run individually. However, only flows, not stages, should be passed to other HLAs.

- Note that only the `run` method was implemented in PAMILA. To support asynchronous operations, we could consider adding other methods like `start`, `abort`, `status`, and `wait`. However, for all of these methods, no additional options should be passed directly. Instead, any options should be specified in the associated `Params` class. This encapsulation approach should make HLAs more robust and modular, reducing the risk of unintentionally breaking dependent HLAs.

- While the function-based approach can mimic these stages and flows through manual chaining of function calls, managing options for each stage becomes cumbersome and error-prone.
