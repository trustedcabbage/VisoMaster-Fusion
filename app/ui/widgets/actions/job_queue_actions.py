"""Batch 'add to job' helpers: naming, payload shaping, skip-processed, auto-assign."""

from __future__ import annotations

import copy
import re
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6 import QtWidgets
from PySide6.QtWidgets import QMessageBox

if TYPE_CHECKING:
    from app.ui.main_ui import MainWindow

INVALID_JOB_NAME_CHARS = '<>:"/\\|?*'
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f]")


def sanitize_job_stem(stem: str) -> str:
    """Return a filesystem-safe job name stem, or 'job' if nothing usable remains."""
    cleaned = []
    for char in str(stem or ""):
        if char in INVALID_JOB_NAME_CHARS or _CONTROL_CHAR_RE.search(char):
            cleaned.append("_")
        else:
            cleaned.append(char)
    stem = "".join(cleaned).strip(" .")
    return stem or "job"


def unique_job_name(existing_names: Iterable[str], stem: str) -> str:
    """Pick an unused job name, appending _2, _3, ... on (case-insensitive) collision."""
    base = sanitize_job_stem(stem)
    taken = {str(name).lower() for name in existing_names}
    if base.lower() not in taken:
        return base
    index = 2
    while f"{base}_{index}".lower() in taken:
        index += 1
    return f"{base}_{index}"


def collect_assigned_source_ids(main_window: MainWindow) -> tuple[list[str], list[str]]:
    """IDs of input faces / embeddings assigned to any target face, or currently checked."""
    input_ids: list[str] = []
    embed_ids: list[str] = []
    seen_input: set[str] = set()
    seen_embed: set[str] = set()

    for target_face in (getattr(main_window, "target_faces", {}) or {}).values():
        for face_id in getattr(target_face, "assigned_input_faces", {}) or {}:
            if face_id not in seen_input:
                seen_input.add(face_id)
                input_ids.append(face_id)
        for embed_id in getattr(target_face, "assigned_merged_embeddings", {}) or {}:
            if embed_id not in seen_embed:
                seen_embed.add(embed_id)
                embed_ids.append(embed_id)

    if not input_ids:
        for face_id, button in (getattr(main_window, "input_faces", {}) or {}).items():
            try:
                checked = button.isChecked()
            except RuntimeError:
                continue
            if checked and face_id not in seen_input:
                seen_input.add(face_id)
                input_ids.append(face_id)
    if not embed_ids:
        for embed_id, button in (
            getattr(main_window, "merged_embeddings", {}) or {}
        ).items():
            try:
                checked = button.isChecked()
            except RuntimeError:
                continue
            if checked and embed_id not in seen_embed:
                seen_embed.add(embed_id)
                embed_ids.append(embed_id)
    return input_ids, embed_ids


def has_swap_source(main_window: MainWindow) -> bool:
    input_ids, embed_ids = collect_assigned_source_ids(main_window)
    return bool(input_ids or embed_ids)


def iter_file_targets(buttons: Iterable[Any]) -> list[Any]:
    return [button for button in buttons if button is not None and not getattr(button, "is_webcam", False)]


def job_selected_media_path(data: dict) -> str | None:
    selected_id = data.get("selected_media_id")
    for media in data.get("target_medias_data", []) or []:
        if not selected_id or media.get("media_id") == selected_id:
            path = media.get("media_path")
            if path:
                return str(path)
    return None


def should_skip_processed_job(
    data: dict,
    is_processed: Callable[[str], bool],
    enabled: bool,
) -> bool:
    if not enabled:
        return False
    path = job_selected_media_path(data)
    if not path:
        return False
    try:
        return bool(is_processed(path))
    except OSError:
        return False


def _single_media_entry(button) -> dict[str, str]:
    return {"media_id": button.media_id, "media_path": button.media_path}


