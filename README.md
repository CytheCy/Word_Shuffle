# Word Shuffle

A compact PySide6 desktop tool for `.shfl` files. Each non-empty source line is shown as a shuffled word or phrase block. **Ctrl-click** a block to remove that exact line from the source file and copy it to the desktop clipboard.

## Run

```bash
./run-word-shuffle.sh "/path/to/list.shfl"
```

With no argument, Word Shuffle reopens the last file used inside the configured shuffle folder. Opening a `.shfl` elsewhere, including from a file manager, does not replace that remembered file or change the configured folder. On first launch it opens `/home/cport/MEGA/Notes/Word Shuffle/try.shfl` when that file exists.

Use **Settings** in the footer to choose the folder that contains your `.shfl` files, change the block font size and spacing, or switch between dark and light mode. These choices are saved for the next launch. The footer selector refreshes when opened and includes `.shfl` files from that folder and its subfolders. You can also use **Ctrl+O** to open another file, **Ctrl+R** to reshuffle, or drag a file into the workspace.

`word-shuffle.desktop` is included for adding the app to a KDE launcher or desktop.
