# -*- coding: utf-8 -*-
"""Space Syntax: Segment Açısal Analizi (PlanX Motoru Entegrasyonu).

PLN3113 - Tire NİP Analiz Stüdyosu

Yarıçaplar R = 400, 800, 1200 m ve n (global).
Metrikler: NAIN (varış/erişilebilirlik potansiyeli) ve NACH (geçiş potansiyeli).
"""
from __future__ import annotations

from qgis.core import (
    QgsFeature,
    QgsFeatureSink,
    QgsGeometry,
    QgsPointXY,
    QgsProcessing,
    QgsProcessingException,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterString,
    QgsWkbTypes,
)

from ..core.planx_engine.planx_base import (
    CANCELLED_MESSAGE,
    DOUBLE,
    INT,
    PlanXBaseAlgorithm,
    check_cancel,
    layer_units_per_metre,
    parse_number_list,
)
from ..core.planx_engine import graphs, syntax

#: Bu segment sayısından itibaren global yarıçap uzun sürebilir (PlanX 4.23.0).
SLOW_GLOBAL_SEGMENTS = 5000


class SpaceSyntaxAlgorithm(PlanXBaseAlgorithm):
    NETWORK = "NETWORK"
    RADII = "RADII"
    OUTPUT = "OUTPUT"

    def name(self):
        return "nip_space_syntax"

    def displayName(self):
        return "1. Space Syntax (Açısal Segment Analizi - NAIN & NACH)"

    def shortHelpString(self):
        return (
            "Yol ağı üzerinde modern açısal segment analizi (Hillier & Iida 2005; Turner 2001). "
            "Gömülü PlanX motoru ile harici eklenti veya depthmapX gerekmeden doğrudan çalışır.\n\n"
            "Her dönüş açısı maliyetlendirilir (düz=0, dik açı=1); polilin eğrilikleri dahil edilir.\n"
            "Her yarıçap için hesaplanan temel metrikler:\n"
            "- NAIN: Normalleştirilmiş Entegrasyon (Varış / Hedef Potansiyeli). Yüksek NAIN merkezleri ve yaya canlılığını gösterir.\n"
            "- NACH: Normalleştirilmiş Seçim (Geçiş / Akış Potansiyeli). Yüksek NACH ana omurga/koridorları gösterir.\n"
            "- CH: Ham Seçim (Choice), TD: Toplam Derinlik, MD: Ortalama Derinlik, NC: Erişilen Segment Sayısı (kendisi dahil).\n\n"
            "PlanX 4.23.0 motoru: seçim yönlü segment uçları üzerinde hesaplanır (bir rota segmente bir uçtan "
            "girer, öbür uçtan çıkar; çıkmaz sokağın seçimi 0'dır). NAIN = NC^1.2 / (TD + 2), "
            "NACH = log10(CH + 1) / log10(TD + 3) (Hillier, Yang & Turner 2012). "
            "1.1.6 ve öncesindeki NAIN/NACH değerleriyle karşılaştırılamaz.\n\n"
            "Yarıçaplar yer metresidir ve katmanın birimine çevrilir (EPSG:3857 gibi ölçekli sistemlerde de doğru; "
            "feet birimli KRS reddedilir). '400, 800' yaya ölçeği; '1200' mahalle ölçeği; 'n' tüm kent ölçeğidir. "
            "İptal edilen koşu çıktı yazmaz."
        )

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.NETWORK,
                "Ulaşım / Yol Ağı Katmanı (Line)",
                [QgsProcessing.SourceType.TypeVectorLine]
            )
        )
        self.addParameter(
            QgsProcessingParameterString(
                self.RADII,
                "Analiz Yarıçapları (Metre, virgülle, 'n' = Global)",
                "400, 800, 1200, n"
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                "Space Syntax Segment Analiz Çıktısı (Lines)",
                QgsProcessing.SourceType.TypeVectorLine
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        network = self.parameterAsSource(parameters, self.NETWORK, context)
        if network is None:
            raise QgsProcessingException("Yol ağı katmanı verilmedi.")
        self.require_projected(network, "Yol ağı")
        radii = parse_number_list(
            self.parameterAsString(parameters, self.RADII, context),
            "Analiz yarıçapları", "400, 800, n", allow_global=True, unit_suffixes=("m",))
        # Yarıçaplar yer metresidir; segment grafı katmanın kendi biriminde ölçer.
        per_metre = 1.0
        if any(r is not None for r in radii):
            per_metre = layer_units_per_metre(
                network.sourceCrs(), network.sourceExtent(), context.transformContext())
        if abs(per_metre - 1.0) > 0.01:
            feedback.pushInfo(
                f"Katman birimi burada yer metresi değil: 1 m = {per_metre:.4g} katman birimi; "
                "yarıçaplar çevrildi.")

        polylines, line_feats = self.source_polylines(network)
        seg_graph = graphs.build_segment_graph(polylines)
        feedback.pushInfo(f"Segment grafı oluşturuldu: {seg_graph.n} segment.")
        if seg_graph.n > SLOW_GLOBAL_SEGMENTS and any(r is None for r in radii):
            feedback.pushWarning(
                f"{seg_graph.n} segmentte global yarıçap uzun sürebilir (20 000 segmentte "
                "yaklaşık 30 dakika). Yalnızca metrik yarıçapları kullanmayı ya da ağı "
                "çalışma alanı artı bir yarıçapla kırpmayı düşünün.")

        specs = [("connectivity", INT)]
        for r in radii:
            lab = syntax.radius_label(r)
            specs += [
                (f"NC_{lab}", DOUBLE), (f"TD_{lab}", DOUBLE),
                (f"MD_{lab}", DOUBLE), (f"NAIN_{lab}", DOUBLE),
                (f"CH_{lab}", DOUBLE), (f"NACH_{lab}", DOUBLE)
            ]
        fields = self.make_fields(*specs, base=network.fields())

        results = []
        for ri, r in enumerate(radii):
            check_cancel(feedback)
            feedback.pushInfo(f"Yarıçap R = {syntax.radius_label(r)} hesaplanıyor...")
            base_pct = 100.0 * ri / len(radii)
            span_pct = 100.0 / len(radii)
            res = syntax.segment_angular_analysis(
                seg_graph, radius=None if r is None else r * per_metre,
                cancel=feedback.isCanceled,
                progress=lambda p, b=base_pct, s=span_pct: feedback.setProgress(int(b + s * p))
            )
            if res.get("cancelled"):
                # Motor yarıda durdu: diziler yalnızca işlenen başlangıçları
                # kapsar ve asla sonuç olarak yazılmamalıdır.
                raise QgsProcessingException(CANCELLED_MESSAGE)
            results.append(res)
        check_cancel(feedback)

        sink, dest = self.parameterAsSink(
            parameters, self.OUTPUT, context, fields,
            QgsWkbTypes.Type.LineString, network.sourceCrs()
        )
        n_src = len(network.fields())
        for s in range(seg_graph.n):
            f = QgsFeature(fields)
            f.setGeometry(QgsGeometry.fromPolylineXY(
                [QgsPointXY(float(x), float(y)) for x, y in polylines[s]]
            ))
            attrs = list(line_feats[s].attributes())[:n_src]
            attrs.append(int(seg_graph.connectivity[s]))
            for res in results:
                attrs += [
                    float(res["nc"][s]), float(res["td"][s]),
                    float(res["md"][s]), float(res["nain"][s]),
                    float(res["choice"][s]), float(res["nach"][s])
                ]
            f.setAttributes(attrs)
            sink.addFeature(f, QgsFeatureSink.Flag.FastInsert)

        check_cancel(feedback)
        return {self.OUTPUT: dest}

    def createInstance(self):
        return SpaceSyntaxAlgorithm()
