import os

from tiled.client import from_uri

from ..unit import Q_


class TiledUid:
    def __init__(self, uid: str):
        self.uid = uid


def get_client():
    """
    To initialize a SQLite server file, first cd into a folder where
    you want to create the database file, and then run in a terminal:

    `(env) $ tiled catalog init catalog.db`

    To start the SQLite server, cd into the folder where the database file is,
    and then run:

    `(env) $ tiled catalog serve catalog.db -w data/ --api-key=secret`

    (This will create a "data" folder in cwd, if it does not exist.)

    Look for a line like this:

    `[-] INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)`

    If you encounter an error like the following instead:

    `[-] ERROR:    [Errno 98] error while attempting to bind on address ('127.0.0.1', 8000): address already in use`

    then change the port number manually to, e.g., 8001, by adding "--port 8001",
    to the `tiled` terminal command above.

    Finally, before you can call this function (get_client), you must set the
    following environment variables (either in a terminal or a script / notebook).

    # If you had to use a default port number above, you must use the actual
    # port number for `_tiled_port`.
    _tiled_port = 8000
    os.environ["PAMILA_TILED_URI"] = f"http://localhost:{_tiled_port}"
    os.environ["PAMILA_TILED_API_KEY"] = "secret"
    """

    URI = os.environ.get("PAMILA_TILED_URI", None)
    API_KEY = os.environ.get("PAMILA_TILED_API_KEY", None)

    client = from_uri(URI, api_key=API_KEY)

    return client


import base64
from pathlib import Path
import sys

import orjson
import pandas as pd
import tiled.utils


def _modified_safe_json_dump(content):
    """
    Override tiled.utils.safe_json_dump()

    Baes64-encode raw bytes, and provide a fallback if orjson numpy handling fails.
    """
    import orjson

    def default(content):
        if isinstance(content, bytes):
            content = f"data:application/octet-stream;base64,{base64.b64encode(content).decode('utf-8')}"
            return content
        if isinstance(content, Path):
            return str(content)
        if isinstance(content, Q_):
            return {
                "__pint_quantity__": True,
                "magnitude": content.magnitude,
                "units": str(content.units),
            }
        # No need to import numpy if it hasn't been used already.
        numpy = sys.modules.get("numpy", None)
        if numpy is not None:
            if isinstance(content, numpy.ndarray):
                # If we make it here, OPT_NUMPY_SERIALIZE failed because we have hit some edge case.
                # Give up on the numpy fast-path and convert to Python list.
                # If the items in this list aren't serializable (e.g. bytes) we'll recurse on each item.
                return content.tolist()
            elif isinstance(content, (bytes, numpy.bytes_)):
                return content.decode("utf-8")
        raise TypeError

    # Not all numpy dtypes are supported by orjson.
    # Fall back to converting to a (possibly nested) Python list.
    return orjson.dumps(content, option=orjson.OPT_SERIALIZE_NUMPY, default=default)


tiled.utils.safe_json_dump = _modified_safe_json_dump  # This didn't work
# completely, because "safe_json_dump" is imported in tiled.client.base.py with
# `from ..utils import UNCHANGED, DictView, ListView, patch_mimetypes, safe_json_dump`.
# To deal with this problem, I replaced `orjson.dumps` with `_modified_orjson_dumps`
# as below.

_original_orjson_dumps = orjson.dumps


