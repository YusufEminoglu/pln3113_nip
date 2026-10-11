# -*- coding: utf-8 -*-
"""1. Geometri ve Duplike Temizleme Processing Algoritması.

DEÜ Mimarlık Fakültesi Şehir ve Bölge Planlama Bölümü
PLN3113 - nip_eklenti_01
"""
from __future__ import annotations

from qgis.core import (
    QgsFeature,
    QgsFeatureSink,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterVectorLayer,
    QgsWkbTypes
)

from ..core.cleaner import GeometryCleanerEngine

class GeometryCleanAlgorithm(QgsProcessingAlgorithm):
    INPUT = 'INPUT'
    OUTPUT = 'OUTPUT'

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.INPUT,
                'Girdi Poligon Katmanı (NİP veya Kadastro)',
                [QgsProcessing.TypeVectorPolygon]
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                'Temizlenmiş ve Tekilleştirilmiş Katman',
                QgsProcessing.TypeVectorPolygon
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        layer = self.parameterAsVectorLayer(parameters, self.INPUT, context)
        if not layer:
            raise QgsProcessingException("Girdi katmanı yüklenemedi!")

        feedback.pushInfo(f"Katman taranıyor: {layer.name()} ({layer.featureCount()} obje)...")

        cleaned_features, stats = GeometryCleanerEngine.clean_layer(layer, feedback)

        feedback.pushInfo(f"Toplam Girdi: {stats['toplam_girdi']}")
        feedback.pushInfo(f"Onarılan Geçersiz Geometri: {stats['gecersiz_onarilan']}")
        feedback.pushInfo(f"Ayıklanan Duplike (Çift) Geometri: {stats['duplike_elenen']} (%{stats.get('duplike_orani', 0)})")
        feedback.pushInfo(f"Temiz Çıktı Obje Sayısı: {stats['temiz_cikan']}")

        (sink, dest_id) = self.parameterAsSink(
            parameters,
            self.OUTPUT,
            context,
            layer.fields(),
            QgsWkbTypes.MultiPolygon,
            layer.sourceCrs()
        )

        for feat in cleaned_features:
            sink.addFeature(feat, QgsFeatureSink.FastInsert)

        return {self.OUTPUT: dest_id}

    def name(self):
        return 'tire_geometri_temizle'

    def displayName(self):
        return '1. Geometri ve Duplike Temizleme Aracı'

    def group(self):
        return 'Tire NİP ve Kentsel Analiz Araçları'

    def groupId(self):
        return 'tire_nip_tools'

    def createInstance(self):
        return GeometryCleanAlgorithm()
