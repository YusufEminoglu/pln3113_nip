# -*- coding: utf-8 -*-
"""nip_eklenti_01 UI Theme and Stylesheet.

DEÜ Mimarlık Fakültesi Şehir ve Bölge Planlama Bölümü
PLN3113 - Tire NİP Analiz Stüdyosu
"""

NIP_STUDIO_QSS = """
QWidget#TireNipDockWidget {
    background-color: #f8fafc;
    color: #0f172a;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
}

QTabWidget::pane {
    border: 1px solid #cbd5e1;
    background: #ffffff;
    border-radius: 8px;
    top: -1px;
}

QTabBar::tab {
    background: #e2e8f0;
    color: #475569;
    padding: 8px 16px;
    font-weight: 600;
    font-size: 12px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
}

QTabBar::tab:selected {
    background: #0f766e;
    color: #ffffff;
}

QTabBar::tab:hover:!selected {
    background: #cbd5e1;
    color: #0f172a;
}

QGroupBox {
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    margin-top: 14px;
    padding: 10px;
    background-color: #ffffff;
    font-weight: 600;
    color: #0f766e;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 4px;
}

QLabel {
    color: #334155;
    font-size: 12px;
}

QLabel#HeaderTitle {
    font-size: 15px;
    font-weight: bold;
    color: #ffffff;
}

QLabel#HeaderSubtitle {
    font-size: 11px;
    color: #ccfbf1;
}

QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {
    border: 1px solid #cbd5e1;
    border-radius: 4px;
    padding: 6px 8px;
    background-color: #ffffff;
    color: #0f172a;
    font-size: 12px;
}

QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus {
    border: 1.5px solid #0f766e;
}

QPushButton {
    border-radius: 5px;
    padding: 7px 14px;
    font-weight: 600;
    font-size: 12px;
}

QPushButton#PrimaryButton {
    background-color: #0f766e;
    color: #ffffff;
    border: none;
}

QPushButton#PrimaryButton:hover {
    background-color: #115e59;
}

QPushButton#PrimaryButton:pressed {
    background-color: #134e4a;
}

QPushButton#CleanButton {
    background-color: #0284c7;
    color: #ffffff;
    border: none;
}

QPushButton#CleanButton:hover {
    background-color: #0369a1;
}

QPushButton#FieldButton {
    background-color: #d97706;
    color: #ffffff;
    border: none;
}

QPushButton#FieldButton:hover {
    background-color: #b45309;
}

QTableWidget {
    background-color: #ffffff;
    alternate-background-color: #f8fafc;
    border: 1px solid #e2e8f0;
    gridline-color: #f1f5f9;
    font-size: 11px;
}

QHeaderView::section {
    background-color: #0f766e;
    color: #ffffff;
    padding: 6px;
    font-weight: bold;
    border: none;
}

QProgressBar {
    border: 1px solid #cbd5e1;
    border-radius: 4px;
    text-align: center;
    background-color: #f1f5f9;
}

QProgressBar::chunk {
    background-color: #0f766e;
    border-radius: 3px;
}
"""
