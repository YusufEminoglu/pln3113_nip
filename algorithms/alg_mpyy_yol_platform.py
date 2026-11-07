# -*- coding: utf-8 -*-
"""Var olan Yolorta akslarından MPYY yol platformu (DigerYolNesneleri + AdaKenari)."""
from __future__ import annotations

from qgis.core import (
    Qgis,
    QgsGeometry,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingOutputNumber,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterNumber,
    QgsProcessingParameterVectorLayer,
)

from ..core.mpyy_road import YolProfili, yol_ekle

NUM_DOUBLE = (Qgis.ProcessingNumberParameterType.Double if hasattr(Qgis, "ProcessingNumberParameterType")
              else QgsProcessingParameterNumber.Type.Double)
NO_THREADING = (Qgis.ProcessingAlgorithmFlag.NoThreading if hasattr(Qgis, "ProcessingAlgorithmFlag")
                else QgsProcessingAlgorithm.Flag.FlagNoThreading)


class MpyyYolPlatformAlgorithm(QgsProcessingAlgorithm):
    YOLORTA = "YOLORTA"
    DIGER = "DIGER"
    ADA = "ADA"
    KALDIRIM = "KALDIRIM"
    REFUJ = "REFUJ"
    SADECE_EKSIK = "SADECE_EKSIK"
    KOSE = "KOSE"

    def name(self):
        return "nip_mpyy_yol_platform"

    def displayName(self):
        return "MPYY Yolorta'dan Yol Platformu Üret"

    def group(self):
        return "03. Yol Platformu ve Geometri Üretimi"

    def groupId(self):
        return "03_yol_geometri_uretimi"

    def createInstance(self):
        return MpyyYolPlatformAlgorithm()

    def flags(self):
        return super().flags() | NO_THREADING

    def shortHelpString(self):
        return (
            "MPYY 1.1.7 NİP veritabanındaki Yolorta akslarından, YolGenisligi değerine göre yol "
            "platformunu üretir ve doğrudan veritabanına yazar: DigerYolNesneleri'ne taşıt yolu, "
            "refüj ve kaldırım; AdaKenari'na platformun dış kenarları. Kesişen yollarda kavşak "
            "açılır ve köşeleri verilen yarıçapla yuvarlanır (ada kenarı R, bordür R + kaldırım); "
            "platform parçaları birbiriyle çakışmaz.\n\n"
            "Taşıt yolu = YolGenisligi − 2 × kaldırım − refüj. YolGenisligi boş ya da buna "
            "yetmeyen akslar atlanır ve uyarı verilir. Varsayılan olarak yalnız platformu "
            "olmayan akslar işlenir.\n"
            "Yeni yolu haritada çizerek üretmek için paneldeki 'MPYY Yol Çiz' aracını kullanın."
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.YOLORTA, "Yolorta (yol orta aksı)", [QgsProcessing.SourceType.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.DIGER, "DigerYolNesneleri (yol platformu)", [QgsProcessing.SourceType.TypeVectorPolygon]))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.ADA, "AdaKenari", [QgsProcessing.SourceType.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterNumber(
            self.KALDIRIM, "Her iki yanda kaldırım (m)", NUM_DOUBLE, 0.0, minValue=0.0, maxValue=20.0))
        self.addParameter(QgsProcessingParameterNumber(
            self.REFUJ, "Orta refüj (m)", NUM_DOUBLE, 0.0, minValue=0.0, maxValue=50.0))
        self.addParameter(QgsProcessingParameterNumber(
            self.KOSE, "Kavşak köşe yarıçapı (m; 0: yuvarlanmaz)", NUM_DOUBLE, 8.0, minValue=0.0, maxValue=50.0))
        self.addParameter(QgsProcessingParameterBoolean(
            self.SADECE_EKSIK, "Yalnız platformu olmayan aksları işle", True))
        self.addOutput(QgsProcessingOutputNumber("URETILEN", "Platformu üretilen aks sayısı"))
        self.addOutput(QgsProcessingOutputNumber("ATLANAN", "Atlanan aks sayısı"))

    def processAlgorithm(self, parameters, context, feedback):
        yolorta = self.parameterAsVectorLayer(parameters, self.YOLORTA, context)
        diger = self.parameterAsVectorLayer(parameters, self.DIGER, context)
        ada = self.parameterAsVectorLayer(parameters, self.ADA, context)
        kaldirim = self.parameterAsDouble(parameters, self.KALDIRIM, context)
        refuj = self.parameterAsDouble(parameters, self.REFUJ, context)
        sadece_eksik = self.parameterAsBoolean(parameters, self.SADECE_EKSIK, context)
        kose = self.parameterAsDouble(parameters, self.KOSE, context)
        if None in (yolorta, diger, ada):
            raise QgsProcessingException("Üç katman da seçilmeli.")
        for name in ("YolGenisligi", "YolTip"):
            if yolorta.fields().indexOf(name) < 0:
                raise QgsProcessingException(f"Yolorta katmanında {name} alanı yok.")

        akslar = [f for f in yolorta.getFeatures() if f.hasGeometry()]
        uretilen = atlanan = 0
        for i, feature in enumerate(akslar):
            if feedback.isCanceled():
                break
            feedback.setProgress(100.0 * i / max(1, len(akslar)))
            geom = feature.geometry()
            if sadece_eksik:
                platform = [p.geometry() for p in diger.getFeatures(geom.boundingBox())
                            if p.hasGeometry() and p.geometry().intersects(geom)]
                if platform:
                    on = geom.intersection(QgsGeometry.unaryUnion(platform)).length()
                    if on >= 0.9 * geom.length():
                        continue
            genislik = feature["YolGenisligi"]
            tip = feature["YolTip"] or "2DereceYol"
            try:
                profil = YolProfili.genislikten(str(tip), float(genislik), kaldirim, refuj, kose)
                yol_ekle(geom, profil, None, diger, ada, yolorta_yaz=False)
                uretilen += 1
            except (TypeError, ValueError) as exc:
                feedback.pushWarning(f"Yolorta #{feature.id()} atlandı: {exc}")
                atlanan += 1
        feedback.pushInfo(f"Platformu üretilen aks: {uretilen}, atlanan: {atlanan}")
        return {"URETILEN": uretilen, "ATLANAN": atlanan}
