from __future__ import annotations

import enum
import re
from dataclasses import dataclass
from functools import total_ordering
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from PySide6 import QtCore, QtGui, QtWidgets

from app.helpers.miscellaneous import MediaMetadata, get_file_type

if TYPE_CHECKING:
    from app.ui.widgets.widget_components import CardButton


class SortableDataRole(enum.IntEnum):
    """Item data roles, based off Qt.ItemDataRole.UserRole (0x100) to stay clear
    of the roles Qt reserves for itself."""

    FileInfoRole = 0x180  # 384
    ImageDimensionRole = 0x181  # 385
    CardButtonRole = 0x182  # 386
    FileTypeRole = 0x183  # 387
    MediaMetadataRole = 0x184  # 388


class SortingMode(enum.IntEnum):
    FileBirthDate = 0x140
    FileName = 0x141
    FileSize = 0x143
    ImageDimension = 0x144
    ImagePixels = 0x145
    VideoLength = 0x146

    def to_id(self) -> str:
        return self.name


initialize_combobox_items = [
    ("Sort by Name", SortingMode.FileName),
    ("Sort by File Date", SortingMode.FileBirthDate),
    ("Sort by File Size", SortingMode.FileSize),
    ("Sort by Dimensions", SortingMode.ImageDimension),
    ("Sort by Total Pixels", SortingMode.ImagePixels),
    ("Sort by Frame Length", SortingMode.VideoLength),
]

_FILE_MODES = frozenset(
    {SortingMode.FileBirthDate, SortingMode.FileName, SortingMode.FileSize}
)


@total_ordering
@dataclass(frozen=True)
class SortableImageDimension:
    width: int
    height: int

    def size(self) -> QtCore.QSize:
        return QtCore.QSize(self.width, self.height)

    @property
    def shape(self) -> tuple[int, int]:
        return self.height, self.width

    @property
    def pixels(self) -> int:
        return self.width * self.height

    @property
    def sort_key(self) -> tuple[int, int]:
        return self.width, self.height

    def contains(self, minimum: "SortableImageDimension") -> bool:
        """True when this dimension is at least as large as minimum on both axes."""
        return self.width >= minimum.width and self.height >= minimum.height

    def __str__(self) -> str:
        return f"{self.width}x{self.height}"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SortableImageDimension):
            return NotImplemented
        return self.sort_key == other.sort_key

    def __hash__(self) -> int:
        return hash(self.sort_key)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, SortableImageDimension):
            return NotImplemented
        return self.sort_key < other.sort_key

    # PARSERS

    @classmethod
    def from_string(cls, value: str) -> "SortableImageDimension":
        match = re.fullmatch(r"\s*(\d+)\s*x\s*(\d+)\s*", value)
        if match is None:
            raise ValueError(f"Not a WIDTHxHEIGHT dimension: {value!r}")
        return cls(int(match.group(1)), int(match.group(2)))

    @classmethod
    def from_metadata(
        cls, metadata: MediaMetadata | None
    ) -> Optional["SortableImageDimension"]:
        if metadata is None or not (metadata.width and metadata.height):
            return None
        return cls(int(metadata.width), int(metadata.height))


