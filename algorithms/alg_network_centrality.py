# -*- coding: utf-8 -*-
"""Primal Ağ Merkeziliği (Network Centrality - PlanX Motoru Entegrasyonu).

DEÜ Mimarlık Fakültesi Şehir ve Bölge Planlama Bölümü
PLN3113 - Tire NİP Analiz Stüdyosu

Yarıçaplar R = 800 m ve 5000 m (veya global).
Metrikler: Betweenness (Aradalık), Closeness (Yakınlık), Straightness (Doğrusallık), Derece.
"""
from __future__ import annotations

import numpy as np

from qgis.core import (
    QgsFeature,
    QgsFeatureSink,
    QgsGeometry,
    QgsPointXY,
    QgsProcessing,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterNumber,
    QgsWkbTypes,
)

from ..core.planx_engine.planx_base import (
    DOUBLE,
    INT,
    PlanXBaseAlgorithm,
)
from ..core.planx_engine import centrality, graphs


class NetworkCentralityAlgorithm(PlanXBaseAlgorithm):
    NETWORK = "NETWORK"
    COST_FIELD = "COST_FIELD"
    RADIUS = "RADIUS"
    SAMPLES = "SAMPLES"
    NODES = "NODES"
    EDGES = "EDGES"

    def name(self):
        return "nip_network_centrality"

    def displayName(self):
        return "2. Primal Ağ Merkeziliği (Betweenness, Closeness, Straightness)"

    def shortHelpString(self):
        return (
            "Ulaşım ağı üzerinde Multiple Centrality Assessment (Porta et al. 2006) metriklerini hesaplar:\n"
            "- Degree (Derece): Kavşağa bağlanan yol sayısı.\n"
            "- Closeness (Yakınlık): Ağdaki tüm noktalara olan ortalama erişim kolaylığı (Wasserman-Faust ve Harmonik).\n"
            "- Straightness (Doğrusallık): Ağ rotalarının kuş uçuşu düz çizgilere ne kadar yakın olduğu (Şebeke dolaysızlığı).\n"
            "- Betweenness (Aradalık): En kısa yolların kavşak ve sokaklardan geçme sıklığı (Brandes 2001).\n\n"
            "Yarıçap (Radius): Analizi yerel bir yürüme (örn: 800m) veya taşıt (örn: 5000m) havzası ile sınırlar. 0 = Global ağ ölçeği.\n"
            "Hem sokak aksları (Line) hem de kavşak noktaları (Point) üretilir."
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
            QgsProcessingParameterField(
                self.COST_FIELD,
                "Maliyet Alanı (Boş = Metrik Uzunluk)",
                parentLayerParameterName=self.NETWORK,
                optional=True,
                type=QgsProcessingParameterField.DataType.Numeric
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.RADIUS,
                "Analiz Yarıçapı Metre (Örn: 800, 5000; 0 = Global)",
                QgsProcessingParameterNumber.Type.Double,
                800.0,
                minValue=0.0
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.SAMPLES,
                "Betweenness Örneklem Kaynak Sayısı (0 = Tam / Kesin Hesap)",
                QgsProcessingParameterNumber.Type.Integer,
                0,
                minValue=0
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.EDGES,
                "Sokak Aksları Merkezilik Katmanı (Lines)",
                QgsProcessing.SourceType.TypeVectorLine,
                optional=False
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.NODES,
                "Kavşak Düğümleri Merkezilik Katmanı (Points)",
                QgsProcessing.SourceType.TypeVectorPoint,
                optional=True
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        network = self.parameterAsSource(parameters, self.NETWORK, context)
        cost_field = self.parameterAsString(parameters, self.COST_FIELD, context)
        radius = self.parameterAsDouble(parameters, self.RADIUS, context) or None
        samples = self.parameterAsInt(parameters, self.SAMPLES, context)
        self.require_projected(network, "Yol ağı")

        graph, polylines, line_feats = self.network_graph(network, cost_field)
        n = graph.num_nodes
        feedback.pushInfo(f"Graf inşa edildi: {n} düğüm / {graph.num_edges} kenar.")

        feedback.pushInfo("Closeness ve Straightness hesaplanıyor...")
        clo = centrality.closeness_straightness(
            graph.indptr, graph.adj_node, graph.adj_cost, n,
            node_xy=graph.node_xy, radius=radius,
            cancel=feedback.isCanceled,
            progress=lambda p: feedback.setProgress(int(45 * p))
        )

        feedback.pushInfo("Betweenness (Brandes) hesaplanıyor...")
        sources = None
        if samples > 0 and samples < n:
            sources = np.random.choice(n, size=samples, replace=False)

        node_bc, edge_bc, _ = centrality.brandes_betweenness(
            graph.indptr, graph.adj_node, graph.adj_cost, n,
            adj_edge=graph.adj_edge, num_edges=graph.num_edges,
            radius=radius, sources=sources,
            cancel=feedback.isCanceled,
            progress=lambda p: feedback.setProgress(int(45 + 50 * p))
        )

        feedback.pushInfo("Eigenvector merkeziliği hesaplanıyor...")
        eigen = centrality.eigenvector(graph.indptr, graph.adj_node, n)

        results = {}
        crs = network.sourceCrs()

        # 1. Sokak Aksları (Lines)
        if self.EDGES in parameters and parameters[self.EDGES]:
            edge_max = float(edge_bc.max()) if edge_bc is not None and len(edge_bc) > 0 and edge_bc.max() > 0 else 1.0
            edge_fields = self.make_fields(
                ("betweenness", DOUBLE),
                ("betw_norm", DOUBLE),
                ("clo_mean", DOUBLE),
                ("str_mean", DOUBLE),
                base=network.fields()
            )
            e_sink, e_dest = self.parameterAsSink(
                parameters, self.EDGES, context, edge_fields,
                QgsWkbTypes.Type.LineString, crs
            )
            n_src = len(network.fields())
            for e_idx in range(graph.num_edges):
                u, v = int(graph.edge_from[e_idx]), int(graph.edge_to[e_idx])
                ebc = float(edge_bc[e_idx]) if edge_bc is not None else 0.0
                c_mean = float((clo["closeness"][u] + clo["closeness"][v]) / 2.0)
                s_mean = float((clo["straightness"][u] + clo["straightness"][v]) / 2.0)
                feat = QgsFeature(edge_fields)
                feat.setGeometry(QgsGeometry.fromPolylineXY(
                    [QgsPointXY(float(x), float(y)) for x, y in polylines[e_idx]]
                ))
                attrs = list(line_feats[e_idx].attributes())[:n_src] + [
                    round(ebc, 4),
                    round(ebc / edge_max, 4),
                    round(c_mean, 6),
                    round(s_mean, 4)
                ]
                feat.setAttributes(attrs)
                e_sink.addFeature(feat, QgsFeatureSink.Flag.FastInsert)
            results[self.EDGES] = e_dest

        # 2. Kavşak Düğümleri (Points)
        if self.NODES in parameters and parameters[self.NODES]:
            node_max = float(node_bc.max()) if len(node_bc) > 0 and node_bc.max() > 0 else 1.0
            node_fields = self.make_fields(
                ("node_id", INT),
                ("degree", INT),
                ("reach", INT),
                ("closeness", DOUBLE),
                ("harm_clo", DOUBLE),
                ("straightness", DOUBLE),
                ("betweenness", DOUBLE),
                ("betw_norm", DOUBLE),
                ("eigenvector", DOUBLE)
            )
            n_sink, n_dest = self.parameterAsSink(
                parameters, self.NODES, context, node_fields,
                QgsWkbTypes.Type.Point, crs
            )
            degs = graph.degrees()
            for i in range(n):
                pt = graph.node_xy[i]
                feat = QgsFeature(node_fields)
                feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(float(pt[0]), float(pt[1]))))
                nbc = float(node_bc[i])
                feat.setAttributes([
                    int(i),
                    int(degs[i]),
                    int(clo["reach"][i]),
                    round(float(clo["closeness"][i]), 6),
                    round(float(clo["harmonic"][i]), 6),
                    round(float(clo["straightness"][i]), 4),
                    round(nbc, 4),
                    round(nbc / node_max, 4),
                    round(float(eigen[i]), 4)
                ])
                n_sink.addFeature(feat, QgsFeatureSink.Flag.FastInsert)
            results[self.NODES] = n_dest

        return results

    def createInstance(self):
        return NetworkCentralityAlgorithm()
