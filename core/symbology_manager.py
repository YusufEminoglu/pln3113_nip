# -*- coding: utf-8 -*-
"""PLN3113 Otomatik Kartografik ve Tematik Stil Yöneticisi (Symbology Manager).

DEÜ Mimarlık Fakültesi Şehir ve Bölge Planlama Bölümü
PLN3113 - Tire NİP Analiz Stüdyosu

Bu modül, NİP analiz çıktılarının (Yol platformu, kavşaklar, ön cephe bağlantıları,
erişim havzaları, OD matrisi, merkezilik, eğim ve MPYY fonksiyonları) harita tuvaline
yüklendiği anda resmî kartografik standartlarda otomatik stillendirilmesini sağlar.
"""
from __future__ import annotations

import os
from pathlib import Path
from qgis.core import (
    QgsCategorizedSymbolRenderer,
    QgsFillSymbol,
    QgsGraduatedSymbolRenderer,
    QgsLineSymbol,
    QgsMarkerSymbol,
    QgsRendererCategory,
    QgsRendererRange,
    QgsSimpleFillSymbolLayer,
    QgsSimpleLineSymbolLayer,
    QgsSimpleMarkerSymbolLayer,
    QgsVectorLayer
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtXml import QDomDocument

TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "resources" / "yerel_nip"


def apply_mpyy_qml_style(layer: QgsVectorLayer, qml_filename: str = "alanlar-5000.qml") -> bool:
    """Katmanda resmî MPYY QML stil dosyasını yükler."""
    if not layer or not layer.isValid():
        return False
    qml_path = TEMPLATE_DIR / qml_filename
    if not qml_path.exists():
        return False
    doc = QDomDocument("qgis")
    doc.setContent(qml_path.read_text(encoding="utf-8"))
    ok, _ = layer.importNamedStyle(doc)
    if ok:
        layer.triggerRepaint()
    return ok


def style_road_platform(layer: QgsVectorLayer) -> None:
    """Yol platform katmanını tip özniteliğine göre kademeli stillendirir."""
    if not layer or not layer.isValid():
        return

    categories = [
        QgsRendererCategory(
            "yol_siniri",
            QgsLineSymbol.createSimple({
                "line_color": "#1e293b",
                "line_width": "0.45",
                "line_style": "solid"
            }),
            "Yol Dış Sınırı (Kırmızı Çizgi)"
        ),
        QgsRendererCategory(
            "kaldirim_bordur",
            QgsLineSymbol.createSimple({
                "line_color": "#64748b",
                "line_width": "0.30",
                "line_style": "dash"
            }),
            "Kaldırım Bordür Hattı"
        ),
        QgsRendererCategory(
            "refuj",
            QgsLineSymbol.createSimple({
                "line_color": "#059669",
                "line_width": "0.40",
                "line_style": "solid"
            }),
            "Orta Refüj Sınırı"
        ),
        QgsRendererCategory(
            "center",
            QgsLineSymbol.createSimple({
                "line_color": "#f59e0b",
                "line_width": "0.35",
                "line_style": "dash dot"
            }),
            "Yol Orta Aks Çizgisi"
        ),
    ]

    default_sym = QgsLineSymbol.createSimple({"line_color": "#94a3b8", "line_width": "0.25"})
    renderer = QgsCategorizedSymbolRenderer("type", categories)
    renderer.setSourceSymbol(default_sym)
    layer.setRenderer(renderer)
    layer.triggerRepaint()


def style_road_junctions(layer: QgsVectorLayer) -> None:
    """Kavşak kırpma çıktı katmanını stillendirir."""
    if not layer or not layer.isValid():
        return

    categories = [
        QgsRendererCategory(
            "center",
            QgsLineSymbol.createSimple({
                "line_color": "#f59e0b",
                "line_width": "0.35",
                "line_style": "dash dot"
            }),
            "Aks Çizgisi (Merkez)"
        ),
        QgsRendererCategory(
            "trimmed",
            QgsLineSymbol.createSimple({
                "line_color": "#334155",
                "line_width": "0.45",
                "line_style": "solid"
            }),
            "Kavşak Giriş/Çıkış Hatları"
        ),
    ]

    default_sym = QgsLineSymbol.createSimple({"line_color": "#334155", "line_width": "0.40"})
    renderer = QgsCategorizedSymbolRenderer("type_link", categories)
    renderer.setSourceSymbol(default_sym)
    layer.setRenderer(renderer)
    layer.triggerRepaint()


def style_road_polygons(layer: QgsVectorLayer) -> None:
    """Poligonlaşan yol yüzeylerini yol asfaltı/kaplama tonuyla stillendirir."""
    if not layer or not layer.isValid():
        return

    symbol = QgsFillSymbol.createSimple({
        "color": "#e2e8f0",
        "outline_color": "#64748b",
        "outline_width": "0.35"
    })
    symbol.setOpacity(0.85)
    layer.setRenderer(QgsCategorizedSymbolRenderer("", []))
    from qgis.core import QgsSingleSymbolRenderer
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    layer.triggerRepaint()


def style_front_facade(lines_layer: QgsVectorLayer = None, points_layer: QgsVectorLayer = None) -> None:
    """Ön cephe servis mesafesi hatları ve servis noktalarını stillendirir."""
    if lines_layer and lines_layer.isValid():
        line_sym = QgsLineSymbol.createSimple({
            "line_color": "#8b5cf6",
            "line_width": "0.45",
            "line_style": "dash"
        })
        from qgis.core import QgsSingleSymbolRenderer
        lines_layer.setRenderer(QgsSingleSymbolRenderer(line_sym))
        lines_layer.triggerRepaint()

    if points_layer and points_layer.isValid():
        pt_sym = QgsMarkerSymbol.createSimple({
            "name": "circle",
            "color": "#06b6d4",
            "outline_color": "#ffffff",
            "outline_width": "0.6",
            "size": "3.2"
        })
        from qgis.core import QgsSingleSymbolRenderer
        points_layer.setRenderer(QgsSingleSymbolRenderer(pt_sym))
        points_layer.triggerRepaint()


def style_service_area(roads_layer: QgsVectorLayer = None, polygons_layer: QgsVectorLayer = None, buffer_layer: QgsVectorLayer = None) -> None:
    """Erişilebilirlik servis yolları, erişim poligonu ve MPYY tamponunu stillendirir."""
    from qgis.core import QgsSingleSymbolRenderer

    if roads_layer and roads_layer.isValid():
        r_sym = QgsLineSymbol.createSimple({
            "line_color": "#10b981",
            "line_width": "0.60",
            "line_style": "solid"
        })
        roads_layer.setRenderer(QgsSingleSymbolRenderer(r_sym))
        roads_layer.triggerRepaint()

    if polygons_layer and polygons_layer.isValid():
        poly_sym = QgsFillSymbol.createSimple({
            "color": "#10b981",
            "outline_color": "#047857",
            "outline_width": "0.50"
        })
        poly_sym.setOpacity(0.35)
        polygons_layer.setRenderer(QgsSingleSymbolRenderer(poly_sym))
        polygons_layer.triggerRepaint()

    if buffer_layer and buffer_layer.isValid():
        buf_sym = QgsFillSymbol.createSimple({
            "color": "transparent",
            "outline_color": "#2563eb",
            "outline_width": "0.55",
            "outline_style": "dash"
        })
        buffer_layer.setRenderer(QgsSingleSymbolRenderer(buf_sym))
        buffer_layer.triggerRepaint()


def style_od_and_centrality(
    routes_layer: QgsVectorLayer = None,
    desire_layer: QgsVectorLayer = None,
    centrality_layer: QgsVectorLayer = None,
    slope_layer: QgsVectorLayer = None
) -> None:
    """OD rotaları, kuş uçuşu arzu hatları, ağ merkezilikleri ve yol eğimlerini stillendirir."""
    from qgis.core import QgsSingleSymbolRenderer

    if routes_layer and routes_layer.isValid():
        rt_sym = QgsLineSymbol.createSimple({
            "line_color": "#2563eb",
            "line_width": "0.65",
            "line_style": "solid"
        })
        routes_layer.setRenderer(QgsSingleSymbolRenderer(rt_sym))
        routes_layer.triggerRepaint()

    if desire_layer and desire_layer.isValid():
        des_sym = QgsLineSymbol.createSimple({
            "line_color": "#f97316",
            "line_width": "0.35",
            "line_style": "dash"
        })
        des_sym.setOpacity(0.65)
        desire_layer.setRenderer(QgsSingleSymbolRenderer(des_sym))
        desire_layer.triggerRepaint()

    if centrality_layer and centrality_layer.isValid():
        # Betweenness Merkezilik Kademelendirmesi
        field_name = "betweenness" if "betweenness" in [f.name() for f in centrality_layer.fields()] else "betw_std"
        ranges = [
            QgsRendererRange(0.0, 0.05, QgsLineSymbol.createSimple({"line_color": "#94a3b8", "line_width": "0.25"}), "Çok Düşük Aradalık"),
            QgsRendererRange(0.05, 0.15, QgsLineSymbol.createSimple({"line_color": "#38bdf8", "line_width": "0.35"}), "Düşük Aradalık"),
            QgsRendererRange(0.15, 0.35, QgsLineSymbol.createSimple({"line_color": "#eab308", "line_width": "0.50"}), "Orta Aradalık"),
            QgsRendererRange(0.35, 0.65, QgsLineSymbol.createSimple({"line_color": "#f97316", "line_width": "0.70"}), "Yüksek Aradalık"),
            QgsRendererRange(0.65, 1.0, QgsLineSymbol.createSimple({"line_color": "#dc2626", "line_width": "0.90"}), "Omurga / Kritik Koridor"),
        ]
        renderer = QgsGraduatedSymbolRenderer(field_name, ranges)
        centrality_layer.setRenderer(renderer)
        centrality_layer.triggerRepaint()

    if slope_layer and slope_layer.isValid():
        # Yol Eğimi Kademelendirmesi
        field_name = "slope_pct" if "slope_pct" in [f.name() for f in slope_layer.fields()] else "egim_yuzde"
        ranges = [
            QgsRendererRange(0.0, 5.0, QgsLineSymbol.createSimple({"line_color": "#16a34a", "line_width": "0.50"}), "Düz / Düşük Eğim (< %5)"),
            QgsRendererRange(5.0, 10.0, QgsLineSymbol.createSimple({"line_color": "#eab308", "line_width": "0.55"}), "Orta Eğim (%5 - %10)"),
            QgsRendererRange(10.0, 15.0, QgsLineSymbol.createSimple({"line_color": "#ea580c", "line_width": "0.65"}), "Yüksek Eğim (%10 - %15)"),
            QgsRendererRange(15.0, 100.0, QgsLineSymbol.createSimple({"line_color": "#dc2626", "line_width": "0.85"}), "Kritik / Dik Eğim (> %15)"),
        ]
        renderer = QgsGraduatedSymbolRenderer(field_name, ranges)
        slope_layer.setRenderer(renderer)
        slope_layer.triggerRepaint()


def style_validity_error_points(layer: QgsVectorLayer) -> None:
    """Geometri geçerlilik ve topoloji hata noktalarını belirgin kırmızı ikonla stillendirir."""
    if not layer or not layer.isValid():
        return
    from qgis.core import QgsSingleSymbolRenderer
    sym = QgsMarkerSymbol.createSimple({
        "name": "cross2",
        "color": "#dc2626",
        "outline_color": "#991b1b",
        "outline_width": "0.8",
        "size": "4.0"
    })
    layer.setRenderer(QgsSingleSymbolRenderer(sym))
    layer.triggerRepaint()
