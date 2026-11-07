# -*- coding: utf-8 -*-
"""QGIS 3.28 (Qt5) ile QGIS 3.38+ / 4 (Qt6) arasında değişen sabitler."""
from __future__ import annotations

from qgis.core import Qgis, QgsGeometry

if Qgis.versionInt() >= 33800:
    from qgis.PyQt.QtCore import QMetaType
    FIELD_STRING = QMetaType.Type.QString
    FIELD_DOUBLE = QMetaType.Type.Double
    FIELD_INT = QMetaType.Type.Int
    FIELD_LONG = QMetaType.Type.LongLong
else:  # QGIS 3.28 - 3.36
    from qgis.PyQt.QtCore import QVariant
    FIELD_STRING = QVariant.String
    FIELD_DOUBLE = QVariant.Double
    FIELD_INT = QVariant.Int
    FIELD_LONG = QVariant.LongLong

if hasattr(Qgis, "BufferSide"):
    SIDE_LEFT, SIDE_RIGHT = Qgis.BufferSide.Left, Qgis.BufferSide.Right
else:
    SIDE_LEFT, SIDE_RIGHT = QgsGeometry.BufferSide.SideLeft, QgsGeometry.BufferSide.SideRight

if hasattr(Qgis, "JoinStyle"):
    JOIN_MITER = Qgis.JoinStyle.Miter
else:
    JOIN_MITER = QgsGeometry.JoinStyle.JoinStyleMiter
