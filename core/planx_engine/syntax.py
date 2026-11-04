# -*- coding: utf-8 -*-
"""Space syntax segment angular analysis.

Port of PlanX 4.23.0 ``engine/syntax.py`` (unchanged code; PLN3113 NİP keeps
its own import path). Against the pre-4.23.0 copy: choice on directed segment
ends (a dead end has choice 0), ``NAIN = NC**1.2 / (TD + 2)`` instead of
``(NC + 2)**1.2 / (TD + 2)``, a SciPy batch path for the global radius, and a
``cancelled`` flag in the result (callers must not write a cancelled result).

Implements the segment-map measures of Hillier & Iida (2005) and Turner
(2001, 2007) on the **directed** segment-end graph built by
:func:`engine.graphs.build_segment_graph`, as depthmapX does: a route that
enters a segment by one end can leave it only by the other, so it can never
back-track out of a cul-de-sac or U-turn through a side street to fake a
tie with the straight route.

* **Angular total depth / mean depth / integration** - least angular cost
  from a segment (either direction of travel) to every other segment,
  optionally limited to a metric radius (midpoint-to-midpoint length along
  the least-angle route).
* **Angular choice** - how many least-angle routes between pairs of
  segments pass through a segment; the end segments of a route are not
  counted (a dead end has choice 0). Tied routes share the pair equally.
* **NACH / NAIN** - the normalized measures of Hillier, Yang & Turner
  (2012, JOSS 3(2): 155-193): ``NACH = log10(CH + 1) / log10(TD + 3)`` and
  ``NAIN = NC ** 1.2 / (TD + 2)``. NC counts the origin segment.

One pass per radius yields both integration and choice. The global radius
uses SciPy (C Dijkstra plus one sparse triangular solve per origin for the
route counts) when it is installed; metric radii and SciPy-free hosts use an
exact pure-Python Brandes pass. Both give the same numbers.
"""
from __future__ import annotations

import heapq

import numpy as np

from . import HAS_SCIPY, Cancelled, centrality

RADIUS_GLOBAL = "n"
_EPS = 1e-9
# Angular costs at or below this are straight-on (zero) moves when ordering
# equal-depth states.
_ZERO = 1e-9
# Origins solved per SciPy Dijkstra call on the global radius.
_BATCH = 4


def parse_radii(text: str):
    """Parse a radii string like ``"400, 800, n"`` -> [400.0, 800.0, None]."""
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
                raise ValueError(f"Radius must be positive: {token}")
            radii.append(value)
    if not radii:
        radii = [None]
    return radii


def radius_label(radius) -> str:
    return RADIUS_GLOBAL if radius is None else f"{radius:g}"


def segment_angular_analysis(seg_graph, radius=None, cancel=None, progress=None):
    """Run one radius. Returns dict of per-segment arrays:
    ``nc`` (node count, origin included), ``td`` (angular total depth),
    ``md`` (mean depth), ``nain``, ``choice`` (pair-based: each unordered
    pair of segments shares one unit among its least-angle routes),
    ``nach``; plus ``cancelled`` (bool). When ``cancelled`` is True the
    arrays cover only the origins processed before ``cancel()`` fired and
    must not be written out as a result.

    A hand-made :class:`SegmentGraph` without the directed segment-end
    arrays falls back to the undirected dual graph.
    """
    g = seg_graph
    cancelled = False
    if getattr(g, "dir_indptr", None) is None:
        node_bc, _, depth = centrality.brandes_betweenness(
            g.indptr, g.adj_seg, g.adj_ang, g.n,
            w_prune=g.adj_metric, radius=radius,
            cancel=cancel, progress=progress, collect_depth=True,
        )
        nc = depth["node_count"]
        td = depth["total_depth"]
        cancelled = bool(cancel is not None and cancel())
    else:
        try:
            if radius is None and HAS_SCIPY and g.n > 1:
                nc, td, node_bc = _directed_global_scipy(g, cancel, progress)
            else:
                nc, td, node_bc = _directed_heap(g, radius, cancel, progress)
        except Cancelled as exc:
            nc, td, node_bc = exc.partial
            cancelled = True
    md = np.where(nc > 1, td / np.maximum(nc - 1, 1), 0.0)
    # Every origin is processed, so each unordered pair is counted twice.
    choice = node_bc / 2.0
    with np.errstate(divide="ignore", invalid="ignore"):
        nain = np.power(nc, 1.2) / (td + 2.0)
        nach = np.log10(choice + 1.0) / np.log10(td + 3.0)
    nach = np.nan_to_num(nach, nan=0.0, posinf=0.0, neginf=0.0)
    nain = np.nan_to_num(nain, nan=0.0, posinf=0.0, neginf=0.0)
    return {"nc": nc, "td": td, "md": md, "nain": nain,
            "choice": choice, "nach": nach, "cancelled": cancelled}


