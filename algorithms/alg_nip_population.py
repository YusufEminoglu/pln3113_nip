# -*- coding: utf-8 -*-
"""2. Tire NİP Nüfus, Donatı, Kamu-Özel, DOP ve Ulaşım Analizi Processing Algoritması.

DEÜ Mimarlık Fakültesi Şehir ve Bölge Planlama Bölümü
PLN3113 - Tire NİP Analiz Stüdyosu
"""
from __future__ import annotations

from qgis.core import (
    NULL,
    QgsCoordinateReferenceSystem,
    QgsDistanceArea,
    QgsFeature,
    QgsFeatureSink,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterField,
    QgsProcessingParameterNumber,
    QgsProcessingParameterVectorLayer,
    QgsWkbTypes
)
from qgis.PyQt.QtCore import QVariant

from ..core.nip_calculator import NipCalculatorEngine

class NipPopulationAlgorithm(QgsProcessingAlgorithm):
    INPUT = 'INPUT'
    ANALYSIS_MODE = 'ANALYSIS_MODE'
    FONKSIYON_FIELD = 'FONKSIYON_FIELD'
    SECONDARY_FONKSIYON_FIELD = 'SECONDARY_FONKSIYON_FIELD'
    SINIR_LAYER = 'SINIR_LAYER'
    SINIR_MODU = 'SINIR_MODU'
    YOL_LAYER = 'YOL_LAYER'
    PROJ_NUFUS = 'PROJ_NUFUS'
    OUTPUT_LAYER = 'OUTPUT_LAYER'
    OUTPUT_EK2 = 'OUTPUT_EK2'
    OUTPUT_DOP = 'OUTPUT_DOP'
    OUTPUT_KENT_KARAKTER = 'OUTPUT_KENT_KARAKTER'
    OUTPUT_FONKSIYON_DAGILIM = 'OUTPUT_FONKSIYON_DAGILIM'
    OUTPUT_KIYAS = 'OUTPUT_KIYAS'

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.INPUT,
                'Nazım İmar Planı veya Fiziki Mevcut Durum Katmanı',
                [QgsProcessing.SourceType.TypeVectorPolygon]
            )
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                self.ANALYSIS_MODE,
                'Analiz Modu / Kapsam',
                options=['Nazım İmar Planı (NİP - Öneri / Revizyon)', 'Fiziki Mevcut Durum (TUCBS / Arazi Kullanımı)'],
                defaultValue=0
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.FONKSIYON_FIELD,
                'Birincil Fonksiyon / TUCBS Sütunu (Örn: Ort__Detay, Ort_Detay veya tucbs_sinifi)',
                parentLayerParameterName=self.INPUT,
                type=QgsProcessingParameterField.DataType.String
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.SECONDARY_FONKSIYON_FIELD,
                'Tamamlayıcı / İkincil Fonksiyon Sütunu (Opsiyonel - örn: arazi_kullanim_tanimi)',
                parentLayerParameterName=self.INPUT,
                type=QgsProcessingParameterField.DataType.String,
                optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.SINIR_LAYER,
                'Plan Onama Sınırı Katmanı (Opsiyonel - Geometrik Yol ve Kesin DOP Hesabı)',
                [QgsProcessing.SourceType.TypeVectorPolygon],
                optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                self.SINIR_MODU,
                'Plan Sınırıyla Kesişen Poligonların İşleme Alınma Yöntemi (Sınır Dışındakiler Otomatik Elenir)',
                options=[
                    'Sınırla Kırp / Kes (Clip - Sınır dışında kalan parça atılır, net iç alan hesaplanır)',
                    'Sınıra Değenleri Dahil Et (Intersect - Sınırı kesen poligonun tamamı korunur)',
                    'Sınırı Aşanları Hariç Tut (Within - Sınırı taşan ada tamamen elenir)',
                    'Ağırlık Merkezine Göre (Centroid - Merkez noktası sınır içindeyse dahil edilir)'
                ],
                defaultValue=0
            )
        )
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.YOL_LAYER,
                'Ulaşım / Yol Aksları Katmanı (Opsiyonel - Ortalama Yol Genişliği Analizi)',
                [QgsProcessing.SourceType.TypeVectorLine],
                optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.PROJ_NUFUS,
                'Hedef Yılı Projeksiyon Nüfusu (Kişi)',
                QgsProcessingParameterNumber.Type.Integer,
                defaultValue=65000,
                minValue=1000
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_LAYER,
                'NİP Nüfus, Donatı ve Ulaşım Analiz Katmanı (Vektör)',
                QgsProcessing.SourceType.TypeVectorPolygon
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_DOP,
                'KÖ - DOP ve Kamu-Özel Dengesi Hesap Özeti',
                QgsProcessing.SourceType.TypeVector,
                optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_KENT_KARAKTER,
                'Kent Karakter Tablosu (Kişi Başı m² Metrikleri)',
                QgsProcessing.SourceType.TypeVector,
                optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_FONKSIYON_DAGILIM,
                'KÖ - Detaylı Fonksiyon ve Alan Dağılım Tablosu',
                QgsProcessing.SourceType.TypeVector,
                optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_EK2,
                'MPYY Ek-2 Donatı Yeterlilik Tablosu',
                QgsProcessing.SourceType.TypeVector,
                optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_KIYAS,
                'Tire Tarihsel Nüfus Kıyaslama Tablosu',
                QgsProcessing.SourceType.TypeVector,
                optional=True
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        layer = self.parameterAsVectorLayer(parameters, self.INPUT, context)
        mode_idx = self.parameterAsEnum(parameters, self.ANALYSIS_MODE, context)
        fonk_col = self.parameterAsString(parameters, self.FONKSIYON_FIELD, context)
        sec_col = self.parameterAsString(parameters, self.SECONDARY_FONKSIYON_FIELD, context)
        proj_nufus = self.parameterAsInt(parameters, self.PROJ_NUFUS, context)
        sinir_layer = self.parameterAsVectorLayer(parameters, self.SINIR_LAYER, context)
        sinir_modu_idx = self.parameterAsEnum(parameters, self.SINIR_MODU, context)
        sinir_modu_map = {0: "clip", 1: "intersect", 2: "within", 3: "centroid"}
        sinir_modu = sinir_modu_map.get(sinir_modu_idx, "clip")
        yol_layer = self.parameterAsVectorLayer(parameters, self.YOL_LAYER, context)

        if not layer:
            raise QgsProcessingException("Girdi katmanı bulunamadı!")

        analysis_mode = "TUCBS" if mode_idx == 1 else "NIP"
        secondary_fonk_col = sec_col.strip() if sec_col and sec_col.strip() else None

        da = QgsDistanceArea()
        da.setSourceCrs(layer.sourceCrs(), context.transformContext())
        if context.project():
            da.setEllipsoid(context.project().ellipsoid())
        else:
            da.setEllipsoid('WGS84')

        sinir_geom = None
        if sinir_layer:
            geoms = [f.geometry() for f in sinir_layer.getFeatures() if f.geometry() and not f.geometry().isEmpty()]
            if geoms:
                sinir_geom = QgsGeometry.unaryUnion(geoms)

        yol_uzunlugu_m = 0.0
        if yol_layer:
            for yf in yol_layer.getFeatures():
                yg = yf.geometry()
                if yg and not yg.isEmpty():
                    yol_uzunlugu_m += da.measureLength(yg)

        feedback.pushInfo(f"Analiz Başlatılıyor ({analysis_mode}): Sütun={fonk_col}, İkincil={secondary_fonk_col}...")

        feats = list(layer.getFeatures())
        parsed_items, summary = NipCalculatorEngine.calculate(
            feats, layer.fields(), fonk_col, proj_nufus, da,
            sinir_geom=sinir_geom,
            sinir_modu=sinir_modu,
            yol_uzunlugu_m=yol_uzunlugu_m,
            secondary_fonk_col=secondary_fonk_col,
            analysis_mode=analysis_mode
        )

        dop = summary["dop_ozet"]
        s_stats = summary.get("sinir_filtre_ozet")
        if s_stats and s_stats.get("aktif"):
            feedback.pushInfo(
                f"Plan Sınırı Filtresi ({s_stats['mod']}): Girdi={s_stats['toplam_girdi_ada']}, "
                f"İçte={s_stats['tamamen_icinde']}, Kesişen={s_stats['kesisen_islenen']}, "
                f"Sınır Dışı Elenen={s_stats['sinir_disi_elenen']}"
            )
        feedback.pushInfo(f"Hesaplanan Toplam Alt Nüfus: {summary['toplam_alt_nufus']:,} Kişi")
        feedback.pushInfo(f"Hesaplanan Toplam Üst Nüfus: {summary['toplam_ust_nufus']:,} Kişi")
        feedback.pushInfo(f"Düzenleme Sahası (DOP Esas Alan): {dop['dop_esas_alan_m2']:,.2f} m²")
        feedback.pushInfo(f"Hesaplanan DOP Oranı: %{dop['dop_orani']} ({dop['dop_uygunluk']})")

        # 1. Çıktı Katmanı Oluştur
        out_fields = QgsFields(layer.fields())
        out_fields.append(QgsField('AlanHa', QVariant.Double))
        out_fields.append(QgsField('ALT_SNR', QVariant.Double))
        out_fields.append(QgsField('UST_SNR', QVariant.Double))
        out_fields.append(QgsField('ALT_NUFUS', QVariant.Double))
        out_fields.append(QgsField('UST_NUFUS', QVariant.Double))
        out_fields.append(QgsField('k_m2_ALT_NUFUS', QVariant.Double))
        out_fields.append(QgsField('k_m2_UST_NUFUS', QVariant.Double))
        out_fields.append(QgsField('T_ISTIHDAM', QVariant.Int))
        out_fields.append(QgsField('GUNLUK_ARAC', QVariant.Double))
        out_fields.append(QgsField('GUNLUK_YAYA', QVariant.Double))
        out_fields.append(QgsField('DOP_DURUMU', QVariant.String))
        out_fields.append(QgsField('DOP_TURU', QVariant.String))
        out_fields.append(QgsField('DONATI_KATEGORI', QVariant.String))

        (sink_layer, dest_layer_id) = self.parameterAsSink(
            parameters,
            self.OUTPUT_LAYER,
            context,
            out_fields,
            QgsWkbTypes.Type.MultiPolygon,
            layer.sourceCrs()
        )

        for it in parsed_items:
            feat = it["feat"]
            new_f = QgsFeature(out_fields)
            new_f.setGeometry(it["geom"])
            attrs = feat.attributes()
            attrs.extend([
                round(it["alan_ha"], 4),
                it["alt_snr"] if it["alt_snr"] is not None else 0.0,
                it["ust_snr"] if it["ust_snr"] is not None else 0.0,
                it["alt_nufus"],
                it["ust_nufus"],
                it["km2_alt_nufus"] if it["km2_alt_nufus"] is not None else NULL,
                it["km2_ust_nufus"] if it["km2_ust_nufus"] is not None else NULL,
                it["istihdam"],
                it["gunluk_arac"],
                it["gunluk_yaya"],
                it["dop_durumu"],
                it["dop_turu"],
                it["donati_kategori"] or ""
            ])
            new_f.setAttributes(attrs)
            sink_layer.addFeature(new_f, QgsFeatureSink.Flag.FastInsert)

        # 2. DOP ve Kamu-Özel Hesap Özeti Tablosu
        dop_fields = QgsFields()
        dop_fields.append(QgsField('parametre', QVariant.String))
        dop_fields.append(QgsField('deger_m2', QVariant.Double))
        dop_fields.append(QgsField('deger_ha', QVariant.Double))
        dop_fields.append(QgsField('oran_yuzde', QVariant.Double))
        dop_fields.append(QgsField('aciklama', QVariant.String))

        dest_dop_id = None
        if self.OUTPUT_DOP in parameters and parameters[self.OUTPUT_DOP] is not None:
            (sink_dop, dest_dop_id) = self.parameterAsSink(
                parameters, self.OUTPUT_DOP, context, dop_fields, QgsWkbTypes.Type.NoGeometry, QgsCoordinateReferenceSystem()
            )
            if sink_dop:
                p_m2 = dop["toplam_plan_alani_m2"]
                e_m2 = dop["dop_esas_alan_m2"]
                sinir_aciklama = "Plan Onama Sınırına Göre Kesin" if dop.get("sinir_katmani_kullanildi") else "İmar Adaları Toplamı Esas Alındı"

                rows_dop = [
                    ("Plan Onama Sınırı / Toplam Alan", p_m2, dop["toplam_plan_alani_ha"], 100.0, sinir_aciklama),
                    ("İmar Adaları (Kullanım Poligonları)", dop["adalar_toplam_m2"], dop["adalar_toplam_ha"], round(dop["adalar_toplam_m2"]/max(1, p_m2)*100.0, 2), "Plan Fonksiyon Blokları"),
                    ("Net Yol ve Ulaşım Ağı Alanı", dop["hesaplanan_yol_m2"], dop["hesaplanan_yol_ha"], dop["yol_orani_yuzde"], "Plan Sınırı - İmar Adaları Boşluğu"),
                    ("DOP Dışı Alanlar (Harice Ayrılan)", dop["dop_disi_alan_m2"], round(dop["dop_disi_alan_m2"]/10000.0, 2), round(dop["dop_disi_alan_m2"]/max(1, p_m2)*100.0, 2), "Orman, Tarım, Su, Sit vb."),
                    ("Düzenleme Sahası (DOP Esas Alan)", e_m2, round(e_m2/10000.0, 2), round(e_m2/max(1, p_m2)*100.0, 2), "Düzenlemeye Giren Net Saha"),
                    ("Toplam Özel Mülkiyet (Tahsis)", dop["toplam_ozel_tahsis_m2"], round(dop["toplam_ozel_tahsis_m2"]/10000.0, 2), round(dop["toplam_ozel_tahsis_m2"]/max(1, e_m2)*100.0, 2), "Konut, Ticaret, Sanayi vb."),
                    ("Kamu Poligon Donatıları", dop["kamu_poligonlar_m2"], round(dop["kamu_poligonlar_m2"]/10000.0, 2), round(dop["kamu_poligonlar_m2"]/max(1, e_m2)*100.0, 2), "Eğitim, Sağlık, Yeşil vb."),
                    ("Toplam Kamu Alanı (Kesinti + Yol)", dop["toplam_kamu_kesinti_m2"], round(dop["toplam_kamu_kesinti_m2"]/10000.0, 2), dop["dop_orani"], "Donatılar + Hesaplanan Yol"),
                    ("Kamu / Özel Mülkiyet Oranı", 0.0, 0.0, dop["kamu_ozel_orani"], "Kamu Kesintisi / Özel Tahsis Oranı"),
                    ("HESAPLANAN DOP ORANI (%)", 0.0, 0.0, dop["dop_orani"], dop["dop_uygunluk"])
                ]
                if dop.get("ortalama_yol_genisligi_m"):
                    rows_dop.insert(3, ("Ortalama Fiili Yol Genişliği (m)", 0.0, 0.0, dop["ortalama_yol_genisligi_m"], f"{dop['yol_agi_uzunlugu_km']} km Yol Ağı / Yol Alanı"))
                for p, m2, ha, pct, desc in rows_dop:
                    df = QgsFeature(dop_fields)
                    df.setAttributes([p, m2, ha, pct, desc])
                    sink_dop.addFeature(df, QgsFeatureSink.Flag.FastInsert)

        # 3. Kent Karakter Tablosu
        kk_fields = QgsFields()
        kk_fields.append(QgsField('nip_fonksiyon', QVariant.String))
        kk_fields.append(QgsField('toplam_m2', QVariant.Double))
        kk_fields.append(QgsField('alt_nufus_m2_kisi', QVariant.Double))
        kk_fields.append(QgsField('ust_nufus_m2_kisi', QVariant.Double))
        kk_fields.append(QgsField('proj_nufus_m2_kisi', QVariant.Double))

        dest_kk_id = None
        if self.OUTPUT_KENT_KARAKTER in parameters and parameters[self.OUTPUT_KENT_KARAKTER] is not None:
            (sink_kk, dest_kk_id) = self.parameterAsSink(
                parameters, self.OUTPUT_KENT_KARAKTER, context, kk_fields, QgsWkbTypes.Type.NoGeometry, QgsCoordinateReferenceSystem()
            )
            if sink_kk:
                for kk in summary["kent_karakter"]:
                    kf = QgsFeature(kk_fields)
                    kf.setAttributes([kk["fonksiyon"], kk["toplam_m2"], kk["alt_nufus_m2_kisi"], kk["ust_nufus_m2_kisi"], kk["proj_nufus_m2_kisi"]])
                    sink_kk.addFeature(kf, QgsFeatureSink.Flag.FastInsert)

        # 4. Detaylı Fonksiyon Dağılım Tablosu
        fd_fields = QgsFields()
        fd_fields.append(QgsField('nip_fonksiyon', QVariant.String))
        fd_fields.append(QgsField('dop_durumu', QVariant.String))
        fd_fields.append(QgsField('alan_turu', QVariant.String))
        fd_fields.append(QgsField('adet', QVariant.Int))
        fd_fields.append(QgsField('alan_m2', QVariant.Double))
        fd_fields.append(QgsField('alan_ha', QVariant.Double))
        fd_fields.append(QgsField('kisi_basi_m2', QVariant.Double))
        fd_fields.append(QgsField('tum_plan_yuzdesi', QVariant.Double))
        fd_fields.append(QgsField('dop_ici_yuzde', QVariant.Double))

        dest_fd_id = None
        if self.OUTPUT_FONKSIYON_DAGILIM in parameters and parameters[self.OUTPUT_FONKSIYON_DAGILIM] is not None:
            (sink_fd, dest_fd_id) = self.parameterAsSink(
                parameters, self.OUTPUT_FONKSIYON_DAGILIM, context, fd_fields, QgsWkbTypes.Type.NoGeometry, QgsCoordinateReferenceSystem()
            )
            if sink_fd:
                for fd in summary["fonksiyon_dagilim"]:
                    ff = QgsFeature(fd_fields)
                    ff.setAttributes([
                        fd["fonksiyon"], fd["dop_durumu"], fd["dop_turu"], fd["adet"],
                        fd["alan_m2"], fd["alan_ha"], fd["kisi_basi_m2"], fd["tum_plan_yuzdesi"], fd["dop_ici_yuzde"]
                    ])
                    sink_fd.addFeature(ff, QgsFeatureSink.Flag.FastInsert)

        # 5. MPYY Ek-2 Tablosu
        ek2_fields = QgsFields()
        ek2_fields.append(QgsField('donati_turu', QVariant.String))
        ek2_fields.append(QgsField('toplam_m2', QVariant.Double))
        ek2_fields.append(QgsField('mpyy_standart_m2', QVariant.Double))
        ek2_fields.append(QgsField('mevcut_m2_alt_nufus', QVariant.Double))
        ek2_fields.append(QgsField('mevcut_m2_ust_nufus', QVariant.Double))
        ek2_fields.append(QgsField('mevcut_m2_projeksiyon', QVariant.Double))
        ek2_fields.append(QgsField('durum_alt_nufus', QVariant.String))
        ek2_fields.append(QgsField('durum_ust_nufus', QVariant.String))
        ek2_fields.append(QgsField('durum_projeksiyon', QVariant.String))

        dest_ek2_id = None
        if self.OUTPUT_EK2 in parameters and parameters[self.OUTPUT_EK2] is not None:
            (sink_ek2, dest_ek2_id) = self.parameterAsSink(
                parameters, self.OUTPUT_EK2, context, ek2_fields, QgsWkbTypes.Type.NoGeometry, QgsCoordinateReferenceSystem()
            )
            if sink_ek2:
                for ek in summary["ek2_rapor"]:
                    ef = QgsFeature(ek2_fields)
                    ef.setAttributes([
                        ek["kategori_adi"], ek["toplam_m2"], ek["standart_m2"],
                        ek["kb_alt"], ek["kb_ust"], ek["kb_proj"],
                        ek["durum_alt"], ek["durum_ust"], ek["durum_proj"]
                    ])
                    sink_ek2.addFeature(ef, QgsFeatureSink.Flag.FastInsert)

        # 6. Kıyaslama Tablosu
        kiyas_fields = QgsFields()
        kiyas_fields.append(QgsField('kapsam', QVariant.String))
        kiyas_fields.append(QgsField('kentsel_merkez', QVariant.String))
        kiyas_fields.append(QgsField('ilce_geneli', QVariant.String))
        kiyas_fields.append(QgsField('kaynak', QVariant.String))

        dest_kiyas_id = None
        if self.OUTPUT_KIYAS in parameters and parameters[self.OUTPUT_KIYAS] is not None:
            (sink_kiyas, dest_kiyas_id) = self.parameterAsSink(
                parameters, self.OUTPUT_KIYAS, context, kiyas_fields, QgsWkbTypes.Type.NoGeometry, QgsCoordinateReferenceSystem()
            )
            if sink_kiyas:
                for row in summary["kiyaslama"]:
                    kf = QgsFeature(kiyas_fields)
                    kf.setAttributes([str(row["kapsam"]), str(row["merkez"]), str(row["ilce"]), str(row["kaynak"])])
                    sink_kiyas.addFeature(kf, QgsFeatureSink.Flag.FastInsert)

        return {
            self.OUTPUT_LAYER: dest_layer_id,
            self.OUTPUT_DOP: dest_dop_id,
            self.OUTPUT_KENT_KARAKTER: dest_kk_id,
            self.OUTPUT_FONKSIYON_DAGILIM: dest_fd_id,
            self.OUTPUT_EK2: dest_ek2_id,
            self.OUTPUT_KIYAS: dest_kiyas_id
        }

    def name(self):
        return 'tire_nip_nufus_hesapla'

    def displayName(self):
        return '2. PLN3113 NİP Nüfus, Donatı, Kamu-Özel ve DOP Analizi'

    def group(self):
        return 'PLN3113 NİP ve Kentsel Analiz Araçları'

    def groupId(self):
        return 'pln3113_nip_tools'

    def createInstance(self):
        return NipPopulationAlgorithm()
