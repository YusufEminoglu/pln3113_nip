# -*- coding: utf-8 -*-
"""PLN3113 NİP - A/B Senaryosu: Mevcut ve Meri Plan Karşılaştırma Analizi.

Her iki yol ağında Space Syntax ve erişim analizleri çalıştırılır;
Delta NACH, Delta NAIN, pedshed verimlilik artışı ve donatı açığı kapanma fark haritası üretilir.
Dört plan karar başlığı (Kademelenme revizyonu, Yayalaştırma, Yeni donatı seçimi, Topolojik bağlantı)
otomatik olarak sınıflandırılır.
"""
from __future__ import annotations

import numpy as np

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsFeatureSink,
    QgsGeometry,
    QgsPointXY,
    QgsProcessing,
    QgsProcessingException,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterNumber,
    QgsSpatialIndex,
    QgsWkbTypes,
)

from ..core.planx_engine import graphs, paths, syntax
from ..core.planx_engine.planx_base import (
    CANCELLED_MESSAGE,
    DOUBLE,
    GROUP_REPORT,
    STRING,
    PlanXBaseAlgorithm,
    check_cancel,
    layer_units_per_metre,
)

# --------------------------------------------------------------------------- #
# Karar eşikleri - PlanX 4.23.0 ölçeği için yeniden türetildi (1.2.0).
#
# 1.1.6 eşikleri (dNACH 0.08, dNAIN 0.05, yeni yol NACH < 0.6 ve NAIN < 0.4)
# eski motora göre ayarlanmıştı: NAIN = (NC + 2)^1.2 / (TD + 2) ve yönsüz
# seçim. 4.23.0'da NAIN = NC^1.2 / (TD + 2) ve seçim yönlü segment uçları
# üzerinde, bu yüzden her değer kaydı.
#
# Yöntem (aynı yüzdelik): üç deterministik referans A/B çifti - (1) PlanX
# Generate Demo City düzeni, 10x10 x 100 m ızgara, A çaprazsız / B çapraz
# bulvarlı; (2) 9x6 x 120 m ızgarada çıkmaz sokakların geçişe açılması;
# (3) 8x8 x 90 m ızgarada merkezde dört aksın yayalaştırılması - eski motor
# (1.1.6, git HEAD) ve yeni motorla aracın varsayılan yarıçapı R = 800 m'de
# çözüldü; B segmentleri A'ya bu aracın kendi kuralıyla (orta nokta <= 20 m)
# eşlendi (529 eşleşen çift, 565 B segmenti). Her eski eşiğin eski dağılımdaki
# yüzdeliği bulundu ve yeni dağılımda aynı yüzdelikteki değer alındı:
#   |dNACH| 0.08 -> yüzdelik 0.777 -> 0.077
#   |dNAIN| 0.05 -> yüzdelik 0.382 -> 0.047
#   NACH_B  0.6  -> yüzdelik 0.005 -> 0.734 (tüm B segmentleri üzerinde)
# NAIN_B 0.4 eski dağılımın en küçük değerinin (1.137) altında kalıyor
# (yüzdelik 0), aynı yüzdelik tanımsız. Bunun yerine iki ölçek arasındaki
# kesin segment ilişkisi kullanıldı: NAIN_yeni = NAIN_eski * (NC/(NC+2))^1.2,
# eşiğe en yakın referans segmentin (en küçük eski NAIN, NC = 104)
# NC'sinde: 0.4 * 0.9774 = 0.391.
# Referans çiftleri ve aynı türetme tests/test_engine_values.py'de yeniden
# kurulur; eşikler orada denetlenir.
# --------------------------------------------------------------------------- #
#: Eşleşen aksta "yük artışı" / "sakinleşme" için NACH farkı eşiği.
DELTA_NACH_THRESHOLD = 0.077
#: Eşleşen aksta "yük artışı" / "sakinleşme" için NAIN farkı eşiği.
DELTA_NAIN_THRESHOLD = 0.047
#: Yeni öneri yol "işlemeyen" sayılır: NACH bunun altında ...
NEW_ROAD_NACH_THRESHOLD = 0.734
#: ... ve NAIN bunun altında.
NEW_ROAD_NAIN_THRESHOLD = 0.391
#: Eşleştirme toleransı ve donatı erişim eşiği (ikisi de yer metresi).
SNAP_TOLERANCE_M = 20.0
COVERAGE_CUTOFF_M = 800.0

