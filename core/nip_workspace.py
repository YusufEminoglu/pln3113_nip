# -*- coding: utf-8 -*-
"""1/5000 Nazım İmar Planı (NİP) Çizim Veritabanı ve Şablon Motoru.

DEÜ Mimarlık Fakültesi Şehir ve Bölge Planlama Bölümü
PLN3113 Şehir Planlama Projesi III - Tire Stüdyosu
"""
from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import uuid
from contextlib import closing
from pathlib import Path

from osgeo import ogr, osr
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsEditorWidgetSetup,
    QgsProject,
    QgsRelation,
    QgsVectorLayer
)
from qgis.PyQt.QtXml import QDomDocument

TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "forms" / "yerel_nip"
GROUP_NAME = "1/5000 Nazım İmar Planı Çizim Katmanları"
STYLE_NAME = "PLN3113 1/5000 NİP Çizim Şablonu"

_GEOMETRY = {
    "MULTIPOLYGON": ogr.wkbMultiPolygon,
    "MULTILINESTRING": ogr.wkbMultiLineString,
    "LINESTRING": ogr.wkbLineString,
    "POINT": ogr.wkbPoint,
    None: ogr.wkbNone,
}


def get_template_spec() -> dict:
    """NİP şablon tablo ve katman spesifikasyonunu döndürür."""
    return json.loads((TEMPLATE_DIR / "template.json").read_text(encoding="utf-8"))


def get_lookups_data() -> dict:
    """NİP fonksiyon ve tabaka eşleştirme verilerini döndürür."""
    return json.loads((TEMPLATE_DIR / "lookups.json").read_text(encoding="utf-8"))


def _field_defn(name: str, declared: str) -> ogr.FieldDefn:
    declared = declared.upper()
    width = 0
    if "(" in declared:
        declared, width = declared.split("(", 1)
        width = int(width.rstrip(")"))
    kind = {
        "TEXT": ogr.OFTString,
        "INTEGER": ogr.OFTInteger64,
        "MEDIUMINT": ogr.OFTInteger,
        "REAL": ogr.OFTReal,
        "DATETIME": ogr.OFTDateTime,
    }[declared]
    defn = ogr.FieldDefn(name, kind)
    if width:
        defn.SetWidth(width)
    return defn


def _to_srs(crs: QgsCoordinateReferenceSystem) -> osr.SpatialReference:
    if not crs or not crs.isValid():
        crs = QgsCoordinateReferenceSystem("EPSG:5637")
    srs = osr.SpatialReference()
    auth = crs.authid()
    if auth and srs.SetFromUserInput(auth) == 0:
        return srs
    srs.ImportFromWkt(crs.toWkt())
    return srs


def create_nip_drawing_workspace(output_path: str, crs: QgsCoordinateReferenceSystem = None) -> str:
    """MpyyNipDB 1/5000 NİP çizim şablonu yapısında GeoPackage veritabanı üretir."""
    output = Path(output_path).resolve()
    if output.exists():
        raise FileExistsError(f"Hedef dosya zaten mevcut: {output}")
    if output.suffix.lower() != ".gpkg":
        output = output.with_suffix(".gpkg")

    spec = get_template_spec()
    if isinstance(crs, str):
        crs_obj = QgsCoordinateReferenceSystem(crs)
    elif isinstance(crs, QgsCoordinateReferenceSystem) and crs.isValid():
        crs_obj = crs
    else:
        crs_obj = QgsCoordinateReferenceSystem("EPSG:5637")
    srs = _to_srs(crs_obj)
    staging = output.parent / (".nip-" + uuid.uuid4().hex)
    staging.mkdir(parents=True, exist_ok=True)
    staged = staging / "dataset.gpkg"

    try:
        source = ogr.GetDriverByName("GPKG").CreateDataSource(str(staged))
        if source is None:
            raise RuntimeError("GeoPackage veri kaynağı oluşturulamadı.")

        for table in spec["tables"]:
            geometry = table["geometry"]
            options = ["GEOMETRY_NAME=geom", "SPATIAL_INDEX=YES", "FID=fid"] if geometry else ["FID=fid"]
            layer = source.CreateLayer(table["table"], srs if geometry else None, _GEOMETRY[geometry], options=options)
            if layer is None:
                raise RuntimeError(f"Katman oluşturulamadı: {table['table']}")
            for field in table["fields"]:
                if layer.CreateField(_field_defn(field["name"], field["type"])) != 0:
                    raise RuntimeError(f"Alan oluşturulamadı: {table['table']}.{field['name']}")

        lookups = get_lookups_data()
        for table, data in lookups.items():
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
                if layer.CreateFeature(feature) != 0:
                    raise RuntimeError(f"Lookup satırı yazılamadı: {table}")
        source = None

        with closing(sqlite3.connect(staged)) as con, con:
            con.execute(
                "CREATE TABLE IF NOT EXISTS layer_styles ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, f_table_catalog TEXT(256), f_table_schema TEXT(256), "
                "f_table_name TEXT(256), f_geometry_column TEXT(256), styleName TEXT(30), styleQML TEXT, "
                "styleSLD TEXT, useAsDefault BOOLEAN, description TEXT, owner TEXT(30), ui TEXT(30), "
                "update_time DATETIME DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')))"
            )
            con.execute(
                "INSERT INTO gpkg_contents(table_name, data_type, identifier) "
                "VALUES ('layer_styles','attributes','layer_styles')"
            )
            for table in spec["tables"]:
                name = table["table"]
                style_file = spec.get("styles", {}).get(name, {}).get("qml")
                if style_file and (TEMPLATE_DIR / style_file).exists():
                    qml_content = (TEMPLATE_DIR / style_file).read_text(encoding="utf-8")
                    con.execute(
                        "INSERT INTO layer_styles(f_table_catalog, f_table_schema, f_table_name, f_geometry_column, "
                        "styleName, styleQML, useAsDefault, description) VALUES ('', '', ?, ?, ?, ?, 1, ?)",
                        (
                            name,
                            "geom" if table["geometry"] else "",
                            name,
                            qml_content,
                            STYLE_NAME,
                        ),
                    )
            integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                raise RuntimeError(f"Veritabanı bütünlüğü doğrulanamadı: {integrity}")

        os.replace(staged, output)
    finally:
        for item in staging.glob("*"):
            with contextlib.suppress(OSError):
                item.unlink()
        with contextlib.suppress(OSError):
            staging.rmdir()

    return str(output)


