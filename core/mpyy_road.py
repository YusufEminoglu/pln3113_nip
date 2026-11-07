# -*- coding: utf-8 -*-
"""MPYY 1.1.7 NİP yol platformu: orta akstan Yolorta + DigerYolNesneleri + AdaKenari.

Ek-1e kataloğu NİP'teki yolları (otoyol, birinci ve ikinci derece yol) üç
tabloya birlikte çizilen kayıtlar olarak tanımlar: "Yolorta + AdaKenari +
DigerYolNesneleri". Bu modül planX CAD Drafting Toolset'teki yol aracının
mantığını izler: yol profili (şerit, refüj, kaldırım) verilir, orta aks
çizilir, platform bileşenleri aksa paralel bantlar olarak üretilir.

- Yolorta: orta aks; YolTip ve YolGenisligi (toplam platform genişliği).
- DigerYolNesneleri: TasitYolu, Refuj ve Kaldirim poligonları.
- AdaKenari: platformun iki dış kenarı (AdaKenariCizgiTip = Onerilen).

Yeni yol var olan bir yolu kestiğinde kavşak çözülür: var olan taşıt yolu
korunur, var olan kaldırım ve refüj yeni taşıt yolunun geçtiği yerde açılır,
yeni bileşenler var olanlardan çıkarılır, ada kenarları karşı yolun
platformunda kesilir. Böylece DigerYolNesneleri kendi içinde çakışmaz.
Ardından kavşak köşeleri yuvarlanır (kavsak_yuvarla): ada kenarı köşe
yarıçapıyla, bordür onunla eş merkezli (köşe yarıçapı + kaldırım) yayla.
"""
from __future__ import annotations

from dataclasses import dataclass

from qgis.core import (
    QgsFeature,
    QgsFeatureRequest,
    QgsGeometry,
    QgsPointXY,
    QgsWkbTypes,
)

from .compat import JOIN_MITER, SIDE_LEFT, SIDE_RIGHT

YOL_TIPLERI = (
    ("ErismeKontrolluKarayoluOtoyol", "Erişme Kontrollü Karayolu (Otoyol)"),
    ("1DereceYol", "Birinci Derece Yol"),
    ("2DereceYol", "İkinci Derece Yol"),
)

TASIT_YOLU, REFUJ, KALDIRIM = "TasitYolu", "Refuj", "Kaldirim"
NESNE_TIP_ALANI = "DigerYolNesneTip"
ADA_KENARI_TIPI = "Onerilen"
ADA_KENARI_KALINLIK = 0.5  # e-Plan NIP_ADA_KENARI SLD çizgi kalınlığı

_SEGMENTS = 8
_MITER_LIMIT = 2.0
_EPS_AREA = 0.01
_EPS_LENGTH = 0.01


