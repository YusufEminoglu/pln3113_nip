# -*- coding: utf-8 -*-
"""Space Syntax: Segment Açısal Analizi (Angular Segment Analysis - NAIN & NACH).

Hillier & Iida (2005), Hillier, Yang & Turner (2012)
PlanX Ulaşım ve Ağ Analiz Motoru
"""
from __future__ import annotations

import numpy as np

from . import centrality

RADIUS_GLOBAL = "n"


def parse_radii(text: str):
    """'400, 800, 1200, n' metnini [400.0, 800.0, 1200.0, None] listesine dönüştürür."""
    radii = []
    for token in str(text).replace(";", ",").split(","):
        token = token.strip().lower()
        if not token:
            continue
        if token in ("n", "rn", "global", "inf"):
            radii.append(None)
        else:
            value = float(token)
            if value <= 0:
                raise ValueError(f"Yarıçap pozitif olmalıdır: {token}")
            radii.append(value)
    if not radii:
        radii = [None]
    return radii


def radius_label(radius) -> str:
    return RADIUS_GLOBAL if radius is None else f"{radius:g}"


def segment_angular_analysis(seg_graph, radius=None, cancel=None, progress=None):
    """Tek bir yarıçap için açısal segment analizi:
    nc (düğüm sayısı), td (toplam açısal derinlik), md (ortalama derinlik),
    nain (normalleştirilmiş entegrasyon), choice (seçim), nach (normalleştirilmiş seçim).
    """
    g = seg_graph
    node_bc, _, depth = centrality.brandes_betweenness(
        g.indptr, g.adj_seg, g.adj_ang, g.n,
        w_prune=g.adj_metric, radius=radius,
        cancel=cancel, progress=progress, collect_depth=True,
    )
    nc = depth["node_count"]
    td = depth["total_depth"]
    md = np.where(nc > 1, td / np.maximum(nc - 1, 1), 0.0)
    choice = node_bc / 2.0
    with np.errstate(divide="ignore", invalid="ignore"):
        nain = np.power(nc + 2.0, 1.2) / (td + 2.0)
        nach = np.log10(choice + 1.0) / np.log10(td + 3.0)
    nach = np.nan_to_num(nach, nan=0.0, posinf=0.0, neginf=0.0)
    nain = np.nan_to_num(nain, nan=0.0, posinf=0.0, neginf=0.0)
    return {"nc": nc, "td": td, "md": md, "nain": nain,
            "choice": choice, "nach": nach}
