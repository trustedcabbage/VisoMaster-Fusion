"""Target media list: multi-selection, context menu, processed ticks, live
thumbnail resizing and the UI lock used by non-blocking batch runs."""

from __future__ import annotations

import datetime
import os
from collections.abc import Iterable
from functools import partial
from typing import TYPE_CHECKING

from PySide6 import QtCore, QtGui, QtWidgets

from app.helpers.processed_media_store import (
    ProcessedMediaStore,
    match_outputs_to_sources,
    normalize_media_key,
)

if TYPE_CHECKING:
    from app.ui.main_ui import MainWindow
    from app.ui.widgets.widget_components import TargetMediaCardButton

PROCESSED_STORE_FILENAME = ".processed_media.json"
_MAX_OPEN_IN_PLAYER = 10

# Widgets that would corrupt a running batch if used. Everything else (lists,
# parameters, settings, menus) stays interactive while a batch runs.
BATCH_CONFLICTING_WIDGETS = (
    "buttonMediaPlay",
    "buttonMediaRecord",
    "saveImageButton",
    "batchImageButton",
    "batchallImageButton",
    "findTargetFacesButton",
    "clearTargetFacesButton",
    "swapfacesButton",
    "editFacesButton",
    "videoSeekSlider",
    "frameAdvanceButton",
    "frameRewindButton",
    "buttonProcessAll",
    "buttonProcessSelected",
    "loadJobButton",
    "deleteJobButton",
    "inputFacesList",
    "inputEmbeddingsList",
    "targetFacesList",
    "buttonTargetVideosPath",
    "buttonInputFacesPath",
)


# ---------------------------------------------------------------- helpers
def iter_target_buttons(main_window: MainWindow) -> Iterable[TargetMediaCardButton]:
    from app.ui.widgets.widget_components import TargetMediaCardButton

    list_widget = main_window.targetVideosList
    for row in range(list_widget.count()):
        button = list_widget.itemWidget(list_widget.item(row))
        if isinstance(button, TargetMediaCardButton):
            yield button


def _is_batch_running(main_window: MainWindow) -> bool:
    return bool(getattr(main_window, "is_batch_processing", False))


def _selection_ids(main_window: MainWindow) -> set:
    selection = getattr(main_window, "target_media_multi_selection", None)
    if selection is None:
        selection = set()
        main_window.target_media_multi_selection = selection
    return selection


# ------------------------------------------------------- processed store
def get_processed_store(main_window: MainWindow) -> ProcessedMediaStore:
    store = getattr(main_window, "processed_media_store", None)
    if store is None:
        root = getattr(main_window, "project_root_path", None) or os.getcwd()
        store = ProcessedMediaStore(os.path.join(str(root), PROCESSED_STORE_FILENAME))
        main_window.processed_media_store = store
    return store


def refresh_processed_badges(main_window: MainWindow) -> None:
    store = get_processed_store(main_window)
    for button in iter_target_buttons(main_window):
        if not button.is_webcam:
            button.set_processed(store.is_processed(button.media_path))


def _set_badge_for_path(main_window: MainWindow, media_path: str, value: bool):
    key = normalize_media_key(media_path)
    for button in iter_target_buttons(main_window):
        if normalize_media_key(button.media_path) == key:
            button.set_processed(value)


def mark_media_processed(
    main_window: MainWindow, media_path: str, output_path: str | None = None
) -> None:
    if not media_path:
        return
    try:
        get_processed_store(main_window).mark_processed(media_path, output_path)
    except OSError as exc:
        print(f"[WARN] Could not record processed media '{media_path}': {exc}")
        return
    _set_badge_for_path(main_window, media_path, True)


def on_output_saved(main_window: MainWindow, media_path: str, output_path: str):
    mark_media_processed(main_window, media_path, output_path)


def set_processed_for_buttons(main_window, buttons, processed: bool) -> None:
    store = get_processed_store(main_window)
    for button in buttons:
        if button.is_webcam:
            continue
        if processed:
            store.mark_processed(button.media_path)
        else:
            store.unmark(button.media_path)
        button.set_processed(processed)