@dataclass
class YolProfili:
    """Yol enkesiti. Uzunluklar metredir; şerit sayısı her yön içindir."""

    yol_tipi: str = "2DereceYol"
    serit_sayisi: int = 1
    serit_genisligi: float = 3.5
    refuj: float = 0.0
    sol_kaldirim: float = 2.0
    sag_kaldirim: float = 2.0
    tek_yon: bool = False
    kose_yaricapi: float = 8.0  # kavşakta ada köşesi yarıçapı (m); 0 ise köşe yuvarlanmaz

    @property
    def tasit_genisligi(self) -> float:
        yon = 1 if self.tek_yon else 2
        return yon * self.serit_sayisi * self.serit_genisligi

    @property
    def toplam_genislik(self) -> float:
        refuj = 0.0 if self.tek_yon else self.refuj
        return self.tasit_genisligi + refuj + self.sol_kaldirim + self.sag_kaldirim

    def dogrula(self) -> list[str]:
        hatalar = []
        if self.yol_tipi not in {kod for kod, _ in YOL_TIPLERI}:
            hatalar.append(f"Bilinmeyen yol tipi: {self.yol_tipi}")
        if self.serit_sayisi < 1:
            hatalar.append("Şerit sayısı en az 1 olmalı.")
        if self.serit_genisligi <= 0:
            hatalar.append("Şerit genişliği 0'dan büyük olmalı.")
        if min(self.refuj, self.sol_kaldirim, self.sag_kaldirim) < 0:
            hatalar.append("Refüj ve kaldırım genişlikleri negatif olamaz.")
        if self.kose_yaricapi < 0:
            hatalar.append("Kavşak köşe yarıçapı negatif olamaz.")
        return hatalar

    @classmethod
    def genislikten(cls, yol_tipi: str, toplam: float, kaldirim: float = 0.0, refuj: float = 0.0,
                    kose_yaricapi: float = 8.0):
        """Yalnız toplam genişliği bilinen bir Yolorta için profil (tek şerit = tüm taşıt yolu)."""
        tasit = toplam - 2 * kaldirim - refuj
        if tasit <= 0:
            raise ValueError(
                f"Toplam genişlik ({toplam:g} m) kaldırım ve refüje yetmiyor; taşıt yolu {tasit:g} m olur."
            )
        return cls(yol_tipi=yol_tipi, serit_sayisi=1, serit_genisligi=tasit / 2.0, refuj=refuj,
                   sol_kaldirim=kaldirim, sag_kaldirim=kaldirim, tek_yon=False, kose_yaricapi=kose_yaricapi)


def _side_buffer(center: QgsGeometry, distance: float, side) -> QgsGeometry:
    return center.singleSidedBuffer(distance, _SEGMENTS, side, JOIN_MITER, _MITER_LIMIT)


def _band(center: QgsGeometry, inner: float, outer: float, side) -> QgsGeometry | None:
    """Aksın bir yanında inner..outer uzaklıkları arasındaki şerit poligonu."""
    if outer - inner <= 1e-6:
        return None
    band = _side_buffer(center, outer, side)
    if inner > 1e-6:
        band = band.difference(_side_buffer(center, inner, side))
    return band if _has_area(band) else None


def _union(geometries) -> QgsGeometry | None:
    parts = [g for g in geometries if g is not None and not g.isEmpty()]
    if not parts:
        return None
    return QgsGeometry.unaryUnion(parts) if len(parts) > 1 else QgsGeometry(parts[0])


def _has_area(geometry) -> bool:
    return geometry is not None and not geometry.isEmpty() and geometry.area() > _EPS_AREA


def _polygonal(geometry) -> QgsGeometry | None:
    """Fark işlemlerinden kalan çizgi/nokta artıklarını atar, yalnız alan parçalarını tutar."""
    if geometry is None or geometry.isEmpty():
        return None
    parts = [QgsGeometry(p) for p in geometry.asGeometryCollection()
             if p.type() == QgsWkbTypes.GeometryType.PolygonGeometry and p.area() > _EPS_AREA]
    if not parts:
        return None
    merged = QgsGeometry.collectGeometry(parts)
    merged.convertToMultiType()
    return merged


def _line_parts(geometry) -> list[QgsGeometry]:
    if geometry is None or geometry.isEmpty():
        return []
    merged = geometry.mergeLines() if geometry.isMultipart() else geometry
    out = []
    for part in merged.asGeometryCollection():
        if part.type() == QgsWkbTypes.GeometryType.LineGeometry and part.length() > _EPS_LENGTH:
            out.append(QgsGeometry(part))
    return out


