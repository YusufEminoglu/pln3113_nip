# -*- coding: utf-8 -*-
"""Gösterge tabanlı kırılganlık endeksi (pay / payda) ve bileşik endeks algoritması."""
from __future__ import annotations

from qgis.core import (
    Qgis,
    QgsCoordinateTransform,
    QgsDistanceArea,
    QgsFeature,
    QgsGeometry,
    QgsProcessing,
    QgsProcessingException,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterFileDestination,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterString,
    QgsProcessingUtils,
    QgsSpatialIndex,
    QgsUnitTypes,
    QgsVectorLayer,
)

from ..core import vulnerability as vu
from ..core.tire_constants import norm_tr
from .alg_nufus_projeksiyonu import (
    ATTRIBUTION,
    YONTEM_KAYNAKLARI,
    FAST_INSERT,
    FIELD_ANY,
    FIELD_NUMERIC,
    FLAG_ADVANCED,
    TYPE_VECTOR_ANY,
    OngoruBaseAlgorithm,
    as_float,
    as_value,
    check_cancel,
    make_field,
    make_fields,
    push_warnings,
)

HAZARD_KEYS = ("sel", "sicak", "deprem")
BREAK_KEYS = tuple(vu.BREAK_METHODS.keys())

# Yer tutucu -> (parametre adı, katman rolü, ad ipuçları)
PLACEHOLDERS = {
    "@NUFUS": ("NUFUS_ALANI", "bolge", ("toplam_nufus", "nufus", "population", "pop")),
    "@COCUK": ("COCUK_ALANI", "bolge", ("cocuk", "0_14", "yas_0_14", "age_0_14")),
    "@YASLI": ("YASLI_ALANI", "bolge", ("yasli", "65_ustu", "64_ustu", "yas_65", "age_65")),
    "@KAT": ("KAT_ALANI", "yapi", ("kat_sayisi", "kat_adedi", "katadedi", "kat", "floors",
                                   "levels")),
    "@MALZEME": ("MALZEME_ALANI", "yapi", ("malzeme", "tasiyici", "yapi_tipi", "yapi_turu",
                                           "material")),
    "@DUZEN": ("DUZEN_ALANI", "yapi", ("nizam", "duzen", "yapilasma")),
    "@GENISLIK": ("GENISLIK_ALANI", "yol", ("genislik", "width")),
    "@KAPLAMA": ("KAPLAMA_ALANI", "yol", ("kaplama", "surface")),
}
DISTANCE_ROLES = {"dere": "DERE", "fay": "FAY", "toplanma": "TOPLANMA", "itfaiye": "ITFAIYE",
                  "hastane": "HASTANE"}
RASTER_ROLES = {"dem": "DEM", "dem_goreli": "DEM", "egim": "EGIM", "lst": "LST"}


def _meters(crs):
    if hasattr(Qgis, "DistanceUnit"):
        return crs.mapUnits() == Qgis.DistanceUnit.Meters
    return crs.mapUnits() == QgsUnitTypes.DistanceUnit.DistanceMeters


def _find_field(fields, hints):
    names = [f.name() for f in fields]
    normed = [norm_tr(n).lower() for n in names]
    for h in hints:
        hn = norm_tr(h).lower()
        for n, nn in zip(names, normed):
            if nn == hn:
                return n
    for h in hints:
        hn = norm_tr(h).lower()
        for n, nn in zip(names, normed):
            if hn in nn:
                return n
    return None


