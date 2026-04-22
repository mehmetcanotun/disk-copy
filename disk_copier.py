#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Disk Kullanıcı Verileri Kopyalama Aracı
Bir diskteki kullanıcı verilerini başka bir diske kopyalar.
"""

import sys
import os
import shutil
import time
import threading
from pathlib import Path
from datetime import datetime

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QProgressBar, QTextEdit, QFileDialog,
    QGroupBox, QCheckBox, QComboBox, QMessageBox, QFrame,
    QSplitter, QStatusBar, QGridLayout
)
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QTimer
from PyQt5.QtGui import QFont, QIcon, QColor, QPalette


class CopySignals(QObject):
    """Thread-safe sinyaller"""
    progress = pyqtSignal(int)
    status = pyqtSignal(str)
    log = pyqtSignal(str, str)  # message, level
    finished = pyqtSignal(bool, str)
    file_count_update = pyqtSignal(int, int, str)  # current, total, filename
    speed_update = pyqtSignal(str)


class DiskCopier(threading.Thread):
    """Arka planda dosya kopyalama işlemi"""

    def __init__(self, source, destination, options, signals):
        super().__init__(daemon=True)
        self.source = source
        self.destination = destination
        self.options = options
        self.signals = signals
        self._stop_event = threading.Event()
        self.total_files = 0
        self.copied_files = 0
        self.total_size = 0
        self.copied_size = 0
        self.skipped_files = 0
        self.error_files = 0
        self.start_time = 0

    def stop(self):
        self._stop_event.set()

    def is_stopped(self):
        return self._stop_event.is_set()

    def _count_files(self, path):
        """Toplam dosya sayısını ve boyutunu hesapla"""
        count = 0
        size = 0
        try:
            for root, dirs, files in os.walk(path):
                if self.is_stopped():
                    return count, size
                # Gizli dosyaları atla (opsiyonel)
                if not self.options.get('include_hidden', False):
                    dirs[:] = [d for d in dirs if not d.startswith('.')]
                    files = [f for f in files if not f.startswith('.')]

                for f in files:
                    filepath = os.path.join(root, f)
                    try:
                        size += os.path.getsize(filepath)
                        count += 1
                    except (OSError, PermissionError):
                        pass
        except (OSError, PermissionError):
            pass
        return count, size

    def _format_size(self, size_bytes):
        """Boyutu okunabilir formata çevir"""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 ** 2:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 ** 3:
            return f"{size_bytes / (1024**2):.1f} MB"
        else:
            return f"{size_bytes / (1024**3):.2f} GB"

    def _format_time(self, seconds):
        """Süreyi okunabilir formata çevir"""
        if seconds < 60:
            return f"{int(seconds)} saniye"
        elif seconds < 3600:
            m, s = divmod(int(seconds), 60)
            return f"{m} dk {s} sn"
        else:
            h, remainder = divmod(int(seconds), 3600)
            m, s = divmod(remainder, 60)
            return f"{h} sa {m} dk {s} sn"

    def run(self):
        try:
            self.start_time = time.time()
            self.signals.status.emit("Dosyalar taranıyor...")
            self.signals.log.emit("Kaynak klasör taranıyor: " + self.source, "info")

            # Dosya sayısını hesapla
            self.total_files, self.total_size = self._count_files(self.source)

            if self.total_files == 0:
                self.signals.finished.emit(False, "Kaynak klasörde kopyalanacak dosya bulunamadı!")
                return

            self.signals.log.emit(
                f"Toplam {self.total_files} dosya bulundu ({self._format_size(self.total_size)})",
                "info"
            )
            self.signals.status.emit(f"Kopyalanıyor... 0/{self.total_files}")

            # Kopyalama işlemi
            for root, dirs, files in os.walk(self.source):
                if self.is_stopped():
                    self.signals.finished.emit(False, "Kopyalama kullanıcı tarafından iptal edildi.")
                    return

                # Gizli dosyaları atla
                if not self.options.get('include_hidden', False):
                    dirs[:] = [d for d in dirs if not d.startswith('.')]
                    files = [f for f in files if not f.startswith('.')]

                # Hedef klasör yolunu oluştur
                rel_path = os.path.relpath(root, self.source)
                dest_dir = os.path.join(self.destination, rel_path)

                # Hedef klasörü oluştur
                try:
                    os.makedirs(dest_dir, exist_ok=True)
                except (OSError, PermissionError) as e:
                    self.signals.log.emit(f"Klasör oluşturulamadı: {dest_dir} - {e}", "error")
                    continue

                for filename in files:
                    if self.is_stopped():
                        self.signals.finished.emit(False, "Kopyalama kullanıcı tarafından iptal edildi.")
                        return

                    src_file = os.path.join(root, filename)
                    dst_file = os.path.join(dest_dir, filename)

                    try:
                        file_size = os.path.getsize(src_file)

                        # Üzerine yazma kontrolü
                        if os.path.exists(dst_file) and not self.options.get('overwrite', True):
                            # Sadece daha yeni dosyaları kopyala
                            if self.options.get('skip_existing', False):
                                self.skipped_files += 1
                                self.copied_files += 1
                                self._update_progress(filename)
                                continue
                            elif self.options.get('newer_only', False):
                                src_mtime = os.path.getmtime(src_file)
                                dst_mtime = os.path.getmtime(dst_file)
                                if src_mtime <= dst_mtime:
                                    self.skipped_files += 1
                                    self.copied_files += 1
                                    self._update_progress(filename)
                                    continue

                        # Dosyayı kopyala
                        shutil.copy2(src_file, dst_file)
                        self.copied_size += file_size
                        self.copied_files += 1
                        self._update_progress(filename)

                    except PermissionError:
                        self.error_files += 1
                        self.copied_files += 1
                        self.signals.log.emit(f"Erişim hatası: {src_file}", "error")
                        self._update_progress(filename)
                    except (OSError, shutil.Error) as e:
                        self.error_files += 1
                        self.copied_files += 1
                        self.signals.log.emit(f"Kopyalama hatası: {src_file} - {e}", "error")
                        self._update_progress(filename)

            # Tamamlandı
            elapsed = time.time() - self.start_time
            summary = (
                f"Kopyalama tamamlandı!\n"
                f"  Toplam: {self.total_files} dosya\n"
                f"  Kopyalanan: {self.copied_files - self.skipped_files - self.error_files}\n"
                f"  Atlanan: {self.skipped_files}\n"
                f"  Hatalı: {self.error_files}\n"
                f"  Boyut: {self._format_size(self.copied_size)}\n"
                f"  Süre: {self._format_time(elapsed)}"
            )
            self.signals.finished.emit(True, summary)

        except Exception as e:
            self.signals.finished.emit(False, f"Beklenmeyen hata: {str(e)}")

    def _update_progress(self, filename):
        """İlerleme durumunu güncelle"""
        if self.total_files > 0:
            progress = int((self.copied_files / self.total_files) * 100)
            self.signals.progress.emit(progress)

        self.signals.file_count_update.emit(self.copied_files, self.total_files, filename)
        self.signals.status.emit(f"Kopyalanıyor... {self.copied_files}/{self.total_files}")

        # Hız hesapla
        elapsed = time.time() - self.start_time
        if elapsed > 0 and self.copied_size > 0:
            speed = self.copied_size / elapsed
            remaining_size = self.total_size - self.copied_size
            if speed > 0:
                eta = remaining_size / speed
                speed_text = f"{self._format_size(int(speed))}/s | Kalan: ~{self._format_time(eta)}"
            else:
                speed_text = "Hesaplanıyor..."
            self.signals.speed_update.emit(speed_text)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.copier = None
        self.signals = CopySignals()
        self._connect_signals()
        self._init_ui()

    def _connect_signals(self):
        self.signals.progress.connect(self._on_progress)
        self.signals.status.connect(self._on_status)
        self.signals.log.connect(self._on_log)
        self.signals.finished.connect(self._on_finished)
        self.signals.file_count_update.connect(self._on_file_count)
        self.signals.speed_update.connect(self._on_speed)

    def _init_ui(self):
        self.setWindowTitle("Disk Veri Kopyalama Aracı")
        self.setMinimumSize(750, 650)
        self.setStyleSheet(self._get_stylesheet())

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(16, 16, 16, 16)

        # ─── Başlık ───
        title_label = QLabel("💾 Disk Veri Kopyalama Aracı")
        title_label.setObjectName("titleLabel")
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)

        # ─── Kaynak & Hedef ───
        paths_group = QGroupBox("Disk Seçimi")
        paths_layout = QGridLayout()
        paths_layout.setSpacing(8)

        # Kaynak
        paths_layout.addWidget(QLabel("Kaynak Disk / Klasör:"), 0, 0)
        self.source_label = QLabel("Seçilmedi")
        self.source_label.setObjectName("pathLabel")
        self.source_label.setMinimumWidth(400)
        paths_layout.addWidget(self.source_label, 0, 1)
        self.btn_source = QPushButton("📂 Seç")
        self.btn_source.setFixedWidth(80)
        self.btn_source.clicked.connect(self._select_source)
        paths_layout.addWidget(self.btn_source, 0, 2)

        # Hedef
        paths_layout.addWidget(QLabel("Hedef Disk / Klasör:"), 1, 0)
        self.dest_label = QLabel("Seçilmedi")
        self.dest_label.setObjectName("pathLabel")
        paths_layout.addWidget(self.dest_label, 1, 1)
        self.btn_dest = QPushButton("📂 Seç")
        self.btn_dest.setFixedWidth(80)
        self.btn_dest.clicked.connect(self._select_destination)
        paths_layout.addWidget(self.btn_dest, 1, 2)

        paths_group.setLayout(paths_layout)
        main_layout.addWidget(paths_group)

        # ─── Seçenekler ───
        options_group = QGroupBox("Kopyalama Seçenekleri")
        options_layout = QHBoxLayout()
        options_layout.setSpacing(16)

        self.chk_hidden = QCheckBox("Gizli dosyaları dahil et")
        self.chk_hidden.setChecked(False)
        options_layout.addWidget(self.chk_hidden)

        self.chk_overwrite = QCheckBox("Var olan dosyaların üzerine yaz")
        self.chk_overwrite.setChecked(True)
        options_layout.addWidget(self.chk_overwrite)

        self.chk_newer = QCheckBox("Sadece yeni dosyaları kopyala")
        self.chk_newer.setChecked(False)
        options_layout.addWidget(self.chk_newer)

        options_layout.addStretch()
        options_group.setLayout(options_layout)
        main_layout.addWidget(options_group)

        # ─── İlerleme ───
        progress_group = QGroupBox("İlerleme Durumu")
        progress_layout = QVBoxLayout()
        progress_layout.setSpacing(6)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")
        self.progress_bar.setMinimumHeight(28)
        progress_layout.addWidget(self.progress_bar)

        info_row = QHBoxLayout()
        self.lbl_file_info = QLabel("Hazır")
        self.lbl_file_info.setObjectName("infoLabel")
        info_row.addWidget(self.lbl_file_info)
        info_row.addStretch()
        self.lbl_speed = QLabel("")
        self.lbl_speed.setObjectName("speedLabel")
        info_row.addWidget(self.lbl_speed)
        progress_layout.addLayout(info_row)

        self.lbl_current_file = QLabel("")
        self.lbl_current_file.setObjectName("currentFileLabel")
        self.lbl_current_file.setWordWrap(True)
        progress_layout.addWidget(self.lbl_current_file)

        progress_group.setLayout(progress_layout)
        main_layout.addWidget(progress_group)

        # ─── Log ───
        log_group = QGroupBox("İşlem Günlüğü")
        log_layout = QVBoxLayout()
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(180)
        self.log_text.setFont(QFont("Consolas", 9))
        log_layout.addWidget(self.log_text)
        log_group.setLayout(log_layout)
        main_layout.addWidget(log_group)

        # ─── Butonlar ───
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_start = QPushButton("▶  Kopyalamayı Başlat")
        self.btn_start.setObjectName("startBtn")
        self.btn_start.setFixedSize(200, 42)
        self.btn_start.clicked.connect(self._start_copy)
        btn_layout.addWidget(self.btn_start)

        self.btn_stop = QPushButton("⏹  Durdur")
        self.btn_stop.setObjectName("stopBtn")
        self.btn_stop.setFixedSize(120, 42)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._stop_copy)
        btn_layout.addWidget(self.btn_stop)

        btn_layout.addStretch()
        main_layout.addLayout(btn_layout)

        # Status bar
        self.statusBar().showMessage("Kaynak ve hedef klasör seçerek başlayın.")

    def _get_stylesheet(self):
        return """
            QMainWindow {
                background-color: #1a1a2e;
            }
            QWidget {
                color: #e0e0e0;
                font-family: 'Segoe UI', Arial;
                font-size: 13px;
            }
            #titleLabel {
                font-size: 22px;
                font-weight: bold;
                color: #00d4ff;
                padding: 8px;
                margin-bottom: 4px;
            }
            QGroupBox {
                border: 1px solid #2a2a4a;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 18px;
                background-color: #16213e;
                font-weight: bold;
                color: #8892b0;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 14px;
                padding: 0 6px;
            }
            #pathLabel {
                background-color: #0f3460;
                border: 1px solid #2a2a4a;
                border-radius: 4px;
                padding: 6px 10px;
                color: #a8d8ea;
            }
            QPushButton {
                background-color: #0f3460;
                border: 1px solid #1a5276;
                border-radius: 6px;
                padding: 6px 14px;
                color: #e0e0e0;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1a5276;
                border-color: #00d4ff;
            }
            QPushButton:pressed {
                background-color: #0a2a4a;
            }
            QPushButton:disabled {
                background-color: #1a1a2e;
                color: #555;
                border-color: #333;
            }
            #startBtn {
                background-color: #00796b;
                border-color: #00897b;
                font-size: 14px;
            }
            #startBtn:hover {
                background-color: #00897b;
                border-color: #00d4ff;
            }
            #stopBtn {
                background-color: #b71c1c;
                border-color: #c62828;
                font-size: 14px;
            }
            #stopBtn:hover {
                background-color: #c62828;
            }
            QProgressBar {
                border: 1px solid #2a2a4a;
                border-radius: 6px;
                background-color: #0f3460;
                text-align: center;
                color: white;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #00796b, stop:1 #00d4ff);
                border-radius: 5px;
            }
            QTextEdit {
                background-color: #0d1b2a;
                border: 1px solid #2a2a4a;
                border-radius: 6px;
                color: #a8d8ea;
                padding: 6px;
            }
            QCheckBox {
                spacing: 6px;
                color: #c0c0c0;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border: 1px solid #4a4a6a;
                border-radius: 3px;
                background-color: #0f3460;
            }
            QCheckBox::indicator:checked {
                background-color: #00796b;
                border-color: #00d4ff;
            }
            #infoLabel {
                color: #8892b0;
                font-size: 12px;
            }
            #speedLabel {
                color: #00d4ff;
                font-size: 12px;
                font-weight: bold;
            }
            #currentFileLabel {
                color: #5c6b7a;
                font-size: 11px;
            }
            QStatusBar {
                background-color: #0d1b2a;
                color: #5c6b7a;
                border-top: 1px solid #2a2a4a;
            }
        """

    def _select_source(self):
        path = QFileDialog.getExistingDirectory(self, "Kaynak Disk/Klasör Seçin")
        if path:
            self.source_label.setText(path)
            self._log(f"Kaynak seçildi: {path}", "info")

    def _select_destination(self):
        path = QFileDialog.getExistingDirectory(self, "Hedef Disk/Klasör Seçin")
        if path:
            self.dest_label.setText(path)
            self._log(f"Hedef seçildi: {path}", "info")

    def _start_copy(self):
        source = self.source_label.text()
        dest = self.dest_label.text()

        if source == "Seçilmedi" or dest == "Seçilmedi":
            QMessageBox.warning(self, "Uyarı", "Lütfen kaynak ve hedef klasörleri seçin!")
            return

        if source == dest:
            QMessageBox.warning(self, "Uyarı", "Kaynak ve hedef aynı olamaz!")
            return

        if not os.path.exists(source):
            QMessageBox.warning(self, "Uyarı", "Kaynak klasör bulunamadı!")
            return

        # Onay
        reply = QMessageBox.question(
            self, "Onay",
            f"Kopyalama başlatılsın mı?\n\n"
            f"Kaynak: {source}\n"
            f"Hedef: {dest}\n\n"
            f"Bu işlem hedef klasördeki aynı adlı dosyaların üzerine yazabilir.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        # Seçenekler
        options = {
            'include_hidden': self.chk_hidden.isChecked(),
            'overwrite': self.chk_overwrite.isChecked(),
            'newer_only': self.chk_newer.isChecked(),
            'skip_existing': not self.chk_overwrite.isChecked() and not self.chk_newer.isChecked(),
        }

        # UI güncelle
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.btn_source.setEnabled(False)
        self.btn_dest.setEnabled(False)
        self.progress_bar.setValue(0)
        self.log_text.clear()

        self._log("═" * 50, "info")
        self._log(f"Kopyalama başlatıldı: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", "info")
        self._log(f"Kaynak: {source}", "info")
        self._log(f"Hedef:  {dest}", "info")
        self._log("═" * 50, "info")

        # Kopyalama thread'ini başlat
        self.copier = DiskCopier(source, dest, options, self.signals)
        self.copier.start()

    def _stop_copy(self):
        if self.copier and self.copier.is_alive():
            reply = QMessageBox.question(
                self, "Onay",
                "Kopyalama işlemini durdurmak istediğinize emin misiniz?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.copier.stop()
                self._log("Durdurma isteği gönderildi...", "warning")

    def _log(self, message, level="info"):
        colors = {
            "info": "#a8d8ea",
            "success": "#66bb6a",
            "warning": "#ffa726",
            "error": "#ef5350"
        }
        color = colors.get(level, "#a8d8ea")
        self.log_text.append(f'<span style="color:{color}">{message}</span>')
        # Auto-scroll
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    # ─── Sinyal Slotları ───
    def _on_progress(self, value):
        self.progress_bar.setValue(value)

    def _on_status(self, text):
        self.statusBar().showMessage(text)

    def _on_log(self, message, level):
        self._log(message, level)

    def _on_file_count(self, current, total, filename):
        self.lbl_file_info.setText(f"{current} / {total} dosya işlendi")
        # Dosya adını kısalt
        if len(filename) > 80:
            filename = "..." + filename[-77:]
        self.lbl_current_file.setText(f"📄 {filename}")

    def _on_speed(self, text):
        self.lbl_speed.setText(text)

    def _on_finished(self, success, message):
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.btn_source.setEnabled(True)
        self.btn_dest.setEnabled(True)

        if success:
            self.progress_bar.setValue(100)
            self._log("═" * 50, "success")
            for line in message.split('\n'):
                self._log(line, "success")
            self._log("═" * 50, "success")
            self.statusBar().showMessage("✅ Kopyalama tamamlandı!")
            QMessageBox.information(self, "Tamamlandı", message)
        else:
            self._log(message, "error")
            self.statusBar().showMessage("❌ " + message)
            QMessageBox.warning(self, "Hata", message)

    def closeEvent(self, event):
        if self.copier and self.copier.is_alive():
            reply = QMessageBox.question(
                self, "Çıkış",
                "Kopyalama işlemi devam ediyor!\nÇıkmak istediğinize emin misiniz?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.copier.stop()
                self.copier.join(timeout=3)
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Dark palette
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor("#1a1a2e"))
    palette.setColor(QPalette.WindowText, QColor("#e0e0e0"))
    palette.setColor(QPalette.Base, QColor("#0d1b2a"))
    palette.setColor(QPalette.Text, QColor("#e0e0e0"))
    palette.setColor(QPalette.Button, QColor("#0f3460"))
    palette.setColor(QPalette.ButtonText, QColor("#e0e0e0"))
    palette.setColor(QPalette.Highlight, QColor("#00d4ff"))
    app.setPalette(palette)

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
