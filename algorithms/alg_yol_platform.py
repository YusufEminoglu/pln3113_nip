# -*- coding: utf-8 -*-
"""1. Yol Platformu, Bordür ve Refüj Hatları Üretme Algoritması.

DEÜ Mimarlık Fakültesi Şehir ve Bölge Planlama Bölümü
PLN3113 - Tire NİP Analiz Stüdyosu
"""
from __future__ import annotations

import contextlib
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
    QgsProcessingParameterField,
    QgsProcessingParameterNumber,
    QgsWkbTypes
)
from qgis.PyQt.QtCore import QVariant


class YolPlatformAlgorithm(QgsProcessingAlgorithm):
    INPUT = 'INPUT'
    FIELD_YOL_TIPI = 'FIELD_YOL_TIPI'
    FIELD_GENISLIK = 'FIELD_GENISLIK'
    FIELD_REFUJ = 'FIELD_REFUJ'
    FIELD_SOL_KALDIRIM = 'FIELD_SOL_KALDIRIM'
    FIELD_SAG_KALDIRIM = 'FIELD_SAG_KALDIRIM'
    DEFAULT_GENISLIK = 'DEFAULT_GENISLIK'
    OUTPUT = 'OUTPUT'

    def name(self):
        return 'nip_yol_platform_uretici'

    def displayName(self):
        return '1. Yol Platformu, Kaldırım ve Refüj Çizgileri Üret'

    def group(self):
        return '03. Yol Platformu ve Geometri Üretimi'

    def groupId(self):
        return '03_yol_geometri_uretimi'

    def shortHelpString(self):
        return (
            "1/5000 NİP yol orta aksı çizgilerinden, yol genişliği, refüj ve tretuvar/kaldırım "
            "ölçülerine göre otomatik olarak paralel yol sınırlarını, refüj kenarlarını ve "
            "kaldırım bordür çizgilerini üretir.\n\n"
            "Sütunlar katmanda mevcutsa otomatik eşleştirilir; sütun bulunamazsa belirlenen "
            "varsayılan genişlik değeri uygulanır."
        )

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT,
                'Yol Orta Çizgi Katmanı (Line)',
                [QgsProcessing.SourceType.TypeVectorLine]
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.FIELD_YOL_TIPI,
                'Yol Tipi / Hiyerarşi Sütunu (Opsiyonel)',
                parentLayerParameterName=self.INPUT,
                type=QgsProcessingParameterField.DataType.String,
                optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.FIELD_GENISLIK,
                'Yol Toplam Genişliği Sütunu (örn: yolGenislik2 veya genislik)',
                parentLayerParameterName=self.INPUT,
                type=QgsProcessingParameterField.DataType.Numeric,
                optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.DEFAULT_GENISLIK,
                'Sütun Yoksa Varsayılan Yol Genişliği (m)',
                QgsProcessingParameterNumber.Type.Double,
                defaultValue=15.0,
                minValue=3.0,
                maxValue=100.0
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.FIELD_REFUJ,
                'Refüj Genişliği Sütunu (Opsiyonel - örn: refujGenislik)',
                parentLayerParameterName=self.INPUT,
                type=QgsProcessingParameterField.DataType.Numeric,
                optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.FIELD_SOL_KALDIRIM,
                'Sol Kaldırım Genişliği Sütunu (Opsiyonel - örn: solKaldirimGenislik)',
                parentLayerParameterName=self.INPUT,
                type=QgsProcessingParameterField.DataType.Numeric,
                optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.FIELD_SAG_KALDIRIM,
                'Sağ Kaldırım Genişliği Sütunu (Opsiyonel - örn: sagKaldirimGenislik)',
                parentLayerParameterName=self.INPUT,
                type=QgsProcessingParameterField.DataType.Numeric,
                optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                'Üretilen Yol Platform Katmanı (MultiLineString)',
                QgsProcessing.SourceType.TypeVectorLine
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        if not source:
            raise QgsProcessingException("Girdi katmanı bulunamadı!")

        col_yol_tipi = self.parameterAsString(parameters, self.FIELD_YOL_TIPI, context)
        col_genislik = self.parameterAsString(parameters, self.FIELD_GENISLIK, context)
        col_refuj = self.parameterAsString(parameters, self.FIELD_REFUJ, context)
        col_sol_kald = self.parameterAsString(parameters, self.FIELD_SOL_KALDIRIM, context)
        col_sag_kald = self.parameterAsString(parameters, self.FIELD_SAG_KALDIRIM, context)
        def_genislik = self.parameterAsDouble(parameters, self.DEFAULT_GENISLIK, context)

        fields = QgsFields()
        fields.append(QgsField("source_fid", QVariant.LongLong))
        fields.append(QgsField("yolTipi", QVariant.String))
        fields.append(QgsField("type", QVariant.String))
        fields.append(QgsField("side", QVariant.String))
        fields.append(QgsField("genislik_m", QVariant.Double))

        (sink, dest_id) = self.parameterAsSink(
            parameters,
            self.OUTPUT,
            context,
            fields,
            QgsWkbTypes.Type.MultiLineString,
            source.sourceCrs()
        )

        def offset_geom(geom: QgsGeometry, offset: float) -> QgsGeometry:
            return geom.offsetCurve(offset, 8, QgsGeometry.JoinStyle.JoinStyleRound, 2.0)

        total = source.featureCount()
        for idx, feat in enumerate(source.getFeatures()):
            if feedback.isCanceled():
                break

            fid = feat.id()
            geom = feat.geometry()
            if not geom or geom.isEmpty():
                continue

            yol_tipi = "Taşıt Yolu"
            if col_yol_tipi and feat[col_yol_tipi] is not None:
                yol_tipi = str(feat[col_yol_tipi])

            genislik = def_genislik
            if col_genislik and feat[col_genislik] is not None:
                with contextlib.suppress(Exception):
                    genislik = float(feat[col_genislik])

            refuj = 0.0
            if col_refuj and feat[col_refuj] is not None:
                with contextlib.suppress(Exception):
                    refuj = float(feat[col_refuj])

            sol_kald = 0.0
            if col_sol_kald and feat[col_sol_kald] is not None:
                with contextlib.suppress(Exception):
                    sol_kald = float(feat[col_sol_kald])

            sag_kald = 0.0
            if col_sag_kald and feat[col_sag_kald] is not None:
                with contextlib.suppress(Exception):
                    sag_kald = float(feat[col_sag_kald])

            # 1. Merkez Hattı
            c_feat = QgsFeature(fields)
            c_feat.setAttribute("source_fid", fid)
            c_feat.setAttribute("yolTipi", yol_tipi)
            c_feat.setAttribute("type", "center")
            c_feat.setAttribute("side", "none")
            c_feat.setAttribute("genislik_m", genislik)
            c_geom = QgsGeometry(geom)
            if not c_geom.isMultipart():
                c_geom.convertToMultiType()
            c_feat.setGeometry(c_geom)
            sink.addFeature(c_feat, QgsFeatureSink.Flag.FastInsert)

            # 2. Refüj Hatları
            if refuj > 0:
                half_refuj = refuj / 2.0
                for side, direction in [("left", -1), ("right", 1)]:
                    r_geom = offset_geom(geom, direction * half_refuj)
                    if r_geom and not r_geom.isEmpty():
                        rf = QgsFeature(fields)
                        rf.setAttribute("source_fid", fid)
                        rf.setAttribute("yolTipi", yol_tipi)
                        rf.setAttribute("type", "refuj")
                        rf.setAttribute("side", side)
                        rf.setAttribute("genislik_m", refuj)
                        if not r_geom.isMultipart():
                            r_geom.convertToMultiType()
                        rf.setGeometry(r_geom)
                        sink.addFeature(rf, QgsFeatureSink.Flag.FastInsert)

            # 3. Yol Dış Sınırları ve Kaldırımlar
            half_width = genislik / 2.0
            if half_width > 0:
                # Sol Taraf
                l_outer_geom = offset_geom(geom, -1 * half_width)
                if l_outer_geom and not l_outer_geom.isEmpty():
                    lf = QgsFeature(fields)
                    lf.setAttribute("source_fid", fid)
                    lf.setAttribute("yolTipi", yol_tipi)
                    lf.setAttribute("type", "yol_siniri")
                    lf.setAttribute("side", "left_outer")
                    lf.setAttribute("genislik_m", genislik)
                    if not l_outer_geom.isMultipart():
                        l_outer_geom.convertToMultiType()
                    lf.setGeometry(l_outer_geom)
                    sink.addFeature(lf, QgsFeatureSink.Flag.FastInsert)

                    if sol_kald > 0:
                        l_in_geom = offset_geom(geom, -1 * half_width + sol_kald)
                        if l_in_geom and not l_in_geom.isEmpty():
                            kf = QgsFeature(fields)
                            kf.setAttribute("source_fid", fid)
                            kf.setAttribute("yolTipi", yol_tipi)
                            kf.setAttribute("type", "kaldirim_bordur")
                            kf.setAttribute("side", "left_inner")
                            kf.setAttribute("genislik_m", sol_kald)
                            if not l_in_geom.isMultipart():
                                l_in_geom.convertToMultiType()
                            kf.setGeometry(l_in_geom)
                            sink.addFeature(kf, QgsFeatureSink.Flag.FastInsert)

                # Sağ Taraf
                r_outer_geom = offset_geom(geom, 1 * half_width)
                if r_outer_geom and not r_outer_geom.isEmpty():
                    rf = QgsFeature(fields)
                    rf.setAttribute("source_fid", fid)
                    rf.setAttribute("yolTipi", yol_tipi)
                    rf.setAttribute("type", "yol_siniri")
                    rf.setAttribute("side", "right_outer")
                    rf.setAttribute("genislik_m", genislik)
                    if not r_outer_geom.isMultipart():
                        r_outer_geom.convertToMultiType()
                    rf.setGeometry(r_outer_geom)
                    sink.addFeature(rf, QgsFeatureSink.Flag.FastInsert)

                    if sag_kald > 0:
                        r_in_geom = offset_geom(geom, 1 * half_width - sag_kald)
                        if r_in_geom and not r_in_geom.isEmpty():
                            rkf = QgsFeature(fields)
                            rkf.setAttribute("source_fid", fid)
                            rkf.setAttribute("yolTipi", yol_tipi)
                            rkf.setAttribute("type", "kaldirim_bordur")
                            rkf.setAttribute("side", "right_inner")
                            rkf.setAttribute("genislik_m", sag_kald)
                            if not r_in_geom.isMultipart():
                                r_in_geom.convertToMultiType()
                            rkf.setGeometry(r_in_geom)
                            sink.addFeature(rkf, QgsFeatureSink.Flag.FastInsert)

            if total > 0 and idx % 20 == 0:
                feedback.setProgress(int((idx / total) * 100))

        return {self.OUTPUT: dest_id}

    def createInstance(self):
        return YolPlatformAlgorithm()
