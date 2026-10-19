import sys
import math
import asyncio
import io
import threading
import time
import os
import json
from typing import Optional, Tuple, List, Dict

from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QRect, pyqtSignal, QObject
from PyQt6.QtGui import (
    QPainter, QColor, QFont, QBrush, QPen, QPainterPath, QPixmap, QImage,
    QCursor, QIcon, QLinearGradient, QAction
)
from PyQt6.QtWidgets import QApplication, QWidget, QSystemTrayIcon, QMenu, QTextEdit, QPushButton
import psutil

import winrt.windows.media.control as wmc
import winrt.windows.storage.streams as streams
from PIL import Image


def extract_dominant_color(pil_img: Image.Image) -> Tuple[int, int, int]:
    """Ekstraksi warna mayoritas dan vibran dari cover album musik"""
    try:
        small = pil_img.convert("RGB").resize((48, 48), Image.Resampling.BILINEAR)
        colors = small.getcolors(48 * 48)
        if not colors:
            return (30, 215, 96)

        best_color = None
        max_score = -1.0

        for count, (r, g, b) in colors:
            brightness = (r * 299 + g * 587 + b * 114) / 1000
            if brightness < 25 or brightness > 235:
                continue

            max_c = max(r, g, b)
            min_c = min(r, g, b)
            saturation = (max_c - min_c) / (max_c + 1e-5)

            score = (saturation ** 1.4) * 3.5 + (count / (48 * 48))
            if score > max_score:
                max_score = score
                best_color = (r, g, b)

        if best_color:
            return best_color
        return colors[0][1]
    except Exception:
        return (30, 215, 96)


class MediaWatcher(QObject):
    media_updated = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self._running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    def _run_loop(self):
        asyncio.run(self._watch_media())

    async def _watch_media(self):
        while self._running:
            try:
                manager = await wmc.GlobalSystemMediaTransportControlsSessionManager.request_async()
                session = manager.get_current_session()
                if session:
                    media_props = await session.try_get_media_properties_async()
                    timeline = session.get_timeline_properties()
                    playback_info = session.get_playback_info()

                    title = media_props.title if media_props else ""
                    artist = media_props.artist if media_props else ""

                    is_playing = False
                    if playback_info:
                        status = playback_info.playback_status
                        is_playing = (status == wmc.GlobalSystemMediaTransportControlsSessionPlaybackStatus.PLAYING)

                    pos_sec = timeline.position.total_seconds() if timeline and timeline.position else 0.0
                    end_sec = timeline.end_time.total_seconds() if timeline and timeline.end_time else 0.0

                    thumb_bytes = None
                    dominant_color = (30, 215, 96)

                    if media_props and media_props.thumbnail:
                        stream = await media_props.thumbnail.open_read_async()
                        size = stream.size
                        if size > 0:
                            reader = streams.DataReader(stream.get_input_stream_at(0))
                            await reader.load_async(size)
                            buf = bytearray(size)
                            reader.read_bytes(buf)
                            thumb_bytes = bytes(buf)
                            try:
                                pil_img = Image.open(io.BytesIO(thumb_bytes))
                                dominant_color = extract_dominant_color(pil_img)
                            except Exception:
                                dominant_color = (30, 215, 96)

                    data = {
                        "has_media": bool(title),
                        "title": title or "Tidak ada lagu",
                        "artist": artist or "Unknown Artist",
                        "is_playing": is_playing,
                        "position": pos_sec,
                        "duration": end_sec,
                        "thumbnail": thumb_bytes,
                        "dominant_color": dominant_color,
                        "session": session
                    }
                    self.media_updated.emit(data)
                else:
                    self.media_updated.emit({
                        "has_media": False,
                        "title": "",
                        "artist": "",
                        "is_playing": False,
                        "position": 0,
                        "duration": 0,
                        "thumbnail": None,
                        "dominant_color": (30, 215, 96),
                        "session": None
                    })
            except Exception:
                pass

            await asyncio.sleep(0.5)

    def stop(self):
        self._running = False


