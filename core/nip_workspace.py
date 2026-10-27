# -*- coding: utf-8 -*-
"""1/5000 Nazım İmar Planı (NİP) MPYY 1.1.7 Çizim Veritabanı ve Şablonu Üretici Motoru.

PLN3113 NİP Stüdyosu için
Çevre, Şehircilik ve İklim Değişikliği Bakanlığı resmî Mekânsal Planlar Yapım
Yönetmeliği (MPYY) 1.1.7 XSD şemasına (nip.V.1.1.7.xsd) %100 uyumlu boş NİP çizim
veritabanını (GeoPackage), e-Plan SLD stillerini, Ek-1e detay kataloğu hiyerarşisini
ve akıllı form açılır menülerini (ValueMap) atomik olarak üretir.
"""
from __future__ import annotations

import base64
import contextlib
import json
import os
import re
import sqlite3
import tempfile
import uuid
from pathlib import Path

from osgeo import gdal, ogr, osr
from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsEditorWidgetSetup,
    QgsFieldConstraints,
    QgsProject,
    QgsRelation,
    QgsRuleBasedRenderer,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QBuffer, QByteArray, QIODevice
from qgis.PyQt.QtGui import QImage
from qgis.PyQt.QtXml import QDomDocument

gdal.UseExceptions()

RESOURCE_DIR = Path(__file__).resolve().parents[1] / "resources" / "mpyy_117"
SCHEMA_PATH = RESOURCE_DIR / "mpyy_schema.json"
HIERARCHY_PATH = RESOURCE_DIR / "mpyy_detail_hierarchy.json"
SLD_DIR = RESOURCE_DIR / "sld"
TARAMA_DIR = RESOURCE_DIR / "tarama"

YEREL_RESOURCE_DIR = Path(__file__).resolve().parents[1] / "resources" / "yerel_nip"
YEREL_TEMPLATE_PATH = YEREL_RESOURCE_DIR / "template.json"
YEREL_LOOKUPS_PATH = YEREL_RESOURCE_DIR / "lookups.json"

SCHEMA_MPYY_117 = "mpyy_117"
SCHEMA_YEREL_NIP = "yerel_nip"

KIND = "MPYY_XSD"
SCHEMA_VERSION = 5
GROUP_NAME = "MPYY 1.1.7 Nazım İmar Planı (NİP)"
YEREL_GROUP_NAME = "PLN3113 1/5000 NİP (Yerel Şablon)"

_OGR_GEOMETRY = {
    "MultiPolygon": ogr.wkbMultiPolygon,
    "Polygon": ogr.wkbPolygon,
    "LineString": ogr.wkbLineString,
    "MultiLineString": ogr.wkbMultiLineString,
    "Point": ogr.wkbPoint,
    "MultiPoint": ogr.wkbMultiPoint,
    None: ogr.wkbNone,
}
_OGR_FIELD = {
    "string": ogr.OFTString,
    "enum": ogr.OFTString,
    "double": ogr.OFTReal,
    "int": ogr.OFTInteger,
    "long": ogr.OFTInteger64,
    "dateTime": ogr.OFTDateTime,
}

NUMERIC_RULES = {
    "Taks": (0.0, 1.0, 0.01, 2, "TAKS bir oran: 0'dan büyük, en çok 1 olmalı (0,35 gibi)."),
    "EmsalKaks": (0.0, 100.0, 0.05, 2, "Emsal (KAKS) 0'dan büyük olmalı."),
    "Emsal": (0.0, 100.0, 0.05, 2, "Emsal 0'dan büyük olmalı."),
    "KatAdedi": (1, 300, 1, 0, "Kat adedi en az 1 olmalı."),
    "YapiYuksekligi": (0.0, 1000.0, 0.5, 2, "Yapı yüksekliği 0'dan büyük olmalı (metre)."),
    "Yukseklik": (0.0, 10000.0, 0.5, 2, "Yükseklik negatif olamaz (metre)."),
    "OnBahceMesafesi": (0.0, 1000.0, 0.5, 2, "Ön bahçe mesafesi negatif olamaz (metre)."),
    "YanBahceMesafesi": (0.0, 1000.0, 0.5, 2, "Yan bahçe mesafesi negatif olamaz (metre)."),
    "ArkaBahceMesafesi": (0.0, 1000.0, 0.5, 2, "Arka bahçe mesafesi negatif olamaz (metre)."),
    "YolGenisligi": (0.0, 1000.0, 0.5, 2, "Yol genişliği negatif olamaz (metre)."),
    "Genislik": (0.0, 1000.0, 0.5, 2, "Genişlik negatif olamaz (metre)."),
    "Yogunluk": (0.0, 5000.0, 1.0, 1, "Nüfus yoğunluğu negatif olamaz (kişi/ha)."),
}


