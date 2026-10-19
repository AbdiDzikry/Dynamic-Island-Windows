# 🏝️ Dynamic Island for Windows

<p align="center">
  <img src="icon.png" width="96" height="96" alt="Dynamic Island Icon" />
</p>

<p align="center">
  <b>A sleek, minimalist, fluid Dynamic Island desktop companion for Windows 10 & 11.</b>
  <br />
  Featuring real-time Windows Media controls, hardware monitoring, multi-tab quick notes, and a digital clock.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-0078D6?style=flat-square&logo=windows" alt="Platform" />
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python" alt="Python" />
  <img src="https://img.shields.io/badge/UI-PyQt6-green?style=flat-square&logo=qt" alt="PyQt6" />
  <img src="https://img.shields.io/badge/License-MIT-yellow?style=flat-square" alt="License" />
</p>

---

## ✨ Features

- **🎵 Media Player (Windows GSMTC Integration)**
  - Seamlessly captures now-playing media from Spotify, Apple Music, YouTube (Chrome/Edge/Brave), etc.
  - Live progress bar, album art thumbnail with rounded aesthetics, and prominent Song Title & Artist name (`👤 Artist`).
  - Interactive playback controls: Play/Pause, Next Track, and Previous Track.

- **⚡ System Performance Monitor**
  - Real-time CPU, RAM, and Battery percentage metrics.
  - Minimalist color-coded progress bars for instant system health awareness.

- **📝 Multi Quick Note (Tabs 1–5)**
  - Keep up to 5 quick notes simultaneously without opening heavy text editors.
  - One-click copy (`📋 Salin`) to clipboard and clear (`🗑️ Hapus`).
  - Automatic persistence to `quick_notes.json` so you never lose your thoughts across restarts.

- **🕒 Minimalist Clock & Date**
  - Clean digital clock with current day, full date, and year.
  - Aesthetic and uncluttered typography.

- **🚀 Glassmorphic Quick-Dock Navigation**
  - Smooth semi-transparent dock header (`🎵`, `⚡`, `📝`, `🕒`) to switch modes with a single click.
  - Auto-collapses into a subtle, pill-shaped compact bar at the top-center of your monitor when not in use.
  - Smooth fluid expansion upon hover.

---

## 🚀 Download & Installation (No Install Required!)

### Option 1: Standalone Portable (Recommended)
1. Head over to the [**Releases**](https://github.com/AbdiDzikry/Dynamic-Island-Windows/releases) page.
2. Download the latest `DynamicIsland-Portable.zip`.
3. Extract the `.zip` anywhere (e.g., `C:\Tools\DynamicIsland`).
4. Run `DynamicIsland.exe` — **no installation or Python required!**

> **Tip:** Create a shortcut of `DynamicIsland.exe` into your Windows Startup folder (`Win + R` > `shell:startup`) to launch it automatically on boot!

---

### Option 2: Run from Source (For Developers)

#### Prerequisites
- Windows 10 (Build 19041+) or Windows 11
- Python 3.10 or higher

#### Installation
1. Clone the repository:
   ```bash
   git clone https://github.com/AbdiDzikry/Dynamic-Island-Windows.git
   cd Dynamic-Island-Windows
   ```

2. Create and activate a virtual environment (optional but recommended):
   ```bash
   python -m venv venv
   venv\Scripts\activate
   ```

3. Install required packages:
   ```bash
   pip install -r requirements.txt
   ```

4. Run the application:
   ```bash
   python app.py
   ```

---

## 🛠️ Building the Standalone `.exe`

To build the executable yourself using PyInstaller:

```bash
pyinstaller --noconfirm --onefile --windowed --icon="app_icon.ico" --name="DynamicIsland" app.py
```

The resulting single-file binary will be located in `dist/DynamicIsland.exe`.

---

## 📜 License

Distributed under the MIT License. See `LICENSE` for more information.

---

<p align="center">
  Crafted with ❤️ by <a href="https://github.com/AbdiDzikry">Abdi Dzikry</a>
</p>
