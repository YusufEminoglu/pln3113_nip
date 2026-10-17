# -*- coding: utf-8 -*-
"""1/5000 Nazım İmar Planı (NİP) Çizim Veritabanı ve Şablonu Oluşturma Algoritması.

DEÜ Mimarlık Fakültesi Şehir ve Bölge Planlama Bölümü
PLN3113 - Tire NİP Analiz Stüdyosu
"""
from __future__ import annotations

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterCrs,
    QgsProcessingParameterFileDestination,
    QgsProcessingOutputString
)

from ..core.nip_workspace import create_nip_drawing_workspace, load_nip_drawing_layers


class NipWorkspaceAlgorithm(QgsProcessingAlgorithm):
    OUTPUT_GPKG = 'OUTPUT_GPKG'
    CRS = 'CRS'
    LOAD_LAYERS = 'LOAD_LAYERS'
    RESULT_PATH = 'RESULT_PATH'

    def name(self):
        return 'nip_workspace_generator'

    def displayName(self):
        return '1/5000 NİP Çizim Veritabanı ve Şablonu Oluştur (GeoPackage) - MPYY 1.1.7'

    def group(self):
        return '02. NİP Çizim Veritabanı ve Şablonu'

    def groupId(self):
        return '02_nip_cizim_sablonu'

    def shortHelpString(self):
        return (
            "Çevre, Şehircilik ve İklim Değişikliği Bakanlığı Mekânsal Planlar Yapım Yönetmeliği "
            "(MPYY) 1.1.7 XSD şemasına (nip.V.1.1.7.xsd) ve PLN3113 stüdyo standartlarına uygun "
            "1/5000 Nazım İmar Planı (NİP) boş çizim veritabanını (GeoPackage) üretir.\n\n"
            "Veritabanı içeriğinde:\n"
            "• 87 adet MPYY 1.1.7 plan nesnesi tipi (Alanlar, Çizgiler, Noktalar)\n"
            "• Bakanlık e-Plan SLD stilleri ve gömülü raster taramalar\n"
            "• Ek-1e Sembol Hiyerarşisi kütüğü (mpyy_detay_katalogu)\n"
            "• Tüm nitelikler için hazır Türkçe ValueMap açılır form menüleri ve kısıtları\n\n"
            "Varsayılan Koordinat Referans Sistemi: EPSG:5253 (TUREF / 3-derece Dilim 9)."
        )

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterFileDestination(
                self.OUTPUT_GPKG,
                'Oluşturulacak NİP GeoPackage Veritabanı Dosyası (*.gpkg)',
                fileFilter='GeoPackage (*.gpkg)'
            )
        )
        self.addParameter(
            QgsProcessingParameterCrs(
                self.CRS,
                'Koordinat Referans Sistemi (KRS)',
                defaultValue='EPSG:5253'
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.LOAD_LAYERS,
                'Oluşturulan Katmanları ve Stilleri QGIS Projesine Otomatik Yükle',
                defaultValue=True
            )
        )
        self.addOutput(
            QgsProcessingOutputString(
                self.RESULT_PATH,
                'Oluşturulan GeoPackage Yolu'
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        output_file = self.parameterAsFileOutput(parameters, self.OUTPUT_GPKG, context)
        crs = self.parameterAsCrs(parameters, self.CRS, context)
        load_layers = self.parameterAsBool(parameters, self.LOAD_LAYERS, context)

        if not output_file:
            raise QgsProcessingException("Lütfen geçerli bir çıktı GeoPackage dosya yolu belirleyin!")

        if not crs or not crs.isValid():
            crs = QgsCoordinateReferenceSystem("EPSG:5253")

        feedback.pushInfo(f"NİP Çizim Veritabanı üretiliyor: {output_file} (KRS: {crs.authid()})...")

        try:
            created_path = create_nip_drawing_workspace(output_file, crs)
            feedback.pushInfo("Veritabanı, lookup tabloları ve QML stilleri başarıyla yazıldı.")
        except Exception as e:
            raise QgsProcessingException(f"Veritabanı oluşturulurken hata oluştu: {str(e)}")

        if load_layers and context.project():
            feedback.pushInfo("Katmanlar ve nitelik ilişkileri QGIS projesine yükleniyor...")
            load_nip_drawing_layers(created_path, context.project())

        return {
            self.RESULT_PATH: created_path
        }

    def createInstance(self):
        return NipWorkspaceAlgorithm()
