# -*- coding: utf-8 -*-
"""PLN3113 NİP - Hizmet Alanları ve Yürüme İzokronları Analizi.

5 dk (400 m), 10 dk (800 m), 15 dk (1200 m) yürüyüş izokronları (4.8 km/s).
PlanX yüksek performanslı kısmi kenar kırpma ve pedshed motoru.
"""
from __future__ import annotations

import contextlib
import numpy as np

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsFeatureSink,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsPointXY,
    QgsProcessing,
    QgsProcessingException,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterNumber,
    QgsProcessingParameterString,
    QgsSpatialIndex,
    QgsWkbTypes,
)

from ..core.planx_engine import graphs, isochrone, paths
from ..core.planx_engine.planx_base import (
    DOUBLE,
    GROUP_NETWORK,
    INT,
    STRING,
    PlanXBaseAlgorithm,
)

ALL_LABEL = "TUM_DONATILAR"


def parse_breaks(text: str):
    vals = sorted({float(t) for t in text.replace(";", ",").split(",") if t.strip()})
    if not vals or any(v <= 0 for v in vals):
        raise QgsProcessingException(
            "Eşik değerleri virgülle ayrılmış pozitif sayılar olmalıdır (örn: 400, 800, 1200).")
    return vals


class ServiceAreasAlgorithm(PlanXBaseAlgorithm):
    GROUP = GROUP_NETWORK
    NETWORK = "NETWORK"
    FACILITIES = "FACILITIES"
    FACILITY_ID = "FACILITY_ID"
    BREAKS = "BREAKS"
    COMBINE = "COMBINE"
    METHOD = "METHOD"
    BUFFER = "BUFFER"
    HULL_DETAIL = "HULL_DETAIL"
    RINGS = "RINGS"
    AREAS = "AREAS"
    CIRCLES = "CIRCLES"
    EDGES = "EDGES"
    SUMMARY = "SUMMARY"

    def name(self):
        return "nip_hizmet_izokron"

    def displayName(self):
        return self.tr("4. Hizmet Alanları ve Yürüme İzokronları (Pedshed Analizi)")

    def shortHelpString(self):
        return self.tr(
            "Kentsel Hizmet Alanları ve Yaya İzokron Analizi:\n\n"
            "5 dk (400 m), 10 dk (800 m) ve 15 dk (1200 m) yürüme izokronları "
            "(4.8 km/s ortalama yaya hızı). Odak: ilkokullar, sağlık ocakları, açık yeşil alanlar.\n\n"
            "PlanX gömülü Dijkstra motoru ile caddeler mid-street (tam bütçenin bittiği metrede) "
            "hassas olarak kırpılır. Her eşik için ayrıca mevzuattaki dairesel etki tamponu (circle) "
            "çizilir ve PEDSHED ORANI (Ağ Havzası Alanı / Daire Alanı) hesaplanır.\n\n"
            "0.40 altındaki pedshed değerleri kopuk/izole donatı olarak sınıflandırılır."
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.NETWORK, self.tr("Yol Ağı (Aks Çizgileri)"), [QgsProcessing.SourceType.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.FACILITIES, self.tr("Donatı / Hizmet Noktaları"), [QgsProcessing.SourceType.TypeVectorAnyGeometry]))
        self.addParameter(QgsProcessingParameterField(
            self.FACILITY_ID, self.tr("Donatı Ad / Kimlik Alanı (Opsiyonel)"),
            parentLayerParameterName=self.FACILITIES, optional=True))
        self.addParameter(QgsProcessingParameterString(
            self.BREAKS,
            self.tr("Yürüme Mesafesi Eşikleri (metre, örn: 400, 800, 1200)"),
            "400, 800, 1200"))
        self.addParameter(QgsProcessingParameterEnum(
            self.COMBINE, self.tr("Analiz Kapsamı"),
            options=[self.tr("Birleşik Genel Havza (En yakın donatı kazanır)"),
                     self.tr("Her Donatı İçin Ayrı + Birleşik")],
            defaultValue=0))
        self.addParameter(QgsProcessingParameterEnum(
            self.METHOD, self.tr("İzokron Poligon Üretim Yöntemi"),
            options=[self.tr("Yol Ağı Tamponu (Street Buffer - Önerilen)"),
                     self.tr("İçbükey Örtü (Concave Hull - İzokron Blobu)"),
                     self.tr("Dışbükey Örtü (Convex Hull - Zarf)")],
            defaultValue=0))
        self.addParameter(QgsProcessingParameterNumber(
            self.BUFFER, self.tr("Yol Tampon Genişliği (metre)"),
            QgsProcessingParameterNumber.Type.Double, 35.0, minValue=1.0))
        self.addParameter(QgsProcessingParameterNumber(
            self.HULL_DETAIL,
            self.tr("Concave Hull Detayı (0 = sıkı, 1 = konveks)"),
            QgsProcessingParameterNumber.Type.Double, 0.3,
            minValue=0.01, maxValue=1.0))
        self.addParameter(QgsProcessingParameterBoolean(
            self.RINGS, self.tr("Bantları halka (fark) olarak üret"), False))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.AREAS, self.tr("Hizmet Alanı İzokron Poligonları"),
            type=QgsProcessing.SourceType.TypeVectorPolygon))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.CIRCLES, self.tr("Mevzuat Dairesel Tamponları (Kuş Uçuşu)"),
            type=QgsProcessing.SourceType.TypeVectorPolygon))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.EDGES, self.tr("Erişilen Yol Parçaları (Kırpılmış Çizgiler)"),
            type=QgsProcessing.SourceType.TypeVectorLine))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.SUMMARY, self.tr("Pedshed Erişilebilirlik Karnesi"),
            type=QgsProcessing.SourceType.TypeVector))

    @staticmethod
    def _snap_to_edge(pt_xy, polylines, edge_geoms, index):
        pt = QgsPointXY(float(pt_xy[0]), float(pt_xy[1]))
        cand = index.nearestNeighbor(pt, 5)
        if not cand:
            cand = range(len(edge_geoms))
        best = (None, 0.0, float("inf"))
        for e in cand:
            sqr_d, min_pt, after, _ = edge_geoms[e].closestSegmentWithContext(pt)
            if sqr_d < best[2]:
                coords = polylines[e]
                seg = np.diff(coords, axis=0)
                cum = np.concatenate([[0.0], np.cumsum(np.hypot(seg[:, 0], seg[:, 1]))])
                total = cum[-1]
                arc = cum[max(after - 1, 0)] + float(
                    np.hypot(min_pt.x() - coords[max(after - 1, 0)][0],
                             min_pt.y() - coords[max(after - 1, 0)][1]))
                t = 0.0 if total <= 0 else min(max(arc / total, 0.0), 1.0)
                best = (int(e), float(t), float(sqr_d))
        return best[0], best[1], float(np.sqrt(best[2]))

    @staticmethod
    def _hull(points_xy, method, detail, buffer_w=25.0):
        if not points_xy:
            return None
        if len(points_xy) < 3:
            mp = QgsGeometry.fromMultiPointXY(points_xy)
            return mp.buffer(buffer_w, 8)
        mp = QgsGeometry.fromMultiPointXY(points_xy)
        hull = None
        if method == 1:
            with contextlib.suppress(Exception):
                h = mp.concaveHull(float(detail), False)
                if h is not None and not h.isNull() and not h.isEmpty():
                    hull = h
        if hull is None or hull.isNull() or hull.isEmpty():
            with contextlib.suppress(Exception):
                hull = mp.convexHull()

        if hull is None or hull.isNull() or hull.isEmpty():
            return mp.buffer(buffer_w, 8)

        # Geometri geçerliliğini onar
        if not hull.isGeosValid():
            with contextlib.suppress(Exception):
                hull = hull.makeValid()

        # Çizgiye veya noktaya dejenere olmuşsa (örneğin tek aks üzerindeki noktalar)
        # MultiPolygon katmanına yazılabilmesi için tamponla alana çevir
        if hull.type() != QgsWkbTypes.GeometryType.PolygonGeometry:
            if hull.isMultipart():
                with contextlib.suppress(Exception):
                    parts = [p for p in hull.asGeometryCollection() if p.type() == QgsWkbTypes.GeometryType.PolygonGeometry]
                    if parts:
                        hull = QgsGeometry.unaryUnion(parts)
            if hull.type() != QgsWkbTypes.GeometryType.PolygonGeometry:
                hull = hull.buffer(buffer_w, 8)

        return None if hull is None or hull.isNull() or hull.isEmpty() else hull

    def processAlgorithm(self, parameters, context, feedback):
        network = self.parameterAsSource(parameters, self.NETWORK, context)
        facilities = self.parameterAsSource(parameters, self.FACILITIES, context)
        fac_id = self.parameterAsString(parameters, self.FACILITY_ID, context)
        breaks = parse_breaks(self.parameterAsString(parameters, self.BREAKS, context))
        per_facility = self.parameterAsEnum(parameters, self.COMBINE, context) == 1
        method = self.parameterAsEnum(parameters, self.METHOD, context)
        buffer_w = self.parameterAsDouble(parameters, self.BUFFER, context)
        hull_detail = self.parameterAsDouble(parameters, self.HULL_DETAIL, context)
        rings = self.parameterAsBoolean(parameters, self.RINGS, context)

        self.require_projected(network, "Yol ağı")
        crs = network.sourceCrs()

        graph, polylines, line_feats = self.network_graph(network)
        f_xy, f_feats = self.source_points(facilities, crs, context.transformContext())
        n_fac = len(f_xy)
        if n_fac == 0:
            raise QgsProcessingException("Donatı katmanında geçerli nokta bulunamadı.")

        labels = []
        seen = {}
        id_idx = facilities.fields().lookupField(fac_id) if fac_id else -1
        for i, f in enumerate(f_feats):
            if id_idx >= 0:
                v = f.attributes()[id_idx]
                lab = str(v) if v is not None else str(i + 1)
            else:
                lab = str(i + 1)
            if lab in seen or lab == ALL_LABEL:
                seen[lab] = seen.get(lab, 1) + 1
                lab = f"{lab}_{seen[lab]}"
            seen.setdefault(lab, 1)
            labels.append(lab)

        edge_geoms = []
        sp_index = QgsSpatialIndex()
        for e, arr in enumerate(polylines):
            g = QgsGeometry.fromPolylineXY([QgsPointXY(x, y) for x, y in arr])
            edge_geoms.append(g)
            qf = QgsFeature(e)
            qf.setGeometry(g)
            sp_index.addFeature(qf)

        max_break = breaks[-1]
        entries = []
        node_src = []
        node_off = []
        source_owner = []
        per_sources = []
        for i in range(n_fac):
            e, t, snap = self._snap_to_edge(f_xy[i], polylines, edge_geoms, sp_index)
            if e is None:
                raise QgsProcessingException("Donatılar yol ağına oturtulamadı.")
            snap_cost = snap
            entries.append((e, t, snap_cost))
            sources_i, offsets_i = [], []
            direction = int(graph.edge_direction[e])
            if direction <= 0:
                sources_i.append(int(graph.edge_from[e]))
                offsets_i.append(snap_cost + t * float(graph.edge_rev_cost[e]))
            if direction >= 0:
                sources_i.append(int(graph.edge_to[e]))
                offsets_i.append(snap_cost + (1.0 - t) * float(graph.edge_cost[e]))
            node_src.extend(sources_i)
            node_off.extend(offsets_i)
            source_owner.extend([i] * len(sources_i))
            per_sources.append((sources_i, offsets_i))

        node_src_a = np.asarray(node_src, dtype=np.int64)
        node_off_a = np.asarray(node_off, dtype=np.float64)
        dist_all, label_all = paths.multi_source_offset(
            graph.indptr, graph.adj_node, graph.adj_cost, graph.num_nodes,
            node_src_a, node_off_a, cutoff=max_break)

        scopes = [(ALL_LABEL, dist_all, entries, None)]
        if per_facility:
            for i in range(n_fac):
                if feedback.isCanceled():
                    break
                s_i, o_i = per_sources[i]
                d_i, _ = paths.multi_source_offset(
                    graph.indptr, graph.adj_node, graph.adj_cost, graph.num_nodes,
                    np.asarray(s_i, dtype=np.int64),
                    np.asarray(o_i, dtype=np.float64),
                    cutoff=max_break)
                scopes.append((labels[i], d_i, [entries[i]], i))

        reach = {}
        for si, (lab, dist, ent, _fi) in enumerate(scopes):
            for brk in breaks:
                if feedback.isCanceled():
                    break
                reach[(lab, brk)] = isochrone.reach_intervals(
                    dist, graph.edge_from, graph.edge_to, graph.edge_cost,
                    brk, entries=ent, reverse_cost=graph.edge_rev_cost,
                    directions=graph.edge_direction)

        def pieces_geoms(lab, brk):
            out = []
            for e, iv in reach.get((lab, brk), {}).items():
                for lo, hi in iv:
                    arr = isochrone.cut_polyline(polylines[e], lo, hi)
                    if arr is not None:
                        out.append(QgsGeometry.fromPolylineXY(
                            [QgsPointXY(x, y) for x, y in arr]))
            return out

        def street_len(lab, brk):
            return float(sum(
                isochrone.interval_length(iv) * float(graph.edge_len[e])
                for e, iv in reach.get((lab, brk), {}).items()))

        # 1. EDGES SINK
        edge_fields = self.make_fields(
            ("donati", STRING), ("mesafe_m", DOUBLE), ("sure_dk", DOUBLE),
            ("parca_uzunluk_m", DOUBLE))
        edge_sink, edges_dest = self.parameterAsSink(
            parameters, self.EDGES, context, edge_fields,
            QgsWkbTypes.Type.LineString, crs)

        for bi, brk in enumerate(breaks):
            prev = breaks[bi - 1] if bi else None
            cur = reach.get((ALL_LABEL, brk), {})
            for e, iv in cur.items():
                band_iv = iv if prev is None else isochrone.subtract_intervals(
                    iv, reach[(ALL_LABEL, prev)].get(e, []))
                for lo, hi in band_iv:
                    arr = isochrone.cut_polyline(polylines[e], lo, hi)
                    if arr is None:
                        continue
                    da = float(dist_all[graph.edge_from[e]])
                    db = float(dist_all[graph.edge_to[e]])
                    win = label_all[graph.edge_from[e] if da <= db else graph.edge_to[e]]
                    fac_lab = labels[source_owner[int(win)]] if win >= 0 and int(win) < len(source_owner) else ""
                    piece_len = float(graph.edge_len[e]) * (hi - lo)
                    out = QgsFeature(edge_fields)
                    out.setGeometry(QgsGeometry.fromPolylineXY(
                        [QgsPointXY(x, y) for x, y in arr]))
                    sure = round(float(brk) / (4800.0 / 60.0), 1)
                    out.setAttributes([fac_lab, float(brk), sure, round(piece_len, 2)])
                    edge_sink.addFeature(out, QgsFeatureSink.Flag.FastInsert)

        # 2. CIRCLES SINK
        circle_fields = self.make_fields(
            ("donati", STRING), ("mesafe_m", DOUBLE), ("sure_dk", DOUBLE), ("alan_m2", DOUBLE))
        circle_sink, circles_dest = self.parameterAsSink(
            parameters, self.CIRCLES, context, circle_fields,
            QgsWkbTypes.Type.MultiPolygon, crs)
        circle_area = {}
        for brk in breaks:
            discs = []
            sure = round(float(brk) / (4800.0 / 60.0), 1)
            for i in range(n_fac):
                disc = QgsGeometry.fromPointXY(QgsPointXY(*f_xy[i])).buffer(brk, 64)
                discs.append(disc)
                circle_area[(labels[i], brk)] = float(disc.area())
                if per_facility:
                    f = QgsFeature(circle_fields)
                    disc_multi = QgsGeometry(disc)
                    if not disc_multi.isMultipart():
                        disc_multi.convertToMultiType()
                    f.setGeometry(disc_multi)
                    f.setAttributes([labels[i], float(brk), sure, float(disc.area())])
                    circle_sink.addFeature(f, QgsFeatureSink.Flag.FastInsert)
            merged = QgsGeometry.unaryUnion(discs)
            circle_area[(ALL_LABEL, brk)] = float(merged.area())
            f = QgsFeature(circle_fields)
            if not merged.isMultipart():
                merged.convertToMultiType()
            f.setGeometry(merged)
            f.setAttributes([ALL_LABEL, float(brk), sure, float(merged.area())])
            circle_sink.addFeature(f, QgsFeatureSink.Flag.FastInsert)

        # 3. AREAS SINK
        area_fields = self.make_fields(
            ("donati", STRING), ("mesafe_m", DOUBLE), ("sure_dk", DOUBLE),
            ("alan_m2", DOUBLE), ("pedshed", DOUBLE), ("durum", STRING))
        area_sink, areas_dest = self.parameterAsSink(
            parameters, self.AREAS, context, area_fields,
            QgsWkbTypes.Type.MultiPolygon, crs)

        cum_area = {}
        for lab, dist, ent, fi in scopes:
            prev_geom = None
            fac_pts = ([QgsPointXY(*f_xy[i]) for i in range(n_fac)]
                       if fi is None else [QgsPointXY(*f_xy[fi])])
            for bi, brk in enumerate(breaks):
                if feedback.isCanceled():
                    break
                pieces = pieces_geoms(lab, brk)
                geom = None
                if pieces:
                    if method == 0:
                        geom = QgsGeometry.unaryUnion(
                            [g.buffer(buffer_w, 8) for g in pieces])
                    else:
                        pts = list(fac_pts)
                        step = max(brk / 32.0, 1.0)
                        for g in pieces:
                            dense = g.densifyByDistance(step)
                            pts.extend(QgsPointXY(v.x(), v.y())
                                       for v in dense.vertices())
                        geom = self._hull(pts, method, hull_detail, buffer_w)
                        # Concave / Convex hull poligon üretemezse yol tamponuna geri dön
                        if geom is None or geom.isEmpty() or geom.type() != QgsWkbTypes.GeometryType.PolygonGeometry:
                            geom = QgsGeometry.unaryUnion(
                                [g.buffer(buffer_w, 8) for g in pieces])

                if geom is None or geom.isEmpty():
                    cum_area[(lab, brk)] = 0.0
                    prev_geom = None
                    continue

                # Geometri geçerliliğini sağla
                if not geom.isGeosValid():
                    with contextlib.suppress(Exception):
                        geom = geom.makeValid()

                c_a = circle_area.get((lab, brk), 1.0)
                n_a = float(geom.area())
                cum_area[(lab, brk)] = n_a
                ratio = n_a / c_a if c_a > 0 else 0.0
                durum = "İzole (<0.40)" if ratio < 0.40 else "Erişilebilir (>=0.40)"
                sure = round(float(brk) / (4800.0 / 60.0), 1)

                out_geom = geom
                if rings and prev_geom is not None:
                    with contextlib.suppress(Exception):
                        diff = geom.difference(prev_geom)
                        if diff is not None and not diff.isEmpty():
                            if not diff.isGeosValid():
                                diff = diff.makeValid()
                            if diff.type() == QgsWkbTypes.GeometryType.PolygonGeometry:
                                out_geom = diff

                if not out_geom.isMultipart():
                    out_geom.convertToMultiType()

                f = QgsFeature(area_fields)
                f.setGeometry(out_geom)
                f.setAttributes([lab, float(brk), sure, float(out_geom.area()), round(ratio, 3), durum])
                area_sink.addFeature(f, QgsFeatureSink.Flag.FastInsert)
                prev_geom = geom

        # 4. SUMMARY SINK
        sum_fields = self.make_fields(
            ("donati", STRING), ("mesafe_m", DOUBLE), ("sure_dk", DOUBLE),
            ("daire_alani_m2", DOUBLE), ("havza_alani_m2", DOUBLE),
            ("pedshed", DOUBLE), ("durum", STRING), ("yol_uzunlugu_m", DOUBLE))
        sum_sink, summary_dest = self.parameterAsSink(
            parameters, self.SUMMARY, context, sum_fields,
            QgsWkbTypes.Type.NoGeometry, QgsCoordinateReferenceSystem())

        scope_labels = [lab for lab, _, _, _ in scopes]
        for lab in scope_labels:
            for brk in breaks:
                c_area = circle_area.get((lab, brk), 0.0)
                n_area = cum_area.get((lab, brk), 0.0)
                ratio = n_area / c_area if c_area > 0 else 0.0
                durum = "İzole (<0.40)" if ratio < 0.40 else "Erişilebilir (>=0.40)"
                sure = round(float(brk) / (4800.0 / 60.0), 1)
                f = QgsFeature(sum_fields)
                f.setAttributes([lab, float(brk), sure, round(c_area, 1), round(n_area, 1),
                                 round(ratio, 3), durum, round(street_len(lab, brk), 1)])
                sum_sink.addFeature(f, QgsFeatureSink.Flag.FastInsert)

        feedback.pushInfo(self.tr("Hizmet alanları ve pedshed analizi başarıyla tamamlandı."))
        return {
            self.AREAS: areas_dest,
            self.CIRCLES: circles_dest,
            self.EDGES: edges_dest,
            self.SUMMARY: summary_dest,
        }

    def createInstance(self):
        return ServiceAreasAlgorithm()
