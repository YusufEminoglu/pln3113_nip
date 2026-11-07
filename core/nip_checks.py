# -*- coding: utf-8 -*-
"""MPYY 1.1.7 NİP katmanları için geometri ve öznitelik kontrolleri.

Kontroller çizimi engellemez: her katmana "Kontrol" adlı sanal (ifade) alan
eklenir. Alan, nesnedeki sorunları metin olarak yazar ("geçersiz geometri |
çakışma: Egitim Tesis Alani" gibi); sorun yoksa boştur (NULL). Bu alana bağlı
uyarı (soft) kısıtı formda sarı işaret, koşullu stil öznitelik tablosunda
kırmızı satır gösterir. Öğrenci çizer, tabloyu "Kontrol" sütununa göre süzer
ve sorunları sonradan düzeltir.

Tümü katman stiline (QML) yazılır; GeoPackage'ın layer_styles tablosuna
kaydedildiğinde başka bilgisayarda da çalışır ve XSD şemasına sütun eklemez.
"""
from __future__ import annotations

from contextlib import suppress

from qgis.core import (
    Qgis,
    QgsConditionalStyle,
    QgsExpression,
    QgsFeatureRequest,
    QgsField,
    QgsFieldConstraints,
    QgsFields,
    QgsGeometry,
    QgsProject,
    QgsSpatialIndex,
    QgsVectorLayer,
    qgsfunction,
)
from qgis.PyQt.QtCore import QThread
from qgis.PyQt.QtGui import QColor, QFont

from .compat import FIELD_STRING

CHECK_FIELD = "Kontrol"
CHECK_ALIAS = "⚠ Kontrol"

# Eşikler (katman KRS birimi: metre / m²)
MIN_PART_AREA = 50.0      # bundan küçük poligon parçası "çok küçük parça"
MIN_OVERLAP_AREA = 1.0    # bundan küçük ortak alan (sayısallaştırma gürültüsü) çakışma sayılmaz
MIN_LINE_LENGTH = 1.0     # bundan kısa çizgi "çok kısa çizgi"

# Zemin (mozaik) katmanları: arazi kullanım kararları. Bir noktada yalnız biri
# bulunabilir; birbirleriyle ve yol platformuyla (DigerYolNesneleri) çakışamaz.
# Sınırlar, koruma alanları, afet tehlike alanları, havza ve mania gibi
# katmanlar bunların üzerine bindirilen katmanlardır; çakışmaları doğaldır.
MOSAIC_TYPES = (
    "AcikYesilAlan",
    "AfetHizmetAlani",
    "AraziKullanimiDevamEttirilerekKorunacakAlanlar",
    "AtikGeriKazTesAlani",
    "AtiksuTesis",
    "DigerYolNesneleri",
    "DogalKarakter",
    "EgitimTesisAlani",
    "EnerjiDagitimDepolama",
    "EnerjiUretim",
    "GelismeKonut",
    "HavaalaniHavalimani",
    "IbadetAlani",
    "IcmesuTesis",
    "KarayoluTesisleri",
    "KatiAtikTesis",
    "KentselCalisma",
    "KiyiKorumaYapilari",
    "KiyiYapilari",
    "KumsalPlaj",
    "Mera",
    "MevcutKonut",
    "Orman",
    "SaglikTesisAlani",
    "SosyalKulturelAlan",
    "SuYuzeyi",
    "Tarim",
    "TehlikeliTesis",
    "TeknikAltyapi",
    "Terminal",
    "TopluTasimaAktarimAlani",
    "TurizmAlani",
    "YapayAda",
)

PLAN_BOUNDARY_TYPE = "PlanSiniri"
ROAD_CENTER_TYPE = "Yolorta"
ROAD_PLATFORM_TYPE = "DigerYolNesneleri"

_POLYGONS = ("MultiPolygon", "Polygon")
_LINES = ("LineString", "MultiLineString")


def _q(text: str) -> str:
    """Metni QGIS ifadesi için tek tırnaklı dizgeye çevirir."""
    return "'" + str(text).replace("'", "''") + "'"


def _overlap_term(layer_ref: str, label: str, same_layer: bool = False) -> str:
    """Hedef katmanla ortak alanı MIN_OVERLAP_AREA ve üstü olan nesne varsa etiketi döndürür.

    overlay_* işlevleri hedef nesneleri tüm öznitelikleriyle okur; hedefte de
    "Kontrol" sanal alanı olduğundan karşılıklı sonsuz değerlendirmeye girer.
    aggregate() yalnız ifadede geçen sütunları okur, bu yüzden burada o kullanılır.
    Kenar paylaşan komşuların ortak alanı 0'dır, çakışma sayılmaz. @parent'a
    başvuran süzgeç sonucu önbelleğe alınmaz, her nesne için ayrı hesaplanır.
    """
    self_filter = "$id <> @nip_id AND " if same_layer else ""
    aggregate = (
        f"coalesce(aggregate({layer_ref}, 'max', area(intersection($geometry, geometry(@parent))), "
        f"filter:={self_filter}intersects($geometry, geometry(@parent))), 0)"
    )
    if same_layer:
        aggregate = f"with_variable('nip_id', $id, {aggregate})"
    return f"CASE WHEN try({aggregate}, 0) >= {MIN_OVERLAP_AREA} THEN {_q(label)} END"


