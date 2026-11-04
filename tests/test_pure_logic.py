# -*- coding: utf-8 -*-
"""Pure-Python logic and parameter tests for pln3113_nip."""
from __future__ import annotations

import os
import re
import unittest

from pln3113_nip.core.tire_constants import (
    TIRE_POPULATION_BENCHMARKS,
    norm_tr,
    resolve_nip_density,
    identify_facility_category,
    get_employment_for_function,
    get_trips_for_function,
    get_default_dop_rule
)


class TestTireConstants(unittest.TestCase):
    """Tire planlama sabitleri ve parametre denetimleri."""

    def test_benchmarks_exist(self):
        keys = ["plan_1997_die", "hedef_2015_model", "tuik_2015_kesin", "tuik_2026_guncel"]
        for k in keys:
            self.assertIn(k, TIRE_POPULATION_BENCHMARKS)
            bm = TIRE_POPULATION_BENCHMARKS[k]
            self.assertGreater(bm["merkez"], 0)
            self.assertGreater(bm["ilce"], 0)
            self.assertIn("kaynak", bm)

    def test_norm_tr(self):
        self.assertEqual(norm_tr("TİRE"), "TIRE")
        self.assertEqual(norm_tr("Işıklı Örnek"), "ISIKLI ORNEK")
        self.assertEqual(norm_tr("Çöğür Düşük"), "COGUR DUSUK")
        self.assertEqual(norm_tr(""), "")

    def test_resolve_nip_density(self):
        # Orta gelişme: (alt, ust, label)
        alt, ust, label = resolve_nip_density("Gelişme Konut Alanı (Orta Yoğunluk)")
        self.assertEqual(alt, 121.0)
        self.assertEqual(ust, 250.0)
        self.assertIn("ORTA", label)

        # Çok yüksek mevcut
        alt_cy, ust_cy, label_cy = resolve_nip_density("Mevcut Konut Alanı (Çok Yüksek 601-900)")
        self.assertEqual(alt_cy, 601.0)
        self.assertEqual(ust_cy, 900.0)
        self.assertIn("ÇOK YÜKSEK", label_cy)

        # Konut dışı (0.0, 0.0)
        alt_d, ust_d, label_d = resolve_nip_density("Park ve Yeşil Alan")
        self.assertEqual(alt_d, 0.0)
        self.assertEqual(ust_d, 0.0)

    def test_identify_facility_category(self):
        egt = identify_facility_category("Eğitim Alanı (İlkokul)")
        self.assertEqual(egt, "EGITIM")

        sag = identify_facility_category("Sağlık Tesisi (Hastane)")
        self.assertEqual(sag, "SAGLIK")

        yesil = identify_facility_category("Park Alanı")
        self.assertEqual(yesil, "YESIL_ALAN")

    def test_employment_rates(self):
        san_emp = get_employment_for_function("Sanayi Alanı", alan_m2=10000.0)
        self.assertGreater(san_emp, 0)
        park_emp = get_employment_for_function("Park", alan_m2=10000.0)
        self.assertEqual(park_emp, 0.0)

    def test_trip_generation_rates(self):
        arac, yaya = get_trips_for_function("Ticaret Alanı", alan_m2=1000.0)
        self.assertGreater(arac, 0)
        self.assertGreater(yaya, 0)

    def test_tucbs_mapping(self):
        from pln3113_nip.core.tire_constants import get_tucbs_info
        # Konut
        info_k = get_tucbs_info("dusukYogunluktaKonutAlani")
        self.assertIsNotNone(info_k)
        self.assertEqual(info_k["alt"], 51.0)
        self.assertEqual(info_k["ust"], 150.0)
        self.assertEqual(info_k["dop_turu"], "DOP İÇİ - ÖZEL (TAHSİS)")

        # Boş arsa özel mülkiyettir (Kamu kesintisi yapılamaz)
        info_a = get_tucbs_info("bosArsa")
        self.assertIsNotNone(info_a)
        self.assertEqual(info_a["dop_turu"], "DOP İÇİ - ÖZEL (TAHSİS)")

        # Eğitim ve Sağlık donatıdır (Kamu kesintisidir)
        info_e = get_tucbs_info("egitimAlani")
        self.assertEqual(info_e["donati"], "EGITIM")
        self.assertEqual(info_e["dop_turu"], "DOP İÇİ - KAMU (KESİNTİ)")

        # Tarım ve Zeytinlik DOP dışıdır
        info_t = get_tucbs_info("zeytinlik")
        self.assertEqual(info_t["dop_durumu"], "DOP DIŞI")

    def test_tucbs_density_and_facility(self):
        # TUCBS density
        alt, ust, label = resolve_nip_density("ortaYogunluktaKonutAlani")
        self.assertEqual(alt, 151.0)
        self.assertEqual(ust, 300.0)

        # TUCBS facility
        sag = identify_facility_category("saglikAlani")
        self.assertEqual(sag, "SAGLIK")
        park = identify_facility_category("parkVeYesilAlan")
        self.assertEqual(park, "YESIL_ALAN")

    def test_get_default_dop_rule(self):
        # Konut (DOP İçi - Özel Tahsis)
        inc_k, durumu_k, turu_k = get_default_dop_rule("Gelişme Konut Alanı (Orta)")
        self.assertTrue(inc_k)
        self.assertEqual(durumu_k, "DOP İÇİ")
        self.assertIn("ÖZEL", turu_k)

        # Eğitim ve Sağlık (DOP İçi - Kamu Kesinti)
        inc_e, durumu_e, turu_e = get_default_dop_rule("Eğitim Alanı (İlkokul)")
        self.assertTrue(inc_e)
        self.assertEqual(durumu_e, "DOP İÇİ")
        self.assertIn("KAMU", turu_e)

        # Park (DOP İçi - Kamu Kesinti)
        inc_p, durumu_p, turu_p = get_default_dop_rule("Park ve Yeşil Alan")
        self.assertTrue(inc_p)
        self.assertEqual(durumu_p, "DOP İÇİ")
        self.assertIn("KAMU", turu_p)

        # Boş Arsa (DOP İçi - Özel Tahsis)
        inc_a, durumu_a, turu_a = get_default_dop_rule("Boş Arsa / Yapılaşmamış Parsel")
        self.assertTrue(inc_a)
        self.assertEqual(durumu_a, "DOP İÇİ")
        self.assertIn("ÖZEL", turu_a)

        # Tarım, Orman, Mera (DOP Dışı - nDOP Hariç)
        inc_t, durumu_t, turu_t = get_default_dop_rule("Tarım Alanı")
        self.assertFalse(inc_t)
        self.assertEqual(durumu_t, "DOP DIŞI")
        self.assertIn("HARİÇ", turu_t)

        inc_o, durumu_o, turu_o = get_default_dop_rule("Orman")
        self.assertFalse(inc_o)
        self.assertEqual(durumu_o, "DOP DIŞI")
        self.assertIn("HARİÇ", turu_o)

        inc_m, durumu_m, turu_m = get_default_dop_rule("Askeri Alan")
        self.assertFalse(inc_m)
        self.assertEqual(durumu_m, "DOP DIŞI")
        self.assertIn("HARİÇ", turu_m)


