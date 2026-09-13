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
    QUrl,
    Signal,
)
from PySide6.QtGui import QDesktopServices, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListView,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


APP_NAME = "Word Shuffle"
ACCENT = "#6c9cf5"
DEFAULT_SAMPLE = Path("/home/cport/MEGA/Notes/Word Shuffle/try.shfl")


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
            if natural_width <= self.maximum_item_width:
                return QSize(width, 40)
            text_width = max(1, width - 34)
            bounds = self.font_metrics.boundingRect(
                0,
                0,
                text_width,
                100_000,
                Qt.AlignCenter | Qt.TextWordWrap | Qt.TextWrapAnywhere,
                word.text,
            )
            return QSize(width, max(40, bounds.height() + 18))
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


class WordShuffleWindow(QMainWindow):
    def __init__(self, initial_file: str | None = None, auto_load: bool = True):
        super().__init__()
        self.settings = QSettings("Local Tools", APP_NAME)
        self.file_path: Path | None = None
        saved_folder = self.settings.value("shuffleFolder", "", str)
        self.shuffle_folder = Path(saved_folder).expanduser() if saved_folder else None
        if self.shuffle_folder and not self.shuffle_folder.is_dir():
            self.shuffle_folder = None
        self.words: list[WordLine] = []
        self.display_order: list[WordLine] = []
        self._build_ui()
        self._refresh_file_selector()
        self._install_shortcuts()

        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        else:
            self.resize(980, 650)

        if auto_load:
            candidate = initial_file or self.settings.value("lastFile", "", str)
            if not candidate and DEFAULT_SAMPLE.is_file():
                candidate = str(DEFAULT_SAMPLE)
            if candidate and Path(candidate).is_file():
                QTimer.singleShot(0, lambda: self.load_file(candidate))
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
        words_label = QLabel("SHUFFLED BLOCKS")
        words_label.setObjectName("sectionLabel")
        meta.addWidget(words_label)
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
        self.word_list.setSpacing(5)
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
        helper_row.addStretch()
        self.status_label = QLabel("READY")
        self.status_label.setObjectName("status")
        helper_row.addWidget(self.status_label)
        content_layout.addLayout(helper_row)
        root.addWidget(content, 1)

        toolbar = QFrame()
        toolbar.setObjectName("toolbar")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(18, 12, 18, 12)
        toolbar_layout.setSpacing(9)

        toolbar_layout.addStretch()

        self.file_selector = FileSelector()
        self.file_selector.setObjectName("fileSelector")
        self.file_selector.setMinimumWidth(190)
        self.file_selector.setPlaceholderText("Choose a .shfl file")
        self.file_selector.setToolTip("Open a file from the selected shuffle folder")
        self.file_selector.about_to_show.connect(self._refresh_file_selector)
        self.file_selector.activated.connect(self._open_selected_file)
        toolbar_layout.addWidget(self.file_selector)

        self.open_button = QPushButton("Open file")
        self.open_button.setObjectName("primaryButton")
        self.open_button.clicked.connect(self.choose_file)
        toolbar_layout.addWidget(self.open_button)

        self.shuffle_button = QPushButton("Shuffle")
        self.shuffle_button.clicked.connect(self.shuffle_words)
        self.shuffle_button.setEnabled(False)
        toolbar_layout.addWidget(self.shuffle_button)

        self.folder_button = QToolButton()
        self.folder_button.setText("Folder")
        self.folder_button.setToolTip("Show the current file in its folder")
        self.folder_button.clicked.connect(self.show_in_folder)
        self.folder_button.setEnabled(False)
        toolbar_layout.addWidget(self.folder_button)

        self.settings_button = QToolButton()
        self.settings_button.setText("Settings")
        self.settings_button.setToolTip("Choose the folder containing .shfl files")
        self.settings_button.clicked.connect(self.choose_shuffle_folder)
        toolbar_layout.addWidget(self.settings_button)
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
        self._set_status("SHUFFLE FOLDER UPDATED")

    def _refresh_file_selector(self) -> None:
        selected_path = str(self.file_path) if self.file_path else ""
        blocker = QSignalBlocker(self.file_selector)
        self.file_selector.clear()
        if self.shuffle_folder and self.shuffle_folder.is_dir():
            try:
                files = sorted(
                    (
                        path
                        for path in self.shuffle_folder.rglob("*")
                        if path.is_file() and path.suffix.lower() == ".shfl"
                    ),
                    key=lambda path: str(path.relative_to(self.shuffle_folder)).casefold(),
                )
            except OSError:
                files = []
            for path in files:
                relative_name = str(path.relative_to(self.shuffle_folder))
                self.file_selector.addItem(relative_name, str(path.resolve()))
        matching_index = self.file_selector.findData(selected_path)
        self.file_selector.setCurrentIndex(matching_index)
        self.file_selector.setEnabled(self.file_selector.count() > 0)
        del blocker

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
        self.settings.setValue("lastFile", str(candidate))
        self.setWindowTitle(f"{candidate.name} — {APP_NAME}")
        self.shuffle_button.setEnabled(bool(self.words))
        self.folder_button.setEnabled(True)
        matching_index = self.file_selector.findData(str(candidate))
        if matching_index >= 0:
            blocker = QSignalBlocker(self.file_selector)
            self.file_selector.setCurrentIndex(matching_index)
            del blocker
        self._render_words()
        self._set_status(f"LOADED {len(self.words)} BLOCKS")

    def shuffle_words(self) -> None:
        if len(self.display_order) > 1:
            previous = self.display_order.copy()
            for _ in range(5):
                random.shuffle(self.display_order)
                if self.display_order != previous:
                    break
            self._render_words()
            self._set_status("SHUFFLED")

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
        preview = selected.text if len(selected.text) <= 34 else selected.text[:31] + "…"
        self._set_status(f'COPIED “{preview}”')

    def show_in_folder(self) -> None:
        if self.file_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.file_path.parent)))

    def _show_empty_state(self) -> None:
        self.empty_widget.setVisible(True)

    def _set_status(self, message: str) -> None:
        self.status_label.setText(message)
        QTimer.singleShot(3500, lambda: self.status_label.setText("READY"))

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


