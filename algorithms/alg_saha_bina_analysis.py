# -*- coding: utf-8 -*-
"""3. Saha ve Bina Bazlı Fiili Nüfus ve İstihdam Tahmini Processing Algoritması.

DEÜ Mimarlık Fakültesi Şehir ve Bölge Planlama Bölümü
PLN3113 - nip_eklenti_01
"""
from __future__ import annotations

from qgis.core import (
    QgsFeature,
    QgsFeatureSink,
    QgsField,
    QgsFields,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterNumber,
    QgsProcessingParameterVectorLayer,
    QgsWkbTypes
)
from qgis.PyQt.QtCore import QVariant

from ..core.field_estimator import FieldEstimatorEngine

class SahaBinaAnalysisAlgorithm(QgsProcessingAlgorithm):
    ADA_LAYER = 'ADA_LAYER'
    BINA_LAYER = 'BINA_LAYER'
    HANEHALKI = 'HANEHALKI'
    DAIRE_M2 = 'DAIRE_M2'
    NET_ORAN = 'NET_ORAN'
    OUTPUT_ADA = 'OUTPUT_ADA'
    OUTPUT_OZET = 'OUTPUT_OZET'

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.ADA_LAYER,
                'Kadastro / Saha Adaları Katmanı',
                [QgsProcessing.TypeVectorPolygon]
            )
        )
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.BINA_LAYER,
                'Bina Katmanı (tire_bina.gpkg)',
                [QgsProcessing.TypeVectorPolygon]
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.HANEHALKI,
                'TÜİK Ortalama Hanehalkı Büyüklüğü (Tire ~ 2.85)',
                QgsProcessingParameterNumber.Double,
                defaultValue=2.85,
                minValue=1.0,
                maxValue=10.0
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.DAIRE_M2,
                'Ortalama Bağımsız Konut Alanı (m²)',
                QgsProcessingParameterNumber.Double,
                defaultValue=110.0,
                minValue=40.0,
                maxValue=500.0
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.NET_ORAN,
                'İnşaat Alanı Net/Brüt Kullanım Oranı',
                QgsProcessingParameterNumber.Double,
                defaultValue=0.85,
                minValue=0.5,
                maxValue=1.0
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_ADA,
                'Ada Bazlı Fiili Nüfus ve İstihdam Katmanı (Vektör)',
                QgsProcessing.TypeVectorPolygon
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_OZET,
                'Mevcut Kent Fiili Nüfus Özet Tablosu',
                QgsProcessing.TypeVector
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        ada_layer = self.parameterAsVectorLayer(parameters, self.ADA_LAYER, context)
        bina_layer = self.parameterAsVectorLayer(parameters, self.BINA_LAYER, context)
        hh = self.parameterAsDouble(parameters, self.HANEHALKI, context)
        daire_m2 = self.parameterAsDouble(parameters, self.DAIRE_M2, context)
        net_oran = self.parameterAsDouble(parameters, self.NET_ORAN, context)

        if not ada_layer or not bina_layer:
            raise QgsProcessingException("Ada veya bina katmanı yüklenemedi!")

        feedback.pushInfo(f"Saha ve Bina Entegrasyonu Başlatılıyor: Ada={ada_layer.featureCount()}, Bina={bina_layer.featureCount()}...")

        result_items, stats = FieldEstimatorEngine.estimate_ada_population(
            ada_layer, bina_layer, hh, daire_m2, net_oran, feedback
        )

        feedback.pushInfo(f"Eşleşen Toplam Bina Sayısı: {stats['toplam_eslesen_bina']:,}")
        feedback.pushInfo(f"Tahmini Konut Birim Sayısı: {stats['toplam_konut_birimi']:,}")
        feedback.pushInfo(f"Tahmini Fiili Yaşayan Nüfus: {stats['toplam_fiili_nufus']:,} Kişi")
        feedback.pushInfo(f"Tahmini Fiili İstihdam: {stats['toplam_fiili_istihdam']:,} Çalışan")

        # 1. Çıktı Ada Katmanı
        out_fields = QgsFields(ada_layer.fields())
        out_fields.append(QgsField('FIILI_BINA_SAYISI', QVariant.Int))
        out_fields.append(QgsField('FIILI_KONUT_SAYISI', QVariant.Int))
        out_fields.append(QgsField('FIILI_TAHMINI_NUFUS', QVariant.Int))
        out_fields.append(QgsField('FIILI_BRUT_YOGUNLUK_HA', QVariant.Double))
        out_fields.append(QgsField('FIILI_TAKS', QVariant.Double))
        out_fields.append(QgsField('FIILI_KAKS', QVariant.Double))
        out_fields.append(QgsField('ORT_KAT', QVariant.Double))
        out_fields.append(QgsField('ACIK_ALAN_YUZDE', QVariant.Double))
        out_fields.append(QgsField('SPACEMATRIX_OSR', QVariant.Double))
        out_fields.append(QgsField('BINA_YOGUNLUK_HA', QVariant.Double))
        out_fields.append(QgsField('ORT_KOMPAKLIK_IPQ', QVariant.Double))
        out_fields.append(QgsField('YAPI_NIZAMI', QVariant.String))
        out_fields.append(QgsField('MAX_BITISIK_DIZI', QVariant.Int))
        out_fields.append(QgsField('DOKU_TIPI', QVariant.String))
        out_fields.append(QgsField('FIILI_ISTIHDAM', QVariant.Int))
        out_fields.append(QgsField('FIILI_ARAC_YOLCULUK', QVariant.Int))
        out_fields.append(QgsField('FIILI_YAYA_YOLCULUK', QVariant.Int))

        (sink_ada, dest_ada_id) = self.parameterAsSink(
            parameters,
            self.OUTPUT_ADA,
            context,
            out_fields,
            QgsWkbTypes.MultiPolygon,
            ada_layer.sourceCrs()
        )

        for item in result_items:
            feat = item["feat"]
            nf = QgsFeature(out_fields)
            nf.setGeometry(item["geom"])
            attrs = feat.attributes()
            attrs.extend([
                item["bina_sayisi"],
                item["konut_birim_sayisi"],
                item["tahmini_nufus"],
                item["fiili_brut_yogunluk_ha"],
                item["fiili_taks"],
                item["fiili_kaks"],
                item["ort_kat"],
                item["acik_alan_yuzde"],
                item["spacematrix_osr"],
                item["bina_yogunluk_ha"],
                item["ort_kompaklik_ipq"],
                item["yapi_nizami"],
                item["max_bitisik_dizi"],
                item["doku_tipi"],
                item["istihdam"],
                item["gunluk_arac"],
                item["gunluk_yaya"]
            ])
            nf.setAttributes(attrs)
            sink_ada.addFeature(nf, QgsFeatureSink.FastInsert)

        # 2. Özet Tablo
        ozet_fields = QgsFields()
        ozet_fields.append(QgsField('parametre', QVariant.String))
        ozet_fields.append(QgsField('deger', QVariant.String))

        (sink_ozet, dest_ozet_id) = self.parameterAsSink(
            parameters,
            self.OUTPUT_OZET,
            context,
            ozet_fields,
            QgsWkbTypes.NoGeometry,
            ada_layer.sourceCrs()
        )

        ozet_satirlari = [
            ("Toplam Kadastro Ada Sayısı", f"{stats['toplam_ada_sayisi']:,}"),
            ("Eşleşen Toplam Bina Sayısı", f"{stats['toplam_eslesen_bina']:,}"),
            ("Tahmini Konut Sayısı (Bağımsız Birim)", f"{stats['toplam_konut_birimi']:,}"),
            ("Tahmini Fiili Yaşayan Nüfus", f"{stats['toplam_fiili_nufus']:,} Kişi"),
            ("Ortalama Fiili TAKS (Taban Doluluğu)", f"{stats['ortalama_taks']:.3f}"),
            ("Ortalama Fiili KAKS / Emsal (İnşaat Yoğunluğu)", f"{stats['ortalama_kaks']:.3f}"),
            ("Ağırlıklı Ortalama Kat Yüksekliği", f"{stats['ortalama_kat']:.1f} Kat"),
            ("Ortalama Açık Alan Oranı (%)", f"% {stats['ortalama_acik_alan_yuzde']:.1f}"),
            ("Toplam Bina Taban Alanı", f"{stats['toplam_taban_m2']:,.0f} m²"),
            ("Toplam İnşaat Alanı (Brüt Yapılaşma)", f"{stats['toplam_insaat_m2']:,.0f} m²"),
            ("Tahmini Fiili İstihdam Kapasitesi", f"{stats['toplam_fiili_istihdam']:,} Çalışan"),
            ("Hanehalkı Büyüklüğü Parametresi", f"{stats['ortalama_hanehalki']}"),
            ("Ortalama Konut Alanı Parametresi", f"{stats['ortalama_daire_m2']} m²")
        ]

        for p, d in ozet_satirlari:
            of = QgsFeature(ozet_fields)
            of.setAttributes([p, d])
            sink_ozet.addFeature(of, QgsFeatureSink.FastInsert)

        return {
            self.OUTPUT_ADA: dest_ada_id,
            self.OUTPUT_OZET: dest_ozet_id
        }

    def name(self):
        return 'tire_saha_bina_nufus'

    def displayName(self):
        return '3. Saha ve Bina Bazlı Fiili Nüfus/İstihdam Tahmini'

    def group(self):
        return 'PLN3113 NİP ve Kentsel Analiz Araçları'

    def groupId(self):
        return 'pln3113_nip_tools'

    def createInstance(self):
        return SahaBinaAnalysisAlgorithm()
