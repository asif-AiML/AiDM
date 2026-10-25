# AiDM Requirements and Tool Installation

AiDM relies on a small set of external tools. The CLI and GUI share the same
backend engines, while the GUI adds one optional Python dependency.

This guide assumes Linux Mint / Ubuntu / Debian-family systems.

---

## Required backend tools

AiDM uses:

- **yt-dlp** for YouTube, supported websites, HLS/DASH and generic extraction;
- **aria2c** for direct downloads, bulk direct downloads and torrents;
- **FFmpeg** for merging, conversion and post-processing where required.

Verify whether they are already installed before installing anything:

```bash
yt-dlp --version
aria2c --version
ffmpeg -version
```

If a command is not found, follow the corresponding first-time installation
section below.

---

# yt-dlp

## First-time installation

AiDM works best with a current yt-dlp build. On Linux, a simple source-friendly
installation is the official standalone binary in `/usr/local/bin`.

Download the latest release:

```bash
sudo wget -O /usr/local/bin/yt-dlp \
  https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp
```

Make it executable:

```bash
sudo chmod a+rx /usr/local/bin/yt-dlp
```

Verify:

```bash
yt-dlp --version
```

If that prints a version number, yt-dlp is ready for AiDM.

### Updating yt-dlp

Because the standalone binary supports self-update:

```bash
sudo yt-dlp -U
```

Then verify again:

```bash
yt-dlp --version
```

### Reinstalling or removing the standalone binary

Reinstall by running the first-time installation commands again.

To remove this installation cleanly:

```bash
sudo rm /usr/local/bin/yt-dlp
```

Do not install multiple unrelated copies of yt-dlp unless you intentionally
manage which one appears first on `PATH`.

Check the active executable with:

```bash
command -v yt-dlp
```

---

# aria2c

## First-time installation

Install aria2 from APT:

```bash
sudo apt update
sudo apt install -y aria2
```

Verify:

```bash
aria2c --version
```

### Updating aria2

```bash
sudo apt update
sudo apt --only-upgrade install aria2
```

### Removing aria2

```bash
sudo apt remove aria2
```

---

# FFmpeg

## First-time installation

Install FFmpeg from APT:

```bash
sudo apt update
sudo apt install -y ffmpeg
```

Verify:

```bash
ffmpeg -version
```

### Updating FFmpeg

```bash
sudo apt update
sudo apt --only-upgrade install ffmpeg
```

### Removing FFmpeg

```bash
sudo apt remove ffmpeg
```

---

# PySide6 — GUI only

The terminal CLI does not require PySide6.

PySide6 is required only when launching the graphical interface:

```bash
python3 aidm_gui.py
```

## First-time installation for source development

Install PySide6 into the Python environment used to run AiDM:

```bash
python3 -m pip install PySide6
```

Verify the import:

```bash
python3 -c "from PySide6.QtWidgets import QApplication, QMainWindow; print('PySide6 OK')"
```

If your distribution prevents package installation into the system Python,
use a dedicated Python environment for source development rather than forcing
pip to overwrite distribution-managed packages.

The future packaged AiDM release should manage GUI dependencies through the
package itself so ordinary users do not need to perform Python dependency
setup manually.

## Linux Qt/X11 dependency

On Linux Mint / Ubuntu / Debian, Qt's X11 `xcb` platform plugin may require
the cursor library:

```bash
sudo apt update
sudo apt install -y libxcb-cursor0
```

This is relevant when startup errors explicitly mention `xcb-cursor0`,
`libxcb-cursor0`, or failure to initialize the Qt `xcb` platform plugin.

Do not install extra Qt packages blindly if the GUI already launches normally.

---

# Launching AiDM from source

## CLI

```bash
python3 aidm.py [INPUT]
```

Example:

```bash
python3 aidm.py 'https://example.com/file.zip'
```

## GUI

```bash
python3 aidm_gui.py
```

The CLI and GUI are separate frontends over the same AiDM backend intelligence.

---

# Quick installation checklist

For a fresh Linux Mint / Ubuntu / Debian machine:

```bash
sudo apt update
sudo apt install -y aria2 ffmpeg libxcb-cursor0

sudo wget -O /usr/local/bin/yt-dlp \
  https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp
sudo chmod a+rx /usr/local/bin/yt-dlp

python3 -m pip install PySide6
```

Then verify:

```bash
yt-dlp --version
aria2c --version
ffmpeg -version
python3 -c "import PySide6; print('PySide6 OK')"
```

For CLI-only use, PySide6 and `libxcb-cursor0` are not required.

---

# Troubleshooting

## Check which executable is being used

```bash
command -v yt-dlp
command -v aria2c
command -v ffmpeg
which python3
```

## VS Code reports unresolved PySide6 imports

If the GUI launches correctly but VS Code reports:

```text
Import "PySide6.QtWidgets" could not be resolved
```

find the interpreter that successfully launches AiDM:

```bash
python3 -c "import sys; print(sys.executable)"
```

Then in VS Code:

1. Press **Ctrl+Shift+P**.
2. Choose **Python: Select Interpreter**.
3. Select that interpreter.
4. Reload the VS Code window if the warning remains.

No AiDM source change is required for an editor/interpreter mismatch.
