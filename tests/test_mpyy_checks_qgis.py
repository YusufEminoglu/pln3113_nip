# -*- coding: utf-8 -*-
"""QGIS değer testleri: MPYY NİP "Kontrol" alanı ve MPYY yol platformu.

Çalıştırma (monorepo kökünden, offscreen):
    python-qgis-ltr.bat -m pln3113_nip.tests.test_mpyy_checks_qgis
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PLUGIN_DIR = Path(__file__).resolve().parent.parent
if str(PLUGIN_DIR.parent) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR.parent))

from qgis.core import (  # noqa: E402
    QgsApplication,
    QgsFeature,
    QgsFieldConstraints,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsRectangle,
    QgsVectorLayer,
    QgsVectorLayerUtils,
)

_RESULTS = []
X0, Y0 = 500000.0, 4200000.0


def _ok(name, condition, detail=""):
    tag = "PASS" if condition else "FAIL"
    print(f"  [{tag}] {name}" + (f" - {detail}" if detail else ""))
    _RESULTS.append(bool(condition))
    return bool(condition)


def _rect(x0, y0, x1, y1):
    g = QgsGeometry.fromRect(QgsRectangle(X0 + x0, Y0 + y0, X0 + x1, Y0 + y1))
    g.convertToMultiType()
    return g


def _line(*pts):
    return QgsGeometry.fromPolylineXY([QgsPointXY(X0 + x, Y0 + y) for x, y in pts])


def _add(layer, geom, **attrs):
    f = QgsFeature(layer.fields())
    f.setGeometry(geom)
    for k, v in attrs.items():
        f.setAttribute(layer.fields().indexOf(k), v)
    layer.dataProvider().addFeatures([f])
    return f


def _kontrol(layer):
    layer.reload()
    return {f.id(): f["Kontrol"] for f in layer.getFeatures()}


def _text(v):
    return "" if v is None or (hasattr(v, "isNull") and v.isNull()) else str(v)


def test_checks(tmpdir):
    from pln3113_nip.core.nip_workspace import create_nip_workspace, find_mpyy_layer, load_nip_layers

    print("MPYY NİP Kontrol alanı")
    gpkg = os.path.join(tmpdir, "nip.gpkg")
    create_nip_workspace(gpkg, crs="EPSG:5253")

    con = sqlite3.connect(gpkg)
    qml = con.execute("SELECT styleQML FROM layer_styles WHERE f_table_name='GelismeKonut'").fetchone()[0]
    cols = [r[1] for r in con.execute("PRAGMA table_info('GelismeKonut')")]
    con.close()
    _ok("kayıtlı stilde Kontrol sanal alanı var", 'name="Kontrol"' in qml and "expressionfields" in qml)
    _ok("kayıtlı stilde koşullu satır stili var", "NİP kontrol" in qml)
    _ok("GeoPackage tablosuna sütun eklenmedi (XSD şeması korunur)", "Kontrol" not in cols, str(cols))

    project = QgsProject.instance()
    project.clear()
    load_nip_layers(gpkg, project=project)
    konut = find_mpyy_layer("GelismeKonut", project)
    egitim = find_mpyy_layer("EgitimTesisAlani", project)
    sinir = find_mpyy_layer("PlanSiniri", project)
    _ok("katmanlar MPYY türüyle bulunuyor", None not in (konut, egitim, sinir))
    _ok("Kontrol tablo sütunlarının başında",
        konut.attributeTableConfig().columns()[0].name == "Kontrol")

    _add(sinir, _rect(0, 0, 1000, 1000), Pin=1.0, PlanAdi="Test")
    full = dict(GelismeKonutAlaniYogunluk="DusukYogunluk", YogunlukDeger=60)
    _add(konut, _rect(0, 0, 200, 200), **full)                 # B ile çakışır, Eğitim ile çakışır
    _add(konut, _rect(150, 150, 300, 300))                           # A ile çakışır, öznitelik eksik
    _add(konut, _rect(200, 0, 400, 100), **full)                     # A'ya yalnız kenarla değer
    bow = QgsGeometry.fromWkt(
        f"MultiPolygon((({X0 + 800} {Y0 + 300}, {X0 + 900} {Y0 + 400}, {X0 + 900} {Y0 + 300}, "
        f"{X0 + 800} {Y0 + 400}, {X0 + 800} {Y0 + 300})))")
    _add(konut, bow, **full)                                         # papyon: geçersiz
    _add(konut, _rect(700, 700, 705, 705), **full)                   # 25 m²
    _add(konut, _rect(950, 0, 1100, 100), **full)                    # plan sınırı dışına taşar
    _add(egitim, _rect(100, -100, 140, 50), Adi="Okul", EgitimTesisTip="Ilkokul")

    k = {i: _text(v) for i, v in _kontrol(konut).items()}
    ids = sorted(k)
    print("    ", k)
    _ok("1: aynı katmanda çakışma ve Eğitim ile çakışma",
        "aynı katmanda çakışma" in k[ids[0]] and "çakışma: Egitim Tesis Alani" in k[ids[0]])
    _ok("1: dolu öznitelikte 'eksik' yok", "eksik" not in k[ids[0]])
    _ok("2: çakışma ve eksik öznitelik",
        "aynı katmanda çakışma" in k[ids[1]] and "eksik: Gelisme Konut Alani Yogunluk" in k[ids[1]]
        and "eksik: Yogunluk Deger" in k[ids[1]])
    _ok("3: yalnız kenarla değen komşu temiz", k[ids[2]] == "", k[ids[2]])
    _ok("4: papyon geçersiz geometri", "geçersiz geometri" in k[ids[3]])
    _ok("5: 25 m² çok küçük parça", "çok küçük parça" in k[ids[4]])
    _ok("6: plan sınırı dışına taşıyor", "plan sınırı dışına taşıyor" in k[ids[5]])
    eg = list(_kontrol(egitim).values())[0]
    _ok("Eğitim: konutla çakışma, plan dışı", "çakışma: Gelisme Konut" in _text(eg)
        and "plan sınırı dışına" in _text(eg), _text(eg))

    idx = konut.fields().indexOf("Kontrol")
    soft = QgsFieldConstraints.ConstraintStrength.ConstraintStrengthSoft
    feats = {f.id(): f for f in konut.getFeatures()}
    ok_bad, _ = QgsVectorLayerUtils.validateAttribute(konut, feats[ids[0]], idx, soft)
    ok_good, _ = QgsVectorLayerUtils.validateAttribute(konut, feats[ids[2]], idx, soft)
    _ok("uyarı kısıtı: sorunlu nesnede başarısız, temizde geçer", (not ok_bad) and ok_good)
    hard = QgsFieldConstraints.ConstraintStrength.ConstraintStrengthHard
    ok_hard, _ = QgsVectorLayerUtils.validateAttribute(konut, feats[ids[0]], idx, hard)
    _ok("zorunlu (hard) kısıt yok: kayıt engellenmez", ok_hard)

    # Düzenleme kipinde yeni çizilen (henüz kaydedilmemiş) nesne de denetlenir.
    konut.startEditing()
    f = QgsFeature(konut.fields())
    f.setGeometry(_rect(10, 10, 60, 60))
    konut.addFeature(f)
    new = [x for x in konut.getFeatures() if x.id() < 0]
    _ok("kaydedilmemiş yeni nesne de çakışma gösterir",
        bool(new) and "aynı katmanda çakışma" in _text(new[0]["Kontrol"]), _text(new[0]["Kontrol"]) if new else "")
    konut.rollBack()

    # Yükleyici hızlı (uzamsal dizinli) işlevi kullanır; sonuç yerleşik ifadeyle aynıdır.
    from qgis.core import QgsExpression, QgsExpressionContext, QgsExpressionContextUtils
    from pln3113_nip.core.nip_checks import build_check_expression
    from pln3113_nip.core.nip_workspace import caption, get_nip_schema
    _ok("yüklenen katman hızlı işlevi kullanıyor", "nip_cakisma(" in konut.expressionField(idx))
    ft = next(t for t in get_nip_schema()["feature_types"] if t["name"] == "GelismeKonut")
    refs = {n: "'" + lyr.id() + "'" for n, lyr in (("EgitimTesisAlani", egitim), ("PlanSiniri", sinir))}
    native = QgsExpression(build_check_expression(ft, refs, caption))
    ctx = QgsExpressionContext(QgsExpressionContextUtils.globalProjectLayerScopes(konut))
    same = True
    for f in konut.getFeatures():
        if not f.geometry().isGeosValid():
            continue  # yerleşik ifade geçersiz geometride kesişimi hesaplayamaz
        ctx.setFeature(f)
        a = sorted(_text(native.evaluate(ctx)).split(" | "))
        b = sorted(_text(f["Kontrol"]).split(" | "))
        if a != b:
            same = False
            print("     fark", f.id(), a, b)
    _ok("hızlı ve yerleşik kontrol aynı sonucu verir", same)

    # Eklentisiz açılış: kayıtlı varsayılan stilde Kontrol alanı gelir.
    plain = QgsVectorLayer(f"{gpkg}|layername=GelismeKonut", "Gelisme Konut", "ogr")
    _ok("eklentisiz açılışta Kontrol alanı var", plain.fields().indexOf("Kontrol") >= 0)
    return gpkg, project


def test_road(project):
    from pln3113_nip.core.mpyy_road import YolProfili, platform_uret, yol_ekle
    from pln3113_nip.core.nip_workspace import find_mpyy_layer

    print("MPYY yol platformu")
    yolorta = find_mpyy_layer("Yolorta", project)
    diger = find_mpyy_layer("DigerYolNesneleri", project)
    ada = find_mpyy_layer("AdaKenari", project)

    p = YolProfili(yol_tipi="1DereceYol", serit_sayisi=1, serit_genisligi=3.5, refuj=2.0,
                   sol_kaldirim=2.0, sag_kaldirim=3.0)
    _ok("toplam genişlik 2x3,5 + 2 + 2 + 3 = 14", abs(p.toplam_genislik - 14.0) < 1e-9)
    parts = platform_uret(_line((0, 0), (100, 0)), p)
    _ok("taşıt yolu 100 x 7 = 700 m²", abs(parts["TasitYolu"].area() - 700) < 0.01, f"{parts['TasitYolu'].area():.3f}")
    _ok("refüj 100 x 2 = 200 m²", abs(parts["Refuj"].area() - 200) < 0.01)
    _ok("kaldırım 100 x (2 + 3) = 500 m²", abs(parts["Kaldirim"].area() - 500) < 0.01)
    sol = [e for e in parts["kenarlar"] if e.boundingBox().yMinimum() > Y0]
    sag = [e for e in parts["kenarlar"] if e.boundingBox().yMaximum() < Y0]
    _ok("sol kenar +6,5 m (1 + 3,5 + 2), sağ kenar -7,5 m (1 + 3,5 + 3)",
        len(sol) == 1 and abs(sol[0].boundingBox().yMinimum() - (Y0 + 6.5)) < 1e-6
        and len(sag) == 1 and abs(sag[0].boundingBox().yMaximum() - (Y0 - 7.5)) < 1e-6)

    tek = YolProfili(serit_sayisi=2, serit_genisligi=3.0, sol_kaldirim=1.5, sag_kaldirim=1.5, tek_yon=True, refuj=4)
    _ok("tek yön: refüj yok sayılır, 2x3 + 3 = 9 m", abs(tek.toplam_genislik - 9.0) < 1e-9)

    r1 = YolProfili(yol_tipi="2DereceYol", serit_sayisi=1, serit_genisligi=3.5, refuj=0.0,
                    sol_kaldirim=2.0, sag_kaldirim=2.0, kose_yaricapi=0.0)
    s1 = yol_ekle(_line((300, 500), (700, 500)), r1, yolorta, diger, ada)
    _ok("ilk yol: 1 Yolorta, 1 taşıt, 1 kaldırım, 2 ada kenarı",
        (s1["Yolorta"], s1["TasitYolu"], s1["Kaldirim"], s1["AdaKenari"]) == (1, 1, 1, 2), str(s1))
    _ok("katmanlar kaydedildi (düzenleme kipinde bırakılmadı)",
        not (yolorta.isEditable() or diger.isEditable() or ada.isEditable()))
    yo = list(yolorta.getFeatures())[0]
    _ok("Yolorta YolGenisligi = 11, YolTip = 2DereceYol",
        abs(yo["YolGenisligi"] - 11.0) < 1e-9 and yo["YolTip"] == "2DereceYol")

    s2 = yol_ekle(_line((500, 300), (500, 700)), r1, yolorta, diger, ada)
    print("    ", s2)
    feats = list(diger.getFeatures())
    overl = 0.0
    for i, a in enumerate(feats):
        for b in feats[i + 1:]:
            overl += a.geometry().intersection(b.geometry()).area()
    _ok("X kavşağında DigerYolNesneleri kendi içinde çakışmıyor", overl < 0.01, f"{overl:.4f} m²")
    union = QgsGeometry.unaryUnion([f.geometry() for f in feats]).area()
    # İki 400 x 11 platform, ortak 11 x 11 kare bir kez sayılır.
    _ok("platform toplam alanı 2 x 4400 - 121 = 8679 m²", abs(union - 8679) < 0.05, f"{union:.3f}")
    _ok("var olan kaldırım yeni taşıt yolunda açıldı", s2["degisen_platform"] >= 1)
    edges = list(ada.getFeatures())
    lengths = sorted(round(f.geometry().length(), 3) for f in edges)
    # Her kenar karşı platformda kesilir: 4 kenar x 2 parça, her parça (400 - 11) / 2 = 194,5 m
    _ok("ada kenarları kavşakta kesildi: 8 parça x 194,5 m", lengths == [194.5] * 8, str(lengths))
    _ok("AdaKenari Onerilen / 0,5", all(f["AdaKenariCizgiTip"] == "Onerilen" and f["CizgiKalinligi"] == 0.5 for f in edges))

    k = {f.id(): _text(f["Kontrol"]) for f in yolorta.getFeatures()}
    _ok("platformu olan Yolorta temiz", all(v == "" for v in k.values()), str(k))
    plat = {f.id(): _text(f["Kontrol"]) for f in diger.getFeatures()}
    _ok("platform parçaları temiz (çakışma yok)", all(v == "" for v in plat.values()), str(plat))

    _add(yolorta, _line((800, 800), (900, 800)), YolTip="2DereceYol", YolGenisligi=10.0)
    k = [_text(f["Kontrol"]) for f in yolorta.getFeatures()]
    _ok("platformsuz Yolorta 'yol platformu üretilmemiş'", any("yol platformu üretilmemiş" in v for v in k), str(k))

    konut = find_mpyy_layer("GelismeKonut", project)
    _add(konut, _rect(480, 400, 520, 450), GelismeKonutAlaniYogunluk="DusukYogunluk", YogunlukDeger=60)
    last = max(f.id() for f in konut.getFeatures())
    v = _text(konut.getFeature(last)["Kontrol"])
    _ok("yol platformuna taşan konut 'çakışma: Diger Yol Nesneleri'", "çakışma: Diger Yol Nesneleri" in v, v)

    try:
        yol_ekle(_line((0, 0), (10, 0)), YolProfili(serit_sayisi=0), yolorta, diger, ada)
        _ok("geçersiz profil reddedilir", False)
    except ValueError:
        _ok("geçersiz profil reddedilir", True)


def test_algorithms(gpkg, project):
    from qgis.core import QgsProcessingContext, QgsProcessingFeedback
    from pln3113_nip.algorithms.alg_mpyy_yol_platform import MpyyYolPlatformAlgorithm
    from pln3113_nip.algorithms.alg_nip_denetim import NipDenetimAlgorithm
    from pln3113_nip.core.nip_workspace import find_mpyy_layer

    print("Processing: platform üretimi ve denetim")
    ctx = QgsProcessingContext()
    ctx.setProject(project)
    fb = QgsProcessingFeedback()
    yolorta = find_mpyy_layer("Yolorta", project)
    diger = find_mpyy_layer("DigerYolNesneleri", project)
    ada = find_mpyy_layer("AdaKenari", project)
    _add(yolorta, _line((300, 850), (450, 850)), YolTip="1DereceYol", YolGenisligi=4.0)  # kaldırıma yetmez
    _add(yolorta, _line((300, 900), (450, 900)), YolTip="1DereceYol")                    # genişlik boş
    before = diger.featureCount()
    alg = MpyyYolPlatformAlgorithm()
    alg.initAlgorithm()
    res = alg.run({"YOLORTA": yolorta, "DIGER": diger, "ADA": ada, "KALDIRIM": 2.5, "REFUJ": 0.0,
                   "SADECE_EKSIK": True}, ctx, fb)[0]
    _ok("toplu platform: 1 üretildi, 2 atlandı (dar ve boş genişlik)",
        res["URETILEN"] == 1 and res["ATLANAN"] == 2, str(res))
    new = [f for f in diger.getFeatures()][before:]
    tasit = sum(f.geometry().area() for f in new if f["DigerYolNesneTip"] == "TasitYolu")
    kald = sum(f.geometry().area() for f in new if f["DigerYolNesneTip"] == "Kaldirim")
    _ok("10 m Yolorta, 2,5 m kaldırım: taşıt 100 x 5, kaldırım 100 x 5",
        abs(tasit - 500) < 0.01 and abs(kald - 500) < 0.01, f"{tasit:.2f} / {kald:.2f}")
    res2 = alg.run({"YOLORTA": yolorta, "DIGER": diger, "ADA": ada, "KALDIRIM": 2.5, "REFUJ": 0.0,
                    "SADECE_EKSIK": True}, ctx, fb)[0]
    _ok("ikinci çalıştırma platformu olanı yeniden üretmez", res2["URETILEN"] == 0, str(res2))

    out = os.path.join(os.path.dirname(gpkg), "bulgular.gpkg")
    audit = NipDenetimAlgorithm()
    audit.initAlgorithm()
    r = audit.run({"INPUT": gpkg, "OUTPUT": out}, ctx, fb)[0]
    found = QgsVectorLayer(r["OUTPUT"], "b", "ogr")
    kinds = {}
    for f in found.getFeatures():
        kinds.setdefault(f["kontrol"], []).append(f)
    print("    ", {k: len(v) for k, v in kinds.items()})
    _ok("denetim: geçersiz geometri bulundu", "geçersiz geometri" in kinds)
    over = [f for f in kinds.get("aynı katmanda çakışma", []) if abs(f["olcu"] - 2500) < 0.01]
    _ok("denetim: konut A-B çakışması 50 x 50 = 2500 m²", len(over) == 1)
    _ok("denetim: konut-eğitim ve konut-platform çakışması",
        len(kinds.get("çakışma", [])) >= 2)
    _ok("denetim: plan dışı taşma", "plan sınırı dışında" in kinds)
    _ok("denetim: plan içindeki boşluk", "boşluk" in kinds)
    _ok("denetim: platformsuz Yolorta", any(f["katman"] == "Yolorta" for f in kinds.get("yol platformu üretilmemiş", [])))
    _ok("denetim: eksik öznitelik", "eksik öznitelik" in kinds)
    _ok("denetim: kenarla değen komşular çakışma sayılmaz",
        not any(f["olcu"] is not None and f["olcu"] < 1 for f in kinds.get("çakışma", []) + kinds.get("aynı katmanda çakışma", [])))
    del found


def test_map_tool(project):
    from qgis.gui import QgsMapCanvas
    from pln3113_nip.core.mpyy_road import YolProfili
    from pln3113_nip.core.nip_workspace import find_mpyy_layer
    from pln3113_nip.maptools.mpyy_road_tool import MpyyYolCizimAraci, YolProfilDialog

    print("Harita aracı")
    dlg = YolProfilDialog(None, YolProfili(serit_sayisi=2, refuj=3.0))
    _ok("pencere profili geri verir (2x2x3,5 + 3 + 4 = 21 m)", abs(dlg.profil().toplam_genislik - 21.0) < 1e-9)

    class _Bar:
        def __init__(self):
            self.log = []

        def pushSuccess(self, *a):
            self.log.append(("ok",) + a)

        def pushCritical(self, *a):
            self.log.append(("err",) + a)

        def pushWarning(self, *a):
            self.log.append(("warn",) + a)

    class _Iface:
        def __init__(self):
            self.canvas = QgsMapCanvas()
            self.canvas.setDestinationCrs(find_mpyy_layer("Yolorta", project).crs())
            self.bar = _Bar()

        def mapCanvas(self):
            return self.canvas

        def messageBar(self):
            return self.bar

    iface = _Iface()
    tool = MpyyYolCizimAraci(iface, YolProfili(sol_kaldirim=1.0, sag_kaldirim=1.0))
    tool.activate()
    yolorta = find_mpyy_layer("Yolorta", project)
    n = yolorta.featureCount()
    tool.noktalar = [QgsPointXY(X0 + 100, Y0 + 950), QgsPointXY(X0 + 250, Y0 + 950)]
    tool._ciz(QgsPointXY(X0 + 260, Y0 + 950))
    _ok("önizleme platformu çizildi", tool.rb_onizleme.asGeometry().area() > 0)
    tool._bitir()
    _ok("araç yolu yazdı ve başarı mesajı verdi",
        yolorta.featureCount() == n + 1 and iface.bar.log and iface.bar.log[-1][0] == "ok", str(iface.bar.log[-1:]))
    _ok("araç sonraki yol için temizlendi", tool.noktalar == [])
    tool.deactivate()


def _mem_layers():
    diger = QgsVectorLayer("MultiPolygon?crs=EPSG:5253&field=DigerYolNesneTip:string", "DigerYolNesneleri", "memory")
    ada = QgsVectorLayer("LineString?crs=EPSG:5253&field=AdaKenariCizgiTip:string&field=CizgiKalinligi:double",
                         "AdaKenari", "memory")
    return diger, ada


def _platform_ok(diger):
    feats = list(diger.getFeatures())
    overl = sum(a.geometry().intersection(b.geometry()).area()
                for i, a in enumerate(feats) for b in feats[i + 1:])
    valid = all(f.geometry().isGeosValid() for f in feats)
    return overl, valid


def _area(diger, tip=None):
    return sum(f.geometry().area() for f in diger.getFeatures() if tip is None or f["DigerYolNesneTip"] == tip)


def test_kavsak():
    import math
    from pln3113_nip.core.mpyy_road import YolProfili, yol_ekle

    print("Kavşak köşesi")
    k = 1 - math.pi / 4  # köşe dolgusu = r² (1 - π/4)
    p = YolProfili(serit_sayisi=1, serit_genisligi=3.5, sol_kaldirim=2.0, sag_kaldirim=2.0, kose_yaricapi=8.0)

    # X kavşağı: 2 x 400 m, 11 m (7 m taşıt + 2 x 2 m kaldırım)
    diger, ada = _mem_layers()
    yol_ekle(_line((300, 500), (700, 500)), p, None, diger, ada, yolorta_yaz=False)
    s = yol_ekle(_line((500, 300), (500, 700)), p, None, diger, ada, yolorta_yaz=False)
    overl, valid = _platform_ok(diger)
    _ok("X: kavşak bulundu", s.get("kavsak") == 1, str(s))
    _ok("X: platform çakışmasız ve geçerli", overl < 0.01 and valid, f"{overl:.4f}")
    beklenen = 2 * 400 * 11 - 121 + 4 * 64 * k
    # Yaylar 16 parçalı çokgenle çizilir: köşe başına ~0,13 m² fazla dolgu, tolerans 1 m².
    _ok(f"X: platform alanı 8679 + 4·8²(1-π/4) = {beklenen:.2f}", abs(_area(diger) - beklenen) < 1.0,
        f"{_area(diger):.2f}")
    beklenen_t = 2 * 400 * 7 - 49 + 4 * 100 * k
    _ok(f"X: taşıt yolu 5551 + 4·10²(1-π/4) = {beklenen_t:.2f} (bordür R = 8 + 2)",
        abs(_area(diger, "TasitYolu") - beklenen_t) < 1.0, f"{_area(diger, 'TasitYolu'):.2f}")
    kenar = sorted(round(f.geometry().length(), 2) for f in ada.getFeatures())
    tek = 2 * 194.5 - (2 * 8 - math.pi / 2 * 8)
    _ok(f"X: ada kenarı köşede birleşti, 4 çizgi x {tek:.2f} m",
        len(kenar) == 4 and all(abs(x - tek) < 0.1 for x in kenar), str(kenar))
    _ok("X: ada kenarları tek parça ve geçerli",
        all(not f.geometry().isMultipart() and f.geometry().isGeosValid() for f in ada.getFeatures()))
    # Kaldırım köşede 2 m genişliğinde halka kalır: kaldırımın en dar yeri ~2 m
    kald = QgsGeometry.unaryUnion([f.geometry() for f in diger.getFeatures() if f["DigerYolNesneTip"] == "Kaldirim"])
    corner = kald.intersection(QgsGeometry.fromRect(QgsRectangle(X0 + 505, Y0 + 505, X0 + 530, Y0 + 530)))
    ic = corner.poleOfInaccessibility(0.01)[1]
    _ok("X: köşedeki kaldırım halkası 2 m (en geniş iç daire yarıçapı ~1 m)", abs(ic - 1.0) < 0.05, f"{ic:.3f}")

    # T kavşağı: sap ana yolun aksında biter; yalnız iki köşe yuvarlanır
    diger, ada = _mem_layers()
    yol_ekle(_line((300, 500), (700, 500)), p, None, diger, ada, yolorta_yaz=False)
    yol_ekle(_line((500, 500), (500, 700)), p, None, diger, ada, yolorta_yaz=False)
    overl, valid = _platform_ok(diger)
    beklenen = 400 * 11 + 200 * 11 - 11 * 5.5 + 2 * 64 * k
    _ok(f"T: platform alanı {beklenen:.2f}, çakışmasız", abs(_area(diger) - beklenen) < 1.0 and overl < 0.01 and valid,
        f"{_area(diger):.2f}")
    kenar = sorted(round(f.geometry().length(), 2) for f in ada.getFeatures())
    _ok("T: 3 ada kenarı (karşı kenar düz kalır)", len(kenar) == 3, str(kenar))

    # Refüjlü yolu kesen yol: refüj kavşak dışında korunur
    diger, ada = _mem_layers()
    bolunmus = YolProfili(serit_sayisi=2, serit_genisligi=3.5, refuj=4.0, sol_kaldirim=3.0, sag_kaldirim=3.0,
                          kose_yaricapi=8.0)
    yol_ekle(_line((300, 500), (700, 500)), bolunmus, None, diger, ada, yolorta_yaz=False)
    yol_ekle(_line((500, 300), (500, 700)), p, None, diger, ada, yolorta_yaz=False)
    overl, valid = _platform_ok(diger)
    _ok("refüj: 400 x 4 - 7 x 4 = 1572 m² korunur", abs(_area(diger, "Refuj") - 1572) < 0.5,
        f"{_area(diger, 'Refuj'):.2f}")
    _ok("refüj: platform çakışmasız ve geçerli", overl < 0.01 and valid)

    # 45 derecelik kavşak
    diger, ada = _mem_layers()
    yol_ekle(_line((300, 500), (700, 500)), p, None, diger, ada, yolorta_yaz=False)
    once = 400 * 11
    s = yol_ekle(_line((350, 350), (650, 650)), p, None, diger, ada, yolorta_yaz=False)
    overl, valid = _platform_ok(diger)
    _ok("45°: kavşak yuvarlandı, çakışmasız ve geçerli", s.get("kavsak") == 1 and s.get("kose_alani", 0) > 0
        and overl < 0.01 and valid, str(s))
    _ok("45°: ada kenarları geçerli ve 4 çizgi", sum(1 for _ in ada.getFeatures()) == 4
        and all(f.geometry().isGeosValid() for f in ada.getFeatures()), str(sum(1 for _ in ada.getFeatures())))
    _ok("45°: platform büyüdü", _area(diger) > once)

    # Dar ada (6 m) iki paralel yol arasında: kavşak onu yutmaz
    diger, ada = _mem_layers()
    yol_ekle(_line((300, 500), (700, 500)), p, None, diger, ada, yolorta_yaz=False)
    yol_ekle(_line((300, 517), (700, 517)), p, None, diger, ada, yolorta_yaz=False)
    yol_ekle(_line((500, 300), (500, 700)), p, None, diger, ada, yolorta_yaz=False)
    serit = QgsGeometry.fromRect(QgsRectangle(X0 + 300, Y0 + 505.5, X0 + 700, Y0 + 511.5))
    plat = QgsGeometry.unaryUnion([f.geometry() for f in diger.getFeatures()])
    kalan = serit.difference(plat).area()
    _ok("dar ada: 6 x 400 - 6 x 11 = 2334 m² korunur", abs(kalan - 2334) < 0.5, f"{kalan:.2f}")
    overl, valid = _platform_ok(diger)
    _ok("dar ada: platform çakışmasız ve geçerli", overl < 0.01 and valid)

    # Dört yolla çevrili ada: kenarı tek kapalı halka
    diger, ada = _mem_layers()
    for a_, b_ in (((300, 400), (700, 400)), ((300, 600), (700, 600)), ((400, 300), (400, 700)), ((600, 300), (600, 700))):
        yol_ekle(_line(a_, b_), p, None, diger, ada, yolorta_yaz=False)
    overl, valid = _platform_ok(diger)
    halka = 4 * 189 - 4 * (2 * 8 - math.pi / 2 * 8)
    kapali = [f.geometry().length() for f in ada.getFeatures()
              if f.geometry().asPolyline()[0] == f.geometry().asPolyline()[-1]]
    _ok(f"çevrili ada: kenar tek kapalı halka, {halka:.2f} m", len(kapali) == 1 and abs(kapali[0] - halka) < 0.5,
        str([round(x, 2) for x in kapali]))
    _ok("çevrili ada: 4 kavşak, platform çakışmasız ve geçerli", overl < 0.01 and valid)

    # Yarıçap 0: köşe yuvarlanmaz
    diger, ada = _mem_layers()
    p0 = YolProfili(kose_yaricapi=0.0)
    yol_ekle(_line((300, 500), (700, 500)), p0, None, diger, ada, yolorta_yaz=False)
    s = yol_ekle(_line((500, 300), (500, 700)), p0, None, diger, ada, yolorta_yaz=False)
    _ok("R = 0: kavşak yuvarlanmaz", "kavsak" not in s and abs(_area(diger) - 8679) < 0.01)


def run_all(tmpdir):
    gpkg, project = test_checks(tmpdir)
    test_road(project)
    test_kavsak()
    test_algorithms(gpkg, project)
    test_map_tool(project)
    project.clear()
    passed = sum(_RESULTS)
    print("-" * 60)
    print(f"  {passed}/{len(_RESULTS)} passed")
    return passed == len(_RESULTS)


def main():
    app = QgsApplication.instance()
    owns = app is None
    profile = tempfile.TemporaryDirectory(prefix="pln3113_nip-checks-")
    if owns:
        app = QgsApplication([], False, profile.name, "external")
        app.initQgis()
    tmpdir = tempfile.mkdtemp(prefix="nip-gpkg-")
    try:
        return run_all(tmpdir)
    finally:
        QgsProject.instance().clear()
        shutil.rmtree(tmpdir, ignore_errors=True)
        if owns:
            app.exitQgis()
        profile.cleanup()


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
