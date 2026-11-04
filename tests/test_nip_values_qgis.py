# -*- coding: utf-8 -*-
"""NİP girdi doğruluğu ve değer testleri (QGIS gerekir).

Çalıştırma (monorepo kökünden):
    python-qgis-ltr.bat -m pln3113_nip.tests.test_nip_values_qgis

Kapsam: farklı KRS'deki plan sınırı/yol (N2), coğrafi veri + 'NONE' elipsoit (N3),
sınırsız DOP'un tahmini etiketlenmesi (N6), NULL sayımları (N12), iptal (N9) ve
elle hesaplanmış nüfus/DOP/Ek-2 sayıları (N4).
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PLUGIN_DIR = Path(__file__).resolve().parent.parent
if str(PLUGIN_DIR.parent) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR.parent))

from qgis.PyQt.QtCore import QVariant  # noqa: E402
from qgis.core import (  # noqa: E402
    NULL,
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsCoordinateTransformContext,
    QgsDistanceArea,
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsPointXY,
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsProcessingUtils,
    QgsProject,
    QgsVectorLayer,
)

_APP = QgsApplication.instance()
_PROFILE = None
if _APP is None:
    _PROFILE = tempfile.TemporaryDirectory(prefix="pln3113_nip-values-")
    _APP = QgsApplication([], False, _PROFILE.name, "external")
    _APP.initQgis()

from pln3113_nip.core.nip_calculator import NipCalculatorEngine as E  # noqa: E402

X0, Y0 = 500000.0, 4200000.0  # EPSG:5253 (TM27) merkez meridyeni: ölçek ~1
KONUT = "Gelişme Konut Alanı (Orta Yoğunluk)"


_PROVIDERS = []  # Python sağlayıcısı çöp toplanmasın diye referans tutulur


def _registry_alg(alg_id):
    reg = QgsApplication.processingRegistry()
    if reg.providerById("pln3113") is None:
        from pln3113_nip.provider import NipEklentiProvider
        _PROVIDERS.append(NipEklentiProvider())
        reg.addProvider(_PROVIDERS[-1])
    alg = reg.createAlgorithmById(alg_id)
    if alg is None:
        raise RuntimeError(f"Algoritma bulunamadı: {alg_id}")
    return alg


class _Feedback(QgsProcessingFeedback):
    def __init__(self, cancel=False):
        super().__init__()
        self.warnings, self.errors, self.infos = [], [], []
        if cancel:
            self.cancel()

    def pushWarning(self, msg):  # noqa: N802
        self.warnings.append(msg)

    def reportError(self, msg, fatalError=False):  # noqa: N802,N803
        self.errors.append(msg)

    def pushInfo(self, msg):  # noqa: N802
        self.infos.append(msg)


def _rect(x, y, w, h):
    return QgsGeometry.fromPolygonXY([[QgsPointXY(x, y), QgsPointXY(x + w, y), QgsPointXY(x + w, y + h),
                                       QgsPointXY(x, y + h), QgsPointXY(x, y)]])


def _poly_layer(crs, rows, name="a"):
    lyr = QgsVectorLayer(f"Polygon?crs={crs}", name, "memory")
    pr = lyr.dataProvider()
    pr.addAttributes([QgsField("fonk", QVariant.String), QgsField("keep", QVariant.Int)])
    lyr.updateFields()
    feats = []
    for g, fk, k in rows:
        f = QgsFeature(lyr.fields())
        if g is not None:
            f.setGeometry(g)
        f.setAttributes([fk, k])
        feats.append(f)
    pr.addFeatures(feats)
    lyr.updateExtents()
    return lyr


def _blocks():
    """Denetim fikstürü: 4 adet 1 ha ada (konut, park, ticaret, orman)."""
    return _poly_layer("EPSG:5253", [
        (_rect(X0, Y0, 100, 100), KONUT, 1),
        (_rect(X0 + 200, Y0, 100, 100), "Park ve Yeşil Alan", 2),
        (_rect(X0 + 400, Y0, 100, 100), "Ticaret Alanı", 3),
        (_rect(X0 + 600, Y0, 100, 100), "Orman Alanı", 4),
    ], "adalar")


def _to(geom, src, dst):
    g = QgsGeometry(geom)
    g.transform(QgsCoordinateTransform(QgsCoordinateReferenceSystem(src), QgsCoordinateReferenceSystem(dst),
                                       QgsProject.instance()))
    return g


def _boundary_4326():
    """900 x 200 m plan onama sınırı (EPSG:5253'te çizilip EPSG:4326'ya taşındı)."""
    lyr = QgsVectorLayer("Polygon?crs=EPSG:4326", "sinir", "memory")
    f = QgsFeature()
    f.setGeometry(_to(_rect(X0 - 50, Y0 - 50, 900, 200), "EPSG:5253", "EPSG:4326"))
    lyr.dataProvider().addFeatures([f])
    return lyr


def _road_4326(length_m=1000.0):
    lyr = QgsVectorLayer("LineString?crs=EPSG:4326", "yol", "memory")
    f = QgsFeature()
    line = QgsGeometry.fromPolylineXY([QgsPointXY(X0, Y0 - 25), QgsPointXY(X0 + length_m, Y0 - 25)])
    f.setGeometry(_to(line, "EPSG:5253", "EPSG:4326"))
    lyr.dataProvider().addFeatures([f])
    return lyr


def _run_population(params, feedback=None):
    QgsProject.instance().setEllipsoid("NONE")  # betik projeleri: elipsoit tanımsız (TRAPS §5.13)
    alg = _registry_alg("pln3113:tire_nip_nufus_hesapla")
    ctx = QgsProcessingContext()
    ctx.setProject(QgsProject.instance())
    fb = feedback or _Feedback()
    full = {"FONKSIYON_FIELD": "fonk", "OUTPUT_LAYER": "TEMPORARY_OUTPUT", "OUTPUT_DOP": "TEMPORARY_OUTPUT",
            "OUTPUT_KIYAS": "TEMPORARY_OUTPUT"}
    full.update(params)
    res, ok = alg.run(full, ctx, fb)
    layers = {}
    if ok:
        for k in ("OUTPUT_LAYER", "OUTPUT_DOP", "OUTPUT_KIYAS"):
            if res.get(k):
                layers[k] = QgsProcessingUtils.mapLayerFromString(res[k], ctx)
    return ok, layers, fb, ctx


def _dop_rows(lyr):
    return [(f["parametre"], f["deger_m2"], f["oran_yuzde"], f["aciklama"]) for f in lyr.getFeatures()]


class TestBoundaryCrs(unittest.TestCase):
    """N2: farklı KRS'deki sınır ve yol ada KRS'sine dönüştürülür."""

    def test_boundary_in_other_crs_keeps_all_blocks(self):
        ok, L, fb, _ = _run_population({"INPUT": _blocks(), "SINIR_LAYER": _boundary_4326()})
        self.assertTrue(ok, fb.errors)
        out = L["OUTPUT_LAYER"]
        self.assertEqual(sorted(f["keep"] for f in out.getFeatures()), [1, 2, 3, 4])
        rows = {r[0]: r for r in _dop_rows(L["OUTPUT_DOP"])}
        plan = rows["Plan Onama Sınırı / Toplam Alan"][1]
        self.assertAlmostEqual(plan / 180000.0, 1.0, delta=1e-3)
        # Gerçek sınırla yasal hüküm: (10000 kamu + 140000 yol) / (180000 - 10000 orman) = %88,24
        dop = rows["HESAPLANAN DOP ORANI (%)"]
        self.assertAlmostEqual(dop[2], 88.24, delta=0.05)
        self.assertEqual(dop[3], "YASAL SINIRI AŞIYOR")

    def test_road_in_other_crs_measured_in_metres(self):
        from pln3113_nip.core.nip_calculator import build_distance_area, prepare_boundary_and_roads
        crs = QgsCoordinateReferenceSystem("EPSG:5253")
        ctx = QgsProject.instance().transformContext()
        da, _, _ = build_distance_area(crs, ctx, "NONE")
        sinir, yol_m, uyarilar = prepare_boundary_and_roads(
            crs, ctx, da, sinir_layer=_boundary_4326(), yol_layer=_road_4326(1000.0))
        self.assertAlmostEqual(yol_m, 1000.0, delta=1.0)
        self.assertTrue(sinir.contains(_rect(X0, Y0, 100, 100)))
        self.assertTrue(any("dönüştürüldü" in u for u in uyarilar))


class TestGeographicEllipsoid(unittest.TestCase):
    """N3: coğrafi veri + proje elipsoidi 'NONE' -> doğru m² alanlar."""

    LON, LAT, D = 27.45, 38.09, 0.001

    def _geo_layer(self):
        return _poly_layer("EPSG:4326", [(_rect(self.LON, self.LAT, self.D, self.D), KONUT, 1)], "geo")

    def _equal_area_m2(self):
        # Bağımsız referans: WGS84 eşit alanlı EASE-Grid 2.0 (EPSG:6933) düzlem alanı
        return _to(_rect(self.LON, self.LAT, self.D, self.D), "EPSG:4326", "EPSG:6933").area()

    def test_calculate_with_none_ellipsoid(self):
        lg = self._geo_layer()
        da = QgsDistanceArea()
        da.setSourceCrs(lg.crs(), QgsCoordinateTransformContext())
        da.setEllipsoid("NONE")
        items, s = E.calculate(list(lg.getFeatures()), lg.fields(), "fonk", 65000, da)
        self.assertEqual(len(items), 1)
        ref = self._equal_area_m2()
        self.assertAlmostEqual(items[0]["alan_m2"] / ref, 1.0, delta=1e-3)
        self.assertAlmostEqual(items[0]["alan_m2"], 9737.25, delta=1.0)
        self.assertEqual((s["toplam_alt_nufus"], s["toplam_ust_nufus"]), (118, 243))
        self.assertTrue(any("elipsoid" in u for u in s["uyarilar"]))

    def test_algorithm_with_project_ellipsoid_none(self):
        ok, L, fb, _ = _run_population({"INPUT": self._geo_layer()})
        self.assertTrue(ok, fb.errors)
        feats = list(L["OUTPUT_LAYER"].getFeatures())
        self.assertEqual(len(feats), 1)
        self.assertAlmostEqual(feats[0]["ALT_NUFUS"], 117.8, delta=0.15)
        self.assertAlmostEqual(feats[0]["UST_NUFUS"], 243.4, delta=0.15)


class TestEstimatedDop(unittest.TestCase):
    """N6 + N4: sınır yokken DOP 'Tahmini' etiketli, yasal hüküm yok; sayılar elle."""

    def test_calculate_numbers_without_boundary(self):
        lyr = _blocks()
        da = QgsDistanceArea()
        da.setSourceCrs(lyr.crs(), QgsCoordinateTransformContext())
        da.setEllipsoid("EPSG:7019")
        items, s = E.calculate(list(lyr.getFeatures()), lyr.fields(), "fonk", 65000, da)
        self.assertEqual((s["toplam_alt_nufus"], s["toplam_ust_nufus"]), (121, 250))
        konut = [i for i in items if i["fonk_raw"] == KONUT][0]
        self.assertAlmostEqual(konut["alt_nufus"], 121.0, delta=0.1)
        self.assertAlmostEqual(konut["ust_nufus"], 250.0, delta=0.1)
        d = s["dop_ozet"]
        # yol = 0,18 x 40000 = 7200; esas = 47200 - 10000 = 37200; (10000 + 7200)/37200 = %46,24
        self.assertAlmostEqual(d["hesaplanan_yol_m2"], 7200.0, delta=1.0)
        self.assertAlmostEqual(d["dop_esas_alan_m2"], 37200.0, delta=2.0)
        self.assertAlmostEqual(d["dop_orani"], 46.24, delta=0.01)
        self.assertTrue(d["tahmini"])
        self.assertIn("TAHMİNİ", d["dop_uygunluk"])
        self.assertNotIn("AŞIYOR", d["dop_uygunluk"])
        ek2 = {r["kategori_id"]: r for r in s["ek2_rapor"]}
        # Ek-2 eğitim 6,5 m²/kişi x 65.000 = 422.500 m² gerekli (eğitim alanı yok)
        self.assertEqual(ek2["EGITIM"]["fark_proj"], -422500.0)
        # yeşil: 10000 m² / 121 kişi = 82,64 m²/kişi; gerekli 1210 -> fark 8790
        self.assertAlmostEqual(ek2["YESIL_ALAN"]["kb_alt"], 82.64, delta=0.01)
        self.assertAlmostEqual(ek2["YESIL_ALAN"]["fark_alt"], 8790.0, delta=1.0)
        # 65.000 kişi -> MPYY EK-2 "0-75.000" grubu; park kamuya ait ve DOP'a tabi: pay %100
        self.assertEqual(s["ek2_nufus_grubu"], "0-75.000")
        self.assertEqual(ek2["SOSYAL_KULTUREL"]["standart_m2"], 0.75)
        self.assertEqual(ek2["TEKNIK_ALTYAPI"]["standart_m2"], 1.0)
        self.assertEqual(ek2["YESIL_ALAN"]["kamu_dop_payi_yuzde"], 100.0)
        # kıyas: varsayılan Türkiye geneli -> Tire referansı ve +26000 yok
        self.assertEqual(len(s["kiyaslama"]), 1)
        self.assertNotIn("26", s["kiyaslama"][0]["ilce"])

    def test_ek2_population_group_thresholds(self):
        """MPYY EK-2 nüfus grupları: standart ilçe projeksiyon nüfusunun grubundan alınır."""
        lyr = _blocks()
        da = QgsDistanceArea()
        da.setSourceCrs(lyr.crs(), QgsCoordinateTransformContext())
        da.setEllipsoid("EPSG:7019")
        feats = list(lyr.getFeatures())
        # 200.000 kişi -> "150.001-500.000": eğitim 0,6+2+2+2 = 6,6; sosyal 1,25; teknik 1,5;
        # ibadet 0,75; eğitim alanı yok -> fark = -6,6 x 200.000 = -1.320.000 m²
        _items, s = E.calculate(feats, lyr.fields(), "fonk", 200000, da)
        ek2 = {r["kategori_id"]: r for r in s["ek2_rapor"]}
        self.assertEqual(s["ek2_nufus_grubu"], "150.001-500.000")
        self.assertEqual(ek2["EGITIM"]["standart_m2"], 6.6)
        self.assertEqual(ek2["EGITIM"]["fark_proj"], -1320000.0)
        self.assertEqual(ek2["SOSYAL_KULTUREL"]["gerekli_proj"], 250000.0)
        self.assertEqual(ek2["TEKNIK_ALTYAPI"]["gerekli_proj"], 300000.0)
        self.assertEqual(ek2["IBADET"]["gerekli_proj"], 150000.0)
        # ilçe projeksiyon nüfusu ayrıca verilirse grup ondan seçilir: 80.000 -> 75.001-150.000
        # sağlık 1,5 x 65.000 = 97.500; sosyal 1,0 x 65.000 = 65.000; teknik 1,25 x 65.000 = 81.250
        _items, s2 = E.calculate(feats, lyr.fields(), "fonk", 65000, da, ek2_nufus=80000)
        ek2b = {r["kategori_id"]: r for r in s2["ek2_rapor"]}
        self.assertEqual(s2["ek2_nufus_grubu"], "75.001-150.000")
        self.assertEqual(ek2b["SAGLIK"]["gerekli_proj"], 97500.0)
        self.assertEqual(ek2b["SOSYAL_KULTUREL"]["gerekli_proj"], 65000.0)
        self.assertEqual(ek2b["TEKNIK_ALTYAPI"]["gerekli_proj"], 81250.0)
        # 600.000 kişi -> "501.000+": sağlık 1,6; teknik 2,0
        _items, s3 = E.calculate(feats, lyr.fields(), "fonk", 600000, da)
        ek2c = {r["kategori_id"]: r for r in s3["ek2_rapor"]}
        self.assertEqual(s3["ek2_nufus_grubu"], "501.000+")
        self.assertEqual(ek2c["SAGLIK"]["gerekli_proj"], 960000.0)
        self.assertEqual(ek2c["TEKNIK_ALTYAPI"]["gerekli_proj"], 1200000.0)

    def test_ek2_semt_spor_and_ozel_rules(self):
        """EK-2 Açıklama 8-9: semt spor alanı yeşil alana, ÖZEL sağlık sağlık standardına sayılır;
        ÖZEL sağlık DOP'ta yine özel tahsistir; otopark teknik altyapıya sayılmaz."""
        lyr = _poly_layer("EPSG:5253", [
            (_rect(X0, Y0, 100, 100), KONUT, 1),
            (_rect(X0 + 200, Y0, 100, 100), "Semt Spor Alanı", 2),
            (_rect(X0 + 400, Y0, 100, 100), "Özel Sağlık Alanı", 3),
            (_rect(X0 + 600, Y0, 100, 100), "Genel Otopark Alanı", 4),
        ], "adalar2")
        da = QgsDistanceArea()
        da.setSourceCrs(lyr.crs(), QgsCoordinateTransformContext())
        da.setEllipsoid("EPSG:7019")
        _items, s = E.calculate(list(lyr.getFeatures()), lyr.fields(), "fonk", 65000, da)
        ek2 = {r["kategori_id"]: r for r in s["ek2_rapor"]}
        self.assertAlmostEqual(ek2["YESIL_ALAN"]["toplam_m2"], 10000.0, delta=2.0)
        self.assertAlmostEqual(ek2["SAGLIK"]["toplam_m2"], 10000.0, delta=2.0)
        self.assertAlmostEqual(ek2["SAGLIK"]["ozel_m2"], 10000.0, delta=2.0)
        self.assertEqual(ek2["TEKNIK_ALTYAPI"]["toplam_m2"], 0.0)
        self.assertAlmostEqual(s["dop_ozet"]["toplam_ozel_tahsis_m2"], 20000.0, delta=4.0)
        self.assertTrue(any("Açıklama 8" in u for u in s["uyarilar"]))

    def test_algorithm_labels_estimate(self):
        ok, L, fb, _ = _run_population({"INPUT": _blocks()})
        self.assertTrue(ok, fb.errors)
        rows = _dop_rows(L["OUTPUT_DOP"])
        names = [r[0] for r in rows]
        self.assertIn("TAHMİNİ DOP ORANI (%)", names)
        self.assertNotIn("HESAPLANAN DOP ORANI (%)", names)
        self.assertIn("Net Yol ve Ulaşım Ağı Alanı (Tahmini)", names)
        verdicts = " ".join(str(r[3]) for r in rows)
        self.assertNotIn("YASAL SINIRI AŞIYOR", verdicts)
        self.assertNotIn("YASAL SINIRDA", verdicts)
        self.assertTrue(any("TAHMİN" in w for w in fb.warnings), fb.warnings)

    def test_rural_population_and_tire_preset_are_parameters(self):
        # Varsayılan (Türkiye geneli): Tire referansı yok, kırsal ek yok
        ok, L, fb, _ = _run_population({"INPUT": _blocks()})
        self.assertTrue(ok, fb.errors)
        rows = [(f["kapsam"], f["ilce_geneli"]) for f in L["OUTPUT_KIYAS"].getFeatures()]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][1], "Kırsal nüfus girilmedi")
        # Tire örnek ön ayarı + kullanıcı kırsal nüfusu
        ok, L, fb, _ = _run_population({"INPUT": _blocks(), "KIRSAL_NUFUS": 30000, "KIYAS_REFERANSI": 1})
        self.assertTrue(ok, fb.errors)
        rows = [(f["kapsam"], f["ilce_geneli"]) for f in L["OUTPUT_KIYAS"].getFeatures()]
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[-1][1], "30.121 - 30.250")