def platform_uret(center: QgsGeometry, profil: YolProfili) -> dict:
    """Orta akstan platform bileşenlerini üretir (geometriler aksın KRS'sinde, metre).

    Dönüş: {"TasitYolu": poligon, "Refuj": poligon|None, "Kaldirim": poligon|None,
            "kenarlar": [sol kenar, sağ kenar]}
    """
    if profil.tek_yon:
        ic, yari = 0.0, profil.tasit_genisligi / 2.0
    else:
        ic, yari = profil.refuj / 2.0, profil.serit_sayisi * profil.serit_genisligi
    dis_sol = ic + yari + profil.sol_kaldirim
    dis_sag = ic + yari + profil.sag_kaldirim

    tasit = _union([_band(center, ic, ic + yari, SIDE_LEFT), _band(center, ic, ic + yari, SIDE_RIGHT)])
    refuj = _union([_band(center, 0.0, ic, SIDE_LEFT), _band(center, 0.0, ic, SIDE_RIGHT)])
    kaldirim = _union([
        _band(center, ic + yari, dis_sol, SIDE_LEFT),
        _band(center, ic + yari, dis_sag, SIDE_RIGHT),
    ])
    kenarlar = [
        center.offsetCurve(dis_sol, _SEGMENTS, JOIN_MITER, _MITER_LIMIT),
        center.offsetCurve(-dis_sag, _SEGMENTS, JOIN_MITER, _MITER_LIMIT),
    ]
    return {
        TASIT_YOLU: _polygonal(tasit),
        REFUJ: _polygonal(refuj),
        KALDIRIM: _polygonal(kaldirim),
        "kenarlar": [k for k in kenarlar if k is not None and not k.isEmpty()],
    }


def _features_near(layer, rect, attributes=None):
    """Kutudaki nesneler. attributes verilirse yalnız o sütunlar okunur; böylece
    katmandaki "Kontrol" sanal alanı boşuna hesaplanmaz."""
    request = QgsFeatureRequest().setFilterRect(rect)
    if attributes is not None:
        request.setSubsetOfAttributes(attributes, layer.fields())
    return [f for f in layer.getFeatures(request) if f.hasGeometry()]


def _set(feature, layer, name, value):
    index = layer.fields().indexOf(name)
    if index >= 0:
        feature.setAttribute(index, value)


def _new_feature(layer, geometry, attributes):
    geometry = QgsGeometry(geometry)
    if QgsWkbTypes.isMultiType(layer.wkbType()):
        geometry.convertToMultiType()
    elif geometry.isMultipart():
        geometry.convertToSingleType()
    feature = QgsFeature(layer.fields())
    feature.setGeometry(geometry)
    for name, value in attributes.items():
        _set(feature, layer, name, value)
    return feature


class YolYazmaHatasi(RuntimeError):
    pass


