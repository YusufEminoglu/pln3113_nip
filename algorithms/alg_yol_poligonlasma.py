# -*- coding: utf-8 -*-
"""3. Yol Çizgilerini Poligonlaştırma ve Plan Verisi Eşleme Algoritması.

DEÜ Mimarlık Fakültesi Şehir ve Bölge Planlama Bölümü
PLN3113 - Tire NİP Analiz Stüdyosu
"""
from __future__ import annotations

try:
    import processing
except ImportError:
    processing = None
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingUtils
)


class YolPoligonlasmaAlgorithm(QgsProcessingAlgorithm):
    INPUT_LINES = 'INPUT_LINES'
    INPUT_ZONES = 'INPUT_ZONES'
    INCLUDE_MANUAL = 'INCLUDE_MANUAL'
    OUTPUT = 'OUTPUT'

    def name(self):
        return 'nip_yol_poligonlasma_esleme'

    def displayName(self):
        return '3. Yol Çizgilerini Poligonlaştır ve Plan Alanı Eşle'

    def group(self):
        return '03. Yol Platformu ve Geometri Üretimi'

    def groupId(self):
        return '03_yol_geometri_uretimi'

    def shortHelpString(self):
        return (
            "Dış yol sınır çizgileri (left_outer, right_outer) ve köşe yuvarlatma (fillet) yaylarını "
            "alarak kapalı yol/ada poligonlarına dönüştürür (polygonize). Ardından oluşan poligonları "
            "referans NİP plan kullanım alanlarıyla en büyük mekânsal çakışma (largest overlap) "
            "esasına göre birleştirir ve öznitelikleri aktarır."
        )

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT_LINES,
                'Yol Dış Çizgileri Katmanı (Left/Right Outer ve Yaylar)',
                [QgsProcessing.SourceType.TypeVectorLine]
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT_ZONES,
                'Referans NİP Plan Kullanım Poligonları Katmanı',
                [QgsProcessing.SourceType.TypeVectorPolygon]
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.INCLUDE_MANUAL,
                'Manuel Çizilmiş veya Niteliksiz Yay Çizgilerini de Dahil Et (Side=NULL / Fillet)',
                defaultValue=True
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                'Öznitelikli Yol / Ada Poligonları (Polygon)',
                QgsProcessing.SourceType.TypeVectorPolygon
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        source_lines = self.parameterAsSource(parameters, self.INPUT_LINES, context)
        source_zones = self.parameterAsSource(parameters, self.INPUT_ZONES, context)
        include_manual = self.parameterAsBool(parameters, self.INCLUDE_MANUAL, context)

        if not source_lines or not source_zones:
            raise QgsProcessingException("Gerekli girdi katmanları bulunamadı!")

        # 1. Filtreleme
        feedback.pushInfo("1. Aşama: Yol dış hatları ve köşe yayları filtreleniyor...")
        field_names = [f.name() for f in source_lines.fields()]
        has_side = "side" in field_names
        has_type = "type" in field_names

        if has_side and has_type and include_manual:
            expression = "\"side\" ILIKE '%outer%' OR \"side\" IS NULL OR \"type\" ILIKE '%fillet%'"
        elif has_side:
            expression = "\"side\" ILIKE '%outer%'"
        else:
            expression = ""

        if expression:
            extract_result = processing.run("native:extractbyexpression", {
                'INPUT': parameters[self.INPUT_LINES],
                'EXPRESSION': expression,
                'OUTPUT': 'TEMPORARY_OUTPUT'
            }, context=context, feedback=feedback, is_child_algorithm=True)
            lines_to_polygonize = extract_result['OUTPUT']
        else:
            lines_to_polygonize = parameters[self.INPUT_LINES]

        ext_obj = QgsProcessingUtils.mapLayerFromString(str(lines_to_polygonize), context)
        if ext_obj and ext_obj.featureCount() == 0:
            raise QgsProcessingException("Filtre sonucunda hiçbir dış çizgi bulunamadı. Lütfen 'side' sütununu kontrol edin!")

        # 2. Poligonlaştırma
        feedback.pushInfo("2. Aşama: Kapalı çizgiler poligon geometrilere dönüştürülüyor...")
        poly_result = processing.run("native:polygonize", {
            'INPUT': lines_to_polygonize,
            'KEEP_FIELDS': False,
            'OUTPUT': 'TEMPORARY_OUTPUT'
        }, context=context, feedback=feedback, is_child_algorithm=True)

        poly_id = poly_result['OUTPUT']
        poly_obj = QgsProcessingUtils.mapLayerFromString(str(poly_id), context)
        if not poly_obj or poly_obj.featureCount() == 0:
            raise QgsProcessingException(
                "Poligonlaştırma tamamlanamadı. Çizgiler tam kapalı halka oluşturmuyor olabilir (Topoloji / Snap hatası)."
            )

        feedback.pushInfo(f"Toplam {poly_obj.featureCount()} adet kapalı poligon üretildi.")

        # 3. Mekânsal Birleştirme (Largest Overlap)
        feedback.pushInfo("3. Aşama: Plan poligonlarıyla en büyük çakışmaya göre öznitelikler aktarılıyor...")
        final_result = processing.run("native:joinattributesbylocation", {
            'INPUT': poly_id,
            'JOIN': parameters[self.INPUT_ZONES],
            'PREDICATE': [0],  # intersects
            'JOIN_FIELDS': [],
            'METHOD': 2,  # Largest overlap
            'DISCARD_NONMATCHING': False,
            'PREFIX': '',
            'OUTPUT': parameters[self.OUTPUT]
        }, context=context, feedback=feedback, is_child_algorithm=True)

        return {self.OUTPUT: final_result['OUTPUT']}

    def createInstance(self):
        return YolPoligonlasmaAlgorithm()
