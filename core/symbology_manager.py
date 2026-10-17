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


def style_space_syntax(layer: QgsVectorLayer, field_name: str = "NACH_R800") -> None:
    """Space syntax NAIN / NACH metriklerini spektral renk skalasıyla kademelendirir."""
    if not layer or not layer.isValid():
        return
    fields = [f.name() for f in layer.fields()]
    if field_name not in fields:
        field_name = next((f for f in fields if "NACH" in f or "NAIN" in f), None)
    if not field_name:
        return
    ranges = [
        QgsRendererRange(0.0, 0.40, QgsLineSymbol.createSimple({"line_color": "#3b82f6", "line_width": "0.30"}), "Düşük (Arka Plan Ağı)"),
        QgsRendererRange(0.40, 0.70, QgsLineSymbol.createSimple({"line_color": "#10b981", "line_width": "0.45"}), "Orta-Düşük Akış"),
        QgsRendererRange(0.70, 1.00, QgsLineSymbol.createSimple({"line_color": "#f59e0b", "line_width": "0.65"}), "Orta-Yüksek Akış"),
        QgsRendererRange(1.00, 1.30, QgsLineSymbol.createSimple({"line_color": "#f97316", "line_width": "0.85"}), "Yüksek (Ön Plan Koridoru)"),
        QgsRendererRange(1.30, 999.0, QgsLineSymbol.createSimple({"line_color": "#dc2626", "line_width": "1.10"}), "Kritik Transit Omurga"),
    ]
    layer.setRenderer(QgsGraduatedSymbolRenderer(field_name, ranges))
    layer.triggerRepaint()


def style_detour_barrier(layer: QgsVectorLayer) -> None:
    """Detour ratio > 1.35 olan bariyerli arzu hatlarını vurgular."""
    if not layer or not layer.isValid():
        return
    categories = [
        QgsRendererCategory(
            "1",
            QgsLineSymbol.createSimple({"line_color": "#dc2626", "line_width": "0.75", "line_style": "dash"}),
            "Bariyerli Hat (Detour > 1.35)"
        ),
        QgsRendererCategory(
            "0",
            QgsLineSymbol.createSimple({"line_color": "#10b981", "line_width": "0.35", "line_style": "solid"}),
            "Doğrudan Erişim (Detour <= 1.35)"
        ),
    ]
    layer.setRenderer(QgsCategorizedSymbolRenderer("is_barrier", categories))
    layer.triggerRepaint()


def style_isochrone_bands(layer: QgsVectorLayer) -> None:
    """5 dk (400m), 10 dk (800m), 15 dk (1200m) yürüme izokron poligonlarını kademelendirir."""
    if not layer or not layer.isValid():
        return
    sym_400 = QgsFillSymbol.createSimple({"color": "#10b981", "outline_color": "#047857", "outline_width": "0.4"})
    sym_400.setOpacity(0.40)
    sym_800 = QgsFillSymbol.createSimple({"color": "#f59e0b", "outline_color": "#b45309", "outline_width": "0.4"})
    sym_800.setOpacity(0.35)
    sym_1200 = QgsFillSymbol.createSimple({"color": "#f97316", "outline_color": "#c2410c", "outline_width": "0.4"})
    sym_1200.setOpacity(0.30)

    categories = [
        QgsRendererCategory("400", sym_400, "5 dk (400 m) - Yürüme Çekirdeği"),
        QgsRendererCategory("800", sym_800, "10 dk (800 m) - Standart Yürüme"),
        QgsRendererCategory("1200", sym_1200, "15 dk (1200 m) - Kentsel Çeper"),
    ]
    layer.setRenderer(QgsCategorizedSymbolRenderer("mesafe_m", categories))
    layer.triggerRepaint()


def style_facility_adequacy_points(layer: QgsVectorLayer) -> None:
    """2SFCA donatı durumunu (Yeterli, Aşırı Yüklü, Kullanılmayan) renklendirir."""
    if not layer or not layer.isValid():
        return
    categories = [
        QgsRendererCategory("Yeterli (Adequate)", QgsMarkerSymbol.createSimple({"color": "#16a34a", "outline_color": "#ffffff", "size": "3.5"}), "Yeterli Kapasite"),
        QgsRendererCategory("Aşırı Yüklü (Overloaded)", QgsMarkerSymbol.createSimple({"color": "#dc2626", "outline_color": "#ffffff", "size": "4.5"}), "Aşırı Yüklü (Kapasite Yetersiz)"),
        QgsRendererCategory("Kullanılmayan (Unused)", QgsMarkerSymbol.createSimple({"color": "#64748b", "outline_color": "#ffffff", "size": "3.0"}), "Atıl / Kullanılmayan"),
    ]
    layer.setRenderer(QgsCategorizedSymbolRenderer("durum", categories))
    layer.triggerRepaint()