STYLESHEET = f"""
QWidget {{
    background: #1b1e24;
    color: #d7dbe2;
    font-family: "Noto Sans", "Inter", sans-serif;
    font-size: 13px;
}}
QFrame#toolbar {{
    background: #20242b;
    border-top: 1px solid #343942;
}}
QLabel#sectionLabel {{
    color: #eef1f6;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
}}
QLabel#helper {{ color: #7f8793; font-size: 11px; }}
QLabel#status {{ color: {ACCENT}; font-size: 10px; font-weight: 700; }}
QLabel#emptyTitle {{ color: #c3c8d0; font-size: 15px; font-weight: 600; }}
QPushButton, QToolButton {{
    min-height: 32px;
    padding: 0 13px;
    background: #292e36;
    color: #d9dde4;
    border: 1px solid #3a414b;
    border-radius: 8px;
}}
QPushButton:hover, QToolButton:hover {{ background: #323842; border-color: #505965; }}
QPushButton:pressed, QToolButton:pressed {{ background: #252a31; }}
QPushButton:disabled, QToolButton:disabled {{ color: #656b74; background: #23272d; border-color: #30353d; }}
QPushButton#primaryButton {{ background: {ACCENT}; color: #10141a; border-color: {ACCENT}; font-weight: 700; }}
QPushButton#primaryButton:hover {{ background: #7ba8f8; border-color: #7ba8f8; }}
QComboBox#fileSelector {{
    min-height: 32px;
    padding: 0 10px;
    background: #292e36;
    color: #d9dde4;
    border: 1px solid #3a414b;
    border-radius: 8px;
}}
QComboBox#fileSelector:hover {{ background: #323842; border-color: #505965; }}
QComboBox#fileSelector:disabled {{ color: #656b74; background: #23272d; border-color: #30353d; }}
QComboBox#fileSelector QAbstractItemView {{
    background: #292e36;
    color: #d9dde4;
    border: 1px solid #505965;
    selection-background-color: {ACCENT};
    selection-color: #10141a;
}}
QFrame#dropPanel {{ background: #181b20; border: 1px solid #303640; border-radius: 10px; }}
QScrollArea#workspaceScroll {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: #181b20; width: 10px; margin: 8px 2px; }}
QScrollBar::handle:vertical {{ background: #3b424d; min-height: 28px; border-radius: 4px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QListView#wordList::item {{
    min-height: 38px;
    padding: 0 16px;
    background: #262b33;
    color: #e4e7ec;
    border: 1px solid #3b424d;
    border-radius: 8px;
    font-size: 14px;
}}
QListView#wordList::item:hover {{ background: #2c3440; color: #ffffff; border-color: {ACCENT}; }}
QListView#wordList {{ background: transparent; border: none; outline: none; }}
QToolTip {{ background: #303641; color: #f0f2f5; border: 1px solid #4a5260; padding: 5px; }}
"""


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("Local Tools")
    app.setWindowIcon(QIcon(str(Path(__file__).with_name("word-shuffle.svg"))))
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)
    window = WordShuffleWindow(sys.argv[1] if len(sys.argv) > 1 else None)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
