from pint import DimensionalityError, UnitRegistry, set_application_registry

ureg = UnitRegistry(cache_folder=":auto:")
set_application_registry(ureg)  # if pickling/unpickling is needed

ureg.setup_matplotlib()

Quantity = ureg.Quantity
Q_ = ureg.Quantity
Unit = ureg.Unit