def style_fca_demand_points(layer: QgsVectorLayer) -> None:
    """2SFCA talep noktalarının hizmet alma durumunu (Kapsandı / Kapsanmadı) renklendirir."""
    if not layer or not layer.isValid():
        return
    categories = [
        QgsRendererCategory(
            "1",
            QgsMarkerSymbol.createSimple({"color": "#10b981", "outline_color": "#ffffff", "size": "2.8"}),
            "Hizmet Alan Nüfus (Kapsandı)"
        ),
        QgsRendererCategory(
            "0",
            QgsMarkerSymbol.createSimple({"color": "#ef4444", "outline_color": "#ffffff", "size": "3.2"}),
            "Hizmet Alamayan Nüfus (Kapsanamadı)"
        ),
    ]
    layer.setRenderer(QgsCategorizedSymbolRenderer("kapsandi", categories))
    layer.triggerRepaint()



def style_scenario_diff_network(layer: QgsVectorLayer) -> None:
    """A/B senaryo fark hatlarını 4 plan karar başlığına göre stillendirir."""
    if not layer or not layer.isValid():
        return
    categories = [
        QgsRendererCategory(
            "Ulaşım Kademelenmesi Revizyonu",
            QgsLineSymbol.createSimple({"line_color": "#dc2626", "line_width": "0.90"}),
            "Kademelenme Revizyonu (Yük Artışı)"
        ),
        QgsRendererCategory(
            "Yayalaştırma / Trafik Sakinleştirme",
            QgsLineSymbol.createSimple({"line_color": "#0d9488", "line_width": "0.75"}),
            "Trafik Sakinleştirme / Yayalaştırma"
        ),
        QgsRendererCategory(
            "Stratejik Yeni Bağlantı Aksı",
            QgsLineSymbol.createSimple({"line_color": "#2563eb", "line_width": "0.80"}),
            "Meri Plan Yeni Aksı (Stratejik)"
        ),
        QgsRendererCategory(
            "İşlemeyen Öneri Yol (Kademelenme Revizyonu)",
            QgsLineSymbol.createSimple({"line_color": "#f59e0b", "line_width": "0.60", "line_style": "dot"}),
            "İşlemeyen Öneri Aks"
        ),
        QgsRendererCategory(
            "Mevcut Karakter Korunacak",
            QgsLineSymbol.createSimple({"line_color": "#94a3b8", "line_width": "0.40"}),
            "Kararlı Mevcut Aks"
        ),
        QgsRendererCategory(
            "Yayalaştırma / Yol Kapatma",
            QgsLineSymbol.createSimple({"line_color": "#64748b", "line_width": "0.50", "line_style": "dash"}),
            "Kapanan / Değişen Mevcut Aks"
        ),
    ]
    layer.setRenderer(QgsCategorizedSymbolRenderer("plan_karar_grubu", categories))
    layer.triggerRepaint()


class SymbologyManager:
    """Kartografik stil yöneticisi sınıfı."""
    apply_mpyy_qml_style = staticmethod(apply_mpyy_qml_style)
    apply_road_platform_symbology = staticmethod(style_road_platform)
    apply_junction_trim_symbology = staticmethod(style_road_junctions)
    apply_road_polygons_symbology = staticmethod(style_road_polygons)
    apply_front_facade_symbology = staticmethod(style_front_facade)
    apply_accessibility_symbology = staticmethod(style_service_area)
    apply_od_routes_symbology = staticmethod(lambda routes, desire: style_od_and_centrality(routes_layer=routes, desire_layer=desire))
    apply_centrality_symbology = staticmethod(lambda centrality: style_od_and_centrality(centrality_layer=centrality))
    apply_slope_symbology = staticmethod(lambda slope: style_od_and_centrality(slope_layer=slope))
    apply_validity_error_points = staticmethod(style_validity_error_points)
    apply_space_syntax_symbology = staticmethod(style_space_syntax)
    apply_detour_barrier_symbology = staticmethod(style_detour_barrier)
    apply_isochrone_bands_symbology = staticmethod(style_isochrone_bands)
    apply_facility_adequacy_symbology = staticmethod(style_facility_adequacy_points)
    apply_scenario_diff_symbology = staticmethod(style_scenario_diff_network)


