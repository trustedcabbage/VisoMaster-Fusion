"""SVG icons and header-mode helper for the Parameters dock tab bar."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6 import QtCore, QtGui, QtWidgets

if TYPE_CHECKING:
    from app.ui.main_ui import MainWindow

PARAMETERS_TAB_HEADER_MODES = ("Text", "Icon + Text", "Icon Only")
PARAMETERS_TAB_HEADER_DEFAULT = "Icon + Text"
_ICON_SIZE = 18

# Simple monochrome line icons; "currentColor" is replaced at render time.
_FACE_SWAP_SVG = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
     stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="8" cy="9" r="3.2"/>
  <circle cx="16" cy="9" r="3.2"/>
  <path d="M3.5 19c.6-2.6 2.6-4 4.5-4s3.9 1.4 4.5 4"/>
  <path d="M11.5 19c.6-2.6 2.6-4 4.5-4s3.9 1.4 4.5 4"/>
  <path d="M10.2 9.2h3.6"/>
</svg>
"""
_FACE_EDITOR_SVG = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
     stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="12" cy="8.5" r="3.3"/>
  <path d="M6 19.5c.8-3.2 3-5 6-5s5.2 1.8 6 5"/>
  <path d="M16.5 3.5l4 4-8.2 8.2-4.2.6.6-4.2z"/>
</svg>
"""
_RESTORERS_SVG = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
     stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
  <path d="M4 12a8 8 0 0 1 13.7-5.6L20 4v7h-7l2.4-2.4A5.5 5.5 0 1 0 17.5 15"/>
</svg>
"""
_DENOISER_SVG = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
     stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="11" cy="11" r="6.5"/>
  <path d="M16 16l5 5"/>
  <path d="M8 11h6M11 8v6"/>
</svg>
"""
_SETTINGS_SVG = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
     stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="12" cy="12" r="3"/>
  <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.2a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.2a1.7 1.7 0 0 0 1.5-1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.2a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9c.3.7.9 1.2 1.5 1.2H21a2 2 0 1 1 0 4h-.2a1.7 1.7 0 0 0-1.5 1z"/>
</svg>
"""
_PRESETS_SVG = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
     stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
  <rect x="4" y="3.5" width="16" height="17" rx="2"/>
  <path d="M8 8h8M8 12h8M8 16h5"/>
