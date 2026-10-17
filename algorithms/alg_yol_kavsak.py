# -*- coding: utf-8 -*-
"""2. Kavşak Temizleme, Trim ve Yaklaşım Parçalama Algoritması.

DEÜ Mimarlık Fakültesi Şehir ve Bölge Planlama Bölümü
PLN3113 - Tire NİP Analiz Stüdyosu
"""
from __future__ import annotations

from qgis.core import (
    QgsFeature,
    QgsFeatureSink,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsPointXY,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterNumber,
    QgsSpatialIndex,
    QgsWkbTypes
)
from qgis.PyQt.QtCore import QVariant


class YolKavsakTrimAlgorithm(QgsProcessingAlgorithm):
    INPUT = 'INPUT'
    OUTPUT = 'OUTPUT'
    RADIUS = 'RADIUS'
    SPLIT_DIST = 'SPLIT_DIST'
    TOLERANCE = 'TOLERANCE'

    def name(self):
        return 'nip_yol_kavsak_trim'

    def displayName(self):
        return '2. Kavşak Temizle ve Yaklaşım Parçala (Trim & Split)'

    def group(self):
        return '03. Yol Platformu ve Geometri Üretimi'

    def groupId(self):
        return '03_yol_geometri_uretimi'

    def shortHelpString(self):
        return (
            "Yol platform katmanındaki merkez hatlarının kesişim noktalarından otomatik kavşak "
            "tamponları (radius) oluşturur; kavşak içindeki yan yol sınırlarını ve bordür çizgilerini "
            "kesip temizler (trim). Ardından kavşak çıkış noktalarından itibaren belirlenen yaklaşım "
            "mesafesinde (split_dist örn: 5m) hatları parçalar."
        )

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT,
                'Girdi Yol Platform Katmanı (Line)',
                [QgsProcessing.SourceType.TypeVectorLine]
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.RADIUS,
                'Kavşak Temizleme Yarıçapı (m)',
                QgsProcessingParameterNumber.Type.Double,
                defaultValue=20.0,
                minValue=1.0,
                maxValue=150.0
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.SPLIT_DIST,
                'Kavşak Yaklaşım / Ayrım Mesafesi (m)',
                QgsProcessingParameterNumber.Type.Double,
                defaultValue=5.0,
                minValue=0.5,
                maxValue=50.0
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.TOLERANCE,
                'Kesişim Yakalama Toleransı - Snap (m)',
                QgsProcessingParameterNumber.Type.Double,
                defaultValue=0.25,
                minValue=0.01,
                maxValue=5.0
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                'Temizlenmiş Yol Platform Katmanı (MultiLineString)',
                QgsProcessing.SourceType.TypeVectorLine
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        if not source:
            raise QgsProcessingException("Girdi katmanı bulunamadı!")

        radius = self.parameterAsDouble(parameters, self.RADIUS, context)
        split_dist = self.parameterAsDouble(parameters, self.SPLIT_DIST, context)
        snap_tolerance = self.parameterAsDouble(parameters, self.TOLERANCE, context)

        fields = QgsFields(source.fields())
        extra_fields = [
            ("parent_fid", QVariant.LongLong),
            ("type_link", QVariant.String),
            ("parca_no", QVariant.Int),
            ("length_m", QVariant.Double),
            ("eligibility", QVariant.Int)
        ]
        for fname, fvar in extra_fields:
            if fields.indexFromName(fname) == -1:
                fields.append(QgsField(fname, fvar))

        (sink, dest_id) = self.parameterAsSink(
            parameters,
            self.OUTPUT,
            context,
            fields,
            QgsWkbTypes.Type.MultiLineString,
            source.sourceCrs()
        )

        centers = []
        others = []

        for f in source.getFeatures():
            ftype = "unknown"
            if "type" in [fld.name() for fld in source.fields()]:
                ftype = str(f["type"] or "unknown").strip().lower()
            if ftype == "center":
                centers.append(f)
            else:
                others.append(f)

        feedback.pushInfo(f"Toplam {len(centers)} merkez hattı ve {len(others)} yan hat tespit edildi.")

        # 2. Kavşak Bulma
        junction_buffers = []
        center_index = QgsSpatialIndex()
        for f in centers:
            center_index.insertFeature(f)

        processed_pairs = set()
        for f1 in centers:
            if feedback.isCanceled():
                break
            bbox = f1.geometry().boundingBox()
            bbox.grow(snap_tolerance * 2)
            candidates = center_index.intersects(bbox)

            for fid2 in candidates:
                if fid2 == f1.id():
                    continue
                pair = tuple(sorted((f1.id(), fid2)))
                if pair in processed_pairs:
                    continue
                processed_pairs.add(pair)

                f2 = next((x for x in centers if x.id() == fid2), None)
                if not f2:
                    continue

                geom1 = f1.geometry()
                geom2 = f2.geometry()

                if geom1.distance(geom2) <= snap_tolerance:
                    intersect_pt = None
                    if geom1.intersects(geom2):
                        intersection = geom1.intersection(geom2)
                        if not intersection.isEmpty():
                            intersect_pt = (
                                intersection.asGeometryCollection()[0]
                                if intersection.isMultipart()
                                else intersection
                            )
                    else:
                        shortest = geom1.shortestLine(geom2)
                        if shortest:
                            intersect_pt = shortest.centroid()

                    if intersect_pt:
                        pt_geom = (
                            QgsGeometry.fromPointXY(intersect_pt)
                            if isinstance(intersect_pt, QgsPointXY)
                            else intersect_pt
                        )
                        junction_buffers.append(pt_geom.buffer(radius, 8))

        combined_junction_geom = QgsGeometry()
        if junction_buffers:
            combined_junction_geom = QgsGeometry.unaryUnion(junction_buffers)

        # 3. Center Hatlarını Aynen Yaz
        for f in centers:
            new_f = QgsFeature(fields)
            geom_c = QgsGeometry(f.geometry())
            if not geom_c.isMultipart():
                geom_c.convertToMultiType()
            new_f.setGeometry(geom_c)
            vals = list(f.attributes())
            vals.extend([f.id(), 'center', 0, round(geom_c.length(), 2), 1])
            new_f.setAttributes(vals)
            sink.addFeature(new_f, QgsFeatureSink.Flag.FastInsert)

        # 4. Trim ve Yaklaşım Ayrımı
        feedback.pushInfo(f"Yan hatlar kavşaktan trimleniyor ve {split_dist}m yaklaşım mesafesine göre parçalanıyor...")
        total_others = len(others)

        for i, f in enumerate(others):
            if feedback.isCanceled():
                break

            geom = f.geometry()
            was_trimmed = False

            if not combined_junction_geom.isEmpty() and geom.intersects(combined_junction_geom):
                trimmed_geom = geom.difference(combined_junction_geom)
                was_trimmed = True
            else:
                trimmed_geom = geom

            if not trimmed_geom or trimmed_geom.isEmpty():
                continue

            parts = trimmed_geom.asGeometryCollection() if trimmed_geom.isMultipart() else [trimmed_geom]
            part_no = 1

            for part in parts:
                if QgsWkbTypes.geometryType(part.wkbType()) != QgsWkbTypes.GeometryType.LineGeometry:
                    continue

                line_abstract = part.constGet()
                length = part.length()
                final_segments = []

                if was_trimmed and length > (split_dist + 0.1):
                    p_start = QgsGeometry.fromPointXY(QgsPointXY(line_abstract.startPoint().x(), line_abstract.startPoint().y()))
                    p_end = QgsGeometry.fromPointXY(QgsPointXY(line_abstract.endPoint().x(), line_abstract.endPoint().y()))

                    dist_start = p_start.distance(combined_junction_geom) if not combined_junction_geom.isEmpty() else 999.0
                    dist_end = p_end.distance(combined_junction_geom) if not combined_junction_geom.isEmpty() else 999.0

                    touch_start = dist_start < 0.1
                    touch_end = dist_end < 0.1

                    if touch_start and touch_end and length > (split_dist * 2):
                        seg1 = QgsGeometry(line_abstract.curveSubstring(0, split_dist))
                        seg2 = QgsGeometry(line_abstract.curveSubstring(split_dist, length - split_dist))
                        seg3 = QgsGeometry(line_abstract.curveSubstring(length - split_dist, length))
                        final_segments.append((seg1, 'approach_5m'))
                        final_segments.append((seg2, 'road_segment'))
                        final_segments.append((seg3, 'approach_5m'))
                    elif touch_start:
                        seg1 = QgsGeometry(line_abstract.curveSubstring(0, split_dist))
                        seg2 = QgsGeometry(line_abstract.curveSubstring(split_dist, length))
                        final_segments.append((seg1, 'approach_5m'))
                        final_segments.append((seg2, 'road_segment'))
                    elif touch_end:
                        seg1 = QgsGeometry(line_abstract.curveSubstring(0, length - split_dist))
                        seg2 = QgsGeometry(line_abstract.curveSubstring(length - split_dist, length))
                        final_segments.append((seg1, 'road_segment'))
                        final_segments.append((seg2, 'approach_5m'))
                    else:
                        final_segments.append((part, 'trimmed_part'))
                else:
                    type_str = 'trimmed_part' if was_trimmed else 'original_part'
                    final_segments.append((part, type_str))

                for seg_geom, seg_type in final_segments:
                    if not seg_geom or seg_geom.isEmpty():
                        continue
                    seg_len = seg_geom.length()
                    eligible = 1 if seg_len > 1.0 else 0

                    if not seg_geom.isMultipart():
                        seg_geom.convertToMultiType()

                    new_f = QgsFeature(fields)
                    new_f.setGeometry(seg_geom)
                    vals = list(f.attributes())
                    vals.extend([f.id(), seg_type, part_no, round(seg_len, 2), eligible])
                    new_f.setAttributes(vals)
                    sink.addFeature(new_f, QgsFeatureSink.Flag.FastInsert)
                    part_no += 1

            if total_others > 0 and i % 25 == 0:
                feedback.setProgress(int(i / total_others * 100))

        return {self.OUTPUT: dest_id}

    def createInstance(self):
        return YolKavsakTrimAlgorithm()
