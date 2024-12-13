import importlib
from pathlib import Path
import sys
from typing import Callable, Dict

from .builtin import PchipInterpolator, identity_conversion, poly1d

FUNC_MAP: Dict[str, Callable] = {
    "identity": identity_conversion,
    "poly1d": poly1d,
    "pchip_interp": PchipInterpolator,
}

IS_FACTORY_FUNC: Dict[str, bool] = {
    "identity": False,
    "poly1d": True,
    "pchip_interp": True,
}


def _register_func(func_name: str, func_obj: Callable, is_factory_function: bool):
    """
    Registers a function with a given name and factory function flag.

    Args:
        func_name (str): The unique identifier for the function.
        func_obj (Callable): The function to register.
        is_factory_function (bool): Indicates if the function is a factory function.
    """
    assert func_name not in FUNC_MAP, f"Function '{func_name}' is already registered."
    FUNC_MAP[func_name] = func_obj
    IS_FACTORY_FUNC[func_name] = is_factory_function


def register(name: str, is_factory_function: bool = False):
    """
    Decorator to register a function with a given name and factory function flag.

    Args:
        name (str): The unique identifier for the function.
        is_factory_function (bool): Indicates if the function is a factory function.
    """

    def decorator(func: Callable):
        _register_func(name, func, is_factory_function)
        return func

    return decorator


def load_plugins(plugin_dir: Path):
    """
    Loads all plugin modules from the specified directory.
    """

    if not plugin_dir.exists():
        raise FileNotFoundError(
            f"Specified directory '{plugin_dir.resolve()}' does not exist"
        )
    if not plugin_dir.is_dir():
        raise NotADirectoryError(
            f"Specified path '{plugin_dir.resolve()}' is not a directory"
        )

    # Iterate over all Python files in the directory
    for file in plugin_dir.glob("*.py"):
        module_name = file.stem

        # Define a unique module name to avoid conflicts
        full_module_name = f"pamila_plugins.{module_name}"
        try:
            spec = importlib.util.spec_from_file_location(full_module_name, file)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                sys.modules[full_module_name] = module
                print(f"Successfully loaded plugin: {module_name}")

            else:
                print(f"Could not load spec for module: {module_name}")
        except Exception as e:
            print(f"Failed to load plugin '{module_name}': {e}")


def get_registered_functions() -> Dict[str, Callable]:
    """
    Returns the dictionaries of registered functions and their factory function flags.
    """
    return FUNC_MAP, IS_FACTORY_FUNC
