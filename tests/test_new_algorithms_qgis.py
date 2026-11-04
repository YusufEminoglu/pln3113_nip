# -*- coding: utf-8 -*-
"""QGIS değer testleri: nüfus projeksiyonu, kohort, mahalle dağıtımı, kırılganlık.

Çalıştırma (monorepo kökünden, offscreen):
    python-qgis-ltr.bat -m pln3113_nip.tests.test_new_algorithms_qgis
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PLUGIN_DIR = Path(__file__).resolve().parent.parent
if str(PLUGIN_DIR.parent) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR.parent))

from qgis.core import (  # noqa: E402
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsRectangle,
    QgsVectorLayer,
)

PROVIDER_ID = "pln3113"
_RESULTS = []


def _ok(name, condition, detail=""):
    tag = "PASS" if condition else "FAIL"
    print(f"  [{tag}] {name}" + (f" - {detail}" if detail else ""))
    _RESULTS.append(bool(condition))
    return bool(condition)


def _layer(uri, name, fields, rows):
    """rows: [(geometry or None, [values])]; fields: 'ad:tip' listesi (memory URI biçimi)."""
    spec = uri + ("&" if "?" in uri else "?") + "&".join(f"field={f}" for f in fields)
    lyr = QgsVectorLayer(spec, name, "memory")
    feats = []
    for geom, values in rows:
        f = QgsFeature(lyr.fields())
        if geom is not None:
            f.setGeometry(geom)
        f.setAttributes(values)
        feats.append(f)
    lyr.dataProvider().addFeatures(feats)
    lyr.updateExtents()
    return lyr


def _square(x0, y0, size):
    return QgsGeometry.fromRect(QgsRectangle(x0, y0, x0 + size, y0 + size))


def _null(value):
    return value is None or (hasattr(value, "isNull") and value.isNull())


def _rows_by(layer, key):
    return {f[key]: f for f in layer.getFeatures()}


def _raises(alg, params, word=None):
    import processing
    try:
        processing.run(alg, params)
    except QgsProcessingException as exc:
        return word is None or word in str(exc)
    return False


def test_registration():
    reg = QgsApplication.processingRegistry()
    ids = ["nufus_projeksiyonu", "kohort_projeksiyonu", "mahalle_dagitimi",
           "kirilganlik_endeksi"]
    missing = [i for i in ids if reg.algorithmById(f"{PROVIDER_ID}:{i}") is None]
    _ok("four new algorithms registered", not missing, f"missing={missing}")
    alg = reg.algorithmById(f"{PROVIDER_ID}:kirilganlik_endeksi")
    _ok("help text is Turkish and attributes Kent Öngörü",
        alg is not None and "Kent Öngörü" in alg.shortHelpString()
        and "Kırılganlık" in alg.displayName())


def test_projection():
    import processing
    res = processing.run(f"{PROVIDER_ID}:nufus_projeksiyonu", {
        "YILLAR": "2007, 2025", "NUFUSLAR": "76327, 87528", "HEDEF_YIL": 2045,
        "YONTEMLER": [0, 1, 2], "YENI_ISTIHDAM": 1000, "CALISAN_BASINA": 2.8,
        "OUTPUT": "memory:", "SERI": "memory:"})
    rows = _rows_by(res["OUTPUT"], "yontem")
    geo = rows.get("geometrik")
    _ok("geometric 2045 = 101,911.6 (hand value)",
        geo is not None and abs(geo["tahmin"] - 101911.6) < 0.1,
        f"got {geo['tahmin'] if geo else None}")
    _ok("economic base adds jobs × persons per worker (1000 × 2.8)",
        geo is not None and abs(geo["tahmin_goc_dahil"] - geo["tahmin"] - 2800.0) < 1e-6)
    ib = rows.get("iller_bankasi")
    # hesaplanan hız %0.763 -> %1'e çekilir: 87,528 × 1.01^20 = 106,800.6
    _ok("İller Bankası clamps 0.763 %/yıl to 1 % and warns",
        ib is not None and abs(ib["tahmin"] - 87528 * 1.01 ** 20) < 1e-6
        and "aralığına çekildi" in str(ib["uyarilar"]))
    _ok("annual series table 2007..2045 per method",
        res["SERI"].featureCount() == 3 * (2045 - 2007 + 1),
        f"rows={res['SERI'].featureCount()}")
    _ok("TAHMINLER summary returned for the dock",
        abs(res["TAHMINLER"]["aritmetik"] - (99973.555 + 2800)) < 0.01)

    table = _layer("None", "seri", ["yil:integer", "nufus:double"],
                   [(None, [2020, 300.0]), (None, [2000, 100.0]), (None, [2010, 200.0]),
                    (None, [2015, None])])
    fb = QgsProcessingFeedback()
    res2 = processing.run(f"{PROVIDER_ID}:nufus_projeksiyonu", {
        "TABLO": table, "YIL_ALANI": "yil", "NUFUS_ALANI": "nufus", "HEDEF_YIL": 2030,
        "YONTEMLER": [3, 4], "OUTPUT": "memory:"}, feedback=fb)
    rows2 = _rows_by(res2["OUTPUT"], "yontem")
    _ok("table input sorted by year, NULL row skipped; regression 2030 = 400",
        abs(rows2["regresyon"]["tahmin"] - 400.0) < 1e-6 and abs(rows2["regresyon"]["r2"] - 1) < 1e-9)
    _ok("polynomial row on 3 points works", _null(rows2["polinom"]["hata"])
        and abs(rows2["polinom"]["tahmin"] - 400.0) < 1e-6)
    _ok("non-increasing years rejected in Turkish",
        _raises(f"{PROVIDER_ID}:nufus_projeksiyonu", {
            "YILLAR": "2010, 2005", "NUFUSLAR": "1, 2", "HEDEF_YIL": 2030,
            "OUTPUT": "memory:"}, "artan"))
    _ok("non-positive population rejected",
        _raises(f"{PROVIDER_ID}:nufus_projeksiyonu", {
            "YILLAR": "2000, 2010", "NUFUSLAR": "100, 0", "HEDEF_YIL": 2030,
            "OUTPUT": "memory:"}, "pozitif"))


def test_cohort():
    import processing
    res = processing.run(f"{PROVIDER_ID}:kohort_projeksiyonu", {
        "BAZ_YIL": 2025, "HEDEF_YIL": 2032,
        "ERKEK": ", ".join(["3000"] * 17), "KADIN": ", ".join(["3100"] * 17),
        "GOC_TURU": 2, "GOC_DEGERI": 200,
        "OUTPUT": "memory:", "GOSTERGELER": "memory:"})
    pyr = res["OUTPUT"]
    _ok("pyramid has 2025, 2030, 2035 and interpolated 2032 (4 × 17 rows)",
        pyr.featureCount() == 68, f"rows={pyr.featureCount()}")
    interp = [f for f in pyr.getFeatures() if f["enterpole"] == 1]
    tot_2032 = sum(f["toplam"] for f in interp)
    _ok("TOPLAM_HEDEF equals the interpolated 2032 pyramid total",
        len(interp) == 17 and abs(tot_2032 - res["TOPLAM_HEDEF"]) < 1e-6)
    ind = {f["yil"]: f for f in res["GOSTERGELER"].getFeatures()}
    _ok("indicator table: base-year total 103,700 and net migration 1,000 per step",
        abs(ind[2025.0]["toplam"] - 103700.0) < 1e-6 and abs(ind[2030.0]["net_goc"] - 1000.0) < 1e-6)
    table = _layer("None", "yas", ["grup:string", "e:double", "k:double"],
                   [(None, [g, 100.0, 100.0]) for g in
                    ["80 ve üzeri"] + [f"{5 * i}–{5 * i + 4}" for i in range(16)]])
    res2 = processing.run(f"{PROVIDER_ID}:kohort_projeksiyonu", {
        "BAZ_YIL": 2025, "HEDEF_YIL": 2030, "TABLO": table, "YAS_ALANI": "grup",
        "ERKEK_ALANI": "e", "KADIN_ALANI": "k", "OUTPUT": "memory:"})
    _ok("age table with '0–4' and '80 ve üzeri' labels accepted",
        res2["OUTPUT"].featureCount() == 34)


def test_allocation():
    import processing
    zones = _layer("Polygon?crs=EPSG:5253", "mah",
                   ["kod:string", "nufus:double", "bolge:string", "kap:double"],
                   [(_square(200, 0, 100), ["C", 300.0, "Kırsal", 330.0]),
                    (_square(0, 0, 100), ["A", 100.0, "GELİŞME", 1000.0]),
                    (_square(100, 0, 100), ["B", 200.0, "gelişme", None])])
    res = processing.run(f"{PROVIDER_ID}:mahalle_dagitimi", {
        "GIRDI": zones, "ANAHTAR": "kod", "NUFUS": "nufus", "HEDEF": 1000, "YONTEM": 0,
        "OUTPUT": "memory:"})
    out = _rows_by(res["OUTPUT"], "kod")
    _ok("proportional allocation joined by key: A 167, B 333, C 500",
        (out["A"]["hedef_nufus"], out["B"]["hedef_nufus"], out["C"]["hedef_nufus"])
        == (167, 333, 500))
    _ok("geometry kept for each key",
        abs(out["C"].geometry().boundingBox().xMinimum() - 200) < 1e-9)
    res2 = processing.run(f"{PROVIDER_ID}:mahalle_dagitimi", {
        "GIRDI": zones, "ANAHTAR": "kod", "NUFUS": "nufus", "HEDEF": 1000, "YONTEM": 1,
        "BOLGE_ALANI": "bolge", "BOLGE_PAYLARI": "Gelişme=0.75; KIRSAL=0.25",
        "OUTPUT": "memory:"})
    out2 = _rows_by(res2["OUTPUT"], "kod")
    # artış 400: gelişme 300 (A +100, B +200), kırsal 100 (C +100)
    _ok("zone shares matched across Turkish case (GELİŞME/gelişme, KIRSAL/Kırsal)",
        (out2["A"]["hedef_nufus"], out2["B"]["hedef_nufus"], out2["C"]["hedef_nufus"])
        == (200, 400, 400))
    res3 = processing.run(f"{PROVIDER_ID}:mahalle_dagitimi", {
        "GIRDI": zones, "ANAHTAR": "kod", "NUFUS": "nufus", "HEDEF": 1000, "YONTEM": 2,
        "KAPASITE_ALANI": "kap", "OUTPUT": "memory:"})
    out3 = _rows_by(res3["OUTPUT"], "kod")
    # boş kapasite A 900, C 30 (B NULL): artış 400 -> A +387.1, C +12.9 -> 487 / 313
    _ok("capacity-capped allocation, NULL capacity gets no growth, total exact",
        out3["B"]["hedef_nufus"] == 200 and out3["A"]["hedef_nufus"] == 487
        and out3["C"]["hedef_nufus"] == 313 and res3["DAGITILAN"] == 1000)
    dup = _layer("None", "dup", ["kod:string", "nufus:double"],
                 [(None, ["A", 1.0]), (None, ["A", 2.0])])
    _ok("duplicate key rejected",
        _raises(f"{PROVIDER_ID}:mahalle_dagitimi", {
            "GIRDI": dup, "ANAHTAR": "kod", "NUFUS": "nufus", "HEDEF": 10, "YONTEM": 0,
            "OUTPUT": "memory:"}, "tekrar"))


def _dem(path):
    """İki bölgeyi kapsayan 200 × 100 m DEM: A (x<100) = 10 m, B = 30 m."""
    from osgeo import gdal
    drv = gdal.GetDriverByName("GTiff")
    ds = drv.Create(path, 20, 10, 1, gdal.GDT_Float32)
    ds.SetGeoTransform((0.0, 10.0, 0.0, 100.0, 0.0, -10.0))
    ds.SetProjection(QgsCoordinateReferenceSystem("EPSG:5253").toWkt())
    band = ds.GetRasterBand(1)
    import numpy as np
    arr = np.full((10, 20), 30.0, dtype=np.float32)
    arr[:, :10] = 10.0
    band.WriteArray(arr)
    band.SetNoDataValue(-9999)
    ds.FlushCache()
    ds = None
    return path


def test_vulnerability(tmpdir):
    import processing
    zones = _layer("Polygon?crs=EPSG:5253", "bolge",
                   ["mah:string", "nufus:double", "cocuk:double", "yasli:double",
                    "yapi_tipi:string"],
                   [(_square(100, 0, 100), ["B", 30.0, 3.0, 3.0, "Betonarme"]),
                    (_square(0, 0, 100), ["A<x>", 150.0, 45.0, 30.0, "YIĞMA"])])
    yapi = _layer("Polygon?crs=EPSG:5253", "yapi", ["malzeme:string", "kat:integer"],
                  [(_square(10, 10, 50), ["YIĞMA", 2]),
                   (_square(110, 10, 20), ["Betonarme Karkas", 6]),
                   (_square(150, 10, 20), [None, 4])])
    report = os.path.join(tmpdir, "rapor.html")
    res = processing.run(f"{PROVIDER_ID}:kirilganlik_endeksi", {
        "BOLGE": zones, "ANAHTAR": "mah", "TEHLIKELER": [0, 2],
        "YAPI": yapi, "MALZEME_ALANI": "malzeme", "KAT_ALANI": "kat",
        "DEM": _dem(os.path.join(tmpdir, "dem.tif")),
        "SINIFLAMA": 2, "OUTPUT": "memory:", "RAPOR": report})
    out = _rows_by(res["OUTPUT"], "mah")
    a, b = out["A<x>"], out["B"]
    _ok("upper-case Turkish 'YIĞMA' building scores 4, 'Betonarme Karkas' scores 2",
        a["K_D_YMZ"] == 4 and b["K_D_YMZ"] == 2, f"A={a['K_D_YMZ']} B={b['K_D_YMZ']}")
    # A: 150 kişi / 1 ha -> 3 ; B: 30 kişi/ha -> 1 ; yaşlı %20 -> 4 (<=20) ; çocuk %30 -> 5
    _ok("density-based population score (150 kişi/ha = 3, 30 kişi/ha = 1)",
        a["K_D_SN"] == 3 and b["K_D_SN"] == 1)
    _ok("ratio indicators by auto-detected fields (yaşlı %20 -> 4, çocuk %30 -> 5)",
        a["K_D_SY"] == 4 and a["K_D_SC"] == 5)
    # TAKS A = 2500/10000 = 0.25 -> 2 ; B = 800/10000 = 0.08 -> 1
    _ok("TAKS from building overlay (0.25 -> 2, 0.08 -> 1)",
        a["K_D_MT"] == 2 and b["K_D_MT"] == 1)
    _ok("flood relative elevation: low zone 5, +20 m zone 3",
        a["K_Y_FR"] == 5 and b["K_Y_FR"] == 3, f"A={a['K_Y_FR']} B={b['K_Y_FR']}")
    # Deprem eksik: FAY, YD, ENK, TOP, ITF, HST, TYL = 7
    _ok("missing indicators counted, scored neutral 1",
        a["K_D_EKSIK"] == 7 and _null(a["K_D_FAY"]), f"eksik={a['K_D_EKSIK']}")
    # A pay: YMZ 4 × YK(2 -> <3:2) × MT 2 × SN 3 × SY 4 × SC 5 = 960 ; payda 1
    _ok("pay/payda index K_D for A = 4·2·2·3·4·5 = 960",
        abs(a["K_D"] - 960.0) < 1e-9 and abs(a["K_D_PAYDA"] - 1.0) < 1e-9, f"K_D={a['K_D']}")
    _ok("composite index and classes written (A most vulnerable = 1. derece)",
        a["K_BIL"] == 100.0 and b["K_BIL"] == 0.0 and a["BIL_DERECE"] == 1
        and b["BIL_DERECE"] == 5)
    text = Path(report).read_text(encoding="utf-8")
    _ok("HTML report written with escaped keys", "A&lt;x&gt;" in text and "A<x>" not in text)

    res2 = processing.run(f"{PROVIDER_ID}:kirilganlik_endeksi", {
        "BOLGE": zones, "ANAHTAR": "mah", "TEHLIKELER": [],
        "OZEL": "YM | Yapı tipi | pay | alan:yapi_tipi | yığma=4; *=2\n"
                "SN | Yoğunluk | pay | yogunluk | <=100:1; *:5",
        "OUTPUT": "memory:"})
    out2 = _rows_by(res2["OUTPUT"], "mah")
    _ok("custom index: zone text 'YIĞMA' matches keyword 'yığma'",
        out2["A<x>"]["K_O_YM"] == 4 and out2["B"]["K_O_YM"] == 2
        and abs(out2["A<x>"]["K_O"] - 20.0) < 1e-9)

    fb = QgsProcessingFeedback()
    fb.cancel()
    canceled = False
    try:
        processing.run(f"{PROVIDER_ID}:kirilganlik_endeksi", {
            "BOLGE": zones, "ANAHTAR": "mah", "TEHLIKELER": [2], "OUTPUT": "memory:"},
            feedback=fb)
    except QgsProcessingException as exc:
        canceled = "iptal" in str(exc)
    _ok("cancel raises instead of writing partial output", canceled)
    _ok("distance measure refuses geographic CRS",
        _raises(f"{PROVIDER_ID}:kirilganlik_endeksi", {
            "BOLGE": _layer("Polygon?crs=EPSG:4326", "geo", ["mah:string"],
                            [(_square(27, 38, 0.01), ["G"])]),
            "ANAHTAR": "mah", "TEHLIKELER": [],
            "OZEL": "FD | Dere | pay | uzaklik:dere | <=100:5; *:1",
            "DERE": _layer("LineString?crs=EPSG:4326", "dere", ["ad:string"],
                           [(QgsGeometry.fromPolylineXY([QgsPointXY(27, 38),
                                                         QgsPointXY(27.1, 38)]), ["d"])]),
            "OUTPUT": "memory:"}, "metre"))


def run_all(tmpdir):
    print("=" * 60)
    print("pln3113_nip new algorithms (QGIS)")
    print("=" * 60)
    for fn in (test_registration, test_projection, test_cohort, test_allocation):
        fn()
    test_vulnerability(tmpdir)
    passed = sum(_RESULTS)
    print("-" * 60)
    print(f"  {passed}/{len(_RESULTS)} passed")
    return passed == len(_RESULTS)


def main():
    app = QgsApplication.instance()
    owns = app is None
    profile = tempfile.TemporaryDirectory(prefix="pln3113_nip-newalg-")
    if owns:
        app = QgsApplication([], False, profile.name, "external")
        app.initQgis()
    plugins_dir = os.path.join(QgsApplication.prefixPath(), "python", "plugins")
    if os.path.exists(plugins_dir) and plugins_dir not in sys.path:
        sys.path.append(plugins_dir)
    from processing.core.Processing import Processing
    from qgis.analysis import QgsNativeAlgorithms
    reg = QgsApplication.processingRegistry()
    if reg.providerById("native") is None:
        reg.addProvider(QgsNativeAlgorithms())
    Processing.initialize()
    provider = None
    if reg.providerById(PROVIDER_ID) is None:
        from pln3113_nip.provider import NipProvider
        provider = NipProvider()
        reg.addProvider(provider)
    try:
        return run_all(profile.name)
    finally:
        if provider is not None:
            reg.removeProvider(provider)
        if owns:
            app.exitQgis()
        profile.cleanup()


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
