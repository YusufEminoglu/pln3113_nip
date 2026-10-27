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
    DOUBLE,
    INT,
    PlanXBaseAlgorithm,
)
from ..core.planx_engine import graphs, syntax


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
            "- CH: Ham Seçim (Choice), TD: Toplam Derinlik, MD: Ortalama Derinlik, NC: Erişilen Düğüm Sayısı.\n\n"
            "Yarıçaplar metrik metre cinsindendir. '400, 800' yaya ölçeği; '1200' mahalle ölçeği; 'n' tüm kent ölçeğidir."
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
        self.require_projected(network, "Yol ağı")
        try:
            radii = syntax.parse_radii(self.parameterAsString(parameters, self.RADII, context))
        except ValueError as exc:
            raise QgsProcessingException(str(exc))

        polylines, line_feats = self.source_polylines(network)
        seg_graph = graphs.build_segment_graph(polylines)
        feedback.pushInfo(f"Segment grafı oluşturuldu: {seg_graph.n} segment.")

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
            if feedback.isCanceled():
                break
            feedback.pushInfo(f"Yarıçap R = {syntax.radius_label(r)} hesaplanıyor...")
            base_pct = 100.0 * ri / len(radii)
            span_pct = 100.0 / len(radii)
            res = syntax.segment_angular_analysis(
                seg_graph, radius=r,
                cancel=feedback.isCanceled,
                progress=lambda p, b=base_pct, s=span_pct: feedback.setProgress(int(b + s * p))
            )
            results.append(res)

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

        return {self.OUTPUT: dest}

    def createInstance(self):
        return SpaceSyntaxAlgorithm()