def _directed_heap(g, radius, cancel, progress):
    """Exact Brandes pass over the directed segment-end states.

    Each origin segment starts in both of its states at depth 0. A
    destination segment's depth is the smaller of its two state depths, and
    the routes that reach it are the least-angle routes into whichever of
    its states attains that depth. Dict state, so a metric radius touches
    only the segments inside it.
    """
    n = g.n
    indptr = g.dir_indptr.tolist()
    adj = g.dir_adj.tolist()
    ang = g.dir_ang.tolist()
    met = g.dir_metric.tolist()
    limited = radius is not None
    rad = float(radius) if limited else 0.0
    nc = np.zeros(n, dtype=np.float64)
    td = np.zeros(n, dtype=np.float64)
    bc = np.zeros(n, dtype=np.float64)
    # Equal-depth states pop in zero-move order, so a straight-on move is
    # never relaxed into a state that has already been settled.
    zr = _zero_rank(g)
    zr = [0] * (2 * n) if zr is None else zr.tolist()
    heappush, heappop = heapq.heappush, heapq.heappop
    for s in range(n):
        if cancel is not None and cancel():
            raise Cancelled((nc, td, bc))
        if progress is not None and s % 64 == 0:
            progress(s / max(1, n))
        s0, s1 = 2 * s, 2 * s + 1
        dist = {s0: 0.0, s1: 0.0}
        sigma = {s0: 1.0, s1: 1.0}
        preds = {s0: [], s1: []}
        done = set()
        order = []
        heap = [(0.0, zr[s0], 0.0, s0), (0.0, zr[s1], 0.0, s1)]
        while heap:
            d, _r, p, u = heappop(heap)
            if u in done:
                continue
            done.add(u)
            order.append(u)
            su = sigma[u]
            for k in range(indptr[u], indptr[u + 1]):
                v = adj[k]
                if v in done:
                    continue
                if limited:
                    np_ = p + met[k]
                    if np_ > rad:
                        continue
                else:
                    np_ = p
                nd = d + ang[k]
                old = dist.get(v)
                tol = _EPS * max(1.0, abs(nd))
                if old is None or nd < old - tol:
                    dist[v] = nd
                    sigma[v] = su
                    preds[v] = [u]
                    heappush(heap, (nd, zr[v], np_, v))
                elif abs(nd - old) <= tol:
                    sigma[v] += su
                    preds[v].append(u)
        best = {}
        for u in order:
            t = u >> 1
            du = dist[u]
            if t not in best or du < best[t]:
                best[t] = du
        nc[s] = len(best)
        td[s] = sum(best.values())
        # Share of the routes to segment t that end in state u.
        sig_t = {}
        terminal = []
        for u in order:
            t = u >> 1
            if t == s:
                continue
            bt = best[t]
            if dist[u] <= bt + _EPS * max(1.0, abs(bt)):
                sig_t[t] = sig_t.get(t, 0.0) + sigma[u]
                terminal.append(u)
        own = {u: sigma[u] / sig_t[u >> 1] for u in terminal}
        delta = dict.fromkeys(order, 0.0)
        for v in reversed(order):
            sv = sigma[v]
            coeff = (own.get(v, 0.0) + delta[v]) / sv if sv > 0 else 0.0
            for u in preds[v]:
                delta[u] += sigma[u] * coeff
            t = v >> 1
            if t != s:
                bc[t] += delta[v]
    if progress is not None:
        progress(1.0)
    return nc, td, bc


def _zero_rank(g):
    """Topological rank of every state in the sub-graph of straight-on
    (zero angular cost) moves, or None if that sub-graph has a cycle.

    Equal-depth states are ordered by it, so a zero-cost move always runs
    from an earlier to a later state in the per-origin ordering.
    """
    m = 2 * g.n
    src_all = np.repeat(np.arange(m, dtype=np.int64), np.diff(g.dir_indptr))
    zero = g.dir_ang <= _ZERO
    zs = src_all[zero]
    zd = g.dir_adj[zero].astype(np.int64)
    rank = np.zeros(m, dtype=np.int64)
    if len(zs) == 0:
        return rank
    indeg = np.bincount(zd, minlength=m).tolist()
    out_ptr = np.concatenate([[0], np.cumsum(np.bincount(zs, minlength=m))]).tolist()
    out_dst = zd[np.argsort(zs, kind="stable")].tolist()
    frontier = [u for u in range(m) if indeg[u] == 0]
    level = 0
    seen = 0
    while frontier:
        nxt = []
        for u in frontier:
            rank[u] = level
            seen += 1
            for k in range(out_ptr[u], out_ptr[u + 1]):
                v = out_dst[k]
                indeg[v] -= 1
                if indeg[v] == 0:
                    nxt.append(v)
        frontier = nxt
        level += 1
    return rank if seen == m else None