class DynamicIsland(QWidget):
    # 4 Fitur Panel
    MODE_MUSIC = 0
    MODE_SYSTEM = 1
    MODE_NOTES = 2
    MODE_CLOCK = 3
    MODE_COUNT = 4

    def __init__(self):
        super().__init__()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        # Dimensi Pulau
        self.compact_w = 270
        self.compact_h = 36
        self.tucked_w = 120
        self.tucked_h = 10
        self.expanded_w = 345
        self.expanded_h = 180
        self.is_expanded = False
        self.is_tucked = False

        # Mode Tab Saat Ini
        self.current_mode = self.MODE_MUSIC

        # Media state
        self.current_title = ""
        self.current_artist = ""
        self.is_playing = False
        self.position = 0.0
        self.duration = 0.0
        self.album_art_pixmap = None
        self.current_session = None

        # System Hardware Stats
        self.cpu_percent = 0.0
        self.ram_percent = 0.0
        self.ram_used_gb = 0.0
        self.ram_total_gb = 0.0
        self.battery_percent = 100
        self.battery_charging = False
        self.has_battery = False

        # Quick Note Persisten File (Format JSON Multi-Note)
        self.notes_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "quick_notes.json")
        self.notes_data: List[str] = [""]
        self.active_note_idx = 0
        self._load_saved_notes()

        # Tab Selector Tombol Note (Note 1, Note 2, Note 3... + Add Tab)
        self.note_tab_buttons: List[QPushButton] = []
        for i in range(5):
            t_btn = QPushButton(f"Note {i+1}", self)
            t_btn.setGeometry(18 + i * 52, 40, 48, 22)
            t_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            t_btn.clicked.connect(lambda checked, idx=i: self._select_note_tab(idx))
            t_btn.hide()
            self.note_tab_buttons.append(t_btn)

        # Tombol Tambah Note (+)
        self.btn_add_note = QPushButton("+", self)
        self.btn_add_note.setGeometry(18 + len(self.notes_data) * 52, 40, 24, 22)
        self.btn_add_note.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add_note.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 18);
                color: #FFFFFF;
                border: 1px solid rgba(255, 255, 255, 30);
                border-radius: 5px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 45);
                border: 1px solid rgba(255, 255, 255, 70);
            }
        """)
        self.btn_add_note.clicked.connect(self._add_new_note)
        self.btn_add_note.hide()

        # Quick Note Editor Widget (Modern Glassmorphism)
        self.note_edit = QTextEdit(self)
        self.note_edit.setGeometry(18, 67, self.expanded_w - 36, 75)
        self.note_edit.setPlaceholderText("Tulis catatan di sini... (otomatis tersimpan)")
        self.note_edit.setText(self.notes_data[self.active_note_idx])
        self.note_edit.textChanged.connect(self._on_note_changed)
        self.note_edit.setStyleSheet("""
            QTextEdit {
                background-color: rgba(255, 255, 255, 12);
                color: #FFFFFF;
                border: 1px solid rgba(255, 255, 255, 25);
                border-radius: 7px;
                padding: 6px 8px;
                font-family: 'Segoe UI';
                font-size: 11px;
                selection-background-color: rgba(255, 255, 255, 60);
            }
            QTextEdit:focus {
                border: 1px solid rgba(255, 255, 255, 75);
                background-color: rgba(255, 255, 255, 18);
            }
        """)
        self.note_edit.hide()

        # Tombol Salin (Copy)
        self.copy_note_btn = QPushButton("📋 Salin", self)
        self.copy_note_btn.setGeometry(self.expanded_w - 146, 148, 62, 22)
        self.copy_note_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_note_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 18);
                color: #E2E8F0;
                border: 1px solid rgba(255, 255, 255, 30);
                border-radius: 5px;
                font-size: 10px;
                font-family: 'Segoe UI';
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: rgba(56, 189, 248, 160);
                color: white;
                border: 1px solid rgba(56, 189, 248, 220);
            }
        """)
        self.copy_note_btn.clicked.connect(self._copy_note)
        self.copy_note_btn.hide()

        # Tombol Bersihkan (Clear)
        self.clear_note_btn = QPushButton("🗑️ Hapus", self)
        self.clear_note_btn.setGeometry(self.expanded_w - 78, 148, 60, 22)
        self.clear_note_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_note_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 18);
                color: #E2E8F0;
                border: 1px solid rgba(255, 255, 255, 30);
                border-radius: 5px;
                font-size: 10px;
                font-family: 'Segoe UI';
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: rgba(239, 68, 68, 170);
                color: white;
                border: 1px solid rgba(239, 68, 68, 220);
            }
        """)
        self.clear_note_btn.clicked.connect(self._clear_note)
        self.clear_note_btn.hide()

        # Translucent Icon Bar / Dock di Bagian Atas Kanan
        self.mode_icons = ["🎵", "⚡", "📝", "🕒"]
        self.mode_tooltips = ["Musik", "Sistem", "Catatan", "Jam & Waktu"]
        self.dock_buttons: List[QPushButton] = []
        dock_start_x = self.expanded_w - 18 - (len(self.mode_icons) * 28)
        for i, (ic, tt) in enumerate(zip(self.mode_icons, self.mode_tooltips)):
            btn = QPushButton(ic, self)
            btn.setGeometry(dock_start_x + i * 28, 5, 26, 24)
            btn.setToolTip(tt)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, idx=i: self._switch_to_mode(idx))
            btn.hide()
            self.dock_buttons.append(btn)

        # Interactive Adaptive Colors
        self.target_color = QColor(30, 215, 96)
        self.current_color = QColor(30, 215, 96)

        # Posisi di tengah atas monitor
        screen = QApplication.primaryScreen().geometry()
        self.screen_width = screen.width()
        self.init_x = (self.screen_width - self.compact_w) // 2
        self.init_y = 12
        self.tucked_y = 0

        self.setGeometry(self.init_x, self.init_y, self.compact_w, self.compact_h)

        # Wave & Update Timer
        self.wave_phase = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._on_tick)
        self.timer.start(40)

        # System Stats Polling Timer (1 Detik)
        self.stats_timer = QTimer(self)
        self.stats_timer.timeout.connect(self._update_system_stats)
        self.stats_timer.start(1000)
        self._update_system_stats()

        # Watcher Windows Media
        self.watcher = MediaWatcher()
        self.watcher.media_updated.connect(self._on_media_updated)

        # Animasi Geometry (Expand / Collapse / Tuck)
        self.anim = QPropertyAnimation(self, b"geometry")
        self.anim.setDuration(220)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        # Timers auto-minimize 2 tahap
        self.collapse_timer = QTimer(self)
        self.collapse_timer.setSingleShot(True)
        self.collapse_timer.setInterval(3000)
        self.collapse_timer.timeout.connect(self._on_collapse_timeout)

        self.tuck_timer = QTimer(self)
        self.tuck_timer.setSingleShot(True)
        self.tuck_timer.setInterval(3000)
        self.tuck_timer.timeout.connect(self._on_tuck_timeout)

        # Mouse Polling Timer
        self.mouse_monitor = QTimer(self)
        self.mouse_monitor.timeout.connect(self._check_mouse_hover)
        self.mouse_monitor.start(100)

    def _load_saved_notes(self):
        try:
            if os.path.exists(self.notes_file):
                with open(self.notes_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list) and len(data) > 0:
                        self.notes_data = data
                    else:
                        self.notes_data = [""]
            else:
                # Cek migrasi dari quick_note.txt lama jika ada
                old_txt = os.path.join(os.path.dirname(os.path.abspath(__file__)), "quick_note.txt")
                if os.path.exists(old_txt):
                    with open(old_txt, "r", encoding="utf-8") as f:
                        old_val = f.read()
                        self.notes_data = [old_val] if old_val else [""]
                else:
                    self.notes_data = [""]
        except Exception:
            self.notes_data = [""]
        self.active_note_idx = 0

    def _save_notes_to_disk(self):
        try:
            with open(self.notes_file, "w", encoding="utf-8") as f:
                json.dump(self.notes_data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _on_note_changed(self):
        if 0 <= self.active_note_idx < len(self.notes_data):
            self.notes_data[self.active_note_idx] = self.note_edit.toPlainText()
            self._save_notes_to_disk()

    def _select_note_tab(self, idx: int):
        if 0 <= idx < len(self.notes_data):
            self.active_note_idx = idx
            self.note_edit.blockSignals(True)
            self.note_edit.setText(self.notes_data[idx])
            self.note_edit.blockSignals(False)
            self._update_note_tab_styles()

    def _add_new_note(self):
        if len(self.notes_data) < 5:
            self.notes_data.append("")
            self.active_note_idx = len(self.notes_data) - 1
            self.note_edit.blockSignals(True)
            self.note_edit.clear()
            self.note_edit.blockSignals(False)
            self._save_notes_to_disk()
            self._sync_mode_widgets()

    def _copy_note(self):
        text = self.note_edit.toPlainText()
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(text)
        # Visual Feedback pada tombol copy
        self.copy_note_btn.setText("✓ Tersalin!")
        QTimer.singleShot(1200, lambda: self.copy_note_btn.setText("📋 Salin"))

    def _clear_note(self):
        self.note_edit.clear()
        self._on_note_changed()

    def _update_note_tab_styles(self):
        for i, btn in enumerate(self.note_tab_buttons):
            if i < len(self.notes_data):
                is_active = (i == self.active_note_idx)
                if is_active:
                    btn.setStyleSheet("""
                        QPushButton {
                            background-color: rgba(255, 255, 255, 45);
                            color: #FFFFFF;
                            border: 1px solid rgba(255, 255, 255, 90);
                            border-radius: 5px;
                            font-size: 10px;
                            font-family: 'Segoe UI';
                            font-weight: bold;
                        }
                    """)
                else:
                    btn.setStyleSheet("""
                        QPushButton {
                            background-color: rgba(255, 255, 255, 12);
                            color: #CBD5E1;
                            border: 1px solid rgba(255, 255, 255, 25);
                            border-radius: 5px;
                            font-size: 10px;
                            font-family: 'Segoe UI';
                        }
                        QPushButton:hover {
                            background-color: rgba(255, 255, 255, 28);
                            color: #FFFFFF;
                        }
                    """)

    def _switch_to_mode(self, mode_idx: int):
        if 0 <= mode_idx < self.MODE_COUNT:
            self.current_mode = mode_idx
            self._sync_mode_widgets()
            self.update()

    def _sync_mode_widgets(self):
        """Menampilkan atau menyembunyikan widget sesuai mode aktif"""
        if self.is_expanded:
            # Tampilkan dan style Dock Icon Buttons
            for i, btn in enumerate(self.dock_buttons):
                btn.show()
                btn.raise_()
                is_active = (i == self.current_mode)
                if is_active:
                    btn.setStyleSheet("""
                        QPushButton {
                            background-color: rgba(255, 255, 255, 40);
                            color: #FFFFFF;
                            border: 1px solid rgba(255, 255, 255, 75);
                            border-radius: 6px;
                            font-size: 12px;
                        }
                    """)
                else:
                    btn.setStyleSheet("""
                        QPushButton {
                            background-color: transparent;
                            color: rgba(255, 255, 255, 120);
                            border: 1px solid transparent;
                            border-radius: 6px;
                            font-size: 12px;
                        }
                        QPushButton:hover {
                            background-color: rgba(255, 255, 255, 22);
                            color: #FFFFFF;
                            border: 1px solid rgba(255, 255, 255, 45);
                        }
                    """)

            if self.current_mode == self.MODE_NOTES:
                for i, btn in enumerate(self.note_tab_buttons):
                    if i < len(self.notes_data):
                        btn.show()
                        btn.raise_()
                    else:
                        btn.hide()

                if len(self.notes_data) < 5:
                    self.btn_add_note.setGeometry(18 + len(self.notes_data) * 52, 40, 24, 22)
                    self.btn_add_note.show()
                    self.btn_add_note.raise_()
                else:
                    self.btn_add_note.hide()

                self._update_note_tab_styles()
                self.note_edit.show()
                self.copy_note_btn.show()
                self.clear_note_btn.show()
                self.note_edit.raise_()
                self.copy_note_btn.raise_()
                self.clear_note_btn.raise_()
            else:
                for btn in self.note_tab_buttons:
                    btn.hide()
                self.btn_add_note.hide()
                self.note_edit.hide()
                self.copy_note_btn.hide()
                self.clear_note_btn.hide()
        else:
            for btn in self.dock_buttons:
                btn.hide()
            for btn in self.note_tab_buttons:
                btn.hide()
            self.btn_add_note.hide()
            self.note_edit.hide()
            self.copy_note_btn.hide()
            self.clear_note_btn.hide()

    def _update_system_stats(self):
        """Memperbarui informasi CPU, RAM, dan Baterai"""
        try:
            self.cpu_percent = psutil.cpu_percent()
            vmem = psutil.virtual_memory()
            self.ram_percent = vmem.percent
            self.ram_used_gb = vmem.used / (1024 ** 3)
            self.ram_total_gb = vmem.total / (1024 ** 3)

            batt = psutil.sensors_battery()
            if batt:
                self.has_battery = True
                self.battery_percent = int(batt.percent)
                self.battery_charging = batt.power_plugged
            else:
                self.has_battery = False
        except Exception:
            pass

    def _check_mouse_hover(self):
        """Memonitor posisi kursor global terhadap area Dynamic Island"""
        global_pos = QCursor.pos()
        is_inside = self.frameGeometry().contains(global_pos)

        # Jangan collapse jika user sedang mengetik di note editor
        if self.note_edit.hasFocus():
            if self.collapse_timer.isActive():
                self.collapse_timer.stop()
            return

        if self.is_tucked:
            if is_inside:
                self.untuck_to_compact()
        elif not self.is_expanded:
            if is_inside:
                if self.tuck_timer.isActive():
                    self.tuck_timer.stop()
                self.expand_island()
            else:
                if not self.tuck_timer.isActive():
                    self.tuck_timer.start(3000)
        else:
            if is_inside:
                if self.collapse_timer.isActive():
                    self.collapse_timer.stop()
                if self.tuck_timer.isActive():
                    self.tuck_timer.stop()
            else:
                if not self.collapse_timer.isActive():
                    self.collapse_timer.start(3000)

    def _on_tick(self):
        if self.is_playing:
            self.wave_phase = (self.wave_phase + 1) % 360
            self.position += 0.04
        self._smooth_color_step()
        self.update()

    def _smooth_color_step(self):
        cr, cg, cb = self.current_color.red(), self.current_color.green(), self.current_color.blue()
        tr, tg, tb = self.target_color.red(), self.target_color.green(), self.target_color.blue()
        self.current_color = QColor(
            int(cr + (tr - cr) * 0.14),
            int(cg + (tg - cg) * 0.14),
            int(cb + (tb - cb) * 0.14)
        )

    def _on_media_updated(self, data):
        new_title = data["title"]
        new_artist = data["artist"]
        self.is_playing = data["is_playing"]
        self.current_session = data["session"]

        if abs(self.position - data["position"]) > 1.5:
            self.position = data["position"]
        self.duration = max(data["duration"], 1.0)

        r, g, b = data["dominant_color"]
        self.target_color = QColor(r, g, b)

        if data["thumbnail"]:
            qimg = QImage.fromData(data["thumbnail"])
            self.album_art_pixmap = QPixmap.fromImage(qimg)
        else:
            self.album_art_pixmap = None

        self.current_title = new_title
        self.current_artist = new_artist
        self.update()

    def _on_collapse_timeout(self):
        global_cursor_pos = QCursor.pos()
        if not self.frameGeometry().contains(global_cursor_pos) and not self.note_edit.hasFocus():
            self.collapse_island()

    def _on_tuck_timeout(self):
        global_cursor_pos = QCursor.pos()
        if not self.is_expanded and not self.frameGeometry().contains(global_cursor_pos):
            self.tuck_island()

    def untuck_to_compact(self):
        self.is_tucked = False
        self.is_expanded = False
        self._sync_mode_widgets()
        new_x = (self.screen_width - self.compact_w) // 2
        self.anim.stop()
        self.anim.setStartValue(self.geometry())
        self.anim.setEndValue(QRect(new_x, self.init_y, self.compact_w, self.compact_h))
        self.anim.start()
        self.tuck_timer.start(3000)

    def enterEvent(self, event):
        self.collapse_timer.stop()
        self.tuck_timer.stop()
        if self.is_tucked:
            self.untuck_to_compact()
        elif not self.is_expanded:
            self.expand_island()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self.is_expanded:
            if not self.note_edit.hasFocus():
                self.collapse_timer.start(3000)
        elif not self.is_tucked:
            self.tuck_timer.start(3000)
        super().leaveEvent(event)

    def expand_island(self):
        self.is_tucked = False
        self.is_expanded = True
        self.collapse_timer.stop()
        self.tuck_timer.stop()
        new_x = (self.screen_width - self.expanded_w) // 2
        self.anim.stop()
        self.anim.setStartValue(self.geometry())
        self.anim.setEndValue(QRect(new_x, self.init_y, self.expanded_w, self.expanded_h))
        self.anim.start()
        self._sync_mode_widgets()

    def collapse_island(self):
        self.is_expanded = False
        self.collapse_timer.stop()
        self._sync_mode_widgets()
        new_x = (self.screen_width - self.compact_w) // 2
        self.anim.stop()
        self.anim.setStartValue(self.geometry())
        self.anim.setEndValue(QRect(new_x, self.init_y, self.compact_w, self.compact_h))
        self.anim.start()
        self.tuck_timer.start(3000)

    def tuck_island(self):
        self.is_tucked = True
        self.is_expanded = False
        self.tuck_timer.stop()
        self.collapse_timer.stop()
        self._sync_mode_widgets()
        new_x = (self.screen_width - self.tucked_w) // 2
        self.anim.stop()
        self.anim.setStartValue(self.geometry())
        self.anim.setEndValue(QRect(new_x, self.tucked_y, self.tucked_w, self.tucked_h))
        self.anim.start()

    def mousePressEvent(self, event):
        pos = event.pos()

        if self.is_tucked:
            self.untuck_to_compact()
            return

        if not self.is_expanded:
            self.expand_island()
            return

        if self.is_expanded:
            # Tombol Tutup (X) di Pojok Kiri Atas
            if 10 <= pos.x() <= 34 and 10 <= pos.y() <= 34:
                self.collapse_island()
                return

            # Kontrol Khusus Mode Musik
            if self.current_mode == self.MODE_MUSIC:
                btn_y = 144
                center_x = self.expanded_w // 2
                # Prev Button
                if (center_x - 55) <= pos.x() <= (center_x - 25) and (btn_y - 15) <= pos.y() <= (btn_y + 15):
                    self._send_media_cmd("prev")
                    return
                # Play / Pause
                elif (center_x - 20) <= pos.x() <= (center_x + 20) and (btn_y - 16) <= pos.y() <= (btn_y + 16):
                    self._send_media_cmd("toggle")
                    return
                # Next Button
                elif (center_x + 25) <= pos.x() <= (center_x + 55) and (btn_y - 15) <= pos.y() <= (btn_y + 15):
                    self._send_media_cmd("next")
                    return

        super().mousePressEvent(event)

    def _send_media_cmd(self, cmd: str):
        if not self.current_session:
            return
        async def _cmd():
            try:
                if cmd == "toggle":
                    await self.current_session.try_toggle_play_pause_async()
                elif cmd == "next":
                    await self.current_session.try_skip_next_async()
                elif cmd == "prev":
                    await self.current_session.try_skip_previous_async()
            except Exception:
                pass
        threading.Thread(target=lambda: asyncio.run(_cmd()), daemon=True).start()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        path = QPainterPath()
        corner_radius = min(h / 2, 28)
        path.addRoundedRect(0, 0, w, h, corner_radius, corner_radius)

        r, g, b = self.current_color.red(), self.current_color.green(), self.current_color.blue()

        gradient = QLinearGradient(0, 0, 0, h)
        top_color = QColor(int(r * 0.85), int(g * 0.85), int(b * 0.85), 245)
        bottom_color = QColor(int(r * 0.20) + 12, int(g * 0.20) + 12, int(b * 0.20) + 14, 250)

        gradient.setColorAt(0.0, top_color)
        gradient.setColorAt(1.0, bottom_color)

        painter.fillPath(path, QBrush(gradient))

        glow_color = QColor(min(r + 50, 255), min(g + 50, 255), min(b + 50, 255), 180)
        painter.setPen(QPen(glow_color, 1.2))
        painter.drawPath(path)

        if self.is_tucked:
            painter.setPen(Qt.PenStyle.NoPen)
            accent_bar = QColor(min(r + 60, 255), min(g + 60, 255), min(b + 60, 255), 210)
            painter.setBrush(QBrush(accent_bar))
            bar_w = 40
            bar_x = (w - bar_w) // 2
            painter.drawRoundedRect(bar_x, 3, bar_w, 4, 2, 2)
        elif not self.is_expanded:
            self._draw_compact(painter, w, h)
        else:
            self._draw_expanded(painter, w, h)

    def _draw_compact(self, painter: QPainter, w: int, h: int):
        thumb_size = 24
        thumb_x = 8
        thumb_y = (h - thumb_size) // 2

        if self.album_art_pixmap:
            thumb_path = QPainterPath()
            thumb_path.addRoundedRect(thumb_x, thumb_y, thumb_size, thumb_size, 6, 6)
            painter.save()
            painter.setClipPath(thumb_path)
            painter.drawPixmap(thumb_x, thumb_y, thumb_size, thumb_size,
                               self.album_art_pixmap.scaled(thumb_size, thumb_size,
                                                           Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                                           Qt.TransformationMode.SmoothTransformation))
            painter.restore()
        else:
            painter.setBrush(QBrush(QColor(255, 255, 255, 50)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(thumb_x, thumb_y, thumb_size, thumb_size, 6, 6)

        text_x = thumb_x + thumb_size + 8
        text_w = w - text_x - 38

        # Mode Compact: Judul & Artis (jika ada)
        if self.current_artist:
            font_title = QFont("Segoe UI", 8)
            font_title.setWeight(QFont.Weight.DemiBold)
            painter.setFont(font_title)
            painter.setPen(QColor(255, 255, 255))
            m_t = painter.fontMetrics()
            elided_t = m_t.elidedText(self.current_title or "Dynamic Island", Qt.TextElideMode.ElideRight, text_w)
            painter.drawText(text_x, (h // 2) - 1, elided_t)

            font_art = QFont("Segoe UI", 7)
            painter.setFont(font_art)
            painter.setPen(QColor(200, 205, 215))
            m_a = painter.fontMetrics()
            elided_a = m_a.elidedText(self.current_artist, Qt.TextElideMode.ElideRight, text_w)
            painter.drawText(text_x, (h // 2) + 11, elided_a)
        else:
            font = QFont("Segoe UI", 9)
            font.setWeight(QFont.Weight.DemiBold)
            painter.setFont(font)
            painter.setPen(QColor(255, 255, 255))
            title_display = self.current_title or "Dynamic Island"
            metrics = painter.fontMetrics()
            elided = metrics.elidedText(title_display, Qt.TextElideMode.ElideRight, text_w)
            painter.drawText(text_x, (h // 2) + 4, elided)

        wave_x = w - 30
        bar_w = 2
        spacing = 2
        painter.setPen(Qt.PenStyle.NoPen)

        r, g, b = self.current_color.red(), self.current_color.green(), self.current_color.blue()
        visualizer_color = QColor(min(r + 60, 255), min(g + 60, 255), min(b + 60, 255), 240)
        painter.setBrush(QBrush(visualizer_color))

        for i in range(4):
            phase = math.radians(self.wave_phase * 6 + i * 55)
            bar_h = 5 + int(math.sin(phase) * 6) if self.is_playing else 3
            bx = int(wave_x + i * (bar_w + spacing))
            by = int((h - bar_h) // 2)
            painter.drawRoundedRect(bx, by, int(bar_w), int(bar_h), 1.0, 1.0)

    def _draw_expanded(self, painter: QPainter, w: int, h: int):
        # Header: Tombol Tutup (X)
        font_x = QFont("Segoe UI", 10)
        painter.setFont(font_x)
        painter.setPen(QColor(255, 255, 255, 140))
        painter.drawText(16, 23, "✕")

        # Label Nama Fitur Aktif di Kiri Header
        mode_names = ["Pemutar Musik", "Status Sistem", "Catatan Cepat", "Jam & Waktu"]
        cur_name = mode_names[self.current_mode]
        font_brand = QFont("Segoe UI", 9)
        font_brand.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font_brand)
        painter.setPen(QColor(255, 255, 255, 220))
        painter.drawText(36, 22, cur_name)

        # Garis tipis pembatas header
        painter.setPen(QPen(QColor(255, 255, 255, 25), 1))
        painter.drawLine(16, 32, w - 16, 32)

        # Konten Mode
        if self.current_mode == self.MODE_MUSIC:
            self._draw_mode_music(painter, w, h)
        elif self.current_mode == self.MODE_SYSTEM:
            self._draw_mode_system(painter, w, h)
        elif self.current_mode == self.MODE_NOTES:
            self._draw_mode_notes(painter, w, h)
        elif self.current_mode == self.MODE_CLOCK:
            self._draw_mode_clock(painter, w, h)

    def _draw_mode_music(self, painter: QPainter, w: int, h: int):
        art_size = 56
        art_x = 20
        art_y = 44

        if self.album_art_pixmap:
            art_path = QPainterPath()
            art_path.addRoundedRect(art_x, art_y, art_size, art_size, 10, 10)
            painter.save()
            painter.setClipPath(art_path)
            painter.drawPixmap(art_x, art_y, art_size, art_size,
                               self.album_art_pixmap.scaled(art_size, art_size,
                                                           Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                                           Qt.TransformationMode.SmoothTransformation))
            painter.restore()
        else:
            painter.setBrush(QBrush(QColor(255, 255, 255, 30)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(art_x, art_y, art_size, art_size, 10, 10)

        info_x = art_x + art_size + 14
        info_w = w - info_x - 20

        # Judul Lagu (Bold, Putih Bersih)
        font_title = QFont("Segoe UI", 11)
        font_title.setBold(True)
        painter.setFont(font_title)
        painter.setPen(QColor(255, 255, 255))
        m_title = painter.fontMetrics()
        elided_title = m_title.elidedText(self.current_title or "Tidak ada lagu aktif", Qt.TextElideMode.ElideRight, info_w)
        painter.drawText(info_x, art_y + 20, elided_title)

        # Nama Artis (Terang & Jelas dengan Ikon Artis/Badge)
        font_artist = QFont("Segoe UI", 9)
        font_artist.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font_artist)
        painter.setPen(QColor(225, 230, 240))
        m_artist = painter.fontMetrics()
        display_artist = self.current_artist if self.current_artist else "Spotify / YouTube Music"
        elided_artist = m_artist.elidedText(f"👤 {display_artist}", Qt.TextElideMode.ElideRight, info_w)
        painter.drawText(info_x, art_y + 40, elided_artist)

        # Bar Durasi
        prog_x = 20
        prog_y = 110
        prog_w = w - 40
        prog_h = 3

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(255, 255, 255, 50)))
        painter.drawRoundedRect(prog_x, prog_y, prog_w, prog_h, 1.5, 1.5)

        progress_ratio = max(0.0, min(1.0, (self.position / self.duration) if self.duration > 0 else 0.0))
        fill_w = int(prog_w * progress_ratio)
        painter.setBrush(QBrush(QColor(255, 255, 255)))
        painter.drawRoundedRect(prog_x, prog_y, fill_w, prog_h, 1.5, 1.5)

        def fmt_time(s):
            m = int(s) // 60
            sec = int(s) % 60
            return f"{m}:{sec:02d}"

        font_time = QFont("Segoe UI", 7)
        painter.setFont(font_time)
        painter.setPen(QColor(210, 210, 215))
        painter.drawText(prog_x, prog_y + 12, fmt_time(self.position))
        painter.drawText(prog_x + prog_w - 24, prog_y + 12, fmt_time(self.duration))

        # Kontrol Playback di Tengah
        center_x = w // 2
        btn_y = 144

        # Prev
        painter.setPen(QPen(QColor(255, 255, 255), 2))
        painter.drawLine(center_x - 36, btn_y - 6, center_x - 44, btn_y)
        painter.drawLine(center_x - 44, btn_y, center_x - 36, btn_y + 6)
        painter.drawLine(center_x - 44, btn_y - 6, center_x - 44, btn_y + 6)

        # Play / Pause
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(255, 255, 255)))
        painter.drawEllipse(center_x - 13, btn_y - 13, 26, 26)

        painter.setBrush(QBrush(QColor(15, 15, 15)))
        if self.is_playing:
            painter.drawRect(center_x - 4, btn_y - 5, 3, 10)
            painter.drawRect(center_x + 2, btn_y - 5, 3, 10)
        else:
            tri = QPainterPath()
            tri.moveTo(center_x - 2, btn_y - 5)
            tri.lineTo(center_x + 5, btn_y)
            tri.lineTo(center_x - 2, btn_y + 5)
            tri.closeSubpath()
            painter.drawPath(tri)

        # Next
        painter.setPen(QPen(QColor(255, 255, 255), 2))
        painter.drawLine(center_x + 36, btn_y - 6, center_x + 44, btn_y)
        painter.drawLine(center_x + 44, btn_y, center_x + 36, btn_y + 6)
        painter.drawLine(center_x + 44, btn_y - 6, center_x + 44, btn_y + 6)

    def _draw_mode_system(self, painter: QPainter, w: int, h: int):
        """Mode 2: Info Hardware Profesional (Card Layout & Subtitle Ringkas)"""
        x = 18
        card_w = w - 36
        start_y = 42

        # Card 1: CPU
        self._draw_sys_card(
            painter, x, start_y, card_w, 36,
            title="CPU Load",
            subtitle=f"{self.cpu_percent:.0f}%",
            progress=self.cpu_percent / 100.0,
            bar_color=QColor(56, 189, 248)  # Sky Blue
        )

        # Card 2: RAM Memory
        start_y += 42
        ram_sub = f"{self.ram_used_gb:.1f} / {self.ram_total_gb:.0f} GB  ({self.ram_percent:.0f}%)"
        self._draw_sys_card(
            painter, x, start_y, card_w, 36,
            title="Memory RAM",
            subtitle=ram_sub,
            progress=self.ram_percent / 100.0,
            bar_color=QColor(168, 85, 247)  # Purple
        )

        # Card 3: Battery / Power
        start_y += 42
        if self.has_battery:
            batt_sub = f"{self.battery_percent}% {'⚡ Mengisi Daya' if self.battery_charging else 'Baterai'}"
            batt_col = QColor(34, 197, 94) if self.battery_percent > 20 else QColor(239, 68, 68)
        else:
            batt_sub = "AC Power Connected"
            batt_col = QColor(34, 197, 94)
        self._draw_sys_card(
            painter, x, start_y, card_w, 36,
            title="Daya Baterai" if self.has_battery else "Status Daya",
            subtitle=batt_sub,
            progress=(self.battery_percent / 100.0) if self.has_battery else 1.0,
            bar_color=batt_col
        )

    def _draw_sys_card(self, painter: QPainter, x: int, y: int, w: int, h: int, title: str, subtitle: str, progress: float, bar_color: QColor):
        """Helper menggambar kartu hardware profesional dengan track bar elegan"""
        # Card Background
        painter.setPen(QPen(QColor(255, 255, 255, 22), 1))
        painter.setBrush(QBrush(QColor(255, 255, 255, 10)))
        painter.drawRoundedRect(x, y, w, h, 7, 7)

        # Judul & Nilai Persentase
        font_t = QFont("Segoe UI", 8)
        font_t.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font_t)
        painter.setPen(QColor(245, 245, 245))
        painter.drawText(x + 10, y + 16, title)

        font_s = QFont("Segoe UI", 7)
        painter.setFont(font_s)
        painter.setPen(QColor(200, 200, 210))
        m_s = painter.fontMetrics()
        sub_w = m_s.horizontalAdvance(subtitle)
        painter.drawText(x + w - sub_w - 10, y + 16, subtitle)

        # Progress Track
        track_y = y + 23
        track_w = w - 20
        track_h = 4
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(255, 255, 255, 25)))
        painter.drawRoundedRect(x + 10, track_y, track_w, track_h, 2, 2)

        # Progress Fill
        fill_w = max(4, int(track_w * max(0.0, min(1.0, progress))))
        painter.setBrush(QBrush(bar_color))
        painter.drawRoundedRect(x + 10, track_y, fill_w, track_h, 2, 2)

    def _draw_mode_notes(self, painter: QPainter, w: int, h: int):
        """Mode 3: Quick Note Persisten Multi-Tab"""
        font_h = QFont("Segoe UI", 7)
        painter.setFont(font_h)
        painter.setPen(QColor(255, 255, 255, 140))
        painter.drawText(20, 163, f"💾 Note {self.active_note_idx + 1} • Tersimpan otomatis")

    def _draw_mode_clock(self, painter: QPainter, w: int, h: int):
        """Mode 4: Jam Digital Modern & Kalender"""
        now = time.localtime()
        time_str = time.strftime("%H:%M:%S", now)
        date_str = time.strftime("%A, %d %B %Y", now)

        font_clock = QFont("Segoe UI", 28)
        font_clock.setBold(True)
        painter.setFont(font_clock)
        painter.setPen(QColor(255, 255, 255))
        m_c = painter.fontMetrics()
        cw = m_c.horizontalAdvance(time_str)
        painter.drawText((w - cw) // 2, 100, time_str)

        font_date = QFont("Segoe UI", 10)
        painter.setFont(font_date)
        painter.setPen(QColor(230, 230, 235))
        m_d = painter.fontMetrics()
        dw = m_d.horizontalAdvance(date_str)
        painter.drawText((w - dw) // 2, 132, date_str)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    icon_path = "C:/Users/PLN/DynamicIsland/app_icon.ico"
    app_icon = QIcon(icon_path)
    app.setWindowIcon(app_icon)

    island = DynamicIsland()
    island.show()

    tray = QSystemTrayIcon(app_icon, app)
    tray.setToolTip("Dynamic Island Multi-Widget")

    menu = QMenu()
    toggle_action = QAction("Tampilkan / Sembunyikan", app)
    def toggle_visibility():
        if island.isVisible():
            island.hide()
        else:
            island.show()
    toggle_action.triggered.connect(toggle_visibility)
    menu.addAction(toggle_action)

    menu.addSeparator()

    quit_action = QAction("Keluar (Exit)", app)
    quit_action.triggered.connect(app.quit)
    menu.addAction(quit_action)

    tray.setContextMenu(menu)
    def on_tray_activated(reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            toggle_visibility()
    tray.activated.connect(on_tray_activated)
    tray.show()

    sys.exit(app.exec())