class TestNipValuesPure(unittest.TestCase):
    """Elle hesaplanmış gerçek sayılar (N4): DOP, ada nüfusu, Ek-2."""

    def test_ada_nufusu_orta_gelisme_1ha(self):
        from pln3113_nip.core.tire_constants import ada_nufusu
        alt, ust = resolve_nip_density("Gelişme Konut Alanı (Orta Yoğunluk)")[:2]
        # 1 ha x 121-250 kişi/ha
        self.assertEqual(ada_nufusu(1.0, alt, ust), (121.0, 250.0))
        # 2,5 ha mevcut yüksek (301-600) -> 752,5 - 1500
        a2, u2 = resolve_nip_density("Mevcut Konut Alanı (Yüksek)")[:2]
        self.assertAlmostEqual(ada_nufusu(2.5, a2, u2)[0], 752.5)
        self.assertAlmostEqual(ada_nufusu(2.5, a2, u2)[1], 1500.0)

    def test_dop_orani_elle(self):
        from pln3113_nip.core.tire_constants import dop_orani_hesapla
        # Denetim fikstürü: kamu poligon 10000 + yol 7200 = 17200; DOP esas 37200 -> %46,24
        self.assertEqual(dop_orani_hesapla(10000.0, 7200.0, 37200.0), 46.24)
        # 30 + 10 / 100 -> %40
        self.assertEqual(dop_orani_hesapla(30.0, 10.0, 100.0), 40.0)

    def test_dop_uygunluk_sinirsiz_tahmini(self):
        from pln3113_nip.core.tire_constants import dop_uygunluk_metni
        self.assertEqual(dop_uygunluk_metni(46.24, True), "YASAL SINIRI AŞIYOR")
        self.assertEqual(dop_uygunluk_metni(45.0, True), "YASAL SINIRDA (UYGUN)")
        tahmini = dop_uygunluk_metni(46.24, False)
        self.assertIn("TAHMİNİ", tahmini)
        self.assertNotIn("AŞIYOR", tahmini)
        self.assertNotIn("UYGUN", tahmini)

    def test_ek2_standartlari_ve_alanlar(self):
        from pln3113_nip.core.tire_constants import MPYY_DONATI_STANDARTLARI as S, ek2_degerlendir
        # Mevcut değerler (yönetmeliğe karşı doğrulanmalı; burada değişmeleri yakalanır)
        beklenen = {"EGITIM": 6.5, "SAGLIK": 1.5, "SOSYAL_KULTUREL": 1.0,
                    "YESIL_ALAN": 10.0, "TEKNIK_ALTYAPI": 1.25, "IBADET": 0.5}
        self.assertEqual({k: v["standart_m2_kisi"] for k, v in S.items()}, beklenen)
        # 10.000 kişi için eğitim: gerekli 65.000 m²; 50.000 m² mevcut -> 15.000 m² açık
        r = ek2_degerlendir(50000.0, S["EGITIM"]["standart_m2_kisi"], 10000)
        self.assertEqual(r["gerekli_m2"], 65000.0)
        self.assertEqual(r["fark_m2"], -15000.0)
        self.assertEqual(r["kisi_basi_m2"], 5.0)
        self.assertEqual(r["durum"], "YETERSİZ")
        # 121 kişi için 1 ha yeşil alan: gerekli 1210 m², kişi başı 82,64 m²
        y = ek2_degerlendir(10000.0, S["YESIL_ALAN"]["standart_m2_kisi"], 121)
        self.assertEqual((y["gerekli_m2"], y["fark_m2"], y["kisi_basi_m2"], y["durum"]),
                         (1210.0, 8790.0, 82.64, "YETERLİ"))

    def test_spor_ve_ozel_saglik_kamu_standardi_degil(self):
        from pln3113_nip.core.tire_constants import get_tucbs_info
        self.assertIsNone(identify_facility_category("Spor Alanı"))
        self.assertIsNone(identify_facility_category("Semt Spor Alanı"))
        self.assertIsNone(identify_facility_category("sporKompleksiAlani"))
        self.assertIsNone(identify_facility_category("Özel Sağlık Alanı"))
        self.assertEqual(identify_facility_category("Sağlık Alanı"), "SAGLIK")
        self.assertEqual(identify_facility_category("Park ve Yeşil Alan"), "YESIL_ALAN")
        # Özel sağlık DOP'ta özel tahsistir (kamu kesintisi değil)
        self.assertEqual(get_tucbs_info("Özel Sağlık Alanı")["dop_turu"], "DOP İÇİ - ÖZEL (TAHSİS)")
        self.assertEqual(get_tucbs_info("Sağlık Alanı")["dop_turu"], "DOP İÇİ - KAMU (KESİNTİ)")

    def test_tire_yalniz_ornek_onayar(self):
        from pln3113_nip.core.tire_constants import NUFUS_KIYAS_ONAYARLARI, TIRE_KIRSAL_NUFUS_ORNEK
        self.assertEqual(NUFUS_KIYAS_ONAYARLARI["yok"], {})
        self.assertIs(NUFUS_KIYAS_ONAYARLARI["tire"], TIRE_POPULATION_BENCHMARKS)
        self.assertEqual(TIRE_KIRSAL_NUFUS_ORNEK, 26000)