def bind_function_relation(project: QgsProject, referencing: QgsVectorLayer, referenced: QgsVectorLayer, field_pairs: list, relation_id: str):
    """QGIS Nitelik Formu için fonksiyon ilişki bağlamasını yapar."""
    manager = project.relationManager()
    existing = manager.relation(relation_id)
    if existing.isValid():
        manager.removeRelation(relation_id)
    relation = QgsRelation()
    relation.setId(relation_id)
    relation.setName(relation_id)
    relation.setReferencingLayer(referencing.id())
    relation.setReferencedLayer(referenced.id())
    for child in field_pairs:
        relation.addFieldPair(child, child)
    manager.addRelation(relation)
    for child in field_pairs:
        index = referencing.fields().indexFromName(child)
        if index != -1:
            setup = referencing.editorWidgetSetup(index)
            if setup.type() == "RelationReference":
                config = dict(setup.config())
                config.update({
                    "Relation": relation_id,
                    "ReferencedLayerId": referenced.id(),
                    "ReferencedLayerName": referenced.name(),
                    "ReferencedLayerDataSource": referenced.source(),
                    "ReferencedLayerProviderKey": referenced.providerType(),
                })
                referencing.setEditorWidgetSetup(index, QgsEditorWidgetSetup("RelationReference", config))
    return relation


def load_nip_drawing_layers(path: str, project: QgsProject = None) -> list[QgsVectorLayer]:
    """1/5000 NİP şablon katmanlarını QGIS projesine yükler, stillerini ve formlarını bağlar."""
    project = project or QgsProject.instance()
    spec = get_template_spec()
    gpkg = str(Path(path).resolve())
    root = project.layerTreeRoot()
    group = root.findGroup(GROUP_NAME) or root.insertGroup(0, GROUP_NAME)
    loaded = {}

    for name in spec.get("layer_order", []):
        layer = QgsVectorLayer(f"{gpkg}|layername={name}", name, "ogr")
        if not layer.isValid():
            continue
        style_file = spec.get("styles", {}).get(name, {}).get("qml")
        if style_file and (TEMPLATE_DIR / style_file).exists():
            doc = QDomDocument("qgis")
            doc.setContent((TEMPLATE_DIR / style_file).read_text(encoding="utf-8"))
            layer.importNamedStyle(doc)
            layer.triggerRepaint()
        project.addMapLayer(layer, False)
        group.addLayer(layer)
        loaded[name] = layer

    for rel in spec.get("relations", []):
        ref_ing = loaded.get(rel.get("referencing"))
        ref_ed = loaded.get(rel.get("referenced"))
        if ref_ing and ref_ed:
            bind_function_relation(project, ref_ing, ref_ed, rel.get("pairs", []), rel.get("id"))

    return list(loaded.values())
