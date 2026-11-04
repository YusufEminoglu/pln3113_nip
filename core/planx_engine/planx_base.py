# -*- coding: utf-8 -*-
"""PlanX algoritmaları için ortak temel sınıf ve geometri/graf yardımcıları.

PLN3113 NİP Analiz Stüdyosu - PlanX Motoru Tabanı
"""
from __future__ import annotations

import math
import os
import numpy as np

from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.PyQt.QtGui import QColor, QIcon
from qgis.core import (
    QgsCoordinateTransform,
    QgsCoordinateTransformContext,
    QgsDistanceArea,
    QgsPointXY,
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

DOUBLE = QVariant.Double
INT = QVariant.Int
LONG = QVariant.LongLong
STRING = QVariant.String

GROUP_NETWORK = "05. Ulaşım ve Network Analizleri"
GROUP_STANDARDS = "04. NİP Nüfus, Donatı ve DOP Analizi"
GROUP_REPORT = "06. Plan Raporlama ve Senaryo Analizleri"

#: İptal edilen her koşunun mesajı (PlanX 4.23.0 "Cancel means cancel"):
#: iptal edilen bir koşu hata verir ve hiçbir çıktı yazmaz.
CANCELLED_MESSAGE = ("Kullanıcı tarafından iptal edildi - işlem bitmeden durdu, "
                     "bu nedenle sonuç üretilmedi.")

#: Space syntax yarıçaplarında "global" anlamına gelen ifadeler.
GLOBAL_TOKENS = ("n", "rn", "global", "inf")


def check_cancel(feedback):
    """``feedback`` iptal edildiyse standart iptal hatasını fırlatır."""
    if feedback is not None and feedback.isCanceled():
        raise QgsProcessingException(CANCELLED_MESSAGE)


def parse_number_list(text, label, example, allow_global=False, unit_suffixes=()):
    """``"400, 800; n"`` gibi bir metni yazıldığı sırayla sayılara çevirir.

    PlanX 4.23.0 ``_inputs.parse_number_list`` karşılığı: "on dakika" ya da
    "abc" gibi bir değer Python izi yerine parametreyi adlandıran düz bir
    Türkçe mesaj verir. ``allow_global`` ``n`` değerini ``None`` olarak kabul
    eder; ``unit_suffixes`` ("m",) ile "400m" 400 olarak okunur. Değerler
    sıfırdan büyük ve sonlu olmalıdır.
    """
    values = []
    raw = str(text if text is not None else "")
    for token in raw.replace(";", ",").split(","):
        token = token.strip()
        if not token:
            continue
        low = token.lower()
        if allow_global and low in GLOBAL_TOKENS:
            values.append(None)
            continue
        number_text = low
        for suffix in unit_suffixes:
            if number_text.endswith(suffix):
                number_text = number_text[: -len(suffix)].strip()
                break
        try:
            value = float(number_text)
        except ValueError:
            raise QgsProcessingException(
                f"{label}: '{token}' bir sayı değil. Virgülle ayrılmış düz sayılar "
                f"yazın, örn: {example}.") from None
        if not math.isfinite(value) or value <= 0:
            raise QgsProcessingException(
                f"{label}: '{token}' sıfırdan büyük, sonlu bir sayı olmalıdır, örn: {example}.")
        values.append(value)
    if not values:
        raise QgsProcessingException(
            f"{label}: değer girilmedi. Virgülle ayrılmış sayılar yazın, örn: {example}.")
    return values


def layer_units_per_metre(crs, extent, transform_context=None):
    """Katman CRS'inde bir yer metresinin kaç koordinat birimi ettiği.

    PlanX 4.23.0 ``_units.GroundUnits.scale`` karşılığı. Yarıçaplar ve
    uzunlukla yönlendirilen hizmet alanı eşikleri yer metresi olarak girilir;
    graf ise katmanın kendi biriminde ölçer (EPSG:3857'de enlemle büyüyen
    "metre"; feet birimli KRS'ler ``require_projected`` ile zaten reddedilir). Kapsamın ortasından geçen bir
    referans doğrunun düzlem uzunluğu elipsoid üzerindeki uzunluğuna bölünür.
    Metre CRS'lerde elipsoid yuvarlama gürültüsü (|k - 1| < 1e-6) 1'e
    yuvarlanır: o gürültü bir eşiği tam eşikte ulaşılan düğümlerin hemen
    ötesine iter ve sıfır uzunluklu parçalar üretir. Coğrafi CRS reddedilir.
    """
    if crs is None or not crs.isValid():
        raise QgsProcessingException(
            "Katmanın koordinat sistemi geçerli değil; uzunluklar yer metresine çevrilemez.")
    if crs.isGeographic():
        raise QgsProcessingException(
            f"Katman coğrafi koordinat sistemi ({crs.authid()}) kullanıyor; derece "
            "cinsinden mesafe anlamsızdır. Katmanı projeksiyonlu bir sisteme "
            "(örn: EPSG:5253 TUREF / TM27) dönüştürün.")
    if (extent is None or extent.isNull()
            or not all(math.isfinite(v) for v in (
                extent.xMinimum(), extent.yMinimum(),
                extent.xMaximum(), extent.yMaximum()))
            or extent.xMaximum() < extent.xMinimum()
            or extent.yMaximum() < extent.yMinimum()):
        raise QgsProcessingException(
            "Katmanın kapsamı yok; koordinat birimleri yer metresine çevrilemez.")
    area = QgsDistanceArea()
    area.setSourceCrs(crs, transform_context or QgsCoordinateTransformContext())
    area.setEllipsoid(crs.ellipsoidAcronym() or "WGS84")
    if not area.ellipsoid() or area.ellipsoid() == "NONE":
        raise QgsProcessingException(
            f"Katmanın koordinat sistemi ({crs.authid()}) bir elipsoid tanımlamıyor; "
            "yer uzunlukları hesaplanamaz. Bilinen datumlu bir sisteme dönüştürün.")
    centre = extent.center()
    half = max(extent.width(), 1.0) / 2.0
    reference = QgsGeometry.fromPolylineXY([
        QgsPointXY(centre.x() - half, centre.y()),
        QgsPointXY(centre.x() + half, centre.y()),
    ])
    planar = reference.length()
    ground = float(area.measureLength(reference))
    if planar <= 0.0 or ground <= 0.0 or not math.isfinite(ground):
        raise QgsProcessingException(
            f"Katman koordinat sisteminin ({crs.authid()}) yerel ölçeği ölçülemedi.")
    scale = planar / ground
    return 1.0 if abs(scale - 1.0) < 1e-6 else scale



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
        # Birimi metre olmayan projeksiyonlu KRS (ör. ABD ayağı) de reddedilir:
        # mesafe, alan ve yarıçap çıktıları metre olarak raporlanır. NIP-FIX'in
        # nüfus aracındaki kuralla aynı yardımcı (core.nip_calculator).
        from ..nip_calculator import metre_birimli_mi
        if crs.isValid() and not metre_birimli_mi(crs):
            raise QgsProcessingException(
                f"'{name}' harita birimi metre olmayan bir koordinat sistemi ({crs.authid()}) "
                "kullanıyor (ör. feet). Ağ analizleri metre birimli projeksiyonlu bir sistem "
                "gerektirir. Lütfen katmanı metre birimli bir sisteme (örn: EPSG:5253 TUREF / TM27) "
                "dönüştürün."
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

        def values(field_name, fallback=None, standardized=False, missing=0.0):
            actual = (standard_name(field_name) if standardized
                      else names.get(str(field_name).lower()))
            if not actual:
                return fallback
            index = source.fields().lookupField(actual)
            result = []
            for feature in features:
                raw = feature.attributes()[index]
                try:
                    value = missing if raw is None else float(raw)
                except (TypeError, ValueError):
                    value = missing
                result.append(value)
            return result

        directions = values("dir_code", standardized=True)
        if directions is not None:
            directions = [int(value) if value in (-1.0, 0.0, 1.0) else 0
                          for value in directions]
        if cost_field:
            costs = values(cost_field, missing=math.nan)
            reverse = costs
            cost_names = (cost_field, cost_field)
        elif use_prepared_costs:
            costs = values("cost_fwd", standardized=True, missing=math.nan)
            reverse = values("cost_rev", standardized=True, missing=math.nan)
            cost_names = (standard_name("cost_fwd"), standard_name("cost_rev"))
            if costs is not None and reverse is None:
                # PlanX 4.23.0: only a forward cost -> the reverse copies it
                # (it used to be the length, so minutes got metres in reverse).
                reverse = costs
                cost_names = (cost_names[0], cost_names[0])
        else:
            costs = reverse = None
        if costs is not None or reverse is not None:
            cls._refuse_unusable_costs(features, costs, reverse, directions, cost_names)
        graph = graphs.build_node_graph(
            polylines, costs=costs, reverse_costs=reverse,
            directions=directions)
        return graph, polylines, features

    @staticmethod
    def _refuse_unusable_costs(features, costs, reverse, directions, cost_names):
        """NULL, sayısal olmayan, sıfır ya da negatif maliyetleri reddeder.

        PlanX 4.23.0 "Network costs" düzeltmesi: graf kurucusu böyle bir
        değerin yerine segment uzunluğunu (katman biriminde) koyuyordu; örneğin
        dakika sütununda eksik bir 2 dakikalık bağlantı sessizce 1000
        "dakikalık" oluyordu. Maliyet yalnızca segmentin geçilebildiği yönde
        denetlenir (tek yönlü yolun ters maliyeti gerekmez).
        """
        bad_ids, all_ids = set(), set()
        examples = []
        for i, feature in enumerate(features):
            all_ids.add(feature.id())
            direction = directions[i] if directions is not None else 0
            checks = []
            if costs is not None and direction >= 0:
                checks.append((costs[i], cost_names[0]))
            if reverse is not None and direction <= 0:
                checks.append((reverse[i], cost_names[1]))
            for value, name in checks:
                if not (math.isfinite(value) and value > 0.0):
                    bad_ids.add(feature.id())
                    if len(examples) < 3:
                        examples.append(f"obje {feature.id()} ({name})")
                    break
        if bad_ids:
            names = sorted({name for name in cost_names if name})
            raise QgsProcessingException(
                f"{len(all_ids)} yol objesinin {len(bad_ids)} tanesinde maliyet alanı "
                f"{' / '.join(repr(n) for n in names)} NULL, sayısal değil, sıfır ya da "
                f"negatif (örn: {', '.join(examples)}). Eklenti bu objeler için maliyet "
                "tahmin etmez - yerine segment uzunluğunu koymak harita birimlerini "
                "maliyete karıştırır. Değerleri doldurun (Alan Hesaplayıcı) ya da "
                "uzunlukla yönlendirmek için maliyet alanını boş bırakın.")

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