def build_job_payload_for_target(
    base_workspace: dict,
    button,
    *,
    is_loaded_target: bool,
    assigned_input_ids: list[str],
    assigned_embed_ids: list[str],
) -> dict:
    """Shape a job JSON payload for one target.

    The currently loaded target keeps faces, markers and parameters. Other
    targets get a fresh detect-and-assign payload (no borrowed face crops).
    """
    payload = copy.deepcopy(base_workspace)
    payload["target_medias_data"] = [_single_media_entry(button)]
    payload["selected_media_id"] = button.media_id
    payload["use_job_name_for_output"] = True
    payload["output_file_name"] = None
    if is_loaded_target:
        payload["pending_auto_assign"] = False
        return payload

    payload["target_faces_data"] = {}
    payload["markers"] = {}
    payload["issue_frames_by_face"] = {}
    payload["dropped_frames"] = []
    payload["job_marker_pairs"] = []
    payload["selected_target_face_id"] = None
    payload["pending_auto_assign"] = True
    payload["pending_assigned_input_faces"] = list(assigned_input_ids)
    payload["pending_assigned_merged_embeddings"] = list(assigned_embed_ids)
    control = payload.setdefault("control", {})
    # Keep sources selected when the job loader clicks the new media.
    control["KeepInputToggle"] = True
    return payload


def job_needs_auto_detect(data: dict) -> bool:
    if data.get("pending_auto_assign"):
        return True
    faces = data.get("target_faces_data") or {}
    return not faces and bool(
        data.get("pending_assigned_input_faces")
        or data.get("pending_assigned_merged_embeddings")
    )


def _apply_pending_checks(main_window: MainWindow, data: dict) -> None:
    input_ids = set(data.get("pending_assigned_input_faces") or [])
    embed_ids = set(data.get("pending_assigned_merged_embeddings") or [])
    for face_id, button in (getattr(main_window, "input_faces", {}) or {}).items():
        try:
            button.setChecked(face_id in input_ids)
        except RuntimeError:
            continue
    for embed_id, button in (getattr(main_window, "merged_embeddings", {}) or {}).items():
        try:
            button.setChecked(embed_id in embed_ids)
        except RuntimeError:
            continue


def auto_detect_and_assign_for_job(main_window: MainWindow, data: dict) -> None:
    """Find faces on the newly loaded media and assign the saved input/embedding IDs."""
    from app.ui.widgets.actions import card_actions

    _apply_pending_checks(main_window, data)
    previous_auto = bool(main_window.control.get("AutoSwapToggle", False))
    previous_keep = bool(main_window.control.get("KeepInputToggle", False))
    main_window.control["AutoSwapToggle"] = True
    main_window.control["KeepInputToggle"] = True
    try:
        card_actions.find_target_faces(main_window)
    finally:
        main_window.control["AutoSwapToggle"] = previous_auto
        main_window.control["KeepInputToggle"] = previous_keep

    if data.get("swap_faces_enabled") and hasattr(main_window, "swapfacesButton"):
        if not main_window.swapfacesButton.isChecked():
            main_window.swapfacesButton.setChecked(True)


def add_to_job_from_shortcut(main_window: MainWindow) -> None:
    """J-key / Edit-menu entry: batch-add when a multi-selection exists, else single add."""
    from app.ui.widgets.actions import job_manager_actions, target_media_actions

    selected = [
        button
        for button in target_media_actions.get_selected_buttons(main_window)
        if not getattr(button, "is_webcam", False)
    ]
    if len(selected) > 1:
        batch_add_targets_to_jobs(main_window, selected)
        return
    if len(selected) == 1:
        current = getattr(main_window, "selected_video_button", None)
        if current is selected[0]:
            job_manager_actions.prompt_job_name(main_window)
            return
        batch_add_targets_to_jobs(main_window, selected)
        return
    job_manager_actions.prompt_job_name(main_window)


