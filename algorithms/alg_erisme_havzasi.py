# -*- coding: utf-8 -*-
"""Erişilebilirlik ve MPYY Hizmet Etki Çapı Poligonları Algoritması.

DEÜ Mimarlık Fakültesi Şehir ve Bölge Planlama Bölümü
PLN3113 - Tire NİP Analiz Stüdyosu
"""
from __future__ import annotations

try:
    import processing
except ImportError:
    processing = None
from qgis.core import (
    QgsFeatureSink,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterDistance,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsWkbTypes
)


class ErismeHavzasiAlgorithm(QgsProcessingAlgorithm):
    INPUT_FACILITIES = 'INPUT_FACILITIES'
    INPUT_ROADS = 'INPUT_ROADS'
    DISTANCE = 'DISTANCE'
    CALCULATE_NETWORK = 'CALCULATE_NETWORK'
    CALCULATE_BUFFER = 'CALCULATE_BUFFER'
    OUTPUT_SERVICE_ROADS = 'OUTPUT_SERVICE_ROADS'
    OUTPUT_SERVICE_POLYGONS = 'OUTPUT_SERVICE_POLYGONS'
    OUTPUT_MPYY_BUFFER = 'OUTPUT_MPYY_BUFFER'

    def name(self):
        return 'nip_erisme_ve_mpyy_etki_capi'

    def displayName(self):
        return '2. Donatı Erişilebilirlik ve MPYY Etki Çapı Havzaları'

    def group(self):
        return '05. Ulaşım ve Network Analizleri'

    def groupId(self):
        return '05_ulasim_network_analizleri'

    def shortHelpString(self):
        return (
            "Sosyal ve teknik altyapı donatıları (Eğitim, Sağlık, Park, İbadet vb.) için "
            "iki farklı yaklaşımla etki ve erişim havzası üretir:\n\n"
            "1. Ağ Tabanlı Gerçek Servis Yolları ve Erişim Havzası: Yol ağı üzerinden yürüyüş mesafesi "
            "boyunca ulaşılan sokakları ve konveks sınır poligonunu üretir.\n"
            "2. MPYY Mevzuat Geometrik Etki Çapı: Mekânsal Planlar Yapım Yönetmeliği standart yarıçaplarına "
            "göre (örn: 500m yürüme mesafesi) dairesel ve çözülmüş (dissolved) servis etki poligonları üretir."
        )

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT_FACILITIES,
                'Donatı / Hizmet Noktaları veya Poligonları (Okul, Sağlık, Park vb.)',
                [QgsProcessing.SourceType.TypeVectorPoint, QgsProcessing.SourceType.TypeVectorPolygon]
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT_ROADS,
                'Ulaşım / Yol Aksları Katmanı (Line)',
                [QgsProcessing.SourceType.TypeVectorLine]
            )
        )
        self.addParameter(
            QgsProcessingParameterDistance(
                self.DISTANCE,
                'Erişim / Hizmet Etki Mesafesi (Metre)',
                parentParameterName=self.INPUT_ROADS,
                defaultValue=500.0,
                minValue=50.0,
                maxValue=10000.0
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.CALCULATE_NETWORK,
                'Yol Ağı Üzerinden Gerçek Servis Yollarını Hesapla',
                defaultValue=True
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.CALCULATE_BUFFER,
                'MPYY Mevzuat Dairesel Etki Çapını (Buffer) Hesapla',
                defaultValue=True
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_SERVICE_ROADS,
                'Ağ Servis Yolları (Line)',
                QgsProcessing.SourceType.TypeVectorLine,
                optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_SERVICE_POLYGONS,
                'Ağ Tabanlı Erişim Havza Poligonu (Polygon)',
                QgsProcessing.SourceType.TypeVectorPolygon,
                optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_MPYY_BUFFER,
                'MPYY Mevzuat Etki Çapı Tamponu (Polygon)',
                QgsProcessing.SourceType.TypeVectorPolygon,
                optional=True
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        source_fac = self.parameterAsSource(parameters, self.INPUT_FACILITIES, context)
        source_roads = self.parameterAsSource(parameters, self.INPUT_ROADS, context)
        distance = self.parameterAsDouble(parameters, self.DISTANCE, context)
        do_network = self.parameterAsBool(parameters, self.CALCULATE_NETWORK, context)
        do_buffer = self.parameterAsBool(parameters, self.CALCULATE_BUFFER, context)

        if not source_fac or not source_roads:
            raise QgsProcessingException("Gerekli girdi katmanları bulunamadı!")

        # Eğer girdi poligon ise centroid noktalarına dönüştür
        fac_geom_type = source_fac.wkbType()
        fac_input = parameters[self.INPUT_FACILITIES]
        if QgsWkbTypes.geometryType(fac_geom_type) == QgsWkbTypes.GeometryType.PolygonGeometry:
            feedback.pushInfo("Donatı poligonlarının ağırlık merkezleri (centroid) türetiliyor...")
            cent_res = processing.run("native:centroids", {
                'INPUT': parameters[self.INPUT_FACILITIES],
                'ALL_PARTS': False,
                'OUTPUT': 'TEMPORARY_OUTPUT'
            }, context=context, feedback=feedback, is_child_algorithm=True)
            fac_points = cent_res['OUTPUT']
        else:
            fac_points = fac_input

        results = {}

        # 1. MPYY Mevzuat Tamponu
        if do_buffer and self.OUTPUT_MPYY_BUFFER in parameters:
            feedback.pushInfo(f"MPYY {distance}m etki çapı tamponu hesaplanıyor...")
            buff_res = processing.run("native:buffer", {
                'INPUT': fac_points,
                'DISTANCE': distance,
                'SEGMENTS': 64,
                'END_CAP_STYLE': 0,
                'JOIN_STYLE': 0,
                'MITER_LIMIT': 2.0,
                'DISSOLVE': True,
                'OUTPUT': parameters[self.OUTPUT_MPYY_BUFFER]
            }, context=context, feedback=feedback, is_child_algorithm=True)
            results[self.OUTPUT_MPYY_BUFFER] = buff_res['OUTPUT']

        # 2. Yol Ağı Tabanlı Servis Alanı
        if do_network:
            feedback.pushInfo(f"Yol ağı üzerinden {distance}m servis yolları hesaplanıyor...")
            service_res = processing.run("native:serviceareafromlayer", {
                'INPUT': parameters[self.INPUT_ROADS],
                'STRATEGY': 0,  # En kısa mesafe
                'DIRECTION_FIELD': '',
                'VALUE_FORWARD': '',
                'VALUE_BACKWARD': '',
                'VALUE_BOTH': '',
                'DEFAULT_DIRECTION': 2,
                'SPEED_FIELD': '',
                'DEFAULT_SPEED': 50.0,
                'TOLERANCE': 0.0,
                'START_POINTS': fac_points,
                'TRAVEL_COST': distance,
                'INCLUDE_BOUNDS': False,
                'OUTPUT_LINES': parameters[self.OUTPUT_SERVICE_ROADS] if self.OUTPUT_SERVICE_ROADS in parameters else 'TEMPORARY_OUTPUT'
            }, context=context, feedback=feedback, is_child_algorithm=True)

            if self.OUTPUT_SERVICE_ROADS in parameters:
                results[self.OUTPUT_SERVICE_ROADS] = service_res['OUTPUT_LINES']

            # Erişim Havzası Poligonu (Convex Hull / Dissolved Buffer on reached network)
            if self.OUTPUT_SERVICE_POLYGONS in parameters:
                feedback.pushInfo("Ulaşılan servis yollarından erişim havza poligonu üretiliyor...")
                lines_buff = processing.run("native:buffer", {
                    'INPUT': service_res['OUTPUT_LINES'],
                    'DISTANCE': 30.0,  # Yol koridoru genişliği
                    'SEGMENTS': 16,
                    'DISSOLVE': True,
                    'OUTPUT': parameters[self.OUTPUT_SERVICE_POLYGONS]
                }, context=context, feedback=feedback, is_child_algorithm=True)
                results[self.OUTPUT_SERVICE_POLYGONS] = lines_buff['OUTPUT']

        return results

    def createInstance(self):
        return ErismeHavzasiAlgorithm()