def scan_output_folder_for_processed(main_window: MainWindow) -> int:
    """Mark target media that already has `<stem>_<timestamp>.<ext>` files in the
    output folder. Returns how many items were newly marked."""
    output_folder = str(main_window.control.get("OutputMediaFolder", "") or "")
    if not output_folder or not os.path.isdir(output_folder):
        QtWidgets.QMessageBox.information(
            main_window,
            "Scan Output Folder",
            "Set an existing Output folder in Settings first.",
        )
        return 0
    output_files = []
    for _dirpath, _dirs, files in os.walk(output_folder):
        output_files.extend(os.path.join(_dirpath, name) for name in files)
    buttons = [b for b in iter_target_buttons(main_window) if not b.is_webcam]
    matches = match_outputs_to_sources([b.media_path for b in buttons], output_files)
    store = get_processed_store(main_window)
    newly_marked = 0
    for source, outputs in matches.items():
        if not store.is_processed(source):
            newly_marked += 1
        for output in outputs:
            store.mark_processed(source, output)
    refresh_processed_badges(main_window)
    QtWidgets.QMessageBox.information(
        main_window,
        "Scan Output Folder",
        f"Found outputs for {len(matches)} target item(s); {newly_marked} newly marked as processed.",
    )
    return newly_marked


# -------------------------------------------------------- multi-selection
def get_selected_buttons(main_window: MainWindow) -> list:
    ids = _selection_ids(main_window)
    return [b for b in iter_target_buttons(main_window) if b.media_id in ids]


def sync_selection_visuals(main_window: MainWindow) -> None:
    ids = _selection_ids(main_window)
    present = set()
    for button in iter_target_buttons(main_window):
        present.add(button.media_id)
        selected = button.media_id in ids
        if button.is_multi_selected != selected:
            button.set_multi_selected(selected)
    ids.intersection_update(present)


def handle_target_media_modifier_click(
    main_window: MainWindow, button, shift: bool = False
) -> None:
    ids = _selection_ids(main_window)
    # Starting a multi-selection includes the media that is currently loaded.
    current = getattr(main_window, "selected_video_button", None)
    if not ids and current and current is not button:
        try:
            ids.add(current.media_id)
        except RuntimeError:
            pass

    buttons = list(iter_target_buttons(main_window))
    anchor_id = getattr(main_window, "_target_media_selection_anchor", None)
    anchor_row = next(
        (i for i, b in enumerate(buttons) if b.media_id == anchor_id), None
    )
    if shift and anchor_row is not None:
        row = buttons.index(button)
        low, high = sorted((anchor_row, row))
        for candidate in buttons[low : high + 1]:
            if not candidate.isHidden():
                ids.add(candidate.media_id)
    else:
        if button.media_id in ids:
            ids.discard(button.media_id)
        else:
            ids.add(button.media_id)
        main_window._target_media_selection_anchor = button.media_id
    sync_selection_visuals(main_window)


def select_all_target_media(main_window: MainWindow) -> None:
    list_widget = main_window.targetVideosList
    ids = _selection_ids(main_window)
    for row in range(list_widget.count()):
        item = list_widget.item(row)
        button = list_widget.itemWidget(item)
        if button is not None and not item.isHidden() and hasattr(button, "media_id"):
            ids.add(button.media_id)
    sync_selection_visuals(main_window)


def clear_target_media_selection(main_window: MainWindow) -> None:
    _selection_ids(main_window).clear()
    main_window._target_media_selection_anchor = None
    sync_selection_visuals(main_window)


def buttons_for_action(main_window: MainWindow, button) -> list:
    """Apply to the whole selection when the clicked card is part of it."""
    selected = get_selected_buttons(main_window)
    if button is not None and button in selected:
        return selected
    return [button] if button is not None else selected


# -------------------------------------------------------------- actions
def remove_buttons(main_window: MainWindow, buttons) -> None:
    for button in list(buttons):
        button.remove_target_media_from_list()
    sync_selection_visuals(main_window)