class TestQt6EnumSafety(unittest.TestCase):
    """Eklenti kodunda bare Qt.* enum kullanımının olmadığını doğrular."""

    FORBIDDEN_BARE_PATTERNS = [
        re.compile(r"\bQt\.(LeftButton|RightButton|MiddleButton)\b"),
        re.compile(r"\bQt\.(Key_\w+)\b"),
        re.compile(r"\bQt\.(RightDockWidgetArea|LeftDockWidgetArea|TopDockWidgetArea|BottomDockWidgetArea)\b"),
        re.compile(r"\bQFrame\.(NoFrame|HLine|VLine|Box|Panel|StyledPanel)\b"),
    ]

    def test_no_unscoped_qt_enums(self):
        pkg_root = os.path.dirname(os.path.dirname(__file__))
        violations = []
        for root, _, files in os.walk(pkg_root):
            if "tests" in root or "__pycache__" in root:
                continue
            for f in files:
                if f.endswith(".py"):
                    path = os.path.join(root, f)
                    with open(path, "r", encoding="utf-8") as py_file:
                        content = py_file.read()
                        for pat in self.FORBIDDEN_BARE_PATTERNS:
                            m = pat.search(content)
                            if m:
                                violations.append(f"{f}: {m.group(0)}")
        self.assertEqual(violations, [], f"Forbidden bare Qt enums found: {violations}")