def yol_ekle(center: QgsGeometry, profil: YolProfili, yolorta, diger, ada_kenari,
             yolorta_yaz: bool = True) -> dict:
    """Bir yolu üç MPYY katmanına yazar ve kavşakları çözer.

    center katmanların KRS'sinde olmalı (üç katman aynı GeoPackage'tan, aynı
    KRS'de beklenir) ve KRS metre birimli izdüşümlü olmalıdır. Düzenleme
    kipinde olmayan katmanlar düzenlemeye açılır ve sonunda kaydedilir; zaten
    düzenlenen katmanlar düzenleme kipinde bırakılır (geri al kullanılabilir).
    Hata olursa bu çağrının açtığı katmanlardaki değişiklikler geri alınır.

    Dönüş: eklenen/değiştirilen nesne sayıları.
    """
    hatalar = profil.dogrula()
    if hatalar:
        raise ValueError(" ".join(hatalar))
    if center is None or center.isEmpty() or center.length() <= 0:
        raise ValueError("Orta aks boş.")
    katmanlar = [k for k in (yolorta if yolorta_yaz else None, diger, ada_kenari) if k is not None]
    for katman in katmanlar:
        crs = katman.crs()
        if crs.isGeographic():
            raise ValueError(f"{katman.name()} coğrafi KRS'de; yol ölçüleri metre olduğu için izdüşümlü KRS gerekir.")
        if crs != katmanlar[0].crs():
            raise ValueError("Yolorta, DigerYolNesneleri ve AdaKenari aynı KRS'de olmalı.")

    if center.isMultipart():
        parcalar = center.asGeometryCollection()
        if len(parcalar) != 1:
            raise ValueError("Orta aks tek parça çizgi olmalı.")
        center = QgsGeometry(parcalar[0])

    yeni = platform_uret(center, profil)
    if yeni[TASIT_YOLU] is None:
        raise ValueError("Taşıt yolu üretilemedi (orta aks geçersiz olabilir).")
    yeni_tum = _union([yeni[TASIT_YOLU], yeni[REFUJ], yeni[KALDIRIM]])
    kutu = yeni_tum.boundingBox()
    kutu.grow(1.0)

    acilan = []
    for katman in katmanlar:
        if not katman.isEditable():
            if not katman.startEditing():
                raise YolYazmaHatasi(f"{katman.name()} düzenlemeye açılamadı.")
            acilan.append(katman)
    for katman in katmanlar:
        katman.beginEditCommand("MPYY yol platformu")
    komut_acik = True

    sayac = {"Yolorta": 0, TASIT_YOLU: 0, REFUJ: 0, KALDIRIM: 0, "AdaKenari": 0,
             "degisen_platform": 0, "silinen_platform": 0, "degisen_kenar": 0}
    try:
        tip_index = diger.fields().indexOf(NESNE_TIP_ALANI)
        if tip_index < 0:
            raise YolYazmaHatasi(f"{diger.name()} katmanında {NESNE_TIP_ALANI} alanı yok.")
        var_olan = _features_near(diger, kutu, [NESNE_TIP_ALANI])
        eski_tasit = _union([f.geometry() for f in var_olan if f.attribute(tip_index) == TASIT_YOLU])
        eski_platform = _union([f.geometry() for f in var_olan])

        # Kavşaklar: yeni taşıt yolunun var olan taşıt yoluyla kesiştiği kutular.
        kavsaklar = []
        if eski_tasit is not None and profil.kose_yaricapi > 0:
            for parca in yeni[TASIT_YOLU].intersection(eski_tasit).asGeometryCollection():
                if parca.type() == QgsWkbTypes.GeometryType.PolygonGeometry and parca.area() > 1.0:
                    kavsaklar.append(QgsGeometry(parca))

        # 1. Yeni taşıt yolu var olan taşıt yolundan çıkarılır (kavşak kutusu var olanda kalır).
        tasit = yeni[TASIT_YOLU]
        if eski_tasit is not None:
            tasit = _polygonal(tasit.difference(eski_tasit))

        # 2. Var olan kaldırım ve refüj yeni taşıt yolunun geçtiği yerde açılır.
        if tasit is not None:
            for feature in var_olan:
                if feature.attribute(tip_index) == TASIT_YOLU or not feature.geometry().intersects(tasit):
                    continue
                kalan = _polygonal(feature.geometry().difference(tasit))
                if kalan is None:
                    diger.deleteFeature(feature.id())
                    sayac["silinen_platform"] += 1
                elif abs(kalan.area() - feature.geometry().area()) > _EPS_AREA:
                    diger.changeGeometry(feature.id(), kalan)
                    sayac["degisen_platform"] += 1

        # 3. Yeni refüj ve kaldırım, var olan platformla ve yeni taşıt yoluyla çakışmaz.
        engel = _union([eski_platform, tasit])
        refuj = yeni[REFUJ]
        if refuj is not None and engel is not None:
            refuj = _polygonal(refuj.difference(engel))
        kaldirim = yeni[KALDIRIM]
        engel = _union([engel, refuj])
        if kaldirim is not None and engel is not None:
            kaldirim = _polygonal(kaldirim.difference(engel))

        for tip, geometri in ((TASIT_YOLU, tasit), (REFUJ, refuj), (KALDIRIM, kaldirim)):
            if geometri is None:
                continue
            if not diger.addFeature(_new_feature(diger, geometri, {NESNE_TIP_ALANI: tip})):
                raise YolYazmaHatasi(f"{tip} eklenemedi.")
            sayac[tip] += 1

        # 4. Ada kenarları: yeni kenar karşı yolun platformunda, var olan kenar yeni platformda kesilir.
        if ada_kenari is not None:
            for feature in _features_near(ada_kenari, kutu):
                geometri = feature.geometry()
                if not geometri.intersects(yeni_tum):
                    continue
                parcalar = _line_parts(geometri.difference(yeni_tum))
                if not parcalar:
                    ada_kenari.deleteFeature(feature.id())
                elif len(parcalar) == 1 and abs(parcalar[0].length() - geometri.length()) <= _EPS_LENGTH:
                    continue
                else:
                    ada_kenari.changeGeometry(feature.id(), _single_like(ada_kenari, parcalar[0]))
                    for parca in parcalar[1:]:
                        ek = QgsFeature(feature)
                        ek.setGeometry(_single_like(ada_kenari, parca))
                        _clear_fid(ek, ada_kenari)
                        ada_kenari.addFeature(ek)
                sayac["degisen_kenar"] += 1
            for kenar in yeni["kenarlar"]:
                parcalar = _line_parts(kenar.difference(eski_platform) if eski_platform is not None else kenar)
                for parca in parcalar:
                    ozellik = {"AdaKenariCizgiTip": ADA_KENARI_TIPI, "CizgiKalinligi": ADA_KENARI_KALINLIK}
                    if not ada_kenari.addFeature(_new_feature(ada_kenari, parca, ozellik)):
                        raise YolYazmaHatasi("AdaKenari eklenemedi.")
                    sayac["AdaKenari"] += 1

        # 5. Kavşak köşeleri yuvarlanır (bordür ve ada kenarı eş merkezli yaylar).
        kaldirim_ort = (profil.sol_kaldirim + profil.sag_kaldirim) / 2.0
        for kutu_k in kavsaklar:
            sonuc = kavsak_yuvarla(diger, ada_kenari, kutu_k, profil.kose_yaricapi, kaldirim_ort)
            sayac["kavsak"] = sayac.get("kavsak", 0) + 1
            sayac["kose_alani"] = round(sayac.get("kose_alani", 0.0) + sonuc["eklenen_alan"], 2)

        if yolorta_yaz and yolorta is not None:
            ozellik = {"YolTip": profil.yol_tipi, "YolGenisligi": round(profil.toplam_genislik, 2)}
            if not yolorta.addFeature(_new_feature(yolorta, center, ozellik)):
                raise YolYazmaHatasi("Yolorta eklenemedi.")
            sayac["Yolorta"] += 1

        for katman in katmanlar:
            katman.endEditCommand()
        komut_acik = False
        for katman in acilan:
            if not katman.commitChanges():
                raise YolYazmaHatasi(f"{katman.name()} kaydedilemedi: " + "; ".join(katman.commitErrors()))
    except Exception:
        if komut_acik:
            for katman in katmanlar:
                katman.destroyEditCommand()
        for katman in acilan:
            if katman.isEditable():
                katman.rollBack()
        raise

    for katman in katmanlar:
        katman.triggerRepaint()
    return sayac


