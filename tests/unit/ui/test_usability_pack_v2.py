"""Tests for usability pack items 9–15 and the follow-up extras."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.helpers.processed_media_store import ProcessedMediaStore
from app.ui.widgets import parameter_tab_icons, preferences_dialog
from app.ui.widgets.actions import (
    job_queue_actions,
    list_view_actions,
    shortcut_actions,
)
from app.ui.widgets.settings_layout_data import SETTINGS_LAYOUT_DATA


# ---------------------------------------------------------------- shortcuts
def test_new_default_shortcuts_are_registered_and_conflict_free():
    defaults = {n: s for n, s, _m, _d in shortcut_actions.DEFAULT_MENU_SHORTCUT_SPECS}
    assert defaults["actionEdit_AddToJob"] == "J"
    assert defaults["actionFile_SaveImage"] == "Ctrl+Shift+P"
    assert defaults["actionEdit_Preferences"] == "Ctrl+,"
    assert "J" in shortcut_actions.RESERVED_SHORTCUTS
    resolved, warnings = shortcut_actions.resolve_shortcuts(defaults)
    assert warnings == []
    assert resolved["actionEdit_AddToJob"] == "J"
    assigned = [s for s in resolved.values() if s]
    assert len(assigned) == len(set(assigned))


def test_j_override_and_disable(tmp_path):
    defaults = {n: s for n, s, _m, _d in shortcut_actions.DEFAULT_MENU_SHORTCUT_SPECS}
    resolved, warnings = shortcut_actions.resolve_shortcuts(
        defaults, {"actionEdit_AddToJob": "Ctrl+J"}
    )
    assert resolved["actionEdit_AddToJob"] == "Ctrl+J"
    assert not any("reserved" in w.lower() for w in warnings)

    resolved, _ = shortcut_actions.resolve_shortcuts(
        defaults, {"actionEdit_AddToJob": ""}
    )
    assert resolved["actionEdit_AddToJob"] == ""


def test_shortcut_json_roundtrip(tmp_path):
    path = tmp_path / "shortcuts.json"
    shortcut_actions.save_shortcut_overrides(path, {"actionQuit": "Ctrl+W"})
    assert shortcut_actions.load_shortcut_overrides(path) == {"actionQuit": "Ctrl+W"}
    shortcut_actions.save_shortcut_overrides(path, {})
    assert not path.exists()


def test_other_action_cannot_steal_j():
    defaults = {"actionEdit_AddToJob": "J", "other": "J"}
    resolved, warnings = shortcut_actions.resolve_shortcuts(defaults)
    assert resolved["actionEdit_AddToJob"] == "J"
    assert resolved["other"] == ""
    assert warnings


# ---------------------------------------------------------------- thumbnails / zoom
def test_thumbnail_step_walks_options_and_stops_at_ends():
    options = list_view_actions.TARGET_THUMBNAIL_SIZE_OPTIONS
    assert list_view_actions.step_target_thumbnail_size_label(options[0], -1) == options[0]
    assert (
        list_view_actions.step_target_thumbnail_size_label(options[0], 1) == options[1]
    )
    assert (
        list_view_actions.step_target_thumbnail_size_label(options[-1], 1) == options[-1]
    )
    assert (
        list_view_actions.step_target_thumbnail_size_label("unknown", 1) == options[1]
    )


def test_new_settings_defaults():
    misc = SETTINGS_LAYOUT_DATA["Misc"]
    assert misc["JobSkipProcessedToggle"]["default"] is False
    assert misc["PlainClickClearsTargetSelectionToggle"]["default"] is True
    assert misc["TargetThumbnailCtrlWheelZoomToggle"]["default"] is True
    assert misc["ParametersTabHeaderModeSelection"]["options"] == [
        "Text",
        "Icon + Text",
        "Icon Only",
    ]
    assert misc["FacesDockDefaultAreaSelection"]["default"] == "Bottom"


# ---------------------------------------------------------------- jobs
class _Face:
    def __init__(self, assigned_faces=None, assigned_embeds=None):
        self.assigned_input_faces = dict(assigned_faces or {})
        self.assigned_merged_embeddings = dict(assigned_embeds or {})


class _Button:
    def __init__(self, media_id, path, is_webcam=False):
        self.media_id = media_id
        self.media_path = path
        self.is_webcam = is_webcam


def test_unique_job_name_collision_and_sanitize():
    assert job_queue_actions.unique_job_name([], "clip") == "clip"
    assert job_queue_actions.unique_job_name(["clip"], "clip") == "clip_2"
    assert job_queue_actions.unique_job_name(["clip", "clip_2"], "clip") == "clip_3"
    assert job_queue_actions.unique_job_name(["CLIP"], "clip") == "clip_2"
    assert ":" not in job_queue_actions.sanitize_job_stem('bad:name?*')
    assert job_queue_actions.sanitize_job_stem("   ") == "job"


def test_payload_loaded_keeps_faces_others_do_not():
    base = {
        "target_medias_data": [{"media_id": "a", "media_path": "/a.mp4"}],
        "selected_media_id": "a",
        "target_faces_data": {"f1": {"parameters": {}}},
        "markers": {"10": {}},
        "issue_frames_by_face": {"f1": [1]},
        "dropped_frames": [2],
        "job_marker_pairs": [[0, 10]],
        "selected_target_face_id": "f1",
        "control": {"KeepInputToggle": False},
        "input_faces_data": {"in1": {"media_path": "/in.jpg"}},
        "embeddings_data": {},
        "swap_faces_enabled": True,
    }
    loaded = _Button("a", "/a.mp4")
    other = _Button("b", "/b.mp4")
    loaded_payload = job_queue_actions.build_job_payload_for_target(
        base,
        loaded,
        is_loaded_target=True,
        assigned_input_ids=["in1"],
        assigned_embed_ids=[],
    )
    assert loaded_payload["target_faces_data"]["f1"]["parameters"] == {}
    assert loaded_payload["markers"] == {"10": {}}
    assert loaded_payload["pending_auto_assign"] is False
    assert loaded_payload["selected_media_id"] == "a"
    assert loaded_payload["target_medias_data"] == [
        {"media_id": "a", "media_path": "/a.mp4"}
    ]

    other_payload = job_queue_actions.build_job_payload_for_target(
        base,
        other,
        is_loaded_target=False,
        assigned_input_ids=["in1"],
        assigned_embed_ids=["emb"],
    )
    assert other_payload["target_faces_data"] == {}
    assert other_payload["markers"] == {}
    assert other_payload["pending_auto_assign"] is True
    assert other_payload["pending_assigned_input_faces"] == ["in1"]
    assert other_payload["pending_assigned_merged_embeddings"] == ["emb"]
    assert other_payload["control"]["KeepInputToggle"] is True
    assert other_payload["selected_media_id"] == "b"
    # Must not leak the other target's face crops.
    assert "f1" not in other_payload["target_faces_data"]


def test_iter_file_targets_skips_webcams():
    buttons = [_Button("a", "/a.mp4"), _Button("cam", "0", is_webcam=True)]
    assert [b.media_id for b in job_queue_actions.iter_file_targets(buttons)] == ["a"]


def test_skip_processed_job_helper(tmp_path):
    video = tmp_path / "video.mp4"
    other = tmp_path / "other.mp4"
    video.write_bytes(b"abc")
    other.write_bytes(b"xyz")
    store = ProcessedMediaStore(tmp_path / ".processed_media.json")
    assert store.mark_processed(str(video))
    data = {
        "selected_media_id": "v1",
        "target_medias_data": [{"media_id": "v1", "media_path": str(video)}],
    }
    assert job_queue_actions.should_skip_processed_job(data, store.is_processed, True)
    assert not job_queue_actions.should_skip_processed_job(
        data, store.is_processed, False
    )
    fresh = {
        "selected_media_id": "v2",
        "target_medias_data": [{"media_id": "v2", "media_path": str(other)}],
    }
    assert not job_queue_actions.should_skip_processed_job(
        fresh, store.is_processed, True
    )


def test_job_needs_auto_detect():
    assert job_queue_actions.job_needs_auto_detect({"pending_auto_assign": True})
    assert job_queue_actions.job_needs_auto_detect(
        {"target_faces_data": {}, "pending_assigned_input_faces": ["a"]}
    )
    assert not job_queue_actions.job_needs_auto_detect(
        {"target_faces_data": {"f": {}}, "pending_auto_assign": False}
    )


def test_collect_assigned_source_ids():
    mw = SimpleNamespace(
        target_faces={"t": _Face({"in1": {}}, {"emb1": {}})},
        input_faces={},
        merged_embeddings={},
    )
    inputs, embeds = job_queue_actions.collect_assigned_source_ids(mw)
    assert inputs == ["in1"]
    assert embeds == ["emb1"]


# ---------------------------------------------------------------- Qt UI helpers
@pytest.fixture(scope="module")
def qapp():
    from PySide6 import QtWidgets

    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    return app


def test_parameter_tab_icons_and_modes(qapp, tmp_path):
    from PySide6 import QtWidgets

    window = QtWidgets.QMainWindow()
    tabs = QtWidgets.QTabWidget()
    pages = {}
    for object_name, label, _svg in parameter_tab_icons.PARAMETERS_TAB_SPECS:
        page = QtWidgets.QWidget()
        page.setObjectName(object_name)
        setattr(window, object_name, page)
        tabs.addTab(page, label)
        pages[object_name] = page
    window.tabWidget = tabs
    window.control = {"ParametersTabHeaderModeSelection": "Text"}
    window.parameter_widgets = {}

    parameter_tab_icons.apply_parameters_tab_header_mode(window, "Text")
    assert tabs.tabText(0) == "Face Swap"
    assert tabs.tabIcon(0).isNull()

    parameter_tab_icons.apply_parameters_tab_header_mode(window, "Icon + Text")
    assert tabs.tabText(0) == "Face Swap"
    assert not tabs.tabIcon(0).isNull()
    assert tabs.tabBar().tabToolTip(0) == "Face Swap"

    parameter_tab_icons.apply_parameters_tab_header_mode(window, "Icon Only")
    assert tabs.tabText(0) == ""
    assert not tabs.tabIcon(0).isNull()
    assert tabs.tabBar().tabToolTip(5) == "Presets"
    assert window.control["ParametersTabHeaderModeSelection"] == "Icon Only"


def test_preferences_dialog_roundtrip(qapp, tmp_path, monkeypatch):
    from PySide6 import QtWidgets

    control = {
        "ThemeSelection": "True-Dark",
        "JobSkipProcessedToggle": False,
        "PlainClickClearsTargetSelectionToggle": True,
        "ParametersTabHeaderModeSelection": "Text",
        "OutputMediaFolder": str(tmp_path),
        "nThreadsSlider": 4,
    }
    mw = QtWidgets.QMainWindow()
    mw.control = control
    mw.parameter_widgets = {}
    mw.project_root_path = tmp_path
    mw.applied_menu_shortcuts = {
        name: seq for name, seq, _m, _d in shortcut_actions.DEFAULT_MENU_SHORTCUT_SPECS
    }
    mw.panel_visibility_state = {
        "target_media": True,
        "input_faces": True,
        "jobs": True,
        "faces": True,
        "parameters": True,
    }
    mw._current_panel_visibility = lambda key: mw.panel_visibility_state.get(key, True)
    mw._set_panel_visibility = lambda key, checked: mw.panel_visibility_state.__setitem__(
        key, checked
    )
    mw.outputFolderLineEdit = QtWidgets.QLineEdit()
    mw.tabWidget = QtWidgets.QTabWidget()
    mw.videoSeekSlider = QtWidgets.QSlider()
    mw.markers = {}
    mw.video_processor = None

    dialog = preferences_dialog.PreferencesDialog(mw)
    dialog.show()
    qapp.processEvents()

    # Toggle a setting in the dialog and confirm it lands in control.
    job_skip = dialog._bound_widgets["JobSkipProcessedToggle"]
    job_skip.setChecked(True)
    qapp.processEvents()
    assert mw.control["JobSkipProcessedToggle"] is True

    exported = dialog.export_settings_dict()
    assert exported["control"]["JobSkipProcessedToggle"] is True
    export_path = tmp_path / "prefs.json"
    export_path.write_text(json.dumps(exported))

    mw.control["JobSkipProcessedToggle"] = False
    dialog.apply_settings_dict(json.loads(export_path.read_text()))
    assert mw.control["JobSkipProcessedToggle"] is True
    dialog.close()


def test_dock_helper_constants():
    from app.ui.widgets.actions import layout_actions

    assert layout_actions._DOCK_MIN_SIZE.width() <= 180
    assert "Bottom" in layout_actions._DOCK_AREA_MAP
    assert "Left" in layout_actions._DOCK_AREA_MAP
