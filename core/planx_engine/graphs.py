# -*- coding: utf-8 -*-
"""Çizgi geometrilerinden graf modelleri (Primal NodeGraph ve Dual SegmentGraph).

PlanX Ulaşım ve Ağ Analiz Motoru
"""
from __future__ import annotations

import contextlib
import math
import numpy as np


class NodeGraph:
    """Kavşakların düğüm, yol akslarının kenar olduğu Primal Graf modeli."""

    __slots__ = ("node_xy", "edge_from", "edge_to", "edge_cost", "edge_rev_cost", "edge_direction", "edge_len",
                 "indptr", "adj_node", "adj_edge", "adj_cost")

    def __init__(self, node_xy, edge_from, edge_to, edge_cost, edge_len,
                 reverse_cost=None, directions=None):
        self.node_xy = node_xy
        self.edge_from = edge_from
        self.edge_to = edge_to
        self.edge_cost = edge_cost
        self.edge_rev_cost = np.asarray(reverse_cost if reverse_cost is not None else edge_cost, dtype=np.float64)
        self.edge_direction = np.asarray(directions if directions is not None else np.zeros(len(edge_from)), dtype=np.int8)
        self.edge_len = edge_len
        self._build_csr()

    @property
    def num_nodes(self) -> int:
        return len(self.node_xy)

    @property
    def num_edges(self) -> int:
        return len(self.edge_from)

    def _build_csr(self):
        n = self.num_nodes
        forward = self.edge_direction >= 0
        reverse = self.edge_direction <= 0
        src = np.concatenate([self.edge_from[forward], self.edge_to[reverse]])
        dst = np.concatenate([self.edge_to[forward], self.edge_from[reverse]])
        edge_ids = np.arange(self.num_edges)
        eid = np.concatenate([edge_ids[forward], edge_ids[reverse]])
        cost = np.concatenate([self.edge_cost[forward], self.edge_rev_cost[reverse]])
        order = np.argsort(src, kind="stable")
        src, dst, eid, cost = src[order], dst[order], eid[order], cost[order]
        counts = np.bincount(src, minlength=n)
        self.indptr = np.concatenate([[0], np.cumsum(counts)]).astype(np.int64)
        self.adj_node = dst.astype(np.int32)
        self.adj_edge = eid.astype(np.int32)
        self.adj_cost = cost.astype(np.float64)

    def degrees(self) -> np.ndarray:
        return np.diff(self.indptr).astype(np.int32)


def polyline_length(coords: np.ndarray) -> float:
    d = np.diff(coords, axis=0)
    return float(np.hypot(d[:, 0], d[:, 1]).sum())


def build_node_graph(polylines, tolerance: float = 0.01, costs=None,
                     reverse_costs=None, directions=None) -> NodeGraph:
    """Polylines dizisinden primal graf inşa eder."""
    node_index = {}
    node_pts = []

    def node_id(pt):
        key = (round(pt[0] / tolerance), round(pt[1] / tolerance))
        idx = node_index.get(key)
        if idx is None:
            idx = len(node_pts)
            node_index[key] = idx
            node_pts.append((float(pt[0]), float(pt[1])))
        return idx

    e_from, e_to, e_len = [], [], []
    for coords in polylines:
        e_from.append(node_id(coords[0]))
        e_to.append(node_id(coords[-1]))
        e_len.append(polyline_length(coords))

    node_xy = np.asarray(node_pts, dtype=np.float64)
    edge_from = np.asarray(e_from, dtype=np.int32)
    edge_to = np.asarray(e_to, dtype=np.int32)
    edge_len = np.asarray(e_len, dtype=np.float64)
    edge_cost = edge_len.copy() if costs is None else np.asarray(costs, dtype=np.float64)

    return NodeGraph(node_xy, edge_from, edge_to, edge_cost, edge_len,
                     reverse_cost=reverse_costs, directions=directions)