def build_check_expression(ft: dict, refs: dict, caption=lambda s: s, fast_ids: dict | None = None) -> str:
    """Bir MPYY nesne türü için "Kontrol" alanının QGIS ifadesini üretir.

    ft: mpyy_schema.json içindeki nesne türü kaydı (name, geometry, fields).
    refs: {nesne türü adı: katman başvurusu ifadesi}. Başvuru katman kimliği
        ya da adı olan tırnaklı bir dizgedir; projede bulunmayan katmana yapılan
        başvuru try() ile yutulur, kontrol yalnız o maddeyi atlar.
    fast_ids: {nesne türü adı: katman kimliği}. Verilirse çakışma ve platform
        kontrolleri eklentinin uzamsal dizinli işlevleriyle (nip_cakisma,
        nip_platform_orani) yapılır; verilmezse yalnız yerleşik QGIS işlevleri
        kullanılır (eklentisiz açılışta da çalışır, ama büyük planda yavaştır).
    """
    name = ft["name"]
    geometry = ft.get("geometry")
    terms = [
        "CASE WHEN $geometry IS NULL OR is_empty($geometry) THEN 'geometri yok' END",
    ]
    if geometry in _POLYGONS:
        terms += [
            "CASE WHEN NOT is_valid($geometry) "
            "THEN 'geçersiz geometri (kendini kesen kenar ya da hatalı halka)' END",
            "CASE WHEN array_min(array_foreach(generate_series(1, num_geometries($geometry)), "
            f"area(geometry_n($geometry, @element)))) < {MIN_PART_AREA} "
            f"THEN {_q(f'çok küçük parça (< {MIN_PART_AREA:g} m²)')} END",
        ]
    elif geometry in _LINES:
        terms += [
            "CASE WHEN NOT is_valid($geometry) THEN 'geçersiz geometri' END",
            f"CASE WHEN length($geometry) < {MIN_LINE_LENGTH} "
            f"THEN {_q(f'çok kısa çizgi (< {MIN_LINE_LENGTH:g} m)')} END",
        ]

    for field in ft.get("fields", []):
        fname = field["name"]
        if fname == "symbolizer" or not field.get("required"):
            continue
        terms.append(
            f"CASE WHEN \"{fname}\" IS NULL OR trim(to_string(\"{fname}\")) = '' "
            f"THEN {_q('eksik: ' + caption(fname))} END"
        )

    fast_overlaps = None
    if name in MOSAIC_TYPES and fast_ids and name in fast_ids:
        targets = [(fast_ids[name], "aynı katmanda çakışma")] + [
            (fast_ids[o], "çakışma: " + caption(o)) for o in MOSAIC_TYPES if o != name and o in fast_ids]
        pairs = ", ".join(f"{_q(i)}, {_q(label)}" for i, label in targets)
        fast_overlaps = f"coalesce(try(nip_cakisma({_q(fast_ids[name])}, map({pairs})), array()), array())"
    elif name in MOSAIC_TYPES:
        terms.append(_overlap_term("@layer", "aynı katmanda çakışma", same_layer=True))
        for other in MOSAIC_TYPES:
            if other != name and other in refs:
                terms.append(_overlap_term(refs[other], "çakışma: " + caption(other)))

    if (name in MOSAIC_TYPES or name == ROAD_CENTER_TYPE) and PLAN_BOUNDARY_TYPE in refs:
        outside = f"difference($geometry, aggregate({refs[PLAN_BOUNDARY_TYPE]}, 'collect', $geometry))"
        measure = (f"length({outside}) >= {MIN_LINE_LENGTH}" if geometry in _LINES
                   else f"area({outside}) >= {MIN_OVERLAP_AREA}")
        # Plan sınırı henüz çizilmediyse aggregate NULL döner ve kontrol atlanır.
        terms.append(f"CASE WHEN try({measure}, false) THEN 'plan sınırı dışına taşıyor' END")

    if name == ROAD_CENTER_TYPE and fast_ids and ROAD_PLATFORM_TYPE in fast_ids:
        terms.append(
            f"CASE WHEN try(nip_platform_orani({_q(fast_ids[ROAD_PLATFORM_TYPE])}), 1) < 0.9 "
            "THEN 'yol platformu üretilmemiş' END"
        )
    elif name == ROAD_CENTER_TYPE and ROAD_PLATFORM_TYPE in refs:
        # Aksın en az %90'ı platform üzerinde olmalı; yalnız başka bir yolun
        # platformunu kesen aks platformsuz sayılır.
        covered = (
            f"length(intersection($geometry, aggregate({refs[ROAD_PLATFORM_TYPE]}, 'collect', $geometry, "
            "filter:=intersects($geometry, geometry(@parent)))))"
        )
        terms.append(
            f"CASE WHEN coalesce(try({covered}, length($geometry)), 0) < 0.9 * length($geometry) "
            "THEN 'yol platformu üretilmemiş' END"
        )

    body = ",\n".join(terms)
    items = f"array_filter(array(\n{body}\n), @element IS NOT NULL)"
    if fast_overlaps:
        items = f"array_cat({items}, {fast_overlaps})"
    return f"nullif(array_to_string({items}, ' | '), '')"