class _MeasureEngine:
    """Ölçüm metinlerini bölge başına ham değer listelerine çevirir."""

    def __init__(self, alg, parameters, context, feedback, source, feats, geoms):
        self.alg = alg
        self.parameters = parameters
        self.context = context
        self.feedback = feedback
        self.source = source
        self.feats = feats
        self.geoms = geoms
        self.crs = source.sourceCrs()
        self.n = len(feats)
        self.cache = {}
        self.warnings = []
        self.notes = []
        self._layers = {}
        self._overlay_cache = {}
        self._area_ha = None
        self._resolved = {}

    # -- yardımcılar ------------------------------------------------------
    def _warn(self, text):
        if text not in self.warnings:
            self.warnings.append(text)

    def layer(self, pname):
        if pname not in self._layers:
            self._layers[pname] = self.alg.parameterAsSource(self.parameters, pname, self.context)
        return self._layers[pname]

    def _role_fields(self, role):
        if role == "bolge":
            return self.source.fields()
        src = self.layer("YAPI" if role == "yapi" else "YOL")
        return src.fields() if src is not None else None

    def resolve(self, token):
        if token in self._resolved:
            return self._resolved[token]
        pname, role, hints = PLACEHOLDERS[token]
        chosen = self.alg.parameterAsString(self.parameters, pname, self.context) or None
        fields = self._role_fields(role)
        if chosen is None and fields is not None:
            chosen = _find_field(fields, hints)
            if chosen:
                self.notes.append(f"{token} için '{chosen}' alanı ad ipucuyla seçildi.")
        self._resolved[token] = chosen
        return chosen

    def _substitute(self, measure):
        out = measure
        for token in sorted(PLACEHOLDERS, key=len, reverse=True):
            if token in out:
                name = self.resolve(token)
                if not name:
                    return None, token
                out = out.replace(token, name)
        return out, None

    def area_ha(self):
        if self._area_ha is None:
            da = QgsDistanceArea()
            da.setSourceCrs(self.crs, self.context.transformContext())
            ell = self.context.ellipsoid() if hasattr(self.context, "ellipsoid") else ""
            if (not ell or ell.upper() == "NONE") and self.crs.isGeographic():
                ell = "EPSG:7030"
                self.notes.append("Coğrafi KRS: alanlar WGS84 elipsoidi üzerinde hesaplandı.")
            if ell and ell.upper() != "NONE":
                da.setEllipsoid(ell)
            vals = []
            for g in self.geoms:
                if g is None or g.isEmpty():
                    vals.append(None)
                    continue
                a = da.measureArea(g)
                if hasattr(da, "convertAreaMeasurement") and hasattr(Qgis, "AreaUnit"):
                    a = da.convertAreaMeasurement(a, Qgis.AreaUnit.SquareMeters)
                vals.append(a / 10000.0 if a > 0 else None)
            self._area_ha = vals
        return self._area_ha

    def _zone_field(self, name):
        if self.source.fields().lookupField(name) < 0:
            self._warn(f"Bölge katmanında '{name}' alanı yok.")
            return None
        return [as_value(f[name]) for f in self.feats]

    def _transformed(self, src):
        xform = None
        if src.sourceCrs() != self.crs:
            xform = QgsCoordinateTransform(src.sourceCrs(), self.crs,
                                           self.context.transformContext())
        items = []
        empty = 0
        for f in src.getFeatures():
            check_cancel(self.feedback)
            g = f.geometry()
            if g is None or g.isEmpty():
                empty += 1
                continue
            g = QgsGeometry(g)
            if xform is not None:
                g.transform(xform)
            items.append((f, g))
        if empty:
            self._warn(f"'{src.sourceName()}' katmanında {empty} boş geometri atlandı.")
        return items

    def overlay(self, role):
        """Bölge başına [(öğe, kesişim alanı ya da uzunluğu)] listesi; katman yoksa None."""
        if role in self._overlay_cache:
            return self._overlay_cache[role]
        src = self.layer("YAPI" if role == "yapi" else "YOL")
        if src is None:
            self._overlay_cache[role] = None
            return None
        items = self._transformed(src)
        index = QgsSpatialIndex()
        for i, (_, g) in enumerate(items):
            index.addFeature(i, g.boundingBox())
        per_zone = []
        for z in self.geoms:
            check_cancel(self.feedback)
            hits = []
            if z is not None and not z.isEmpty():
                for i in index.intersects(z.boundingBox()):
                    f, g = items[i]
                    if not z.intersects(g):
                        continue
                    inter = z.intersection(g)
                    size = inter.area() if role == "yapi" else inter.length()
                    if size > 0:
                        hits.append((f, size))
            per_zone.append(hits)
        self._overlay_cache[role] = per_zone
        return per_zone

    # -- ölçümler ---------------------------------------------------------
    def value(self, measure):
        resolved, missing = self._substitute(measure)
        if resolved is None:
            self._warn(f"'{measure}' ölçümü için {missing} alanı bulunamadı; parametreden seçin.")
            return [None] * self.n
        if resolved not in self.cache:
            self.cache[resolved] = self._compute(resolved)
        return self.cache[resolved]

    def _compute(self, m):
        none = [None] * self.n
        head, _, rest = m.partition(":")
        head = head.strip().lower()
        if head == "alan_ha":
            return list(self.area_ha())
        if head == "yogunluk":
            name = self.resolve("@NUFUS")
            if not name:
                self._warn("Yoğunluk için nüfus alanı bulunamadı.")
                return none
            pops = self._zone_field(name)
            if pops is None:
                return none
            out = []
            nulls = 0
            for p, a in zip(pops, self.area_ha()):
                p = as_float(p)
                if p is None:
                    nulls += 1
                out.append(p / a if (p is not None and a) else None)
            if nulls:
                self._warn(f"Nüfus alanı '{name}' {nulls} bölgede boş.")
            return out
        if head == "alan":
            vals = self._zone_field(rest.strip())
            return none if vals is None else vals
        if head == "oran":
            if "/" not in rest:
                raise vu.VulnerabilityError(f"'{m}': oran ölçümü 'oran:alan1/alan2' olmalı.")
            a_name, b_name = [s.strip() for s in rest.split("/", 1)]
            a, b = self._zone_field(a_name), self._zone_field(b_name)
            if a is None or b is None:
                return none
            out = []
            for x, y in zip(a, b):
                x, y = as_float(x), as_float(y)
                out.append(100.0 * x / y if (x is not None and y) else None)
            return out
        if head == "raster":
            return self._raster(rest.strip().lower())
        if head == "uzaklik":
            return self._distance(rest.strip().lower())
        if head == "yapi":
            return self._yapi(rest.strip())
        if head == "yol":
            return self._yol(rest.strip())
        raise vu.VulnerabilityError(f"Bilinmeyen ölçüm: {m!r}")

    def _require_metric(self, what):
        if self.crs.isGeographic() or not _meters(self.crs):
            raise QgsProcessingException(
                f"{what} için bölge katmanı metre birimli projeksiyonlu bir KRS'de olmalı "
                f"(şu an {self.crs.authid() or self.crs.description()}). Ör. EPSG:5253.")

    def _distance(self, role):
        if role not in DISTANCE_ROLES:
            raise vu.VulnerabilityError(f"Bilinmeyen uzaklık katmanı: {role!r}")
        src = self.layer(DISTANCE_ROLES[role])
        if src is None:
            self._warn(f"Uzaklık ({role}) için katman verilmedi; gösterge eksik sayıldı.")
            return [None] * self.n
        self._require_metric("Uzaklık ölçümü")
        items = self._transformed(src)
        if not items:
            self._warn(f"'{role}' katmanında geometri yok.")
            return [None] * self.n
        out = []
        for z in self.geoms:
            check_cancel(self.feedback)
            if z is None or z.isEmpty():
                out.append(None)
                continue
            best = None
            for _, g in items:
                d = 0.0 if z.intersects(g) else z.distance(g)
                if best is None or d < best:
                    best = d
                if best == 0.0:
                    break
            out.append(best)
        return out

    def _raster(self, role):
        if role not in RASTER_ROLES:
            raise vu.VulnerabilityError(f"Bilinmeyen raster: {role!r}")
        layer = self.alg.parameterAsRasterLayer(self.parameters, RASTER_ROLES[role], self.context)
        if layer is None:
            self._warn(f"Raster ({role}) verilmedi; gösterge eksik sayıldı.")
            return [None] * self.n
        key = "__raster__" + RASTER_ROLES[role]
        if key not in self.cache:
            self.cache[key] = self._zonal_mean(layer)
        means = self.cache[key]
        if role == "dem_goreli":
            real = [v for v in means if v is not None]
            if not real:
                return [None] * self.n
            lo = min(real)
            return [None if v is None else v - lo for v in means]
        return list(means)

    def _zonal_mean(self, raster):
        import processing  # QGIS Processing eklentisi
        mem = QgsVectorLayer("MultiPolygon", "bolgeler", "memory")
        mem.setCrs(self.crs)
        prov = mem.dataProvider()
        prov.addAttributes([make_field("zid", "int")])
        mem.updateFields()
        feats = []
        for i, g in enumerate(self.geoms):
            if g is None or g.isEmpty():
                continue
            f = QgsFeature(mem.fields())
            f.setGeometry(g)
            f.setAttributes([i])
            feats.append(f)
        prov.addFeatures(feats)
        res = processing.run("native:zonalstatisticsfb", {
            "INPUT": mem, "INPUT_RASTER": raster, "RASTER_BAND": 1,
            "COLUMN_PREFIX": "zs_", "STATISTICS": [2], "OUTPUT": "TEMPORARY_OUTPUT",
        }, context=self.context, feedback=None, is_child_algorithm=True)
        out_layer = QgsProcessingUtils.mapLayerFromString(res["OUTPUT"], self.context)
        means = [None] * self.n
        if out_layer is None:
            self._warn(f"'{raster.name()}' için bölgesel istatistik alınamadı.")
            return means
        for f in out_layer.getFeatures():
            means[int(f["zid"])] = as_float(f["zs_mean"])
        nulls = sum(1 for g, v in zip(self.geoms, means) if v is None and g is not None)
        if nulls:
            self._warn(f"'{raster.name()}' {nulls} bölgeyi kapsamıyor ya da veri yok.")
        return means

    def _field_check(self, role, name):
        fields = self._role_fields(role)
        if fields is None or fields.lookupField(name) < 0:
            self._warn(f"{'Yapı' if role == 'yapi' else 'Yol'} katmanında '{name}' alanı yok.")
            return False
        return True

    def _yapi(self, spec):
        parts = spec.split(":")
        kind = parts[0].lower()
        ov = self.overlay("yapi")
        if ov is None:
            self._warn(f"Yapı katmanı verilmedi; 'yapi:{spec}' göstergesi eksik sayıldı.")
            return [None] * self.n
        zone_area = [g.area() if g is not None and not g.isEmpty() else None for g in self.geoms]
        if kind in ("taks", "acik"):
            out = []
            for hits, za in zip(ov, zone_area):
                if not za:
                    out.append(None)
                    continue
                taks = min(1.0, sum(s for _, s in hits) / za)
                out.append(taks if kind == "taks" else 100.0 * (1.0 - taks))
            return out
        if len(parts) < 2:
            raise vu.VulnerabilityError(f"'yapi:{spec}' eksik: alan adı gerekli.")
        fname = parts[1]
        if not self._field_check("yapi", fname):
            return [None] * self.n
        out = []
        nulls = 0
        for hits, za in zip(ov, zone_area):
            if kind == "kategori":
                pairs = [(as_value(f[fname]), s) for f, s in hits]
                nulls += sum(1 for t, _ in pairs if t is None)
                pairs = [(t, s) for t, s in pairs if t is not None]
                out.append(pairs or None)
            elif kind in ("ort", "kaks"):
                acc = wsum = 0.0
                for f, s in hits:
                    v = as_float(f[fname])
                    if v is None:
                        nulls += 1
                        continue
                    acc += v * s
                    wsum += s
                if kind == "ort":
                    out.append(acc / wsum if wsum > 0 else None)
                else:
                    out.append(acc / za if (za and wsum > 0) else (0.0 if za and not hits else None))
            elif kind == "pay":
                if len(parts) < 3:
                    raise vu.VulnerabilityError(f"'yapi:{spec}': pay ölçümü sözcük listesi ister.")
                kws = [norm_tr(w.strip()) for w in parts[2].split(",") if w.strip()]
                tot = hit = 0.0
                for f, s in hits:
                    t = as_value(f[fname])
                    if t is None:
                        nulls += 1
                        continue
                    tot += s
                    if any(k in norm_tr(str(t)) for k in kws):
                        hit += s
                out.append(100.0 * hit / tot if tot > 0 else None)
            else:
                raise vu.VulnerabilityError(f"Bilinmeyen yapı ölçümü: 'yapi:{spec}'")
        if nulls:
            self._warn(f"Yapı alanı '{fname}' {nulls} yapıda boş; o yapılar bu ölçümde atlandı.")
        return out

    def _yol(self, spec):
        parts = spec.split(":")
        kind = parts[0].lower()
        if len(parts) < 2:
            raise vu.VulnerabilityError(f"'yol:{spec}' eksik: alan adı gerekli.")
        ov = self.overlay("yol")
        if ov is None:
            self._warn(f"Yol katmanı verilmedi; 'yol:{spec}' göstergesi eksik sayıldı.")
            return [None] * self.n
        fname = parts[1]
        if not self._field_check("yol", fname):
            return [None] * self.n
        threshold = None
        kws = None
        if kind in ("esikalti", "esikustu"):
            if len(parts) < 3:
                raise vu.VulnerabilityError(f"'yol:{spec}': eşik değeri gerekli.")
            threshold = float(parts[2].replace(",", "."))
        elif kind == "pay":
            if len(parts) < 3:
                raise vu.VulnerabilityError(f"'yol:{spec}': sözcük listesi gerekli.")
            kws = [norm_tr(w.strip()) for w in parts[2].split(",") if w.strip()]
        elif kind != "ort":
            raise vu.VulnerabilityError(f"Bilinmeyen yol ölçümü: 'yol:{spec}'")
        out = []
        nulls = 0
        for hits in ov:
            acc = tot = 0.0
            for f, s in hits:
                raw = as_value(f[fname])
                if raw is None:
                    nulls += 1
                    continue
                if kind == "pay":
                    tot += s
                    if any(k in norm_tr(str(raw)) for k in kws):
                        acc += s
                    continue
                v = as_float(raw)
                if v is None:
                    nulls += 1
                    continue
                tot += s
                if kind == "ort":
                    acc += v * s
                elif kind == "esikalti" and v < threshold:
                    acc += s
                elif kind == "esikustu" and v >= threshold:
                    acc += s
            if tot <= 0:
                out.append(None)
            elif kind == "ort":
                out.append(acc / tot)
            else:
                out.append(100.0 * acc / tot)
        if nulls:
            self._warn(f"Yol alanı '{fname}' {nulls} yol parçasında boş ya da sayı değil; atlandı.")
        return out