def _single_like(layer, geometry):
    geometry = QgsGeometry(geometry)
    if QgsWkbTypes.isMultiType(layer.wkbType()):
        geometry.convertToMultiType()
    return geometry


def _clear_fid(feature, layer):
    index = layer.fields().indexOf("fid")
    if index >= 0:
        feature.setAttribute(index, None)


# ---------------------------------------------------------------------------
# Kavşak köşesi
# ---------------------------------------------------------------------------
_ARC_SEGMENTS = 16


def _closing(geometry: QgsGeometry, radius: float) -> QgsGeometry:
    """Morfolojik kapanış: içbükey köşeleri radius yarıçaplı yayla doldurur, dışbükeyleri korur."""
    return geometry.buffer(radius, _ARC_SEGMENTS).buffer(-radius, _ARC_SEGMENTS)


def _pieces(geometry, min_area=0.5):
    if geometry is None or geometry.isEmpty():
        return []
    return [QgsGeometry(p) for p in geometry.asGeometryCollection()
            if p.type() == QgsWkbTypes.GeometryType.PolygonGeometry and p.area() >= min_area]


def _merge_into(layer, features, piece, prefer_types, tip_index):
    """Parçayı, en uzun ortak kenarı paylaştığı tercih edilen türdeki nesneye katar."""
    best, best_len = None, 0.0
    edge = QgsGeometry(piece.constGet().boundary())
    for wanted in prefer_types:
        for feature in features:
            if feature.attribute(tip_index) != wanted:
                continue
            shared = edge.intersection(feature.geometry().buffer(0.01, 2)).length()
            if shared > best_len:
                best, best_len = feature, shared
        if best is not None:
            break
    if best is None:
        return False
    merged = _polygonal(QgsGeometry.unaryUnion([best.geometry(), piece]))
    if merged is None:
        return False
    layer.changeGeometry(best.id(), merged)
    best.setGeometry(merged)
    return True


