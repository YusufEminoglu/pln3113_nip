# -*- coding: utf-8 -*-
"""PLN3113 NİP - 2SFCA Tesis Yeterliliği ve Kapasite-Talep Analizi.

Donatı kapasitesi (öğrenci, yatak, m²) ile talep (ada nüfus merkez noktaları)
karşılaştırılır. Aşırı yüklü (overloaded) ve hizmet ulaşamayan (uncovered) alanlar tespit edilir.
E2SFCA (Enhanced Two-Step Floating Catchment Area) yöntemi.
"""
from __future__ import annotations

import numpy as np

from qgis.core import (
    QgsCoordinateTransform,
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
    DEFAULT_CAPACITY = "DEFAULT_CAPACITY"
    MAX_COST = "MAX_COST"
    FCA_DECAY = "FCA_DECAY"
    OUT_FACILITIES = "OUT_FACILITIES"
    OUT_DEMAND = "OUT_DEMAND"
    OUT_DEMAND_POINTS = "OUT_DEMAND_POINTS"
    OUT_FACILITY_POINTS = "OUT_FACILITY_POINTS"

    def name(self):
        return "nip_2sfca_yeterlilik"

    def displayName(self):
        return self.tr("5. 2SFCA Donatı Yeterliliği ve Kapasite-Erişim Analizi")

    def shortHelpString(self):
        return self.tr(
            "2SFCA Donatı Yeterliliği ve Kapasite-Erişim Analizi:\n\n"
            "2SFCA (Geliştirilmiş İki Adımlı Yüzen Havza / E2SFCA) Yöntemi:\n"
            "1. Adım: Donatı kapasitesi (öğrenci, yatak, m²) ile yol ağı havzasındaki ağırlıklı "
            "nüfus talebi oranlanır (Arz-Talep Oranı R_j).\n"
            "2. Adım: Her talep noktası (ada nüfus merkezi / konut) için erişilebilir donatıların "
            "R_j oranları Gauss mesafe azalım fonksiyonuyla toplanır (fca_erisim_skoru).\n\n"
            "Çıktılar:\n"
            "- Donatılar: Orijinal geometri (poligon/nokta), atanan nüfus, doluluk oranı (utilization) ve yük durumu.\n"
            "- Talep Alanları: Orijinal ada/bina poligonları veya noktaları (Kapsandı 1/0, ağ mesafesi, 2SFCA skoru).\n"
            "- Talep Noktaları: Ada/bina merkez noktaları (Nokta katmanı)."
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
            type=QgsProcessingParameterField.DataType.Any))
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.FACILITIES, self.tr("Donatı / Tesis Noktaları"), [QgsProcessing.SourceType.TypeVectorAnyGeometry]))
        self.addParameter(QgsProcessingParameterField(
            self.FACILITY_ID, self.tr("Donatı Ad / Kimlik Alanı"),
            parentLayerParameterName=self.FACILITIES, optional=True,
            type=QgsProcessingParameterField.DataType.Any))
        self.addParameter(QgsProcessingParameterField(
            self.CAPACITY_FIELD, self.tr("Donatı Kapasite Alanı (Kişi, Yatak, m² vb.)"),
            parentLayerParameterName=self.FACILITIES, optional=True,
            type=QgsProcessingParameterField.DataType.Any))
        self.addParameter(QgsProcessingParameterNumber(
            self.DEFAULT_CAPACITY, self.tr("Varsayılan Donatı Kapasitesi (Kapasite alanı seçilmediğinde)"),
            QgsProcessingParameterNumber.Type.Double, 100.0, minValue=1.0, optional=True))
        self.addParameter(QgsProcessingParameterNumber(
            self.MAX_COST, self.tr("Maksimum Yürüme / Servis Havzası Mesafesi (metre)"),
            QgsProcessingParameterNumber.Type.Double, 800.0, minValue=10.0))
        self.addParameter(QgsProcessingParameterNumber(
            self.FCA_DECAY, self.tr("Gauss Mesafe Azalım Gücü (Decay Strength, 0 = Ağırlıksız)"),
            QgsProcessingParameterNumber.Type.Double, 1.0, minValue=0.0, maxValue=10.0))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUT_FACILITIES, self.tr("Donatı Yeterlilik ve Yük Durumu (Orijinal Geometri)"),
            type=QgsProcessing.SourceType.TypeVectorAnyGeometry))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUT_DEMAND, self.tr("Talep Kapsama ve 2SFCA Erişim Skoru (Orijinal Geometri)"),
            type=QgsProcessing.SourceType.TypeVectorAnyGeometry))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUT_DEMAND_POINTS, self.tr("Talep Merkez / Servis Noktaları (Nokta Çıktısı)"),
            type=QgsProcessing.SourceType.TypeVectorPoint, optional=True))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUT_FACILITY_POINTS, self.tr("Donatı Servis Giriş Noktaları (Nokta Çıktısı)"),
            type=QgsProcessing.SourceType.TypeVectorPoint, optional=True))

    def processAlgorithm(self, parameters, context, feedback):
        network = self.parameterAsSource(parameters, self.NETWORK, context)
        demand = self.parameterAsSource(parameters, self.DEMAND, context)
        facilities = self.parameterAsSource(parameters, self.FACILITIES, context)
        pop_field = self.parameterAsString(parameters, self.POP_FIELD, context)
        fac_id = self.parameterAsString(parameters, self.FACILITY_ID, context)
        cap_field = self.parameterAsString(parameters, self.CAPACITY_FIELD, context)
        default_cap = self.parameterAsDouble(parameters, self.DEFAULT_CAPACITY, context) if self.DEFAULT_CAPACITY in parameters else 100.0
        if default_cap <= 0:
            default_cap = 100.0
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
                if v is None or str(v).strip() == "":
                    return 1.0
                return max(0.0, float(v))
            except (TypeError, ValueError):
                return 1.0

        f_ids = []
        for i, f in enumerate(f_feats):
            val = f.attributes()[fid_idx] if fid_idx >= 0 else None
            if val is not None and str(val).strip() != "":
                f_ids.append(str(val))
            else:
                f_ids.append(f"Donati_{i + 1}")

        populations = np.asarray([pop_of(feature) for feature in d_feats], dtype=float)
        capacity_values = []
        for i, feature in enumerate(f_feats):
            if cap_idx >= 0:
                try:
                    v = feature.attributes()[cap_idx]
                    if v is None or str(v).strip() == "":
                        capacity_values.append(default_cap)
                    else:
                        capacity_values.append(max(1.0, float(v)))
                except (TypeError, ValueError):
                    capacity_values.append(default_cap)
            else:
                capacity_values.append(default_cap)

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
        dem_geom_type = demand.wkbType()
        is_dem_poly = (QgsWkbTypes.geometryType(dem_geom_type) == QgsWkbTypes.GeometryType.PolygonGeometry)
        out_dem_wkb = QgsWkbTypes.Type.MultiPolygon if is_dem_poly else QgsWkbTypes.Type.Point

        dem_xform = None
        if crs is not None and demand.sourceCrs() != crs:
            dem_xform = QgsCoordinateTransform(demand.sourceCrs(), crs, context.transformContext())

        assigned = {}
        d_fields = self.make_fields(
            ("kapsandi", INT), ("donati", STRING),
            ("ag_mesafesi_m", DOUBLE), ("fca_erisim_skoru", DOUBLE),
            base=demand.fields())

        d_sink, d_dest = self.parameterAsSink(
            parameters, self.OUT_DEMAND, context, d_fields, out_dem_wkb, crs)
        d_pts_sink, d_pts_dest = self.parameterAsSink(
            parameters, self.OUT_DEMAND_POINTS, context, d_fields, QgsWkbTypes.Type.Point, crs)

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

            attrs = list(feat.attributes())[:n_dem] + [
                1 if covered else 0, fac, round(cost_val, 1), round(float(fca_access[i]), 5)
            ]

            if d_sink:
                out = QgsFeature(d_fields)
                if is_dem_poly:
                    g = QgsGeometry(feat.geometry())
                    if dem_xform is not None:
                        g.transform(dem_xform)
                    if not g.isMultipart():
                        g.convertToMultiType()
                    out.setGeometry(g)
                else:
                    out.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(*d_xy[i])))
                out.setAttributes(attrs)
                d_sink.addFeature(out, QgsFeatureSink.Flag.FastInsert)

            if d_pts_sink:
                out_pt = QgsFeature(d_fields)
                out_pt.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(*d_xy[i])))
                out_pt.setAttributes(attrs)
                d_pts_sink.addFeature(out_pt, QgsFeatureSink.Flag.FastInsert)

        # Facilities output
        fac_geom_type = facilities.wkbType()
        is_fac_poly = (QgsWkbTypes.geometryType(fac_geom_type) == QgsWkbTypes.GeometryType.PolygonGeometry)
        out_fac_wkb = QgsWkbTypes.Type.MultiPolygon if is_fac_poly else QgsWkbTypes.Type.Point

        fac_xform = None
        if crs is not None and facilities.sourceCrs() != crs:
            fac_xform = QgsCoordinateTransform(facilities.sourceCrs(), crs, context.transformContext())

        f_fields = self.make_fields(
            ("donati", STRING), ("kapasite", DOUBLE), ("atanan_nufus", DOUBLE),
            ("doluluk_orani", DOUBLE), ("durum", STRING),
            ("havza_talep", DOUBLE), ("arz_orani_R", DOUBLE))

        f_sink, f_dest = self.parameterAsSink(
            parameters, self.OUT_FACILITIES, context, f_fields, out_fac_wkb, crs)
        f_pts_sink, f_pts_dest = self.parameterAsSink(
            parameters, self.OUT_FACILITY_POINTS, context, f_fields, QgsWkbTypes.Type.Point, crs)

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

            attrs = [
                f_ids[j], cap, round(load, 1), round(util, 3), status,
                round(float(catchment_demand[j]), 1), round(float(supply_ratio[j]), 5)
            ]

            if f_sink:
                out = QgsFeature(f_fields)
                if is_fac_poly:
                    g = QgsGeometry(feat.geometry())
                    if fac_xform is not None:
                        g.transform(fac_xform)
                    if not g.isMultipart():
                        g.convertToMultiType()
                    out.setGeometry(g)
                else:
                    out.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(*f_xy[j])))
                out.setAttributes(attrs)
                f_sink.addFeature(out, QgsFeatureSink.Flag.FastInsert)

            if f_pts_sink:
                out_pt = QgsFeature(f_fields)
                out_pt.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(*f_xy[j])))
                out_pt.setAttributes(attrs)
                f_pts_sink.addFeature(out_pt, QgsFeatureSink.Flag.FastInsert)

        share = covered_pop / total_pop if total_pop > 0 else 0.0
        feedback.pushInfo(self.tr(
            f"Kapsanan Nüfus: {covered_pop:.0f} / {total_pop:.0f} (%{share * 100:.1f}); "
            f"{overloaded} donatıda aşırı yük (kapasite yetersizliği) tespit edildi."))

        results = {self.OUT_FACILITIES: f_dest, self.OUT_DEMAND: d_dest}
        if d_pts_dest:
            results[self.OUT_DEMAND_POINTS] = d_pts_dest
        if f_pts_dest:
            results[self.OUT_FACILITY_POINTS] = f_pts_dest
        return results

    def createInstance(self):
        return FacilityAdequacyAlgorithm()
