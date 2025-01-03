from copy import deepcopy
import json
import sys
from typing import Dict, List

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
import yaml

# ---------------------- Helper Functions ---------------------- #


def show_error(message):
    msg = QMessageBox()
    msg.setIcon(QMessageBox.Critical)
    msg.setWindowTitle("Error")
    msg.setText(message)
    msg.exec_()


def show_info(message):
    msg = QMessageBox()
    msg.setIcon(QMessageBox.Information)
    msg.setWindowTitle("Information")
    msg.setText(message)
    msg.exec_()


# ---------------------- FuncSpec Dialog ---------------------- #


class FuncSpecDialog(QDialog):
    def __init__(self, parent=None, existing_funcspec=None, conv_spec_names=None):
        super().__init__(parent)
        self.setWindowTitle("Add/Edit Func Spec")
        self.setMinimumWidth(400)
        self.funcspec_data = None

        self.init_ui(existing_funcspec, conv_spec_names)

    def init_ui(self, existing_funcspec, conv_spec_names):
        layout = QVBoxLayout()

        form_layout = QFormLayout()

        self.funcspec_key_edit = QComboBox()
        if conv_spec_names:
            self.funcspec_key_edit.addItems(conv_spec_names)
        self.funcspec_key_edit.addItem("identity")
        self.funcspec_name_edit = QLineEdit()
        self.funcspec_args_edit = QTextEdit()
        self.funcspec_args_edit.setPlaceholderText(
            "Enter list of arguments, e.g., [[-0.1, 0.0]]"
        )
        self.funcspec_kwargs_edit = QTextEdit()
        self.funcspec_kwargs_edit.setPlaceholderText(
            "Enter dictionary of keyword arguments, e.g., {'some_key': 42}"
        )

        form_layout.addRow("Func Spec Key:", self.funcspec_key_edit)
        form_layout.addRow("Name:", self.funcspec_name_edit)
        form_layout.addRow("Args:", self.funcspec_args_edit)
        form_layout.addRow("Kwargs:", self.funcspec_kwargs_edit)

        layout.addLayout(form_layout)

        # Buttons
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()
        submit_btn = QPushButton("Submit")
        cancel_btn = QPushButton("Cancel")
        buttons_layout.addWidget(submit_btn)
        buttons_layout.addWidget(cancel_btn)
        layout.addLayout(buttons_layout)

        self.setLayout(layout)

        # Connect buttons
        submit_btn.clicked.connect(self.submit)
        cancel_btn.clicked.connect(self.reject)

        # If editing, populate data
        if existing_funcspec:
            self.populate_data(existing_funcspec)

    def populate_data(self, existing_funcspec):
        index = self.funcspec_key_edit.findText(
            existing_funcspec.get("key", ""), Qt.MatchFixedString
        )
        if index >= 0:
            self.funcspec_key_edit.setCurrentIndex(index)
        self.funcspec_name_edit.setText(existing_funcspec.get("name", ""))
        self.funcspec_args_edit.setPlainText(str(existing_funcspec.get("args", [])))
        self.funcspec_kwargs_edit.setPlainText(str(existing_funcspec.get("kwargs", {})))

    def submit(self):
        key = self.funcspec_key_edit.currentText().strip()
        name = self.funcspec_name_edit.text().strip()
        args_text = self.funcspec_args_edit.toPlainText().strip()
        kwargs_text = self.funcspec_kwargs_edit.toPlainText().strip()

        if not key:
            show_error("Func Spec Key is required.")
            return
        if not name:
            show_error("Func Spec Name is required.")
            return

        try:
            args = eval(args_text) if args_text else []
            kwargs = eval(kwargs_text) if kwargs_text else {}
        except Exception as e:
            show_error(f"Error parsing Args or Kwargs: {e}")
            return

        self.funcspec_data = {"key": key, "name": name, "args": args, "kwargs": kwargs}

        self.accept()


# ---------------------- PVID to Repr Map Dialog ---------------------- #


class PVIDReprMapDialog(QDialog):
    def __init__(self, parent=None, existing_map=None):
        super().__init__(parent)
        self.setWindowTitle("Add/Edit pvid_to_repr_map Entry")
        self.setMinimumWidth(400)
        self.map_data = None

        self.init_ui(existing_map)

    def init_ui(self, existing_map):
        layout = QVBoxLayout()

        form_layout = QFormLayout()

        self.pvid_key_edit = QLineEdit()
        self.repr_value_edit = QLineEdit()

        form_layout.addRow("PVID:", self.pvid_key_edit)
        form_layout.addRow("Repr Value:", self.repr_value_edit)

        layout.addLayout(form_layout)

        # Buttons
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()
        submit_btn = QPushButton("Submit")
        cancel_btn = QPushButton("Cancel")
        buttons_layout.addWidget(submit_btn)
        buttons_layout.addWidget(cancel_btn)
        layout.addLayout(buttons_layout)

        self.setLayout(layout)

        # Connect buttons
        submit_btn.clicked.connect(self.submit)
        cancel_btn.clicked.connect(self.reject)

        # If editing, populate data
        if existing_map:
            self.populate_data(existing_map)

    def populate_data(self, existing_map):
        self.pvid_key_edit.setText(existing_map.get("pvid", ""))
        self.repr_value_edit.setText(existing_map.get("repr", ""))

    def submit(self):
        pvid = self.pvid_key_edit.text().strip()
        repr_val = self.repr_value_edit.text().strip()

        if not pvid:
            show_error("PVID is required.")
            return
        if not repr_val:
            show_error("Repr Value is required.")
            return

        self.map_data = {"pvid": pvid, "repr": repr_val}

        self.accept()


# ---------------------- Repr Units Dialog ---------------------- #


class ReprUnitsDialog(QDialog):
    def __init__(self, parent=None, existing_units=None, repr_list=None):
        super().__init__(parent)
        self.setWindowTitle("Add/Edit Repr Unit")
        self.setMinimumWidth(400)
        self.units_data = None

        self.init_ui(existing_units, repr_list)

    def init_ui(self, existing_units, repr_list):
        layout = QVBoxLayout()

        form_layout = QFormLayout()

        self.repr_key_edit = QComboBox()
        self.repr_key_edit.setEditable(True)
        if repr_list:
            self.repr_key_edit.addItems(repr_list)
        self.unit_value_edit = QLineEdit()

        form_layout.addRow("Repr:", self.repr_key_edit)
        form_layout.addRow("Unit:", self.unit_value_edit)

        layout.addLayout(form_layout)

        # Buttons
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()
        submit_btn = QPushButton("Submit")
        cancel_btn = QPushButton("Cancel")
        buttons_layout.addWidget(submit_btn)
        buttons_layout.addWidget(cancel_btn)
        layout.addLayout(buttons_layout)

        self.setLayout(layout)

        # Connect buttons
        submit_btn.clicked.connect(self.submit)
        cancel_btn.clicked.connect(self.reject)

        # If editing, populate data
        if existing_units:
            self.populate_data(existing_units)

    def populate_data(self, existing_units):
        index = self.repr_key_edit.findText(
            existing_units.get("repr", ""), Qt.MatchFixedString
        )
        if index >= 0:
            self.repr_key_edit.setCurrentIndex(index)
        self.unit_value_edit.setText(existing_units.get("unit", ""))

    def submit(self):
        repr_key = self.repr_key_edit.currentText().strip()
        unit_val = self.unit_value_edit.text().strip()

        if not repr_key:
            show_error("Repr is required.")
            return
        if not unit_val:
            show_error("Unit is required.")
            return

        self.units_data = {"repr": repr_key, "unit": unit_val}

        self.accept()


# ---------------------- Channel Dialog ---------------------- #


