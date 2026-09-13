#!/usr/bin/env python3
"""Word Shuffle — a small, native desktop scratchpad for .shfl files."""

from __future__ import annotations

import random
import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import (
    QAbstractListModel,
    QIODeviceBase,
    QModelIndex,
    QSaveFile,
    QSettings,
    QSignalBlocker,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


APP_NAME = "Word Shuffle"
DEFAULT_SAMPLE = Path("/home/cport/MEGA/Notes/Word Shuffle/try.shfl")
DEFAULT_BLOCK_FONT_SIZE = 14
DEFAULT_BLOCK_SPACING = 5
DEFAULT_THEME = "dark"


@dataclass(frozen=True)
class WordLine:
    line_number: int
    text: str


class WordListModel(QAbstractListModel):
    """Lightweight model that keeps large shuffle files responsive."""

    def __init__(self):
        super().__init__()
        self.words: list[WordLine] = []
        self.font_metrics = None
        self.maximum_item_width = 600

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # type: ignore[override]
        return 0 if parent.isValid() else len(self.words)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):  # type: ignore[override]
        if not index.isValid() or not 0 <= index.row() < len(self.words):
            return None
        word = self.words[index.row()]
        if role == Qt.DisplayRole:
            return word.text
        if role == Qt.UserRole:
            return word
        if role == Qt.SizeHintRole and self.font_metrics is not None:
            natural_width = self.font_metrics.horizontalAdvance(word.text) + 34
            width = min(natural_width, self.maximum_item_width)
            minimum_height = max(40, self.font_metrics.height() + 18)
            if natural_width <= self.maximum_item_width:
                return QSize(width, minimum_height)
            text_width = max(1, width - 34)
            bounds = self.font_metrics.boundingRect(
                0,
                0,
                text_width,
                100_000,
                Qt.AlignCenter | Qt.TextWordWrap | Qt.TextWrapAnywhere,
                word.text,
            )
            return QSize(width, max(minimum_height, bounds.height() + 18))
        return None

    def set_words(self, words: list[WordLine], font_metrics) -> None:
        self.beginResetModel()
        self.words = words.copy()
        self.font_metrics = font_metrics
        self.endResetModel()

    def set_maximum_item_width(self, width: int) -> None:
        width = max(80, width)
        if width == self.maximum_item_width:
            return
        self.maximum_item_width = width
        if self.words:
            self.dataChanged.emit(
                self.index(0),
                self.index(len(self.words) - 1),
                [Qt.SizeHintRole],
            )


class WordList(QListView):
    remove_requested = Signal(object)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton and event.modifiers() & Qt.ControlModifier:
            index = self.indexAt(event.position().toPoint())
            if index.isValid():
                self.remove_requested.emit(index.data(Qt.UserRole))
                event.accept()
                return
        super().mousePressEvent(event)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        model = self.model()
        if isinstance(model, WordListModel):
            model.set_maximum_item_width(self.viewport().width() - 12)


