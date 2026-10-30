"""Shortcuts, thumbnail-size presets and job-list clearing."""

from pathlib import Path

from app.ui.widgets.actions import (
    job_manager_actions,
    list_view_actions,
    shortcut_actions,
)


# ------------------------------------------------------------- shortcuts
def test_default_shortcuts_have_no_conflicts():
    defaults = {n: s for n, s, _m, _d in shortcut_actions.DEFAULT_MENU_SHORTCUT_SPECS}
    resolved, warnings = shortcut_actions.resolve_shortcuts(defaults)
    assert warnings == []
    assigned = [s for s in resolved.values() if s]
    assert len(assigned) == len(set(assigned)) == len(defaults)


def test_override_wins_and_conflicting_default_is_dropped():
    defaults = {"a": "Ctrl+S", "b": "Ctrl+O"}
    resolved, warnings = shortcut_actions.resolve_shortcuts(
        defaults, {"b": "Ctrl+S", "nope": "Ctrl+K"}
    )
    assert resolved == {"a": "", "b": "Ctrl+S"}
    assert any("nope" in w for w in warnings)
    assert any("already used" in w for w in warnings)


def test_reserved_and_empty_overrides():
    resolved, warnings = shortcut_actions.resolve_shortcuts(
        {"a": "Ctrl+S", "b": "Ctrl+O"}, {"a": "Space", "b": ""}
    )
    assert resolved == {"a": "", "b": ""}
    assert any("reserved" in w for w in warnings)


def test_load_shortcut_overrides(tmp_path):
    assert shortcut_actions.load_shortcut_overrides(tmp_path / "none.json") == {}
    bad = tmp_path / "bad.json"
    bad.write_text("[1, 2]")
    assert shortcut_actions.load_shortcut_overrides(bad) == {}
    good = tmp_path / "good.json"
    good.write_text('{"actionQuit": "Ctrl+W", "actionSave_CurrentWorkspace": null}')
    assert shortcut_actions.load_shortcut_overrides(good) == {
        "actionQuit": "Ctrl+W",
        "actionSave_CurrentWorkspace": "",
    }


# ------------------------------------------------------- thumbnail size
def test_thumbnail_size_parsing():
    parse = list_view_actions.parse_target_thumbnail_size
    assert parse(None) is None
    assert parse(list_view_actions.TARGET_THUMBNAIL_SIZE_DEFAULT) is None
    assert parse("640x360") == (640, 360)
    assert parse("1280x720") == (1280, 720)
    assert parse("4000x3000") == (1280, 720)  # capped
    assert parse("garbage") is None


def test_button_size_grows_with_preset():
    size_for = list_view_actions.target_button_size_for
    assert size_for(None) == (96, 96)
    width, height = size_for("1280x720")
    assert width >= 1280 and height >= 720


def test_settings_options_match_presets():
    # Imported here: settings_layout_data must load after the action modules.
    from app.ui.widgets import settings_layout_data

    misc = settings_layout_data.SETTINGS_LAYOUT_DATA["Misc"]
    entry = misc["TargetThumbnailSizeSelection"]
    assert entry["options"] == list_view_actions.TARGET_THUMBNAIL_SIZE_OPTIONS
    assert entry["default"] == list_view_actions.TARGET_THUMBNAIL_SIZE_DEFAULT
    assert misc["NonBlockingBatchToggle"]["default"] is True
    assert misc["BatchSkipProcessedToggle"]["default"] is False


def test_thumbnail_manager_per_size(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    class _MW:
        control = {"TargetThumbnailSizeSelection": "640x360"}  # noqa: RUF012
        thumbnail_manager = object()

    mw = _MW()
    manager, scale = list_view_actions.get_target_thumbnail_request(mw)
    assert scale == (640, 360)
    assert (manager.max_width, manager.max_height) == (640, 360)
    assert Path(manager.thumbnail_dir) == tmp_path / ".thumbnails" / "640x360"
    again, _ = list_view_actions.get_target_thumbnail_request(mw)
    assert again is manager
    default_manager, default_scale = list_view_actions.get_target_thumbnail_request(
        mw, list_view_actions.TARGET_THUMBNAIL_SIZE_DEFAULT
    )
    assert default_manager is mw.thumbnail_manager
    assert default_scale == (70, 70)


# ------------------------------------------------------------ job clear
def test_trash_job_files(tmp_path):
    (tmp_path / "a.json").write_text("{}")
    (tmp_path / "b.json").write_text("{}")
    (tmp_path / "keep.txt").write_text("x")
    trashed = []

    def fake_trash(path):
        if path.endswith("b.json"):
            raise OSError("locked")
        trashed.append(Path(path).name)

    moved, failures = job_manager_actions.trash_job_files(tmp_path, trash=fake_trash)
    assert moved == 1 and trashed == ["a.json"]
    assert failures == ["b: locked"]
    assert job_manager_actions.trash_job_files(tmp_path / "missing") == (0, [])


def _clear_jobs_window(tmp_path, skip_confirm):
    class _List:
        def count(self):
            return 2

    class _MW:
        control = {"SkipClearConfirmationToggle": skip_confirm}  # noqa: RUF012
        job_processor = None
        jobQueueList = _List()

    return _MW()


def test_clear_job_list_respects_confirmation(tmp_path, monkeypatch):
    jobs = tmp_path / "jobs"
    jobs.mkdir()
    (jobs / "a.json").write_text("{}")
    monkeypatch.setattr(job_manager_actions, "get_jobs_dir", lambda mw: jobs)
    monkeypatch.setattr(job_manager_actions, "refresh_job_list", lambda mw: None)
    monkeypatch.setattr(
        job_manager_actions.common_widget_actions,
        "create_and_show_toast_message",
        lambda *a, **k: None,
    )
    trashed = []
    monkeypatch.setattr(job_manager_actions, "send2trash", trashed.append)
    asked = []
    monkeypatch.setattr(
        job_manager_actions.QMessageBox,
        "question",
        lambda *a, **k: asked.append(a) or job_manager_actions.QMessageBox.No,
    )
    # Defaults are bound at definition time, so route trash_job_files to the patch.
    real = job_manager_actions.trash_job_files
    monkeypatch.setattr(
        job_manager_actions,
        "trash_job_files",
        lambda d: real(d, trash=trashed.append),
    )

    assert (
        job_manager_actions.clear_job_list(_clear_jobs_window(tmp_path, False)) is False
    )
    assert len(asked) == 1 and trashed == []

    assert (
        job_manager_actions.clear_job_list(_clear_jobs_window(tmp_path, True)) is True
    )
    assert len(asked) == 1  # no prompt when warnings are turned off
    assert [Path(p).name for p in trashed] == ["a.json"]


def test_clear_job_list_blocked_while_queue_runs(tmp_path, monkeypatch):
    mw = _clear_jobs_window(tmp_path, True)
    monkeypatch.setattr(
        job_manager_actions, "_is_job_processor_running", lambda m: True
    )
    warned = []
    monkeypatch.setattr(
        job_manager_actions.QMessageBox, "warning", lambda *a, **k: warned.append(a)
    )
    assert job_manager_actions.clear_job_list(mw) is False
    assert warned
