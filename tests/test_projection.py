# -*- coding: utf-8 -*-
"""Saf Python değer testleri: projeksiyon, kohort, dağıtım, kırılganlık.

Beklenen değerler elle hesaplandı (yorumlarda formül); QGIS gerekmez.
"""
from __future__ import annotations

import math
import unittest

from pln3113_nip.core import allocation as al
from pln3113_nip.core import cohort as co
from pln3113_nip.core import projection as pj
from pln3113_nip.core import vulnerability as vu


class TestTrendMethods(unittest.TestCase):

    def test_geometric_hand_value(self):
        # 87,528 × (87,528/76,327)^(20/18) = 101,911.6
        r = pj.project_trend([2007, 2025], [76327, 87528], "geometrik", 2045)
        self.assertAlmostEqual(r["value"], 101911.6, delta=0.1)
        self.assertAlmostEqual(r["params"]["r"], (87528 / 76327) ** (1 / 18) - 1, places=12)
        self.assertIsNone(r["backtest_pct"])          # iki gözlemle geri test yok

    def test_arithmetic_hand_value(self):
        # 87,528 + (87,528 − 76,327)/18 × 20 = 99,973.56
        r = pj.project_trend([2007, 2025], [76327, 87528], "aritmetik", 2045)
        self.assertAlmostEqual(r["value"], 87528 + 11201 / 18 * 20, places=6)
        self.assertAlmostEqual(r["value"], 99973.56, delta=0.01)

    def test_geometric_backtest(self):
        # 100 -> 121 (10 yıl): 2020 kestirimi 121 × 1.21 = 146.41; hata (146.41-150)/150 = -2.3933 %
        r = pj.project_trend([2000, 2010, 2020], [100, 121, 150], "geometrik", 2030)
        self.assertAlmostEqual(r["backtest_pct"], -2.393333, places=5)

    def test_iller_bankasi_lower_clamp(self):
        # 1000 -> 1100 / 20 yıl: %0.4777 -> %1; 2030 = 1100 × 1.01^10 = 1215.08
        r = pj.project_trend([2000, 2020], [1000, 1100], "iller_bankasi", 2030)
        self.assertAlmostEqual(r["value"], 1100 * 1.01 ** 10, places=6)
        self.assertTrue(r["params"]["sinirlandi"])
        self.assertAlmostEqual(r["params"]["a_hesaplanan_yuzde"], 0.47766, places=4)
        self.assertTrue(any("aralığına çekildi" in w for w in r["warnings"]))

    def test_iller_bankasi_upper_clamp_and_no_clamp(self):
        r = pj.project_trend([2000, 2010], [1000, 2000], "iller_bankasi", 2020)
        self.assertAlmostEqual(r["value"], 2000 * 1.03 ** 10, places=6)   # 2687.83
        self.assertTrue(r["warnings"])
        r2 = pj.project_trend([2000, 2010], [1000, 1200], "iller_bankasi", 2020)
        self.assertFalse(r2["params"]["sinirlandi"])                      # %1.84 aralıkta
        self.assertAlmostEqual(r2["value"], 1440.0, places=6)
        self.assertEqual(r2["warnings"], [])

    def test_regression_hand_value(self):
        # x̄=2010, ȳ=200, Sxx=200, Sxy=1000 -> b=5; 2030 = 300; R² = 1 − 15000/20000 = 0.25
        r = pj.project_trend([2000, 2010, 2020], [100, 300, 200], "regresyon", 2030)
        self.assertAlmostEqual(r["value"], 300.0, places=6)
        self.assertAlmostEqual(r["r2"], 0.25, places=9)

    def test_polynomial_exact(self):
        # P = 1000 + 10u + 0.5u², u = t − 2000; 2040 = 1000 + 400 + 800 = 2200
        ys = [2000, 2010, 2020, 2030]
        ps = [1000 + 10 * (y - 2000) + 0.5 * (y - 2000) ** 2 for y in ys]
        r = pj.project_trend(ys, ps, "polinom", 2040)
        self.assertAlmostEqual(r["value"], 2200.0, places=4)
        self.assertAlmostEqual(r["r2"], 1.0, places=9)
        self.assertAlmostEqual(r["backtest_pct"], 0.0, places=6)

    def test_polynomial_needs_three_points(self):
        with self.assertRaises(pj.ProjectionError):
            pj.project_trend([2000, 2010], [1, 2], "polinom", 2020)

    @staticmethod
    def _logistic(t, k=100000.0, a=2.0, b=-0.05):
        return k / (1.0 + math.exp(a + b * (t - 2000)))

    def test_logistic_recovers_k(self):
        ys = [2000, 2010, 2020, 2030]
        ps = [self._logistic(y) for y in ys]
        r = pj.project_trend(ys, ps, "lojistik", 2050)
        self.assertAlmostEqual(r["params"]["K"] / 100000.0, 1.0, places=3)
        # 2050: 100000 / (1 + e^(2 − 2.5)) = 62,245.93
        self.assertAlmostEqual(r["value"], 100000 / (1 + math.exp(-0.5)), delta=30)
        self.assertGreater(r["r2"], 0.9999)
        self.assertFalse(any("sınır" in w for w in r["warnings"]))

    def test_pearl_reed_exact(self):
        ys = [2000, 2010, 2020]
        ps = [self._logistic(y) for y in ys]
        self.assertAlmostEqual(pj.pearl_reed_k(*ps), 100000.0, delta=1e-6)
        r = pj.project_trend(ys, ps, "lojistik", 2050, pearl_reed=True)
        self.assertAlmostEqual(r["params"]["K"], 100000.0, delta=1e-6)
        self.assertAlmostEqual(r["value"], 100000 / (1 + math.exp(-0.5)), delta=1e-6)

    def test_pearl_reed_rejects(self):
        with self.assertRaises(pj.ProjectionError):     # orta yıl yok
            pj.project_trend([2000, 2007, 2020], [10, 20, 25], "lojistik", 2030, pearl_reed=True)
        with self.assertRaises(pj.ProjectionError):     # büyüme hızlanıyor: P0·P2 >= P1²
            pj.pearl_reed_k(1000, 1500, 2250)

    def test_logistic_k_boundary_warning(self):
        r = pj.project_trend([2000, 2005, 2010, 2015], [1000, 1500, 2250, 3375], "lojistik", 2030)
        self.assertTrue(any("arama üst sınırına" in w for w in r["warnings"]))
        self.assertAlmostEqual(r["params"]["K"], 3375 * 10.0, delta=3375 * 10.0 * 0.03)

    def test_logistic_user_k(self):
        with self.assertRaises(pj.ProjectionError):
            pj.project_trend([2000, 2010, 2020], [100, 150, 180], "lojistik", 2030, saturation=150)
        r = pj.project_trend([2000, 2010, 2020], [100, 150, 180], "lojistik", 2030, saturation=250)
        self.assertEqual(r["params"]["K"], 250.0)
        self.assertLess(r["value"], 250.0)

    def test_input_validation(self):
        bad = [
            (([2010, 2010], [1, 2]), "artan"),
            (([2010, 2005], [1, 2]), "artan"),
            (([2010], [1]), "en az iki"),
            (([2000, 2010], [100, 0]), "pozitif"),
            (([2000, 2010], [100, -5]), "pozitif"),
            (([2000, 2010], [100]), "eşit"),
            (([2000, "x"], [1, 2]), "sayı"),
        ]
        for (ys, ps), word in bad:
            with self.assertRaises(pj.ProjectionError) as cm:
                pj.project_trend(ys, ps, "geometrik", 2030)
            self.assertIn(word, str(cm.exception).lower())
        with self.assertRaises(pj.ProjectionError):
            pj.project_trend([2000, 2010], [1, 2], "ustel", 2030)

    def test_project_all_reports_errors(self):
        out = pj.project_all([2000, 2010], [100, 120], 2030)
        by = {r["method"]: r for r in out}
        self.assertEqual(set(by), set(pj.METHODS))
        self.assertIn("en az 3", by["polinom"]["error"])
        self.assertIsNone(by["lojistik"]["value"])
        self.assertAlmostEqual(by["aritmetik"]["value"], 160.0)

    def test_series_and_target_before_last(self):
        r = pj.project_trend([2000, 2010], [100, 120], "aritmetik", 2013)
        self.assertEqual(r["series"][0], (2000.0, 100.0))
        self.assertEqual(r["series"][-1][0], 2013.0)
        r2 = pj.project_trend([2000, 2010], [100, 120], "aritmetik", 2005)
        self.assertAlmostEqual(r2["value"], 110.0)
        self.assertTrue(any("son gözlemden" in w for w in r2["warnings"]))

    def test_parse_number_list(self):
        self.assertEqual(pj.parse_number_list("2007, 2010; 2015\n2020"), [2007, 2010, 2015, 2020])
        self.assertEqual(pj.parse_number_list("76.327 87.528"), [76327, 87528])
        self.assertEqual(pj.parse_number_list("0.010 0.055", allow_thousands=False), [0.010, 0.055])
        self.assertEqual(pj.parse_number_list("0.010"), [0.010])
        self.assertEqual(pj.parse_number_list("1.500", allow_thousands=False), [1.5])

    def test_economic_base(self):
        r = pj.economic_base_migration(2.8, new_jobs=1000)
        self.assertAlmostEqual(r["goc_nufusu"], 2800.0)
        # (400 × 2.5 − 200) × 3 = 2400
        r2 = pj.economic_base_migration(3.0, basic_jobs=400, base_multiplier=2.5,
                                        local_supply_jobs=200)
        self.assertAlmostEqual(r2["goc_nufusu"], 2400.0)
        r3 = pj.economic_base_migration(3.0, current_employment=5000, target_employment=4000)
        self.assertEqual(r3["goc_nufusu"], 0.0)
        self.assertTrue(r3["warnings"])
        with self.assertRaises(pj.ProjectionError):
            pj.economic_base_migration(0, new_jobs=10)