DECISION_UPGRADE = "Ulaşım Kademelenmesi Revizyonu"
DECISION_CALM = "Yayalaştırma / Trafik Sakinleştirme"


def classify_matched(d_nach, d_nain):
    """Eşleşen bir aksın (durum, plan kararı) sınıfı."""
    if d_nach > DELTA_NACH_THRESHOLD or d_nain > DELTA_NAIN_THRESHOLD:
        return "Mevcut Aks: Yük Artışı (Kritik Arter)", DECISION_UPGRADE
    if d_nach < -DELTA_NACH_THRESHOLD or d_nain < -DELTA_NAIN_THRESHOLD:
        return "Mevcut Aks: Sakinleşen Trafik", DECISION_CALM
    return "Mevcut Aks: Kararlı / Değişmeyen", "Mevcut Karakter Korunacak"


def classify_new_road(nach_b, nain_b):
    """Eşleşmeyen (yeni) bir B aksının plan kararı."""
    if nach_b < NEW_ROAD_NACH_THRESHOLD and nain_b < NEW_ROAD_NAIN_THRESHOLD:
        return "İşlemeyen Öneri Yol (Kademelenme Revizyonu)"
    return "Stratejik Yeni Bağlantı Aksı"


class ScenarioCompareAlgorithm(PlanXBaseAlgorithm):
    GROUP = GROUP_REPORT
    NETWORK_A = "NETWORK_A"
    NETWORK_B = "NETWORK_B"
    RADIUS = "RADIUS"
    FACILITIES = "FACILITIES"
    DEMAND = "DEMAND"
    POP_FIELD = "POP_FIELD"
    DIFF_NETWORK = "DIFF_NETWORK"
    SUMMARY_TABLE = "SUMMARY_TABLE"

    def name(self):
        return "nip_scenario_compare"

    def displayName(self):
        return self.tr("6. A/B Senaryo Karşılaştırması (Mevcut vs Meri Plan Fark Haritası)")

    def shortHelpString(self):
        return self.tr(
            "Mevcut ve Meri Plan Senaryo Karşılaştırması (A/B Analizi):\n\n"
            "Mevcut yol ağı (A) ile Meri / Öneri plan yol ağı (B) üzerinde Space Syntax ve "
            "erişim analizlerini eşzamanlı çalıştırır.\n\n"
            "Fark Haritası ve Metrikler:\n"
            "- Delta NACH = Meri NACH - Mevcut NACH (Geçiş ve arter yük değişimi)\n"
            "- Delta NAIN = Meri NAIN - Mevcut NAIN (Varış/erişilebilirlik potansiyeli değişimi)\n"
            "- Dört Plan Karar Başlığı:\n"
            "  1. Ulaşım kademelenmesi revizyonu: İşlemeyen öneri yollar ile aşırı yük altındaki arterler\n"
            "  2. Yayalaştırma ve trafik sakinleştirme: Arasta/MİA çevresindeki sakinleşen veya yayalaştırılacak akslar\n"
            "  3. Yeni donatı yeri seçimi: Yüksek Delta NAIN odaklarına donatı önceliklendirmesi\n"
            "  4. Topolojik ve fiziksel bağlantılar: Kritik darboğazlar ve köprü/altgeçit önerileri\n\n"
            "Eşikler (PlanX 4.23.0 ölçeği; R = 800 m referans ağlarında aynı yüzdelikle türetildi): "
            f"|dNACH| > {DELTA_NACH_THRESHOLD}, |dNAIN| > {DELTA_NAIN_THRESHOLD}; yeni yol işlemiyor: "
            f"NACH < {NEW_ROAD_NACH_THRESHOLD} ve NAIN < {NEW_ROAD_NAIN_THRESHOLD}. "
            "1.1.6 sonuçlarıyla karşılaştırılamaz. Yarıçap yer metresidir. İptal edilen koşu çıktı yazmaz."
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.NETWORK_A, self.tr("Senaryo A: Mevcut Yol Ağı (Lines)"), [QgsProcessing.SourceType.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.NETWORK_B, self.tr("Senaryo B: Meri / Öneri Plan Yol Ağı (Lines)"), [QgsProcessing.SourceType.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterNumber(
            self.RADIUS, self.tr("Space Syntax Metrik Yarıçapı (metre)"),
            QgsProcessingParameterNumber.Type.Double, 800.0, minValue=100.0))
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.FACILITIES, self.tr("Donatı Noktaları (Opsiyonel - Pedshed/Erişim Kıyası İçin)"),
            [QgsProcessing.SourceType.TypeVectorAnyGeometry], optional=True))
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.DEMAND, self.tr("Talep / Ada Nüfus Merkezleri (Opsiyonel)"),
            [QgsProcessing.SourceType.TypeVectorAnyGeometry], optional=True))
        self.addParameter(QgsProcessingParameterField(
            self.POP_FIELD, self.tr("Talep Nüfus Alanı"),
            parentLayerParameterName=self.DEMAND, optional=True,
            type=QgsProcessingParameterField.DataType.Numeric))

        self.addParameter(QgsProcessingParameterFeatureSink(
            self.DIFF_NETWORK, self.tr("Ağ Fark Haritası (Delta NACH & NAIN Aksları)"),
            type=QgsProcessing.SourceType.TypeVectorLine))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.SUMMARY_TABLE, self.tr("A/B Senaryo Karşılaştırma Karnesi"),
            type=QgsProcessing.SourceType.TypeVector))

    def _run_syntax(self, network_source, radius, feedback, step_label, context=None):
        feedback.pushInfo(self.tr(f"{step_label}: Space Syntax grafı kuruluyor..."))
        polylines, line_feats = self.source_polylines(network_source)
        seg_graph = graphs.build_segment_graph(polylines)
        per_metre = layer_units_per_metre(
            network_source.sourceCrs(), network_source.sourceExtent(),
            context.transformContext() if context is not None else None)
        feedback.pushInfo(self.tr(f"{step_label}: {seg_graph.n} segment analiz ediliyor (R={radius:g} m)..."))
        res = syntax.segment_angular_analysis(
            seg_graph, radius=radius * per_metre, cancel=feedback.isCanceled)
        if res.get("cancelled"):
            # Yarım diziler asla sonuç olarak yazılmaz.
            raise QgsProcessingException(CANCELLED_MESSAGE)
        nach = res["nach"]
        nain = res["nain"]
        return seg_graph, polylines, line_feats, nach, nain

    def processAlgorithm(self, parameters, context, feedback):
        source_a = self.parameterAsSource(parameters, self.NETWORK_A, context)
        source_b = self.parameterAsSource(parameters, self.NETWORK_B, context)
        radius = self.parameterAsDouble(parameters, self.RADIUS, context)
        facilities = self.parameterAsSource(parameters, self.FACILITIES, context)
        demand = self.parameterAsSource(parameters, self.DEMAND, context)
        pop_field = self.parameterAsString(parameters, self.POP_FIELD, context)

        self.require_projected(source_a, "Senaryo A yol ağı")
        self.require_projected(source_b, "Senaryo B yol ağı")
        crs = source_b.sourceCrs()

        # Run Syntax on Network A
        if source_a.sourceCrs() != crs:
            raise QgsProcessingException(
                "Senaryo A ve B yol ağları aynı koordinat sisteminde olmalıdır "
                f"({source_a.sourceCrs().authid()} / {crs.authid()}); akslar orta noktalarıyla eşlenir.")
        _, polys_a, feats_a, nach_a, nain_a = self._run_syntax(
            source_a, radius, feedback, "Senaryo A (Mevcut)", context)
        check_cancel(feedback)

        # Run Syntax on Network B
        _, polys_b, feats_b, nach_b, nain_b = self._run_syntax(
            source_b, radius, feedback, "Senaryo B (Meri)", context)
        check_cancel(feedback)
        per_metre_b = layer_units_per_metre(crs, source_b.sourceExtent(), context.transformContext())

        # Spatial Index on Network A polylines (midpoints)
        sp_index_a = QgsSpatialIndex()
        midpoints_a = []
        for i, arr in enumerate(polys_a):
            mid_idx = len(arr) // 2
            pt = QgsPointXY(float(arr[mid_idx][0]), float(arr[mid_idx][1]))
            midpoints_a.append(pt)
            f = QgsFeature(i)
            f.setGeometry(QgsGeometry.fromPointXY(pt))
            sp_index_a.addFeature(f)

        diff_fields = self.make_fields(
            ("aks_id", STRING),
            ("senaryo_durum", STRING),
            ("plan_karar_grubu", STRING),
            ("delta_nach", DOUBLE),
            ("delta_nain", DOUBLE),
            ("nach_a", DOUBLE),
            ("nach_b", DOUBLE),
            ("nain_a", DOUBLE),
            ("nain_b", DOUBLE),
            ("uzunluk_m", DOUBLE),
        )
        diff_sink, diff_dest = self.parameterAsSink(
            parameters, self.DIFF_NETWORK, context, diff_fields,
            QgsWkbTypes.Type.LineString, crs)

        matched_a = set()
        snap_tol = SNAP_TOLERANCE_M * per_metre_b  # yer metresi -> katman birimi

        count_new = 0
        count_upgrade = 0
        count_calm = 0
        count_stable = 0

        for j, arr in enumerate(polys_b):
            check_cancel(feedback)
            mid_idx = len(arr) // 2
            pt_b = QgsPointXY(float(arr[mid_idx][0]), float(arr[mid_idx][1]))
            cand_a = sp_index_a.nearestNeighbor(pt_b, 1)

            val_nach_b = float(nach_b[j])
            val_nain_b = float(nain_b[j])
            length_b = float(np.sum(np.hypot(np.diff(arr[:, 0]), np.diff(arr[:, 1])))) / per_metre_b

            if cand_a and midpoints_a[cand_a[0]].distance(pt_b) <= snap_tol:
                idx_a = cand_a[0]
                matched_a.add(idx_a)
                val_nach_a = float(nach_a[idx_a])
                val_nain_a = float(nain_a[idx_a])
                d_nach = val_nach_b - val_nach_a
                d_nain = val_nain_b - val_nain_a

                status, decision = classify_matched(d_nach, d_nain)
                if decision == DECISION_UPGRADE:
                    count_upgrade += 1
                elif decision == DECISION_CALM:
                    count_calm += 1
                else:
                    count_stable += 1
            else:
                val_nach_a = 0.0
                val_nain_a = 0.0
                d_nach = val_nach_b
                d_nain = val_nain_b
                status = "Yeni Öneri Yol (Meri Plan Aksı)"
                decision = classify_new_road(val_nach_b, val_nain_b)
                count_new += 1

            feat = QgsFeature(diff_fields)
            feat.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(x, y) for x, y in arr]))
            feat.setAttributes([
                f"B_{j + 1}", status, decision,
                round(d_nach, 4), round(d_nain, 4),
                round(val_nach_a, 4), round(val_nach_b, 4),
                round(val_nain_a, 4), round(val_nain_b, 4),
                round(length_b, 1)
            ])
            diff_sink.addFeature(feat, QgsFeatureSink.Flag.FastInsert)

        # Edges in A that were cancelled or removed in B
        count_removed = 0
        for i, arr in enumerate(polys_a):
            if i not in matched_a:
                count_removed += 1
                length_a = float(np.sum(np.hypot(np.diff(arr[:, 0]), np.diff(arr[:, 1])))) / per_metre_b
                feat = QgsFeature(diff_fields)
                feat.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(x, y) for x, y in arr]))
                feat.setAttributes([
                    f"A_{i + 1}", "İptal Edilen / Değişen Aks", "Yayalaştırma / Yol Kapatma",
                    round(-float(nach_a[i]), 4), round(-float(nain_a[i]), 4),
                    round(float(nach_a[i]), 4), 0.0,
                    round(float(nain_a[i]), 4), 0.0,
                    round(length_a, 1)
                ])
                diff_sink.addFeature(feat, QgsFeatureSink.Flag.FastInsert)

        # Summary table
        sum_fields = self.make_fields(
            ("metrik", STRING),
            ("senaryo_a_mevcut", STRING),
            ("senaryo_b_meri", STRING),
            ("delta_fark", STRING),
            ("plan_yorumu", STRING),
        )
        sum_sink, sum_dest = self.parameterAsSink(
            parameters, self.SUMMARY_TABLE, context, sum_fields,
            QgsWkbTypes.Type.NoGeometry, QgsCoordinateReferenceSystem())

        mean_nach_a = float(np.mean(nach_a)) if len(nach_a) else 0.0
        mean_nach_b = float(np.mean(nach_b)) if len(nach_b) else 0.0
        mean_nain_a = float(np.mean(nain_a)) if len(nain_a) else 0.0
        mean_nain_b = float(np.mean(nain_b)) if len(nain_b) else 0.0

        rows = [
            ("Ortalama NACH (Geçiş Potansiyeli)", f"{mean_nach_a:.3f}", f"{mean_nach_b:.3f}",
             f"{mean_nach_b - mean_nach_a:+.3f}", "Kent bütününde transit hareket kapasitesi değişimi"),
            ("Ortalama NAIN (Varış Potansiyeli)", f"{mean_nain_a:.3f}", f"{mean_nain_b:.3f}",
             f"{mean_nain_b - mean_nain_a:+.3f}", "Yaya ve kentsel canlılık koridorlarının bütünleşmesi"),
            ("Yeni Öneri Yol Aks Sayısı", "0", str(count_new), f"+{count_new}",
             "Meri planda eklenen yeni arter ve bağlantılar"),
            ("Kademelenme Revizyonu Gerektiren Aks", "-", str(count_upgrade), str(count_upgrade),
             "Aşırı yüklenen arterlerde genişletme / profil revizyonu"),
            ("Trafik Sakinleştirme / Yayalaştırma", "-", str(count_calm), str(count_calm),
             "Tarihi çekirdek ve MİA çevresi öncelikli yaya koridorları"),
        ]

        # Optional facilities and demand check
        if facilities is not None and demand is not None:
            # Erişim eşiği metre cinsindendir: hazır maliyet sütunları (dakika
            # olabilir) değil uzunluk kullanılır.
            graph_a, _, _ = self.network_graph(source_a, use_prepared_costs=False)
            graph_b, _, _ = self.network_graph(source_b, use_prepared_costs=False)
            cutoff_u = COVERAGE_CUTOFF_M * per_metre_b
            d_xy, d_feats = self.source_points(demand, crs, context.transformContext())
            f_xy, _ = self.source_points(facilities, crs, context.transformContext())
            if len(d_xy) > 0 and len(f_xy) > 0:
                d_nodes_a = graphs.nearest_nodes(graph_a, d_xy)
                f_nodes_a = graphs.nearest_nodes(graph_a, f_xy)
                dist_a, _ = paths.multi_source(graph_a.indptr, graph_a.adj_node, graph_a.adj_cost,
                                               graph_a.num_nodes, f_nodes_a, cutoff=cutoff_u)
                cov_a = float(np.sum(np.isfinite(dist_a[d_nodes_a])))

                d_nodes_b = graphs.nearest_nodes(graph_b, d_xy)
                f_nodes_b = graphs.nearest_nodes(graph_b, f_xy)
                dist_b, _ = paths.multi_source(graph_b.indptr, graph_b.adj_node, graph_b.adj_cost,
                                               graph_b.num_nodes, f_nodes_b, cutoff=cutoff_u)
                cov_b = float(np.sum(np.isfinite(dist_b[d_nodes_b])))

                total_dem = len(d_xy)
                pct_a = (cov_a / total_dem) * 100.0
                pct_b = (cov_b / total_dem) * 100.0
                rows.append((
                    "Donatı Açığı Kapanma (800m)", f"%{pct_a:.1f}", f"%{pct_b:.1f}",
                    f"%{pct_b - pct_a:+.1f}",
                    "Yeni yol ağı sayesinde donatı erişilebilirliğindeki artış"
                ))

        check_cancel(feedback)
        for r in rows:
            feat = QgsFeature(sum_fields)
            feat.setAttributes(list(r))
            sum_sink.addFeature(feat, QgsFeatureSink.Flag.FastInsert)

        feedback.pushInfo(self.tr(
            f"A/B Senaryo Karşılaştırması Tamamlandı: {count_new} yeni öneri aks, "
            f"{count_upgrade} yük artışı aksı, {count_calm} sakinleşen aks tespit edildi."))

        return {
            self.DIFF_NETWORK: diff_dest,
            self.SUMMARY_TABLE: sum_dest,
        }

    def createInstance(self):
        return ScenarioCompareAlgorithm()