class DropPanel(QFrame):
    file_dropped = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("dropPanel")
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event) -> None:  # type: ignore[override]
        if event.mimeData().hasUrls() and any(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # type: ignore[override]
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self.file_dropped.emit(url.toLocalFile())
                event.acceptProposedAction()
                return


class FileSelector(QComboBox):
    about_to_show = Signal()

    def showPopup(self) -> None:  # type: ignore[override]
        self.about_to_show.emit()
        super().showPopup()


class SettingsDialog(QDialog):
    def __init__(
        self,
        parent: QWidget,
        shuffle_folder: Path | None,
        block_font_size: int,
        block_spacing: int,
        theme: str,
    ):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.setMinimumWidth(500)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(12)

        folder_row = QWidget()
        folder_layout = QHBoxLayout(folder_row)
        folder_layout.setContentsMargins(0, 0, 0, 0)
        folder_layout.setSpacing(8)
        self.folder_edit = QLineEdit(str(shuffle_folder) if shuffle_folder else "")
        self.folder_edit.setReadOnly(True)
        self.folder_edit.setPlaceholderText("No shuffle folder selected")
        folder_layout.addWidget(self.folder_edit, 1)
        browse_button = QPushButton("Choose…")
        browse_button.clicked.connect(self._choose_folder)
        folder_layout.addWidget(browse_button)
        form.addRow("Shuffle folder", folder_row)

        self.font_size_input = QSpinBox()
        self.font_size_input.setRange(9, 36)
        self.font_size_input.setSuffix(" px")
        self.font_size_input.setValue(block_font_size)
        form.addRow("Block font size", self.font_size_input)

        self.spacing_input = QSpinBox()
        self.spacing_input.setRange(0, 40)
        self.spacing_input.setSuffix(" px")
        self.spacing_input.setValue(block_spacing)
        form.addRow("Space between blocks", self.spacing_input)

        self.theme_input = QComboBox()
        self.theme_input.addItem("Dark", "dark")
        self.theme_input.addItem("Light", "light")
        self.theme_input.setCurrentIndex(max(0, self.theme_input.findData(theme)))
        form.addRow("Appearance", self.theme_input)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def shuffle_folder(self) -> Path | None:
        value = self.folder_edit.text().strip()
        return Path(value).expanduser().resolve() if value else None

    def _choose_folder(self) -> None:
        current = self.shuffle_folder
        start = str(current or DEFAULT_SAMPLE.parent)
        path = QFileDialog.getExistingDirectory(self, "Choose shuffle folder", start)
        if path:
            self.folder_edit.setText(str(Path(path).expanduser().resolve()))


class WordShuffleWindow(QMainWindow):
    def __init__(self, initial_file: str | None = None, auto_load: bool = True):
        super().__init__()
        self.settings = QSettings("Local Tools", APP_NAME)
        self.file_path: Path | None = None
        saved_folder = self.settings.value("shuffleFolder", "", str)
        self.shuffle_folder = Path(saved_folder).expanduser().resolve() if saved_folder else None
        if self.shuffle_folder and not self.shuffle_folder.is_dir():
            self.shuffle_folder = None
        self.block_font_size = max(
            9,
            min(36, self.settings.value("blockFontSize", DEFAULT_BLOCK_FONT_SIZE, int)),
        )
        self.block_spacing = max(
            0,
            min(40, self.settings.value("blockSpacing", DEFAULT_BLOCK_SPACING, int)),
        )
        saved_theme = self.settings.value("theme", DEFAULT_THEME, str).lower()
        self.theme = saved_theme if saved_theme in {"dark", "light"} else DEFAULT_THEME
        self.words: list[WordLine] = []
        self.display_order: list[WordLine] = []
        self._build_ui()
        self._apply_theme()
        self._refresh_file_selector()
        self._install_shortcuts()

        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        else:
            self.resize(980, 650)

        if auto_load:
            candidate = self._startup_file(initial_file)
            if candidate:
                QTimer.singleShot(0, lambda: self.load_file(str(candidate)))
            else:
                self._show_empty_state()
        else:
            self._show_empty_state()

    def _build_ui(self) -> None:
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(640, 420)
        self.setAcceptDrops(True)

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.setCentralWidget(central)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(22, 18, 22, 18)
        content_layout.setSpacing(10)

        meta = QHBoxLayout()
        meta.addStretch()
        self.count_label = QLabel("0 REMAINING")
        self.count_label.setObjectName("sectionLabel")
        meta.addWidget(self.count_label)
        content_layout.addLayout(meta)

        self.panel = DropPanel()
        self.panel.file_dropped.connect(self.load_file)
        panel_layout = QVBoxLayout(self.panel)
        panel_layout.setContentsMargins(20, 20, 20, 20)

        self.word_model = WordListModel()
        self.word_list = WordList()
        self.word_list.setObjectName("wordList")
        self.word_list.setModel(self.word_model)
        self.word_list.setViewMode(QListView.IconMode)
        self.word_list.setFlow(QListView.LeftToRight)
        self.word_list.setWrapping(True)
        self.word_list.setWordWrap(True)
        self.word_list.setTextElideMode(Qt.ElideNone)
        self.word_list.setResizeMode(QListView.Adjust)
        self.word_list.setMovement(QListView.Static)
        self.word_list.setLayoutMode(QListView.Batched)
        self.word_list.setBatchSize(250)
        self._apply_block_display()
        self.word_list.setSelectionMode(QListView.NoSelection)
        self.word_list.setCursor(Qt.PointingHandCursor)
        self.word_list.setToolTip("Ctrl-click a block to remove and copy it")
        self.word_list.remove_requested.connect(self.remove_and_copy)
        panel_layout.addWidget(self.word_list, 1)

        self.empty_widget = QWidget()
        empty_layout = QVBoxLayout(self.empty_widget)
        empty_layout.setAlignment(Qt.AlignCenter)
        empty_title = QLabel("Drop a .shfl or text file here")
        empty_title.setObjectName("emptyTitle")
        empty_title.setAlignment(Qt.AlignCenter)
        empty_help = QLabel("One line becomes one word or phrase block")
        empty_help.setObjectName("helper")
        empty_help.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(empty_title)
        empty_layout.addWidget(empty_help)
        panel_layout.addWidget(self.empty_widget, 1)
        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("workspaceScroll")
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setWidget(self.panel)
        content_layout.addWidget(self.scroll_area, 1)

        helper_row = QHBoxLayout()
        helper = QLabel("CTRL + CLICK  removes a block from the file and copies it")
        helper.setObjectName("helper")
        helper_row.addWidget(helper)
        content_layout.addLayout(helper_row)
        root.addWidget(content, 1)

        toolbar = QFrame()
        toolbar.setObjectName("toolbar")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(18, 12, 18, 12)
        toolbar_layout.setSpacing(9)

        self.settings_button = QToolButton()
        self.settings_button.setObjectName("settingsButton")
        self.settings_button.setText("⚙")
        self.settings_button.setAccessibleName("Settings")
        self.settings_button.setToolTip("Settings")
        self.settings_button.setFixedSize(34, 34)
        self.settings_button.clicked.connect(self.show_settings)
        toolbar_layout.addWidget(self.settings_button)

        toolbar_layout.addStretch()

        self.file_selector = FileSelector()
        self.file_selector.setObjectName("fileSelector")
        self.file_selector.setMinimumWidth(190)
        self.file_selector.setPlaceholderText("Choose a .shfl file")
        self.file_selector.setToolTip("Open a file from the selected shuffle folder")
        self.file_selector.about_to_show.connect(self._refresh_file_selector)
        self.file_selector.activated.connect(self._open_selected_file)
        toolbar_layout.addWidget(self.file_selector)

        self.shuffle_button = QPushButton("Shuffle")
        self.shuffle_button.clicked.connect(self.shuffle_words)
        self.shuffle_button.setEnabled(False)
        toolbar_layout.addWidget(self.shuffle_button)

        root.addWidget(toolbar)

    def _install_shortcuts(self) -> None:
        QShortcut(QKeySequence.Open, self, activated=self.choose_file)
        QShortcut(QKeySequence("Ctrl+R"), self, activated=self.shuffle_words)

    def choose_file(self) -> None:
        if self.file_path:
            start = str(self.file_path.parent)
        elif self.shuffle_folder:
            start = str(self.shuffle_folder)
        else:
            start = str(DEFAULT_SAMPLE.parent)
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open word list",
            start,
            "Shuffle files (*.shfl *.SHFL *.txt *.TXT);;All files (*)",
        )
        if path:
            self.load_file(path)

    def choose_shuffle_folder(self) -> None:
        start = str(self.shuffle_folder or (self.file_path.parent if self.file_path else DEFAULT_SAMPLE.parent))
        path = QFileDialog.getExistingDirectory(self, "Choose shuffle folder", start)
        if not path:
            return
        self.shuffle_folder = Path(path).expanduser().resolve()
        self.settings.setValue("shuffleFolder", str(self.shuffle_folder))
        self._refresh_file_selector()

    def show_settings(self) -> None:
        dialog = SettingsDialog(
            self,
            self.shuffle_folder,
            self.block_font_size,
            self.block_spacing,
            self.theme,
        )
        if dialog.exec() != QDialog.Accepted:
            return

        folder_changed = dialog.shuffle_folder != self.shuffle_folder
        self.shuffle_folder = dialog.shuffle_folder
        if self.shuffle_folder:
            self.settings.setValue("shuffleFolder", str(self.shuffle_folder))
        else:
            self.settings.remove("shuffleFolder")
        self._set_block_display_preferences(
            dialog.font_size_input.value(),
            dialog.spacing_input.value(),
        )
        self._set_theme(dialog.theme_input.currentData())
        if folder_changed:
            self._refresh_file_selector()

    def _set_block_display_preferences(self, font_size: int, spacing: int) -> None:
        self.block_font_size = max(9, min(36, font_size))
        self.block_spacing = max(0, min(40, spacing))
        self.settings.setValue("blockFontSize", self.block_font_size)
        self.settings.setValue("blockSpacing", self.block_spacing)
        self._apply_block_display()
        if self.display_order:
            self._render_words()

    def _apply_block_display(self) -> None:
        font = self.word_list.font()
        font.setPixelSize(self.block_font_size)
        self.word_list.setFont(font)
        self.word_list.setSpacing(self.block_spacing)

    def _set_theme(self, theme: str) -> None:
        self.theme = theme if theme in {"dark", "light"} else DEFAULT_THEME
        self.settings.setValue("theme", self.theme)
        self._apply_theme()

    def _apply_theme(self) -> None:
        self.setStyleSheet(stylesheet_for_theme(self.theme))
        # Apply this after the stylesheet so the adjustable block font wins.
        self._apply_block_display()

    def _refresh_file_selector(self) -> None:
        selected_path = str(self.file_path) if self.file_path else ""
        blocker = QSignalBlocker(self.file_selector)
        self.file_selector.clear()
        for path in self._files_in_shuffle_folder():
            relative_name = str(path.relative_to(self.shuffle_folder))
            self.file_selector.addItem(relative_name, str(path))
        matching_index = self.file_selector.findData(selected_path)
        self.file_selector.setCurrentIndex(matching_index)
        self.file_selector.setEnabled(self.file_selector.count() > 0)
        del blocker

    def _files_in_shuffle_folder(self) -> list[Path]:
        if not self.shuffle_folder or not self.shuffle_folder.is_dir():
            return []
        try:
            folder = self.shuffle_folder.resolve()
            return sorted(
                (
                    path.resolve()
                    for path in self.shuffle_folder.rglob("*")
                    if path.is_file()
                    and path.suffix.lower() == ".shfl"
                    and self._is_in_shuffle_folder(path.resolve())
                ),
                key=lambda path: str(path.relative_to(folder)).casefold(),
            )
        except (OSError, ValueError):
            return []

    def _is_in_shuffle_folder(self, path: Path) -> bool:
        if not self.shuffle_folder:
            return False
        try:
            path.relative_to(self.shuffle_folder.resolve())
            return True
        except ValueError:
            return False

    def _startup_file(self, initial_file: str | None) -> Path | None:
        if initial_file:
            candidate = Path(initial_file).expanduser().resolve()
            return candidate if candidate.is_file() else None

        saved_file = self.settings.value("lastFile", "", str)
        if saved_file:
            candidate = Path(saved_file).expanduser().resolve()
            if candidate.is_file() and self._is_in_shuffle_folder(candidate):
                return candidate

        folder_files = self._files_in_shuffle_folder()
        if folder_files:
            return folder_files[0]
        if not self.shuffle_folder and DEFAULT_SAMPLE.is_file():
            return DEFAULT_SAMPLE.resolve()
        return None

    def _open_selected_file(self, index: int) -> None:
        path = self.file_selector.itemData(index)
        if path:
            self.load_file(path)

    def load_file(self, path: str) -> None:
        candidate = Path(path).expanduser().resolve()
        try:
            lines = candidate.read_bytes().decode("utf-8-sig").splitlines()
        except (OSError, UnicodeError) as error:
            QMessageBox.warning(self, "Could not open file", str(error))
            return

        self.file_path = candidate
        self.words = [WordLine(i, line) for i, line in enumerate(lines) if line.strip()]
        self.display_order = self.words.copy()
        random.shuffle(self.display_order)
        if self._is_in_shuffle_folder(candidate):
            self.settings.setValue("lastFile", str(candidate))
        self.setWindowTitle(f"{candidate.name} — {APP_NAME}")
        self.shuffle_button.setEnabled(bool(self.words))
        matching_index = self.file_selector.findData(str(candidate))
        if matching_index >= 0:
            blocker = QSignalBlocker(self.file_selector)
            self.file_selector.setCurrentIndex(matching_index)
            del blocker
        self._render_words()

    def shuffle_words(self) -> None:
        if len(self.display_order) > 1:
            previous = self.display_order.copy()
            for _ in range(5):
                random.shuffle(self.display_order)
                if self.display_order != previous:
                    break
            self._render_words()

    def _render_words(self) -> None:
        self.word_model.set_words(self.display_order, self.word_list.fontMetrics())
        self.word_list.setVisible(bool(self.display_order))
        self.empty_widget.setVisible(not self.display_order)
        self.count_label.setText(f"{len(self.words)} REMAINING")
        self.panel.updateGeometry()

    def remove_and_copy(self, selected: WordLine) -> None:
        if not self.file_path:
            return
        try:
            raw = self.file_path.read_bytes()
            had_bom = raw.startswith(b"\xef\xbb\xbf")
            decoded = raw.decode("utf-8-sig")
            newline = "\r\n" if "\r\n" in decoded else "\n"
            had_trailing_newline = decoded.endswith(("\n", "\r"))
            disk_lines = decoded.splitlines()
            index = selected.line_number
            if index >= len(disk_lines) or disk_lines[index] != selected.text:
                raise RuntimeError("The file changed outside Word Shuffle. Reload it and try again.")
            del disk_lines[index]
            payload = newline.join(disk_lines)
            if disk_lines and had_trailing_newline:
                payload += newline
            encoded = payload.encode("utf-8")
            if had_bom:
                encoded = b"\xef\xbb\xbf" + encoded
            save_file = QSaveFile(str(self.file_path))
            if not save_file.open(QIODeviceBase.OpenModeFlag.WriteOnly):
                raise OSError(save_file.errorString())
            if save_file.write(encoded) < 0 or not save_file.commit():
                raise OSError(save_file.errorString())
        except (OSError, UnicodeError, RuntimeError) as error:
            QMessageBox.warning(self, "Could not update file", str(error))
            return

        QApplication.clipboard().setText(selected.text)
        self.words = [
            WordLine(word.line_number - (word.line_number > selected.line_number), word.text)
            for word in self.words
            if word != selected
        ]
        order_texts = [word for word in self.display_order if word != selected]
        line_lookup = {(word.text, word.line_number): word for word in self.words}
        self.display_order = []
        for old in order_texts:
            new_number = old.line_number - (old.line_number > selected.line_number)
            updated = line_lookup.get((old.text, new_number))
            if updated:
                self.display_order.append(updated)
        self._render_words()
        self.shuffle_button.setEnabled(bool(self.words))

    def _show_empty_state(self) -> None:
        self.empty_widget.setVisible(True)

    def dragEnterEvent(self, event) -> None:  # type: ignore[override]
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # type: ignore[override]
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self.load_file(url.toLocalFile())
                event.acceptProposedAction()
                return

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.settings.setValue("geometry", self.saveGeometry())
        super().closeEvent(event)