def _is_expression_origin(origin) -> bool:
    """QGIS 3.28 (QgsFields.OriginExpression) ile 3.38+/4 (Qgis.FieldOrigin.Expression) uyumlu."""
    candidates = []
    with suppress(AttributeError):
        candidates.append(Qgis.FieldOrigin.Expression)
    with suppress(AttributeError):
        candidates.append(QgsFields.OriginExpression)
    return any(origin == c for c in candidates)


def _remove_check_field(layer: QgsVectorLayer) -> None:
    fields = layer.fields()
    for index in range(fields.count() - 1, -1, -1):
        if fields.at(index).name() == CHECK_FIELD and _is_expression_origin(fields.fieldOrigin(index)):
            layer.removeExpressionField(index)


def apply_checks(layer: QgsVectorLayer, ft: dict, refs: dict, caption=lambda s: s,
                 fast_ids: dict | None = None) -> int:
    """Katmana "Kontrol" sanal alanını, uyarı kısıtını ve tablo vurgusunu kurar.

    Var olan "Kontrol" sanal alanı (örneğin GeoPackage'tan gelen varsayılan stil)
    önce kaldırılır, böylece başvurular bu projedeki katmanlara göre yenilenir.
    Eklenen alanın dizinini döndürür.
    """
    _remove_check_field(layer)
    expression = build_check_expression(ft, refs, caption, fast_ids)
    field = QgsField(CHECK_FIELD, FIELD_STRING, "string")
    index = layer.addExpressionField(expression, field)
    layer.setFieldAlias(index, CHECK_ALIAS)
    layer.setConstraintExpression(
        index,
        f'"{CHECK_FIELD}" IS NULL',
        "Nesnede düzeltilmesi gereken sorun var; ayrıntı ⚠ Kontrol alanında.",
    )
    layer.setFieldConstraint(
        index,
        QgsFieldConstraints.Constraint.ConstraintExpression,
        QgsFieldConstraints.ConstraintStrength.ConstraintStrengthSoft,
    )

    row = QgsConditionalStyle(f'"{CHECK_FIELD}" IS NOT NULL')
    row.setName("NİP kontrol: düzeltilecek")
    row.setBackgroundColor(QColor("#fde2e1"))
    cell = QgsConditionalStyle("@value IS NOT NULL")
    cell.setName("NİP kontrol: düzeltilecek")
    cell.setTextColor(QColor("#9f1d14"))
    font = QFont()
    font.setBold(True)
    cell.setFont(font)
    styles = layer.conditionalStyles()
    styles.setRowStyles([s for s in styles.rowStyles() if s.name() != row.name()] + [row])
    styles.setFieldStyles(CHECK_FIELD, [cell])

    _move_column_first(layer, CHECK_FIELD)
    return index


def _move_column_first(layer: QgsVectorLayer, name: str) -> None:
    config = layer.attributeTableConfig()
    config.update(layer.fields())
    columns = config.columns()
    for position, column in enumerate(columns):
        if column.name == name:
            columns.insert(0, columns.pop(position))
            break
    config.setColumns(columns)
    layer.setAttributeTableConfig(config)


