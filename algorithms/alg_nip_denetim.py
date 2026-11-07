# -*- coding: utf-8 -*-
"""MPYY 1.1.7 NİP topoloji ve öznitelik denetimi (bütün GeoPackage).

Katmanlardaki "⚠ Kontrol" alanı her nesneyi tek başına denetler. Bu araç
bütün çizimi birlikte tarar ve bulguları tek bir katmana yazar: geçersiz
geometrinin yeri, çakışmanın kendisi (ortak alan poligonu), plan sınırı
içinde hiçbir arazi kullanımına ya da yol platformuna ayrılmamış boşluklar.
"""
from __future__ import annotations

from qgis.core import (
    QgsFeature,
    QgsFeatureRequest,
    QgsFeatureSink,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterFeatureSink,
    QgsProcessingOutputNumber,
    QgsProcessingParameterFile,
    QgsProject,
    QgsSpatialIndex,
    QgsVectorLayer,
    QgsWkbTypes,
)

from ..core.compat import FIELD_DOUBLE, FIELD_LONG, FIELD_STRING
from ..core.nip_checks import (
    MIN_LINE_LENGTH,
    MIN_OVERLAP_AREA,
    MIN_PART_AREA,
    MOSAIC_TYPES,
    PLAN_BOUNDARY_TYPE,
    ROAD_CENTER_TYPE,
    ROAD_PLATFORM_TYPE,
)
from ..core.nip_workspace import caption, get_nip_schema

_POLY = ("MultiPolygon", "Polygon")
_LINE = ("LineString", "MultiLineString")


def _wkb_multipolygon():
    from qgis.core import Qgis
    return Qgis.WkbType.MultiPolygon if hasattr(Qgis, "WkbType") else QgsWkbTypes.Type.MultiPolygon


def _as_area(geometry: QgsGeometry, pad: float) -> QgsGeometry | None:
    """Bulgu geometrisini çokgen yapar: çizgi/nokta bulgular küçük bir tamponla gösterilir."""
    if geometry is None or geometry.isEmpty():
        return None
    if geometry.type() == QgsWkbTypes.GeometryType.PolygonGeometry:
        out = QgsGeometry(geometry)
    else:
        out = geometry.buffer(pad, 8)
    if out.isEmpty():
        return None
    out.convertToMultiType()
    return out