class KirilganlikEndeksiAlgorithm(OngoruBaseAlgorithm):
    BOLGE = "BOLGE"
    ANAHTAR = "ANAHTAR"
    TEHLIKELER = "TEHLIKELER"
    OZEL = "OZEL"
    OZEL_KOD = "OZEL_KOD"
    SINIFLAMA = "SINIFLAMA"
    AGIRLIKLAR = "AGIRLIKLAR"
    LOG = "LOG"
    OUTPUT = "OUTPUT"
    RAPOR = "RAPOR"

    def name(self):
        return "kirilganlik_endeksi"

    def displayName(self):
        return "4. Kırılganlık Endeksi (Pay / Payda) ve Bileşik Endeks"

    def shortHelpString(self):
        presets = "\n".join(f"[{vu.PRESETS[k]['kod']}] {vu.PRESETS[k]['ad']}:\n"
                            f"{vu.PRESETS[k]['metin']}" for k in HAZARD_KEYS)
        return (
            "Her gösterge 1-5 puanlanır; K = Π(pay: maruziyet ve hassasiyet) / Π(payda: uyum "
            "kapasitesi). Eksik veri uydurulmaz: puan 1 (etkisiz) alınır ve bölgenin EKSIK "
            "sayısına yazılır. Kategori eşleşmesi Türkçe karakter ve büyük/küçük harften "
            "bağımsızdır ('YIĞMA' = 'yığma').\n\n"
            "Düzeltmeler: nüfus mutlak sayıyla değil yoğunlukla (kişi/ha) puanlanır; selde "
            "yüksek kot DAHA AZ maruz (göreli yükseklik), düz alan DAHA ÇOK maruz (eğim pay "
            "tarafında).\n\n"
            "Endeksler min-max (0-100) ölçeklenip ağırlıklı ortalamayla bileşik endeks (K_BIL) "
            "üretilir. Sınıflama: Jenks, eşit sayılı, eşit aralık ya da geometrik; 1. derece = "
            "çok yüksek kırılganlık. Çıktı alanları anahtar alanıyla eşleştirilerek yazılır.\n\n"
            "Özel endeks: her satır 'KOD | Etiket | pay/payda | ölçüm | puanlama'. Ölçümler: "
            "alan:<alan>, alan_ha, yogunluk, oran:<a>/<b>, raster:dem|dem_goreli|egim|lst, "
            "uzaklik:dere|fay|toplanma|itfaiye|hastane, yapi:taks|acik|kaks:<alan>|ort:<alan>|"
            "kategori:<alan>|pay:<alan>:<sözcükler>, yol:ort:<alan>|pay:<alan>:<sözcükler>|"
            "esikalti:<alan>:<değer>|esikustu:<alan>:<değer>. Puanlama: '<=100:5; <500:3; *:1', "
            "'yığma,taş=4; betonarme=2; *=3', 'dilim', 'dilim ters', 'esit', 'yuvarla'.\n\n"
            "Ön ayarlar (Tire örneği eşikleri; başka yerleşimde gözden geçirin, metni "
            "kopyalayıp özel endeks olarak düzenleyebilirsiniz):\n" + presets + "\n"
            + YONTEM_KAYNAKLARI + "\n\n" + ATTRIBUTION
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.BOLGE, "Bölge / mahalle katmanı (poligon)",
            [QgsProcessing.SourceType.TypeVectorPolygon]))
        self.addParameter(QgsProcessingParameterField(
            self.ANAHTAR, "Anahtar alanı (benzersiz)", None, self.BOLGE, FIELD_ANY))
        self.addParameter(QgsProcessingParameterEnum(
            self.TEHLIKELER, "Hazır endeksler", [vu.PRESETS[k]["ad"] for k in HAZARD_KEYS],
            allowMultiple=True, defaultValue=[0, 1, 2], optional=True))
        self.addParameter(QgsProcessingParameterString(
            self.OZEL, "Özel endeks göstergeleri (satır başına bir gösterge)", "",
            multiLine=True, optional=True))
        self.addParameter(QgsProcessingParameterString(
            self.OZEL_KOD, "Özel endeks kodu", "K_O", optional=True))
        for pname, label in (("NUFUS_ALANI", "Nüfus alanı"),
                             ("COCUK_ALANI", "Çocuk (0-14) nüfus alanı"),
                             ("YASLI_ALANI", "Yaşlı (65+) nüfus alanı")):
            self.addParameter(QgsProcessingParameterField(
                pname, label + " (boş = ad ipucuyla bul)", None, self.BOLGE, FIELD_NUMERIC,
                optional=True))
        self.addParameter(QgsProcessingParameterFeatureSource(
            "YAPI", "Yapı katmanı (poligon)", [QgsProcessing.SourceType.TypeVectorPolygon],
            optional=True))
        for pname, label, kind in (("KAT_ALANI", "Yapı kat sayısı alanı", FIELD_NUMERIC),
                                   ("MALZEME_ALANI", "Yapı malzemesi / taşıyıcı alanı", FIELD_ANY),
                                   ("DUZEN_ALANI", "Yapı nizamı alanı", FIELD_ANY)):
            self.addParameter(QgsProcessingParameterField(
                pname, label, None, "YAPI", kind, optional=True))
        self.addParameter(QgsProcessingParameterFeatureSource(
            "YOL", "Yol katmanı (çizgi)", [QgsProcessing.SourceType.TypeVectorLine], optional=True))
        for pname, label, kind in (("GENISLIK_ALANI", "Yol genişliği alanı (m)", FIELD_NUMERIC),
                                   ("KAPLAMA_ALANI", "Yol kaplama alanı", FIELD_ANY)):
            self.addParameter(QgsProcessingParameterField(
                pname, label, None, "YOL", kind, optional=True))
        for pname, label in (("DERE", "Dere / akarsu katmanı"), ("FAY", "Diri fay katmanı"),
                             ("TOPLANMA", "Afet toplanma alanları"), ("ITFAIYE", "İtfaiye"),
                             ("HASTANE", "Hastane / sağlık tesisi")):
            self.addParameter(QgsProcessingParameterFeatureSource(
                pname, label, [TYPE_VECTOR_ANY], optional=True))
        for pname, label in (("DEM", "Sayısal yükseklik modeli (DEM)"),
                             ("EGIM", "Eğim rasteri (%)"),
                             ("LST", "Yüzey sıcaklığı rasteri (°C)")):
            self.addParameter(QgsProcessingParameterRasterLayer(pname, label, optional=True))
        self.addParameter(QgsProcessingParameterEnum(
            self.SINIFLAMA, "Sınıflama yöntemi", [vu.BREAK_METHODS[k][0] for k in BREAK_KEYS],
            defaultValue=BREAK_KEYS.index("geometrik")))
        weights = "; ".join(f"{k}={v:.2f}" for k, v in vu.COMPOSITE_WEIGHTS.items()) + "; K_O=0.25"
        adv = [
            QgsProcessingParameterString(self.AGIRLIKLAR, "Bileşik endeks ağırlıkları (KOD=ağırlık)",
                                         weights, optional=True),
            QgsProcessingParameterBoolean(self.LOG, "Bileşikte logaritmik normalleştirme", False),
        ]
        for p in adv:
            p.setFlags(p.flags() | FLAG_ADVANCED)
            self.addParameter(p)
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, "Kırılganlık endeksi", QgsProcessing.SourceType.TypeVectorPolygon))
        self.addParameter(QgsProcessingParameterFileDestination(
            self.RAPOR, "HTML rapor", "HTML dosyaları (*.html)", optional=True))

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.BOLGE, context)
        if source is None:
            raise QgsProcessingException("Bölge katmanı okunamadı.")
        key_f = self.parameterAsString(parameters, self.ANAHTAR, context)
        chosen = self.parameterAsEnums(parameters, self.TEHLIKELER, context)
        hazards = [HAZARD_KEYS[i] for i in chosen]
        custom_text = self.parameterAsString(parameters, self.OZEL, context) or ""
        indices = []
        try:
            for h in hazards:
                indices.append((vu.PRESETS[h]["kod"], vu.PRESETS[h]["ad"],
                                vu.preset_indicators(h)))
            if custom_text.strip():
                code = (self.parameterAsString(parameters, self.OZEL_KOD, context)
                        or "K_O").strip().upper()
                if code in [c for c, _, _ in indices]:
                    raise QgsProcessingException(f"Özel endeks kodu {code} hazır endeksle çakışıyor.")
                indices.append((code, "Özel endeks", vu.parse_indicators(custom_text)))
        except vu.VulnerabilityError as exc:
            raise QgsProcessingException(str(exc)) from None
        if not indices:
            raise QgsProcessingException("En az bir hazır endeks seçin ya da özel endeks tanımlayın.")

        feats, geoms, keys = [], [], []
        seen = set()
        for f in source.getFeatures():
            check_cancel(feedback)
            k = as_value(f[key_f])
            if k is None or str(k).strip() == "":
                raise QgsProcessingException(f"Anahtar alanı '{key_f}' boş olan bölge var; "
                                             "tüm bölgelerin anahtarı dolu olmalı.")
            if k in seen:
                raise QgsProcessingException(f"Anahtar tekrar ediyor: {k!r}.")
            seen.add(k)
            keys.append(k)
            feats.append(f)
            g = f.geometry()
            geoms.append(QgsGeometry(g) if g is not None and not g.isEmpty() else None)
        if not feats:
            raise QgsProcessingException("Bölge katmanında öğe yok.")
        empty = sum(1 for g in geoms if g is None)
        if empty:
            feedback.pushWarning(f"{empty} bölgenin geometrisi boş; alan/uzaklık ölçümleri eksik.")

        engine = _MeasureEngine(self, parameters, context, feedback, source, feats, geoms)
        method = BREAK_KEYS[self.parameterAsEnum(parameters, self.SINIFLAMA, context)]
        break_fn = vu.BREAK_METHODS[method][1]
        results = []
        all_warnings = []
        for step, (code, title, inds) in enumerate(indices):
            check_cancel(feedback)
            feedback.pushInfo(f"{code} ({title}) hesaplanıyor: {vu.formula_text(inds, code)}")
            raw = {}
            try:
                for ind in inds:
                    check_cancel(feedback)
                    raw[ind.code] = engine.value(ind.measure)
                res = vu.compute_index(inds, raw)
            except vu.VulnerabilityError as exc:
                raise QgsProcessingException(f"{code}: {exc}") from None
            res["breaks"] = break_fn(res["index"], 5)
            res["classes"] = vu.classify(res["index"], res["breaks"])
            all_warnings.extend(f"{code}: {w}" for w in res["warnings"])
            results.append((code, title, inds, res))
            feedback.setProgress(int(80 * (step + 1) / len(indices)))
        all_warnings = engine.warnings + all_warnings
        for note in engine.notes:
            feedback.pushInfo(note)
        push_warnings(feedback, all_warnings)

        comp = None
        if len(results) >= 2:
            try:
                weights = vu.parse_weights(self.parameterAsString(parameters, self.AGIRLIKLAR,
                                                                  context))
            except vu.VulnerabilityError as exc:
                raise QgsProcessingException(str(exc)) from None
            series = {code: res["index"] for code, _, _, res in results}
            missing_w = [c for c in series if weights.get(c, 0) <= 0]
            if missing_w:
                if len(missing_w) == len(series):
                    feedback.pushWarning("Hiçbir endeksin ağırlığı yok; eşit ağırlık kullanıldı.")
                    weights = {c: 1.0 for c in series}
                else:
                    feedback.pushWarning("Ağırlığı olmayan endeks(ler) bileşiğe katılmadı: "
                                         + ", ".join(missing_w))
            comp = vu.composite(series, weights, self.parameterAsBool(parameters, self.LOG, context))
            comp["breaks"] = break_fn(comp["values"], 5)
            comp["classes"] = vu.classify(comp["values"], comp["breaks"])

        specs = []
        for code, _, inds, _ in results:
            specs += [(f"{code}_{ind.code}", "int") for ind in inds]
            specs += [(code, "double"), (f"{code}_PAY", "double"), (f"{code}_PAYDA", "double"),
                      (f"{code}_EKSIK", "int"), (f"{code}_DERECE", "int"),
                      (f"{code}_SINIF", "string")]
        if comp is not None:
            specs += [("K_BIL", "double"), ("BIL_DERECE", "int"), ("BIL_SINIF", "string"),
                      ("BIL_TEHLIKE", "int")]
        fields, names = make_fields(specs, base=source.fields())

        by_key = {}
        for r, k in enumerate(keys):
            vals = []
            for code, _, inds, res in results:
                vals += [res["scores"][ind.code][r] for ind in inds]
                cls = res["classes"][r]
                vals += [res["index"][r], res["numerator"][r], res["denominator"][r],
                         res["missing_count"][r], cls,
                         vu.CLASS_LABELS[cls - 1] if cls else None]
            if comp is not None:
                cls = comp["classes"][r]
                vals += [comp["values"][r], cls, vu.CLASS_LABELS[cls - 1] if cls else None,
                         sum(1 for c in comp["normalized"]
                             if comp["normalized"][c][r] is not None
                             and comp["normalized"][c][r] >= 50.0)]
            by_key[k] = vals

        sink, dest = self.parameterAsSink(parameters, self.OUTPUT, context, fields,
                                          source.wkbType(), source.sourceCrs())
        if sink is None:
            raise QgsProcessingException("Çıktı katmanı oluşturulamadı.")
        for f in source.getFeatures():
            check_cancel(feedback)
            nf = QgsFeature(fields)
            nf.setGeometry(f.geometry())
            nf.setAttributes(list(f.attributes()) + by_key[as_value(f[key_f])])
            sink.addFeature(nf, FAST_INSERT)

        out = {self.OUTPUT: dest, "UYARILAR": all_warnings, "ALANLAR": names}
        report_path = self.parameterAsFileOutput(parameters, self.RAPOR, context)
        if report_path:
            self._write_report(report_path, results, comp, keys, all_warnings, method)
            out[self.RAPOR] = report_path
        feedback.setProgress(100)
        return out

    @staticmethod
    def _write_report(path, results, comp, keys, warnings, method):
        sections = []
        for code, title, inds, res in results:
            rows = [[i.code, i.label, i.role, i.measure, i.scoring_text,
                     res["info"][i.code]["eksik"], res["info"][i.code]["eslesmeyen"]]
                    for i in inds]
            sections.append((f"{code} - {title}: {vu.formula_text(inds, code)}",
                             ["Kod", "Gösterge", "Rol", "Ölçüm", "Puanlama", "Eksik bölge",
                              "Eşleşmeyen kategori"], rows))
            counts = [sum(1 for c in res["classes"] if c == d) for d in range(1, 6)]
            sections.append((f"{code} sınıfları ({vu.BREAK_METHODS[method][0]})",
                             ["Derece", "Alt sınır", "Üst sınır", "Bölge sayısı"],
                             [[vu.CLASS_LABELS[d - 1],
                               f"{res['breaks'][5 - d]:.4g}" if res["breaks"] else "",
                               f"{res['breaks'][6 - d]:.4g}" if res["breaks"] else "",
                               counts[d - 1]] for d in range(1, 6)]))
            order = sorted(range(len(keys)), key=lambda r: res["index"][r], reverse=True)[:10]
            sections.append((f"{code}: en kırılgan 10 bölge", ["Anahtar", code, "Derece", "Eksik"],
                             [[keys[r], f"{res['index'][r]:.4g}", res["classes"][r],
                               res["missing_count"][r]] for r in order]))
        if comp is not None:
            sections.append(("Bileşik endeks ağırlıkları", ["Endeks", "Ağırlık"],
                             [[c, f"{w:.3f}"] for c, w in comp["weights"].items()]))
        text = vu.html_report("Kırılganlık endeksi raporu", sections, warnings,
                              YONTEM_KAYNAKLARI + " " + ATTRIBUTION)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
