# -*- coding: utf-8 -*-
"""PLN3113 Saf Python & PyQGIS Ulaşım ve Ağ Analiz Motoru (QNEAT ve Dış Eklenti Bağımsız).

PLN3113 - Tire NİP Analiz Stüdyosu
"""
from __future__ import annotations

import heapq
import math
import numpy as np

from qgis.core import (
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsRasterLayer,
    QgsSpatialIndex,
    QgsVectorLayer
)

INF = float("inf")


class NetworkGraph:
    """Yol katmanından düğüm-kenar (primal) graf modeli kuran ve Dijkstra işleten sınıf."""

    def __init__(self, node_xy: np.ndarray, edge_from: np.ndarray, edge_to: np.ndarray,
                 edge_cost: np.ndarray, edge_len: np.ndarray, edge_geoms: list[QgsGeometry] = None):
        self.node_xy = node_xy
        self.edge_from = edge_from
        self.edge_to = edge_to
        self.edge_cost = edge_cost
        self.edge_len = edge_len
        self.edge_geoms = edge_geoms or []
        self._build_adjacency()
        self._build_spatial_index()

    @property
    def num_nodes(self) -> int:
        return len(self.node_xy)

    @property
    def num_edges(self) -> int:
        return len(self.edge_from)

    def _build_adjacency(self):
        n = self.num_nodes
        # İki yönlü (undirected) ulaşım ağı
        src = np.concatenate([self.edge_from, self.edge_to])
        dst = np.concatenate([self.edge_to, self.edge_from])
        eids = np.arange(self.num_edges)
        edge_idx = np.concatenate([eids, eids])
        costs = np.concatenate([self.edge_cost, self.edge_cost])

        order = np.argsort(src, kind="stable")
        src, dst, edge_idx, costs = src[order], dst[order], edge_idx[order], costs[order]

        counts = np.bincount(src, minlength=n)
        self.indptr = np.concatenate([[0], np.cumsum(counts)]).astype(np.int64)
        self.adj_node = dst.astype(np.int32)
        self.adj_edge = edge_idx.astype(np.int32)
        self.adj_cost = costs.astype(np.float64)

    def _build_spatial_index(self):
        self.spatial_index = QgsSpatialIndex()
        for i, (x, y) in enumerate(self.node_xy):
            f = QgsFeature(i)
            f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(float(x), float(y))))
            self.spatial_index.addFeature(f)

    def find_nearest_node(self, pt: QgsPointXY) -> int:
        nearest = self.spatial_index.nearestNeighbor(pt, 1)
        return int(nearest[0]) if nearest else 0

    nearest_node = find_nearest_node

    def dijkstra_tree(self, source: int, cutoff: float = None):
        """Öncül düğüm ve kenar izlemeli Dijkstra algoritması."""
        n = self.num_nodes
        dist = np.full(n, INF, dtype=np.float64)
        pred_node = np.full(n, -1, dtype=np.int64)
        pred_edge = np.full(n, -1, dtype=np.int64)

        dist[source] = 0.0
        heap = [(0.0, source)]

        while heap:
            d, u = heapq.heappop(heap)
            if d > dist[u]:
                continue
            for k in range(self.indptr[u], self.indptr[u + 1]):
                v = self.adj_node[k]
                nd = d + self.adj_cost[k]
                if cutoff is not None and nd > cutoff:
                    continue
                if nd < dist[v]:
                    dist[v] = nd
                    pred_node[v] = u
                    pred_edge[v] = self.adj_edge[k]
                    heapq.heappush(heap, (nd, v))

        return dist, pred_node, pred_edge

    def reconstruct_route(self, pred_node: np.ndarray, pred_edge: np.ndarray,
                          source: int, target: int) -> list[int]:
        """Kaynak ile hedef arasındaki en kısa yolun kenar indekslerini sırasıyla döndürür."""
        if target == source or pred_node[target] == -1:
            return []
        edges = []
        curr = target
        visited = set()
        while curr != source and curr != -1 and curr not in visited:
            visited.add(curr)
            e = pred_edge[curr]
            if e != -1:
                edges.append(e)
            curr = pred_node[curr]
        edges.reverse()
        return edges

    def reconstruct_path_edges(self, *args, **kwargs):
        """Flexible wrapper for route reconstruction."""
        if len(args) == 4:
            a, b, c, d = args
            if isinstance(a, int) and isinstance(b, int):
                return self.reconstruct_route(c, d, a, b)
            else:
                return self.reconstruct_route(a, b, c, d)
        return self.reconstruct_route(*args, **kwargs)

    dijkstra = dijkstra_tree