class TestCohort(unittest.TestCase):

    def _params(self, **kw):
        p = {"sx_male": [1.0] * 17, "sx_female": [1.0] * 17, "asfr": [0.0] * 7,
             "birth_survival_male": 0.99, "birth_survival_female": 0.99, "srb": 100.0}
        p.update(kw)
        return p

    def test_defaults_file(self):
        d = co.load_defaults()
        self.assertEqual(len(d["sx_male"]), 17)
        self.assertEqual(len(d["sx_female"]), 17)
        self.assertAlmostEqual(co.tfr(d["asfr"]), 1.51, places=6)
        self.assertAlmostEqual(sum(d["migration_profile"]), 1.0, places=6)
        self.assertTrue(all(0 < s <= 1 for s in d["sx_male"] + d["sx_female"]))
        # kadın yaşama oranları her yaşta erkeğinkinden yüksek (model tablo tutarlılığı)
        self.assertTrue(all(f >= m for m, f in zip(d["sx_male"], d["sx_female"])))
        self.assertIn("TÜİK", d["sources"]["sx"])

    def test_ageing_without_events(self):
        base = {"year": 2025, "male": [100.0] * 17, "female": [100.0] * 17}
        r = co.project_cohort(base, self._params(), 2030)
        m = r["male"][2030]
        self.assertEqual(m[0], 0.0)                 # doğum yok
        self.assertEqual(m[5], 100.0)
        self.assertEqual(m[16], 200.0)              # 75-79 + 80+
        self.assertAlmostEqual(r["totals"][2030], 3400.0)

    def test_births_use_birth_survival_not_sx0(self):
        # sx = 1 (sx0 = 0.5 hariç), ASFR 0.02 × 7, her grupta 1000 kadın:
        # B = 5 × Σ 0.02 × (1000 + 1000)/2 = 700;  erkek 0-4 = 700 × 0.5 × 0.99 = 346.5
        sxm = [1.0] * 17
        sxm[0] = 0.5
        base = {"year": 2025, "male": [1000.0] * 17, "female": [1000.0] * 17}
        r = co.project_cohort(base, self._params(asfr=[0.02] * 7, sx_male=sxm), 2030)
        self.assertAlmostEqual(r["births"][2030], 700.0, places=9)
        self.assertAlmostEqual(r["male"][2030][0], 346.5, places=9)
        self.assertAlmostEqual(r["female"][2030][0], 346.5, places=9)
        self.assertAlmostEqual(r["male"][2030][1], 500.0, places=9)   # 0-4 -> 5-9 Sx0 ile

    def test_interpolated_target(self):
        base = {"year": 2025, "male": [100.0] * 17, "female": [100.0] * 17}
        p = self._params(migration_mode="kisi", migration_value=100)
        r = co.project_cohort(base, p, 2032)
        self.assertEqual(r["years"], [2025, 2030, 2035])
        a, b = r["male"][2030][5], r["male"][2035][5]
        self.assertAlmostEqual(r["target"]["male"][5], a * (b / a) ** 0.4, places=9)
        self.assertTrue(any("enterpole" in w for w in r["warnings"]))

    def test_migration_persons_and_rate(self):
        base = {"year": 2025, "male": [100.0] * 17, "female": [100.0] * 17}
        r = co.project_cohort(base, self._params(migration_mode="kisi", migration_value=100), 2035)
        self.assertAlmostEqual(r["totals"][2030], 3400 + 500, places=6)   # 5 × 100
        self.assertAlmostEqual(r["migrants"][2035], 500.0)
        r2 = co.project_cohort(base, self._params(migration_mode="oran", migration_value=0.01),
                               2030)
        self.assertAlmostEqual(r2["migrants"][2030], 3400 * (1.01 ** 5 - 1), places=6)
        # göç profili: 20-24 payı 0.135, yarısı erkek
        self.assertAlmostEqual(r2["male"][2030][4] - 100.0,
                               3400 * (1.01 ** 5 - 1) * 0.135 * 0.5, places=6)

    def test_negative_migration_clamped_with_warning(self):
        base = {"year": 2025, "male": [1.0] * 17, "female": [1.0] * 17}
        r = co.project_cohort(base, self._params(migration_mode="kisi", migration_value=-1000),
                              2030)
        self.assertTrue(all(v >= 0 for v in r["male"][2030]))
        self.assertTrue(any("negatife" in w for w in r["warnings"]))

    def test_tfr_path(self):
        base = {"year": 2025, "male": [1000.0] * 17, "female": [1000.0] * 17}
        p = self._params(asfr=[0.0302] * 5 + [0.0, 0.0], tfr_target=1.0, tfr_target_year=2035)
        r = co.project_cohort(base, p, 2045)
        # TDH0 = 5 × 0.151 = 0.755; 2027.5: 0.755 + (1 − 0.755) × 0.25
        self.assertAlmostEqual(r["tfr_path"][2030], 0.755 + 0.245 * 0.25, places=9)
        self.assertAlmostEqual(r["tfr_path"][2040], 1.0, places=9)   # hedef yıldan sonra sabit

    def test_indicators(self):
        male = [50, 50, 50] + [50] * 10 + [25, 25, 25, 25]
        female = list(male)
        ind = co.indicators(male, female)
        # çocuk 300, çalışma 1000, yaşlı 200
        self.assertAlmostEqual(ind["toplam_bagimlilik"], 50.0)
        self.assertAlmostEqual(ind["genc_bagimlilik"], 30.0)
        self.assertAlmostEqual(ind["yasli_bagimlilik"], 20.0)
        self.assertAlmostEqual(ind["yaslanma_endeksi"], 200 / 300 * 100)
        self.assertAlmostEqual(co.median_age([100] * 17), 42.5)   # 850. kişi: 8,5 grup
        self.assertAlmostEqual(ind["cinsiyet_orani"], 100.0)

    def test_broad_groups_preserve_totals(self):
        m, f = co.spread_broad_groups([300, 1000, 200], [290, 1010, 250])
        self.assertAlmostEqual(sum(m[:3]), 300)
        self.assertAlmostEqual(sum(m[3:13]), 1000)
        self.assertAlmostEqual(sum(f[13:]), 250)

    def test_age_labels(self):
        self.assertEqual(co.normalize_age_label("0–4"), 0)
        self.assertEqual(co.normalize_age_label("80 ve üzeri"), 16)
        self.assertEqual(co.normalize_age_label("15 - 19"), 3)
        self.assertIsNone(co.normalize_age_label("çocuk"))

    def test_cohort_errors(self):
        base = {"year": 2025, "male": [1.0] * 16, "female": [1.0] * 17}
        with self.assertRaises(co.CohortError):
            co.project_cohort(base, {}, 2030)
        base = {"year": 2025, "male": [1.0] * 17, "female": [1.0] * 17}
        with self.assertRaises(co.CohortError):
            co.project_cohort(base, {}, 2020)
        with self.assertRaises(co.CohortError):
            co.project_cohort(base, {"sx_male": [1.2] * 17}, 2030)
        with self.assertRaises(co.CohortError):
            co.project_cohort(base, {"migration_mode": "bilinmez"}, 2030)

    def test_explicit_zero_is_not_replaced_by_default(self):
        base = {"year": 2025, "male": [1000.0] * 17, "female": [1000.0] * 17}
        with self.assertRaises(co.CohortError):          # SRB 0 -> hata, 105'e dönmez
            co.project_cohort(base, self._params(srb=0), 2030)
        with self.assertRaises(co.CohortError):          # yaşama oranı 0 -> hata
            co.project_cohort(base, self._params(birth_survival_male=0.0), 2030)
        # hedef TDH 0 gerçek bir hedeftir: 2025-2035 doğrusal, 2027.5'te TDH0 × 0.75
        r = co.project_cohort(base, self._params(asfr=[0.02] * 7, tfr_target=0.0,
                                                 tfr_target_year=2035), 2040)
        self.assertAlmostEqual(r["tfr_path"][2030], 0.7 * 0.75, places=9)
        self.assertEqual(r["births"][2040], 0.0)

    def test_default_run_is_plausible(self):
        base = {"year": 2025, "male": [3000.0] * 17, "female": [3000.0] * 17}
        r = co.project_cohort(base, {}, 2045)
        self.assertEqual(r["years"], [2025, 2030, 2035, 2040, 2045])
        self.assertLess(r["totals"][2045], r["totals"][2025])     # TDH 1.51 < 2.1


