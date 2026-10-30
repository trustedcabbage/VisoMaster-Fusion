"""Keyboard shortcuts for the main window's menu actions.

Every menu action gets a default shortcut from ``DEFAULT_MENU_SHORTCUTS``.
Users can override or disable them with a ``shortcuts.json`` file in the
project root, e.g. ``{"actionSave_CurrentWorkspace": "Ctrl+Alt+S",
"actionQuit": ""}`` (an empty string removes the shortcut).

The single-key hotkeys handled in ``MainWindow.keyPressEvent`` (Space, R, S,
A/D, ...) are reserved, so menu shortcuts never shadow playback controls.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6 import QtCore, QtGui

if TYPE_CHECKING:
    from app.ui.main_ui import MainWindow

SHORTCUTS_OVERRIDE_FILENAME = "shortcuts.json"

# Keys consumed by MainWindow.keyPressEvent or set elsewhere outside the menus.
RESERVED_SHORTCUTS: dict[str, str] = {
    "Esc": "Leave fullscreen / theatre mode",
    "F11": "Fullscreen",
    "T": "Theatre mode",
    "V": "Advance 1 frame",
    "C": "Rewind 1 frame",
    "D": "Advance frames by slider value",
    "A": "Rewind frames by slider value",
    "Z": "Seek to start",
    "Space": "Play / stop",
    "R": "Record start / stop",
    "F": "Add video marker",
    "Alt+F": "Remove video marker",
    "W": "Next marker",
    "Q": "Previous marker",
    "S": "Swap faces",
}

# (attribute name on MainWindow, default shortcut, menu, description)
DEFAULT_MENU_SHORTCUT_SPECS: tuple[tuple[str, str, str, str], ...] = (
    # File
    ("actionLoad_SavedWorkspace", "Ctrl+O", "File", "Load saved workspace"),
    ("actionReset_to_LastWorkspace", "Ctrl+Shift+O", "File", "Reset to last workspace"),
    ("actionSave_LastWorkspace", "Ctrl+Shift+S", "File", "Save as last workspace"),
    ("actionSave_CurrentWorkspace", "Ctrl+S", "File", "Save current workspace"),
    ("actionOpen_Videos_Folder", "Ctrl+Shift+M", "File", "Load target media folder"),
    ("actionOpen_Video_Files", "Ctrl+M", "File", "Load target media files"),
    (
        "actionLoad_Source_Images_Folder",
        "Ctrl+Shift+I",
        "File",
        "Load input faces folder",
    ),
    ("actionLoad_Source_Image_Files", "Ctrl+I", "File", "Load input face files"),
    (
        "actionOpen_Target_Media_Folder",
        "Ctrl+Alt+M",
        "File",
        "Open target media folder",
    ),
    ("actionOpen_Input_Faces_Folder", "Ctrl+Alt+I", "File", "Open input faces folder"),
    ("actionOpen_Output_Folder", "Ctrl+Alt+O", "File", "Open output folder"),
    ("actionLoad_Embeddings", "Ctrl+E", "File", "Load embeddings"),
    ("actionSave_Embeddings", "Ctrl+Alt+E", "File", "Save embeddings"),
    ("actionSave_Embeddings_As", "Ctrl+Shift+E", "File", "Save embeddings as"),
    ("actionQuit_WithoutSaving", "Ctrl+Shift+Q", "File", "Quit without saving"),
    ("actionQuit", "Ctrl+Q", "File", "Quit"),
    # Edit
    (
        "actionEdit_CopyParameters",
        "Ctrl+Shift+C",
        "Edit",
        "Copy parameters from selected face",
    ),
    (
        "actionEdit_PasteParameters",
        "Ctrl+Shift+V",
        "Edit",
        "Paste parameters to selected face",
    ),
    (
        "actionEdit_ResetParameters",
        "Ctrl+Alt+R",
        "Edit",
        "Reset selected face parameters",
    ),
    (
        "actionEdit_SelectAllTargetMedia",
        "Ctrl+Shift+A",
        "Edit",
        "Select all target media",
    ),
    (
        "actionEdit_ClearTargetMediaSelection",
        "Ctrl+Shift+D",
        "Edit",
        "Clear target media selection",
    ),
    (
        "actionEdit_ScanProcessedMedia",
        "Ctrl+Alt+P",
        "Edit",
        "Mark processed media from output folder",
    ),
    ("actionEdit_ClearJobList", "Ctrl+Shift+Del", "Edit", "Clear job list"),
    # View
    (
        "actionViewToggle_target_media",
        "Alt+1",
        "View",
        "Show/hide Target Videos/Images",
    ),
    ("actionViewToggle_input_faces", "Alt+2", "View", "Show/hide Input Faces"),
    ("actionViewToggle_jobs", "Alt+3", "View", "Show/hide Job Manager"),
    ("actionViewToggle_faces", "Alt+4", "View", "Show/hide Faces / Embeddings"),
    ("actionViewToggle_parameters", "Alt+5", "View", "Show/hide Parameters"),
    ("actionView_FitToView", "Ctrl+0", "View", "Fit to view"),
    ("actionView_100Zoom", "Ctrl+1", "View", "100% zoom"),
    ("actionView_FaceCompare", "X", "View", "Face compare"),
    # Help
    ("actionHelp_QuickStartGuide", "F1", "Help", "Quick start guide"),
    ("actionHelp_UserManual", "Shift+F1", "Help", "User manual"),
    ("actionView_Help_Shortcuts", "Ctrl+F1", "Help", "View shortcuts"),
    ("actionView_Help_Presets", "Ctrl+Shift+F1", "Help", "View presets help"),
    ("actionHelp_About", "Alt+F1", "Help", "About"),
)

# Mask-view actions are generated at runtime; they get Ctrl+Alt+<n> by position.
MASK_ACTION_SHORTCUT_TEMPLATE = "Ctrl+Alt+{index}"


def normalize_sequence(sequence: str) -> str:
    """Canonical portable text for a key sequence ('' when empty/invalid)."""
    if not sequence:
        return ""
    return QtGui.QKeySequence(sequence).toString(
        QtGui.QKeySequence.SequenceFormat.PortableText
    )


def load_shortcut_overrides(path: str | Path) -> dict[str, str]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        print(f"[WARN] Shortcuts: could not read {path}: {exc}")
        return {}
    if not isinstance(data, dict):
        print(f"[WARN] Shortcuts: {path} must contain a JSON object.")
        return {}
    return {str(k): str(v or "") for k, v in data.items()}


def resolve_shortcuts(
    defaults: Mapping[str, str],
    overrides: Mapping[str, str] | None = None,
    reserved: Iterable[str] = RESERVED_SHORTCUTS,
) -> tuple[dict[str, str], list[str]]:
    """Merge defaults with overrides and drop conflicting assignments.

    Returns ``(action -> normalized sequence, warnings)``. A sequence used by a
    reserved hotkey or by an earlier action is dropped from the later action.
    Overrides are applied first so a user's choice wins over a default.
    """
    overrides = dict(overrides or {})
    warnings: list[str] = []
    reserved_norm = {normalize_sequence(k) for k in reserved}

    unknown = sorted(set(overrides) - set(defaults))
    for name in unknown:
        warnings.append(f"Unknown action in shortcut overrides: {name}")

    merged = {name: overrides.get(name, seq) for name, seq in defaults.items()}
    order = [n for n in defaults if n in overrides] + [
        n for n in defaults if n not in overrides
    ]

    used: dict[str, str] = {}
    result: dict[str, str] = {}
    for name in order:
        seq = normalize_sequence(merged[name])
        if not seq:
            result[name] = ""
            continue
        if seq in reserved_norm:
            warnings.append(f"{name}: '{seq}' is a reserved hotkey; shortcut removed.")
            result[name] = ""
            continue
        if seq in used:
            warnings.append(
                f"{name}: '{seq}' is already used by {used[seq]}; shortcut removed."
            )
            result[name] = ""
            continue
        used[seq] = name
        result[name] = seq
    return {name: result[name] for name in defaults}, warnings


def _collect_default_shortcuts(main_window: MainWindow) -> dict[str, str]:
    defaults = {name: seq for name, seq, _menu, _desc in DEFAULT_MENU_SHORTCUT_SPECS}
    mask_actions = getattr(main_window, "_view_mask_actions", {}) or {}
    for index, option in enumerate(mask_actions, start=1):
        if index > 9:
            break
        defaults[f"mask:{option}"] = MASK_ACTION_SHORTCUT_TEMPLATE.format(index=index)
    return defaults


def _find_action(main_window: MainWindow, name: str) -> QtGui.QAction | None:
    if name.startswith("mask:"):
        return (getattr(main_window, "_view_mask_actions", {}) or {}).get(name[5:])
    action = getattr(main_window, name, None)
    return action if isinstance(action, QtGui.QAction) else None


def apply_menu_shortcuts(main_window: MainWindow) -> dict[str, str]:
    """Assign shortcuts to all menu actions. Returns the applied mapping."""
    project_root = Path(getattr(main_window, "project_root_path", Path.cwd()))
    overrides = load_shortcut_overrides(project_root / SHORTCUTS_OVERRIDE_FILENAME)
    resolved, warnings = resolve_shortcuts(
        _collect_default_shortcuts(main_window), overrides
    )
    for warning in warnings:
        print(f"[WARN] Shortcuts: {warning}")

    applied: dict[str, str] = {}
    for name, seq in resolved.items():
        action = _find_action(main_window, name)
        if action is None:
            continue
        action.setShortcut(QtGui.QKeySequence(seq) if seq else QtGui.QKeySequence())
        action.setShortcutContext(QtCore.Qt.ShortcutContext.WindowShortcut)
        action.setShortcutVisibleInContextMenu(True)
        # Make sure the shortcut fires even if its menu was never opened.
        if action not in main_window.actions():
            main_window.addAction(action)
        applied[name] = seq
    main_window.applied_menu_shortcuts = applied
    return applied


def build_shortcuts_table_html(main_window: MainWindow) -> str:
    """HTML table of the active menu shortcuts for the Help > Shortcuts dialog."""
    applied = getattr(main_window, "applied_menu_shortcuts", {}) or {}
    descriptions = {
        name: (menu, desc) for name, _s, menu, desc in DEFAULT_MENU_SHORTCUT_SPECS
    }
    rows: list[str] = []
    current_menu = None
    for name, seq in applied.items():
        if not seq:
            continue
        if name.startswith("mask:"):
            action = _find_action(main_window, name)
            menu = "View"
            desc = action.text().replace("&", "") if action else name[5:]
        else:
            menu, desc = descriptions.get(name, ("Other", name))
        if menu != current_menu:
            rows.append(f"<br><b><u>{menu} menu:</u></b><br>")
            current_menu = menu
        rows.append(f"<b>{seq}</b> : {desc}<br>")
    rows.append(
        f"<br><i>Customize in {SHORTCUTS_OVERRIDE_FILENAME} in the app folder, "
        'e.g. {"actionQuit": "Ctrl+W"}.</i><br>'
    )
    return "".join(rows)