def _corner_fill(parca: QgsGeometry, kavsak: QgsGeometry, yaricap: float, temas: float,
                 bolge_siniri: QgsGeometry | None = None) -> bool:
    """Kapanış dolgusu gerçek bir köşe dolgusu mu?

    Köşe dolgusu kavşak kutusuna bitişiktir (bordür dolgusu kutunun köşesine,
    ada köşesi dolgusu kaldırım genişliği kadar ötesine değer) ve alanı açıya
    bağlıdır: 90°'de r²(1 - π/4) ≈ 0,21 r², 30°'de ≈ 2,4 r², 23°'de ≈ 4 r². Kavşağa
    değmeyen ya da 4 r²'den büyük dolgular, yakın iki yol arasındaki dar adayı ya da yakın
    yol uçlarını yutan kapanış artıklarıdır ve kabul edilmez. Gerçek köşe dolgusu
    kavşak bölgesinin içinde kalır; bölge sınırına dayanan dolgu, dar bir adayı
    bölge boyunca yutan kapanıştır.
    """
    if bolge_siniri is not None and parca.intersects(bolge_siniri):
        return False
    return parca.area() <= 4.0 * yaricap * yaricap and parca.intersects(kavsak.buffer(temas, 4))


def kavsak_yuvarla(diger, ada_kenari, kavsak: QgsGeometry, kose_yaricapi: float, kaldirim: float) -> dict:
    """Bir kavşağın köşelerini yuvarlar. Katmanlar düzenleme kipinde olmalı.

    kavsak: iki taşıt yolunun ortak alanı (kavşak kutusu). Kutunun çevresindeki
    bölgede taşıt yolu bordür yarıçapı (köşe yarıçapı + kaldırım) ile, platformun
    tamamı köşe yarıçapı ile kapanır (eş merkezli yaylar). Bordür dolgusu
    kaldırımdan alınıp taşıt yoluna, ada köşesi dolgusu kaldırıma (kaldırım
    yoksa taşıt yoluna) katılır. Ada kenarlarında köşe kolları silinir, yerine
    köşe yayı eklenir ve kollarla tek çizgide birleştirilir.
    """
    tip_index = diger.fields().indexOf(NESNE_TIP_ALANI)
    rb = float(kose_yaricapi)
    kaldirim = max(0.0, float(kaldirim))
    rc = rb + kaldirim
    box = kavsak.boundingBox()
    diag = (box.width() ** 2 + box.height() ** 2) ** 0.5
    # Bölge dar açılı köşelerin teğet noktalarını da içerir (25°'de köşeden ~4,5 R).
    bolge = kavsak.centroid().buffer(diag / 2.0 + 5.0 * rc + kaldirim + 3.0, 64)
    bolge_siniri = QgsGeometry(bolge.constGet().boundary()).buffer(0.05, 2)
    alan = bolge.boundingBox()
    alan.grow(2.0 * rc + 1.0)
    sonuc = {"eklenen_alan": 0.0, "bordur": 0, "kose": 0, "reddedilen": 0}

    feats = _features_near(diger, alan, [NESNE_TIP_ALANI])
    # Refüj taşıt yoluyla birlikte kapanır; yoksa bölünmüş yolda refüj boşluğu dolardı.
    yol_ici = _union([f.geometry() for f in feats if f.attribute(tip_index) in (TASIT_YOLU, REFUJ)])
    tum = _union([f.geometry() for f in feats])
    if yol_ici is None or tum is None:
        return sonuc
    tum_once = tum

    # Bordür: taşıt yolu + refüj kapanışı; dolgu kaldırımdan alınıp taşıt yoluna katılır.
    bordurler = []
    for parca in _pieces(_closing(yol_ici, rc).intersection(bolge).difference(yol_ici)):
        if not _corner_fill(parca, kavsak, rc, 0.5, bolge_siniri):
            sonuc["reddedilen"] += 1
            continue
        bordurler.append(parca.buffer(0.05, 2))
        for feature in feats:
            if feature.attribute(tip_index) != KALDIRIM or not feature.geometry().intersects(parca):
                continue
            kalan = _polygonal(feature.geometry().difference(parca))
            if kalan is None:
                diger.deleteFeature(feature.id())
                feature.setGeometry(QgsGeometry())
            else:
                diger.changeGeometry(feature.id(), kalan)
                feature.setGeometry(kalan)
        if _merge_into(diger, feats, parca, (TASIT_YOLU,), tip_index):
            sonuc["bordur"] += 1
    feats = [f for f in feats if f.hasGeometry() and not f.geometry().isEmpty()]
    tum_bordur = _union([f.geometry() for f in feats])

    # Ada köşesi: platformun tamamının kapanışı; dolgu kaldırıma katılır.
    koseler = []
    for parca in _pieces(_closing(tum_bordur, rb).intersection(bolge).difference(tum_bordur)):
        # Ada köşesi, yalnız aynı köşenin bordürü de yuvarlandıysa yuvarlanır (eş merkezli
        # yaylar): kabul edilen bir bordür dolgusu en çok kaldırım genişliği kadar uzakta
        # olmalı. Bordür reddedildiyse köşe iki çizgide de sivri kalır.
        yakin = any(parca.distance(b) <= kaldirim + 0.5 for b in bordurler)
        if parca.intersects(bolge_siniri) or parca.area() > 4.0 * rb * rb or not yakin:
            sonuc["reddedilen"] += 1
            continue
        if _merge_into(diger, feats, parca, (KALDIRIM, TASIT_YOLU), tip_index):
            sonuc["kose"] += 1
            koseler.append(parca)
    tum = _union([f.geometry() for f in feats])
    sonuc["eklenen_alan"] = tum.area() - tum_once.area()

    if ada_kenari is not None:
        _ada_kenari_yuvarla(ada_kenari, tum, tum_bordur, koseler, bolge)
    return sonuc