class TestAllocation(unittest.TestCase):

    def test_largest_remainder(self):
        self.assertEqual(al.largest_remainder([166.667, 333.333, 500.0], 1000), [167, 333, 500])
        self.assertEqual(al.largest_remainder([0.5, 0.5, 0.5, 0.5], 2), [1, 1, 0, 0])
        vals = [1000 / 7.0] * 7
        self.assertEqual(sum(al.largest_remainder(vals, 1000)), 1000)

    def test_proportional_exact_total(self):
        res = al.allocate(["a", "b", "c"], [100, 200, 300], 1000)
        self.assertEqual([r["hedef"] for r in res["rows"]], [167, 333, 500])
        self.assertEqual(res["total"], 1000)

    def test_zone_shares(self):
        # artış 400: G %75 = 300 -> a +75, b +225; K %25 = 100 -> c +100
        res = al.allocate(["a", "b", "c"], [100, 300, 100], 900, "bolge",
                          zones=["Gelişme", "GELİŞME", "Kırsal"],
                          zone_shares={"gelişme": 0.75, "KIRSAL": 0.25})
        self.assertEqual([r["hedef"] for r in res["rows"]], [175, 525, 200])

    def test_zone_unknown_and_normalised(self):
        res = al.allocate(["a", "b"], [100, 100], 300, "bolge", zones=["G", "X"],
                          zone_shares={"G": 0.5, "Y": 0.5})
        self.assertEqual(res["by_key"]["a"]["hedef"], 200)
        self.assertEqual(res["by_key"]["b"]["hedef"], 100)
        self.assertTrue(any("pay tablosunda yok" in w for w in res["warnings"]))

    def test_capacity_with_unallocated(self):
        res = al.allocate(["a", "b"], [100, 200], 500, "kapasite", capacities=[150, 260])
        self.assertEqual([r["hedef"] for r in res["rows"]], [150, 260])
        self.assertAlmostEqual(res["unallocated"], 90.0)
        self.assertTrue(res["warnings"])

    def test_capacity_redistribution_proportional_to_room(self):
        # boş kapasite 50 / 150 -> artış 100'ün 25 / 75'i
        res = al.allocate(["a", "b", "c"], [100, 100, 100], 400, "kapasite",
                          capacities=[150, 250, None])
        self.assertEqual([r["hedef"] for r in res["rows"]], [125, 175, 100])
        self.assertEqual(res["null_capacity"], 1)

    def test_shrink_and_nulls(self):
        res = al.allocate(["a", "b", "c"], [100, 200, 300], 300, "kapasite",
                          capacities=[1, 1, 1])
        self.assertEqual([r["hedef"] for r in res["rows"]], [50, 100, 150])
        res2 = al.allocate(["a", "b"], [None, 100], 200)
        self.assertEqual(res2["null_population"], 1)
        self.assertEqual(res2["by_key"]["b"]["hedef"], 200)

    def test_key_errors(self):
        with self.assertRaises(al.AllocationError):
            al.allocate(["a", "a"], [1, 2], 10)
        with self.assertRaises(al.AllocationError):
            al.allocate(["a", None], [1, 2], 10)

    def test_parse_zone_shares(self):
        self.assertEqual(al.parse_zone_shares("Gelişme=75%; Kırsal=0.20; Koruma: 5"),
                         {"Gelişme": 0.75, "Kırsal": 0.2, "Koruma": 0.05})


