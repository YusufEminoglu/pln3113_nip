# -*- coding: utf-8 -*-
"""PlanX algoritmaları için ortak temel sınıf ve geometri/graf yardımcıları.

PLN3113 NİP Analiz Stüdyosu - PlanX Motoru Tabanı
"""
from __future__ import annotations

import os
import numpy as np

from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.PyQt.QtGui import QColor, QIcon
from qgis.core import (
    QgsCoordinateTransform,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsGraduatedSymbolRenderer,
    QgsRendererRange,
    QgsSymbol,
)

from . import graphs

DOUBLE = QVariant.Type.Double if hasattr(QVariant, 'Type') else QVariant.Double
INT = QVariant.Type.Int if hasattr(QVariant, 'Type') else QVariant.Int
LONG = QVariant.Type.LongLong if hasattr(QVariant, 'Type') else QVariant.LongLong
STRING = QVariant.Type.String if hasattr(QVariant, 'Type') else QVariant.String

GROUP_NETWORK = "05. Ulaşım ve Network Analizleri"
GROUP_STANDARDS = "04. NİP Nüfus, Donatı ve DOP Analizi"
GROUP_REPORT = "06. Plan Raporlama ve Senaryo Analizleri"



class PlanXBaseAlgorithm(QgsProcessingAlgorithm):
    """PlanX temelli algoritmalar için ortak temel sınıf."""

    GROUP = "05. Ulaşım ve Network Analizleri"
    GROUP_ID = "05_ulasim_network_analizleri"
    ICON = "icon.png"

    def tr(self, text: str) -> str:
        return QCoreApplication.translate(self.__class__.__name__, text)

    def group(self) -> str:
        return self.GROUP

    def groupId(self) -> str:
        return self.GROUP_ID

    def icon(self) -> QIcon:
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        icon_path = os.path.join(base_dir, "icons", self.ICON)
        if os.path.exists(icon_path):
            return QIcon(icon_path)
        icon_path = os.path.join(base_dir, "icons", "icon.png")
        return QIcon(icon_path) if os.path.exists(icon_path) else super().icon()

    @staticmethod
    def require_projected(source, name: str):
        crs = source.sourceCrs()
        if crs.isValid() and crs.isGeographic():
            raise QgsProcessingException(
                f"'{name}' coğrafi koordinat sistemi ({crs.authid()}) kullanıyor. "
                "PlanX ağ ve merkezilik analizleri metrik koordinatlar gerektirir. "
                "Lütfen katmanı projeksiyonlu bir koordinat sistemine (örn: EPSG:5253 TUREF / TM27) dönüştürün."
            )

    @staticmethod
    def source_polylines(source, feedback=None, min_length: float = 1e-6,
                         target_crs=None, transform_context=None):
        """Çizgi katmanını tek parçalı (k, 2) koordinat dizilerine ayırır."""
        xform = None
        if target_crs is not None and source.sourceCrs() != target_crs:
            xform = QgsCoordinateTransform(source.sourceCrs(), target_crs, transform_context)
        polylines, features = [], []
        for f in source.getFeatures():
            g = f.geometry()
            if g is None or g.isEmpty():
                continue
            g = QgsGeometry(g)
            if xform is not None:
                g.transform(xform)
            parts = g.asMultiPolyline() if g.isMultipart() else [g.asPolyline()]
            for part in parts:
                if len(part) < 2:
                    continue
                arr = np.asarray([(p.x(), p.y()) for p in part], dtype=np.float64)
                seg = np.diff(arr, axis=0)
                if float(np.hypot(seg[:, 0], seg[:, 1]).sum()) <= min_length:
                    continue
                polylines.append(arr)
                features.append(f)
        if not polylines:
            raise QgsProcessingException("Yol katmanında geçerli çizgi geometrisi bulunamadı.")
        return polylines, features

    @classmethod
    def network_graph(cls, source, cost_field="", feedback=None,
                      min_length: float = 1e-6, use_prepared_costs=True):
        """Yol katmanından Primal NodeGraph oluşturur."""
        polylines, features = cls.source_polylines(source, feedback, min_length)
        names = {field.name().lower(): field.name() for field in source.fields()}

        def standard_name(field_name):
            base = str(field_name).lower()
            matches = []
            for key, actual in names.items():
                if key == base:
                    matches.append((1, actual))
                elif key.startswith(base + "_") and key[len(base) + 1:].isdigit():
                    matches.append((int(key[len(base) + 1:]), actual))
            return max(matches, default=(0, None))[1]

        def values(field_name, fallback=None, standardized=False):
            actual = (standard_name(field_name) if standardized
                      else names.get(str(field_name).lower()))
            if not actual:
                return fallback
            index = source.fields().lookupField(actual)
            result = []
            for feature in features:
                try:
                    result.append(float(feature.attributes()[index]))
                except (TypeError, ValueError):
                    result.append(0.0)
            return result

        directions = values("dir_code", standardized=True)
        if directions is not None:
            directions = [int(value) if value in (-1.0, 0.0, 1.0) else 0
                          for value in directions]
        if cost_field:
            costs = values(cost_field)
            reverse = costs
        elif use_prepared_costs:
            costs = values("cost_fwd", standardized=True)
            reverse = values("cost_rev", standardized=True)
        else:
            costs = reverse = None
        graph = graphs.build_node_graph(
            polylines, costs=costs, reverse_costs=reverse,
            directions=directions)
        return graph, polylines, features

    @staticmethod
    def source_points(source, target_crs, transform_context):
        """Vektör katmanından (nokta, çizgi veya poligon yüzey noktası) (M, 2) koordinat dizisi üretir."""
        xform = None
        if target_crs is not None and source.sourceCrs() != target_crs:
            xform = QgsCoordinateTransform(source.sourceCrs(), target_crs, transform_context)
        pts, feats = [], []
        for f in source.getFeatures():
            g = f.geometry()
            if g is None or g.isEmpty():
                continue
            g = QgsGeometry(g)
            if xform is not None:
                g.transform(xform)
            p = g.pointOnSurface().asPoint()
            pts.append((p.x(), p.y()))
            feats.append(f)
        if not pts:
            raise QgsProcessingException(f"'{source.sourceName()}' katmanında kullanılabilir geometri bulunamadı.")
        return np.asarray(pts, dtype=np.float64), feats

    @staticmethod
    def make_fields(*specs, base=None) -> QgsFields:
        """(alan_adı, tip) demetlerinden QgsFields oluşturur."""
        fields = QgsFields()
        existing = set()
        if base is not None:
            for fld in base:
                fields.append(QgsField(fld))
                existing.add(fld.name().lower())
        for name, vtype in specs:
            final = name
            i = 1
            while final.lower() in existing:
                i += 1
                final = f"{name}_{i}"
            fields.append(QgsField(final, vtype))
            existing.add(final.lower())
        return fields

    @staticmethod
    def apply_quantile_symbology(layer, field_name: str, colors=None):
        """Sonuç katmanına 5 sınıflı quantile renklendirme uygular."""
        if not layer or not layer.isValid():
            return
        fields = [f.name() for f in layer.fields()]
        if field_name not in fields:
            return
        values = [f[field_name] for f in layer.getFeatures() if f[field_name] is not None]
        try:
            values = sorted(float(v) for v in values)
        except (TypeError, ValueError):
            return
        if len(values) < 2 or values[0] == values[-1]:
            return
        if colors is None:
            colors = ("#38bdf8", "#34d399", "#fbbf24", "#f97316", "#dc2626")
        ranges = []
        for idx, color in enumerate(colors):
            lo = values[int(idx * (len(values) - 1) / len(colors))]
            hi = values[int((idx + 1) * (len(values) - 1) / len(colors))]
            symbol = QgsSymbol.defaultSymbol(layer.geometryType())
            if symbol is None:
                return
            symbol.setColor(QColor(color))
            ranges.append(QgsRendererRange(lo, hi, symbol, f"{lo:.3g} - {hi:.3g}"))
        layer.setRenderer(QgsGraduatedSymbolRenderer(field_name, ranges))
        layer.triggerRepaint()