def caption(code: str) -> str:
    """Teknik camelCase/PascalCase şema isimlerini okunabilir Türkçe başlığa çevirir."""
    text = re.sub(r"(?<=[a-zçğıöşü0-9])(?=[A-ZÇĞİÖŞÜ])", " ", str(code))
    return re.sub(r"(?<=[A-Za-z])(?=[0-9])|(?<=[0-9])(?=[A-Za-z])", " ", text).strip()


def _crs_srs(value):
    """QgsCoordinateReferenceSystem veya authid stringinden osr.SpatialReference üretir."""
    crs = value if isinstance(value, QgsCoordinateReferenceSystem) else QgsCoordinateReferenceSystem(str(value))
    if not crs.isValid():
        crs = QgsCoordinateReferenceSystem("EPSG:5253")
    srs = osr.SpatialReference()
    if srs.SetFromUserInput(crs.authid() or crs.toWkt()) != 0:
        raise ValueError("GDAL seçilen KRS'yi okuyamıyor")
    return srs


def get_nip_schema() -> dict:
    """MPYY 1.1.7 NİP şemasını döndürür."""
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["levels"]["NIP"]


def get_nip_hierarchy() -> list[dict]:
    """Ek-1e NİP sembol hiyerarşisi kayıtlarını döndürür."""
    with open(HIERARCHY_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["records"]


def _png_bytes(path: Path) -> bytes:
    """Raster tarama görselini sıkıştırılmış PNG baytlarına dönüştürür."""
    image = QImage(str(path))
    if image.isNull():
        return path.read_bytes()
    bytes_arr = QByteArray()
    buf = QBuffer(bytes_arr)
    buf.open(QIODevice.OpenModeFlag.WriteOnly if hasattr(QIODevice, "OpenModeFlag") else QIODevice.WriteOnly)
    image.save(buf, "PNG")
    return bytes(bytes_arr)


def _embed_images(symbol):
    """SLD raster tarama görsellerini taşınabilirlik için sembolün içine gömer (base64)."""
    for index in range(symbol.symbolLayerCount()):
        layer = symbol.symbolLayer(index)
        if layer.layerType() == "RasterFill" and hasattr(layer, "imageFilePath"):
            path = layer.imageFilePath()
            if path.startswith("file:"):
                from qgis.PyQt.QtCore import QUrl
                path = QUrl(path).toLocalFile()
            if path and not path.startswith("base64:") and Path(path).is_file():
                layer.setImageFilePath("base64:" + base64.b64encode(_png_bytes(Path(path))).decode("ascii"))
        sub = layer.subSymbol()
        if sub is not None:
            _embed_images(sub)


def configure_nip_layer(layer: QgsVectorLayer, ft: dict, codelists: dict) -> None:
    """Katmanda MPYY 1.1.7 öznitelik formlarını, ValueMap açılır kutularını ve kısıtları kurar."""
    fields = layer.fields()
    fid_idx = fields.indexFromName("fid")
    if fid_idx >= 0:
        layer.setEditorWidgetSetup(fid_idx, QgsEditorWidgetSetup("Hidden", {}))

    for f_info in ft["fields"]:
        fname = f_info["name"]
        idx = fields.indexFromName(fname)
        if idx < 0:
            continue
        layer.setFieldAlias(idx, caption(fname))
        ftype = f_info["type"]
        is_req = f_info["required"]

        if ftype == "enum" and f_info.get("codelist") in codelists:
            codes = codelists[f_info["codelist"]]
            entries = [] if is_req else [{"(boş)": "{2839923C-8B7D-419E-B84B-CA2FE9B80EC7}"}]
            entries += [{caption(c): c} for c in codes]
            layer.setEditorWidgetSetup(idx, QgsEditorWidgetSetup("ValueMap", {"map": entries}))
            if is_req:
                layer.setFieldConstraint(
                    idx, QgsFieldConstraints.Constraint.ConstraintNotNull,
                    QgsFieldConstraints.ConstraintStrength.ConstraintStrengthSoft
                )
        elif ftype == "dateTime":
            layer.setEditorWidgetSetup(
                idx,
                QgsEditorWidgetSetup(
                    "DateTime",
                    {"allow_null": not is_req, "calendar_popup": True,
                     "display_format": "dd.MM.yyyy HH:mm", "field_format": "yyyy-MM-ddTHH:mm:ss",
                     "field_iso_format": True}
                )
            )

    # Sayısal alan kontrolleri
    for fname, rule in NUMERIC_RULES.items():
        idx = fields.indexFromName(fname)
        if idx < 0:
            continue
        min_v, max_v, step, prec, reason = rule
        layer.setEditorWidgetSetup(
            idx,
            QgsEditorWidgetSetup(
                "Range",
                {"Min": min_v, "Max": max_v, "Step": step, "Precision": prec, "Style": "SpinBox", "AllowNull": True}
            )
        )
        layer.setConstraintExpression(idx, f'"{fname}" IS NULL OR ("{fname}" >= {min_v} AND "{fname}" <= {max_v})', reason)


def apply_sld_to_layer(layer: QgsVectorLayer, tname: str) -> bool:
    """Katmanda resmî e-Plan SLD stilini uygular ve taramaları gömer."""
    sld_path = SLD_DIR / f"{tname}.sld"
    if not sld_path.exists():
        return False
    text = sld_path.read_text(encoding="utf-8").replace("mpyy-tarama:", TARAMA_DIR.resolve().as_uri() + "/")
    with tempfile.TemporaryDirectory() as folder:
        tmp_file = Path(folder) / f"{tname}.sld"
        tmp_file.write_text(text, encoding="utf-8")
        msg, ok = layer.loadSldStyle(str(tmp_file))
        if ok and layer.renderer():
            symbol = layer.renderer().symbol() if hasattr(layer.renderer(), "symbol") else None
            if symbol:
                _embed_images(symbol)
            elif isinstance(layer.renderer(), QgsRuleBasedRenderer):
                for rule in layer.renderer().rootRule().children():
                    if rule.symbol():
                        _embed_images(rule.symbol())
        return ok


def create_mpyy_117_workspace(output_path: str, crs="EPSG:5253") -> str:
    """Bakanlığın MPYY 1.1.7 (nip.V.1.1.7.xsd) şemasına %100 uygun boş NİP GeoPackage üretir."""
    output = Path(output_path).resolve()
    if output.exists():
        raise FileExistsError(f"Hedef dosya zaten mevcut: {output}")
    if output.suffix.lower() != ".gpkg":
        raise ValueError("Çıktı uzantısı .gpkg olmalıdır.")

    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        root_data = json.load(f)
    schema = root_data["levels"]["NIP"]
    source_info = root_data.get("source", {})

    srs = _crs_srs(crs)
    staging = output.parent / (".nip-" + uuid.uuid4().hex)
    staging.mkdir(parents=True, exist_ok=True)
    staged = staging / "dataset.gpkg"

    try:
        ds = ogr.GetDriverByName("GPKG").CreateDataSource(str(staged))
        if ds is None:
            raise RuntimeError("GeoPackage oluşturulamadı.")

        for ft in schema["feature_types"]:
            geom_type = ft["geometry"]
            options = ["FID=fid"] + (["GEOMETRY_NAME=geom", "SPATIAL_INDEX=YES"] if geom_type else [])
            layer = ds.CreateLayer(ft["name"], srs if geom_type else None, _OGR_GEOMETRY[geom_type], options=options)
            if layer is None:
                raise RuntimeError(f"Katman oluşturulamadı: {ft['name']}")

            fields = [f for f in ft["fields"] if f["name"] != "symbolizer"]
            if any(f["name"] == "symbolizer" for f in ft["fields"]):
                fields.append([f for f in ft["fields"] if f["name"] == "symbolizer"][0])

            for f_info in fields:
                field_defn = ogr.FieldDefn(f_info["name"], _OGR_FIELD[f_info["type"]])
                if layer.CreateField(field_defn) != 0:
                    raise RuntimeError(f"Alan oluşturulamadı: {ft['name']}.{f_info['name']}")

        ds = None

        con = sqlite3.connect(staged)
        try:
            con.execute(
                "CREATE TABLE mpyy_metadata (dataset_id TEXT PRIMARY KEY, schema_version INTEGER NOT NULL, "
                "workspace_kind TEXT NOT NULL, plan_levels TEXT NOT NULL)"
            )
            con.execute("INSERT INTO mpyy_metadata VALUES (?, ?, ?, ?)", (str(uuid.uuid4()), SCHEMA_VERSION, KIND, "NIP"))

            con.execute(
                "CREATE TABLE mpyy_sema (plan_kademesi TEXT PRIMARY KEY, xsd_dosyasi TEXT NOT NULL, "
                "xsd_sha256 TEXT NOT NULL, hedef_ad_alani TEXT NOT NULL, kaynak_url TEXT NOT NULL, arsiv_sha256 TEXT NOT NULL)"
            )
            con.execute(
                "INSERT INTO gpkg_contents(table_name, data_type, identifier) VALUES ('mpyy_sema', 'attributes', 'MPYY şema kaynağı')"
            )
            con.execute(
                "INSERT INTO mpyy_sema VALUES (?, ?, ?, ?, ?, ?)",
                (
                    "NIP",
                    schema["xsd"]["file"],
                    schema["xsd"]["sha256"].replace(" ", ""),
                    schema["target_namespace"],
                    source_info.get("url", ""),
                    source_info.get("sha256", "").replace(" ", "")
                )
            )

            con.execute(
                "CREATE TABLE mpyy_detay_katalogu (id INTEGER PRIMARY KEY, sembol_adi TEXT NOT NULL, "
                "detay_sinifi TEXT NOT NULL, detay_alt_sinifi TEXT NOT NULL, plan_kademesi TEXT NOT NULL, "
                "geometri TEXT NOT NULL, plan_gml_tipi TEXT NOT NULL, sld_kurali TEXT NOT NULL, kaynak_sayfa INTEGER NOT NULL)"
            )
            con.execute(
                "INSERT INTO gpkg_contents(table_name, data_type, identifier) VALUES ('mpyy_detay_katalogu', 'attributes', 'Ek-1e detay kataloğu hiyerarşisi')"
            )
            hier_records = get_nip_hierarchy()
            con.executemany(
                "INSERT INTO mpyy_detay_katalogu (sembol_adi, detay_sinifi, detay_alt_sinifi, plan_kademesi, geometri, "
                "plan_gml_tipi, sld_kurali, kaynak_sayfa) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (r["sembol_adi"], r["detay_sinifi"], r["detay_alt_sinifi"], r["plan_kademesi"], r["geometri"],
                     r["plan_gml_tipi"], r["sld_kurali"], r["kaynak_sayfa"])
                    for r in hier_records
                ]
            )

            con.execute(
                "CREATE TABLE layer_styles (id INTEGER PRIMARY KEY AUTOINCREMENT, f_table_catalog TEXT(256), "
                "f_table_schema TEXT(256), f_table_name TEXT(256), f_geometry_column TEXT(256), styleName TEXT(30), "
                "styleQML TEXT, styleSLD TEXT, useAsDefault BOOLEAN, description TEXT, owner TEXT(30), ui TEXT(30), "
                "update_time DATETIME DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')))"
            )
            con.execute(
                "INSERT INTO gpkg_contents(table_name, data_type, identifier) VALUES ('layer_styles', 'attributes', 'layer_styles')"
            )
            con.commit()
        finally:
            con.close()

        os.replace(staged, output)
    finally:
        if staging.exists():
            for item in staging.glob("*"):
                with contextlib.suppress(OSError):
                    item.unlink()
            with contextlib.suppress(OSError):
                staging.rmdir()

    # Katman stillerini ve form kurallarını derleyip GeoPackage içine kaydet
    codelists = schema["codelists"]
    for ft in schema["feature_types"]:
        tname = ft["name"]
        lyr = QgsVectorLayer(f"{output}|layername={tname}", tname, "ogr")
        if not lyr.isValid():
            continue
        configure_nip_layer(lyr, ft, codelists)
        apply_sld_to_layer(lyr, tname)
        with contextlib.suppress(Exception):
            lyr.saveStyleToDatabase("MPYY 1.1.7", "MPYY 1.1.7 NİP Şablon Formu", True, "")
        del lyr

    return str(output)