class TestVulnerability(unittest.TestCase):

    def test_range_scoring(self):
        sc = vu.parse_scoring("<=100:5; <=250:4; <500:3; *:1")
        self.assertEqual(vu.range_score(100, sc["ranges"], sc["else"]), 5)
        self.assertEqual(vu.range_score(101, sc["ranges"], sc["else"]), 4)
        self.assertEqual(vu.range_score(499.9, sc["ranges"], sc["else"]), 3)
        self.assertEqual(vu.range_score(500, sc["ranges"], sc["else"]), 1)

    def test_turkish_category_matching(self):
        ind = vu.preset_indicators("deprem")[1]          # YMZ
        self.assertEqual(ind.code, "YMZ")
        scores, unmatched, _ = vu.score_indicator(ind, ["YIĞMA", "yigma", "Betonarme Karkas",
                                                        "ÇELİK", "bilinmiyor", None])
        self.assertEqual(scores, [4, 4, 2, 1, 3, None])
        self.assertEqual(unmatched, 1)

    def test_area_weighted_category(self):
        ind = vu.Indicator("M", "m", "pay", "yapi:kategori:x", "yığma=4; betonarme=2; *=3")
        # (4 × 300 + 2 × 100) / 400 = 3.5 -> 4
        scores, _, _ = vu.score_indicator(ind, [[("YIĞMA", 300.0), ("BETONARME", 100.0)]])
        self.assertEqual(scores, [4])

    def test_index_and_missing_neutral_one(self):
        inds = vu.parse_indicators(
            "A | a | pay | alan:a | yuvarla\n"
            "B | b | pay | alan:b | yuvarla\n"
            "C | c | payda | alan:c | yuvarla\n"
            "D | d | pay | alan:d | yuvarla")
        res = vu.compute_index(inds, {"A": [5, 2], "B": [4, None], "C": [2, 1],
                                      "D": [None, None]})
        self.assertEqual(res["index"], [10.0, 2.0])      # 5×4/2 ; 2×1/1
        self.assertEqual(res["missing_count"], [1, 2])
        self.assertEqual(res["disabled"], ["D"])
        self.assertEqual(res["used"]["B"], [4, 1])

    def test_quantile_and_equal_scoring(self):
        ind = vu.Indicator("Q", "q", "pay", "alan:q", "dilim")
        self.assertEqual(vu.score_indicator(ind, [1, 2, 3, 4, 5])[0], [1, 2, 3, 4, 5])
        ind_r = vu.Indicator("Q", "q", "pay", "alan:q", "dilim ters")
        self.assertEqual(vu.score_indicator(ind_r, [1, 2, 3, 4, 5])[0], [5, 4, 3, 2, 1])
        ind_e = vu.Indicator("E", "e", "pay", "alan:e", "esit")
        self.assertEqual(vu.score_indicator(ind_e, [0, 10, 100, None])[0], [1, 1, 5, None])

    def test_flood_directions_corrected(self):
        inds = {i.code: i for i in vu.preset_indicators("sel")}
        fr, fe, sn = inds["FR"], inds["FE"], inds["SN"]
        self.assertEqual(fr.role, "pay")
        self.assertEqual(vu.score_indicator(fr, [0.0, 100.0])[0], [5, 1])   # alçak = maruz
        self.assertEqual(fe.role, "pay")
        self.assertEqual(vu.score_indicator(fe, [1.0, 30.0])[0], [5, 1])    # düz = maruz
        self.assertEqual(sn.measure, "yogunluk")
        self.assertEqual(vu.score_indicator(sn, [50.0, 500.0])[0], [1, 5])

    def test_all_presets_parse(self):
        for key in vu.PRESETS:
            inds = vu.preset_indicators(key)
            self.assertGreater(len(inds), 5)
            self.assertTrue(any(not i.is_numerator for i in inds))

    def test_parse_errors(self):
        for text in ("A | a | pay | alan:a",                 # 4 parça
                     "A | a | ikisi | alan:a | yuvarla",       # rol
                     "A | a | pay | alan:a | <=5:7; *:1",      # puan 7
                     "A | a | pay | alan:a | <=5:2",           # * yok
                     "A | a | pay | alan:a | yuvarla\nA | b | pay | alan:b | yuvarla"):
            with self.assertRaises(vu.VulnerabilityError):
                vu.parse_indicators(text)

    def test_breaks(self):
        self.assertEqual(vu.equal_breaks([0, 10]), [0, 2, 4, 6, 8, 10])
        g = vu.geometric_breaks([1, 32])
        for a, b in zip(g, [1, 2, 4, 8, 16, 32]):
            self.assertAlmostEqual(a, b, places=9)
        self.assertEqual(vu.quantile_breaks([1, 2, 3, 4, 5, 6]), [1, 2, 3, 4, 5, 6])
        data = [1, 2, 3, 10, 11, 12, 20, 21, 22, 40, 41, 42, 80, 81, 82]
        self.assertEqual(vu.jenks_breaks(data), [1, 3, 12, 22, 42, 82])
        cls = vu.classify(data, vu.jenks_breaks(data))
        self.assertEqual(cls[0], 5)
        self.assertEqual(cls[-1], 1)
        self.assertEqual(cls[7], 3)
        gz = vu.geometric_breaks([0, 50, 100])          # sıfır içeren seri sınıflanır
        self.assertEqual(gz[0], 0)
        self.assertNotIn(None, vu.classify([0, 50, 100], gz))

    def test_break_definitions(self):
        # Hyndman-Fan tip 7: n=5, p=0.2 -> konum 0.8 -> 10 + 0.8 × (20 − 10) = 18
        q = vu.quantile_breaks([10, 20, 30, 40, 100])
        for a, b in zip(q, [10, 18, 26, 34, 52, 100]):
            self.assertAlmostEqual(a, b, places=9)
        # lo <= 0: x' = x − min + 1, sınırlar 1 .. 101 geometrik, geri ötelenir
        g = vu.geometric_breaks([0, 100])
        for i, b in enumerate(g):
            self.assertAlmostEqual(b, -1 + 101 ** (i / 5), places=9)
        g2 = vu.geometric_breaks([-10, 10])
        self.assertAlmostEqual(g2[1], -11 + 21 ** 0.2, places=9)
        # sınıf üst sınırı dahil: 10 tam sınırda alt sınıfta kalır
        self.assertEqual(vu.classify([0, 2, 2.0001, 10], [0, 2, 4, 6, 8, 10]), [5, 5, 4, 1])
        # 5'ten az farklı değer: her değer kendi sınıfı
        self.assertEqual(vu.jenks_breaks([1, 1, 2, 3]), [1, 1, 2, 3, 3, 3])

    def test_tie_averaged_ranks(self):
        self.assertEqual(vu.tie_averaged_ranks([30, 10, 20, 10, 30, 30]),
                         [4.0, 0.5, 2.0, 0.5, 4.0, 4.0])

    def test_composite(self):
        res = vu.composite({"K_Y": [1, 2, 3], "K_S": [10, None, 30]}, {"K_Y": 1, "K_S": 1})
        self.assertEqual(res["values"], [0.0, 50.0, 100.0])
        self.assertEqual(res["weights"], {"K_Y": 0.5, "K_S": 0.5})
        self.assertEqual(vu.minmax([1, math.e, math.e ** 2], log=True), [0.0, 50.0, 100.0])
        self.assertEqual(vu.parse_weights("K_D=0.4; k_y=0.35"), {"K_D": 0.4, "K_Y": 0.35})

    def test_html_escaped(self):
        page = vu.html_report("<b>R</b>", [("S", ["<x>"], [["<script>alert(1)</script>"]])],
                              ["a & b"])
        self.assertNotIn("<script>", page)
        self.assertIn("&lt;script&gt;", page)
        self.assertIn("a &amp; b", page)


if __name__ == "__main__":
    unittest.main()
