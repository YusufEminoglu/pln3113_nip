# -*- coding: utf-8 -*-
"""Value tests for the PlanX 4.23.0 engine port and the network tools (1.2.0).

Run offscreen with a QGIS Python from the monorepo root:

    python -m unittest pln3113_nip.tests.test_engine_values

Covers: the auditor's T-junction fixture (NAIN, choice, NACH equal to PlanX
4.23.0), dead-end choice 0, the re-derived scenario thresholds, cancel (no
partial arrays written), NULL/zero costs refused, ground-metre radii and
breaks, feet CRSs refused, no sub-millimetre service-area pieces, deterministic sampling.
"""
from __future__ import annotations

import math
import os
import shutil
import tempfile
import unittest

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from qgis.core import (  # noqa: E402
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransformContext,
    QgsDistanceArea,
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsPointXY,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsVectorLayer,
)

_APP = None


def setUpModule():
    global _APP
    if QgsApplication.instance() is None:
        _APP = QgsApplication([], False)
        _APP.initQgis()
    import sys
    plugins_dir = os.path.join(QgsApplication.prefixPath(), "python", "plugins")
    if plugins_dir not in sys.path:
        sys.path.append(plugins_dir)
    from processing.core.Processing import Processing
    Processing.initialize()


def _seg(a, b):
    return np.array([a, b], dtype=float)


#: The auditor's fixture (NIP-AUDIT verify1.py): T junction with a straight
#: through route A-B, a side street C, and a dead end D beyond B.
T_FIXTURE = [_seg((0, 0), (100, 0)), _seg((100, 0), (200, 0)),
             _seg((100, 0), (100, 100)), _seg((200, 0), (300, 0))]


def _engine():
    from pln3113_nip.core.planx_engine import graphs, syntax
    return graphs, syntax


def _line_layer(crs, lines, fields=(), values=None):
    lyr = QgsVectorLayer(f"LineString?crs={crs}", "net", "memory")
    pr = lyr.dataProvider()
    if fields:
        pr.addAttributes([QgsField(name, vtype) for name, vtype in fields])
        lyr.updateFields()
    feats = []
    for i, coords in enumerate(lines):
        f = QgsFeature(lyr.fields())
        f.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(float(x), float(y)) for x, y in coords]))
        if values is not None:
            f.setAttributes(list(values[i]))
        feats.append(f)
    pr.addFeatures(feats)
    lyr.updateExtents()
    return lyr


def _point_layer(crs, pts):
    lyr = QgsVectorLayer(f"Point?crs={crs}", "pts", "memory")
    feats = []
    for x, y in pts:
        f = QgsFeature()
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
        feats.append(f)
    lyr.dataProvider().addFeatures(feats)
    lyr.updateExtents()
    return lyr


class _Result(dict):
    """processing.run results with layer outputs resolved to layers."""


def _run(alg, params, feedback=None):
    import processing
    from qgis.core import QgsProcessingContext, QgsProcessingUtils
    ctx = QgsProcessingContext()
    res = processing.run(alg, params, context=ctx, feedback=feedback or QgsProcessingFeedback())
    out = _Result()
    out.context = ctx  # keeps the temporary layers alive
    for key, value in res.items():
        if isinstance(value, str):
            layer = QgsProcessingUtils.mapLayerFromString(value, ctx)
            out[key] = layer if layer is not None else value
        else:
            out[key] = value
    return out


class LateCancel(QgsProcessingFeedback):
    """Reports "cancelled" from the ``after``-th poll on (mid-run cancel)."""

    def __init__(self, after):
        super().__init__()
        self.after = after
        self.polls = 0

    def isCanceled(self):  # noqa: N802 - Qt API name
        self.polls += 1
        return self.polls > self.after