def _confirm_batch_add(main_window: MainWindow, buttons: list, job_names: list[str]) -> bool:
    sample = ", ".join(job_names[:8])
    extra = f" and {len(job_names) - 8} more" if len(job_names) > 8 else ""
    auto_swap = bool(main_window.control.get("AutoSwapToggle", False))
    keep_input = bool(main_window.control.get("KeepInputToggle", False))
    message = (
        f"Create {len(buttons)} job(s), named from each file:\n\n"
        f"{sample}{extra}\n\n"
        "The currently loaded target keeps its faces, markers and parameters.\n"
        "Other targets will detect faces at process time and use the current "
        "input face / embedding assignment.\n\n"
        f"Auto Swap is {'ON' if auto_swap else 'OFF'}; "
        f"Keep Input is {'ON' if keep_input else 'OFF'} "
        "(Keep Input is forced on for auto-detect jobs)."
    )
    reply = QMessageBox.question(
        main_window,
        "Add Selected to Jobs",
        message,
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.Yes,
    )
    return reply == QMessageBox.Yes


def batch_add_targets_to_jobs(
    main_window: MainWindow, buttons: Iterable[Any] | None = None
) -> list[str]:
    """Create one job file per selected non-webcam target after a single confirmation.

    Returns the list of created job names (empty if cancelled or blocked).
    """
    from app.ui.widgets.actions import (
        common_actions as common_widget_actions,
        job_manager_actions,
        target_media_actions,
    )

    if job_manager_actions._is_job_processor_running(main_window):
        QMessageBox.warning(
            main_window,
            "Job Queue Running",
            "Stop the job queue before adding new jobs.",
        )
        return []

    if buttons is None:
        buttons = target_media_actions.get_selected_buttons(main_window)
    targets = iter_file_targets(buttons)
    if not targets:
        QMessageBox.information(
            main_window,
            "Add to Jobs",
            "Select one or more target videos or images first (webcams cannot be queued).",
        )
        return []

    output_folder = str(main_window.control.get("OutputMediaFolder", "") or "").strip()
    if not output_folder:
        QMessageBox.warning(
            main_window,
            "Workspace Not Ready",
            "An Output Folder must be set in Settings before saving a job.",
        )
        return []

    if not has_swap_source(main_window):
        reply = QMessageBox.warning(
            main_window,
            "Confirm Save",
            "No input faces or embeddings are assigned (or selected).\n"
            "No face swaps will happen for these jobs. Proceed anyway?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return []

    existing = set(job_manager_actions.list_jobs(main_window))
    planned: list[tuple[Any, str]] = []
    for button in targets:
        stem = Path(button.media_path).stem
        name = unique_job_name(existing, stem)
        existing.add(name)
        planned.append((button, name))

    if not _confirm_batch_add(main_window, targets, [name for _b, name in planned]):
        return []

    base = job_manager_actions._serialize_job_data(main_window)
    input_ids, embed_ids = collect_assigned_source_ids(main_window)
    current = getattr(main_window, "selected_video_button", None)
    created: list[str] = []
    jobs_dir = job_manager_actions.get_jobs_dir(main_window)
    for button, job_name in planned:
        is_loaded = current is not None and getattr(current, "media_id", None) == button.media_id
        payload = build_job_payload_for_target(
            base,
            button,
            is_loaded_target=is_loaded,
            assigned_input_ids=input_ids,
            assigned_embed_ids=embed_ids,
        )
        payload["use_job_name_for_output"] = True
        payload["output_file_name"] = None
        data_filename = jobs_dir / f"{job_name}.json"
        try:
            import json

            with open(data_filename, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=4)
            created.append(job_name)
        except OSError as exc:
            QMessageBox.warning(
                main_window,
                "Save Error",
                f"Failed to save job '{job_name}':\n{exc}",
            )
            break

    job_manager_actions.refresh_job_list(main_window)
    if created:
        common_widget_actions.create_and_show_toast_message(
            main_window,
            "Jobs Saved",
            f"Added {len(created)} job(s) to the queue.",
        )
    return created
