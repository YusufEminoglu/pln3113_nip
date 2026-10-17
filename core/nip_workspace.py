# -*- coding: utf-8 -*-
"""1/5000 Nazım İmar Planı (NİP) Çizim Şablonu ve GeoPackage Üretici Motoru.

Dokuz Eylül Üniversitesi Şehir ve Bölge Planlama Bölümü PLN3113 NİP Stüdyosu için
MpyyNipDB 1/5000 standart katmanlarını (alanlar-5000, cizgiler_5000, plan onama sınırı,
fonksiyon tabloları, QML stilleri, öznitelik formları ve ilişkileri) atomik olarak üretir.
"""

import contextlib
import json
import os
import sqlite3
import uuid
from contextlib import closing
from pathlib import Path

from osgeo import gdal, ogr, osr
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsEditorWidgetSetup,
    QgsProject,
    QgsRelation,
    QgsVectorLayer,
)
from qgis.PyQt.QtXml import QDomDocument

gdal.UseExceptions()

TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "resources" / "yerel_nip"
GROUP_NAME = "PLN3113 1/5000 NİP Çizim Katmanları"
STYLE_NAME = "PLN3113 MpyyNipDB Çizim Şablonu"
SCHEMA_VERSION = 1
KIND = "PLN3113_YEREL_NIP"

_GEOMETRY = {
    "MULTIPOLYGON": ogr.wkbMultiPolygon,
    "MULTILINESTRING": ogr.wkbMultiLineString,
    "LINESTRING": ogr.wkbLineString,
    "POINT": ogr.wkbPoint,
    None: ogr.wkbNone,
}


def get_template():
    return json.loads((TEMPLATE_DIR / "template.json").read_text(encoding="utf-8"))


def get_lookups():
    return json.loads((TEMPLATE_DIR / "lookups.json").read_text(encoding="utf-8"))


def _field_defn(name, declared):
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


def _crs_srs(value):
    crs = value if isinstance(value, QgsCoordinateReferenceSystem) else QgsCoordinateReferenceSystem(str(value))
    if not crs.isValid():
        crs = QgsCoordinateReferenceSystem("EPSG:5253")
    srs = osr.SpatialReference()
    if srs.SetFromUserInput(crs.authid() or crs.toWkt()) != 0:
        raise ValueError("GDAL seçilen KRS'yi okuyamıyor")
    return srs


def create_nip_workspace(output_path, crs="EPSG:5253"):
    """MpyyNipDB 1/5000 şablonuyla hazır NİP GeoPackage oluşturur."""
    output = Path(output_path).resolve()
    if output.exists():
        raise FileExistsError(f"Hedef dosya zaten mevcut: {output}")
    if output.suffix.lower() != ".gpkg":
        raise ValueError("Çıktı uzantısı .gpkg olmalıdır.")

    spec = get_template()
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
            layer = source.CreateLayer(table["table"], srs if geometry else None, _GEOMETRY[geometry], options=options)
            if layer is None:
                raise RuntimeError(f"Katman oluşturulamadı: {table['table']}")
            for field in table["fields"]:
                if layer.CreateField(_field_defn(field["name"], field["type"])) != 0:
                    raise RuntimeError(f"Alan oluşturulamadı: {table['table']}.{field['name']}")

        for table, data in get_lookups().items():
            layer = source.GetLayerByName(table)
            if layer is None:
                raise RuntimeError(f"Lookup tablosu bulunamadı: {table}")
            for row in data["rows"]:
                feature = ogr.Feature(layer.GetLayerDefn())
                for column, value in zip(data["columns"], row):
                    if value is None:
                        feature.SetFieldNull(column)
                    else:
                        feature.SetField(column, value)
                if layer.CreateFeature(feature) != 0:
                    raise RuntimeError(f"Satır yazılamadı: {table}")
        source = None

        with closing(sqlite3.connect(staged)) as con, con:
            con.execute(
                "CREATE TABLE mpyy_metadata (dataset_id TEXT PRIMARY KEY, schema_version INTEGER NOT NULL, "
                "workspace_kind TEXT NOT NULL, plan_levels TEXT NOT NULL)"
            )
            con.execute(
                "INSERT INTO mpyy_metadata VALUES (?,?,?,?)",
                (str(uuid.uuid4()), SCHEMA_VERSION, KIND, "NIP"),
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
                qml_file = TEMPLATE_DIR / spec["styles"][name]["qml"]
                qml_content = qml_file.read_text(encoding="utf-8") if qml_file.exists() else ""
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


def import_template_style(layer, template_table):
    """MpyyNipDB şablon katman stil ve formunu katmana uygular."""
    spec = get_template()["styles"].get(template_table)
    if not spec:
        return
    qml_path = TEMPLATE_DIR / spec["qml"]
    if not qml_path.exists():
        return
    document = QDomDocument("qgis")
    document.setContent(qml_path.read_text(encoding="utf-8"))
    ok, message = layer.importNamedStyle(document)
    if not ok:
        raise RuntimeError(f"{layer.name()} stili uygulanamadı: {message}")
    layer.setCustomProperty("nip/form", f"{STYLE_NAME}: {template_table}")
    layer.setCustomProperty("nip/template", template_table)
    layer.triggerRepaint()


def bind_function_relation(project, referencing, referenced, field_pairs, relation_id=None):
    """NİP fonksiyon açılır menüsü için QGIS proje ilişkisini (RelationReference) kurar."""
    relation_id = relation_id or get_template()["relations"][0]["id"]
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
    if not relation.isValid():
        raise RuntimeError(f"NİP fonksiyon ilişkisi kurulamadı: {relation.validationError()}")

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


def load_nip_workspace_layers(
    path,
    iface=None,
    project=None,
    apply_styles=True,
    setup_forms=True,
    setup_relations=True
):
    """1/5000 NİP şablonundaki tüm katmanları QGIS projesine yükler ve stilleri bağlar."""
    project = project or QgsProject.instance()
    spec = get_template()
    gpkg = str(Path(path).resolve())
    root = project.layerTreeRoot()
    group = root.findGroup(GROUP_NAME) or root.insertGroup(0, GROUP_NAME)
    loaded = {}

    for name in spec["layer_order"]:
        layer = QgsVectorLayer(f"{gpkg}|layername={name}", name, "ogr")
        if not layer.isValid():
            raise RuntimeError(f"Katman açılamadı: {name}")
        if apply_styles:
            import_template_style(layer, name)
        project.addMapLayer(layer, False)
        group.addLayer(layer)
        loaded[name] = layer

    if setup_relations:
        for relation in spec.get("relations", []):
            referencing = loaded.get(relation["referencing"])
            referenced = loaded.get(relation["referenced"])
            if referencing is not None and referenced is not None:
                bind_function_relation(project, referencing, referenced, relation["pairs"], relation["id"])

    return loaded


# Uyumluluk Takma Adları (Aliases)
create_nip_drawing_workspace = create_nip_workspace
load_nip_drawing_layers = load_nip_workspace_layers