# --------------------------------------------------------------------------- #
class TestAuditorFixture(unittest.TestCase):
    """NAIN, choice, NACH on the T junction equal PlanX 4.23.0."""

    # PlanX 4.23.0 on this fixture: NC = 4 everywhere, TD = [1, 1, 3, 1],
    # choice = [0, 2, 0, 0] (only B lies between other segments; the dead end
    # D and the ends A, C carry no through route).
    NC = [4.0, 4.0, 4.0, 4.0]
    TD = [1.0, 1.0, 3.0, 1.0]
    CHOICE = [0.0, 2.0, 0.0, 0.0]

    def _expected(self):
        nain = [nc ** 1.2 / (td + 2.0) for nc, td in zip(self.NC, self.TD)]
        nach = [math.log10(ch + 1.0) / math.log10(td + 3.0) for ch, td in zip(self.CHOICE, self.TD)]
        return nain, nach

    def _check(self, res):
        nain, nach = self._expected()
        np.testing.assert_allclose(res["nc"], self.NC, atol=1e-9)
        np.testing.assert_allclose(res["td"], self.TD, atol=1e-9)
        np.testing.assert_allclose(res["choice"], self.CHOICE, atol=1e-9)
        np.testing.assert_allclose(res["nain"], nain, atol=1e-9)
        np.testing.assert_allclose(res["nach"], nach, atol=1e-9)
        # The audit's rounded PlanX 4.23.0 print-out.
        np.testing.assert_allclose(np.round(res["nain"], 4), [1.7593, 1.7593, 1.0556, 1.7593])
        np.testing.assert_allclose(np.round(res["nach"], 4), [0.0, 0.7925, 0.0, 0.0])

    def test_global_radius(self):
        graphs, syntax = _engine()
        self._check(syntax.segment_angular_analysis(graphs.build_segment_graph(T_FIXTURE), None))

    def test_metric_radius_heap_path_same_numbers(self):
        graphs, syntax = _engine()
        self._check(syntax.segment_angular_analysis(graphs.build_segment_graph(T_FIXTURE), 1e9))

    def test_equals_planx_when_available(self):
        try:
            from planx.engine import graphs as pg, syntax as ps
        except ImportError:
            self.skipTest("PlanX is not next to the plugin (monorepo only)")
        graphs, syntax = _engine()
        mine = syntax.segment_angular_analysis(graphs.build_segment_graph(T_FIXTURE), None)
        ref = ps.segment_angular_analysis(pg.build_segment_graph(T_FIXTURE), None)
        for key in ("nc", "td", "nain", "choice", "nach"):
            np.testing.assert_allclose(mine[key], ref[key], atol=1e-12, err_msg=key)


class TestDeadEndChoice(unittest.TestCase):
    """A segment that is a dead end can never lie between two others."""

    def test_dead_ends_have_zero_choice(self):
        graphs, syntax = _engine()
        # 2x2 grid of 100 m blocks plus two cul-de-sacs off its edges.
        lines = []
        for i in range(3):
            for j in range(2):
                lines.append(_seg((i * 100, j * 100), (i * 100, (j + 1) * 100)))
                lines.append(_seg((j * 100, i * 100), ((j + 1) * 100, i * 100)))
        lines.append(_seg((200, 100), (260, 100)))   # stub east
        lines.append(_seg((100, 200), (100, 250)))   # stub north
        g = graphs.build_segment_graph(lines)
        for radius in (None, 300.0):
            res = syntax.segment_angular_analysis(g, radius)
            dead = [len(lines) - 2, len(lines) - 1]   # the two stubs
            np.testing.assert_allclose(res["choice"][dead], 0.0, atol=1e-12)
            np.testing.assert_allclose(res["nach"][dead], 0.0, atol=1e-12)
            self.assertTrue((res["choice"][:-2] > 0).any())