def get_yerel_template() -> dict:
    """PLN3113 Stüdyo yerel NİP (MpyyNipDB 1/5000) şablon tanımını döndürür."""
    with open(YEREL_TEMPLATE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_yerel_lookups() -> dict:
    """PLN3113 Stüdyo yerel NİP lookup fonksiyon verilerini döndürür."""
    with open(YEREL_LOOKUPS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


_YEREL_GEOMETRY = {
    "MULTIPOLYGON": ogr.wkbMultiPolygon,
    "Polygon": ogr.wkbPolygon,
    "MULTILINESTRING": ogr.wkbMultiLineString,
    "LINESTRING": ogr.wkbLineString,
    "POINT": ogr.wkbPoint,
    None: ogr.wkbNone,
}


def _field_defn_yerel(name: str, type_str: str) -> ogr.FieldDefn:
    name = str(name).strip()
    upper = str(type_str).upper()
    if upper.startswith("TEXT") or upper.startswith("VARCHAR"):
        width = 254
        m = re.search(r"\((\d+)\)", upper)
        if m:
            width = int(m.group(1))
        defn = ogr.FieldDefn(name, ogr.OFTString)
        defn.SetWidth(width)
        return defn
    if upper in ("INTEGER", "INT", "MEDIUMINT"):
        return ogr.FieldDefn(name, ogr.OFTInteger)
    if upper in ("REAL", "DOUBLE", "FLOAT", "NUMERIC"):
        return ogr.FieldDefn(name, ogr.OFTReal)
    if upper in ("DATETIME", "TIMESTAMP"):
        return ogr.FieldDefn(name, ogr.OFTDateTime)
    if upper == "DATE":
        return ogr.FieldDefn(name, ogr.OFTDate)
    return ogr.FieldDefn(name, ogr.OFTString)


def create_yerel_nip_workspace(output_path: str, crs="EPSG:5253") -> str:
    """PLN3113 Stüdyo Yerel / Klasik NİP GeoPackage (MpyyNipDB 1/5000) şablonunu oluşturur."""
    output = Path(output_path).resolve()
    if output.exists():
        raise FileExistsError(f"Hedef dosya zaten mevcut: {output}")
    if output.suffix.lower() != ".gpkg":
        raise ValueError("Çıktı uzantısı .gpkg olmalıdır.")

    spec = get_yerel_template()
    srs = _crs_srs(crs)
    staging = output.parent / (".nip-" + uuid.uuid4().hex)
    staging.mkdir(parents=True, exist_ok=True)
    staged = staging / "dataset.gpkg"

    try:
        source = ogr.GetDriverByName("GPKG").CreateDataSource(str(staged))
        if source is None:
            raise RuntimeError("GeoPackage oluşturulamadı.")

        for table in spec["tables"]:
            geometry = table["geometry"]
            options = ["GEOMETRY_NAME=geom", "SPATIAL_INDEX=YES", "FID=fid"] if geometry else ["FID=fid"]
            layer = source.CreateLayer(table["table"], srs if geometry else None, _YEREL_GEOMETRY.get(geometry, ogr.wkbNone), options=options)
            if layer is None:
                raise RuntimeError(f"Katman oluşturulamadı: {table['table']}")
            for field in table["fields"]:
                if layer.CreateField(_field_defn_yerel(field["name"], field["type"])) != 0:
                    raise RuntimeError(f"Alan oluşturulamadı: {table['table']}.{field['name']}")

        for table, data in get_yerel_lookups().items():
            layer = source.GetLayerByName(table)
            if layer is None:
                continue
            for row in data["rows"]:
                feature = ogr.Feature(layer.GetLayerDefn())
                for column, value in zip(data["columns"], row):
                    if value is None:
                        feature.SetFieldNull(column)
                    else:
                        feature.SetField(column, value)
                with contextlib.suppress(Exception):
                    layer.CreateFeature(feature)
        source = None

        con = sqlite3.connect(staged)
        try:
            con.execute(
                "CREATE TABLE mpyy_metadata (dataset_id TEXT PRIMARY KEY, schema_version INTEGER NOT NULL, "
                "workspace_kind TEXT NOT NULL, plan_levels TEXT NOT NULL)"
            )
            con.execute(
                "INSERT INTO mpyy_metadata VALUES (?,?,?,?)",
                (str(uuid.uuid4()), SCHEMA_VERSION, "YEREL_NIP", "NIP"),
            )
            con.execute(
                """CREATE TABLE layer_styles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, f_table_catalog TEXT(256), f_table_schema TEXT(256),
                    f_table_name TEXT(256), f_geometry_column TEXT(256), styleName TEXT(30), styleQML TEXT,
                    styleSLD TEXT, useAsDefault BOOLEAN, description TEXT, owner TEXT(30), ui TEXT(30),
                    update_time DATETIME DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')))"""
            )
            con.execute(
                "INSERT INTO gpkg_contents(table_name, data_type, identifier) VALUES ('layer_styles','attributes','layer_styles')"
            )
            for table in spec["tables"]:
                name = table["table"]
                style_info = spec.get("styles", {}).get(name)
                if not style_info:
                    continue
                qml_file = YEREL_RESOURCE_DIR / style_info["qml"]
                qml_content = qml_file.read_text(encoding="utf-8") if qml_file.exists() else ""
                con.execute(
                    "INSERT INTO layer_styles(f_table_catalog, f_table_schema, f_table_name, f_geometry_column, "
                    "styleName, styleQML, useAsDefault, description) VALUES ('', '', ?, ?, ?, ?, 1, ?)",
                    (
                        name,
                        "geom" if table["geometry"] else "",
                        name,
                        qml_content,
                        "MpyyNipDB",
                    ),
                )
            con.commit()
        finally:
            con.close()

        os.replace(staged, output)
    finally:
        if staging.exists():
            for item in staging.glob("*"):
                with contextlib.suppress(OSError):
                    item.unlink()
            with contextlib.suppress(OSError):
                staging.rmdir()

    return str(output)


def import_yerel_template_style(layer: QgsVectorLayer, template_table: str):
    """MpyyNipDB şablon katman stil ve formunu katmana uygular."""
    spec = get_yerel_template().get("styles", {}).get(template_table)
    if not spec:
        return
    qml_path = YEREL_RESOURCE_DIR / spec["qml"]
    if not qml_path.exists():
        return
    document = QDomDocument("qgis")
    document.setContent(qml_path.read_text(encoding="utf-8"))
    with contextlib.suppress(Exception):
        ok, _ = layer.importNamedStyle(document)
        if ok:
            layer.setCustomProperty("nip/form", f"MpyyNipDB: {template_table}")
            layer.setCustomProperty("nip/template", template_table)
            layer.triggerRepaint()


def bind_yerel_function_relation(project: QgsProject, referencing: QgsVectorLayer, referenced: QgsVectorLayer, field_pairs: dict, relation_id: str | None = None):
    """NİP fonksiyon açılır menüsü için QGIS proje ilişkisini (RelationReference) kurar."""
    relation_id = relation_id or get_yerel_template()["relations"][0]["id"]
    manager = project.relationManager()
    if manager.relation(relation_id).isValid():
        manager.removeRelation(relation_id)

    relation = QgsRelation()
    relation.setId(relation_id)
    relation.setName("1/5000 NİP Fonksiyon Kataloğu")
    relation.setReferencingLayer(referencing.id())
    relation.setReferencedLayer(referenced.id())
    for child, parent in field_pairs.items():
        relation.addFieldPair(child, parent)
    if relation.isValid():
        manager.addRelation(relation)

        for child in field_pairs:
            index = referencing.fields().indexFromName(child)
            if index < 0:
                continue
            setup = referencing.editorWidgetSetup(index)
            if setup.type() != "RelationReference":
                continue
            config = dict(setup.config())
            config.update(
                {
                    "Relation": relation_id,
                    "ReferencedLayerId": referenced.id(),
                    "ReferencedLayerName": referenced.name(),
                    "ReferencedLayerDataSource": referenced.source(),
                    "ReferencedLayerProviderKey": referenced.providerType(),
                }
            )
            referencing.setEditorWidgetSetup(index, QgsEditorWidgetSetup("RelationReference", config))
    return relation


def load_yerel_nip_layers(
    path: str,
    project: QgsProject | None = None,
    apply_styles: bool = True,
    setup_forms: bool = True,
    setup_relations: bool = True,
    **kwargs
) -> dict[str, QgsVectorLayer]:
    """1/5000 NİP yerel şablonundaki tüm katmanları QGIS projesine yükler ve stilleri bağlar."""
    project = project or QgsProject.instance()
    spec = get_yerel_template()
    gpkg = str(Path(path).resolve())
    root = project.layerTreeRoot()
    group = root.findGroup(YEREL_GROUP_NAME) or root.insertGroup(0, YEREL_GROUP_NAME)
    loaded = {}

    for name in spec["layer_order"]:
        layer = QgsVectorLayer(f"{gpkg}|layername={name}", name, "ogr")
        if not layer.isValid():
            continue
        if apply_styles:
            import_yerel_template_style(layer, name)
        project.addMapLayer(layer, False)
        group.addLayer(layer)
        loaded[name] = layer

    if setup_relations:
        for relation in spec.get("relations", []):
            referencing = loaded.get(relation["referencing"])
            referenced = loaded.get(relation["referenced"])
            if referencing is not None and referenced is not None:
                bind_yerel_function_relation(project, referencing, referenced, relation["pairs"], relation["id"])

    return loaded


def create_nip_workspace(output_path: str, crs="EPSG:5253", schema_type=SCHEMA_MPYY_117) -> str:
    """1/5000 NİP çizim veritabanını oluşturur (MPYY 1.1.7 veya Yerel Şablon)."""
    if str(schema_type).lower() in ("yerel_nip", "yerel", "mpyynipdb", "1", "klasik"):
        return create_yerel_nip_workspace(output_path, crs=crs)
    return create_mpyy_117_workspace(output_path, crs=crs)


def detect_nip_schema(path: str) -> str:
    """GeoPackage içindeki tablolardan şema türünü otomatik tespit eder."""
    with contextlib.suppress(Exception):
        con = sqlite3.connect(path)
        tables = [r[0] for r in con.execute("SELECT table_name FROM gpkg_contents").fetchall()]
        con.close()
        if "mpyy_detay_katalogu" in tables or "GelismeKonut" in tables:
            return SCHEMA_MPYY_117
        if "alanlar-5000" in tables:
            return SCHEMA_YEREL_NIP
    return SCHEMA_MPYY_117


def load_mpyy_117_layers(path: str, project: QgsProject | None = None, **kwargs) -> dict[str, QgsVectorLayer]:
    """MPYY 1.1.7 NİP GeoPackage katmanlarını gruplu ve stillendirilmiş olarak projeye yükler."""
    project = project or QgsProject.instance()
    gpkg = str(Path(path).resolve())
    root = project.layerTreeRoot()
    title = GROUP_NAME
    base = root.findGroup(title) or root.insertGroup(0, title)

    schema = get_nip_schema()
    codelists = schema["codelists"]
    loaded = []

    groups_def = [
        ("Alanlar (Poligonlar)", ("MultiPolygon", "Polygon")),
        ("Çizgiler (Ulaşım, Hatlar ve Sınırlar)", ("LineString", "MultiLineString")),
        ("Noktalar (Özel Tesis ve Donatılar)", ("Point", "MultiPoint")),
        ("Tablolar", (None,)),
    ]

    for group_name, geometries in groups_def:
        members = sorted(
            [t for t in schema["feature_types"] if t["geometry"] in geometries],
            key=lambda t: t["name"]
        )
        if not members:
            continue
        group = base.findGroup(group_name) or base.addGroup(group_name)
        group.setExpanded(False)
        for ft in members:
            tname = ft["name"]
            layer = QgsVectorLayer(f"{gpkg}|layername={tname}", caption(tname), "ogr")
            if not layer.isValid():
                continue
            configure_nip_layer(layer, ft, codelists)
            project.addMapLayer(layer, False)
            group.addLayer(layer)
            loaded.append(layer)

    # Ek-1e Sembol Hiyerarşisi Kataloğu
    cat_layer = QgsVectorLayer(f"{gpkg}|layername=mpyy_detay_katalogu", "Ek-1e Detay Kataloğu", "ogr")
    if cat_layer.isValid():
        cat_group = base.findGroup("Katalog") or base.addGroup("Katalog")
        cat_group.setExpanded(False)
        project.addMapLayer(cat_layer, False)
        cat_group.addLayer(cat_layer)
        loaded.append(cat_layer)

    return {lyr.name(): lyr for lyr in loaded}


def load_nip_layers(path: str, project: QgsProject | None = None, schema_type: str | None = None, **kwargs) -> dict[str, QgsVectorLayer]:
    """Seçilen veya otomatik algılanan şemaya göre katmanları projeye yükler."""
    if not schema_type:
        schema_type = detect_nip_schema(path)
    if str(schema_type).lower() in ("yerel_nip", "yerel", "mpyynipdb", "1", "klasik"):
        return load_yerel_nip_layers(path, project=project, **kwargs)
    return load_mpyy_117_layers(path, project=project, **kwargs)


# Geriye dönük uyumluluk takma adları
create_nip_drawing_workspace = create_nip_workspace
load_nip_drawing_layers = load_nip_layers
