# -*- coding: utf-8 -*-
"""Menşe-Hedef (OD) Maliyet Matrisi, Rotalama ve Engel Analizi (PlanX Motoru Entegrasyonu).

DEÜ Mimarlık Fakültesi Şehir ve Bölge Planlama Bölümü
PLN3113 - Tire NİP Analiz Stüdyosu

Konut mahalleleri (orijin) ile MİA, sanayi ve hastane/otogar (destinasyon) ilişkisi.
Metrik: Detour Ratio (Ağ Mesafesi / Kuş Uçuşu). 1.35 üzeri akslarda engel (barrier) analizi.
"""
from __future__ import annotations

import math
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
    STRING,
)
from ..core.planx_engine import graphs, paths


class ODCostMatrixAlgorithm(PlanXBaseAlgorithm):
    NETWORK = "NETWORK"
    ORIGINS = "ORIGINS"
    ORIGIN_ID = "ORIGIN_ID"
    DESTINATIONS = "DESTINATIONS"
    DEST_ID = "DEST_ID"
    COST_FIELD = "COST_FIELD"
    CUTOFF = "CUTOFF"
    BARRIER_RATIO = "BARRIER_RATIO"
    OUTPUT_MATRIX = "OUTPUT_MATRIX"
    OUTPUT_DESIRE = "OUTPUT_DESIRE"
    OUTPUT_ROUTES = "OUTPUT_ROUTES"
    MATRIX = OUTPUT_MATRIX
    DESIRE_LINES = OUTPUT_DESIRE
    ROUTES = OUTPUT_ROUTES

    def name(self):
        return "nip_od_rotalama"

    def displayName(self):
        return "3. Menşe-Hedef (OD) Matrisi, Rotalama ve Engel Analizi"

    def shortHelpString(self):
        return (
            "Ulaşım ağı üzerinden Menşe (Orijin) ve Hedef (Destinasyon) çiftleri arasında tam "
            "ağ maliyet matrisi, kuş uçuşu arzu hatları ve en kısa ağ rotalarını üretir.\n\n"
            "PLN3113 Ödev 13 Standartları:\n"
            "- Orijin: Konut mahalleleri, ada ağırlık merkezleri veya nüfus yoğunluk odakları.\n"
            "- Destinasyon: MİA (Merkezi İş Alanı), Sanayi, Hastane, Terminal/Otogar odakları.\n"
            "- Detour Ratio (Sapma Oranı) = Ağ Mesafesi / Kuş Uçuşu Mesafe.\n"
            "- 1.35 üzeri detour oranına sahip akslar 'Kritik Engel / Barrier' olarak bayraklanır "
            "(Demiryolu, dere veya topoğrafik kopuklukların tespiti için kullanılır)."
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
            QgsProcessingParameterFeatureSource(
                self.ORIGINS,
                "Orijin Noktaları (Konut Mahalleleri / Ada Merkezleri)",
                [QgsProcessing.SourceType.TypeVectorAnyGeometry]
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.ORIGIN_ID,
                "Orijin Kimlik / Ad Alanı",
                parentLayerParameterName=self.ORIGINS,
                optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.DESTINATIONS,
                "Destinasyon Noktaları (MİA, Sanayi, Hastane, Otogar)",
                [QgsProcessing.SourceType.TypeVectorAnyGeometry],
                optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.DEST_ID,
                "Destinasyon Kimlik / Ad Alanı (Boş = Orijin Adı)",
                parentLayerParameterName=self.DESTINATIONS,
                optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.COST_FIELD,
                "Yol Ağı Maliyet Alanı (Boş = Metrik Uzunluk)",
                parentLayerParameterName=self.NETWORK,
                optional=True,
                type=QgsProcessingParameterField.DataType.Numeric
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.CUTOFF,
                "Maksimum Ağ Mesafesi / Maliyet Kesme Limiti (0 = Sınırsız)",
                QgsProcessingParameterNumber.Type.Double,
                0.0,
                minValue=0.0
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.BARRIER_RATIO,
                "Engel (Barrier) Eşiği Detour Oranı (Ödev 13 Standardı = 1.35)",
                QgsProcessingParameterNumber.Type.Double,
                1.35,
                minValue=1.0,
                maxValue=5.0
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.MATRIX,
                "OD Maliyet Matrisi Tablosu (No Geometry)",
                QgsProcessing.SourceType.TypeVector,
                optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.DESIRE_LINES,
                "Kuş Uçuşu Arzu Hatları ve Engel Analizi (Lines)",
                QgsProcessing.SourceType.TypeVectorLine,
                optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.ROUTES,
                "Gerçek Yol Ağı En Kısa Rotaları (Lines)",
                QgsProcessing.SourceType.TypeVectorLine,
                optional=True
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        network = self.parameterAsSource(parameters, self.NETWORK, context)
        origins = self.parameterAsSource(parameters, self.ORIGINS, context)
        orig_id_field = self.parameterAsString(parameters, self.ORIGIN_ID, context)
        destinations = self.parameterAsSource(parameters, self.DESTINATIONS, context)
        dest_id_field = self.parameterAsString(parameters, self.DEST_ID, context)
        cost_field = self.parameterAsString(parameters, self.COST_FIELD, context)
        cutoff = self.parameterAsDouble(parameters, self.CUTOFF, context) or None
        barrier_threshold = self.parameterAsDouble(parameters, self.BARRIER_RATIO, context)
        self.require_projected(network, "Yol ağı")

        crs = network.sourceCrs()
        graph, polylines, line_feats = self.network_graph(network, cost_field)
        n = graph.num_nodes

        o_xy, o_feats = self.source_points(origins, crs, context.transformContext())
        o_nodes = graphs.nearest_nodes(graph, o_xy)
        o_idx = origins.fields().lookupField(orig_id_field)
        o_ids = [str(feat.attributes()[o_idx]) if o_idx >= 0 else str(i) for i, feat in enumerate(o_feats)]

        if destinations is not None:
            d_xy, d_feats = self.source_points(destinations, crs, context.transformContext())
            d_nodes = graphs.nearest_nodes(graph, d_xy)
            d_idx = destinations.fields().lookupField(dest_id_field) if dest_id_field else -1
            d_ids = [str(feat.attributes()[d_idx]) if d_idx >= 0 else str(j) for j, feat in enumerate(d_feats)]
        else:
            d_xy, d_feats = o_xy, o_feats
            d_nodes = o_nodes
            d_ids = o_ids

        feedback.pushInfo(f"OD Analizi: {len(o_nodes)} orijin x {len(d_nodes)} destinasyon...")
        unique_o_nodes, orig_map = np.unique(o_nodes, return_inverse=True)
        dmat = paths.many_to_many(
            graph.indptr, graph.adj_node, graph.adj_cost, n,
            unique_o_nodes, cutoff=cutoff, cancel=feedback.isCanceled
        )

        matrix_fields = self.make_fields(
            ("origin_id", STRING),
            ("dest_id", STRING),
            ("net_cost", DOUBLE),
            ("straight_cost", DOUBLE),
            ("detour_ratio", DOUBLE),
            ("is_barrier", INT)
        )
        line_fields = self.make_fields(
            ("origin_id", STRING),
            ("dest_id", STRING),
            ("net_cost", DOUBLE),
            ("straight_cost", DOUBLE),
            ("detour_ratio", DOUBLE),
            ("is_barrier", INT)
        )

        results = {}
        matrix_sink = None
        if self.MATRIX in parameters and parameters[self.MATRIX]:
            matrix_sink, m_dest = self.parameterAsSink(
                parameters, self.MATRIX, context, matrix_fields,
                QgsWkbTypes.Type.NoGeometry, crs
            )
            results[self.MATRIX] = m_dest

        desire_sink = None
        if self.DESIRE_LINES in parameters and parameters[self.DESIRE_LINES]:
            desire_sink, dl_dest = self.parameterAsSink(
                parameters, self.DESIRE_LINES, context, line_fields,
                QgsWkbTypes.Type.LineString, crs
            )
            results[self.DESIRE_LINES] = dl_dest

        route_sink = None
        if self.ROUTES in parameters and parameters[self.ROUTES]:
            route_sink, rt_dest = self.parameterAsSink(
                parameters, self.ROUTES, context, line_fields,
                QgsWkbTypes.Type.LineString, crs
            )
            results[self.ROUTES] = rt_dest

        total_pairs = len(o_nodes) * len(d_nodes)
        done = 0
        barrier_count = 0

        for i, u_idx in enumerate(orig_map):
            if feedback.isCanceled():
                break
            s_node = int(o_nodes[i])
            s_xy = o_xy[i]
            s_id = o_ids[i]
            row_d = dmat[u_idx]

            for j, t_node in enumerate(d_nodes):
                t_node = int(t_node)
                t_xy = d_xy[j]
                t_id = d_ids[j]
                if s_id == t_id and len(o_nodes) == len(d_nodes):
                    continue

                net_c = float(row_d[t_node])
                if not np.isfinite(net_c):
                    continue

                dx = float(t_xy[0] - s_xy[0])
                dy = float(t_xy[1] - s_xy[1])
                eu_c = float(math.hypot(dx, dy))
                detour = float(net_c / max(eu_c, 1e-3))
                is_barrier = 1 if detour >= barrier_threshold else 0
                if is_barrier:
                    barrier_count += 1

                attrs = [s_id, t_id, round(net_c, 2), round(eu_c, 2), round(detour, 3), is_barrier]

                if matrix_sink:
                    mf = QgsFeature(matrix_fields)
                    mf.setAttributes(attrs)
                    matrix_sink.addFeature(mf, QgsFeatureSink.Flag.FastInsert)

                if desire_sink:
                    df = QgsFeature(line_fields)
                    df.setGeometry(QgsGeometry.fromPolylineXY([
                        QgsPointXY(float(s_xy[0]), float(s_xy[1])),
                        QgsPointXY(float(t_xy[0]), float(t_xy[1]))
                    ]))
                    df.setAttributes(attrs)
                    desire_sink.addFeature(df, QgsFeatureSink.Flag.FastInsert)

                if route_sink:
                    r_nodes, r_edges = paths.shortest_path(
                        graph.indptr, graph.adj_node, graph.adj_edge, graph.adj_cost,
                        n, s_node, t_node, cutoff=cutoff
                    )
                    if r_edges:
                        route_lines = []
                        for edge_id in r_edges:
                            pts = [QgsPointXY(float(x), float(y)) for x, y in polylines[edge_id]]
                            route_lines.extend(pts)
                        if len(route_lines) >= 2:
                            rf = QgsFeature(line_fields)
                            rf.setGeometry(QgsGeometry.fromPolylineXY(route_lines))
                            rf.setAttributes(attrs)
                            route_sink.addFeature(rf, QgsFeatureSink.Flag.FastInsert)

                done += 1
                if done % 100 == 0:
                    feedback.setProgress(int(100.0 * done / max(1, total_pairs)))

        feedback.pushInfo(
            f"OD Matrisi tamamlandı: {done} çift hesaplandı. "
            f"Detour >= {barrier_threshold} olan {barrier_count} kritik engel aksı tespit edildi."
        )
        return results

    def createInstance(self):
        return ODCostMatrixAlgorithm()


ODMatrixAlgorithm = ODCostMatrixAlgorithm