def delete_buttons_to_trash(main_window: MainWindow, buttons) -> None:
    buttons = [b for b in buttons if not b.is_webcam]
    if not buttons:
        return
    if len(buttons) > 1:
        reply = QtWidgets.QMessageBox.question(
            main_window,
            "Delete Files",
            f"Send {len(buttons)} files to the recycle bin?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if reply != QtWidgets.QMessageBox.Yes:
            return
    for button in buttons:
        button.delete_target_media_to_trash()
    sync_selection_visuals(main_window)


def open_in_default_player(buttons) -> None:
    for button in list(buttons)[:_MAX_OPEN_IN_PLAYER]:
        if not button.is_webcam and os.path.exists(button.media_path):
            QtGui.QDesktopServices.openUrl(
                QtCore.QUrl.fromLocalFile(os.path.abspath(button.media_path))
            )


def copy_paths(buttons) -> None:
    paths = [os.path.abspath(b.media_path) for b in buttons if not b.is_webcam]
    if paths:
        QtWidgets.QApplication.clipboard().setText("\n".join(paths))


def describe_media(main_window: MainWindow, button) -> str:
    path = button.media_path
    lines = [f"Path: {os.path.abspath(path)}", f"Type: {button.file_type}"]
    if os.path.exists(path):
        stat = os.stat(path)
        lines.append(f"Size: {stat.st_size / (1024 * 1024):.2f} MB")
        modified = datetime.datetime.fromtimestamp(stat.st_mtime)
        lines.append(f"Modified: {modified:%Y-%m-%d %H:%M:%S}")
    if button.file_type == "video":
        try:
            import cv2

            capture = cv2.VideoCapture(path)
            if capture.isOpened():
                width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
                fps = capture.get(cv2.CAP_PROP_FPS) or 0.0
                frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
                lines.append(f"Resolution: {width}x{height}")
                lines.append(f"FPS: {fps:.3f}")
                lines.append(f"Frames: {frames}")
                if fps > 0:
                    lines.append(
                        f"Duration: {datetime.timedelta(seconds=int(frames / fps))}"
                    )
            capture.release()
        except Exception as exc:  # metadata is best-effort
            lines.append(f"(Could not read video metadata: {exc})")
    elif button.file_type == "image":
        size = QtGui.QImageReader(path).size()
        if size.isValid():
            lines.append(f"Resolution: {size.width()}x{size.height()}")
    store = get_processed_store(main_window)
    if store.is_processed(path):
        outputs = store.outputs_for(path)
        lines.append("Processed: yes")
        lines.extend(f"  Output: {o}" for o in outputs[-5:])
    else:
        lines.append("Processed: no")
    return "\n".join(lines)


def show_media_info(main_window: MainWindow, button) -> None:
    QtWidgets.QMessageBox.information(
        main_window,
        os.path.basename(button.media_path),
        describe_media(main_window, button),
    )


def add_current_media_to_job(main_window: MainWindow) -> None:
    from app.ui.widgets.actions import job_manager_actions

    job_manager_actions.prompt_job_name(main_window)


def batch_process_buttons(main_window: MainWindow, buttons, all_faces: bool):
    from app.ui.widgets.actions import video_control_actions

    paths = [b.media_path for b in buttons if not b.is_webcam]
    if paths:
        video_control_actions.process_batch_images(
            main_window, all_faces, media_paths=paths
        )


def build_target_media_context_menu(main_window: MainWindow, button) -> QtWidgets.QMenu:
    from app.ui.widgets.actions import list_view_actions, video_control_actions

    targets = buttons_for_action(main_window, button)
    count = len(targets)
    suffix = f" ({count} selected)" if count > 1 else ""
    scan_active = video_control_actions.is_issue_scan_active(main_window)
    batch_running = _is_batch_running(main_window)
    blocked = scan_active or batch_running
    file_targets = [b for b in targets if not b.is_webcam]

    menu = QtWidgets.QMenu(button)

    def add(text, slot, enabled=True, tip=None):
        action = menu.addAction(text)
        action.triggered.connect(slot)
        action.setEnabled(bool(enabled))
        if tip:
            action.setToolTip(tip)
        return action

    add(
        "Open in default player" + suffix,
        partial(open_in_default_player, file_targets),
        file_targets,
    )
    add("Open file location", button.open_target_path_by_explorer, not button.is_webcam)
    add(
        "Copy path" + ("s" if count > 1 else ""),
        partial(copy_paths, file_targets),
        file_targets,
    )
    add(
        "Show info…",
        partial(show_media_info, main_window, button),
        not button.is_webcam,
    )
    menu.addSeparator()

    is_current = getattr(main_window, "selected_video_button", None) is button
    add(
        "Add to job…",
        partial(add_current_media_to_job, main_window),
        is_current and count == 1 and not batch_running,
    )
    add(
        "Batch process" + suffix + " (current config)",
        partial(batch_process_buttons, main_window, file_targets, False),
        file_targets and not blocked,
    )
    add(
        "Batch process" + suffix + " (all faces, images)",
        partial(batch_process_buttons, main_window, file_targets, True),
        any(b.file_type == "image" for b in file_targets) and not blocked,
    )
    menu.addSeparator()

    store = get_processed_store(main_window)
    any_processed = any(store.is_processed(b.media_path) for b in file_targets)
    any_unprocessed = any(not store.is_processed(b.media_path) for b in file_targets)
    add(
        "Mark as processed" + suffix,
        partial(set_processed_for_buttons, main_window, file_targets, True),
        any_unprocessed,
    )
    add(
        "Unmark processed" + suffix,
        partial(set_processed_for_buttons, main_window, file_targets, False),
        any_processed,
    )
    add(
        "Scan output folder for processed media",
        partial(scan_output_folder_for_processed, main_window),
    )
    menu.addSeparator()

    add("Select all", partial(select_all_target_media, main_window))
    add(
        "Clear selection",
        partial(clear_target_media_selection, main_window),
        _selection_ids(main_window),
    )
    menu.addSeparator()

    add(
        "Remove from list" + suffix,
        partial(remove_buttons, main_window, targets),
        not blocked,
    )
    add(
        "Delete file to recycle bin" + suffix,
        partial(delete_buttons_to_trash, main_window, file_targets),
        file_targets and not blocked,
    )
    menu.addSeparator()
    add(
        "Clear All Media",
        partial(list_view_actions.clear_all_target_media, main_window),
        bool(main_window.target_videos) and not blocked,
    )
    return menu


# ---------------------------------------------------- thumbnail resizing
def apply_target_thumbnail_size(main_window: MainWindow, label=None, *args) -> None:
    """Settings exec_function: resize cards now and regenerate pixmaps in the
    background at the new resolution (cached per size)."""
    from app.ui.widgets import ui_workers
    from app.ui.widgets.actions import list_view_actions

    if label is None:
        label = main_window.control.get("TargetThumbnailSizeSelection")
    width, height = list_view_actions.target_button_size_for(label)
    list_widget = getattr(main_window, "targetVideosList", None)
    if list_widget is None:
        return
    size = QtCore.QSize(width, height)
    list_widget.setGridSize(QtCore.QSize(width + 4, height + 4))
    buttons = []
    for row in range(list_widget.count()):
        item = list_widget.item(row)
        button = list_widget.itemWidget(item)
        if button is None:
            continue
        item.setSizeHint(size)
        button.setFixedSize(size)
        if hasattr(button, "media_path") and not button.is_webcam:
            buttons.append((button.media_path, button.file_type, button.media_id))
    list_widget.doItemsLayout()

    previous = getattr(main_window, "target_thumbnail_refresh_worker", None)
    if previous is not None:
        try:
            previous.cancel()
        except RuntimeError:
            pass
    if not buttons:
        return
    manager, scale = list_view_actions.get_target_thumbnail_request(main_window, label)
    worker = ui_workers.TargetThumbnailRefreshWorker(
        main_window, buttons, manager, scale
    )
    worker.thumbnail_ready.connect(partial(_on_refreshed_thumbnail, main_window))
    main_window.target_thumbnail_refresh_worker = worker
    # Keep every worker referenced until its thread finishes (a cancelled one may
    # still be inside its current file).
    alive = getattr(main_window, "_thumbnail_refresh_workers", None)
    if alive is None:
        alive = []
        main_window._thumbnail_refresh_workers = alive
    alive.append(worker)
    worker.finished.connect(partial(_forget_worker, alive, worker))
    worker.start()


def _forget_worker(alive: list, worker) -> None:
    if worker in alive:
        alive.remove(worker)
    worker.deleteLater()


def _on_refreshed_thumbnail(main_window: MainWindow, media_id: str, image) -> None:
    button = main_window.target_videos.get(media_id)
    if button is None or image is None or image.isNull():
        return
    try:
        button.set_thumbnail_pixmap(QtGui.QPixmap.fromImage(image))
    except RuntimeError:
        pass


# ----------------------------------------------------- batch UI locking
def set_batch_ui_locked(main_window: MainWindow, locked: bool) -> None:
    """Disable only the controls that conflict with a running batch."""
    previous = getattr(main_window, "_batch_locked_widgets", None)
    if locked:
        changed = []
        for name in BATCH_CONFLICTING_WIDGETS:
            widget = getattr(main_window, name, None)
            if widget is not None and widget.isEnabled():
                widget.setEnabled(False)
                changed.append(widget)
        main_window._batch_locked_widgets = changed
    elif previous:
        for widget in previous:
            try:
                widget.setEnabled(True)
            except RuntimeError:
                pass
        main_window._batch_locked_widgets = []