class TestScenarioThresholds(unittest.TestCase):
    """Thresholds re-derived for the 4.23.0 scale (see alg_scenario_compare)."""

    @staticmethod
    def _grid(nx, ny, size, skip=()):
        out = []
        for i in range(nx + 1):
            for j in range(ny):
                if ("v", i, j) not in skip:
                    out.append(_seg((i * size, j * size), (i * size, (j + 1) * size)))
        for j in range(ny + 1):
            for i in range(nx):
                if ("h", i, j) not in skip:
                    out.append(_seg((i * size, j * size), ((i + 1) * size, j * size)))
        return out

    @classmethod
    def _pairs(cls):
        size = 120.0
        nx, ny, every = 9, 6, 3

        def horizontals(feet):
            out = []
            for j in range(ny + 1):
                for i in range(nx):
                    x0, x1, y = i * size, (i + 1) * size, j * size
                    if (i, j) in feet:
                        out += [_seg((x0, y), ((x0 + x1) / 2, y)), _seg(((x0 + x1) / 2, y), (x1, y))]
                    else:
                        out.append(_seg((x0, y), (x1, y)))
            for i in range(nx + 1):
                for j in range(ny):
                    out.append(_seg((i * size, j * size), (i * size, (j + 1) * size)))
            return out

        marked = [(i, j) for i in range(nx) for j in range(ny) if (i + 2 * j) % every == 0]
        stubs = [_seg((i * size + size / 2, j * size), (i * size + size / 2, j * size + 0.6 * size))
                 for i, j in marked]
        tails = [_seg((i * size + size / 2, j * size + 0.6 * size), (i * size + size / 2, (j + 1) * size))
                 for i, j in marked]
        through = []
        for s, t in zip(stubs, tails):
            through += [s, t]
        diag = [_seg((k * 100.0, k * 100.0), ((k + 1) * 100.0, (k + 1) * 100.0)) for k in range(10)]
        return [
            (cls._grid(10, 10, 100.0), cls._grid(10, 10, 100.0) + diag),
            (horizontals(set(marked)) + stubs,
             horizontals(set(marked) | {(i, j + 1) for i, j in marked}) + through),
            (cls._grid(8, 8, 90.0),
             cls._grid(8, 8, 90.0, skip={("v", 4, 3), ("v", 4, 4), ("h", 3, 4), ("h", 4, 4)})),
        ]

    def test_constants(self):
        from pln3113_nip.algorithms import alg_scenario_compare as sc
        self.assertEqual(sc.DELTA_NACH_THRESHOLD, 0.077)
        self.assertEqual(sc.DELTA_NAIN_THRESHOLD, 0.047)
        self.assertEqual(sc.NEW_ROAD_NACH_THRESHOLD, 0.734)
        self.assertEqual(sc.NEW_ROAD_NAIN_THRESHOLD, 0.391)

    def test_derivation_reproduces(self):
        """New-engine values at the old thresholds' percentiles (R = 800 m)."""
        from pln3113_nip.algorithms import alg_scenario_compare as sc
        graphs, syntax = _engine()
        d_nach, d_nain, b_nach = [], [], []
        for a_lines, b_lines in self._pairs():
            ra = syntax.segment_angular_analysis(graphs.build_segment_graph(a_lines), 800.0)
            rb = syntax.segment_angular_analysis(graphs.build_segment_graph(b_lines), 800.0)
            ma = np.array([p[len(p) // 2] for p in a_lines])
            for j, p in enumerate(b_lines):
                mid = p[len(p) // 2]
                dist = np.hypot(ma[:, 0] - mid[0], ma[:, 1] - mid[1])
                i = int(np.argmin(dist))
                if dist[i] <= sc.SNAP_TOLERANCE_M:
                    d_nach.append(abs(rb["nach"][j] - ra["nach"][i]))
                    d_nain.append(abs(rb["nain"][j] - ra["nain"][i]))
            b_nach += list(rb["nach"])
        self.assertEqual(len(d_nach), 529)
        self.assertEqual(len(b_nach), 565)
        # Percentiles the 1.1.6 thresholds held on the 1.1.6 engine.
        self.assertAlmostEqual(float(np.quantile(d_nach, 0.777)), sc.DELTA_NACH_THRESHOLD, delta=0.0015)
        self.assertAlmostEqual(float(np.quantile(d_nain, 0.382)), sc.DELTA_NAIN_THRESHOLD, delta=0.0015)
        self.assertAlmostEqual(float(np.quantile(b_nach, 0.005)), sc.NEW_ROAD_NACH_THRESHOLD, delta=0.0015)
        # NAIN_B: exact scale relation at NC = 104.
        self.assertAlmostEqual(0.4 * (104.0 / 106.0) ** 1.2, sc.NEW_ROAD_NAIN_THRESHOLD, delta=0.0005)

    def test_classification_boundaries(self):
        from pln3113_nip.algorithms import alg_scenario_compare as sc
        self.assertEqual(sc.classify_matched(0.078, 0.0)[1], sc.DECISION_UPGRADE)
        self.assertEqual(sc.classify_matched(0.0, 0.048)[1], sc.DECISION_UPGRADE)
        self.assertEqual(sc.classify_matched(-0.078, 0.0)[1], sc.DECISION_CALM)
        self.assertEqual(sc.classify_matched(0.0, -0.048)[1], sc.DECISION_CALM)
        self.assertEqual(sc.classify_matched(0.076, -0.046)[1], "Mevcut Karakter Korunacak")
        self.assertTrue(sc.classify_new_road(0.0, 0.3).startswith("İşlemeyen"))  # dead-end proposal
        self.assertTrue(sc.classify_new_road(0.733, 0.390).startswith("İşlemeyen"))
        self.assertEqual(sc.classify_new_road(0.735, 0.390), "Stratejik Yeni Bağlantı Aksı")
        self.assertEqual(sc.classify_new_road(0.5, 0.392), "Stratejik Yeni Bağlantı Aksı")


class TestCancel(unittest.TestCase):
    """Cancel raises; nothing is written."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="nipeng-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_engine_flags_cancel(self):
        graphs, syntax = _engine()
        g = graphs.build_segment_graph(T_FIXTURE)
        for radius in (None, 500.0):
            res = syntax.segment_angular_analysis(g, radius, cancel=lambda: True)
            self.assertTrue(res.get("cancelled"), radius)

    def test_paths_raise_cancelled(self):
        from pln3113_nip.core.planx_engine import Cancelled, graphs, paths
        g = graphs.build_node_graph(T_FIXTURE)
        with self.assertRaises(Cancelled) as ctx:
            paths.many_to_many(g.indptr, g.adj_node, g.adj_cost, g.num_nodes,
                               [0, 1, 2], cancel=lambda: True)
        self.assertTrue(np.isinf(ctx.exception.partial).all())

    def _grid_layer(self, n=6, size=100.0):
        lines = []
        for i in range(n + 1):
            for j in range(n):
                lines.append(_seg((500000 + i * size, 4200000 + j * size), (500000 + i * size, 4200000 + (j + 1) * size)))
                lines.append(_seg((500000 + j * size, 4200000 + i * size), (500000 + (j + 1) * size, 4200000 + i * size)))
        return _line_layer("EPSG:5253", lines)

    def test_space_syntax_cancel_mid_run_writes_nothing(self):
        from pln3113_nip.algorithms.alg_space_syntax import SpaceSyntaxAlgorithm
        net = self._grid_layer()
        for after in (0, 5):
            out = os.path.join(self.tmp, f"ss_{after}.gpkg")
            with self.assertRaises(QgsProcessingException):
                _run(SpaceSyntaxAlgorithm(), {"NETWORK": net, "RADII": "400, n", "OUTPUT": out},
                     LateCancel(after))
            self.assertFalse(os.path.exists(out), f"partial output written (after={after})")

    def test_scenario_cancel_writes_nothing(self):
        from pln3113_nip.algorithms.alg_scenario_compare import ScenarioCompareAlgorithm
        net = self._grid_layer()
        out_d = os.path.join(self.tmp, "diff.gpkg")
        out_s = os.path.join(self.tmp, "sum.gpkg")
        with self.assertRaises(QgsProcessingException):
            _run(ScenarioCompareAlgorithm(), {"NETWORK_A": net, "NETWORK_B": net, "RADIUS": 800.0,
                                              "DIFF_NETWORK": out_d, "SUMMARY_TABLE": out_s},
                 LateCancel(3))
        self.assertFalse(os.path.exists(out_d))
        self.assertFalse(os.path.exists(out_s))

    def test_completed_run_still_writes(self):
        from pln3113_nip.algorithms.alg_space_syntax import SpaceSyntaxAlgorithm
        net = _line_layer("EPSG:5253", [c + np.array([500000, 4200000]) for c in T_FIXTURE])
        res = _run(SpaceSyntaxAlgorithm(), {"NETWORK": net, "RADII": "n", "OUTPUT": "memory:"})
        lyr = res["OUTPUT"]
        ch = sorted(round(f["CH_n"], 6) for f in lyr.getFeatures())
        self.assertEqual(ch, [0.0, 0.0, 0.0, 2.0])


class TestNetworkInputs(unittest.TestCase):
    """PlanX 4.23.0 fixes that apply to the other network tools."""

    def test_null_and_zero_costs_refused(self):
        from pln3113_nip.algorithms.alg_network_centrality import NetworkCentralityAlgorithm
        from pln3113_nip.core.planx_engine.planx_base import DOUBLE
        lines = [c + np.array([500000, 4200000]) for c in T_FIXTURE]
        for bad in (None, 0.0, -1.0):
            net = _line_layer("EPSG:5253", lines, [("dk", DOUBLE)],
                              [[1.0], [2.0], [bad], [1.5]])
            with self.assertRaises(QgsProcessingException) as ctx:
                _run(NetworkCentralityAlgorithm(), {"NETWORK": net, "COST_FIELD": "dk", "RADIUS": 0.0,
                                                    "EDGES": "memory:"})
            self.assertIn("maliyet", str(ctx.exception).lower())

    def test_centrality_sampling_is_deterministic(self):
        from pln3113_nip.algorithms import alg_network_centrality as nc
        lines = []
        for i in range(7):
            for j in range(6):
                lines.append(_seg((500000 + i * 100, 4200000 + j * 100), (500000 + i * 100, 4200000 + (j + 1) * 100)))
                lines.append(_seg((500000 + j * 100, 4200000 + i * 100), (500000 + (j + 1) * 100, 4200000 + i * 100)))
        net = _line_layer("EPSG:5253", lines)
        runs = []
        for _ in range(2):
            res = _run(nc.NetworkCentralityAlgorithm(), {"NETWORK": net, "RADIUS": 0.0, "SAMPLES": 5,
                                                         "EDGES": "memory:"})
            runs.append([f["betweenness"] for f in res["EDGES"].getFeatures()])
        self.assertEqual(runs[0], runs[1])
        with open(nc.__file__, encoding="utf-8") as fh:
            self.assertNotIn("np.random", fh.read())

    def test_space_syntax_radius_is_ground_metres(self):
        """EPSG:3857 at 41 N: 300 m = ~397 map units, so the 350-unit neighbour is inside."""
        from pln3113_nip.algorithms.alg_space_syntax import SpaceSyntaxAlgorithm
        x0, y0 = 3000000.0, 5012341.0
        lines = [_seg((x0 + k * 350.0, y0), (x0 + (k + 1) * 350.0, y0)) for k in range(4)]
        net = _line_layer("EPSG:3857", lines)
        res = _run(SpaceSyntaxAlgorithm(), {"NETWORK": net, "RADII": "300", "OUTPUT": "memory:"})
        nc = [f["NC_300"] for f in res["OUTPUT"].getFeatures()]
        self.assertEqual(nc, [2.0, 3.0, 3.0, 2.0])

    def test_feet_crs_refused(self):
        """A projected CRS in feet is refused with a plain Turkish message."""
        from pln3113_nip.algorithms.alg_space_syntax import SpaceSyntaxAlgorithm
        from pln3113_nip.algorithms.alg_network_centrality import NetworkCentralityAlgorithm
        from pln3113_nip.algorithms.alg_service_areas import ServiceAreasAlgorithm
        from pln3113_nip.core.planx_engine.planx_base import PlanXBaseAlgorithm
        x0, y0 = 1000000.0, 200000.0   # EPSG:2263, NY Long Island (US survey feet)
        lines = [_seg((x0 + k * 400.0, y0), (x0 + (k + 1) * 400.0, y0)) for k in range(4)]
        net = _line_layer("EPSG:2263", lines)
        fac = _point_layer("EPSG:2263", [(x0, y0)])
        cases = (
            (SpaceSyntaxAlgorithm(), {"NETWORK": net, "RADII": "n", "OUTPUT": "memory:"}),
            (NetworkCentralityAlgorithm(), {"NETWORK": net, "RADIUS": 0.0, "EDGES": "memory:"}),
            (ServiceAreasAlgorithm(), {"NETWORK": net, "FACILITIES": fac, "BREAKS": "100",
                                       "AREAS": "memory:", "CIRCLES": "memory:",
                                       "EDGES": "memory:", "SUMMARY": "memory:"}),
        )
        for alg, params in cases:
            with self.assertRaises(QgsProcessingException) as ctx:
                _run(alg, params)
            self.assertIn("metre", str(ctx.exception), alg.name())
        with self.assertRaises(QgsProcessingException):
            PlanXBaseAlgorithm.require_projected(net, "Yol ağı")
        metre = _line_layer("EPSG:5253", [c + np.array([500000, 4200000]) for c in T_FIXTURE])
        PlanXBaseAlgorithm.require_projected(metre, "Yol ağı")   # metres pass

    def test_service_area_breaks_ground_metres_and_no_slivers(self):
        """EPSG:3857 at 41 N: a map unit is ~0.755 ground metres."""
        from pln3113_nip.algorithms.alg_service_areas import ServiceAreasAlgorithm
        crs = QgsCoordinateReferenceSystem("EPSG:3857")
        x0, y0 = 3000000.0, 5012341.0
        da = QgsDistanceArea()
        da.setSourceCrs(crs, QgsCoordinateTransformContext())
        da.setEllipsoid("WGS84")
        ref = QgsGeometry.fromPolylineXY([QgsPointXY(x0, y0), QgsPointXY(x0 + 1000.0, y0)])
        k = 1000.0 / da.measureLength(ref)          # map units per ground metre
        self.assertGreater(k, 1.3)
        edge = 100.0 * k                             # each edge is 100 ground metres
        lines = [_seg((x0 + i * edge, y0), (x0 + (i + 1) * edge, y0)) for i in range(4)]
        net = _line_layer("EPSG:3857", lines)
        fac = _point_layer("EPSG:3857", [(x0, y0)])
        res = _run(ServiceAreasAlgorithm(), {
            "NETWORK": net, "FACILITIES": fac, "BREAKS": "100, 200", "AREAS": "memory:",
            "CIRCLES": "memory:", "EDGES": "memory:", "SUMMARY": "memory:"})
        pieces = list(res["EDGES"].getFeatures())
        self.assertTrue(pieces)
        for f in pieces:
            self.assertGreater(f["parca_uzunluk_m"], 1e-3)
            self.assertGreater(f.geometry().length(), 1e-3 * k)
        by_break = {}
        for f in pieces:
            by_break[f["mesafe_m"]] = by_break.get(f["mesafe_m"], 0.0) + f.geometry().length()
        # The 100 m band reaches exactly one edge (100 ground m = edge map units).
        self.assertAlmostEqual(by_break[100.0], edge, delta=0.01 * k)
        self.assertAlmostEqual(by_break[200.0], edge, delta=0.01 * k)
        summary = {f["mesafe_m"]: f for f in res["SUMMARY"].getFeatures() if f["donati"] == "TUM_DONATILAR"}
        self.assertAlmostEqual(summary[100.0]["yol_uzunlugu_m"], 100.0, delta=0.5)
        self.assertAlmostEqual(summary[100.0]["daire_alani_m2"], math.pi * 100.0 ** 2, delta=0.01 * math.pi * 1e4)


if __name__ == "__main__":
    unittest.main()
