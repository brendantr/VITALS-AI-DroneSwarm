"""Dark theme stylesheet for VITALS PyQt6 GUI."""

DARK_THEME = """
/* ── Global ───────────────────────────────────────────── */
QMainWindow, QWidget {
    background-color: #1a1a2e;
    color: #e0e0e0;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 13px;
}

/* ── QLabel ───────────────────────────────────────────── */
QLabel {
    color: #e0e0e0;
    background: transparent;
}

/* ── QPushButton ──────────────────────────────────────── */
QPushButton {
    background-color: #16213e;
    color: #e0e0e0;
    border: 1px solid #0f3460;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 500;
    min-height: 28px;
}
QPushButton:hover {
    background-color: #0f3460;
    border-color: #533483;
}
QPushButton:pressed {
    background-color: #533483;
}
QPushButton:disabled {
    background-color: #0d1b2a;
    color: #555555;
    border-color: #1b2838;
}

/* Primary action buttons */
QPushButton[cssClass="primary"] {
    background-color: #0f3460;
    border-color: #533483;
    font-weight: 600;
}
QPushButton[cssClass="primary"]:hover {
    background-color: #533483;
}

/* Danger buttons */
QPushButton[cssClass="danger"] {
    background-color: #6b1d1d;
    border-color: #8b2525;
}
QPushButton[cssClass="danger"]:hover {
    background-color: #8b2525;
}

/* ── QLineEdit / QTextEdit ────────────────────────────── */
QLineEdit, QTextEdit, QPlainTextEdit {
    background-color: #16213e;
    color: #e0e0e0;
    border: 1px solid #0f3460;
    border-radius: 6px;
    padding: 6px 10px;
    selection-background-color: #533483;
}
QLineEdit:focus, QTextEdit:focus {
    border-color: #533483;
}

/* ── QFrame ───────────────────────────────────────────── */
QFrame[cssClass="sidebar"] {
    background-color: #16213e;
    border-right: 1px solid #0f3460;
}
QFrame[cssClass="card"] {
    background-color: #16213e;
    border: 1px solid #0f3460;
    border-radius: 8px;
}

/* ── QScrollArea / QScrollBar ─────────────────────────── */
QScrollArea {
    border: none;
    background: transparent;
}
QScrollBar:vertical {
    background-color: #1a1a2e;
    width: 8px;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background-color: #0f3460;
    border-radius: 4px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background-color: #533483;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QScrollBar:horizontal {
    background-color: #1a1a2e;
    height: 8px;
    border-radius: 4px;
}
QScrollBar::handle:horizontal {
    background-color: #0f3460;
    border-radius: 4px;
    min-width: 30px;
}

/* ── QComboBox / QOptionMenu ──────────────────────────── */
QComboBox {
    background-color: #16213e;
    color: #e0e0e0;
    border: 1px solid #0f3460;
    border-radius: 6px;
    padding: 6px 10px;
}
QComboBox:hover {
    border-color: #533483;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox QAbstractItemView {
    background-color: #16213e;
    color: #e0e0e0;
    selection-background-color: #533483;
    border: 1px solid #0f3460;
}

/* ── QDialog ──────────────────────────────────────────── */
QDialog {
    background-color: #1a1a2e;
    color: #e0e0e0;
}

/* ── Drone status colors ──────────────────────────────── */
QLabel[cssClass="status-active"] {
    color: #00e676;
    font-weight: bold;
}
QLabel[cssClass="status-standby"] {
    color: #ffab00;
    font-weight: bold;
}
QLabel[cssClass="status-critical"] {
    color: #ff1744;
    font-weight: bold;
}
QLabel[cssClass="status-boot"] {
    color: #78909c;
    font-weight: bold;
}

/* ── Chat bubbles ─────────────────────────────────────── */
QLabel[cssClass="chat-user"] {
    background-color: #0f3460;
    color: white;
    border-radius: 12px;
    padding: 8px 12px;
}
QLabel[cssClass="chat-system"] {
    background-color: #2a2a4a;
    color: #b0b0b0;
    border-radius: 12px;
    padding: 8px 12px;
}

/* ── Drone info card ──────────────────────────────────── */
QFrame[cssClass="drone-card"] {
    background-color: #0f3460;
    border: 1px solid #533483;
    border-radius: 8px;
    padding: 8px;
}

/* ── POI info card ────────────────────────────────────── */
QFrame[cssClass="poi-card"] {
    background-color: #0f3460;
    border: 1px solid #337ab7;
    border-radius: 8px;
    padding: 8px;
}

/* ── Job info card ────────────────────────────────────── */
QFrame[cssClass="job-active"] {
    background-color: #0f3460;
    border-left: 3px solid #00e676;
    border-radius: 4px;
    padding: 6px;
}
QFrame[cssClass="job-queued"] {
    background-color: #16213e;
    border-left: 3px solid #555555;
    border-radius: 4px;
    padding: 6px;
}
"""
