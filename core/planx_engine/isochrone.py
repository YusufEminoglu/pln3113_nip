# -*- coding: utf-8 -*-
"""Hassas yol ağı izokronları ve kısmi kenar kırpma hesaplayıcı.

PlanX Ulaşım ve Ağ Analiz Motoru
"""
from __future__ import annotations

import numpy as np

EPS = 1e-9


def reach_fractions(dist_a, dist_b, edge_cost, cutoff,
                    reverse_cost=None, directions=None):
    """Maliyet limiti içinde her kenarın iki ucundan ulaşılan kesirlerini (t in [0, 1]) hesaplar."""
    dist_a = np.asarray(dist_a, dtype=np.float64)
    dist_b = np.asarray(dist_b, dtype=np.float64)
    cost = np.maximum(np.asarray(edge_cost, dtype=np.float64), EPS)
    reverse = (cost if reverse_cost is None else
               np.maximum(np.asarray(reverse_cost, dtype=np.float64), EPS))
    direction = (np.zeros(len(cost), dtype=np.int8) if directions is None
                 else np.asarray(directions, dtype=np.int8))
    with np.errstate(invalid="ignore"):
        fa = (cutoff - dist_a) / cost
        fb = (cutoff - dist_b) / reverse
    fa = np.clip(np.nan_to_num(fa, nan=-1.0, posinf=-1.0, neginf=-1.0), 0.0, 1.0)
    fb = np.clip(np.nan_to_num(fb, nan=-1.0, posinf=-1.0, neginf=-1.0), 0.0, 1.0)
    fa = np.where(direction >= 0, fa, 0.0)
    fb = np.where(direction <= 0, fb, 0.0)
    full = fa + fb >= 1.0 - EPS
    return full, fa, fb


def edge_intervals(full, fa, fb):
    """Bir kenarın ulaşılan [lo, hi] aralıklarını döndürür."""
    if full:
        return [(0.0, 1.0)]
    iv = []
    if fa > EPS:
        iv.append((0.0, float(fa)))
    if fb > EPS:
        iv.append((1.0 - float(fb), 1.0))
    return iv


def merge_intervals(intervals):
    """Aralıkların birleşimini hesaplar."""
    clean = []
    for lo, hi in intervals:
        lo, hi = max(0.0, float(lo)), min(1.0, float(hi))
        if hi - lo > EPS:
            clean.append((lo, hi))
    if not clean:
        return []
    clean.sort()
    out = [list(clean[0])]
    for lo, hi in clean[1:]:
        if lo <= out[-1][1] + EPS:
            out[-1][1] = max(out[-1][1], hi)
        else:
            out.append([lo, hi])
    return [(lo, hi) for lo, hi in out]


def subtract_intervals(a, b):
    """İki aralık listesinin farkını (a - b) hesaplar."""
    if not a:
        return []
    if not b:
        return list(a)
    out = []
    for lo, hi in a:
        pieces = [(lo, hi)]
        for blo, bhi in b:
            nxt = []
            for plo, phi in pieces:
                if bhi <= plo + EPS or blo >= phi - EPS:
                    nxt.append((plo, phi))
                    continue
                if blo > plo + EPS:
                    nxt.append((plo, min(blo, phi)))
                if bhi < phi - EPS:
                    nxt.append((max(bhi, plo), phi))
            pieces = nxt
            if not pieces:
                break
        out.extend(p for p in pieces if p[1] - p[0] > EPS)
    return out


def interval_length(intervals):
    """Kapsanan toplam kesir uzunluğunu verir."""
    return float(sum(hi - lo for lo, hi in intervals))


def _cumlen(coords):
    seg = np.diff(coords, axis=0)
    return np.concatenate([[0.0], np.cumsum(np.hypot(seg[:, 0], seg[:, 1]))])


def point_at(coords, t):
    """(k, 2) polyline üzerinde t yay-uzunluğu kesrindeki noktayı döndürür."""
    coords = np.asarray(coords, dtype=np.float64)
    cum = _cumlen(coords)
    total = cum[-1]
    if total <= EPS:
        return coords[0].copy()
    s = min(max(float(t), 0.0), 1.0) * total
    i = int(np.searchsorted(cum, s, side="right")) - 1
    i = min(max(i, 0), len(coords) - 2)
    seg_len = cum[i + 1] - cum[i]
    u = 0.0 if seg_len <= EPS else (s - cum[i]) / seg_len
    return coords[i] + u * (coords[i + 1] - coords[i])


def cut_polyline(coords, t0, t1):
    """t0 < t1 yay-uzunluğu kesirleri arasındaki alt çizgiyi (polyline) döndürür."""
    coords = np.asarray(coords, dtype=np.float64)
    cum = _cumlen(coords)
    total = cum[-1]
    t0, t1 = max(0.0, float(t0)), min(1.0, float(t1))
    if total <= EPS or t1 - t0 <= EPS:
        return None
    s0, s1 = t0 * total, t1 * total
    pts = [point_at(coords, t0)]
    inside = (cum > s0 + EPS) & (cum < s1 - EPS)
    for i in np.nonzero(inside)[0]:
        pts.append(coords[i])
    pts.append(point_at(coords, t1))
    out = np.asarray(pts, dtype=np.float64)
    keep = [0]
    for i in range(1, len(out)):
        if np.hypot(*(out[i] - out[keep[-1]])) > EPS:
            keep.append(i)
    if len(keep) < 2:
        return None
    return out[keep]


def entry_interval(t0, snap_cost, edge_cost, cutoff, reverse_cost=None,
                   direction=0):
    """Kenar üzerindeki bir giriş noktasının doğrudan erişebildiği aralık."""
    budget = float(cutoff) - float(snap_cost)
    if budget <= EPS:
        return None
    forward_span = budget / max(float(edge_cost), EPS)
    reverse_span = budget / max(
        float(edge_cost if reverse_cost is None else reverse_cost), EPS)
    lo = t0 if direction > 0 else max(0.0, t0 - reverse_span)
    hi = t0 if direction < 0 else min(1.0, t0 + forward_span)
    if hi - lo <= EPS:
        return None
    return (lo, hi)


def reach_intervals(dist, edge_from, edge_to, edge_cost, cutoff, entries=None,
                    reverse_cost=None, directions=None):
    """Belirli bir eşikte (cutoff) her kenarın erişilen aralıklarını döndürür."""
    full, fa, fb = reach_fractions(
        dist[edge_from], dist[edge_to], edge_cost, cutoff,
        reverse_cost=reverse_cost, directions=directions)
    out = {}
    touched = np.nonzero(full | (fa > EPS) | (fb > EPS))[0]
    for e in touched:
        out[int(e)] = edge_intervals(bool(full[e]), float(fa[e]), float(fb[e]))
    if entries:
        extra = {}
        for e, t0, snap in entries:
            reverse = edge_cost[e] if reverse_cost is None else reverse_cost[e]
            direction = 0 if directions is None else directions[e]
            piece = entry_interval(
                t0, snap, edge_cost[e], cutoff,
                reverse_cost=reverse, direction=direction)
            if piece is not None:
                extra.setdefault(int(e), []).append(piece)
        for e, pieces in extra.items():
            out[e] = merge_intervals(out.get(e, []) + pieces)
    return out