def _triangular_solver():
    """Return ``make(rows, cols, m) -> (solve_transposed, solve)`` for the
    unit upper-triangular ``I - T`` with ``T[rows, cols] = 1``.

    ``spsolve_triangular`` is compiled from SciPy 1.13 on and is several
    times faster than a sparse LU there; before that it loops in Python, so
    older hosts factorize with SuperLU in natural order (no fill-in on a
    triangular matrix). Same numbers either way.
    """
    import scipy
    from scipy.sparse import csc_matrix, csr_matrix
    from scipy.sparse.linalg import splu, spsolve_triangular

    def _version(text):
        out = []
        for part in str(text).split(".")[:2]:
            digits = "".join(ch for ch in part if ch.isdigit())
            out.append(int(digits or 0))
        return tuple(out)

    compiled = _version(scipy.__version__) >= (1, 13)

    def make(rows, cols, m):
        diag = np.arange(m, dtype=np.int64)
        vals = np.concatenate([np.ones(m), -np.ones(len(rows))])
        r = np.concatenate([diag, rows])
        c = np.concatenate([diag, cols])
        if compiled:
            upper = csr_matrix((vals, (r, c)), shape=(m, m))
            lower = csr_matrix((vals, (c, r)), shape=(m, m))
            return (lambda b: spsolve_triangular(lower, b, lower=True, unit_diagonal=True),
                    lambda b: spsolve_triangular(upper, b, lower=False, unit_diagonal=True))
        lu = splu(csc_matrix((vals, (r, c)), shape=(m, m)), permc_spec="NATURAL",
                  diag_pivot_thresh=0.0, options={"SymmetricMode": True})
        return (lambda b: lu.solve(b, trans="T")), lu.solve

    return make