def _ada_kenari_yuvarla(ada_kenari, platform: QgsGeometry, platform_once: QgsGeometry, koseler, bolge) -> None:
    """Köşe kollarını siler, köşe yaylarını ekler ve kollarla birleştirir.

    Kollar yeni platformun içinde kaldığı için 2 cm içe daraltılmış platformla
    farkı alınarak silinir; sınırda kalan kenarlar ve yol uçları dokunulmaz.
    Yay, köşe dolgusunun eski platforma değmeyen kenarıdır.
    """
    ic = platform.buffer(-0.02, 4)
    kutu = bolge.boundingBox()
    for feature in _features_near(ada_kenari, kutu):
        geometri = feature.geometry()
        if not geometri.intersects(ic):
            continue
        parcalar = _line_parts(geometri.difference(ic))
        if not parcalar:
            ada_kenari.deleteFeature(feature.id())
            continue
        ada_kenari.changeGeometry(feature.id(), _single_like(ada_kenari, parcalar[0]))
        for parca in parcalar[1:]:
            ek = QgsFeature(feature)
            ek.setGeometry(_single_like(ada_kenari, parca))
            _clear_fid(ek, ada_kenari)
            ada_kenari.addFeature(ek)

    eski = platform_once.buffer(0.02, 4)
    for kose in koseler:
        sinir = QgsGeometry(kose.constGet().boundary())
        for yay in _line_parts(sinir.difference(eski)):
            n = yay.constGet().nCoordinates()
            uclar = [QgsGeometry.fromPointXY(QgsPointXY(yay.vertexAt(0))),
                     QgsGeometry.fromPointXY(QgsPointXY(yay.vertexAt(n - 1)))]
            ara = yay.boundingBox()
            ara.grow(0.5)
            # Yay önce bir ucundaki, sonra öbür ucundaki kola ikili olarak eklenir.
            hedef = None
            for uc in uclar:
                for f in _features_near(ada_kenari, ara):
                    if hedef is not None and f.id() == hedef.id():
                        continue
                    if f.geometry().distance(uc) > 0.3:
                        continue
                    parcalar = [hedef.geometry() if hedef is not None else yay, f.geometry()]
                    birlesik = _join_lines(parcalar, tol=0.3)
                    if birlesik is None:
                        continue
                    if hedef is None:
                        ada_kenari.changeGeometry(f.id(), _single_like(ada_kenari, birlesik))
                        hedef = ada_kenari.getFeature(f.id())
                    else:
                        ada_kenari.changeGeometry(hedef.id(), _single_like(ada_kenari, birlesik))
                        ada_kenari.deleteFeature(f.id())
                        hedef = ada_kenari.getFeature(hedef.id())
                    break
            if hedef is not None:
                # Yollarla çevrili adanın son köşesi: çizginin iki ucu buluşur, halka kapanır.
                halka = hedef.geometry().asPolyline() if not hedef.geometry().isMultipart() else []
                if len(halka) > 3 and 0 < halka[0].distance(halka[-1]) <= 0.3:
                    ada_kenari.changeGeometry(hedef.id(), _single_like(
                        ada_kenari, QgsGeometry.fromPolylineXY(halka + [halka[0]])))
                continue
            ozellik = {"AdaKenariCizgiTip": ADA_KENARI_TIPI, "CizgiKalinligi": ADA_KENARI_KALINLIK}
            ada_kenari.addFeature(_new_feature(ada_kenari, yay, ozellik))