def _modified_orjson_dumps(*args, default=None, **kwargs):

    # Force-replace "default" here
    def pint_compatible_default(content):
        if isinstance(content, bytes):
            content = f"data:application/octet-stream;base64,{base64.b64encode(content).decode('utf-8')}"
            return content
        if isinstance(content, Path):
            return str(content)
        if isinstance(content, Q_):
            return {
                "__pint_quantity__": True,
                "magnitude": content.magnitude,
                "units": str(content.units),
            }
        # No need to import numpy if it hasn't been used already.
        numpy = sys.modules.get("numpy", None)
        if numpy is not None:
            if isinstance(content, numpy.ndarray):
                # If we make it here, OPT_NUMPY_SERIALIZE failed because we have hit some edge case.
                # Give up on the numpy fast-path and convert to Python list.
                # If the items in this list aren't serializable (e.g. bytes) we'll recurse on each item.
                return content.tolist()
            elif isinstance(content, (bytes, numpy.bytes_)):
                return content.decode("utf-8")
        raise TypeError

    return _original_orjson_dumps(*args, default=pint_compatible_default, **kwargs)


orjson.dumps = _modified_orjson_dumps


def pint_serializable_df(df_w_unit):

    # Identify columns with Pint Quantity objects
    quantity_columns = [
        col for col in df_w_unit.columns if isinstance(df_w_unit[col].iloc[0], Q_)
    ]

    df_wo_unit = df_w_unit.copy()

    # Store units for each Quantity column
    units = {}
    for col in quantity_columns:
        # Ensure all units in the column are consistent
        column_units = df_w_unit[col].apply(lambda x: str(x.units)).unique()
        if len(column_units) > 1:
            raise ValueError(f"Column '{col}' has inconsistent units: {column_units}")
        units[col] = column_units[0]

        # Convert Quantity objects to magnitudes (numerical values)
        df_wo_unit[col] = df_w_unit[col].apply(lambda x: x.magnitude)
        df_wo_unit[col].attrs["unit"] = units[col]

    return dict(df_wo_unit=df_wo_unit, units=units)


from bluesky.callbacks.tiled_writer import TiledWriter as OrigTiledWriter
from bluesky.callbacks.tiled_writer import _RunWriter
from bluesky.consolidators import DataSource, StructureFamily
from event_model.documents import Event, EventDescriptor
from pydantic.v1.utils import deep_update
from tiled.structures.table import TableStructure