def _directed_global_scipy(g, cancel, progress):
    """Global radius with SciPy: the numbers of :func:`_directed_heap`.

    Per batch of origins, ``csgraph.dijkstra`` gives every state's least
    angular depth (min over the origin's two starting states). The tight
    moves ``d[u] + w == d[v]`` form the least-angle route DAG; ordering the
    states by (depth, zero-move rank) makes it strictly upper triangular, so
    the route counts solve ``(I - T)^T sigma = e`` and the Brandes
    dependencies ``(I - T) x = own / sigma``. The whole batch is one
    block-diagonal system: two sparse triangular solves, all in C.
    """
    from scipy.sparse import csr_matrix, csgraph

    rank = _zero_rank(g)
    if rank is None:  # a zero-angle cycle: leave it to the exact heap pass
        return _directed_heap(g, None, cancel, progress)
    make_solver = _triangular_solver()
    n = g.n
    m = 2 * n
    e_src = np.repeat(np.arange(m, dtype=np.int64), np.diff(g.dir_indptr))
    e_dst = g.dir_adj.astype(np.int64)
    e_w = g.dir_ang.astype(np.float64)
    # Sparse routines may drop explicit zeros; the smallest subnormal is a
    # real edge yet adds nothing to any depth.
    W = csr_matrix((np.where(e_w > 0.0, e_w, 5e-324), g.dir_adj, g.dir_indptr),
                   shape=(m, m))
    seg_of = np.arange(m, dtype=np.int64) >> 1
    by_rank = np.argsort(rank, kind="stable")
    seg_dst = seg_of[e_dst]
    batch_size = int(max(1, min(_BATCH, 2000000 // max(1, len(e_w), m))))
    nc = np.zeros(n, dtype=np.float64)
    td = np.zeros(n, dtype=np.float64)
    bc = np.zeros(n, dtype=np.float64)
    for start in range(0, n, batch_size):
        if cancel is not None and cancel():
            raise Cancelled((nc, td, bc))
        if progress is not None:
            progress(start / float(n))
        src = np.arange(start, min(n, start + batch_size), dtype=np.int64)
        b = len(src)
        rows = np.arange(b, dtype=np.int64)
        idx = np.empty(2 * b, dtype=np.int64)
        idx[0::2] = 2 * src
        idx[1::2] = 2 * src + 1
        d = csgraph.dijkstra(W, directed=True, indices=idx)
        d = np.minimum(d[0::2], d[1::2])
        d[d < 1e-300] = 0.0  # subnormal stand-ins for straight moves
        d[rows, 2 * src] = 0.0
        d[rows, 2 * src + 1] = 0.0
        reached = np.isfinite(d)
        dseg = np.minimum(d[:, 0::2], d[:, 1::2])
        fin = np.isfinite(dseg)
        nc[src] = fin.sum(axis=1)
        td[src] = np.where(fin, dseg, 0.0).sum(axis=1)
        # Per-origin topological order: depth, then zero-move rank.
        order = by_rank[np.argsort(d[:, by_rank], axis=1, kind="stable")]
        pos = np.empty_like(order)
        np.put_along_axis(pos, order, np.broadcast_to(np.arange(m), (b, m)), axis=1)
        ds = d[:, e_src]
        nd = ds + e_w
        with np.errstate(invalid="ignore"):
            tight = (np.abs(nd - d[:, e_dst]) <= _EPS * np.maximum(1.0, np.abs(nd)))
        del ds, nd
        bi, ei = np.nonzero(tight)  # inf - inf is nan: unreached never tight
        del tight
        ps = pos[bi, e_src[ei]]
        pt = pos[bi, e_dst[ei]]
        keep = (ps < pt) & (seg_dst[ei] != src[bi])
        offset = bi[keep] * m
        solve_t, solve = make_solver(offset + ps[keep], offset + pt[keep], b * m)
        e = np.zeros((b, m))
        e[rows, pos[rows, 2 * src]] = 1.0
        e[rows, pos[rows, 2 * src + 1]] = 1.0
        sigma = np.empty((b, m))
        np.put_along_axis(sigma, order, solve_t(e.ravel()).reshape(b, m), axis=1)
        sigma[~reached] = 0.0
        # Terminal states: the ones attaining their segment's depth.
        dmin = dseg[:, seg_of]
        with np.errstate(invalid="ignore"):
            term = (reached & (seg_of[None, :] != src[:, None])
                    & (d <= dmin + _EPS * np.maximum(1.0, np.abs(dmin))))
        flat_seg = (rows[:, None] * n + seg_of[None, :])
        sig_t = np.bincount(flat_seg[term], weights=sigma[term], minlength=b * n)
        own = np.zeros((b, m))
        own[term] = sigma[term] / sig_t[flat_seg[term]]
        rhs = np.zeros((b, m))
        ok = sigma > 0
        rhs[ok] = own[ok] / sigma[ok]
        x = np.empty((b, m))
        np.put_along_axis(
            x, order, solve(np.take_along_axis(rhs, order, axis=1).ravel()).reshape(b, m), axis=1)
        delta = np.where(reached, sigma * x - own, 0.0)
        contrib = np.bincount(flat_seg.ravel(), weights=delta.ravel(),
                              minlength=b * n).reshape(b, n)
        contrib[rows, src] = 0.0
        bc += contrib.sum(axis=0)
    if progress is not None:
        progress(1.0)
    return nc, td, bc


def _r_squared(x, y):
    """Squared Pearson correlation over the finite pairs, None when undefined."""
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 3:
        return None
    x, y = x[ok], y[ok]
    if x.std() == 0.0 or y.std() == 0.0:
        return None
    r = float(np.corrcoef(x, y)[0, 1])
    return r * r


def intelligibility_synergy(connectivity, nain_by_radius):
    """Hillier's two whole-map summaries of a segment analysis.

    ``nain_by_radius`` maps a radius (None = global) to that radius's NAIN.

    * **Intelligibility** (Hillier et al. 1987; Hillier 1996): r-squared of
      connectivity against integration at the widest radius - how well what
      a person sees from a segment (its immediate connections) predicts how
      the segment sits in the whole. A legible grid scores high; a labyrinth
      of similar-looking junctions scores low.
    * **Synergy**: r-squared of local integration (the smallest radius)
      against the widest - whether the local and the city-wide structure
      agree, i.e. whether the neighbourhood centres lie on the city's
      through routes.

    Returns ``{"intelligibility": float|None, "synergy": float|None,
    "global_radius": r, "local_radius": r}``; synergy is None with fewer than
    two radii. Computed on segments, so the values are not comparable with
    axial-map figures from the older literature.
    """
    if not nain_by_radius:
        return {"intelligibility": None, "synergy": None,
                "global_radius": None, "local_radius": None}
    radii = list(nain_by_radius)
    finite = sorted(r for r in radii if r is not None)
    widest = None if None in radii else finite[-1]
    smallest = finite[0] if finite else None
    out = {"global_radius": widest, "local_radius": smallest,
           "intelligibility": _r_squared(connectivity, nain_by_radius[widest]),
           "synergy": None}
    if len(radii) >= 2 and smallest is not None and smallest != widest:
        out["synergy"] = _r_squared(nain_by_radius[smallest], nain_by_radius[widest])
    return out