def _join_lines(lines, tol: float = 0.01):
    """Uçları tol içinde çakışan çizgileri köşe listesi üzerinden tek çizgiye zincirler.

    unaryUnion + mergeLines büyük koordinatlarda (TM, 10^6 m) milimetre altı uç
    farklarını birleştiremez; burada uçlar doğrudan eşlenir. Hepsi tek zincire
    girmezse None döner.
    """
    def pts(g):
        return [QgsPointXY(p) for p in (g.asPolyline() if not g.isMultipart() else g.asMultiPolyline()[0])]

    if any(g.isMultipart() and len(g.asMultiPolyline()) != 1 for g in lines):
        return None
    chain = pts(lines[0])
    rest = [pts(g) for g in lines[1:]]
    while rest:
        for i, other in enumerate(rest):
            if other[0].distance(chain[-1]) <= tol:
                chain = chain + other[1:]
            elif other[-1].distance(chain[-1]) <= tol:
                chain = chain + other[::-1][1:]
            elif other[-1].distance(chain[0]) <= tol:
                chain = other[:-1] + chain
            elif other[0].distance(chain[0]) <= tol:
                chain = other[::-1][:-1] + chain
            else:
                continue
            rest.pop(i)
            break
        else:
            return None
    return QgsGeometry.fromPolylineXY(chain)
