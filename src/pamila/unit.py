from pint import (
    DimensionalityError,
    UndefinedUnitError,
    UnitRegistry,
    set_application_registry,
)
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

Q_ = Quantity = ureg.Quantity

_CANONICAL_UNIT_STRS = {}
_CANONICAL_UNIT_OBJS = {}


def _get_canonical_name(unit_str: str):
    if unit_str not in _CANONICAL_UNIT_STRS:
        try:
            _CANONICAL_UNIT_STRS[unit_str] = ureg.get_name(unit_str)
        except UndefinedUnitError:
            _CANONICAL_UNIT_STRS[unit_str] = str(ureg.Unit(unit_str))
    return _CANONICAL_UNIT_STRS[unit_str]


def _get_canonical_unit_obj(unit_str: str):
    if unit_str not in _CANONICAL_UNIT_OBJS:
        _CANONICAL_UNIT_OBJS[unit_str] = getattr(ureg, _get_canonical_name(unit_str))
    return _CANONICAL_UNIT_OBJS[unit_str]


def Unit(unit_str: str):
    return _get_canonical_unit_obj(unit_str)


def fast_create_Q(value: int | float, unit_str: str) -> Q_:
    return Q_(value, _get_canonical_name(unit_str))


def fast_convert(value_w_unit: Q_, dst_unit_str: str):
    return value_w_unit.to(_get_canonical_unit_obj(dst_unit_str))