class NipDenetimAlgorithm(QgsProcessingAlgorithm):
    INPUT = "INPUT"
    OUTPUT = "OUTPUT"

    def name(self):
        return "nip_mpyy_denetim"

    def displayName(self):
        return "MPYY NİP Topoloji ve Öznitelik Denetimi"

    def group(self):
        return "02. NİP Çizim Veritabanı ve Şablonu"

    def groupId(self):
        return "02_nip_veritabani"

    def createInstance(self):
        return NipDenetimAlgorithm()

    def shortHelpString(self):
        return (
            "MPYY 1.1.7 NİP GeoPackage'ını baştan sona denetler ve bulguları bir katmana yazar:\n"
            "• geçersiz geometri (yeriyle), boş geometri, çok küçük parça "
            f"(< {MIN_PART_AREA:g} m²), çok kısa çizgi (< {MIN_LINE_LENGTH:g} m);\n"
            "• zorunlu özniteliği boş nesneler;\n"
            "• arazi kullanım katmanları ve yol platformu (DigerYolNesneleri) arasındaki çakışmalar "
            f"(ortak alan ≥ {MIN_OVERLAP_AREA:g} m²; kenar paylaşmak çakışma değildir);\n"
            "• plan sınırı dışına taşan nesneler ve plan sınırı içinde hiçbir kullanıma "
            "ayrılmamış boşluklar;\n"
            "• platformu üretilmemiş yol orta aksları (Yolorta).\n\n"
            "Sınırlar, koruma, afet tehlike, havza ve mania gibi bindirme katmanları arazi "
            "kullanımıyla çakışabilir; bunlar çakışma denetimine girmez.\n"
            "Denetim kayıtlı veriyi okur: önce düzenlemeleri kaydedin."
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFile(
            self.INPUT, "MPYY 1.1.7 NİP GeoPackage (.gpkg)", extension="gpkg"))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, "NİP denetim bulguları", QgsProcessing.SourceType.TypeVectorPolygon))
        self.addOutput(QgsProcessingOutputNumber("BULGU_SAYISI", "Bulgu sayısı"))

    def processAlgorithm(self, parameters, context, feedback):
        path = self.parameterAsFile(parameters, self.INPUT, context)
        schema = get_nip_schema()
        types = {ft["name"]: ft for ft in schema["feature_types"] if ft["geometry"] in _POLY + _LINE}

        layers = {}
        for name in types:
            # Varsayılan stil yüklenmez: içindeki "Kontrol" sanal alanı her nesnede
            # yeniden hesaplanır ve denetimi on katına kadar yavaşlatır.
            options = QgsVectorLayer.LayerOptions(QgsProject.instance().transformContext())
            options.loadDefaultStyle = False
            layer = QgsVectorLayer(f"{path}|layername={name}", name, "ogr", options)
            if layer.isValid():
                layers[name] = layer
        if not layers:
            raise QgsProcessingException("Dosyada MPYY 1.1.7 NİP katmanı bulunamadı.")
        crs = next(iter(layers.values())).crs()
        if crs.isGeographic():
            raise QgsProcessingException("Katmanlar coğrafi KRS'de; alan ve uzunluk denetimi için izdüşümlü KRS gerekir.")

        fields = QgsFields()
        fields.append(QgsField("katman", FIELD_STRING))
        fields.append(QgsField("nesne_fid", FIELD_LONG))
        fields.append(QgsField("diger_katman", FIELD_STRING))
        fields.append(QgsField("diger_nesne_fid", FIELD_LONG))
        fields.append(QgsField("kontrol", FIELD_STRING))
        fields.append(QgsField("aciklama", FIELD_STRING))
        fields.append(QgsField("olcu", FIELD_DOUBLE))
        sink, dest = self.parameterAsSink(parameters, self.OUTPUT, context, fields, _wkb_multipolygon(), crs)
        if sink is None:
            raise QgsProcessingException("Çıktı katmanı oluşturulamadı.")

        counts = {}

        def bulgu(geometry, katman, fid, kontrol, aciklama, olcu=None, diger=None, diger_fid=None, pad=1.0):
            area = _as_area(geometry, pad)
            if area is None:
                return
            f = QgsFeature(fields)
            f.setGeometry(area)
            f.setAttributes([caption(katman), fid, caption(diger) if diger else None, diger_fid,
                             kontrol, aciklama, None if olcu is None else round(float(olcu), 2)])
            sink.addFeature(f, QgsFeatureSink.Flag.FastInsert)
            counts[kontrol] = counts.get(kontrol, 0) + 1

        mosaic = []  # (tür, fid, geometri)
        plan_parts = []
        roads = []
        total = max(1, len(layers))
        for step, (name, layer) in enumerate(sorted(layers.items())):
            if feedback.isCanceled():
                return {}
            feedback.setProgress(60.0 * step / total)
            ft = types[name]
            required = [f["name"] for f in ft["fields"] if f.get("required") and f["name"] != "symbolizer"]
            is_poly = ft["geometry"] in _POLY
            request = QgsFeatureRequest().setSubsetOfAttributes(required, layer.fields())
            for feature in layer.getFeatures(request):
                fid = feature.id()
                geom = feature.geometry()
                if geom is None or geom.isEmpty():
                    feedback.pushWarning(f"{caption(name)} #{fid}: geometri yok")
                    counts["geometri yok"] = counts.get("geometri yok", 0) + 1
                    continue
                for error in geom.validateGeometry():
                    where = QgsGeometry.fromPointXY(error.where()) if error.hasWhere() else geom
                    bulgu(where, name, fid, "geçersiz geometri", error.what(), pad=2.0)
                if is_poly:
                    for part in geom.asGeometryCollection():
                        if part.area() < MIN_PART_AREA:
                            bulgu(part, name, fid, "çok küçük parça", f"{part.area():.1f} m²", part.area(), pad=2.0)
                elif geom.length() < MIN_LINE_LENGTH:
                    bulgu(geom, name, fid, "çok kısa çizgi", f"{geom.length():.2f} m", geom.length(), pad=2.0)
                for fname in required:
                    value = feature[fname]
                    if value is None or (hasattr(value, "isNull") and value.isNull()) or str(value).strip() == "":
                        bulgu(geom, name, fid, "eksik öznitelik", caption(fname))
                valid = geom if geom.isGeosValid() else geom.makeValid()
                if name in MOSAIC_TYPES:
                    mosaic.append((name, fid, valid))
                elif name == PLAN_BOUNDARY_TYPE:
                    plan_parts.append(valid)
                elif name == ROAD_CENTER_TYPE:
                    roads.append((fid, geom))

        # Çakışmalar: tüm zemin katmanları tek bir uzamsal dizinde.
        index = QgsSpatialIndex()
        for i, (_, _, geom) in enumerate(mosaic):
            f = QgsFeature(i)
            f.setGeometry(geom)
            index.addFeature(f)
        for i, (name, fid, geom) in enumerate(mosaic):
            if feedback.isCanceled():
                return {}
            feedback.setProgress(60.0 + 25.0 * i / max(1, len(mosaic)))
            for j in index.intersects(geom.boundingBox()):
                if j <= i:
                    continue
                other_name, other_fid, other = mosaic[j]
                common = geom.intersection(other)
                polys = [p for p in common.asGeometryCollection()
                         if p.type() == QgsWkbTypes.GeometryType.PolygonGeometry and p.area() > 0]
                area = sum(p.area() for p in polys)
                if area >= MIN_OVERLAP_AREA:
                    label = "aynı katmanda çakışma" if other_name == name else "çakışma"
                    bulgu(QgsGeometry.collectGeometry(polys), name, fid, label,
                          f"{caption(name)} #{fid} ile {caption(other_name)} #{other_fid}: {area:.1f} m²",
                          area, other_name, other_fid)

        plan = QgsGeometry.unaryUnion(plan_parts) if plan_parts else None
        if plan is not None and not plan.isEmpty():
            for name, fid, geom in mosaic:
                outside = geom.difference(plan)
                if not outside.isEmpty() and outside.area() >= MIN_OVERLAP_AREA:
                    bulgu(outside, name, fid, "plan sınırı dışında", f"{outside.area():.1f} m²", outside.area())
            covered = QgsGeometry.unaryUnion([g for _, _, g in mosaic]) if mosaic else None
            gaps = plan.difference(covered) if covered is not None else QgsGeometry(plan)
            for part in gaps.asGeometryCollection():
                if part.type() == QgsWkbTypes.GeometryType.PolygonGeometry and part.area() >= MIN_OVERLAP_AREA:
                    bulgu(part, PLAN_BOUNDARY_TYPE, None, "boşluk",
                          "Plan sınırı içinde arazi kullanımı ya da yol platformu yok", part.area())
        else:
            feedback.pushWarning("PlanSiniri boş: plan dışı taşma ve boşluk denetimi yapılmadı.")

        platform = [g for n, _, g in mosaic if n == ROAD_PLATFORM_TYPE]
        platform_union = QgsGeometry.unaryUnion(platform) if platform else None
        for fid, geom in roads:
            on = geom.intersection(platform_union).length() if platform_union is not None else 0.0
            if on < 0.9 * geom.length():
                bulgu(geom, ROAD_CENTER_TYPE, fid, "yol platformu üretilmemiş",
                      f"Aksın %{100.0 * on / geom.length():.0f}'i platform üzerinde", geom.length(), pad=2.0)

        feedback.setProgress(100)
        if counts:
            feedback.pushInfo("Bulgular: " + ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())))
        else:
            feedback.pushInfo("Bulgu yok: çizim denetimden geçti.")
        return {self.OUTPUT: dest, "BULGU_SAYISI": sum(counts.values())}
