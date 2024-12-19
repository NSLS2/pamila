from pint import DimensionalityError, UnitRegistry, set_application_registry
import platformdirs

_pint_cache_folder = platformdirs.user_cache_path() / "pamila" / "pint"

try:
    ureg = UnitRegistry(cache_folder=_pint_cache_folder)
except FileNotFoundError:
    # As of 12/20/2024, `pint` cache loading fails if `cache_folder=":auto:"`
    # is used, which records the hard-coded path to the files within the `pint`
    # installation folder, and the installation folder disappears when you
    # delete the associated conda environment. You could delete ~/.cache/pint
    # manually to resolve this issue, but here we programmatically resolve it:
    _pint_cache_folder.unlink()
    ureg = UnitRegistry(cache_folder=_pint_cache_folder)

set_application_registry(ureg)  # if pickling/unpickling is needed

ureg.setup_matplotlib()

Quantity = ureg.Quantity
Q_ = ureg.Quantity
Unit = ureg.Unit
