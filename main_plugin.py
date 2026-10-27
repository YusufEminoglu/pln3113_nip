# -*- coding: utf-8 -*-
"""nip_eklenti_01 main plugin entry point.

PLN3113 - Tire NİP Analiz Stüdyosu
"""
from __future__ import annotations

import os
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction
from qgis.core import QgsApplication

from .provider import NipEklentiProvider

PLUGIN_DIR = os.path.dirname(__file__)

class NipEklentiPlugin:
    """Tire NİP ve Kentsel Analiz Eklentisi Ana Sınıfı."""

    def __init__(self, iface):
        self.iface = iface
        self.provider = None
        self.dock = None
        self.action = None
        self.action_guide = None

    def initProcessing(self):
        """Processing sağlayıcısını QGIS'e kaydeder."""
        if self.provider is None:
            self.provider = NipEklentiProvider()
            QgsApplication.processingRegistry().addProvider(self.provider)

    def initGui(self):
        """Arayüz ikonlarını ve menü butonlarını oluşturur."""
        self.initProcessing()

        icon_path = os.path.join(PLUGIN_DIR, "icons", "icon.png")
        icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()

        self.action = QAction(icon, "Tire NİP ve Kentsel Analiz Stüdyosu", self.iface.mainWindow())
        self.action.setObjectName("actionTireNipStudio")
        self.action.setToolTip("PLN3113 Tire NİP Nüfus, Donatı ve Mevcut Kent Analiz Panelini Aç")
        self.action.triggered.connect(self.open_dock)

        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("&Tire NİP Stüdyosu", self.action)

        # Metodoloji ve Teorik Rehber Menüsü
        self.action_guide = QAction("📚 Metodoloji ve Stüdyo Rehberi", self.iface.mainWindow())
        self.action_guide.setObjectName("actionTireNipGuide")
        self.action_guide.setToolTip("A'dan Z'ye Tire NİP Analiz ve Metodoloji El Kitabını Aç")
        self.action_guide.triggered.connect(self.open_guide)
        self.iface.addPluginToMenu("&Tire NİP Stüdyosu", self.action_guide)

    def open_dock(self):
        """Dock panelini ekrana getirir."""
        if self.dock is None:
            from .dock import TireNipDockWidget
            self.dock = TireNipDockWidget(self.iface, self.iface.mainWindow())
            self.iface.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)
        self.dock.show()
        self.dock.raise_()

    def open_guide(self):
        """Metodoloji rehberini açar."""
        # Kılavuz ve teorik rehber geophilo.com'da tek sayfada yayımlanır.
        from qgis.PyQt.QtCore import QUrl
        from qgis.PyQt.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl("https://geophilo.com/pln3113_nip/#teorik"))

    def unload(self):
        """Eklenti kapatılırken temizlik yapar."""
        if self.action_guide:
            self.iface.removePluginMenu("&Tire NİP Stüdyosu", self.action_guide)
            del self.action_guide
            self.action_guide = None

        if self.action:
            self.iface.removePluginMenu("&Tire NİP Stüdyosu", self.action)
            self.iface.removeToolBarIcon(self.action)
            del self.action
            self.action = None

        if self.provider:
            QgsApplication.processingRegistry().removeProvider(self.provider)
            self.provider = None

        if self.dock:
            self.iface.removeDockWidget(self.dock)
            self.dock.deleteLater()
            self.dock = None