class TestNullsAndCancel(unittest.TestCase):
    """N12 + N9: NULL'lar sayılır/uyarılır; iptal çıktı yazmaz."""

    def test_dropped_and_null_blocks_counted(self):
        lyr = _poly_layer("EPSG:5253", [
            (_rect(X0, Y0, 100, 100), KONUT, 1),
            (_rect(X0 + 200, Y0, 100, 100), NULL, 2),
            (None, KONUT, 3),
            (_rect(X0 + 5000, Y0, 100, 100), KONUT, 4),
        ])
        sinir = _rect(X0 - 10, Y0 - 10, 400, 200)
        items, s = E.calculate(list(lyr.getFeatures()), lyr.fields(), "fonk", 65000, None, sinir_geom=sinir)
        self.assertEqual(len(items), 2)
        self.assertEqual(s["elenen_ada"]["bos_geometri"], 1)
        self.assertEqual(s["elenen_ada"]["sinir_disi"], 1)
        self.assertEqual(s["elenen_ada"]["fonksiyonu_bos"], 1)
        text = " ".join(s["uyarilar"])
        self.assertIn("boş/geçersiz geometri", text)
        self.assertIn("sınırı dışında", text)
        self.assertIn("NULL", text)

    def test_facility_null_population_and_capacity_warned(self):
        road = QgsVectorLayer("LineString?crs=EPSG:5253", "yol", "memory")
        f = QgsFeature()
        f.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(X0, Y0), QgsPointXY(X0 + 1000, Y0)]))
        road.dataProvider().addFeatures([f])
        dem = QgsVectorLayer("Point?crs=EPSG:5253", "talep", "memory")
        dem.dataProvider().addAttributes([QgsField("nufus", QVariant.Double)])
        dem.updateFields()
        feats = []
        for x, p in ((X0 + 100, 10.0), (X0 + 200, NULL), (X0 + 300, 5.0)):
            q = QgsFeature(dem.fields())
            q.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, Y0)))
            q.setAttributes([p])
            feats.append(q)
        dem.dataProvider().addFeatures(feats)
        fac = QgsVectorLayer("Point?crs=EPSG:5253", "donati", "memory")
        fac.dataProvider().addAttributes([QgsField("kap", QVariant.Double)])
        fac.updateFields()
        q = QgsFeature(fac.fields())
        q.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(X0, Y0)))
        q.setAttributes([NULL])
        fac.dataProvider().addFeatures([q])

        alg = _registry_alg("pln3113:nip_2sfca_yeterlilik")
        ctx = QgsProcessingContext()
        ctx.setProject(QgsProject.instance())
        fb = _Feedback()
        res, ok = alg.run({"NETWORK": road, "DEMAND": dem, "POP_FIELD": "nufus", "FACILITIES": fac,
                           "CAPACITY_FIELD": "kap", "DEFAULT_CAPACITY": 100.0, "MAX_COST": 800.0,
                           "OUT_FACILITIES": "TEMPORARY_OUTPUT", "OUT_DEMAND": "TEMPORARY_OUTPUT"}, ctx, fb)
        self.assertTrue(ok, fb.errors)
        out = QgsProcessingUtils.mapLayerFromString(res["OUT_FACILITIES"], ctx)
        row = next(out.getFeatures())
        self.assertEqual(row["atanan_nufus"], 15.0)  # NULL nüfus 1 kişi sayılmaz
        self.assertEqual(row["kapasite"], 100.0)
        text = " ".join(fb.warnings)
        self.assertIn("1 talep noktasında nüfus değeri boş", text)
        self.assertIn("1 donatıda kapasite değeri boş", text)

    def test_population_cancel_writes_nothing(self):
        ok, L, fb, _ = _run_population({"INPUT": _blocks()}, feedback=_Feedback(cancel=True))
        self.assertFalse(ok)
        self.assertEqual(L, {})
        self.assertTrue(any("iptal" in e for e in fb.errors), fb.errors)

    def test_saha_refuses_feet_crs(self):
        ada = _poly_layer("EPSG:2229", [(_rect(6500000, 1800000, 300, 300), "konut", 1)])
        bina = _poly_layer("EPSG:2229", [(_rect(6500010, 1800010, 50, 50), "bina", 1)])
        alg = _registry_alg("pln3113:tire_saha_bina_nufus")
        ctx = QgsProcessingContext()
        ctx.setProject(QgsProject.instance())
        fb = _Feedback()
        res, ok = alg.run({"ADA_LAYER": ada, "BINA_LAYER": bina, "OUTPUT_ADA": "TEMPORARY_OUTPUT",
                           "OUTPUT_OZET": "TEMPORARY_OUTPUT"}, ctx, fb)
        self.assertFalse(ok)
        self.assertTrue(any("metre" in e for e in fb.errors), fb.errors)


def main():
    result = unittest.main(module=__name__, exit=False, verbosity=2).result
    return result.wasSuccessful()


if __name__ == "__main__":
    _ok = main()
    if _PROFILE is not None:
        _APP.exitQgis()
    sys.exit(0 if _ok else 1)