</svg>
"""

PARAMETERS_TAB_SPECS: tuple[tuple[str, str, str], ...] = (
    ("face_swap_tab", "Face Swap", _FACE_SWAP_SVG),
    ("face_editor_tab", "Face Editor", _FACE_EDITOR_SVG),
    ("common_tab", "Restorers", _RESTORERS_SVG),
    ("denoiser_tab", "Denoiser", _DENOISER_SVG),
    ("settings_tab", "Settings", _SETTINGS_SVG),
    ("preset_tab", "Presets", _PRESETS_SVG),
)


def icon_from_svg(svg: str, color: str = "#c8c8c8", size: int = _ICON_SIZE) -> QtGui.QIcon:
    """Render an SVG string to a QIcon without touching media.qrc."""
    from PySide6.QtSvg import QSvgRenderer

    colored = svg.replace("currentColor", color)
    renderer = QSvgRenderer(QtCore.QByteArray(colored.encode("utf-8")))
    pixmap = QtGui.QPixmap(size, size)
    pixmap.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    icon = QtGui.QIcon()
    icon.addPixmap(pixmap, QtGui.QIcon.Mode.Normal, QtGui.QIcon.State.Off)
    # A darker/lighter variant for selected tabs.
    alt = "#2b2b2b" if color.lower() in {"#c8c8c8", "#d0d0d0", "#ffffff"} else "#f2f2f2"
    alt_pix = QtGui.QPixmap(size, size)
    alt_pix.fill(QtCore.Qt.GlobalColor.transparent)
    alt_renderer = QSvgRenderer(
        QtCore.QByteArray(svg.replace("currentColor", alt).encode("utf-8"))
    )
    painter = QtGui.QPainter(alt_pix)
    alt_renderer.render(painter)
    painter.end()
    icon.addPixmap(alt_pix, QtGui.QIcon.Mode.Selected, QtGui.QIcon.State.On)
    icon.addPixmap(alt_pix, QtGui.QIcon.Mode.Selected, QtGui.QIcon.State.Off)
    return icon


def apply_parameters_tab_header_mode(
    main_window: "MainWindow", mode: str | None = None, *_args
) -> None:
    """Apply Text / Icon + Text / Icon Only to the Parameters tab bar."""
    tab_widget = getattr(main_window, "tabWidget", None)
    if tab_widget is None:
        return
    if mode is None:
        mode = (getattr(main_window, "control", {}) or {}).get(
            "ParametersTabHeaderModeSelection", PARAMETERS_TAB_HEADER_DEFAULT
        )
    if mode not in PARAMETERS_TAB_HEADER_MODES:
        mode = PARAMETERS_TAB_HEADER_DEFAULT

    show_icon = mode != "Text"
    show_text = mode != "Icon Only"
    tab_widget.setIconSize(QtCore.QSize(_ICON_SIZE, _ICON_SIZE))
    palette = tab_widget.palette()
    color = palette.color(QtGui.QPalette.ColorRole.WindowText)
    color_hex = color.name() if color.isValid() else "#c8c8c8"

    for object_name, label, svg in PARAMETERS_TAB_SPECS:
        page = getattr(main_window, object_name, None)
        if page is None:
            continue
        index = tab_widget.indexOf(page)
        if index < 0:
            continue
        tab_widget.setTabIcon(
            index, icon_from_svg(svg, color_hex) if show_icon else QtGui.QIcon()
        )
        tab_widget.setTabText(index, label if show_text else "")
        tab_bar = tab_widget.tabBar()
        if tab_bar is not None:
            tab_bar.setTabToolTip(index, label)

    if getattr(main_window, "control", None) is not None:
        main_window.control["ParametersTabHeaderModeSelection"] = mode


def install_parameters_tab_header_menu(main_window: "MainWindow") -> None:
    """Right-click the tab bar to change Text / Icon + Text / Icon Only."""
    tab_widget = getattr(main_window, "tabWidget", None)
    if tab_widget is None or getattr(main_window, "_parameters_tab_menu_installed", False):
        return
    tab_bar = tab_widget.tabBar()
    if tab_bar is None:
        return
    tab_bar.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)

    def _show_menu(pos) -> None:
        menu = QtWidgets.QMenu(tab_bar)
        current = (getattr(main_window, "control", {}) or {}).get(
            "ParametersTabHeaderModeSelection", PARAMETERS_TAB_HEADER_DEFAULT
        )
        for mode in PARAMETERS_TAB_HEADER_MODES:
            action = menu.addAction(mode)
            action.setCheckable(True)
            action.setChecked(mode == current)
            action.triggered.connect(
                lambda checked=False, chosen=mode: _choose_mode(main_window, chosen)
            )
        menu.exec(tab_bar.mapToGlobal(pos))
        menu.deleteLater()

    tab_bar.customContextMenuRequested.connect(_show_menu)
    main_window._parameters_tab_menu_installed = True


def _choose_mode(main_window: "MainWindow", mode: str) -> None:
    from app.ui.widgets.actions import common_actions

    apply_parameters_tab_header_mode(main_window, mode)
    widget = (getattr(main_window, "parameter_widgets", {}) or {}).get(
        "ParametersTabHeaderModeSelection"
    )
    if widget is not None:
        try:
            widget.enable_refresh_frame = False
            widget.set_value(mode)
            widget.enable_refresh_frame = True
        except Exception:
            pass
    common_actions.create_control(
        main_window, "ParametersTabHeaderModeSelection", mode
    )