class SortableListWidget(QtWidgets.QListWidget):
    """QListWidget whose items sort themselves by the selected SortingMode."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._sorting_mode: SortingMode = SortingMode.FileName
        self._min_image_dimension: Optional[SortableImageDimension] = None

    def setSortingMode(self, sort_mode: SortingMode | None) -> None:
        if isinstance(sort_mode, SortingMode):
            self._sorting_mode = sort_mode

    def sortingMode(self) -> SortingMode:
        return self._sorting_mode

    def setMinImageDimension(self, imgdim: SortableImageDimension | None) -> None:
        self._min_image_dimension = imgdim

    def minImageDimension(self) -> Optional[SortableImageDimension]:
        return self._min_image_dimension


class TargetVideosListWidget(SortableListWidget):
    """Promoted class for MainWindow.ui's targetVideosList.

    Adds click-drag rubber-band multi-select and Ctrl+wheel thumbnail zoom.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._press_pos: QtCore.QPoint | None = None
        self._press_modifiers = QtCore.Qt.KeyboardModifier.NoModifier
        self._press_card = None
        self._rubber: QtWidgets.QRubberBand | None = None
        self._rubber_active = False
        self._origin_selection: set = set()
        self._zoom_timer = QtCore.QTimer(self)
        self._zoom_timer.setSingleShot(True)
        self._zoom_timer.setInterval(120)
        self._pending_zoom_label: str | None = None
        self._zoom_timer.timeout.connect(self._commit_pending_zoom)
        self.viewport().installEventFilter(self)

    def _main_window(self):
        return self.window()

    def eventFilter(self, obj, event):
        if obj is self.viewport():
            etype = event.type()
            if etype == QtCore.QEvent.Type.MouseButtonPress:
                if self._on_viewport_press(event):
                    return True
            elif etype == QtCore.QEvent.Type.MouseMove:
                if self._on_pointer_move(event):
                    return True
            elif etype == QtCore.QEvent.Type.MouseButtonRelease:
                if self._on_pointer_release(event):
                    return True
            elif etype == QtCore.QEvent.Type.Wheel:
                if self._on_wheel(event):
                    return True
        return super().eventFilter(obj, event)

    def _card_at(self, pos: QtCore.QPoint):
        item = self.itemAt(pos)
        if item is None:
            return None
        return self.itemWidget(item)

    def _cards(self) -> list:
        cards = []
        for row in range(self.count()):
            item = self.item(row)
            if item is None or item.isHidden():
                continue
            widget = self.itemWidget(item)
            if widget is not None and hasattr(widget, "media_id"):
                cards.append(widget)
        return cards

    def begin_pointer_gesture(self, event: QtGui.QMouseEvent, card=None) -> bool:
        """Start a possible click or rubber-band. Returns True if the card should swallow the press."""
        if event.button() != QtCore.Qt.MouseButton.LeftButton:
            return False
        mw = self._main_window()
        if not getattr(mw, "target_videos", None):
            return False
        self._press_pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        # Map card-local coordinates into the viewport.
        if card is not None:
            self._press_pos = card.mapTo(self.viewport(), self._press_pos)
        self._press_modifiers = event.modifiers()
        self._press_card = card if card is not None else self._card_at(self._press_pos)
        self._rubber_active = False
        self._origin_selection = set(
            getattr(mw, "target_media_multi_selection", set()) or set()
        )
        return True

    def _on_viewport_press(self, event) -> bool:
        if event.button() != QtCore.Qt.MouseButton.LeftButton:
            return False
        # Clicks on cards are handled by TargetMediaCardButton, which forwards here.
        # Only start a gesture from empty space in the viewport.
        child = self.viewport().childAt(event.position().toPoint() if hasattr(event, "position") else event.pos())
        if child is not None and child is not self.viewport():
            # Could be a card or a label inside a card; let the card handle it.
            parent = child
            while parent is not None and parent is not self.viewport():
                if hasattr(parent, "media_id") and hasattr(parent, "load_media"):
                    return False
                parent = parent.parentWidget() if hasattr(parent, "parentWidget") else None
        return self.begin_pointer_gesture(event, card=None)

    def _ensure_rubber(self) -> QtWidgets.QRubberBand:
        if self._rubber is None:
            self._rubber = QtWidgets.QRubberBand(
                QtWidgets.QRubberBand.Shape.Rectangle, self.viewport()
            )
        return self._rubber

    def _on_pointer_move(self, event) -> bool:
        if self._press_pos is None:
            return False
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        if hasattr(event, "source") and event.source() is not None:
            pass
        # If the event originated on a card, map into viewport coords.
        widget = self.sender() if False else None  # unused; mapping is done by callers
        if not self._rubber_active:
            if (pos - self._press_pos).manhattanLength() < QtWidgets.QApplication.startDragDistance():
                return True
            self._rubber_active = True
            self._ensure_rubber().show()
        rect = QtCore.QRect(self._press_pos, pos).normalized()
        self._ensure_rubber().setGeometry(rect)
        self._apply_rubber_selection(rect)
        return True

    def update_pointer_gesture(self, event: QtGui.QMouseEvent, source_widget=None) -> bool:
        if self._press_pos is None:
            return False
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        if source_widget is not None:
            pos = source_widget.mapTo(self.viewport(), pos)
        # Build a fake-local move using viewport coords.
        if not self._rubber_active:
            if (pos - self._press_pos).manhattanLength() < QtWidgets.QApplication.startDragDistance():
                return True
            self._rubber_active = True
            self._ensure_rubber().show()
        rect = QtCore.QRect(self._press_pos, pos).normalized()
        self._ensure_rubber().setGeometry(rect)
        self._apply_rubber_selection(rect)
        return True

    def _apply_rubber_selection(self, rect: QtCore.QRect) -> None:
        mw = self._main_window()
        from app.ui.widgets.actions import target_media_actions

        ids = target_media_actions._selection_ids(mw)
        modifiers = self._press_modifiers
        shift = bool(modifiers & QtCore.Qt.KeyboardModifier.ShiftModifier)
        ctrl = bool(modifiers & QtCore.Qt.KeyboardModifier.ControlModifier)
        hit: set = set()
        for card in self._cards():
            top_left = card.mapTo(self.viewport(), QtCore.QPoint(0, 0))
            card_rect = QtCore.QRect(top_left, card.size())
            if card_rect.intersects(rect):
                hit.add(card.media_id)
        if shift or ctrl:
            ids.clear()
            ids.update(self._origin_selection | hit)
        else:
            ids.clear()
            ids.update(hit)
        target_media_actions.sync_selection_visuals(mw)

    def finish_pointer_gesture(self, event: QtGui.QMouseEvent, source_widget=None) -> bool:
        if self._press_pos is None:
            return False
        rubber = self._rubber_active
        if self._rubber is not None:
            self._rubber.hide()
        self._rubber_active = False
        press_card = self._press_card
        modifiers = self._press_modifiers
        self._press_pos = None
        self._press_card = None
        if rubber:
            # Selection already applied during move; never load media.
            return True
        mw = self._main_window()
        from app.ui.widgets.actions import target_media_actions

        ctrl = bool(modifiers & QtCore.Qt.KeyboardModifier.ControlModifier)
        shift = bool(modifiers & QtCore.Qt.KeyboardModifier.ShiftModifier)
        if press_card is not None:
            if ctrl or shift:
                target_media_actions.handle_target_media_modifier_click(
                    mw, press_card, shift=shift
                )
            else:
                clear_on_click = (getattr(mw, "control", {}) or {}).get(
                    "PlainClickClearsTargetSelectionToggle", True
                )
                if clear_on_click:
                    target_media_actions.clear_target_media_selection(mw)
                press_card.load_media()
        else:
            clear_on_click = (getattr(mw, "control", {}) or {}).get(
                "PlainClickClearsTargetSelectionToggle", True
            )
            if clear_on_click and not ctrl and not shift:
                target_media_actions.clear_target_media_selection(mw)
        return True

    def _on_pointer_release(self, event) -> bool:
        if event.button() != QtCore.Qt.MouseButton.LeftButton:
            return False
        if self._press_pos is None:
            return False
        return self.finish_pointer_gesture(event, source_widget=None)

    def _on_wheel(self, event) -> bool:
        if not (event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier):
            return False
        mw = self._main_window()
        control = getattr(mw, "control", {}) or {}
        if not control.get("TargetThumbnailCtrlWheelZoomToggle", True):
            return False
        from app.ui.widgets.actions import list_view_actions

        delta = event.angleDelta().y()
        if delta == 0:
            return True
        direction = 1 if delta > 0 else -1
        current = control.get(
            "TargetThumbnailSizeSelection",
            list_view_actions.TARGET_THUMBNAIL_SIZE_DEFAULT,
        )
        if self._pending_zoom_label:
            current = self._pending_zoom_label
        self._pending_zoom_label = list_view_actions.step_target_thumbnail_size_label(
            current, direction
        )
        self._zoom_timer.start(120)
        return True

    def _commit_pending_zoom(self) -> None:
        label = self._pending_zoom_label
        self._pending_zoom_label = None
        if not label:
            return
        from app.ui.widgets.actions import list_view_actions

        list_view_actions.apply_thumbnail_size_label(self._main_window(), label)