def nearest_nodes(graph: NodeGraph, points: np.ndarray) -> np.ndarray:
    """Noktaları (M, 2) en yakın graf düğümüne eşler (int32 düğüm ID'leri)."""
    pts = np.asarray(points, dtype=np.float64)
    with contextlib.suppress(Exception):
        from scipy.spatial import cKDTree
        _, idx = cKDTree(graph.node_xy).query(pts)
        return idx.astype(np.int32)

    out = np.empty(len(pts), dtype=np.int32)
    nodes = graph.node_xy
    for i, p in enumerate(pts):
        d2 = (nodes[:, 0] - p[0]) ** 2 + (nodes[:, 1] - p[1]) ** 2
        out[i] = int(np.argmin(d2))
    return out


# --------------------------------------------------------------------------- #
# Space Syntax Dual (Segment) Graf Modeli
# --------------------------------------------------------------------------- #
class SegmentGraph:
    """Segmentlerin düğüm, dönüş açılarının maliyet olduğu Dual Graf modeli."""

    __slots__ = ("n", "seg_len", "seg_curve", "connectivity",
                 "indptr", "adj_seg", "adj_ang", "adj_metric")

    def __init__(self, n, seg_len, seg_curve, indptr, adj_seg, adj_ang, adj_metric):
        self.n = n
        self.seg_len = seg_len
        self.seg_curve = seg_curve
        self.indptr = indptr
        self.adj_seg = adj_seg
        self.adj_ang = adj_ang
        self.adj_metric = adj_metric
        counts = np.zeros(n, dtype=np.int32)
        for s in range(n):
            counts[s] = len(set(adj_seg[indptr[s]:indptr[s + 1]].tolist()))
        self.connectivity = counts


def _bearing(p0, p1) -> float:
    return math.degrees(math.atan2(p1[1] - p0[1], p1[0] - p0[0]))


def _ang_diff(a: float, b: float) -> float:
    d = abs(a - b) % 360.0
    return 360.0 - d if d > 180.0 else d


def internal_curvature_deg(coords: np.ndarray) -> float:
    if len(coords) < 3:
        return 0.0
    total = 0.0
    prev = _bearing(coords[0], coords[1])
    for i in range(1, len(coords) - 1):
        cur = _bearing(coords[i], coords[i + 1])
        total += _ang_diff(prev, cur)
        prev = cur
    return total


def build_segment_graph(polylines, tolerance: float = 0.01) -> SegmentGraph:
    """Açısal Space Syntax için segment dual grafı inşa eder (Hillier & Iida 2005)."""
    def node_key(pt):
        return (round(pt[0] / tolerance), round(pt[1] / tolerance))

    ends = {}
    n = len(polylines)
    seg_len = np.empty(n, dtype=np.float64)
    seg_curve = np.empty(n, dtype=np.float64)
    for s, coords in enumerate(polylines):
        seg_len[s] = polyline_length(coords)
        seg_curve[s] = internal_curvature_deg(coords) / 90.0
        for pt, nxt in ((coords[0], coords[1]), (coords[-1], coords[-2])):
            key = node_key(pt)
            ends.setdefault(key, []).append((s, _bearing(pt, nxt)))

    src, dst, ang, metric = [], [], [], []
    for incident in ends.values():
        m = len(incident)
        if m < 2:
            continue
        for i in range(m):
            s, bs = incident[i]
            for j in range(i + 1, m):
                t, bt = incident[j]
                if s == t:
                    continue
                turn = _ang_diff(bs + 180.0, bt) / 90.0
                cost_ang = turn + 0.5 * (seg_curve[s] + seg_curve[t])
                cost_met = 0.5 * (seg_len[s] + seg_len[t])
                src.extend((s, t))
                dst.extend((t, s))
                ang.extend((cost_ang, cost_ang))
                metric.extend((cost_met, cost_met))

    src = np.asarray(src, dtype=np.int64)
    order = np.argsort(src, kind="stable")
    counts = np.bincount(src, minlength=n)
    indptr = np.concatenate([[0], np.cumsum(counts)]).astype(np.int64)
    return SegmentGraph(
        n,
        seg_len,
        seg_curve,
        indptr,
        np.asarray(dst, dtype=np.int32)[order],
        np.asarray(ang, dtype=np.float64)[order],
        np.asarray(metric, dtype=np.float64)[order],
    )