# ---------------------------------------------------------------------------
# Uzamsal dizinli ifade işlevleri (eklenti yüklüyken)
# ---------------------------------------------------------------------------
class _LayerIndex:
    """Katman başına uzamsal dizin ve geometri önbelleği; katman değişince yenilenir.

    Düzenleme tamponundaki (kaydedilmemiş) nesneler de dizine girer. Nesneler
    özniteliksiz okunur, bu yüzden hedefteki "Kontrol" alanı hesaplanmaz.
    """

    def __init__(self):
        self._cache = {}
        self._wired = set()

    def _dirty(self, layer_id):
        self._cache.pop(layer_id, None)

    def _forget(self, layer_id):
        self._cache.pop(layer_id, None)
        self._wired.discard(layer_id)

    def _wire(self, layer):
        lid = layer.id()
        if lid in self._wired:
            return
        self._wired.add(lid)
        for signal in (layer.featureAdded, layer.featureDeleted, layer.geometryChanged,
                       layer.dataChanged, layer.afterRollBack, layer.afterCommitChanges):
            signal.connect(lambda *_a, lid=lid: self._dirty(lid))
        layer.willBeDeleted.connect(lambda lid=lid: self._forget(lid))

    def get(self, layer):
        self._wire(layer)
        key = (layer.featureCount(), layer.isEditable())
        entry = self._cache.get(layer.id())
        if entry is not None and entry[0] == key:
            return entry[1], entry[2]
        index = QgsSpatialIndex()
        geoms = {}
        for feature in layer.getFeatures(QgsFeatureRequest().setNoAttributes()):
            if not feature.hasGeometry():
                continue
            geom = feature.geometry()
            if not geom.isGeosValid():
                geom = geom.makeValid()
            geoms[feature.id()] = geom
            index.addFeature(feature.id(), geom.boundingBox())
        self._cache[layer.id()] = (key, index, geoms)
        return index, geoms

    def clear(self):
        self._cache.clear()


_INDEX = _LayerIndex()


def _main_thread_layer(layer_id):
    layer = QgsProject.instance().mapLayer(str(layer_id))
    if not isinstance(layer, QgsVectorLayer):
        return None
    if QThread.currentThread() is not layer.thread():
        return None  # katman başka iş parçacığından okunamaz; kontrol bu maddeyi atlar
    return layer


def _source_geometry(feature):
    if feature is None or not feature.hasGeometry():
        return None
    geom = feature.geometry()
    if geom.isEmpty():
        return None
    return geom if geom.isGeosValid() else geom.makeValid()


@qgsfunction(args="auto", group="PLN3113 NİP", usesgeometry=True, referenced_columns=[], handlesnull=True)
def nip_cakisma(self_id, targets, feature, parent):
    """<h3>nip_cakisma(kendi_katman_kimliği, map(hedef_kimlik, etiket, ...))</h3>
    Nesneyle ortak alanı en az 1 m² olan nesne bulunan hedef katmanların etiketlerini
    dizi olarak döndürür. Kendi katmanında nesnenin kendisi atlanır. PLN3113 NİP eklentisi."""
    geom = _source_geometry(feature)
    if geom is None or not targets:
        return []
    bbox = geom.boundingBox()
    engine = QgsGeometry.createGeometryEngine(geom.constGet())
    engine.prepareGeometry()
    found = []
    for layer_id, label in dict(targets).items():
        layer = _main_thread_layer(layer_id)
        if layer is None:
            continue
        index, geoms = _INDEX.get(layer)
        own = str(layer_id) == str(self_id)
        for fid in index.intersects(bbox):
            if own and fid == feature.id():
                continue
            other = geoms.get(fid)
            if other is None or not engine.intersects(other.constGet()):
                continue
            if geom.intersection(other).area() >= MIN_OVERLAP_AREA:
                found.append(label)
                break
    return found


@qgsfunction(args="auto", group="PLN3113 NİP", usesgeometry=True, referenced_columns=[], handlesnull=True)
def nip_platform_orani(platform_id, feature, parent):
    """<h3>nip_platform_orani(platform_katman_kimliği)</h3>
    Çizginin hedef poligon katmanı (yol platformu) üzerinde kalan uzunluk oranı (0-1).
    PLN3113 NİP eklentisi."""
    geom = _source_geometry(feature)
    layer = _main_thread_layer(platform_id)
    if geom is None or layer is None or geom.length() <= 0:
        return None
    index, geoms = _INDEX.get(layer)
    parts = [geoms[fid] for fid in index.intersects(geom.boundingBox()) if fid in geoms]
    if not parts:
        return 0.0
    covered = geom.intersection(QgsGeometry.unaryUnion(parts)).length()
    return min(1.0, covered / geom.length())


def register_functions():
    """Eklenti yüklenirken çağrılır; unload sonrası yeniden yüklemede işlevleri geri kaydeder."""
    for func in (nip_cakisma, nip_platform_orani):
        if not QgsExpression.isFunctionName(func.name()):
            QgsExpression.registerFunction(func)


def unregister_functions():
    for name in ("nip_cakisma", "nip_platform_orani"):
        if QgsExpression.isFunctionName(name):
            QgsExpression.unregisterFunction(name)
    _INDEX.clear()