class TestPlanXEnginePure(unittest.TestCase):
    """pln3113_nip icindeki gomme planx_engine saf-Python modul testleri."""

    def test_node_graph_and_paths(self):
        import numpy as np
        from pln3113_nip.core.planx_engine.graphs import build_node_graph
        from pln3113_nip.core.planx_engine.paths import many_to_many, multi_source

        # 3 cizgi segmenti: 0--(0,0)->(10,0), 1--(10,0)->(30,0)
        lines = [
            np.array([[0.0, 0.0], [10.0, 0.0]]),
            np.array([[10.0, 0.0], [30.0, 0.0]]),
        ]
        g = build_node_graph(lines)

        self.assertEqual(g.num_nodes, 3)
        self.assertEqual(g.num_edges, 2)
        self.assertEqual(g.degrees()[1], 2)

        # En kisa yol matrisi
        dmat = many_to_many(g.indptr, g.adj_node, g.adj_cost, g.num_nodes, sources=[0])
        self.assertAlmostEqual(dmat[0, 0], 0.0)
        self.assertAlmostEqual(dmat[0, 1], 10.0)
        self.assertAlmostEqual(dmat[0, 2], 30.0)

        # Coklu kaynak
        min_cost, src_idx = multi_source(g.indptr, g.adj_node, g.adj_cost, g.num_nodes, sources=[0, 2])
        self.assertAlmostEqual(min_cost[1], 10.0)
        self.assertEqual(src_idx[1], 0)

    def test_segment_graph_and_syntax(self):
        import numpy as np
        from pln3113_nip.core.planx_engine.graphs import build_segment_graph
        from pln3113_nip.core.planx_engine.syntax import segment_angular_analysis

        # T seklinde 3 yol segmenti:
        # 0: (0,0)->(100,0)
        # 1: (100,0)->(200,0)
        # 2: (100,0)->(100,100)
        lines = [
            np.array([[0.0, 0.0], [100.0, 0.0]]),
            np.array([[100.0, 0.0], [200.0, 0.0]]),
            np.array([[100.0, 0.0], [100.0, 100.0]]),
        ]
        sg = build_segment_graph(lines)
        self.assertEqual(sg.n, 3)

        res = segment_angular_analysis(sg, radius=None)
        self.assertIn("nain", res)
        self.assertIn("nach", res)
        self.assertIn("choice", res)
        self.assertIn("md", res)
        self.assertEqual(len(res["nach"]), 3)

    def test_centrality_metrics(self):
        import numpy as np
        from pln3113_nip.core.planx_engine.graphs import build_node_graph
        from pln3113_nip.core.planx_engine.centrality import closeness_straightness

        lines = [
            np.array([[0.0, 0.0], [100.0, 0.0]]),
            np.array([[100.0, 0.0], [200.0, 0.0]]),
            np.array([[100.0, 0.0], [100.0, 100.0]]),
        ]
        g = build_node_graph(lines)
        out = closeness_straightness(g.indptr, g.adj_node, g.adj_cost, g.num_nodes,
                                     node_xy=g.node_xy, radius=None)

        self.assertIn("closeness", out)
        self.assertIn("straightness", out)
        self.assertIn("harmonic", out)
        # Merkezdeki dugum (index 1) en yuksek closeness'a sahip olmali
        self.assertGreater(out["closeness"][1], out["closeness"][0])

    def test_isochrone_polyline_cut(self):
        from pln3113_nip.core.planx_engine.isochrone import cut_polyline, reach_fractions, edge_intervals

        poly = [(0.0, 0.0), (100.0, 0.0)]
        cut = cut_polyline(poly, 0.25, 0.75)
        self.assertEqual(len(cut), 2)
        self.assertAlmostEqual(cut[0][0], 25.0)
        self.assertAlmostEqual(cut[1][0], 75.0)

        full, fa, fb = reach_fractions([100.0], [200.0], [100.0], 150.0)
        iv = edge_intervals(full[0], fa[0], fb[0])
        self.assertEqual(len(iv), 1)
        self.assertAlmostEqual(iv[0][1], 0.5)


if __name__ == "__main__":
    unittest.main()
