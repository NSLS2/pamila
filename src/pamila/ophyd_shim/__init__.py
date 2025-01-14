import ophyd


def custom_ophyd_set_cl():

    # If using pyepics and ophyd.v2 (p4p and aioca), need to use the same
    # libCom and libCa as provided by epicscorelibs
    # https://github.com/BCDA-APS/apstools/issues/836
    try:
        import epicscorelibs.path.pyepics  # noqa
    except ImportError:
        # No epicscorelibs, let pyepics use bundled CA
        pass
    from . import _pyepics_shim as shim

    shim.setup(ophyd.logger)

    exports = (
        "setup",
        "caput",
        "caget",
        "get_pv",
        "thread_class",
        "name",
        "release_pvs",
        "get_dispatcher",
    )
    # this sets the module level value
    ophyd.cl = ophyd.types.SimpleNamespace(**{k: getattr(shim, k) for k in exports})


custom_ophyd_set_cl()
