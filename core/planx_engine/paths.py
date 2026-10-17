# -*- coding: utf-8 -*-
"""En kısa yol, OD matrisi ve çoklu kaynak Dijkstra algoritmaları.

PlanX Ulaşım ve Ağ Analiz Motoru
"""
from __future__ import annotations

import heapq
import numpy as np

from . import HAS_SCIPY

INF = float("inf")


def _to_scipy(indptr, adj, weights, n):
    from scipy.sparse import csr_matrix
    return csr_matrix((weights, adj, indptr), shape=(n, n))


def _heap_dijkstra(indptr, adj, weights, n, source, cutoff=None):
    dist = np.full(n, INF)
    dist[source] = 0.0
    heap = [(0.0, source)]
    while heap:
        d, u = heapq.heappop(heap)
        if d > dist[u]:
            continue
        for k in range(indptr[u], indptr[u + 1]):
            v = adj[k]
            nd = d + weights[k]
            if cutoff is not None and nd > cutoff:
                continue
            if nd < dist[v]:
                dist[v] = nd
                heapq.heappush(heap, (nd, v))
    return dist


def many_to_many(indptr, adj, weights, n, sources, cutoff=None, cancel=None):
    """Her kaynaktan tüm düğümlere olan en kısa mesafeler: (len(sources), n) dizisi."""
    sources = np.asarray(sources, dtype=np.int64)
    if HAS_SCIPY:
        from scipy.sparse import csgraph
        return csgraph.dijkstra(
            _to_scipy(indptr, adj, weights, n),
            directed=True, indices=sources,
            limit=INF if cutoff is None else float(cutoff),
        )
    out = np.empty((len(sources), n))
    for i, s in enumerate(sources):
        if cancel is not None and cancel():
            break
        out[i] = _heap_dijkstra(indptr, adj, weights, n, int(s), cutoff)
    return out


def multi_source(indptr, adj, weights, n, sources, cutoff=None):
    """Herhangi bir kaynaktan olan minimum maliyet ve en yakın kaynak indeksi."""
    sources = np.asarray(sources, dtype=np.int64)
    if HAS_SCIPY:
        from scipy.sparse import csgraph
        dist, _, src_node = csgraph.dijkstra(
            _to_scipy(indptr, adj, weights, n),
            directed=True, indices=sources, min_only=True,
            return_predecessors=True,
            limit=INF if cutoff is None else float(cutoff),
        )
        pos = {int(node): i for i, node in enumerate(sources)}
        label = np.array([pos.get(int(s), -1) for s in src_node], dtype=np.int64)
        label[~np.isfinite(dist)] = -1
        return dist, label

    dist = np.full(n, INF)
    label = np.full(n, -1, dtype=np.int64)
    heap = []
    for i, s in enumerate(sources):
        s = int(s)
        if dist[s] > 0.0:
            dist[s] = 0.0
            label[s] = i
            heap.append((0.0, s, i))
    heapq.heapify(heap)
    while heap:
        d, u, lab = heapq.heappop(heap)
        if d > dist[u]:
            continue
        for k in range(indptr[u], indptr[u + 1]):
            v = adj[k]
            nd = d + weights[k]
            if cutoff is not None and nd > cutoff:
                continue
            if nd < dist[v]:
                dist[v] = nd
                label[v] = lab
                heapq.heappush(heap, (nd, v, lab))
    return dist, label


def shortest_path_tree(indptr, adj_node, adj_edge, weights, n, source,
                       cutoff=None):
    """Dijkstra with predecessor tracking for route reconstruction."""
    dist = np.full(n, INF)
    pred_node = np.full(n, -1, dtype=np.int64)
    pred_edge = np.full(n, -1, dtype=np.int64)
    dist[source] = 0.0
    heap = [(0.0, source)]
    while heap:
        d, u = heapq.heappop(heap)
        if d > dist[u]:
            continue
        for k in range(indptr[u], indptr[u + 1]):
            v = adj_node[k]
            nd = d + weights[k]
            if cutoff is not None and nd > cutoff:
                continue
            if nd < dist[v]:
                dist[v] = nd
                pred_node[v] = u
                pred_edge[v] = adj_edge[k]
                heapq.heappush(heap, (nd, v))
    return dist, pred_node, pred_edge


def reconstruct_path(pred_node, pred_edge, source, target):
    """Walk predecessor arrays back from target to source."""
    if target == source:
        return [int(source)], []
    if pred_node[target] < 0:
        return [], []
    nodes = [int(target)]
    edges = []
    cur = int(target)
    while cur != source:
        edges.append(int(pred_edge[cur]))
        cur = int(pred_node[cur])
        nodes.append(cur)
        if len(nodes) > len(pred_node):
            return [], []
    nodes.reverse()
    edges.reverse()
    return nodes, edges


def multi_source_offset(indptr, adj, weights, n, sources, offsets, cutoff=None):
    """Min over sources of offset_s + path cost to every node."""
    sources = np.asarray(sources, dtype=np.int64)
    offsets = np.asarray(offsets, dtype=np.float64)
    dist = np.full(n, INF)
    label = np.full(n, -1, dtype=np.int64)
    heap = []
    for i, s in enumerate(sources):
        s = int(s)
        off = float(offsets[i])
        if not np.isfinite(off):
            continue
        if off < dist[s]:
            dist[s] = off
            label[s] = i
            heap.append((off, s, i))
    heapq.heapify(heap)
    while heap:
        d, u, lab = heapq.heappop(heap)
        if d > dist[u]:
            continue
        for k in range(indptr[u], indptr[u + 1]):
            v = adj[k]
            nd = d + weights[k]
            if cutoff is not None and nd > cutoff:
                continue
            if nd < dist[v]:
                dist[v] = nd
                label[v] = lab
                heapq.heappush(heap, (nd, v, lab))
    return dist, label


def shortest_path(indptr, adj_node, adj_edge, weights, n, source, target, cutoff=None):
    """Tek bir kaynak ve hedef arasındaki en kısa yolu (düğümler ve kenarlar) bulur."""
    source, target = int(source), int(target)
    if source == target:
        return [source], []
    dist, pred_node, pred_edge = shortest_path_tree(indptr, adj_node, adj_edge, weights, n, source, cutoff=cutoff)
    return reconstruct_path(pred_node, pred_edge, source, target)



def dijkstra_pruned(indptr, adj, w_cost, w_prune, n, source, radius):
    """Açısal maliyeti minimize ederken metrik yarıçapta budama (Space Syntax)."""
    cost = np.full(n, INF)
    prune = np.full(n, INF)
    cost[source] = 0.0
    prune[source] = 0.0
    heap = [(0.0, 0.0, source)]
    while heap:
        c, p, u = heapq.heappop(heap)
        if c > cost[u]:
            continue
        for k in range(indptr[u], indptr[u + 1]):
            v = adj[k]
            np_ = p + w_prune[k]
            if radius is not None and np_ > radius:
                continue
            nc = c + w_cost[k]
            if nc < cost[v]:
                cost[v] = nc
                prune[v] = np_
                heapq.heappush(heap, (nc, np_, v))
    return cost, prune
