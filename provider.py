# -*- coding: utf-8 -*-
"""Processing provider for nip_eklenti_01."""
from __future__ import annotations

import os
from qgis.core import QgsProcessingProvider
from qgis.PyQt.QtGui import QIcon

from .algorithms.alg_geometry_clean import GeometryCleanAlgorithm
from .algorithms.alg_nip_population import NipPopulationAlgorithm
from .algorithms.alg_saha_bina_analysis import SahaBinaAnalysisAlgorithm

PLUGIN_DIR = os.path.dirname(__file__)

class NipEklentiProvider(QgsProcessingProvider):

    def loadAlgorithms(self):
        self.addAlgorithm(GeometryCleanAlgorithm())
        self.addAlgorithm(NipPopulationAlgorithm())
        self.addAlgorithm(SahaBinaAnalysisAlgorithm())

    def id(self):
        return 'pln3113_nip'

    def name(self):
        return 'PLN3113 NİP Stüdyosu'

    def longName(self):
        return 'PLN3113 1/5000 NİP ve Kentsel Analiz Araçları'

    def icon(self):
        icon_path = os.path.join(PLUGIN_DIR, "icons", "icon.png")
        if os.path.exists(icon_path):
            return QIcon(icon_path)
        return super().icon()
