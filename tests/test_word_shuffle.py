import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from word_shuffle import WordShuffleWindow


class WordShuffleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_ctrl_click_removes_exact_duplicate_and_copies(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "words.shfl"
            source.write_text("same\nphrase here\nsame\n", encoding="utf-8")
            window = WordShuffleWindow(auto_load=False)
            window.load_file(str(source))
            target = next(word for word in window.display_order if word.line_number == 2)
            row = window.display_order.index(target)
            window.show()
            self.app.processEvents()
            point = window.word_list.visualRect(window.word_model.index(row)).center()
            QTest.mouseClick(window.word_list.viewport(), Qt.LeftButton, Qt.ControlModifier, point)
            self.assertEqual(source.read_text(encoding="utf-8"), "same\nphrase here\n")
            self.assertEqual(QApplication.clipboard().text(), "same")
            self.assertEqual([word.text for word in window.words], ["same", "phrase here"])
            window.close()

    def test_switching_large_files_replaces_the_model(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            first = folder / "first.shfl"
            second = folder / "second.shfl"
            first.write_text("".join(f"first-{i}\n" for i in range(5000)), encoding="utf-8")
            second.write_text("".join(f"second-{i}\n" for i in range(5000)), encoding="utf-8")
            window = WordShuffleWindow(auto_load=False)
            window.show()
            window.load_file(str(first))
            window.load_file(str(second))
            self.app.processEvents()

            self.assertEqual(window.word_model.rowCount(), 5000)
            self.assertTrue(
                all(word.text.startswith("second-") for word in window.word_model.words)
            )
            window.close()

    def test_long_phrases_wrap_and_show_in_full(self):
        import tempfile
        from pathlib import Path

        phrase = (
            "a complete phrase that is long enough to wrap onto several lines "
            "while still remaining fully visible inside its block"
        )
        long_word = "unbroken" * 40
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "long.shfl"
            source.write_text(f"{phrase}\n{long_word}\n", encoding="utf-8")
            window = WordShuffleWindow(auto_load=False)
            window.resize(360, 500)
            window.show()
            window.load_file(str(source))
            self.app.processEvents()

            self.assertTrue(window.word_list.wordWrap())
            self.assertEqual(window.word_list.textElideMode(), Qt.ElideNone)
            for row in range(window.word_model.rowCount()):
                index = window.word_model.index(row)
                size = index.data(Qt.SizeHintRole)
                self.assertLessEqual(size.width(), window.word_list.viewport().width())
                self.assertGreater(size.height(), 40)
                self.assertEqual(index.data(Qt.DisplayRole), window.word_model.words[row].text)
            window.close()

    def test_block_font_size_and_spacing_update_layout_and_are_saved(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "words.shfl"
            source.write_text("one block\na phrase with several words\n", encoding="utf-8")
            window = WordShuffleWindow(auto_load=False)
            window.load_file(str(source))
            old_height = window.word_model.index(0).data(Qt.SizeHintRole).height()

            with patch.object(window.settings, "setValue") as save_setting:
                window._set_block_display_preferences(28, 17)

            self.assertEqual(window.word_list.font().pixelSize(), 28)
            self.assertEqual(window.word_list.spacing(), 17)
            self.assertGreater(
                window.word_model.index(0).data(Qt.SizeHintRole).height(), old_height
            )
            self.assertIn(
                unittest.mock.call("blockFontSize", 28), save_setting.call_args_list
            )
            self.assertIn(
                unittest.mock.call("blockSpacing", 17), save_setting.call_args_list
            )
            window.close()

    def test_dark_and_light_themes_apply_and_are_saved(self):
        window = WordShuffleWindow(auto_load=False)

        with patch.object(window.settings, "setValue") as save_setting:
            window._set_theme("light")
            light_stylesheet = window.styleSheet()
            window._set_theme("dark")
            dark_stylesheet = window.styleSheet()

        self.assertIn("background: #f4f6f8", light_stylesheet)
        self.assertIn("background: #1b1e24", dark_stylesheet)
        self.assertNotEqual(light_stylesheet, dark_stylesheet)
        self.assertIn(unittest.mock.call("theme", "light"), save_setting.call_args_list)
        self.assertIn(unittest.mock.call("theme", "dark"), save_setting.call_args_list)
        window.close()

    def test_external_edit_is_detected(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "words.shfl"
            source.write_text("alpha\nbeta\n", encoding="utf-8")
            window = WordShuffleWindow(auto_load=False)
            window.load_file(str(source))
            selected = next(word for word in window.words if word.line_number == 0)
            source.write_text("changed\nbeta\n", encoding="utf-8")
            with patch.object(__import__("word_shuffle").QMessageBox, "warning") as warning:
                window.remove_and_copy(selected)
            warning.assert_called_once()
            self.assertEqual(source.read_text(encoding="utf-8"), "changed\nbeta\n")
            window.close()

    def test_footer_selector_lists_and_opens_shfl_files(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / "Beta.shfl").write_text("beta\n", encoding="utf-8")
            (folder / "alpha.shfl").write_text("alpha\n", encoding="utf-8")
            (folder / "ignored.txt").write_text("ignored\n", encoding="utf-8")
            nested = folder / "archive"
            nested.mkdir()
            (nested / "older.SHFL").write_text("older\n", encoding="utf-8")
            window = WordShuffleWindow(auto_load=False)
            with (
                patch.object(
                    __import__("word_shuffle").QFileDialog,
                    "getExistingDirectory",
                    return_value=str(folder),
                ),
                patch.object(window.settings, "setValue") as save_setting,
            ):
                window.choose_shuffle_folder()
            save_setting.assert_called_once_with("shuffleFolder", str(folder.resolve()))

            self.assertEqual(
                [window.file_selector.itemText(i) for i in range(window.file_selector.count())],
                ["alpha.shfl", "archive/older.SHFL", "Beta.shfl"],
            )
            window.file_selector.activated.emit(2)
            self.assertEqual(window.file_path, (folder / "Beta.shfl").resolve())
            self.assertEqual([word.text for word in window.words], ["beta"])

            (folder / "new.shfl").write_text("new\n", encoding="utf-8")
            window.file_selector.about_to_show.emit()
            self.assertGreaterEqual(window.file_selector.findText("new.shfl"), 0)

            root = window.centralWidget().layout()
            toolbar = root.itemAt(root.count() - 1).widget()
            self.assertEqual(toolbar.objectName(), "toolbar")
            self.assertIs(toolbar.layout().itemAt(0).widget(), window.settings_button)
            self.assertEqual(window.settings_button.text(), "⚙")
            self.assertEqual(window.settings_button.accessibleName(), "Settings")
            window.close()

    def test_external_file_does_not_replace_last_file_from_shuffle_folder(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shuffle_folder = root / "sets"
            shuffle_folder.mkdir()
            saved_file = shuffle_folder / "saved.shfl"
            external_file = root / "external.shfl"
            saved_file.write_text("saved\n", encoding="utf-8")
            external_file.write_text("external\n", encoding="utf-8")

            window = WordShuffleWindow(auto_load=False)
            window.shuffle_folder = shuffle_folder.resolve()
            with patch.object(window.settings, "setValue") as save_setting:
                window.load_file(str(saved_file))
                window.load_file(str(external_file))

            self.assertEqual(
                [
                    call
                    for call in save_setting.call_args_list
                    if call.args and call.args[0] == "lastFile"
                ],
                [unittest.mock.call("lastFile", str(saved_file.resolve()))],
            )
            self.assertEqual(window.shuffle_folder, shuffle_folder.resolve())
            window.close()

    def test_normal_startup_ignores_external_last_file(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shuffle_folder = root / "sets"
            shuffle_folder.mkdir()
            folder_file = shuffle_folder / "folder-file.shfl"
            external_file = root / "external.shfl"
            folder_file.write_text("folder\n", encoding="utf-8")
            external_file.write_text("external\n", encoding="utf-8")

            window = WordShuffleWindow(auto_load=False)
            window.shuffle_folder = shuffle_folder.resolve()
            with patch.object(window.settings, "value", return_value=str(external_file)):
                startup_file = window._startup_file(None)

            self.assertEqual(startup_file, folder_file.resolve())
            window.close()


if __name__ == "__main__":
    unittest.main()
