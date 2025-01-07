from __future__ import annotations

from typing import Dict, List, Literal

import numpy as np
from pydantic import BaseModel, Field

from . import (
    _register_element,
    get_mlvs_via_name,
    get_phys_length,
    get_spos,
    sort_by_spos,
)
from ..utils import KeyValueTagList, SPositionList


class PvIdToReprMap(BaseModel):
    ext: Dict[str, str] = Field(default_factory=dict)
    int: Dict[str, str] = Field(default_factory=dict)


class ElementSpec(BaseModel):
    name: str
    machine_name: str
    pvid_to_repr_map: PvIdToReprMap
    repr_units: Dict[str, str]
    channel_names: List[str]
    description: str = ""
    s_list: SPositionList | None = None
    tags: KeyValueTagList = Field(default_factory=KeyValueTagList)
    exist_ok: bool = False


class Element:
    def __init__(self, spec: ElementSpec):
        assert isinstance(spec, ElementSpec)

        self._spec = spec

        self.name = spec.name
        self.machine_name = spec.machine_name
        self.pvid_to_repr_map = spec.pvid_to_repr_map
        self.repr_units = spec.repr_units
        self.channel_names = spec.channel_names
        self.description = spec.description
        self.s_list = spec.s_list
        self.tags = spec.tags

        _register_element(self, spec.exist_ok)

    def __repr__(self):
        # return f"Element({self._spec!r})"
        ch_names = ", ".join(self.channel_names)
        return f"Element (s_c={self.get_spos(loc='c'):~.3P}): {self.name} (ch.=[{ch_names}])"

    def __str__(self):
        return f"Element: {self.name}"

    def get_spec(self):
        return self._spec

    def get_all_channel_names(self):
        return self.channel_names

    def get_mlv(self, channel_name: str):
        elem_name = self.name
        mlv_name = f"{elem_name}_{channel_name}"

        mlvs = get_mlvs_via_name(self.machine_name, mlv_name, search_type="exact")
        assert len(mlvs) == 1
        return mlvs[mlv_name]

    def get_spos(self, loc: Literal["b", "e", "c"] = "c"):
        s_list = self._spec.s_list
        return get_spos(s_list, loc=loc)

    def get_phys_length(self):
        s_list = self._spec.s_list
        return get_phys_length(s_list)

    def get_neighbors(
        self,
        elements_to_select_from: List[Element] | Dict[str, Element],
        n_ds: int | None = 1,
        n_us: int | None = 1,
    ):

        assert (n_ds is None) or (n_ds >= 1)
        assert (n_us is None) or (n_us >= 1)

        s_self = self.get_spos(loc="c").to("m").m

        sorted_elements = sort_by_spos(
            elements_to_select_from, loc="c", exclude_nan=True
        )
        s_sorted = [elem.get_spos(loc="c").to("m").m for elem in sorted_elements]

        if self in sorted_elements:
            sep_ind = sorted_elements.index(self)
            us_elements = sorted_elements[:sep_ind]
            ds_elements = sorted_elements[sep_ind + 1 :]
        else:
            s_diff = np.array(s_sorted) - s_self
            sep_ind = np.argmin(np.abs(s_diff))
            if s_diff[sep_ind] >= 0:
                us_elements = sorted_elements[:sep_ind]
                ds_elements = sorted_elements[sep_ind:]
            else:
                us_elements = sorted_elements[: sep_ind + 1]
                ds_elements = sorted_elements[sep_ind + 1 :]

        neighbors = dict(ds=None, us=None)

        if n_ds:
            comb_elems = ds_elements + us_elements
            neighbors["ds"] = comb_elems[:n_ds]

        if n_us:
            comb_elems = us_elements[::-1] + ds_elements[::-1]
            neighbors["us"] = comb_elems[:n_us]

        return neighbors