class ChannelDialog(QDialog):
    def __init__(self, parent=None, existing_channel=None, pvids=None, repr_list=None):
        super().__init__(parent)
        self.setWindowTitle("Add/Edit Channel")
        self.setMinimumWidth(800)

        self.channel_data = None
        self.pvids = pvids if pvids else {"ext": [], "int": []}
        self.repr_list = repr_list if repr_list else []
        self.selected_high_level_reprs = []
        self.selected_pvs = {
            "ext": {
                "get": {"input_pvs": []},
                "put": {"output_pvs": [], "aux_input_pvs": []},
            },
            "int": {
                "get": {"input_pvs": []},
                "put": {"output_pvs": [], "aux_input_pvs": []},
            },
        }

        # "get" and "put" conversion displays
        self.ext_get_conv_label = QLabel()
        self.ext_put_conv_label = QLabel()
        self.int_get_conv_label = QLabel()
        self.int_put_conv_label = QLabel()

        self.init_ui(existing_channel)

    def init_ui(self, existing_channel):
        layout = QVBoxLayout()

        # Channel Details Group
        channel_details_group = QGroupBox("Channel Details")
        channel_details_layout = QFormLayout()

        self.channel_name_edit = QLineEdit()
        self.channel_type_combo = QComboBox()
        self.channel_type_combo.addItems(["RB", "SP"])

        # High-Level Reprs
        self.high_level_reprs_combo = QComboBox()
        self.high_level_reprs_combo.addItems(self.repr_list)
        self.add_hilv_repr_btn = QPushButton("Add Repr")
        self.remove_hilv_repr_btn = QPushButton("Remove Selected")
        self.hilv_repr_list = QListWidget()
        self.hilv_repr_list.setSelectionMode(QAbstractItemView.SingleSelection)

        hilv_repr_layout = QVBoxLayout()
        combo_layout = QHBoxLayout()
        combo_layout.addWidget(self.high_level_reprs_combo)
        combo_layout.addWidget(self.add_hilv_repr_btn)
        hilv_repr_layout.addLayout(combo_layout)
        hilv_repr_layout.addWidget(self.hilv_repr_list)
        hilv_repr_layout.addWidget(self.remove_hilv_repr_btn)

        channel_details_layout.addRow("Channel Name:", self.channel_name_edit)
        channel_details_layout.addRow("Channel Type:", self.channel_type_combo)
        channel_details_layout.addRow("High-Level Reprs:", hilv_repr_layout)

        channel_details_group.setLayout(channel_details_layout)
        layout.addWidget(channel_details_group)

        # Connect add/remove for High-Level Reprs
        self.add_hilv_repr_btn.clicked.connect(self.add_hilv_repr)
        self.remove_hilv_repr_btn.clicked.connect(self.remove_hilv_repr)

        # Modes Tabs
        self.tabs = QTabWidget()
        for prefix, name in [
            ("ext", "External (ext) / Online"),
            ("int", "Internal (int) / Offline"),
        ]:
            tab = QWidget()
            self.init_mode_tab(tab, prefix)
            self.update_conv_func_displays(prefix)
            self.tabs.addTab(tab, name)
        layout.addWidget(self.tabs)

        # Buttons
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()
        submit_btn = QPushButton("Submit")
        cancel_btn = QPushButton("Cancel")
        buttons_layout.addWidget(submit_btn)
        buttons_layout.addWidget(cancel_btn)
        layout.addLayout(buttons_layout)

        self.setLayout(layout)
        submit_btn.clicked.connect(self.submit)
        cancel_btn.clicked.connect(self.reject)

        # Populate data if editing
        if existing_channel:
            self.populate_data(existing_channel)

    def get_available_pvid_combo(self, prefix, key):

        list_widget = self.__dict__[f"{prefix}_{key}_list"]

        avail_pvids = deepcopy(self.pvids.get(prefix, []))

        for i in range(list_widget.count()):
            non_avail_pvid = list_widget.item(i).text()
            if non_avail_pvid in avail_pvids:
                avail_pvids.remove(non_avail_pvid)

        return avail_pvids

    def init_mode_tab(self, tab, prefix):
        layout = QVBoxLayout()

        for group_name, key_list, label_list in [
            ("get", ["input_pvs"], ["Input"]),
            ("put", ["output_pvs", "aux_input_pvs"], ["Output", "Aux. Input"]),
        ]:
            group = QGroupBox(group_name)
            group_layout = QFormLayout()

            for key, label in zip(key_list, label_list):
                combo = QComboBox()
                combo.addItems(self.pvids.get(prefix, []))
                add_btn = QPushButton(f"Add")
                remove_btn = QPushButton("Remove Selected")
                selected_list = QListWidget()
                selected_list.setSelectionMode(QAbstractItemView.SingleSelection)

                inner_layout = QVBoxLayout()
                combo_row = QHBoxLayout()
                combo_row.addWidget(combo, stretch=1)
                combo_row.addWidget(add_btn, stretch=0)
                inner_layout.addLayout(combo_row)
                inner_layout.addWidget(selected_list)
                inner_layout.addWidget(remove_btn)

                group_layout.addRow(f"{label} PVs:", inner_layout)

                self.__dict__[f"{prefix}_{key}_combo"] = combo
                self.__dict__[f"{prefix}_{key}_list"] = selected_list

                add_btn.clicked.connect(lambda _, p=prefix, k=key: self.add_pv(p, k))
                remove_btn.clicked.connect(
                    lambda _, p=prefix, k=key: self.remove_pv(p, k)
                )

            conv_spec_edit = QLineEdit()
            _label = QLabel("Conversion Spec Name\n(optional)")
            _label.setWordWrap(True)
            group_layout.addRow(_label, conv_spec_edit)
            self.__dict__[f"{prefix}_{group_name}_conv_spec_edit"] = conv_spec_edit

            # Add "get" and "put" conversion displays
            match prefix:
                case "ext":
                    match group_name:
                        case "get":
                            group_layout.addRow(
                                '"get" conversion:', self.ext_get_conv_label
                            )
                        case "put":
                            group_layout.addRow(
                                '"put" conversion:', self.ext_put_conv_label
                            )
                case "int":
                    match group_name:
                        case "get":
                            group_layout.addRow(
                                '"get" conversion:', self.int_get_conv_label
                            )
                        case "put":
                            group_layout.addRow(
                                '"put" conversion:', self.int_put_conv_label
                            )
                case _:
                    raise ValueError

            group.setLayout(group_layout)
            layout.addWidget(group)

        tab.setLayout(layout)

    def add_pv(self, prefix, key):
        combo = self.__dict__[f"{prefix}_{key}_combo"]
        text = combo.currentText().strip()
        get_or_put = self._get_get_or_put(key)
        if text and text not in self.selected_pvs[prefix][get_or_put][key]:
            self.selected_pvs[prefix][get_or_put][key].append(text)
            self.__dict__[f"{prefix}_{key}_list"].addItem(text)

            # Update the combo selection
            index = combo.findText(text)
            if index != -1:
                combo.removeItem(index)

            self.update_conv_func_displays(prefix)

    def remove_pv(self, prefix, key):
        selected_list = self.__dict__[f"{prefix}_{key}_list"]
        sel = selected_list.selectedItems()
        if sel:
            item = sel[0]
            text = item.text()
            get_or_put = self._get_get_or_put(key)
            self.selected_pvs[prefix][get_or_put][key].remove(text)
            selected_list.takeItem(selected_list.row(item))

            # Update the combo selection
            combo = self.__dict__[f"{prefix}_{key}_combo"]
            combo.clear()
            combo.addItems(self.get_available_pvid_combo(prefix, key))

            self.update_conv_func_displays(prefix)

    def _get_get_or_put(self, key):
        match key:
            case "input_pvs":
                return "get"
            case "output_pvs" | "aux_input_pvs":
                return "put"
            case _:
                raise ValueError

    def add_hilv_repr(self):
        text = self.high_level_reprs_combo.currentText().strip()
        if text and text not in self.selected_high_level_reprs:
            self.selected_high_level_reprs.append(text)
            self.hilv_repr_list.addItem(text)
            index = self.high_level_reprs_combo.findText(text)
            self.high_level_reprs_combo.removeItem(index)
            self.update_conv_func_displays("ext")
            self.update_conv_func_displays("int")

    def remove_hilv_repr(self):
        sel = self.hilv_repr_list.selectedItems()
        if sel:
            item = sel[0]
            text = item.text()
            self.selected_high_level_reprs.remove(text)
            self.hilv_repr_list.takeItem(self.hilv_repr_list.row(item))
            self.high_level_reprs_combo.addItem(text)
            self.update_conv_func_displays("ext")
            self.update_conv_func_displays("int")

    def update_conv_func_displays(self, prefix):

        match prefix:
            case "ext":
                get_label = self.ext_get_conv_label
                put_label = self.ext_put_conv_label
            case "int":
                get_label = self.int_get_conv_label
                put_label = self.int_put_conv_label
            case _:
                raise ValueError

        # Update "get" conversion
        try:
            pv_list = self.selected_pvs[prefix]["get"]["input_pvs"]
        except KeyError:
            pv_list = []
        input_str = ", ".join(pv_list)
        output_str = ", ".join(
            [f"{repr_} <cur.>" for repr_ in self.selected_high_level_reprs]
        )
        get_label.setText(f"({input_str}) => ({output_str})")

        # Update "put" conversion
        try:
            aux_pv_list = self.selected_pvs[prefix]["put"]["aux_input_pvs"]
        except KeyError:
            aux_pv_list = []
        input_str = ", ".join(
            [f"{repr_} <new>" for repr_ in self.selected_high_level_reprs] + aux_pv_list
        )
        try:
            pv_list = self.selected_pvs[prefix]["put"]["output_pvs"]
        except KeyError:
            pv_list = []
        output_str = ", ".join(pv_list)
        put_label.setText(f"({input_str}) => ({output_str})")

    def submit(self):
        # Validate required fields
        channel_name = self.channel_name_edit.text().strip()
        if not channel_name:
            show_error("Channel Name is required.")
            return

        high_level_reprs_list = [
            self.hilv_repr_list.item(i).text()
            for i in range(self.hilv_repr_list.count())
        ]
        if not high_level_reprs_list:
            show_error("High-Level Reprs are required.")
            return

        def process_mode(prefix):
            mode_data = {}
            for get_or_put, key_list in [
                ("get", ["input_pvs"]),
                ("put", ["output_pvs", "aux_input_pvs"]),
            ]:

                for key in key_list:
                    selected_list = [
                        self.__dict__[f"{prefix}_{key}_list"].item(i).text()
                        for i in range(self.__dict__[f"{prefix}_{key}_list"].count())
                    ]

                    if selected_list:
                        if get_or_put not in mode_data:
                            mode_data[get_or_put] = {}
                        mode_data[get_or_put][key] = selected_list

            if "get" in mode_data:
                get_conv_spec = self.__dict__.get(f"{prefix}_get_conv_spec_edit")
                if get_conv_spec:
                    text = get_conv_spec.text().strip()
                    if text:
                        mode_data["get"]["conv_spec_name"] = text

            if "put" in mode_data:
                put_conv_spec = self.__dict__.get(f"{prefix}_put_conv_spec_edit")
                if put_conv_spec:
                    text = put_conv_spec.text().strip()
                    if text:
                        mode_data["put"]["conv_spec_name"] = text

            return mode_data if mode_data else None

        external_data = process_mode("ext")
        internal_data = process_mode("int")

        self.channel_data = {
            "channel_name": channel_name,
            "channel_type": self.channel_type_combo.currentText(),
            "high_level_reprs": high_level_reprs_list,
            "external": external_data,
            "internal": internal_data,
        }
        self.accept()  # Close the dialog with success

    def populate_data(self, existing_channel):
        # Populate Channel Details
        self.channel_name_edit.setText(existing_channel.get("channel_name", ""))
        self.channel_type_combo.setCurrentText(
            existing_channel.get("channel_type", "RB")
        )

        # Clear and populate High-Level Reprs
        self.hilv_repr_list.clear()
        self.high_level_reprs_combo.clear()
        self.high_level_reprs_combo.addItems(self.repr_list)
        self.selected_high_level_reprs = existing_channel.get("high_level_reprs", [])

        for repr_ in self.selected_high_level_reprs:
            self.hilv_repr_list.addItem(repr_)
            index = self.high_level_reprs_combo.findText(repr_)
            if index != -1:
                self.high_level_reprs_combo.removeItem(index)

        # Helper to populate mode-specific data
        def populate_mode_data(prefix, mode_data):
            if not mode_data:
                return

            get_data = mode_data.get("get", {})
            put_data = mode_data.get("put", {})

            for key, selected_pvs in [
                ("input_pvs", get_data.get("input_pvs", [])),
                ("output_pvs", put_data.get("output_pvs", [])),
                ("aux_input_pvs", put_data.get("aux_input_pvs", [])),
            ]:
                get_or_put = self._get_get_or_put(key)
                self.selected_pvs[prefix][get_or_put][key] = selected_pvs
                list_widget = self.__dict__[f"{prefix}_{key}_list"]
                list_widget.clear()
                for pv in selected_pvs:
                    list_widget.addItem(pv)

                # Update the combo selection
                combo = self.__dict__[f"{prefix}_{key}_combo"]
                combo.clear()
                combo.addItems(self.get_available_pvid_combo(prefix, key))

            # Populate conversion spec names
            get_conv_spec = get_data.get("conv_spec_name", "")
            put_conv_spec = put_data.get("conv_spec_name", "")
            if f"{prefix}_get_conv_spec_edit" in self.__dict__:
                self.__dict__[f"{prefix}_get_conv_spec_edit"].setText(get_conv_spec)
            if f"{prefix}_put_conv_spec_edit" in self.__dict__:
                self.__dict__[f"{prefix}_put_conv_spec_edit"].setText(put_conv_spec)

        # Populate External and Internal Modes
        populate_mode_data("ext", existing_channel.get("external", {}))
        populate_mode_data("int", existing_channel.get("internal", {}))

        self.update_conv_func_displays("ext")
        self.update_conv_func_displays("int")