THEMES = {
    "dark": {
        "accent": "#6c9cf5",
        "window": "#1b1e24",
        "text": "#d7dbe2",
        "toolbar": "#20242b",
        "toolbar_border": "#343942",
        "section": "#eef1f6",
        "muted": "#7f8793",
        "empty": "#c3c8d0",
        "control": "#292e36",
        "control_text": "#d9dde4",
        "control_border": "#3a414b",
        "control_hover": "#323842",
        "control_hover_border": "#505965",
        "control_pressed": "#252a31",
        "disabled_text": "#656b74",
        "disabled": "#23272d",
        "disabled_border": "#30353d",
        "selection_text": "#10141a",
        "panel": "#181b20",
        "panel_border": "#303640",
        "scroll_handle": "#3b424d",
        "block": "#262b33",
        "block_text": "#e4e7ec",
        "block_border": "#3b424d",
        "block_hover": "#2c3440",
        "block_hover_text": "#ffffff",
        "tooltip": "#303641",
        "tooltip_text": "#f0f2f5",
        "tooltip_border": "#4a5260",
    },
    "light": {
        "accent": "#3268c8",
        "window": "#f4f6f8",
        "text": "#27313f",
        "toolbar": "#e9edf2",
        "toolbar_border": "#cdd5df",
        "section": "#1d2733",
        "muted": "#687383",
        "empty": "#4a5565",
        "control": "#ffffff",
        "control_text": "#253140",
        "control_border": "#c4ccd7",
        "control_hover": "#f1f4f8",
        "control_hover_border": "#929fb0",
        "control_pressed": "#e5eaf0",
        "disabled_text": "#98a2af",
        "disabled": "#edf0f3",
        "disabled_border": "#d8dde4",
        "selection_text": "#ffffff",
        "panel": "#ffffff",
        "panel_border": "#d3d9e2",
        "scroll_handle": "#b5bfcc",
        "block": "#f5f7fa",
        "block_text": "#253140",
        "block_border": "#cbd3dd",
        "block_hover": "#e7effb",
        "block_hover_text": "#17243a",
        "tooltip": "#27313f",
        "tooltip_text": "#ffffff",
        "tooltip_border": "#526171",
    },
}


