# -*- coding: utf-8 -*-
"""Ada, Parsel ve Bina İçin Ön Cephe ve Servis Alma Noktası Bulucu Algoritması.

PLN3113 - Tire NİP Analiz Stüdyosu
"""
from __future__ import annotations

try:
    import processing
except ImportError:
    processing = None
from qgis.core import (
    QgsFeature,
    QgsFeatureSink,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingUtils,
    QgsPointXY,
    QgsWkbTypes
)
from qgis.PyQt.QtCore import QVariant


class OnCepheBulucuAlgorithm(QgsProcessingAlgorithm):
    INPUT_POLYGONS = 'INPUT_POLYGONS'
    INPUT_ROADS = 'INPUT_ROADS'
    OUTPUT_LINES = 'OUTPUT_LINES'
    OUTPUT_POINTS = 'OUTPUT_POINTS'

    def name(self):
        return 'on_cephe_ve_servis_noktasi_bulucu'

    def displayName(self):
        return '1. Ada / Parsel / Bina Ön Cephe ve Servis Noktası Bulucu'

    def group(self):
        return '05. Ulaşım ve Network Analizleri'

    def groupId(self):
        return '05_ulasim_network_analizleri'

    def shortHelpString(self):
        return (
            "İmar adası, parsel veya bina poligonlarının sınır kenarlarını ayrıştırarak (explode lines), "
            "yol ağına en yakın olan kenarını (Ön Cephe) tespit eder.\n\n"
            "Çıktı olarak:\n"
            "1. En Yakın Servis Yoluna Uzaklık Hatları (Mesafe çizgisi ve uzaklık özniteliği)\n"
            "2. Servis Aldığı Cephe Noktası (Network analizlerinde 'Nereden / Origin' başlangıç noktası olarak kullanılır)"
        )

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT_POLYGONS,
                'Poligon Katmanı (Ada, Parsel veya Bina)',
                [QgsProcessing.SourceType.TypeVectorPolygon]
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
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_LINES,
                'En Yakın Servis Yoluna Bağlantı Çizgileri (Line)',
                QgsProcessing.SourceType.TypeVectorLine
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_POINTS,
                'Servis Aldığı Cephe Noktaları - Origin (Point)',
                QgsProcessing.SourceType.TypeVectorPoint
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        source_poly = self.parameterAsSource(parameters, self.INPUT_POLYGONS, context)
        source_roads = self.parameterAsSource(parameters, self.INPUT_ROADS, context)

        if not source_poly or not source_roads:
            raise QgsProcessingException("Gerekli girdi katmanları bulunamadı!")

        feedback.pushInfo("1. Aşama: Poligon sınırları çizgilere ve kenarlara parçalanıyor...")
        poly_to_lines = processing.run('native:polygonstolines', {
            'INPUT': parameters[self.INPUT_POLYGONS],
            'OUTPUT': 'TEMPORARY_OUTPUT'
        }, context=context, feedback=feedback, is_child_algorithm=True)

        exploded_lines = processing.run('native:explodelines', {
            'INPUT': poly_to_lines['OUTPUT'],
            'OUTPUT': 'TEMPORARY_OUTPUT'
        }, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.pushInfo("2. Aşama: Kenar ağırlık merkezleri hesaplanıyor...")
        centroids = processing.run('native:centroids', {
            'INPUT': exploded_lines['OUTPUT'],
            'ALL_PARTS': False,
            'OUTPUT': 'TEMPORARY_OUTPUT'
        }, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.pushInfo("3. Aşama: Kenar merkezlerinden yollara en kısa dik çizgiler türetiliyor...")
        shortest_lines = processing.run('native:shortestline', {
            'SOURCE': centroids['OUTPUT'],
            'DESTINATION': parameters[self.INPUT_ROADS],
            'METHOD': 0,
            'NEIGHBORS': 1,
            'DISTANCE': None,
            'OUTPUT': 'TEMPORARY_OUTPUT'
        }, context=context, feedback=feedback, is_child_algorithm=True)

        # En kısa çizgileri orijinal poligon fid'sine göre gruplayıp en yakın olanı seçme
        short_obj = QgsProcessingUtils.mapLayerFromString(str(shortest_lines['OUTPUT']), context)
        if not short_obj or short_obj.featureCount() == 0:
            raise QgsProcessingException("Uzaklık çizgileri hesaplanamadı.")

        # Line sink tanımla
        fields_line = QgsFields(short_obj.fields())
        fields_line.append(QgsField("servis_mesafe_m", QVariant.Double))
        (sink_lines, dest_lines_id) = self.parameterAsSink(
            parameters,
            self.OUTPUT_LINES,
            context,
            fields_line,
            QgsWkbTypes.Type.LineString,
            short_obj.sourceCrs()
        )

        # Point sink tanımla
        fields_pt = QgsFields(source_poly.fields())
        fields_pt.append(QgsField("poly_fid", QVariant.LongLong))
        fields_pt.append(QgsField("servis_mesafe_m", QVariant.Double))
        (sink_pts, dest_pts_id) = self.parameterAsSink(
            parameters,
            self.OUTPUT_POINTS,
            context,
            fields_pt,
            QgsWkbTypes.Type.Point,
            short_obj.sourceCrs()
        )

        # Her orijinal poligon için en kısa kenarı tespit et
        best_by_poly = {}
        for feat in short_obj.getFeatures():
            geom = feat.geometry()
            if not geom or geom.isEmpty():
                continue
            dist = geom.length()
            poly_id = feat.id()
            # Özniteliklerde fid veya kaynak id varsa
            for candidate_field in ["fid", "id", "ID", "source_fid"]:
                if candidate_field in [f.name() for f in feat.fields()] and feat[candidate_field] is not None:
                    poly_id = feat[candidate_field]
                    break

            if poly_id not in best_by_poly or dist < best_by_poly[poly_id]["dist"]:
                best_by_poly[poly_id] = {
                    "dist": dist,
                    "feat": feat,
                    "geom": geom
                }

        feedback.pushInfo(f"Toplam {len(best_by_poly)} adet ada/parsel/bina için ön cephe ve servis noktası oluşturuluyor...")

        for poly_id, item in best_by_poly.items():
            g = item["geom"]
            dist_val = round(item["dist"], 2)

            # Çizgi özelliği
            lf = QgsFeature(fields_line)
            lf.setGeometry(g)
            vals_line = list(item["feat"].attributes())
            vals_line.append(dist_val)
            lf.setAttributes(vals_line)
            sink_lines.addFeature(lf, QgsFeatureSink.Flag.FastInsert)

            # Başlangıç noktası (Cephe Noktası)
            line_abs = g.constGet()
            if line_abs and line_abs.numPoints() >= 1:
                p_origin = QgsPointXY(line_abs.startPoint().x(), line_abs.startPoint().y())
                pf = QgsFeature(fields_pt)
                pf.setGeometry(QgsGeometry.fromPointXY(p_origin))
                attrs = []
                for fld in source_poly.fields():
                    if fld.name() in [f.name() for f in item["feat"].fields()]:
                        attrs.append(item["feat"][fld.name()])
                    else:
                        attrs.append(None)
                attrs.extend([poly_id, dist_val])
                pf.setAttributes(attrs)
                sink_pts.addFeature(pf, QgsFeatureSink.Flag.FastInsert)

        return {
            self.OUTPUT_LINES: dest_lines_id,
            self.OUTPUT_POINTS: dest_pts_id
        }

    def createInstance(self):
        return OnCepheBulucuAlgorithm()
