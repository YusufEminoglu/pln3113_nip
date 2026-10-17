# -*- coding: utf-8 -*-
"""PLN3113 NİP - 2SFCA Tesis Yeterliliği ve Kapasite-Talep Analizi (Ödev 13).

Donatı kapasitesi (öğrenci, yatak, m²) ile talep (ada nüfus merkez noktaları)
karşılaştırılır. Aşırı yüklü (overloaded) ve hizmet ulaşamayan (uncovered) alanlar tespit edilir.
E2SFCA (Enhanced Two-Step Floating Catchment Area) yöntemi.
"""
from __future__ import annotations

import numpy as np

from qgis.core import (
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
    QgsWkbTypes,
)

from ..core.planx_engine import graphs, paths
from ..core.planx_engine.planx_base import (
    DOUBLE,
    GROUP_STANDARDS,
    INT,
    STRING,
    PlanXBaseAlgorithm,
)


class FacilityAdequacyAlgorithm(PlanXBaseAlgorithm):
    GROUP = GROUP_STANDARDS
    NETWORK = "NETWORK"
    DEMAND = "DEMAND"
    POP_FIELD = "POP_FIELD"
    FACILITIES = "FACILITIES"
    FACILITY_ID = "FACILITY_ID"
    CAPACITY_FIELD = "CAPACITY_FIELD"
    MAX_COST = "MAX_COST"
    FCA_DECAY = "FCA_DECAY"
    OUT_FACILITIES = "OUT_FACILITIES"
    OUT_DEMAND = "OUT_DEMAND"

    def name(self):
        return "nip_2sfca_yeterlilik"

    def displayName(self):
        return self.tr("13.5 2SFCA Donatı Yeterliliği ve Kapasite-Erişim Analizi")

    def shortHelpString(self):
        return self.tr(
            "PLN3113 1. Ara Jüri Ödev 13 gereksinimi 5. Adım:\n\n"
            "2SFCA (Geliştirilmiş İki Adımlı Yüzen Havza / E2SFCA) Yöntemi:\n"
            "1. Adım: Donatı kapasitesi (öğrenci, yatak, m²) ile yol ağı havzasındaki ağırlıklı "
            "nüfus talebi oranlanır (Arz-Talep Oranı R_j).\n"
            "2. Adım: Her talep noktası (ada nüfus merkezi / konut) için erişilebilir donatıların "
            "R_j oranları Gauss mesafe azalım fonksiyonuyla toplanır (fca_erisim_skoru).\n\n"
            "Çıktılar:\n"
            "- Donatılar: Atanan nüfus, doluluk oranı (utilization) ve durum (Yeterli, Aşırı Yüklü, Kullanılmayan).\n"
            "- Talep Noktaları: Kapsandı (1/0), en yakın donatı, ağ yürüme mesafesi ve 2SFCA erişim skoru."
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.NETWORK, self.tr("Yol Ağı (Aks Çizgileri)"), [QgsProcessing.SourceType.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.DEMAND, self.tr("Talep / Nüfus Noktaları (Ada Merkezleri veya Binalar)"),
            [QgsProcessing.SourceType.TypeVectorAnyGeometry]))
        self.addParameter(QgsProcessingParameterField(
            self.POP_FIELD, self.tr("Nüfus Alanı (Boşsa her nokta 1 kişi)"),
            parentLayerParameterName=self.DEMAND, optional=True,
            type=QgsProcessingParameterField.DataType.Numeric))
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.FACILITIES, self.tr("Donatı / Tesis Noktaları"), [QgsProcessing.SourceType.TypeVectorAnyGeometry]))
        self.addParameter(QgsProcessingParameterField(
            self.FACILITY_ID, self.tr("Donatı Ad / Kimlik Alanı"),
            parentLayerParameterName=self.FACILITIES, optional=True))
        self.addParameter(QgsProcessingParameterField(
            self.CAPACITY_FIELD, self.tr("Donatı Kapasite Alanı (Kişi, Yatak, m² vb.)"),
            parentLayerParameterName=self.FACILITIES, optional=True,
            type=QgsProcessingParameterField.DataType.Numeric))
        self.addParameter(QgsProcessingParameterNumber(
            self.MAX_COST, self.tr("Maksimum Yürüme / Servis Havzası Mesafesi (metre)"),
            QgsProcessingParameterNumber.Type.Double, 800.0, minValue=10.0))
        self.addParameter(QgsProcessingParameterNumber(
            self.FCA_DECAY, self.tr("Gauss Mesafe Azalım Gücü (Decay Strength, 0 = Ağırlıksız)"),
            QgsProcessingParameterNumber.Type.Double, 1.0, minValue=0.0, maxValue=10.0))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUT_FACILITIES, self.tr("Donatı Yeterlilik ve Yük Durumu"),
            type=QgsProcessing.SourceType.TypeVectorPoint))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUT_DEMAND, self.tr("Talep Kapsama ve 2SFCA Erişim Skoru"),
            type=QgsProcessing.SourceType.TypeVectorPoint))

    def processAlgorithm(self, parameters, context, feedback):
        network = self.parameterAsSource(parameters, self.NETWORK, context)
        demand = self.parameterAsSource(parameters, self.DEMAND, context)
        facilities = self.parameterAsSource(parameters, self.FACILITIES, context)
        pop_field = self.parameterAsString(parameters, self.POP_FIELD, context)
        fac_id = self.parameterAsString(parameters, self.FACILITY_ID, context)
        cap_field = self.parameterAsString(parameters, self.CAPACITY_FIELD, context)
        max_cost = self.parameterAsDouble(parameters, self.MAX_COST, context)
        fca_decay = self.parameterAsDouble(parameters, self.FCA_DECAY, context)

        self.require_projected(network, "Yol ağı")
        crs = network.sourceCrs()

        graph, polylines, _ = self.network_graph(network)
        d_xy, d_feats = self.source_points(demand, crs, context.transformContext())
        f_xy, f_feats = self.source_points(facilities, crs, context.transformContext())

        if len(d_xy) == 0:
            raise QgsProcessingException("Talep katmanında geçerli nokta bulunamadı.")
        if len(f_xy) == 0:
            raise QgsProcessingException("Donatı katmanında geçerli nokta bulunamadı.")

        d_nodes = graphs.nearest_nodes(graph, d_xy)
        f_nodes = graphs.nearest_nodes(graph, f_xy)

        pop_idx = demand.fields().lookupField(pop_field) if pop_field else -1
        fid_idx = facilities.fields().lookupField(fac_id) if fac_id else -1
        cap_idx = facilities.fields().lookupField(cap_field) if cap_field else -1

        unique_nodes, first_pos = np.unique(f_nodes, return_index=True)
        dist, label = paths.multi_source(
            graph.indptr, graph.adj_node, graph.adj_cost,
            graph.num_nodes, unique_nodes, cutoff=max_cost)

        def pop_of(feat):
            if pop_idx < 0:
                return 1.0
            try:
                v = feat.attributes()[pop_idx]
                return max(0.0, float(v)) if v is not None else 0.0
            except (TypeError, ValueError):
                return 0.0

        f_ids = [str(f.attributes()[fid_idx]) if fid_idx >= 0 else str(i + 1) for i, f in enumerate(f_feats)]
        populations = np.asarray([pop_of(feature) for feature in d_feats], dtype=float)
        capacity_values = []
        for i, feature in enumerate(f_feats):
            if cap_idx >= 0:
                try:
                    v = feature.attributes()[cap_idx]
                    capacity_values.append(max(0.0, float(v)) if v is not None else 100.0)
                except (TypeError, ValueError):
                    capacity_values.append(100.0)
            else:
                capacity_values.append(100.0)

        # Facility to demand distance matrix (f x d)
        facility_dist = paths.many_to_many(
            graph.indptr, graph.adj_node, graph.adj_cost, graph.num_nodes,
            f_nodes, cutoff=max_cost,
        )[:, d_nodes]

        decay_weights = np.where(
            np.isfinite(facility_dist),
            np.exp(-fca_decay * (facility_dist / max(max_cost, 1e-9)) ** 2),
            0.0,
        )

        # 1. Adım: Her donatının havzasındaki ağırlıklı nüfus talebi
        catchment_demand = decay_weights @ populations
        supply_ratio = np.divide(
            np.asarray(capacity_values), catchment_demand,
            out=np.zeros(len(f_feats), dtype=float), where=catchment_demand > 0,
        )

        # 2. Adım: Her talep noktası için erişilebilirlik skoru (E2SFCA)
        fca_access = decay_weights.T @ supply_ratio

        # Demand output
        assigned = {}
        d_fields = self.make_fields(
            ("kapsandi", INT), ("donati", STRING),
            ("ag_mesafesi_m", DOUBLE), ("fca_erisim_skoru", DOUBLE),
            base=demand.fields())
        d_sink, d_dest = self.parameterAsSink(
            parameters, self.OUT_DEMAND, context, d_fields, QgsWkbTypes.Type.Point, crs)

        covered_pop = 0.0
        total_pop = float(np.sum(populations))
        n_dem = len(demand.fields())

        for i, feat in enumerate(d_feats):
            if feedback.isCanceled():
                break
            p = populations[i]
            node = d_nodes[i]
            d = dist[node]
            lab = label[node]
            covered = bool(lab >= 0 and np.isfinite(d))
            fac = ""
            cost_val = -1.0
            if covered:
                j = int(first_pos[lab])
                fac = f_ids[j]
                cost_val = float(d)
                assigned[j] = assigned.get(j, 0.0) + p
                covered_pop += p

            out = QgsFeature(d_fields)
            out.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(*d_xy[i])))
            out.setAttributes(list(feat.attributes())[:n_dem] +
                              [1 if covered else 0, fac, round(cost_val, 1), round(float(fca_access[i]), 5)])
            d_sink.addFeature(out, QgsFeatureSink.Flag.FastInsert)

        # Facilities output
        f_fields = self.make_fields(
            ("donati", STRING), ("kapasite", DOUBLE), ("atanan_nufus", DOUBLE),
            ("doluluk_orani", DOUBLE), ("durum", STRING),
            ("havza_talep", DOUBLE), ("arz_orani_R", DOUBLE))
        f_sink, f_dest = self.parameterAsSink(
            parameters, self.OUT_FACILITIES, context, f_fields, QgsWkbTypes.Type.Point, crs)

        overloaded = 0
        for j, feat in enumerate(f_feats):
            cap = capacity_values[j]
            load = assigned.get(j, 0.0)
            util = load / cap if cap > 0 else (0.0 if load == 0 else 9999.0)
            if load == 0:
                status = "Kullanılmayan (Unused)"
            elif util <= 1.0:
                status = "Yeterli (Adequate)"
            else:
                status = "Aşırı Yüklü (Overloaded)"
                overloaded += 1

            out = QgsFeature(f_fields)
            out.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(*f_xy[j])))
            out.setAttributes([
                f_ids[j], cap, round(load, 1), round(util, 3), status,
                round(float(catchment_demand[j]), 1), round(float(supply_ratio[j]), 5)
            ])
            f_sink.addFeature(out, QgsFeatureSink.Flag.FastInsert)

        share = covered_pop / total_pop if total_pop > 0 else 0.0
        feedback.pushInfo(self.tr(
            f"Kapsanan Nüfus: {covered_pop:.0f} / {total_pop:.0f} (%{share * 100:.1f}); "
            f"{overloaded} donatıda aşırı yük (kapasite yetersizliği) tespit edildi."))

        return {self.OUT_FACILITIES: f_dest, self.OUT_DEMAND: d_dest}

    def createInstance(self):
        return FacilityAdequacyAlgorithm()
