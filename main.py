import sys
import sqlite3
from pathlib import Path
from datetime import date
from contextlib import contextmanager
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QScrollArea,
    QFrame, QCheckBox, QMessageBox, QSizePolicy, QGraphicsDropShadowEffect
)
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve, pyqtSignal, QSize, QEvent, QTimer
from PyQt6.QtGui import QFont, QColor, QPalette, QIcon

# ── Database ──────────────────────────────────────────────────────────────────

DB_PATH = Path.home() / "tasks.db"

# Demo/default tasks from early builds. Remove these once if an old database
# already contains them, so the app starts clean for real daily use.
DEFAULT_TASK_TITLES = (
    "Review SQLite schema",
    "Morning run — 5km",
    'Read "Clean Code" chapter 4',
    "Set up PyQt6 Windows app",
    "Grocery shopping",
    "Meditation — 15 min",
)

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def db_connection():
    conn = get_db()
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    with db_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                title    TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'personal',
                done     INTEGER NOT NULL DEFAULT 0,
                created  TEXT NOT NULL DEFAULT (date('now')),
                updated  TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS previous_tasks (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                title    TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'personal',
                created  TEXT NOT NULL,
                archived TEXT NOT NULL DEFAULT (date('now'))
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_done     ON tasks(done)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_category ON tasks(category)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_previous_archived ON previous_tasks(archived)")
        remove_default_tasks(conn)
        rollover_old_tasks(conn)
        conn.commit()


def remove_default_tasks(conn):
    placeholders = ", ".join("?" for _ in DEFAULT_TASK_TITLES)
    conn.execute(
        f"DELETE FROM tasks WHERE title IN ({placeholders})",
        DEFAULT_TASK_TITLES,
    )


def rollover_old_tasks(conn):
    today = str(date.today())
    conn.execute("""
        INSERT INTO previous_tasks (title, category, created, archived)
        SELECT title, category, created, ?
        FROM tasks
        WHERE done = 0 AND created < ?
    """, (today, today))
    conn.execute("DELETE FROM tasks WHERE created < ?", (today,))


def fetch_tasks(filter_by=None):
    q = "SELECT * FROM tasks"
    params = []
    if filter_by == "done":
        q += " WHERE done = 1"
    elif filter_by == "pending":
        q += " WHERE done = 0"
    elif filter_by in ("work", "personal", "health", "learning"):
        q += " WHERE category = ?"
        params.append(filter_by)
    q += " ORDER BY done ASC, id DESC"
    with db_connection() as conn:
        return [dict(r) for r in conn.execute(q, params).fetchall()]

def add_task(title, category):
    with db_connection() as conn:
        conn.execute(
            "INSERT INTO tasks (title, category, done, created) VALUES (?, ?, 0, ?)",
            (title, category, str(date.today()))
        )
        conn.commit()

def toggle_done(task_id, current):
    with db_connection() as conn:
        conn.execute(
            "UPDATE tasks SET done=?, updated=? WHERE id=?",
            (0 if current else 1, str(date.today()), task_id)
        )
        conn.commit()

def update_title(task_id, new_title):
    with db_connection() as conn:
        conn.execute(
            "UPDATE tasks SET title=?, updated=? WHERE id=?",
            (new_title, str(date.today()), task_id)
        )
        conn.commit()

def delete_task(task_id):
    with db_connection() as conn:
        conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))
        conn.commit()

def get_stats():
    with db_connection() as conn:
        row = conn.execute("""
            SELECT
                COUNT(*) AS total,
                SUM(done) AS done,
                SUM(1 - done) AS pending
            FROM tasks
        """).fetchone()
        return dict(row)

# ── Styles ────────────────────────────────────────────────────────────────────

CATEGORY_COLORS = {
    "work":     ("#1A5296", "#D6E8FA"),
    "personal": ("#4A1B8C", "#EBE4FA"),
    "health":   ("#1B6B3A", "#D8F0E2"),
    "learning": ("#7A4500", "#FDEAC8"),
}