def stylesheet_for_theme(theme: str) -> str:
    colors = THEMES.get(theme, THEMES[DEFAULT_THEME])
    return f"""
QWidget {{
    background: {colors["window"]};
    color: {colors["text"]};
    font-family: "Noto Sans", "Inter", sans-serif;
}}
QFrame#toolbar {{
    background: {colors["toolbar"]};
    border-top: 1px solid {colors["toolbar_border"]};
}}
QLabel#sectionLabel {{
    color: {colors["section"]};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
}}
QLabel#helper {{ color: {colors["muted"]}; font-size: 11px; }}
QLabel#emptyTitle {{ color: {colors["empty"]}; font-size: 15px; font-weight: 600; }}
QPushButton, QToolButton {{
    min-height: 32px;
    padding: 0 13px;
    background: {colors["control"]};
    color: {colors["control_text"]};
    border: 1px solid {colors["control_border"]};
    border-radius: 8px;
}}
QToolButton#settingsButton {{
    min-height: 0;
    padding: 0;
    font-size: 26px;
}}
QPushButton:hover, QToolButton:hover {{ background: {colors["control_hover"]}; border-color: {colors["control_hover_border"]}; }}
QPushButton:pressed, QToolButton:pressed {{ background: {colors["control_pressed"]}; }}
QPushButton:disabled, QToolButton:disabled {{ color: {colors["disabled_text"]}; background: {colors["disabled"]}; border-color: {colors["disabled_border"]}; }}
QLineEdit, QSpinBox, QComboBox {{
    min-height: 30px;
    padding: 0 8px;
    background: {colors["control"]};
    color: {colors["control_text"]};
    border: 1px solid {colors["control_border"]};
    border-radius: 6px;
}}
QComboBox#fileSelector {{
    min-height: 32px;
    padding: 0 10px;
    background: {colors["control"]};
    color: {colors["control_text"]};
    border: 1px solid {colors["control_border"]};
    border-radius: 8px;
}}
QComboBox:hover {{ background: {colors["control_hover"]}; border-color: {colors["control_hover_border"]}; }}
QComboBox:disabled {{ color: {colors["disabled_text"]}; background: {colors["disabled"]}; border-color: {colors["disabled_border"]}; }}
QComboBox QAbstractItemView {{
    background: {colors["control"]};
    color: {colors["control_text"]};
    border: 1px solid {colors["control_hover_border"]};
    selection-background-color: {colors["accent"]};
    selection-color: {colors["selection_text"]};
}}
QFrame#dropPanel {{ background: {colors["panel"]}; border: 1px solid {colors["panel_border"]}; border-radius: 10px; }}
QScrollArea#workspaceScroll {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: {colors["panel"]}; width: 10px; margin: 8px 2px; }}
QScrollBar::handle:vertical {{ background: {colors["scroll_handle"]}; min-height: 28px; border-radius: 4px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QListView#wordList::item {{
    min-height: 38px;
    padding: 0 16px;
    background: {colors["block"]};
    color: {colors["block_text"]};
    border: 1px solid {colors["block_border"]};
    border-radius: 8px;
}}
QListView#wordList::item:hover {{ background: {colors["block_hover"]}; color: {colors["block_hover_text"]}; border-color: {colors["accent"]}; }}
QListView#wordList {{ background: transparent; border: none; outline: none; }}
QToolTip {{ background: {colors["tooltip"]}; color: {colors["tooltip_text"]}; border: 1px solid {colors["tooltip_border"]}; padding: 5px; }}
"""


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("Local Tools")
    app.setWindowIcon(QIcon(str(Path(__file__).with_name("word-shuffle.svg"))))
    app.setStyle("Fusion")
    app_font = app.font()
    app_font.setPixelSize(13)
    app.setFont(app_font)
    window = WordShuffleWindow(sys.argv[1] if len(sys.argv) > 1 else None)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
