# -*- coding: utf-8 -*-
"""Pure-Python logic and parameter tests for tire_nip."""
from __future__ import annotations

import os
import re
import unittest

from tire_nip.core.tire_constants import (
    TIRE_POPULATION_BENCHMARKS,
    norm_tr,
    resolve_nip_density,
    identify_facility_category,
    get_employment_for_function,
    get_trips_for_function
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


if __name__ == "__main__":
    unittest.main()