class SortableListWidgetItem(QtWidgets.QListWidgetItem):
    def fileType(self) -> str:
        stored = self.data(SortableDataRole.FileTypeRole)
        if stored:
            return str(stored)
        fileinfo = self.fileInfo()
        if fileinfo is None:
            return ""
        return get_file_type(fileinfo.filePath()) or ""

    # DATA

    def cardButton(self) -> Optional["CardButton"]:
        return self.data(SortableDataRole.CardButtonRole)

    def setCardButton(self, card_button: "CardButton") -> None:
        self.setData(SortableDataRole.CardButtonRole, card_button)

    def fileInfo(self) -> Optional[QtCore.QFileInfo]:
        fileinfo = self.data(SortableDataRole.FileInfoRole)
        return fileinfo if isinstance(fileinfo, QtCore.QFileInfo) else None

    def setFileInfo(self, info: QtCore.QFileInfo) -> None:
        self.setData(SortableDataRole.FileInfoRole, info)

    def setFileType(self, file_type: str) -> None:
        self.setData(SortableDataRole.FileTypeRole, file_type)

    def imageDimension(self) -> Optional[SortableImageDimension]:
        imgdim = self.data(SortableDataRole.ImageDimensionRole)
        return imgdim if isinstance(imgdim, SortableImageDimension) else None

    def setImageDimension(self, imgdim: SortableImageDimension) -> None:
        self.setData(SortableDataRole.ImageDimensionRole, imgdim)

    def mediaMetadata(self) -> Optional[MediaMetadata]:
        metadata = self.data(SortableDataRole.MediaMetadataRole)
        return metadata if isinstance(metadata, MediaMetadata) else None

    def setMediaMetadata(self, metadata: MediaMetadata) -> None:
        self.setData(SortableDataRole.MediaMetadataRole, metadata)

    # COMPARATORS

    def _sort_key(self, sort_mode: SortingMode):
        """Value to order this item by, or None when it cannot be determined."""
        if sort_mode in _FILE_MODES:
            fileinfo = self.fileInfo()
            if fileinfo is None:
                return None
            if sort_mode == SortingMode.FileBirthDate:
                return fileinfo.birthTime()
            if sort_mode == SortingMode.FileName:
                return fileinfo.baseName().casefold()
            return fileinfo.size()

        if sort_mode == SortingMode.VideoLength:
            metadata = self.mediaMetadata()
            return None if metadata is None else metadata.total_frames

        imgdim = self.imageDimension()
        if imgdim is None:
            return None
        if sort_mode == SortingMode.ImageDimension:
            return imgdim.sort_key
        if sort_mode == SortingMode.ImagePixels:
            return imgdim.pixels
        return None

    def __lt__(self, other) -> bool:
        list_widget = self.listWidget()
        if not isinstance(list_widget, SortableListWidget):
            return False
        if not isinstance(other, SortableListWidgetItem):
            return False

        left = self._sort_key(list_widget.sortingMode())
        right = other._sort_key(list_widget.sortingMode())

        # Items that lack the data being sorted on (webcams have no file on disk)
        # sink below the ones that have it, rather than comparing equal to
        # everything, which would scramble the whole order.
        if left is None or right is None:
            return left is not None

        if left != right:
            return left < right

        # Qt's sort is not stable, so tie-break on the file name to keep items
        # with equal keys (same size, same dimensions, ...) in a predictable order.
        return self._tie_break_key() < other._tie_break_key()

    def _tie_break_key(self) -> str:
        fileinfo = self.fileInfo()
        return fileinfo.fileName().casefold() if fileinfo else ""

    # SERIALIZERS

    def to_tooltip(self) -> str:
        tipslist: list[str] = []
        fileinfo = self.fileInfo()
        if fileinfo:
            tipslist.append(f"FileName: {fileinfo.fileName()}")
            tipslist.append(f"FileType: {self.fileType()}")
            tipslist.append(
                f"FileDate: {fileinfo.birthTime().toLocalTime().toString('yyyy-MM-dd HH:mm:ss')}"
            )
            tipslist.append(
                f"FileSize: {QtCore.QLocale.system().formattedDataSize(fileinfo.size())}"
            )
            tipslist.append(f"Path: {Path(fileinfo.filePath()).parent}")

        image_dim = self.imageDimension()
        if image_dim:
            tipslist.append(f"Dimensions: {image_dim}")

        metadata = self.mediaMetadata()
        if metadata and self.fileType() == "video":
            tipslist.append(f"Length: {metadata.total_frames} frames")
            if metadata.frame_rate:
                tipslist.append(f"Frame Rate: {metadata.frame_rate:.3f}")
            if metadata.bitrate_kbits:
                tipslist.append(f"Bitrate: {metadata.bitrate_kbits:.0f} kBit/s")

        return "\n".join(tipslist)