APP_STYLE = """
QMainWindow, QWidget#central {
    background: #F5F4F0;
}
QScrollArea {
    background: transparent;
    border: none;
}
QScrollBar:vertical {
    background: #EEEDE9;
    width: 6px;
    border-radius: 3px;
}
QScrollBar::handle:vertical {
    background: #C8C7C2;
    border-radius: 3px;
    min-height: 30px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""

# ── Task Row Widget ───────────────────────────────────────────────────────────

class TaskRow(QFrame):
    changed = pyqtSignal()

    def __init__(self, task: dict, parent=None):
        super().__init__(parent)
        self.task = task
        self.editing = False
        self._build()

    def _build(self):
        self.setObjectName("taskRow")
        self.setFixedHeight(56)
        self.setStyleSheet("""
            #taskRow {
                background: white;
                border: 1px solid #E4E3DF;
                border-radius: 10px;
            }
            #taskRow:hover {
                border-color: #C8C7C2;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 10, 0)
        layout.setSpacing(12)

        # Checkbox
        self.check = QCheckBox()
        self.check.setChecked(bool(self.task["done"]))
        self.check.setStyleSheet("""
            QCheckBox::indicator {
                width: 18px; height: 18px;
                border: 1.5px solid #BBBAБ6;
                border-radius: 5px;
                background: white;
            }
            QCheckBox::indicator:checked {
                background: #1D9E75;
                border-color: #1D9E75;
                image: none;
            }
            QCheckBox::indicator:hover { border-color: #888; }
        """)
        self.check.toggled.connect(self._toggle)
        layout.addWidget(self.check)

        # Title (label + edit input, stacked)
        self.title_label = QLabel(self.task["title"])
        self.title_label.setFont(QFont("Segoe UI", 10))
        done = bool(self.task["done"])
        self.title_label.setStyleSheet(
            "color: #999; text-decoration: line-through;" if done
            else "color: #1A1A1A;"
        )
        self.title_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self.title_edit = QLineEdit(self.task["title"])
        self.title_edit.setFont(QFont("Segoe UI", 10))
        self.title_edit.setStyleSheet("""
            QLineEdit {
                border: none;
                border-bottom: 1.5px solid #4A90D9;
                background: transparent;
                color: #1A1A1A;
                padding: 0;
            }
        """)
        self.title_edit.setVisible(False)
        self.title_edit.returnPressed.connect(self._save_edit)
        self.title_edit.editingFinished.connect(self._save_edit)

        layout.addWidget(self.title_label)
        layout.addWidget(self.title_edit)

        # Category badge
        cat = self.task["category"]
        fg, bg = CATEGORY_COLORS.get(cat, ("#555", "#EEE"))
        badge = QLabel(cat)
        badge.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        badge.setStyleSheet(f"""
            color: {fg};
            background: {bg};
            border-radius: 8px;
            padding: 2px 9px;
        """)
        badge.setFixedHeight(20)
        layout.addWidget(badge)

        # Edit button
        self.edit_btn = QPushButton("✎")
        self.edit_btn.setFixedSize(28, 28)
        self.edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.edit_btn.setToolTip("Edit")
        self.edit_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #AAAAAA;
                font-size: 14px;
                border-radius: 6px;
            }
            QPushButton:hover { background: #F0EFEB; color: #444; }
        """)
        self.edit_btn.clicked.connect(self._start_edit)
        layout.addWidget(self.edit_btn)

        # Delete button
        del_btn = QPushButton("✕")
        del_btn.setFixedSize(28, 28)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setToolTip("Delete")
        del_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #AAAAAA;
                font-size: 12px;
                border-radius: 6px;
            }
            QPushButton:hover { background: #FDEAEA; color: #A32D2D; }
        """)
        del_btn.clicked.connect(self._delete)
        layout.addWidget(del_btn)

    def _toggle(self, checked):
        toggle_done(self.task["id"], not checked)
        self.changed.emit()

    def _start_edit(self):
        if self.editing:
            return
        self.editing = True
        self.title_label.setVisible(False)
        self.title_edit.setVisible(True)
        self.title_edit.setText(self.task["title"])
        self.title_edit.setFocus()
        self.title_edit.selectAll()
        self.edit_btn.setText("✔")

    def _save_edit(self):
        if not self.editing:
            return
        self.editing = False
        new_title = self.title_edit.text().strip()
        if new_title and new_title != self.task["title"]:
            update_title(self.task["id"], new_title)
            self.task["title"] = new_title
        self.title_label.setText(self.task["title"])
        self.title_label.setVisible(True)
        self.title_edit.setVisible(False)
        self.edit_btn.setText("✎")

    def _delete(self):
        reply = QMessageBox.question(
            self, "Delete task",
            f'Delete "{self.task["title"]}"?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            delete_task(self.task["id"])
            self.changed.emit()


# ── Stat Card ─────────────────────────────────────────────────────────────────

class StatCard(QFrame):
    def __init__(self, label, value, accent="#1A1A1A"):
        super().__init__()
        self.setStyleSheet(f"""
            QFrame {{
                background: white;
                border: 1px solid #E4E3DF;
                border-radius: 10px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(2)

        lbl = QLabel(label)
        lbl.setFont(QFont("Segoe UI", 8))
        lbl.setStyleSheet("color: #888888; border: none;")

        self.val = QLabel(str(value))
        self.val.setFont(QFont("Segoe UI", 22, QFont.Weight.Medium))
        self.val.setStyleSheet(f"color: {accent}; border: none;")

        layout.addWidget(lbl)
        layout.addWidget(self.val)

    def set_value(self, v):
        self.val.setText(str(v))


# ── Main Window ───────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.force_quit = False
        self.setWindowTitle("My Tasks")
        self.setMinimumSize(680, 560)
        self.resize(720, 640)
        self.active_filter = None
        self.setStyleSheet(APP_STYLE)
        self._build_ui()
        self.refresh()

    def closeEvent(self, event):
        if self.force_quit:
            event.accept()
            return

        event.ignore()
        self.hide()

    def changeEvent(self, event):
        if (
            event.type() == QEvent.Type.WindowStateChange
            and self.isMinimized()
            and not self.force_quit
        ):
            QTimer.singleShot(0, self.hide)
            return

        super().changeEvent(event)

    def quit_from_tray(self):
        self.force_quit = True
        QApplication.instance().quit()

    def _build_ui(self):
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(0)

        # Header
        hdr = QHBoxLayout()
        title = QLabel("My Tasks")
        title.setFont(QFont("Segoe UI", 18, QFont.Weight.Medium))
        title.setStyleSheet("color: #1A1A1A;")
        today = QLabel(date.today().strftime("%a, %d %b %Y"))
        today.setFont(QFont("Segoe UI", 10))
        today.setStyleSheet("color: #888;")
        hdr.addWidget(title)
        hdr.addStretch()
        hdr.addWidget(today)
        root.addLayout(hdr)
        root.addSpacing(20)

        # Stats row
        stats_row = QHBoxLayout()
        stats_row.setSpacing(10)
        self.card_total   = StatCard("Total",   0, "#1A1A1A")
        self.card_done    = StatCard("Done",    0, "#1D9E75")
        self.card_pending = StatCard("Pending", 0, "#BA7517")
        for c in (self.card_total, self.card_done, self.card_pending):
            c.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            stats_row.addWidget(c)
        root.addLayout(stats_row)
        root.addSpacing(18)

        # Add task row
        add_row = QHBoxLayout()
        add_row.setSpacing(8)

        self.input = QLineEdit()
        self.input.setPlaceholderText("Add a new task…")
        self.input.setFont(QFont("Segoe UI", 10))
        self.input.setFixedHeight(38)
        self.input.setStyleSheet("""
            QLineEdit {
                background: white;
                border: 1px solid #DDDCD8;
                border-radius: 8px;
                padding: 0 12px;
                color: #1A1A1A;
            }
            QLineEdit:focus { border-color: #4A90D9; }
        """)
        self.input.returnPressed.connect(self._add_task)

        self.cat_combo = QComboBox()
        self.cat_combo.addItems(["personal", "work", "health", "learning"])
        self.cat_combo.setFixedHeight(38)
        self.cat_combo.setFixedWidth(110)
        self.cat_combo.setFont(QFont("Segoe UI", 10))
        self.cat_combo.setStyleSheet("""
            QComboBox {
                background: white;
                border: 1px solid #DDDCD8;
                border-radius: 8px;
                padding: 0 10px;
                color: #1A1A1A;
            }
            QComboBox:focus { border-color: #4A90D9; }
            QComboBox::drop-down { border: none; width: 24px; }
            QComboBox QAbstractItemView {
                background: white;
                border: 1px solid #DDDCD8;
                border-radius: 6px;
                selection-background-color: #F0EFEB;
                selection-color: #1A1A1A;
            }
        """)

        add_btn = QPushButton("+ Add")
        add_btn.setFixedHeight(38)
        add_btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Medium))
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setStyleSheet("""
            QPushButton {
                background: #1A1A1A;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 0 18px;
            }
            QPushButton:hover { background: #333; }
            QPushButton:pressed { background: #000; }
        """)
        add_btn.clicked.connect(self._add_task)

        add_row.addWidget(self.input)
        add_row.addWidget(self.cat_combo)
        add_row.addWidget(add_btn)
        root.addLayout(add_row)
        root.addSpacing(14)

        # Filter pills
        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)
        self.filter_btns = {}
        filters = [("All", None), ("Pending", "pending"), ("Done", "done"),
                   ("Work", "work"), ("Personal", "personal"),
                   ("Health", "health"), ("Learning", "learning")]
        for label, fval in filters:
            btn = QPushButton(label)
            btn.setFixedHeight(28)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFont(QFont("Segoe UI", 9))
            btn.setProperty("fval", fval)
            btn.setCheckable(True)
            btn.clicked.connect(lambda _, b=btn: self._set_filter(b))
            self._style_filter(btn, fval is None)
            self.filter_btns[fval] = btn
            filter_row.addWidget(btn)
        filter_row.addStretch()
        root.addLayout(filter_row)
        root.addSpacing(12)

        # Task list in scroll area
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)

        self.list_container = QWidget()
        self.list_container.setStyleSheet("background: transparent;")
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(6)
        self.list_layout.addStretch()

        self.scroll.setWidget(self.list_container)
        root.addWidget(self.scroll)

    def _style_filter(self, btn, active):
        if active:
            btn.setStyleSheet("""
                QPushButton {
                    background: #1A1A1A;
                    color: white;
                    border: none;
                    border-radius: 14px;
                    padding: 0 14px;
                }
            """)
        else:
            btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    color: #888;
                    border: 1px solid #DDDCD8;
                    border-radius: 14px;
                    padding: 0 14px;
                }
                QPushButton:hover { background: #F0EFEB; color: #1A1A1A; }
            """)

    def _set_filter(self, clicked_btn):
        fval = clicked_btn.property("fval")
        self.active_filter = fval
        for val, btn in self.filter_btns.items():
            self._style_filter(btn, val == fval)
        self.refresh()

    def _add_task(self):
        title = self.input.text().strip()
        if not title:
            return
        cat = self.cat_combo.currentText()
        add_task(title, cat)
        self.input.clear()
        self.refresh()

    def refresh(self):
        # Clear existing task rows (keep the trailing stretch)
        while self.list_layout.count() > 1:
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        tasks = fetch_tasks(self.active_filter)

        if not tasks:
            empty = QLabel("No tasks here")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setFont(QFont("Segoe UI", 10))
            empty.setStyleSheet("color: #AAAAAA; padding: 40px 0;")
            self.list_layout.insertWidget(0, empty)
        else:
            for i, task in enumerate(tasks):
                row = TaskRow(task)
                row.changed.connect(self.refresh)
                self.list_layout.insertWidget(i, row)

        stats = get_stats()
        self.card_total.set_value(stats["total"] or 0)
        self.card_done.set_value(int(stats["done"] or 0))
        self.card_pending.set_value(int(stats["pending"] or 0))


# ── System Tray ───────────────────────────────────────────────────────────────

from PyQt6.QtWidgets import QSystemTrayIcon, QMenu
from PyQt6.QtGui import QPixmap

def make_tray_icon():
    # Simple coloured square as icon (no external file needed)
    px = QPixmap(16, 16)
    px.fill(QColor("#1A1A1A"))
    return QIcon(px)


def show_window(win):
    win.setWindowState(
        (win.windowState() & ~Qt.WindowState.WindowMinimized)
        | Qt.WindowState.WindowActive
    )
    win.showNormal()
    win.raise_()
    win.activateWindow()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    # Stay alive when the window is closed
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("My Tasks")

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#F5F4F0"))
    app.setPalette(palette)

    tray_icon = make_tray_icon()
    app.setWindowIcon(tray_icon)

    win = MainWindow()
    win.setWindowIcon(tray_icon)
    win.show()

    # ── Tray icon + menu ──
    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, "System tray unavailable", "System tray is not available.")
        sys.exit(1)

    tray = QSystemTrayIcon(tray_icon, parent=app)
    tray.setToolTip("My Tasks")

    tray_menu = QMenu()

    show_action = tray_menu.addAction("Show")
    show_action.triggered.connect(lambda: show_window(win))

    hide_action = tray_menu.addAction("Hide")
    hide_action.triggered.connect(win.hide)

    tray_menu.addSeparator()

    quit_action = tray_menu.addAction("Quit")
    quit_action.triggered.connect(win.quit_from_tray)

    tray.setContextMenu(tray_menu)

    # Single-click tray icon → toggle window
    def tray_activated(reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if win.isVisible():
                win.hide()
            else:
                show_window(win)

    tray.activated.connect(tray_activated)
    tray.show()

    # Keep strong references alive in packaged builds.
    app.main_window = win
    app.tray_icon = tray
    app.tray_menu = tray_menu

    sys.exit(app.exec())