def build_network_graph(line_layer: QgsVectorLayer, tolerance: float = 0.5,
                        cost_field: str = None) -> NetworkGraph:
    """QGIS Çizgi katmanından topological primal graph oluşturur."""
    raw_nodes = []
    edges_from = []
    edges_to = []
    edges_cost = []
    edges_len = []
    edges_geom = []

    spatial_idx = QgsSpatialIndex()
    node_map = {}

    def get_or_create_node(pt: QgsPointXY) -> int:
        if tolerance > 0.001:
            near = spatial_idx.nearestNeighbor(pt, 1)
            if near:
                candidate_id = near[0]
                cx, cy = raw_nodes[candidate_id]
                if math.hypot(pt.x() - cx, pt.y() - cy) <= tolerance:
                    return candidate_id

        nid = len(raw_nodes)
        raw_nodes.append((pt.x(), pt.y()))
        feat = QgsFeature(nid)
        feat.setGeometry(QgsGeometry.fromPointXY(pt))
        spatial_idx.addFeature(feat)
        return nid

    cost_idx = line_layer.fields().indexFromName(cost_field) if cost_field else -1

    for feat in line_layer.getFeatures():
        geom = feat.geometry()
        if not geom or geom.isEmpty():
            continue

        lines = geom.asGeometryCollection() if geom.isMultipart() else [geom]
        for part in lines:
            line_str = part.constGet()
            if not line_str or line_str.numPoints() < 2:
                continue

            p1 = QgsPointXY(line_str.startPoint().x(), line_str.startPoint().y())
            p2 = QgsPointXY(line_str.endPoint().x(), line_str.endPoint().y())
            u = get_or_create_node(p1)
            v = get_or_create_node(p2)

            length = float(part.length())
            if length <= 0.001:
                continue

            cost = length
            if cost_idx != -1 and feat[cost_idx] is not None:
                try:
                    c_val = float(feat[cost_idx])
                    if c_val > 0:
                        cost = c_val
                except (ValueError, TypeError):
                    pass

            edges_from.append(u)
            edges_to.append(v)
            edges_cost.append(cost)
            edges_len.append(length)
            edges_geom.append(QgsGeometry(part))

    node_xy = np.array(raw_nodes, dtype=np.float64) if raw_nodes else np.empty((0, 2), dtype=np.float64)
    return NetworkGraph(
        node_xy,
        np.array(edges_from, dtype=np.int32),
        np.array(edges_to, dtype=np.int32),
        np.array(edges_cost, dtype=np.float64),
        np.array(edges_len, dtype=np.float64),
        edges_geom
    )


def compute_centrality_metrics(graph: NetworkGraph, radius: float = None) -> dict:
    """Ağ üzerindeki düğüm ve kenarların Closeness ve Betweenness merkeziliklerini hesaplar."""
    n = graph.num_nodes
    reach = np.zeros(n, dtype=np.float64)
    farness = np.zeros(n, dtype=np.float64)
    closeness = np.zeros(n, dtype=np.float64)
    betweenness = np.zeros(graph.num_edges, dtype=np.float64)

    for s in range(n):
        dist, pred_node, pred_edge = graph.dijkstra_tree(s, cutoff=radius)
        mask = np.isfinite(dist)
        mask[s] = False
        r = int(mask.sum())
        reach[s] = r
        if r > 0:
            ds = dist[mask]
            farness[s] = float(ds.sum())
            closeness[s] = (r / farness[s]) * (r / max(1, n - 1))

        # Brandes yaklaşımıyla kenar yükü / betweenness akışı
        for t in np.where(mask)[0]:
            curr = t
            steps = 0
            while curr != s and curr != -1 and steps < 500:
                e = pred_edge[curr]
                if e != -1:
                    betweenness[e] += 1.0
                curr = pred_node[curr]
                steps += 1

    return {
        "node_closeness": closeness,
        "node_reach": reach,
        "edge_betweenness": betweenness
    }


def compute_road_slope_metrics(line_geom: QgsGeometry, dem_layer: QgsRasterLayer) -> dict:
    """DEM rasterından yol çizgisinin başlangıç/bitiş kotlarını alıp eğim yüzdesini hesaplar."""
    if not dem_layer or not dem_layer.isValid() or not line_geom or line_geom.isEmpty():
        return {"egim_yuzde": 0.0, "egim_sinifi": "Belirsiz", "z_min": 0.0, "z_max": 0.0}

    line_abstract = line_geom.constGet()
    if not line_abstract or line_abstract.numPoints() < 2:
        return {"egim_yuzde": 0.0, "egim_sinifi": "Belirsiz", "z_min": 0.0, "z_max": 0.0}

    p_start = QgsPointXY(line_abstract.startPoint().x(), line_abstract.startPoint().y())
    p_end = QgsPointXY(line_abstract.endPoint().x(), line_abstract.endPoint().y())

    val_start, ok1 = dem_layer.dataProvider().sample(p_start, 1)
    val_end, ok2 = dem_layer.dataProvider().sample(p_end, 1)

    if not ok1 or not ok2 or math.isnan(val_start) or math.isnan(val_end):
        return {"egim_yuzde": 0.0, "egim_sinifi": "Veri Dışı", "z_min": 0.0, "z_max": 0.0}

    length = max(0.5, line_geom.length())
    delta_z = abs(val_end - val_start)
    slope_pct = round((delta_z / length) * 100.0, 2)

    if slope_pct <= 4.0:
        cat = "Düz / Rahat (%0-4)"
    elif slope_pct <= 8.0:
        cat = "Hafif Eğimli (%5-8)"
    elif slope_pct <= 12.0:
        cat = "Orta Eğimli (%8-12)"
    elif slope_pct <= 16.0:
        cat = "Dik Yol (%12-16)"
    else:
        cat = "Çok Dik / Kritik (>%16)"

    return {
        "egim_yuzde": slope_pct,
        "egim_sinifi": cat,
        "z_min": min(val_start, val_end),
        "z_max": max(val_start, val_end),
        "delta_z": round(delta_z, 2)
    }
