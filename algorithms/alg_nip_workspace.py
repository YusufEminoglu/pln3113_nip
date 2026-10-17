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
    QgsProcessingParameterEnum,
    QgsProcessingParameterFileDestination,
    QgsProcessingOutputString
)

from ..core.nip_workspace import (
    SCHEMA_MPYY_117,
    SCHEMA_YEREL_NIP,
    create_nip_workspace,
    load_nip_layers,
    create_nip_drawing_workspace,
    load_nip_drawing_layers
)


class NipWorkspaceAlgorithm(QgsProcessingAlgorithm):
    OUTPUT_GPKG = 'OUTPUT_GPKG'
    SCHEMA_TYPE = 'SCHEMA_TYPE'
    CRS = 'CRS'
    LOAD_LAYERS = 'LOAD_LAYERS'
    RESULT_PATH = 'RESULT_PATH'

    SCHEMA_OPTIONS = [
        'Mekânsal Planlar Yapım Yönetmeliği (MPYY 1.1.7 Resmî XSD Şeması - 87 Katman & e-Plan SLD)',
        'PLN3113 Stüdyo Yerel / Klasik NİP Şablonu (MpyyNipDB 1/5000 - Alanlar/Çizgiler/İlişkiler)'
    ]

    def name(self):
        return 'nip_workspace_generator'

    def displayName(self):
        return '1/5000 NİP Çizim Veritabanı ve Şablonu Oluştur (GeoPackage)'

    def group(self):
        return '02. NİP Çizim Veritabanı ve Şablonu'

    def groupId(self):
        return '02_nip_cizim_sablonu'

    def shortHelpString(self):
        return (
            "1/5000 Nazım İmar Planı (NİP) çizim veritabanını (GeoPackage) iki farklı standartta üretir:\n\n"
            "1. Resmî MPYY 1.1.7 XSD Şeması:\n"
            "• Çevre, Şehircilik ve İklim Değişikliği Bakanlığı resmî nip.V.1.1.7.xsd standardı\n"
            "• 87 adet plan nesnesi tipi (58 Alan, 23 Çizgi, 6 Nokta)\n"
            "• Bakanlık e-Plan SLD stilleri ve gömülü raster taramalar\n"
            "• Ek-1e Sembol Hiyerarşisi kütüğü (mpyy_detay_katalogu)\n\n"
            "2. PLN3113 Stüdyo Yerel / Klasik NİP Şablonu (MpyyNipDB 1/5000):\n"
            "• alanlar-5000, cizgiler_5000_v2, yollar_ve_adalar_icin_cizgiler, 5000_revizyon_planonama_snr, yolgenisliksembol\n"
            "• fonksiyonlar-5000_tablo ve 1-N ilişkisel form (RelationReference) kurgusu\n"
            "• Hazır QML lejant stilleri ve öznitelik form kuralları\n\n"
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
            QgsProcessingParameterEnum(
                self.SCHEMA_TYPE,
                'NİP Veritabanı Şablon Türü',
                options=self.SCHEMA_OPTIONS,
                defaultValue=0
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
        schema_idx = self.parameterAsEnum(parameters, self.SCHEMA_TYPE, context)
        crs = self.parameterAsCrs(parameters, self.CRS, context)
        load_layers = self.parameterAsBool(parameters, self.LOAD_LAYERS, context)

        if not output_file:
            raise QgsProcessingException("Lütfen geçerli bir çıktı GeoPackage dosya yolu belirleyin!")

        if not crs or not crs.isValid():
            crs = QgsCoordinateReferenceSystem("EPSG:5253")

        schema_type = SCHEMA_YEREL_NIP if schema_idx == 1 else SCHEMA_MPYY_117
        schema_name = "Yerel / Klasik NİP (1/5000)" if schema_idx == 1 else "Resmî MPYY 1.1.7 XSD"

        feedback.pushInfo(f"NİP Çizim Veritabanı üretiliyor: {output_file}")
        feedback.pushInfo(f"Şablon Türü: {schema_name} | KRS: {crs.authid()}...")

        try:
            created_path = create_nip_workspace(output_file, crs=crs, schema_type=schema_type)
            feedback.pushInfo("Veritabanı, lookup tabloları ve stiller başarıyla yazıldı.")
        except Exception as e:
            raise QgsProcessingException(f"Veritabanı oluşturulurken hata oluştu: {str(e)}")

        if load_layers and context.project():
            feedback.pushInfo("Katmanlar ve nitelik ilişkileri QGIS projesine yükleniyor...")
            load_nip_layers(created_path, project=context.project(), schema_type=schema_type)

        return {
            self.RESULT_PATH: created_path
        }

    def createInstance(self):
        return NipWorkspaceAlgorithm()