# ---------------------- Element Dialog ---------------------- #


class ElementDialog(QDialog):

    def __init__(
        self,
        parent=None,
        existing_element=None,
        existing_pv_elem_maps=None,
        existing_simpv_elem_maps=None,
        existing_simpv_defs=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Add/Edit Element")
        self.setMinimumWidth(1000)
        self.element_data = None
        self.channels = existing_element.get("channels", []) if existing_element else []

        self.init_ui(
            existing_element,
            existing_pv_elem_maps,
            existing_simpv_elem_maps,
            existing_simpv_defs,
        )

    def init_ui(
        self,
        existing_element,
        existing_pv_elem_maps,
        existing_simpv_elem_maps,
        existing_simpv_defs,
    ):
        layout = QVBoxLayout()

        # Element Details Group
        element_details_group = QGroupBox("Element Details")
        element_details_layout = QFormLayout()

        self.element_name_edit = QLineEdit()
        self.element_description_edit = QLineEdit()

        element_details_layout.addRow("Element Name:", self.element_name_edit)
        element_details_layout.addRow(
            "Description (optional):", self.element_description_edit
        )

        element_details_group.setLayout(element_details_layout)
        layout.addWidget(element_details_group)

        # pvid_to_repr_map Groups
        self.init_pvid_reprs_groups(
            layout, existing_pv_elem_maps, existing_simpv_elem_maps, existing_simpv_defs
        )

        # repr_units Group
        repr_units_group = QGroupBox("repr_units")
        repr_units_layout = QVBoxLayout()

        self.repr_units_table = QTableWidget(0, 2)
        self.repr_units_table.setHorizontalHeaderLabels(["Repr", "Unit"])
        header = self.repr_units_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)  # First column stretches
        header.setSectionResizeMode(
            1, QHeaderView.Stretch
        )  # Second column stretches equally
        self.repr_units_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.repr_units_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.repr_units_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.repr_units_table.cellDoubleClicked.connect(self.edit_repr_unit)

        repr_units_buttons_layout = QHBoxLayout()
        add_unit_btn = QPushButton("Add")
        edit_unit_btn = QPushButton("Edit")
        delete_unit_btn = QPushButton("Delete")
        repr_units_buttons_layout.addWidget(add_unit_btn)
        repr_units_buttons_layout.addWidget(edit_unit_btn)
        repr_units_buttons_layout.addWidget(delete_unit_btn)
        repr_units_buttons_layout.addStretch()

        repr_units_layout.addWidget(self.repr_units_table)
        repr_units_layout.addLayout(repr_units_buttons_layout)
        repr_units_group.setLayout(repr_units_layout)
        layout.addWidget(repr_units_group)

        # channel_map Group
        channels_group = QGroupBox("channel_map")
        channels_layout = QVBoxLayout()

        self.channels_list = QListWidget()
        self.channels_list.setSelectionMode(QAbstractItemView.SingleSelection)
        # Connect double-click signal to the edit_channel method
        self.channels_list.itemDoubleClicked.connect(self.edit_channel)
        channels_layout.addWidget(self.channels_list)

        channels_buttons_layout = QHBoxLayout()
        add_channel_btn = QPushButton("Add Channel")
        edit_channel_btn = QPushButton("Edit Channel")
        delete_channel_btn = QPushButton("Delete Channel")
        channels_buttons_layout.addWidget(add_channel_btn)
        channels_buttons_layout.addWidget(edit_channel_btn)
        channels_buttons_layout.addWidget(delete_channel_btn)
        channels_buttons_layout.addStretch()

        channels_layout.addLayout(channels_buttons_layout)
        channels_group.setLayout(channels_layout)
        layout.addWidget(channels_group)

        # func_specs Group
        func_specs_group = QGroupBox("func_specs")
        func_specs_layout = QVBoxLayout()

        self.func_specs_table = QTableWidget(0, 4)
        self.func_specs_table.setHorizontalHeaderLabels(
            ["Key", "Name", "Args", "Kwargs"]
        )
        self.func_specs_table.horizontalHeader().setStretchLastSection(True)
        self.func_specs_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.func_specs_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.func_specs_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.func_specs_table.cellDoubleClicked.connect(self.edit_funcspec)

        func_specs_buttons_layout = QHBoxLayout()
        add_funcspec_btn = QPushButton("Add")
        edit_funcspec_btn = QPushButton("Edit")
        delete_funcspec_btn = QPushButton("Delete")
        func_specs_buttons_layout.addWidget(add_funcspec_btn)
        func_specs_buttons_layout.addWidget(edit_funcspec_btn)
        func_specs_buttons_layout.addWidget(delete_funcspec_btn)
        func_specs_buttons_layout.addStretch()

        func_specs_layout.addWidget(self.func_specs_table)
        func_specs_layout.addLayout(func_specs_buttons_layout)
        func_specs_group.setLayout(func_specs_layout)
        layout.addWidget(func_specs_group)

        # Buttons
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()
        submit_btn = QPushButton("Submit")
        cancel_btn = QPushButton("Cancel")
        buttons_layout.addWidget(submit_btn)
        buttons_layout.addWidget(cancel_btn)
        layout.addLayout(buttons_layout)

        self.setLayout(layout)

        # Connect buttons for pvid_to_repr_map - External
        self.add_pvid_ext_btn.clicked.connect(lambda: self.add_pvid_repr("ext"))
        self.edit_pvid_ext_btn.clicked.connect(lambda: self.edit_pvid_repr("ext"))
        self.delete_pvid_ext_btn.clicked.connect(lambda: self.delete_pvid_repr("ext"))

        # Connect buttons for pvid_to_repr_map - Internal
        self.add_pvid_int_btn.clicked.connect(lambda: self.add_pvid_repr("int"))
        self.edit_pvid_int_btn.clicked.connect(lambda: self.edit_pvid_repr("int"))
        self.delete_pvid_int_btn.clicked.connect(lambda: self.delete_pvid_repr("int"))

        # Connect repr_units buttons
        add_unit_btn.clicked.connect(self.add_repr_unit)
        edit_unit_btn.clicked.connect(self.edit_repr_unit)
        delete_unit_btn.clicked.connect(self.delete_repr_unit)

        # Connect func_specs buttons
        add_funcspec_btn.clicked.connect(self.add_funcspec)
        edit_funcspec_btn.clicked.connect(self.edit_funcspec)
        delete_funcspec_btn.clicked.connect(self.delete_funcspec)

        # Connect channel_map buttons
        add_channel_btn.clicked.connect(self.add_channel)
        edit_channel_btn.clicked.connect(self.edit_channel)
        delete_channel_btn.clicked.connect(self.delete_channel)

        # Connect submit and cancel buttons
        submit_btn.clicked.connect(self.submit)
        cancel_btn.clicked.connect(self.reject)

        # If editing, populate data
        if existing_element:
            self.populate_data(existing_element)

    def init_pvid_reprs_groups(
        self,
        layout,
        existing_pv_elem_maps,
        existing_simpv_elem_maps,
        existing_simpv_defs,
    ):
        # External pvid_to_repr_map Group
        ext_pvid_group = QGroupBox("pvid_to_repr_map - External (ext)")
        ext_pvid_layout = QVBoxLayout()

        self.ext_pvid_table = QTableWidget(0, 2)
        self.ext_pvid_table.setHorizontalHeaderLabels(["PVID", "Repr"])
        header = self.ext_pvid_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)  # First column stretches
        header.setSectionResizeMode(
            1, QHeaderView.Stretch
        )  # Second column stretches equally
        self.ext_pvid_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.ext_pvid_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.ext_pvid_table.setSelectionMode(QAbstractItemView.SingleSelection)

        ext_pvid_buttons_layout = QHBoxLayout()
        self.add_pvid_ext_btn = QPushButton("Add External PVID")
        self.edit_pvid_ext_btn = QPushButton("Edit External PVID")
        self.delete_pvid_ext_btn = QPushButton("Delete External PVID")
        ext_pvid_buttons_layout.addWidget(self.add_pvid_ext_btn)
        ext_pvid_buttons_layout.addWidget(self.edit_pvid_ext_btn)
        ext_pvid_buttons_layout.addWidget(self.delete_pvid_ext_btn)
        ext_pvid_buttons_layout.addStretch()
        self.map_pv_btn = QPushButton("Map PV")
        ext_pvid_buttons_layout.addWidget(self.map_pv_btn)

        self.map_pv_btn.clicked.connect(
            lambda _, m=existing_pv_elem_maps: self.open_map_pv_dialog(m)
        )

        self.ext_pvid_table.cellDoubleClicked.connect(
            lambda: self.edit_pvid_repr("ext")
        )

        ext_pvid_layout.addWidget(self.ext_pvid_table)
        ext_pvid_layout.addLayout(ext_pvid_buttons_layout)
        ext_pvid_group.setLayout(ext_pvid_layout)
        layout.addWidget(ext_pvid_group)

        # Internal pvid_to_repr_map Group
        int_pvid_group = QGroupBox("pvid_to_repr_map - Internal (int)")
        int_pvid_layout = QVBoxLayout()

        self.int_pvid_table = QTableWidget(0, 2)
        self.int_pvid_table.setHorizontalHeaderLabels(["PVID", "Repr"])
        header = self.int_pvid_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)  # First column stretches
        header.setSectionResizeMode(
            1, QHeaderView.Stretch
        )  # Second column stretches equally
        self.int_pvid_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.int_pvid_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.int_pvid_table.setSelectionMode(QAbstractItemView.SingleSelection)

        int_pvid_buttons_layout = QHBoxLayout()
        self.add_pvid_int_btn = QPushButton("Add Internal PVID")
        self.edit_pvid_int_btn = QPushButton("Edit Internal PVID")
        self.delete_pvid_int_btn = QPushButton("Delete Internal PVID")
        int_pvid_buttons_layout.addWidget(self.add_pvid_int_btn)
        int_pvid_buttons_layout.addWidget(self.edit_pvid_int_btn)
        int_pvid_buttons_layout.addWidget(self.delete_pvid_int_btn)
        int_pvid_buttons_layout.addStretch()
        self.map_simpv_btn = QPushButton("Map SimPV")
        int_pvid_buttons_layout.addWidget(self.map_simpv_btn)
        self.define_simpv_btn = QPushButton("Define SimPV")
        int_pvid_buttons_layout.addWidget(self.define_simpv_btn)

        self.map_simpv_btn.clicked.connect(
            lambda _, m=existing_simpv_elem_maps: self.open_map_simpv_dialog(m)
        )
        self.define_simpv_btn.clicked.connect(
            lambda _, m1=existing_simpv_elem_maps, m2=existing_simpv_defs: self.open_define_simpv_dialog(
                m1, m2
            )
        )

        self.int_pvid_table.cellDoubleClicked.connect(
            lambda: self.edit_pvid_repr("int")
        )

        int_pvid_layout.addWidget(self.int_pvid_table)
        int_pvid_layout.addLayout(int_pvid_buttons_layout)
        int_pvid_group.setLayout(int_pvid_layout)
        layout.addWidget(int_pvid_group)

    def open_map_pv_dialog(self, existing_pv_elem_maps: Dict):

        table = self.ext_pvid_table
        selected_items = table.selectedItems()
        if not selected_items:
            show_error(f"Please select a pvid_to_repr_map entry to edit in 'ext'.")
            return
        row = table.currentRow()
        pvid = table.item(row, 0).text()

        dialog = MapPVDialog(self, pv_elem_maps=existing_pv_elem_maps, pvid=pvid)
        if dialog.exec_() == QDialog.Accepted:
            new_data = dialog.pv_elem_maps
            existing_pv_elem_maps.update(new_data)

    def open_map_simpv_dialog(self, existing_simpv_elem_maps: Dict):

        table = self.int_pvid_table
        selected_items = table.selectedItems()
        if not selected_items:
            show_error(f"Please select a pvid_to_repr_map entry to edit in 'int'.")
            return
        row = table.currentRow()
        pvid = table.item(row, 0).text()

        dialog = MapSimPVDialog(
            self, simpv_elem_maps=existing_simpv_elem_maps, pvid=pvid
        )
        if dialog.exec_() == QDialog.Accepted:
            new_data = dialog.simpv_elem_maps
            existing_simpv_elem_maps.update(new_data)

    def open_define_simpv_dialog(
        self, existing_simpv_elem_maps: Dict, existing_simpv_defs: List
    ):

        table = self.int_pvid_table
        selected_items = table.selectedItems()
        if not selected_items:
            show_error(f"Please select a pvid_to_repr_map entry to edit in 'int'.")
            return
        row = table.currentRow()
        pvid = table.item(row, 0).text()

        pvid_to_pvsuffix_map = {
            d["pvid_in_elem"]: pvname for pvname, d in existing_simpv_elem_maps.items()
        }
        pvsuffix = pvid_to_pvsuffix_map[pvid]

        dialog = DefineSimPVDialog(
            self, simpv_defs=existing_simpv_defs, pvsuffix=pvsuffix
        )
        if dialog.exec_() == QDialog.Accepted:
            new_data = dialog.simpv_defs
            existing_simpv_defs.update(new_data)

    def add_pvid_repr(self, mode):
        dialog = PVIDReprMapDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            pvid = dialog.map_data["pvid"]
            repr_val = dialog.map_data["repr"]

            table = self.ext_pvid_table if mode == "ext" else self.int_pvid_table

            # Check for unique PVID in the selected mode
            for row in range(table.rowCount()):
                existing_pvid = table.item(row, 0).text().strip()
                if pvid.lower() == existing_pvid.lower():
                    show_error(f"PVID '{pvid}' already exists in {mode}.")
                    return

            table.insertRow(table.rowCount())
            table.setItem(table.rowCount() - 1, 0, QTableWidgetItem(pvid))
            table.setItem(table.rowCount() - 1, 1, QTableWidgetItem(repr_val))

    def edit_pvid_repr(self, mode):
        table = self.ext_pvid_table if mode == "ext" else self.int_pvid_table
        selected_items = table.selectedItems()
        if not selected_items:
            show_error(f"Please select a pvid_to_repr_map entry to edit in {mode}.")
            return
        row = table.currentRow()
        pvid = table.item(row, 0).text()
        repr_val = table.item(row, 1).text()
        existing_map = {"pvid": pvid, "repr": repr_val}
        dialog = PVIDReprMapDialog(self, existing_map)
        if dialog.exec_() == QDialog.Accepted:
            updated_map = dialog.map_data
            new_pvid = updated_map["pvid"]

            # Check for unique PVID excluding the current row
            for r in range(table.rowCount()):
                if r == row:
                    continue
                existing_pvid = table.item(r, 0).text().strip()
                if new_pvid.lower() == existing_pvid.lower():
                    show_error(f"PVID '{new_pvid}' already exists in {mode}.")
                    return

            table.setItem(row, 0, QTableWidgetItem(updated_map["pvid"]))
            table.setItem(row, 1, QTableWidgetItem(updated_map["repr"]))

    def delete_pvid_repr(self, mode):
        table = self.ext_pvid_table if mode == "ext" else self.int_pvid_table
        selected_items = table.selectedItems()
        if not selected_items:
            show_error(f"Please select a pvid_to_repr_map entry to delete in {mode}.")
            return
        row = table.currentRow()
        pvid = table.item(row, 0).text()
        reply = QMessageBox.question(
            self,
            "Confirm Deletion",
            f"Are you sure you want to delete the pvid_to_repr_map entry '{pvid}' in {mode}?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            table.removeRow(row)

    def add_repr_unit(self):
        available_reprs = self.get_available_reprs()
        dialog = ReprUnitsDialog(self, repr_list=available_reprs)

        if dialog.exec_() == QDialog.Accepted:
            repr_key = dialog.units_data["repr"]
            unit_val = dialog.units_data["unit"]

            # Check for unique Repr
            for row in range(self.repr_units_table.rowCount()):
                existing_repr = self.repr_units_table.item(row, 0).text().strip()
                if repr_key.lower() == existing_repr.lower():
                    show_error(f"Repr '{repr_key}' already exists.")
                    return

            self.repr_units_table.insertRow(self.repr_units_table.rowCount())
            self.repr_units_table.setItem(
                self.repr_units_table.rowCount() - 1, 0, QTableWidgetItem(repr_key)
            )
            self.repr_units_table.setItem(
                self.repr_units_table.rowCount() - 1, 1, QTableWidgetItem(unit_val)
            )

    def edit_repr_unit(self):
        selected_items = self.repr_units_table.selectedItems()
        if not selected_items:
            show_error("Please select a repr_unit entry to edit.")
            return
        row = self.repr_units_table.currentRow()
        repr_key = self.repr_units_table.item(row, 0).text()
        unit_val = self.repr_units_table.item(row, 1).text()
        existing_units = {"repr": repr_key, "unit": unit_val}
        available_reprs = self.get_available_reprs()
        available_reprs.append(repr_key)  # Allow the current repr
        dialog = ReprUnitsDialog(self, existing_units, repr_list=available_reprs)
        if dialog.exec_() == QDialog.Accepted:
            updated_units = dialog.units_data
            new_repr = updated_units["repr"]

            # Check for unique Repr excluding the current row
            for r in range(self.repr_units_table.rowCount()):
                if r == row:
                    continue
                existing_repr = self.repr_units_table.item(r, 0).text().strip()
                if new_repr.lower() == existing_repr.lower():
                    show_error(f"Repr '{new_repr}' already exists.")
                    return

            self.repr_units_table.setItem(
                row, 0, QTableWidgetItem(updated_units["repr"])
            )
            self.repr_units_table.setItem(
                row, 1, QTableWidgetItem(updated_units["unit"])
            )

    def delete_repr_unit(self):
        selected_items = self.repr_units_table.selectedItems()
        if not selected_items:
            show_error("Please select a repr_unit entry to delete.")
            return
        row = self.repr_units_table.currentRow()
        repr_key = self.repr_units_table.item(row, 0).text()
        reply = QMessageBox.question(
            self,
            "Confirm Deletion",
            f"Are you sure you want to delete the repr_unit entry '{repr_key}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.repr_units_table.removeRow(row)

    def add_funcspec(self):
        conv_spec_names = self.get_conv_spec_names()

        # Exclude already-defined funcspec keys
        used_keys = []
        for row in range(self.func_specs_table.rowCount()):
            used_keys.append(self.func_specs_table.item(row, 0).text().strip())
        available_conv_specs = [cs for cs in conv_spec_names if cs not in used_keys]

        dialog = FuncSpecDialog(self, conv_spec_names=available_conv_specs)

        if dialog.exec_() == QDialog.Accepted:
            funcspec = dialog.funcspec_data
            self.func_specs_table.insertRow(self.func_specs_table.rowCount())
            self.func_specs_table.setItem(
                self.func_specs_table.rowCount() - 1,
                0,
                QTableWidgetItem(funcspec["key"]),
            )
            self.func_specs_table.setItem(
                self.func_specs_table.rowCount() - 1,
                1,
                QTableWidgetItem(funcspec["name"]),
            )
            self.func_specs_table.setItem(
                self.func_specs_table.rowCount() - 1,
                2,
                QTableWidgetItem(str(funcspec["args"])),
            )
            self.func_specs_table.setItem(
                self.func_specs_table.rowCount() - 1,
                3,
                QTableWidgetItem(str(funcspec["kwargs"])),
            )

    def edit_funcspec(self):
        selected_items = self.func_specs_table.selectedItems()
        if not selected_items:
            show_error("Please select a func_spec entry to edit.")
            return
        row = self.func_specs_table.currentRow()
        key = self.func_specs_table.item(row, 0).text()
        name = self.func_specs_table.item(row, 1).text()
        args = self.func_specs_table.item(row, 2)
        args = args.text() if args else ""
        kwargs = self.func_specs_table.item(row, 3)
        kwargs = kwargs.text() if kwargs else ""
        existing_funcspec = {
            "key": key,
            "name": name,
            "args": eval(args) if args else "",
            "kwargs": eval(kwargs) if kwargs else "",
        }
        conv_spec_names = self.get_conv_spec_names()
        dialog = FuncSpecDialog(
            self, existing_funcspec, conv_spec_names=conv_spec_names
        )
        if dialog.exec_() == QDialog.Accepted:
            updated_funcspec = dialog.funcspec_data
            self.func_specs_table.setItem(
                row, 0, QTableWidgetItem(updated_funcspec["key"])
            )
            self.func_specs_table.setItem(
                row, 1, QTableWidgetItem(updated_funcspec["name"])
            )
            self.func_specs_table.setItem(
                row, 2, QTableWidgetItem(str(updated_funcspec["args"]))
            )
            self.func_specs_table.setItem(
                row, 3, QTableWidgetItem(str(updated_funcspec["kwargs"]))
            )

    def delete_funcspec(self):
        selected_items = self.func_specs_table.selectedItems()
        if not selected_items:
            show_error("Please select a func_spec entry to delete.")
            return
        row = self.func_specs_table.currentRow()
        key = self.func_specs_table.item(row, 0).text()
        reply = QMessageBox.question(
            self,
            "Confirm Deletion",
            f"Are you sure you want to delete the func_spec entry '{key}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.func_specs_table.removeRow(row)

    def add_channel(self):
        pvids = self.get_all_pvids()
        # Pass current Reprs so High-Level Reprs can be selected from them only
        repr_list = self.get_current_reprs()

        dialog = ChannelDialog(self, pvids=pvids, repr_list=repr_list)
        if dialog.exec_() == QDialog.Accepted:
            channel = dialog.channel_data
            self.channels.append(channel)
            self.update_channels_list()

    def edit_channel(self):
        selected_items = self.channels_list.selectedItems()
        if not selected_items:
            show_error("Please select a channel to edit.")
            return
        index = self.channels_list.row(selected_items[0])
        channel = self.channels[index]

        pvids = self.get_all_pvids()
        repr_list = self.get_current_reprs()
        dialog = ChannelDialog(
            self, existing_channel=channel, pvids=pvids, repr_list=repr_list
        )
        if dialog.exec_() == QDialog.Accepted:
            self.channels[index] = dialog.channel_data
            self.update_channels_list()

    def delete_channel(self):
        selected_items = self.channels_list.selectedItems()
        if not selected_items:
            show_error("Please select a channel to delete.")
            return
        index = self.channels_list.row(selected_items[0])

        reply = QMessageBox.question(
            self,
            "Confirm Deletion",
            f"Are you sure you want to delete the channel '{self.channels[index]['channel_name']}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            del self.channels[index]
            self.update_channels_list()

    def update_channels_list(self):
        self.channels_list.clear()
        for ch in self.channels:
            self.channels_list.addItem(f"{ch['channel_name']} ({ch['channel_type']})")

    def get_current_reprs(self):
        reprs = []
        for row in range(self.ext_pvid_table.rowCount()):
            repr_val = self.ext_pvid_table.item(row, 1).text().strip()
            if repr_val and repr_val not in reprs:
                reprs.append(repr_val)
        for row in range(self.int_pvid_table.rowCount()):
            repr_val = self.int_pvid_table.item(row, 1).text().strip()
            if repr_val and repr_val not in reprs:
                reprs.append(repr_val)
        return reprs

    def get_existing_repr_units(self):
        units = []
        for row in range(self.repr_units_table.rowCount()):
            repr_key = self.repr_units_table.item(row, 0).text().strip()
            if repr_key and repr_key not in units:
                units.append(repr_key)
        return units

    def get_available_reprs(self):
        existing_repr_units = self.get_existing_repr_units()
        all_reprs = self.get_current_reprs()
        available_reprs = [r for r in all_reprs if r not in existing_repr_units]
        return available_reprs

    def get_conv_spec_names(self):
        conv_specs = []
        for ch in self.channels:
            if "external" in ch:
                conv_name = ch["external"].get("conv_spec_name")
                if conv_name and conv_name not in conv_specs:
                    conv_specs.append(conv_name)
            if "internal" in ch:
                conv_name = ch["internal"].get("conv_spec_name")
                if conv_name and conv_name not in conv_specs:
                    conv_specs.append(conv_name)
        return conv_specs

    def populate_data(self, existing_element):
        # Populate Element Details
        self.element_name_edit.setText(existing_element.get("element_name", ""))
        self.element_description_edit.setText(existing_element.get("description", ""))

        # Populate External pvid_to_repr_map
        ext_map = existing_element["pvid_to_repr_map"].get("ext", {})
        for pvid, repr_val in ext_map.items():
            self.ext_pvid_table.insertRow(self.ext_pvid_table.rowCount())
            self.ext_pvid_table.setItem(
                self.ext_pvid_table.rowCount() - 1, 0, QTableWidgetItem(pvid)
            )
            self.ext_pvid_table.setItem(
                self.ext_pvid_table.rowCount() - 1, 1, QTableWidgetItem(repr_val)
            )

        # Populate Internal pvid_to_repr_map
        int_map = existing_element["pvid_to_repr_map"].get("int", {})
        for pvid, repr_val in int_map.items():
            self.int_pvid_table.insertRow(self.int_pvid_table.rowCount())
            self.int_pvid_table.setItem(
                self.int_pvid_table.rowCount() - 1, 0, QTableWidgetItem(pvid)
            )
            self.int_pvid_table.setItem(
                self.int_pvid_table.rowCount() - 1, 1, QTableWidgetItem(repr_val)
            )

        # Populate repr_units
        repr_units = existing_element.get("repr_units", {})
        for repr_key, unit_val in repr_units.items():
            self.repr_units_table.insertRow(self.repr_units_table.rowCount())
            self.repr_units_table.setItem(
                self.repr_units_table.rowCount() - 1, 0, QTableWidgetItem(repr_key)
            )
            self.repr_units_table.setItem(
                self.repr_units_table.rowCount() - 1, 1, QTableWidgetItem(unit_val)
            )

        # Populate func_specs
        func_specs = existing_element.get("func_specs", {})
        for key, spec in func_specs.items():
            self.func_specs_table.insertRow(self.func_specs_table.rowCount())
            self.func_specs_table.setItem(
                self.func_specs_table.rowCount() - 1, 0, QTableWidgetItem(key)
            )
            self.func_specs_table.setItem(
                self.func_specs_table.rowCount() - 1, 1, QTableWidgetItem(spec["name"])
            )
            try:
                self.func_specs_table.setItem(
                    self.func_specs_table.rowCount() - 1,
                    2,
                    QTableWidgetItem(str(spec["args"])),
                )
            except KeyError:
                pass
            try:
                self.func_specs_table.setItem(
                    self.func_specs_table.rowCount() - 1,
                    3,
                    QTableWidgetItem(str(spec["kwargs"])),
                )
            except KeyError:
                pass

        # Populate channels
        channels = existing_element.get("channels", [])
        for ch in channels:
            self.channels_list.addItem(f"{ch['channel_name']} ({ch['channel_type']})")

    def get_conv_spec_names(self):
        conv_specs = []
        for ch in self.channels:
            if "external" in ch:
                for get_or_put, v in ch["external"].items():
                    conv_name = v.get("conv_spec_name")
                    if conv_name and conv_name not in conv_specs:
                        conv_specs.append(conv_name)
            if "internal" in ch:
                for get_or_put, v in ch["internal"].items():
                    conv_name = v.get("conv_spec_name")
                    if conv_name and conv_name not in conv_specs:
                        conv_specs.append(conv_name)

        return conv_specs

    def submit(self):
        # Validate Element Name
        element_name = self.element_name_edit.text().strip()
        if not element_name:
            show_error("Element Name is required.")
            return

        # Compile pvid_to_repr_map_ext
        pvid_to_repr_map_ext = {}
        pvid_set_ext = set()
        for row in range(self.ext_pvid_table.rowCount()):
            pvid = self.ext_pvid_table.item(row, 0).text().strip()
            repr_val = self.ext_pvid_table.item(row, 1).text().strip()
            if pvid in pvid_set_ext:
                show_error(f"Duplicate PVID '{pvid}' found in pvid_to_repr_map['ext'].")
                return
            pvid_set_ext.add(pvid)
            if pvid and repr_val:
                pvid_to_repr_map_ext[pvid] = repr_val

        # Compile pvid_to_repr_map_int
        pvid_to_repr_map_int = {}
        pvid_set_int = set()
        for row in range(self.int_pvid_table.rowCount()):
            pvid = self.int_pvid_table.item(row, 0).text().strip()
            repr_val = self.int_pvid_table.item(row, 1).text().strip()
            if pvid in pvid_set_int:
                show_error(f"Duplicate PVID '{pvid}' found in pvid_to_repr_map['int'].")
                return
            pvid_set_int.add(pvid)
            if pvid and repr_val:
                pvid_to_repr_map_int[pvid] = repr_val

        # Compile repr_units with uniqueness check
        repr_units = {}
        repr_set = set()
        for row in range(self.repr_units_table.rowCount()):
            repr_key = self.repr_units_table.item(row, 0).text().strip()
            unit_val = self.repr_units_table.item(row, 1).text().strip()
            if repr_key in repr_set:
                show_error(f"Duplicate Repr '{repr_key}' found in repr_units.")
                return
            repr_set.add(repr_key)
            if repr_key and unit_val:
                repr_units[repr_key] = unit_val

        # Compile func_specs
        func_specs = {}
        for row in range(self.func_specs_table.rowCount()):
            key = self.func_specs_table.item(row, 0).text().strip()
            name = self.func_specs_table.item(row, 1).text().strip()
            args = self.func_specs_table.item(row, 2)
            args = args.text().strip() if args else ""
            kwargs = self.func_specs_table.item(row, 3)
            kwargs = kwargs.text().strip() if kwargs else ""
            if key and name:
                try:
                    args_eval = eval(args) if args else []
                    kwargs_eval = eval(kwargs) if kwargs else {}
                except Exception as e:
                    show_error(
                        f"Error parsing args or kwargs for func_spec '{key}': {e}"
                    )
                    return
                func_specs[key] = {
                    "name": name,
                    "args": args_eval,
                    "kwargs": kwargs_eval,
                }

        # Compile channels
        compiled_channels = []
        for ch in self.channels:
            channel_entry = {
                "channel_name": ch["channel_name"],
                "channel_type": ch["channel_type"],
                "high_level_reprs": ch["high_level_reprs"],
            }
            if "external" in ch:
                channel_entry["external"] = ch["external"]
            if "internal" in ch:
                channel_entry["internal"] = ch["internal"]
            compiled_channels.append(channel_entry)

        # Compile element data
        compiled_data = {"element_name": element_name}

        description = self.element_description_edit.text().strip()
        if description:
            compiled_data["description"] = description

        if pvid_to_repr_map_ext:
            if "pvid_to_repr_map" not in compiled_data:
                compiled_data["pvid_to_repr_map"] = {}
            compiled_data["pvid_to_repr_map"]["ext"] = pvid_to_repr_map_ext

        if pvid_to_repr_map_int:
            if "pvid_to_repr_map" not in compiled_data:
                compiled_data["pvid_to_repr_map"] = {}
            compiled_data["pvid_to_repr_map"]["int"] = pvid_to_repr_map_int

        if repr_units:
            compiled_data["repr_units"] = repr_units

        if func_specs:
            compiled_data["func_specs"] = func_specs

        if compiled_channels:
            compiled_data["channels"] = compiled_channels

        self.element_data = compiled_data

        self.accept()  # Close the dialog with success

    def get_all_pvids(self):
        pvids_ext = [
            self.ext_pvid_table.item(row, 0).text().strip()
            for row in range(self.ext_pvid_table.rowCount())
        ]
        pvids_int = [
            self.int_pvid_table.item(row, 0).text().strip()
            for row in range(self.int_pvid_table.rowCount())
        ]
        return {"ext": pvids_ext, "int": pvids_int}


# ---------------------- Main Window ---------------------- #


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Element and Channel Manager")
        self.setMinimumSize(1200, 800)
        self.elements = []  # List to store elements
        self.pv_elem_maps = {}  # Dict to store pv_elem_maps
        self.simpv_elem_maps = {}  # Dict to store simpv_elem_maps
        self.simpv_defs = {}  # Dict to store simpv definitions

        self.init_ui()

    def init_ui(self):
        central_widget = QWidget()
        main_layout = QVBoxLayout()

        header_group = QGroupBox("Header Info:")
        header_layout = QFormLayout()
        self.facility_edit = QLineEdit()
        self.machine_edit = QLineEdit()
        self.simulator_config_edit = QLineEdit()
        header_layout.addRow("Facility:", self.facility_edit)
        header_layout.addRow("Machine:", self.machine_edit)
        header_layout.addRow("Simulator Config.:", self.simulator_config_edit)
        header_group.setLayout(header_layout)
        main_layout.addWidget(header_group)

        elements_group = QGroupBox("Elements:")
        elements_layout = QVBoxLayout()

        self.elements_list = QListWidget()
        self.elements_list.setSelectionMode(QAbstractItemView.SingleSelection)
        # Connect double-click signal to the edit_element method
        self.elements_list.itemDoubleClicked.connect(self.edit_element)
        elements_layout.addWidget(self.elements_list)

        elements_buttons_layout = QHBoxLayout()
        add_element_btn = QPushButton("Add Element")
        edit_element_btn = QPushButton("Edit Element")
        delete_element_btn = QPushButton("Delete Element")
        elements_buttons_layout.addWidget(add_element_btn)
        elements_buttons_layout.addWidget(edit_element_btn)
        elements_buttons_layout.addWidget(delete_element_btn)
        elements_buttons_layout.addStretch()

        elements_layout.addLayout(elements_buttons_layout)
        elements_group.setLayout(elements_layout)
        main_layout.addWidget(elements_group)

        # Bottom Buttons
        bottom_buttons_layout = QHBoxLayout()

        # Load Section
        _load_btn_label = QLabel("Load from YAML:")
        load_btn = QPushButton("elements")
        load_pv_elem_maps_btn = QPushButton("pv_elem_maps")
        load_simpv_elem_maps_btn = QPushButton("simpv_elem_maps")
        load_simpv_defs_btn = QPushButton("simpv_definitions")
        load_buttons_layout = QVBoxLayout()
        load_buttons_layout.addWidget(_load_btn_label)
        load_buttons_layout.addWidget(load_btn)
        load_buttons_layout.addWidget(load_pv_elem_maps_btn)
        load_buttons_layout.addWidget(load_simpv_elem_maps_btn)
        load_buttons_layout.addWidget(load_simpv_defs_btn)
        bottom_buttons_layout.addLayout(load_buttons_layout)

        # Spacer
        bottom_buttons_layout.addStretch()

        # Preview Section
        _preview_label = QLabel("Preview:")
        preview_btn = QPushButton("elements")
        preview_pv_elem_maps_btn = QPushButton("pv_elem_maps")
        preview_simpv_elem_maps_btn = QPushButton("simpv_elem_maps")
        preview_simpv_defs_btn = QPushButton("simpv_definitions")
        preview_buttons_layout = QVBoxLayout()
        preview_buttons_layout.addWidget(_preview_label)
        preview_buttons_layout.addWidget(preview_btn)
        preview_buttons_layout.addWidget(preview_pv_elem_maps_btn)
        preview_buttons_layout.addWidget(preview_simpv_elem_maps_btn)
        preview_buttons_layout.addWidget(preview_simpv_defs_btn)
        bottom_buttons_layout.addLayout(preview_buttons_layout)

        # Save Section
        _save_label = QLabel("Save to YAML:")
        save_btn = QPushButton("elements")
        save_pv_elem_maps_btn = QPushButton("pv_elem_maps")
        save_simpv_elem_maps_btn = QPushButton("simpv_elem_maps")
        save_simpv_defs_btn = QPushButton("simpv_definitions")
        save_buttons_layout = QVBoxLayout()
        save_buttons_layout.addWidget(_save_label)
        save_buttons_layout.addWidget(save_btn)
        save_buttons_layout.addWidget(save_pv_elem_maps_btn)
        save_buttons_layout.addWidget(save_simpv_elem_maps_btn)
        save_buttons_layout.addWidget(save_simpv_defs_btn)
        bottom_buttons_layout.addLayout(save_buttons_layout)

        # Exit Button
        exit_btn = QPushButton("Exit")
        bottom_buttons_layout.addWidget(exit_btn)

        main_layout.addLayout(bottom_buttons_layout)

        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

        # Connect buttons
        add_element_btn.clicked.connect(self.add_element)
        edit_element_btn.clicked.connect(self.edit_element)
        delete_element_btn.clicked.connect(self.delete_element)
        preview_btn.clicked.connect(self.preview_elements)
        load_btn.clicked.connect(self.load_elements_from_yaml)
        save_btn.clicked.connect(self.save_elements_to_yaml)
        exit_btn.clicked.connect(self.close)
        load_pv_elem_maps_btn.clicked.connect(self.load_pv_elem_maps_from_yaml)
        save_pv_elem_maps_btn.clicked.connect(self.save_pv_elem_maps_to_yaml)
        preview_pv_elem_maps_btn.clicked.connect(self.preview_pv_elem_maps)
        load_simpv_elem_maps_btn.clicked.connect(self.load_simpv_elem_maps_from_yaml)
        save_simpv_elem_maps_btn.clicked.connect(self.save_simpv_elem_maps_to_yaml)
        preview_simpv_elem_maps_btn.clicked.connect(self.preview_simpv_elem_maps)
        load_simpv_defs_btn.clicked.connect(self.load_simpv_defs_from_yaml)
        save_simpv_defs_btn.clicked.connect(self.save_simpv_defs_to_yaml)
        preview_simpv_defs_btn.clicked.connect(self.preview_simpv_defs)

    def add_element(self):
        dialog = ElementDialog(
            self,
            existing_pv_elem_maps=self.pv_elem_maps,
            existing_simpv_elem_maps=self.simpv_elem_maps,
            existing_simpv_defs=self.simpv_defs,
        )
        if dialog.exec_() == QDialog.Accepted:
            element = dialog.element_data
            self.elements.append(element)
            self.update_elements_list()

    def edit_element(self):
        selected_items = self.elements_list.selectedItems()
        if not selected_items:
            show_error("Please select an element to edit.")
            return
        index = self.elements_list.row(selected_items[0])
        element = self.elements[index]

        dialog = ElementDialog(
            self,
            existing_element=element,
            existing_pv_elem_maps=self.pv_elem_maps,
            existing_simpv_elem_maps=self.simpv_elem_maps,
            existing_simpv_defs=self.simpv_defs,
        )
        if dialog.exec_() == QDialog.Accepted:
            self.elements[index] = dialog.element_data
            self.update_elements_list()

    def delete_element(self):
        selected_items = self.elements_list.selectedItems()
        if not selected_items:
            show_error("Please select an element to delete.")
            return
        index = self.elements_list.row(selected_items[0])

        reply = QMessageBox.question(
            self,
            "Confirm Deletion",
            f"Are you sure you want to delete the element '{self.elements[index]['element_name']}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            del self.elements[index]
            self.update_elements_list()

    def update_elements_list(self):
        self.elements_list.clear()
        for elem in self.elements:
            self.elements_list.addItem(elem["element_name"])

    def populate_header_info(self, facility: str, machine: str, simulator_config: str):
        self.facility_edit.setText(facility)
        self.machine_edit.setText(machine)
        self.simulator_config_edit.setText(simulator_config)

    def load_elements_from_yaml(self):
        options = QFileDialog.Options()
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Load Data from YAML",
            "",
            "YAML Files (*.yaml);;All Files (*)",
            options=options,
        )
        if filename:
            try:
                with open(filename, "r") as file:
                    data = yaml.safe_load(file)
                # Clear current elements
                self.elements.clear()
                # Check for "elem_definitions" in loaded data
                elem_definitions = data.get("elem_definitions", {})
                for elem_name, elem_data in elem_definitions.items():
                    loaded_element = {"element_name": elem_name}
                    loaded_element.update(elem_data)

                    # Convert "channel_map" to a "channels" list
                    channel_map = elem_data.get("channel_map", {})
                    channels = []
                    for ch_name, ch_data in channel_map.items():
                        ch_entry = {
                            "channel_name": ch_name,
                            "channel_type": ch_data.get("handle", ""),
                            "high_level_reprs": ch_data.get("HiLv_reprs", []),
                        }
                        if "ext" in ch_data:
                            ch_entry["external"] = ch_data["ext"]
                        if "int" in ch_data:
                            ch_entry["internal"] = ch_data["int"]
                        channels.append(ch_entry)
                    loaded_element["channels"] = channels

                    self.elements.append(loaded_element)

                self.populate_header_info(
                    data.get("facility"),
                    data.get("machine"),
                    data.get("simulator_config"),
                )
                self.update_elements_list()
                show_info(f"Data successfully loaded from {filename}")
            except Exception as e:
                show_error(f"Error loading file: {e}")

    def load_pv_elem_maps_from_yaml(self):
        options = QFileDialog.Options()
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Load Data from YAML",
            "",
            "YAML Files (*.yaml);;All Files (*)",
            options=options,
        )
        if filename:
            try:
                with open(filename, "r") as file:
                    data = yaml.safe_load(file)
                # Clear current pv_elem_maps
                self.pv_elem_maps.clear()
                # Check for "pv_elem_maps" in loaded data
                pv_elem_maps = data.get("pv_elem_maps", {})
                for pvname, map_data in pv_elem_maps.items():
                    self.pv_elem_maps[pvname] = map_data
                show_info(f"Data successfully loaded from {filename}")
            except Exception as e:
                show_error(f"Error loading file: {e}")

    def load_simpv_elem_maps_from_yaml(self):
        options = QFileDialog.Options()
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Load Data from YAML",
            "",
            "YAML Files (*.yaml);;All Files (*)",
            options=options,
        )
        if filename:
            try:
                with open(filename, "r") as file:
                    data = yaml.safe_load(file)
                # Clear current simpv_elem_maps
                self.simpv_elem_maps.clear()
                # Check for "simpv_elem_maps" in loaded data
                simpv_elem_maps = data.get("simpv_elem_maps", {})
                for pvsuffix, map_data in simpv_elem_maps.items():
                    self.simpv_elem_maps[pvsuffix] = map_data
                show_info(f"Data successfully loaded from {filename}")
            except Exception as e:
                show_error(f"Error loading file: {e}")

    def load_simpv_defs_from_yaml(self):
        options = QFileDialog.Options()
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Load Data from YAML",
            "",
            "YAML Files (*.yaml);;All Files (*)",
            options=options,
        )
        if filename:
            try:
                with open(filename, "r") as file:
                    data = yaml.safe_load(file)
                # Clear current simpv_defs
                self.simpv_defs.clear()
                # Check for "sim_pv_definitions" in loaded data
                simpv_defs_list = data.get("sim_pv_definitions", {})
                for d in simpv_defs_list:
                    self.simpv_defs[d["pvsuffix"]] = {
                        k: v for k, v in d.items() if k != "pvsuffix"
                    }
                show_info(f"Data successfully loaded from {filename}")
            except Exception as e:
                show_error(f"Error loading file: {e}")

    def _compile_data(self):

        compiled_data = {
            "facility": self.facility_edit.text().strip(),
            "machine": self.machine_edit.text().strip(),
            "simulator_config": self.simulator_config_edit.text().strip(),
            "elem_definitions": {},
        }

        for elem in self.elements:
            elem_name = elem.get("element_name")
            if not elem_name:
                continue

            elem_def = {"pvid_to_repr_map": {}}
            if "pvid_to_repr_map_ext" in elem:
                elem_def["pvid_to_repr_map"]["ext"] = elem["pvid_to_repr_map_ext"]
            if "pvid_to_repr_map_int" in elem:
                elem_def["pvid_to_repr_map"]["int"] = elem["pvid_to_repr_map_int"]
            if "repr_units" in elem and elem["repr_units"]:
                elem_def["repr_units"] = elem["repr_units"]
            if "func_specs" in elem and elem["func_specs"]:
                elem_def["func_specs"] = elem["func_specs"]
            if "channels" in elem and elem["channels"]:
                channel_map = {}
                for ch in elem["channels"]:
                    ch_name = ch.get("channel_name")
                    if not ch_name:
                        continue
                    ch_entry = {
                        "handle": ch.get("channel_type"),
                        "HiLv_reprs": ch.get("high_level_reprs", []),
                    }
                    if "external" in ch and ch["external"]:
                        ch_entry["ext"] = deepcopy(ch["external"])
                    if "internal" in ch and ch["internal"]:
                        ch_entry["int"] = deepcopy(ch["internal"])

                    channel_map[ch_name] = ch_entry
                if channel_map:
                    elem_def["channel_map"] = channel_map
            compiled_data["elem_definitions"][elem_name] = elem_def

        return compiled_data

    def preview_elements(self):

        compiled_data = self._compile_data()
        yaml_data = yaml.dump(compiled_data, sort_keys=False)

        # Display in a scrollable dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Preview 'elements' Data")
        dialog.setMinimumSize(800, 600)
        layout = QVBoxLayout()
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setPlainText(yaml_data)
        layout.addWidget(text_edit)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)
        dialog.setLayout(layout)
        dialog.exec_()

    def preview_pv_elem_maps(self):

        compiled_data = {
            "facility": self.facility_edit.text().strip(),
            "machine": self.machine_edit.text().strip(),
            "simulator_config": self.simulator_config_edit.text().strip(),
            "pv_elem_maps": self.pv_elem_maps,
        }

        yaml_data = yaml.dump(compiled_data, sort_keys=False)

        # Display in a scrollable dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Preview 'pv_elem_maps' Data")
        dialog.setMinimumSize(800, 600)
        layout = QVBoxLayout()
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setPlainText(yaml_data)
        layout.addWidget(text_edit)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)
        dialog.setLayout(layout)
        dialog.exec_()

    def preview_simpv_elem_maps(self):

        compiled_data = {
            "facility": self.facility_edit.text().strip(),
            "machine": self.machine_edit.text().strip(),
            "simulator_config": self.simulator_config_edit.text().strip(),
            "simpv_elem_maps": self.simpv_elem_maps,
        }

        yaml_data = yaml.dump(compiled_data, sort_keys=False)

        # Display in a scrollable dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Preview 'simpv_elem_maps' Data")
        dialog.setMinimumSize(800, 600)
        layout = QVBoxLayout()
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setPlainText(yaml_data)
        layout.addWidget(text_edit)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)
        dialog.setLayout(layout)
        dialog.exec_()

    def preview_simpv_defs(self):

        compiled_data = {
            "facility": self.facility_edit.text().strip(),
            "machine": self.machine_edit.text().strip(),
            "simulator_config": self.simulator_config_edit.text().strip(),
        }

        simpv_defs_list = compiled_data["simpv_definitions"] = []
        for pvsuffix, d in self.simpv_defs.items():
            new_d = dict(pvsuffix=pvsuffix)
            new_d.update(d)
            simpv_defs_list.append(new_d)

        yaml_data = yaml.dump(compiled_data, sort_keys=False)

        # Display in a scrollable dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Preview 'simpv_defs' Data")
        dialog.setMinimumSize(800, 600)
        layout = QVBoxLayout()
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setPlainText(yaml_data)
        layout.addWidget(text_edit)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)
        dialog.setLayout(layout)
        dialog.exec_()

    def save_elements_to_yaml(self):

        compiled_data = self._compile_data()

        # Open file dialog to select save location
        options = QFileDialog.Options()
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Save 'elements' Data to YAML",
            "",
            "YAML Files (*.yaml);;All Files (*)",
            options=options,
        )
        if filename:
            try:
                with open(filename, "w") as file:
                    yaml.dump(compiled_data, file, sort_keys=False)
                show_info(f"Data successfully saved to {filename}")
            except Exception as e:
                show_error(f"Error saving file: {e}")

    def save_pv_elem_maps_to_yaml(self):

        compiled_data = {
            "facility": self.facility_edit.text().strip(),
            "machine": self.machine_edit.text().strip(),
            "simulator_config": self.simulator_config_edit.text().strip(),
            "pv_elem_maps": self.pv_elem_maps,
        }

        # Open file dialog to select save location
        options = QFileDialog.Options()
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Save 'pv_elem_maps' Data to YAML",
            "",
            "YAML Files (*.yaml);;All Files (*)",
            options=options,
        )
        if filename:
            try:
                with open(filename, "w") as file:
                    yaml.dump(compiled_data, file, sort_keys=False)
                show_info(f"Data successfully saved to {filename}")
            except Exception as e:
                show_error(f"Error saving file: {e}")

    def save_simpv_elem_maps_to_yaml(self):

        compiled_data = {
            "facility": self.facility_edit.text().strip(),
            "machine": self.machine_edit.text().strip(),
            "simulator_config": self.simulator_config_edit.text().strip(),
            "simpv_elem_maps": self.simpv_elem_maps,
        }

        # Open file dialog to select save location
        options = QFileDialog.Options()
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Save 'simpv_elem_maps' Data to YAML",
            "",
            "YAML Files (*.yaml);;All Files (*)",
            options=options,
        )
        if filename:
            try:
                with open(filename, "w") as file:
                    yaml.dump(compiled_data, file, sort_keys=False)
                show_info(f"Data successfully saved to {filename}")
            except Exception as e:
                show_error(f"Error saving file: {e}")

    def save_simpv_defs_to_yaml(self):

        compiled_data = {
            "facility": self.facility_edit.text().strip(),
            "machine": self.machine_edit.text().strip(),
            "simulator_config": self.simulator_config_edit.text().strip(),
        }
        simpv_defs_list = compiled_data["simpv_definitions"] = []
        for pvsuffix, d in self.simpv_defs.items():
            new_d = dict(pvsuffix=pvsuffix)
            new_d.update(d)
            simpv_defs_list.append(new_d)

        # Open file dialog to select save location
        options = QFileDialog.Options()
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Save 'simpv_defs' Data to YAML",
            "",
            "YAML Files (*.yaml);;All Files (*)",
            options=options,
        )
        if filename:
            try:
                with open(filename, "w") as file:
                    yaml.dump(compiled_data, file, sort_keys=False)
                show_info(f"Data successfully saved to {filename}")
            except Exception as e:
                show_error(f"Error saving file: {e}")