class _ModifiedRunWriter(_RunWriter):
    def descriptor(self, doc: EventDescriptor):
        if self.root_node is None:
            raise RuntimeError(
                "RunWriter is properly initialized: no Start document has been recorded."
            )

        desc_name = doc["name"]
        metadata = dict(doc)

        # Remove variable fields of the metadata and encapsulate them into sub-dictionaries with uids as the keys
        uid = metadata.pop("uid")
        conf_dict = {uid: metadata.pop("configuration", {})}
        time_dict = {uid: metadata.pop("time")}
        var_fields = {"configuration": conf_dict, "time": time_dict}

        if desc_name not in self.root_node.keys():
            # Create a new descriptor node; write only the fixed part of the metadata
            desc_node = self.root_node.create_container(
                key=desc_name, metadata=metadata
            )
            desc_node.create_container(key="external")
            desc_node.create_container(key="internal")
            desc_node.create_container(key="config")
        else:
            # Get existing descriptor node (with fixed and variable metadata saved before)
            desc_node = self.root_node[desc_name]

        # Update (add new values to) variable fields of the metadata
        metadata = deep_update(dict(desc_node.metadata), var_fields)
        desc_node.update_metadata(metadata)

        # Keep specifications for external and internal data_keys for faster access
        self.data_keys_int.update(
            {
                k: v
                for k, v in metadata["data_keys"].items()
                if "external" not in v.keys()
            }
        )
        self.data_keys_ext.update(
            {k: v for k, v in metadata["data_keys"].items() if "external" in v.keys()}
        )

        # Write the configuration data: loop over all detectors
        conf_node = desc_node["config"]
        for det_name, det_dict in conf_dict[uid].items():
            df_dict = {"descriptor_uid": uid}
            df_dict.update(det_dict.get("data", {}))
            df_dict.update(
                {f"ts_{c}": v for c, v in det_dict.get("timestamps", {}).items()}
            )
            df = pd.DataFrame(df_dict, index=[0], columns=df_dict.keys())
            # --- Added by Y.H. ---
            _df_d = pint_serializable_df(df)
            df = _df_d["df_wo_unit"]
            converted_units = _df_d["units"]
            for k, v in converted_units.items():
                det_dict["data_keys"][k]["converted_units"] = v
            # ---------------------
            if det_name in conf_node.keys():
                conf_node[det_name].append_partition(df, 0)
            else:
                conf_node.new(
                    structure_family=StructureFamily.table,
                    data_sources=[
                        DataSource(
                            structure_family=StructureFamily.table,
                            structure=TableStructure.from_pandas(df),
                            mimetype="text/csv",
                        ),
                    ],
                    key=det_name,
                    metadata=det_dict["data_keys"],
                )
                conf_node[det_name].write_partition(df, 0)

        self._desc_nodes[uid] = desc_node

    def event(self, doc: Event):
        desc_node = self._desc_nodes[doc["descriptor"]]

        # Process _internal_ data -- those keys without 'external' flag or those that have been filled
        data_keys_spec = {
            k: v for k, v in self.data_keys_int.items() if doc["filled"].get(k, True)
        }
        data_keys_spec.update(
            {k: v for k, v in self.data_keys_ext.items() if doc["filled"].get(k, False)}
        )
        parent_node = desc_node["internal"]
        df_dict = {"seq_num": doc["seq_num"]}
        df_dict.update(
            {k: v for k, v in doc["data"].items() if k in data_keys_spec.keys()}
        )
        df_dict.update(
            {f"ts_{k}": v for k, v in doc["timestamps"].items()}
        )  # Keep all timestamps
        df = pd.DataFrame(df_dict, index=[0], columns=df_dict.keys())
        # --- Added by Y.H. ---
        _df_d = pint_serializable_df(df)
        df = _df_d["df_wo_unit"]
        converted_units = _df_d["units"]
        for k, v in converted_units.items():
            data_keys_spec[k]["converted_units"] = v
        # ---------------------
        if "events" in parent_node.keys():
            parent_node["events"].append_partition(df, 0)
        else:
            parent_node.new(
                structure_family=StructureFamily.table,
                data_sources=[
                    DataSource(
                        structure_family=StructureFamily.table,
                        structure=TableStructure.from_pandas(df),
                        mimetype="text/csv",
                    ),
                ],
                key="events",
                metadata=data_keys_spec,
            )
            parent_node["events"].write_partition(df, 0)

        # Process _external_ data: Loop over all referenced Datums
        for data_key in self.data_keys_ext.keys():
            if doc["filled"].get(data_key, False):
                continue

            if datum_id := doc["data"].get(data_key):
                if datum_id in self._docs_cache.keys():
                    # Convert the Datum document to the StreamDatum format
                    datum_doc = self._docs_cache.pop(datum_id)
                    datum_doc["uid"] = datum_doc.pop("datum_id")
                    datum_doc["stream_resource"] = datum_doc.pop("resource")
                    datum_doc["descriptor"] = doc["descriptor"]  # From Event document
                    datum_doc["indices"] = {
                        "start": doc["seq_num"] - 1,
                        "stop": doc["seq_num"],
                    }
                    datum_doc["seq_nums"] = {
                        "start": doc["seq_num"],
                        "stop": doc["seq_num"] + 1,
                    }

                    # Update the Resource document (add data_key as in StreamResource)
                    if datum_doc["stream_resource"] in self._docs_cache.keys():
                        self._docs_cache[datum_doc["stream_resource"]][
                            "data_key"
                        ] = data_key

                    self.stream_datum(datum_doc)
                else:
                    raise RuntimeError(
                        f"Datum {datum_id} is referenced before being declared."
                    )


class _ModifiedTiledWriter(OrigTiledWriter):
    def _factory(self, name, doc):
        return [_ModifiedRunWriter(self.client)], []


TiledWriter = _ModifiedTiledWriter
