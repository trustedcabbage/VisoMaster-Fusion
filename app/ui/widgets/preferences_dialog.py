"""Tabbed Preferences dialog bound to the live ``control`` dict."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6 import QtCore, QtGui, QtWidgets

from app.ui.widgets import parameter_tab_icons
from app.ui.widgets.actions import common_actions, shortcut_actions
from app.ui.widgets.settings_layout_data import SETTINGS_LAYOUT_DATA

if TYPE_CHECKING:
    from app.ui.main_ui import MainWindow

_TAB_KEYS = (
    "General & UI",
    "Appearance & Docks",
    "Target Media",
    "Shortcuts",
    "Job Manager",
    "Performance & GPU",
    "Output & Naming",
    "Backup & Reset",
)


def _flatten_settings() -> dict[str, dict]:
    flat: dict[str, dict] = {}
    for _section, widgets in SETTINGS_LAYOUT_DATA.items():
        if not isinstance(widgets, dict):
            continue
        for name, data in widgets.items():
            if isinstance(data, dict) and "label" in data:
                flat[name] = data
    return flat


class PreferencesDialog(QtWidgets.QDialog):
    def __init__(self, main_window: "MainWindow", parent=None):
        super().__init__(parent or main_window)
        self.main_window = main_window
        self.setWindowTitle("Preferences")
        self.setMinimumSize(720, 560)
        self.resize(820, 640)
        self._setting_defs = _flatten_settings()
        self._updating = False
        self._bound_widgets: dict[str, QtWidgets.QWidget] = {}

        layout = QtWidgets.QVBoxLayout(self)
        self.tabs = QtWidgets.QTabWidget(self)
        layout.addWidget(self.tabs, 1)

        self.tabs.addTab(self._build_general_tab(), "General & UI")
        self.tabs.addTab(self._build_appearance_tab(), "Appearance & Docks")
        self.tabs.addTab(self._build_target_media_tab(), "Target Media")
        self.tabs.addTab(self._build_shortcuts_tab(), "Shortcuts")
        self.tabs.addTab(self._build_job_tab(), "Job Manager")
        self.tabs.addTab(self._build_performance_tab(), "Performance & GPU")
        self.tabs.addTab(self._build_output_tab(), "Output & Naming")
        self.tabs.addTab(self._build_backup_tab(), "Backup & Reset")

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Close
        )
        buttons.rejected.connect(self.accept)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
        self.refresh_from_control()

    # ---------------------------------------------------------------- bind
    def _control_value(self, name: str, default=None):
        control = getattr(self.main_window, "control", {}) or {}
        if name in control:
            return control[name]
        definition = self._setting_defs.get(name, {})
        return definition.get("default", default)

    def _apply_control(self, name: str, value) -> None:
        if self._updating:
            return
        definition = self._setting_defs.get(name, {})
        exec_fn = definition.get("exec_function")
        exec_args = definition.get("exec_function_args") or []
        # Avoid a second refresh_frame/exec if the value is unchanged.
        current = (getattr(self.main_window, "control", {}) or {}).get(name, object())
        if current == value:
            return
        common_actions.update_control(
            self.main_window, name, value, exec_fn, exec_args
        )
        widget = (getattr(self.main_window, "parameter_widgets", {}) or {}).get(name)
        if widget is not None:
            try:
                widget.enable_refresh_frame = False
                common_actions._set_single_widget_value(widget, value)
                widget.enable_refresh_frame = True
            except Exception:
                pass

    def _add_toggle(self, parent_layout, name: str, fallback_label: str = "") -> QtWidgets.QCheckBox:
        definition = self._setting_defs.get(name, {})
        box = QtWidgets.QCheckBox(definition.get("label", fallback_label or name), self)
        if definition.get("help"):
            box.setToolTip(definition["help"])
        box.setChecked(bool(self._control_value(name, False)))
        box.toggled.connect(lambda checked, key=name: self._apply_control(key, bool(checked)))
        parent_layout.addWidget(box)
        self._bound_widgets[name] = box
        return box

    def _add_combo(self, parent_layout, name: str, fallback_label: str = "", options: list | None = None) -> QtWidgets.QComboBox:
        definition = self._setting_defs.get(name, {})
        row = QtWidgets.QHBoxLayout()
        label = QtWidgets.QLabel(definition.get("label", fallback_label or name), self)
        combo = QtWidgets.QComboBox(self)
        choices = options or definition.get("options") or []
        combo.addItems([str(item) for item in choices])
        if definition.get("help"):
            combo.setToolTip(definition["help"])
            label.setToolTip(definition["help"])
        current = str(self._control_value(name, definition.get("default", "")))
        index = combo.findText(current)
        if index >= 0:
            combo.setCurrentIndex(index)
        combo.currentTextChanged.connect(lambda text, key=name: self._apply_control(key, text))
        row.addWidget(label, 1)
        row.addWidget(combo, 1)
        parent_layout.addLayout(row)
        self._bound_widgets[name] = combo
        return combo

    def _add_spin(self, parent_layout, name: str, fallback_label: str = "") -> QtWidgets.QSpinBox:
        definition = self._setting_defs.get(name, {})
        row = QtWidgets.QHBoxLayout()
        label = QtWidgets.QLabel(definition.get("label", fallback_label or name), self)
        spin = QtWidgets.QSpinBox(self)
        try:
            min_value = int(float(definition.get("min_value", definition.get("min", 0))))
        except (TypeError, ValueError):
            min_value = 0
        try:
            max_value = int(float(definition.get("max_value", definition.get("max", 9999))))
        except (TypeError, ValueError):
            max_value = 9999
        spin.setRange(min_value, max_value)
        try:
            spin.setValue(int(float(self._control_value(name, definition.get("default", 0)) or 0)))
        except (TypeError, ValueError):
            spin.setValue(min_value)
        if definition.get("help"):
            spin.setToolTip(definition["help"])
        spin.valueChanged.connect(lambda value, key=name: self._apply_control(key, int(value)))
        row.addWidget(label, 1)
        row.addWidget(spin, 1)
        parent_layout.addLayout(row)
        self._bound_widgets[name] = spin
        return spin

    def _scroll_form(self) -> tuple[QtWidgets.QWidget, QtWidgets.QVBoxLayout]:
        page = QtWidgets.QWidget(self)
        outer = QtWidgets.QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QtWidgets.QScrollArea(page)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        inner = QtWidgets.QWidget(scroll)
        layout = QtWidgets.QVBoxLayout(inner)
        layout.setContentsMargins(12, 12, 12, 12)
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        return page, layout

    # ---------------------------------------------------------------- tabs
    def _build_general_tab(self) -> QtWidgets.QWidget:
        page, layout = self._scroll_form()
        self._add_combo(layout, "ThemeSelection")
        self._add_toggle(layout, "SkipClearConfirmationToggle")
        self._add_toggle(layout, "EnableMediaToastToggle")
        self._add_toggle(layout, "AutoSaveWorkspaceToggle")
        self._add_toggle(layout, "AutoSaveLastWorkspaceToggle")
        self._add_toggle(layout, "AutoLoadWorkspaceToggle")
        self._add_toggle(layout, "SliderMouseWheelControlToggle")
        self._add_toggle(layout, "NonBlockingBatchToggle")
        layout.addStretch(1)
        return page

    def _build_appearance_tab(self) -> QtWidgets.QWidget:
        page, layout = self._scroll_form()
        self._add_combo(layout, "ThemeSelection")
        self._add_combo(layout, "ParametersTabHeaderModeSelection")
        self._add_combo(layout, "FacesDockDefaultAreaSelection")

        layout.addWidget(QtWidgets.QLabel("Dock visibility:", self))
        for key, title in (
            ("target_media", "Target Videos/Images"),
            ("input_faces", "Input Faces"),
            ("jobs", "Job Manager"),
            ("faces", "Faces & Embeddings"),
            ("parameters", "Parameters"),
        ):
            box = QtWidgets.QCheckBox(title, self)
            visible = True
            if hasattr(self.main_window, "_current_panel_visibility"):
                try:
                    visible = bool(self.main_window._current_panel_visibility(key))
                except Exception:
                    visible = True
            box.setChecked(visible)
            box.toggled.connect(
                lambda checked, panel=key: self._set_panel(panel, checked)
            )
            layout.addWidget(box)
            self._bound_widgets[f"dock_visible_{key}"] = box

        reset = QtWidgets.QPushButton("Reset Layout", self)
        reset.setToolTip("Restore the default dock arrangement.")
        reset.clicked.connect(self._reset_layout)
        layout.addWidget(reset)
        layout.addStretch(1)
        return page

    def _build_target_media_tab(self) -> QtWidgets.QWidget:
        page, layout = self._scroll_form()
        self._add_combo(layout, "TargetThumbnailSizeSelection")
        self._add_toggle(layout, "TargetThumbnailCtrlWheelZoomToggle")
        self._add_toggle(layout, "PlainClickClearsTargetSelectionToggle")
        self._add_toggle(layout, "TargetMediaFolderRecursiveToggle")
        self._add_toggle(layout, "InputFacesFolderRecursiveToggle")
        self._add_toggle(layout, "ShowSeekBarThumbnailsToggle")
        scan = QtWidgets.QPushButton("Scan output folder for processed media", self)
        scan.setToolTip("Mark target items that already have outputs with a green tick.")
        scan.clicked.connect(self._scan_processed)
        layout.addWidget(scan)
        layout.addStretch(1)
        return page

    def _build_job_tab(self) -> QtWidgets.QWidget:
        page, layout = self._scroll_form()
        self._add_toggle(layout, "JobSkipProcessedToggle")
        self._add_toggle(layout, "BatchSkipProcessedToggle")
        self._add_toggle(layout, "SkipClearConfirmationToggle")
        self._add_toggle(layout, "AutoSwapToggle")
        self._add_toggle(layout, "KeepInputToggle")
        layout.addStretch(1)
        return page

    def _build_performance_tab(self) -> QtWidgets.QWidget:
        page, layout = self._scroll_form()
        self._add_combo(layout, "ProvidersPrioritySelection")
        self._add_spin(layout, "nThreadsSlider")
        self._add_spin(layout, "nStreamSlider")
        self._add_toggle(layout, "KeepModelsAliveToggle")
        self._add_toggle(layout, "GlobalInputResizeToggle")
        self._add_combo(layout, "GlobalInputResizeSizeSelection")
        self._add_spin(layout, "MaxFacesToDetectSlider")
        layout.addStretch(1)
        return page

    def _build_output_tab(self) -> QtWidgets.QWidget:
        page, layout = self._scroll_form()
        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("Output folder:", self))
        self.output_edit = QtWidgets.QLineEdit(self)
        self.output_edit.setReadOnly(True)
        self.output_edit.setText(str(self._control_value("OutputMediaFolder", "") or ""))
        browse = QtWidgets.QPushButton("Browse…", self)
        browse.clicked.connect(self._browse_output)
        row.addWidget(self.output_edit, 1)
        row.addWidget(browse)
        layout.addLayout(row)
        self._bound_widgets["OutputMediaFolder"] = self.output_edit
        self._add_toggle(layout, "ImageFormatToggle")
        self._add_toggle(layout, "OutputToTargetLocationToggle")
        self._add_toggle(layout, "PreserveOutputDirectoryStructureToggle")
        self._add_toggle(layout, "ClusterOutputBySourceToggle")
        self._add_toggle(layout, "OutputFpsCapEnableToggle")
        self._add_spin(layout, "OutputMaxFpsSlider")
        self._add_toggle(layout, "OpenOutputToggle")
        self._add_toggle(layout, "HDREncodeToggle")
        layout.addStretch(1)
        return page

    def _build_backup_tab(self) -> QtWidgets.QWidget:
        page, layout = self._scroll_form()
        intro = QtWidgets.QLabel(
            "Export or import the current settings and keyboard shortcuts as JSON.",
            self,
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        export_btn = QtWidgets.QPushButton("Export settings + shortcuts…", self)
        export_btn.clicked.connect(self._export_json)
        import_btn = QtWidgets.QPushButton("Import settings + shortcuts…", self)
        import_btn.clicked.connect(self._import_json)
        reset_btn = QtWidgets.QPushButton("Reset settings to defaults", self)
        reset_btn.clicked.connect(self._reset_defaults)
        layout.addWidget(export_btn)
        layout.addWidget(import_btn)
        layout.addWidget(reset_btn)
        layout.addStretch(1)
        return page

    def _build_shortcuts_tab(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget(self)
        layout = QtWidgets.QVBoxLayout(page)
        self.shortcut_table = QtWidgets.QTableWidget(0, 3, self)
        self.shortcut_table.setHorizontalHeaderLabels(["Action", "Description", "Shortcut"])
        self.shortcut_table.horizontalHeader().setSectionResizeMode(
            0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
        )
        self.shortcut_table.horizontalHeader().setSectionResizeMode(
            1, QtWidgets.QHeaderView.ResizeMode.Stretch
        )
        self.shortcut_table.horizontalHeader().setSectionResizeMode(
            2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
        )
        self.shortcut_table.verticalHeader().setVisible(False)
        self.shortcut_table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        layout.addWidget(self.shortcut_table, 1)
        self._shortcut_editors: dict[str, QtWidgets.QKeySequenceEdit] = {}
        self._populate_shortcut_table()
        row = QtWidgets.QHBoxLayout()
        reset_one = QtWidgets.QPushButton("Reset Selected", self)
        reset_all = QtWidgets.QPushButton("Reset All", self)
        reset_one.clicked.connect(self._reset_selected_shortcut)
        reset_all.clicked.connect(self._reset_all_shortcuts)
        row.addWidget(reset_one)
        row.addWidget(reset_all)
        row.addStretch(1)
        layout.addLayout(row)
        self.shortcut_status = QtWidgets.QLabel(self)
        self.shortcut_status.setWordWrap(True)
        layout.addWidget(self.shortcut_status)
        return page

    # ---------------------------------------------------------------- shortcuts
    def _populate_shortcut_table(self) -> None:
        self.shortcut_table.setRowCount(0)
        self._shortcut_editors.clear()
        applied = getattr(self.main_window, "applied_menu_shortcuts", {}) or {}
        defaults = {
            name: seq for name, seq, _menu, _desc in shortcut_actions.DEFAULT_MENU_SHORTCUT_SPECS
        }
        for name, default, menu, desc in shortcut_actions.DEFAULT_MENU_SHORTCUT_SPECS:
            row = self.shortcut_table.rowCount()
            self.shortcut_table.insertRow(row)
            label = QtWidgets.QTableWidgetItem(name)
            label.setFlags(label.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            desc_item = QtWidgets.QTableWidgetItem(f"{menu}: {desc}")
            desc_item.setFlags(desc_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            self.shortcut_table.setItem(row, 0, label)
            self.shortcut_table.setItem(row, 1, desc_item)
            editor = QtWidgets.QKeySequenceEdit(self)
            seq = applied.get(name, default)
            if seq:
                editor.setKeySequence(QtGui.QKeySequence(seq))
            editor.editingFinished.connect(
                lambda action=name, widget=editor: self._on_shortcut_edited(action, widget)
            )
            self.shortcut_table.setCellWidget(row, 2, editor)
            self._shortcut_editors[name] = editor

    def _collect_editor_overrides(self) -> dict[str, str]:
        overrides: dict[str, str] = {}
        defaults = {
            name: seq for name, seq, _m, _d in shortcut_actions.DEFAULT_MENU_SHORTCUT_SPECS
        }
        for name, editor in self._shortcut_editors.items():
            seq = shortcut_actions.normalize_sequence(
                editor.keySequence().toString(QtGui.QKeySequence.SequenceFormat.PortableText)
            )
            if seq != shortcut_actions.normalize_sequence(defaults.get(name, "")):
                overrides[name] = seq
        return overrides

    def _on_shortcut_edited(self, action: str, editor: QtWidgets.QKeySequenceEdit) -> None:
        overrides = self._collect_editor_overrides()
        defaults = {
            name: seq for name, seq, _m, _d in shortcut_actions.DEFAULT_MENU_SHORTCUT_SPECS
        }
        _resolved, warnings = shortcut_actions.resolve_shortcuts(defaults, overrides)
        reserved_hits = [w for w in warnings if "reserved" in w.lower() and action in w]
        if reserved_hits:
            self.shortcut_status.setText(reserved_hits[0])
            # Revert the offending editor to the last applied/default value.
            applied = getattr(self.main_window, "applied_menu_shortcuts", {}) or {}
            fallback = applied.get(action, defaults.get(action, ""))
            editor.blockSignals(True)
            editor.setKeySequence(QtGui.QKeySequence(fallback) if fallback else QtGui.QKeySequence())
            editor.blockSignals(False)
            return
        self._save_and_apply_shortcuts(overrides, warnings)

    def _save_and_apply_shortcuts(self, overrides: dict[str, str], warnings: list[str] | None = None) -> None:
        root = Path(getattr(self.main_window, "project_root_path", Path.cwd()))
        path = root / shortcut_actions.SHORTCUTS_OVERRIDE_FILENAME
        try:
            shortcut_actions.save_shortcut_overrides(path, overrides)
        except OSError as exc:
            self.shortcut_status.setText(f"Could not write {path}: {exc}")
            return
        applied = shortcut_actions.apply_menu_shortcuts(self.main_window)
        self.shortcut_status.setText(
            "; ".join(warnings) if warnings else f"Saved {len(applied)} shortcuts."
        )

    def _reset_selected_shortcut(self) -> None:
        rows = {index.row() for index in self.shortcut_table.selectedIndexes()}
        defaults = {
            name: seq for name, seq, _m, _d in shortcut_actions.DEFAULT_MENU_SHORTCUT_SPECS
        }
        names = list(self._shortcut_editors)
        for row in rows:
            if 0 <= row < len(names):
                name = names[row]
                editor = self._shortcut_editors[name]
                editor.blockSignals(True)
                editor.setKeySequence(QtGui.QKeySequence(defaults.get(name, "")))
                editor.blockSignals(False)
        self._save_and_apply_shortcuts(self._collect_editor_overrides())

    def _reset_all_shortcuts(self) -> None:
        defaults = {
            name: seq for name, seq, _m, _d in shortcut_actions.DEFAULT_MENU_SHORTCUT_SPECS
        }
        for name, editor in self._shortcut_editors.items():
            editor.blockSignals(True)
            editor.setKeySequence(QtGui.QKeySequence(defaults.get(name, "")))
            editor.blockSignals(False)
        self._save_and_apply_shortcuts({})

    # ---------------------------------------------------------------- actions
    def _set_panel(self, key: str, checked: bool) -> None:
        setter = getattr(self.main_window, "_set_panel_visibility", None)
        if setter:
            setter(key, checked)

    def _reset_layout(self) -> None:
        from app.ui.widgets.actions import layout_actions

        layout_actions.reset_dock_layout(self.main_window)
        self.refresh_from_control()

    def _scan_processed(self) -> None:
        from app.ui.widgets.actions import target_media_actions

        target_media_actions.scan_output_folder_for_processed(self.main_window)

    def _browse_output(self) -> None:
        folder = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select Output Folder", self.output_edit.text() or ""
        )
        if not folder:
            return
        self.output_edit.setText(folder)
        self._apply_control("OutputMediaFolder", folder)
        line = getattr(self.main_window, "outputFolderLineEdit", None)
        if line is not None:
            line.setText(folder)

    def export_settings_dict(self) -> dict:
        control = dict(getattr(self.main_window, "control", {}) or {})
        root = Path(getattr(self.main_window, "project_root_path", Path.cwd()))
        shortcuts = shortcut_actions.load_shortcut_overrides(
            root / shortcut_actions.SHORTCUTS_OVERRIDE_FILENAME
        )
        return {"control": control, "shortcuts": shortcuts}

    def apply_settings_dict(self, data: dict) -> None:
        control = data.get("control") or {}
        if isinstance(control, dict):
            self.main_window.control.update(control)
            common_actions.set_control_widgets_values(self.main_window, enable_exec_func=True)
        shortcuts = data.get("shortcuts")
        if isinstance(shortcuts, dict):
            root = Path(getattr(self.main_window, "project_root_path", Path.cwd()))
            shortcut_actions.save_shortcut_overrides(
                root / shortcut_actions.SHORTCUTS_OVERRIDE_FILENAME, shortcuts
            )
            shortcut_actions.apply_menu_shortcuts(self.main_window)
        parameter_tab_icons.apply_parameters_tab_header_mode(self.main_window)
        self.refresh_from_control()

    def _export_json(self) -> None:
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export Settings", "visomaster-preferences.json", "JSON (*.json)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(self.export_settings_dict(), handle, indent=2)
        except OSError as exc:
            QtWidgets.QMessageBox.warning(self, "Export Failed", str(exc))

    def _import_json(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Import Settings", "", "JSON (*.json)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError) as exc:
            QtWidgets.QMessageBox.warning(self, "Import Failed", str(exc))
            return
        if not isinstance(data, dict):
            QtWidgets.QMessageBox.warning(self, "Import Failed", "File must contain a JSON object.")
            return
        self.apply_settings_dict(data)

    def _reset_defaults(self) -> None:
        reply = QtWidgets.QMessageBox.question(
            self,
            "Reset Settings",
            "Reset all settings to their default values? Shortcuts are not changed.",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if reply != QtWidgets.QMessageBox.Yes:
            return
        defaults = {
            name: data.get("default")
            for name, data in self._setting_defs.items()
            if "default" in data
        }
        self.main_window.control.update(defaults)
        common_actions.set_control_widgets_values(self.main_window, enable_exec_func=True)
        parameter_tab_icons.apply_parameters_tab_header_mode(self.main_window)
        self.refresh_from_control()

    def refresh_from_control(self) -> None:
        """Pull live ``control`` / panel visibility into the dialog widgets."""
        self._updating = True
        try:
            for name, widget in self._bound_widgets.items():
                if name.startswith("dock_visible_"):
                    key = name.split("dock_visible_", 1)[1]
                    if hasattr(self.main_window, "_current_panel_visibility"):
                        try:
                            widget.setChecked(
                                bool(self.main_window._current_panel_visibility(key))
                            )
                        except Exception:
                            pass
                    continue
                value = self._control_value(name)
                if isinstance(widget, QtWidgets.QCheckBox):
                    widget.setChecked(bool(value))
                elif isinstance(widget, QtWidgets.QComboBox):
                    index = widget.findText(str(value))
                    if index >= 0:
                        widget.setCurrentIndex(index)
                elif isinstance(widget, QtWidgets.QSpinBox):
                    try:
                        widget.setValue(int(value))
                    except (TypeError, ValueError):
                        pass
                elif isinstance(widget, QtWidgets.QLineEdit):
                    widget.setText(str(value or ""))
            if hasattr(self, "_shortcut_editors"):
                applied = getattr(self.main_window, "applied_menu_shortcuts", {}) or {}
                defaults = {
                    n: s for n, s, _m, _d in shortcut_actions.DEFAULT_MENU_SHORTCUT_SPECS
                }
                for name, editor in self._shortcut_editors.items():
                    seq = applied.get(name, defaults.get(name, ""))
                    editor.blockSignals(True)
                    editor.setKeySequence(QtGui.QKeySequence(seq) if seq else QtGui.QKeySequence())
                    editor.blockSignals(False)
        finally:
            self._updating = False


def open_preferences_dialog(main_window: "MainWindow") -> PreferencesDialog:
    dialog = PreferencesDialog(main_window, main_window)
    dialog.exec()
    return dialog