class MapPVDialog(QDialog):
    def __init__(self, parent=None, pv_elem_maps=None, pvid: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Map PV to Elements")
        self.setMinimumWidth(600)
        self.pv_elem_maps = pv_elem_maps
        self.pvid_to_pvname_map = {
            d["pvid_in_elem"]: pvname for pvname, d in pv_elem_maps.items()
        }
        assert pvid != ""
        self._pvid = pvid

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # Input fields for PV definition
        self.pvname_edit = QLineEdit()
        self.elem_names_edit = QLineEdit()
        self.handle_combo = QComboBox()
        self.handle_combo.addItems(["RB", "SP"])
        self.pvid_in_elem_edit = QLineEdit()
        self.dt_pvname_edit = QLineEdit()
        self.dt_pvunit_edit = QLineEdit()
        self.pvunit_edit = QLineEdit()

        self.pvid_in_elem_edit.setReadOnly(True)
        self.pvid_in_elem_edit.setText(self._pvid)

        if self._pvid in self.pvid_to_pvname_map:
            pvname = self.pvid_to_pvname_map[self._pvid]
            self.pvname_edit.setText(pvname)

            d = self.pv_elem_maps[pvname]

            self.elem_names_edit.setText(", ".join(d["elem_names"]))

            index = self.handle_combo.findText(d["handle"], Qt.MatchFixedString)
            if index >= 0:
                self.handle_combo.setCurrentIndex(index)

            DT_pvname = d.get("DT_pvname", None)
            if DT_pvname:
                self.dt_pvname_edit.setText(DT_pvname)
            DT_pvunit = d.get("DT_pvunit", None)
            if DT_pvunit:
                self.dt_pvunit_edit.setText(DT_pvunit)
            pvunit = d.get("pvunit", None)
            if pvunit:
                self.pvunit_edit.setText(pvunit)

        form_layout = QFormLayout()
        form_layout.addRow("PV Name:", self.pvname_edit)
        _label = QLabel("Element Names\n(comma-separated):")
        _label.setWordWrap(True)
        form_layout.addRow(_label, self.elem_names_edit)
        form_layout.addRow("Handle:", self.handle_combo)
        form_layout.addRow("PVID in Element:", self.pvid_in_elem_edit)
        form_layout.addRow("DT PV Name:", self.dt_pvname_edit)
        form_layout.addRow("DT PV Unit:", self.dt_pvunit_edit)
        form_layout.addRow("PV Unit:", self.pvunit_edit)

        layout.addLayout(form_layout)

        # Buttons for Submit and Cancel
        buttons_layout = QHBoxLayout()
        submit_btn = QPushButton("Submit")
        cancel_btn = QPushButton("Cancel")
        buttons_layout.addStretch()
        buttons_layout.addWidget(submit_btn)
        buttons_layout.addWidget(cancel_btn)

        layout.addLayout(buttons_layout)
        self.setLayout(layout)

        # Connect buttons
        submit_btn.clicked.connect(self.submit)
        cancel_btn.clicked.connect(self.reject)

    def submit(self):
        pvname = self.pvname_edit.text().strip()
        if not pvname:
            show_error("PV Name is required.")
            return

        elem_names = [
            name.strip()
            for name in self.elem_names_edit.text().split(",")
            if name.strip()
        ]
        handle = self.handle_combo.currentText()
        pvid_in_elem = self.pvid_in_elem_edit.text().strip()
        dt_pvname = self.dt_pvname_edit.text().strip()
        dt_pvunit = self.dt_pvunit_edit.text().strip()
        pvunit = self.pvunit_edit.text().strip()

        if not elem_names or not pvid_in_elem or not dt_pvname or not pvunit:
            show_error("All fields except PV Unit must be filled.")
            return

        self.pv_elem_maps[pvname] = {
            "elem_names": elem_names,
            "handle": handle,
            "pvid_in_elem": pvid_in_elem,
            "DT_pvname": dt_pvname,
            "DT_pvunit": dt_pvunit,
            "pvunit": pvunit,
        }

        self.accept()  # Close the dialog with success


class MapSimPVDialog(QDialog):
    def __init__(self, parent=None, simpv_elem_maps=None, pvid: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Map SimPV to Elements")
        self.setMinimumWidth(600)
        self.simpv_elem_maps = simpv_elem_maps
        self.pvid_to_pvsuffix_map = {
            d["pvid_in_elem"]: pvname for pvname, d in simpv_elem_maps.items()
        }
        assert pvid != ""
        self._pvid = pvid

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # Input fields for PV definition
        self.pvsuffix_edit = QLineEdit()
        self.elem_names_edit = QLineEdit()
        self.handle_combo = QComboBox()
        self.handle_combo.addItems(["RB", "SP"])
        self.pvid_in_elem_edit = QLineEdit()
        self.pvunit_edit = QLineEdit()

        self.pvid_in_elem_edit.setReadOnly(True)
        self.pvid_in_elem_edit.setText(self._pvid)

        if self._pvid in self.pvid_to_pvsuffix_map:
            pvsuffix = self.pvid_to_pvsuffix_map[self._pvid]
            self.pvsuffix_edit.setText(pvsuffix)

            d = self.simpv_elem_maps[pvsuffix]

            self.elem_names_edit.setText(", ".join(d["elem_names"]))

            index = self.handle_combo.findText(d["handle"], Qt.MatchFixedString)
            if index >= 0:
                self.handle_combo.setCurrentIndex(index)

            pvunit = d.get("pvunit", None)
            if pvunit:
                self.pvunit_edit.setText(pvunit)

        form_layout = QFormLayout()
        form_layout.addRow("SimPV Suffix:", self.pvsuffix_edit)
        _label = QLabel("Element Names\n(comma-separated):")
        _label.setWordWrap(True)
        form_layout.addRow(_label, self.elem_names_edit)
        form_layout.addRow("Handle:", self.handle_combo)
        form_layout.addRow("PVID in Element:", self.pvid_in_elem_edit)
        form_layout.addRow("PV Unit:", self.pvunit_edit)

        layout.addLayout(form_layout)

        # Buttons for Submit and Cancel
        buttons_layout = QHBoxLayout()
        submit_btn = QPushButton("Submit")
        cancel_btn = QPushButton("Cancel")
        buttons_layout.addStretch()
        buttons_layout.addWidget(submit_btn)
        buttons_layout.addWidget(cancel_btn)

        layout.addLayout(buttons_layout)
        self.setLayout(layout)

        # Connect buttons
        submit_btn.clicked.connect(self.submit)
        cancel_btn.clicked.connect(self.reject)

    def submit(self):
        pvsuffix = self.pvsuffix_edit.text().strip()
        if not pvsuffix:
            show_error("PV Suffix is required.")
            return

        elem_names = [
            name.strip()
            for name in self.elem_names_edit.text().split(",")
            if name.strip()
        ]
        handle = self.handle_combo.currentText()
        pvid_in_elem = self.pvid_in_elem_edit.text().strip()
        pvunit = self.pvunit_edit.text().strip()

        if not elem_names or not handle or not pvid_in_elem or not pvunit:
            show_error("All fields must be filled.")
            return

        self.simpv_elem_maps[pvsuffix] = {
            "elem_names": elem_names,
            "handle": handle,
            "pvid_in_elem": pvid_in_elem,
            "pvunit": pvunit,
        }

        self.accept()  # Close the dialog with success


class DefineSimPVDialog(QDialog):
    def __init__(self, parent=None, simpv_defs=None, pvsuffix: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Define SimPV")
        self.setMinimumWidth(600)
        self.simpv_defs = simpv_defs
        self._pvsuffix = pvsuffix

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # Input fields for PV definition
        self.pvsuffix_edit = QLineEdit()
        self.pvlass_combo = QComboBox()
        self.pvlass_combo.addItems(
            [
                "BPMSlowAcqSimPV",
                "CorrectorSimPV",
                "QuadrupoleSimPV",
                "SextupoleSimPV",
                "RfFreqSimPV",
                "BeamCurrentSimPV",
                "TuneSimPV",
            ]
        )
        self.args_edit = QLineEdit()
        self.kwargs_edit = QLineEdit()

        self.pvsuffix_edit.setReadOnly(True)
        self.pvsuffix_edit.setText(self._pvsuffix)

        if self._pvsuffix in self.simpv_defs:
            d = self.simpv_defs[self._pvsuffix]

            index = self.pvlass_combo.findText(d["pvclass"], Qt.MatchFixedString)
            if index >= 0:
                self.pvlass_combo.setCurrentIndex(index)

            if d.get("args", None):
                self.args_edit.setText(json.dumps(d["args"], indent=2))

            if d.get("kargs", None):
                self.kwargs_edit.setText(json.dumps(d["kwargs"], indent=2))

        form_layout = QFormLayout()
        form_layout.addRow("SimPV Suffix:", self.pvsuffix_edit)
        form_layout.addRow("SimPV Class", self.pvlass_combo)
        form_layout.addRow("Class args:", self.args_edit)
        form_layout.addRow("Class kwargs:", self.kwargs_edit)

        layout.addLayout(form_layout)

        # Buttons for Submit and Cancel
        buttons_layout = QHBoxLayout()
        submit_btn = QPushButton("Submit")
        cancel_btn = QPushButton("Cancel")
        buttons_layout.addStretch()
        buttons_layout.addWidget(submit_btn)
        buttons_layout.addWidget(cancel_btn)

        layout.addLayout(buttons_layout)
        self.setLayout(layout)

        # Connect buttons
        submit_btn.clicked.connect(self.submit)
        cancel_btn.clicked.connect(self.reject)

    def submit(self):
        pvsuffix = self.pvsuffix_edit.text().strip()
        if not pvsuffix:
            show_error("PV Suffix is required.")
            return

        pvclass = self.pvlass_combo.currentText()
        args = self.args_edit.text().strip()
        if args:
            args = json.loads(args)
        else:
            args = []
        kwargs = self.kwargs_edit.text().strip()
        if kwargs:
            kwargs = json.loads(kwargs)
        else:
            kwargs = {}

        self.simpv_defs[pvsuffix] = {"pvclass": pvclass}
        if args:
            self.simpv_defs[pvsuffix]["args"] = args
        if kwargs:
            self.simpv_defs[pvsuffix]["kwargs"] = kwargs

        self.accept()  # Close the dialog with success


# ---------------------- Main Execution ---------------------- #


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
