# -*- coding: utf-8 -*-
"""Processing provider for PLN3113 Tire NİP ve Kentsel Analiz Stüdyosu."""
from __future__ import annotations

import os
from qgis.core import QgsProcessingProvider
from qgis.PyQt.QtGui import QIcon

from .algorithms.alg_geometry_clean import GeometryCleanAlgorithm
from .algorithms.alg_nip_workspace import NipWorkspaceAlgorithm
from .algorithms.alg_yol_platform import YolPlatformAlgorithm
from .algorithms.alg_yol_kavsak import YolKavsakTrimAlgorithm
from .algorithms.alg_yol_poligonlasma import YolPoligonlasmaAlgorithm
from .algorithms.alg_nip_population import NipPopulationAlgorithm
from .algorithms.alg_saha_bina_analysis import SahaBinaAnalysisAlgorithm
from .algorithms.alg_on_cephe_bulucu import OnCepheBulucuAlgorithm
from .algorithms.alg_erisme_havzasi import ErismeHavzasiAlgorithm
from .algorithms.alg_space_syntax import SpaceSyntaxAlgorithm
from .algorithms.alg_network_centrality import NetworkCentralityAlgorithm
from .algorithms.alg_od_matrix import ODMatrixAlgorithm
from .algorithms.alg_service_areas import ServiceAreasAlgorithm
from .algorithms.alg_facility_adequacy import FacilityAdequacyAlgorithm
from .algorithms.alg_scenario_compare import ScenarioCompareAlgorithm

PLUGIN_DIR = os.path.dirname(__file__)


class NipEklentiProvider(QgsProcessingProvider):

    def loadAlgorithms(self):
        # 01. Geometri ve Topoloji Onarımı
        self.addAlgorithm(GeometryCleanAlgorithm())

        # 02. NİP Çizim Veritabanı ve Şablonu
        self.addAlgorithm(NipWorkspaceAlgorithm())

        # 03. Yol Platformu ve Geometri Üretimi
        self.addAlgorithm(YolPlatformAlgorithm())
        self.addAlgorithm(YolKavsakTrimAlgorithm())
        self.addAlgorithm(YolPoligonlasmaAlgorithm())

        # 04. NİP Nüfus, Donatı ve DOP Analizi
        self.addAlgorithm(NipPopulationAlgorithm())
        self.addAlgorithm(SahaBinaAnalysisAlgorithm())

        # 05. Ulaşım ve Network Analizleri
        self.addAlgorithm(OnCepheBulucuAlgorithm())
        self.addAlgorithm(ErismeHavzasiAlgorithm())

        # 06. PlanX Kentsel Ağ ve Mekânsal Erişim Analizleri
        self.addAlgorithm(SpaceSyntaxAlgorithm())
        self.addAlgorithm(NetworkCentralityAlgorithm())
        self.addAlgorithm(ODMatrixAlgorithm())
        self.addAlgorithm(ServiceAreasAlgorithm())
        self.addAlgorithm(FacilityAdequacyAlgorithm())
        self.addAlgorithm(ScenarioCompareAlgorithm())

    def id(self):
        return 'pln3113'

    def name(self):
        return 'PLN3113 NİP Stüdyosu'

    def longName(self):
        return 'PLN3113 1/5000 NİP ve Kentsel Analiz Araçları'

    def icon(self):
        icon_path = os.path.join(PLUGIN_DIR, "icons", "icon.png")
        if os.path.exists(icon_path):
            return QIcon(icon_path)
        return super().icon()


NipProvider = NipEklentiProvider

