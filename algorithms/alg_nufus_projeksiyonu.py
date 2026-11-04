# -*- coding: utf-8 -*-
"""Nüfus projeksiyonu (eğilim yöntemleri + ekonomik taban göçü) Processing algoritması.

Bu dosya ayrıca 07. grup algoritmalarının (nüfus projeksiyonu, kohort,
mahalle dağıtımı, kırılganlık) ortak QGIS yardımcılarını taşır.
"""
from __future__ import annotations

import math
import os

from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QIcon
from qgis.core import (
    Qgis,
    QgsFeature,
    QgsFeatureSink,
    QgsField,
    QgsFields,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterNumber,
    QgsProcessingParameterString,
    QgsWkbTypes,
)

from ..core import projection as pj

GROUP = "07. Nüfus Projeksiyonu, Dağıtım ve Kırılganlık"
GROUP_ID = "07_nufus_projeksiyon_kirilganlik"
ATTRIBUTION = ("Nüfus projeksiyonu, dağıtım ve kırılganlık özellikleri Kent Öngörü v1.0.0 "
               "(Berkay Memiş, GPL-2.0-or-later) temel alınarak yeniden yazıldı; pay/payda "
               "yöntemi PLN3113 stüdyosundan.")

if Qgis.versionInt() >= 33800:
    from qgis.PyQt.QtCore import QMetaType
    _TYPES = {"double": QMetaType.Type.Double, "int": QMetaType.Type.Int,
              "string": QMetaType.Type.QString}
else:  # QGIS 3.28 - 3.36
    _TYPES = {"double": QVariant.Double, "int": QVariant.Int, "string": QVariant.String}

NO_GEOMETRY = Qgis.WkbType.NoGeometry if hasattr(Qgis, "WkbType") else QgsWkbTypes.NoGeometry
FAST_INSERT = QgsFeatureSink.Flag.FastInsert
if hasattr(Qgis, "ProcessingFieldParameterDataType"):
    FIELD_NUMERIC = Qgis.ProcessingFieldParameterDataType.Numeric
    FIELD_ANY = Qgis.ProcessingFieldParameterDataType.Any
else:
    FIELD_NUMERIC = QgsProcessingParameterField.Numeric
    FIELD_ANY = QgsProcessingParameterField.Any
if hasattr(Qgis, "ProcessingNumberParameterType"):
    NUM_DOUBLE = Qgis.ProcessingNumberParameterType.Double
    NUM_INT = Qgis.ProcessingNumberParameterType.Integer
else:
    NUM_DOUBLE = QgsProcessingParameterNumber.Double
    NUM_INT = QgsProcessingParameterNumber.Integer
if hasattr(Qgis, "ProcessingParameterFlag"):
    FLAG_ADVANCED = Qgis.ProcessingParameterFlag.Advanced
else:
    from qgis.core import QgsProcessingParameterDefinition
    FLAG_ADVANCED = QgsProcessingParameterDefinition.FlagAdvanced
TYPE_VECTOR_ANY = QgsProcessing.SourceType.TypeVector


def make_field(name, kind):
    return QgsField(name, _TYPES[kind])


def make_fields(specs, base=None):
    """(ad, tür) listesinden QgsFields; taban alanlarla çakışan ada _2, _3 eklenir.

    Döndürür (fields, {istenen_ad: gerçek_ad}).
    """
    fields = QgsFields()
    existing = set()
    if base is not None:
        for f in base:
            fields.append(QgsField(f))
            existing.add(f.name().lower())
    names = {}
    for name, kind in specs:
        final = name
        i = 1
        while final.lower() in existing:
            i += 1
            final = f"{name}_{i}"
        fields.append(make_field(final, kind))
        existing.add(final.lower())
        names[name] = final
    return fields, names


def as_float(value):
    """QGIS öznitelik değerini float'a çevirir; NULL / boş / sayı değil -> None."""
    if value is None:
        return None
    if hasattr(value, "isNull") and value.isNull():
        return None
    if isinstance(value, str):
        value = value.strip().replace(",", ".")
        if not value:
            return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(out) else out


def as_value(value):
    """NULL QVariant -> None; diğerleri olduğu gibi."""
    if value is None:
        return None
    if hasattr(value, "isNull") and value.isNull():
        return None
    return value


def check_cancel(feedback):
    if feedback is not None and feedback.isCanceled():
        raise QgsProcessingException("İşlem kullanıcı tarafından iptal edildi.")


def push_warnings(feedback, warnings):
    for w in warnings:
        feedback.pushWarning(w)


class OngoruBaseAlgorithm(QgsProcessingAlgorithm):
    """07. grup algoritmaları için ortak taban."""

    def group(self):
        return GROUP

    def groupId(self):
        return GROUP_ID

    def icon(self):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "icons", "report.png")
        return QIcon(path) if os.path.exists(path) else super().icon()

    def createInstance(self):
        return type(self)()


class NufusProjeksiyonuAlgorithm(OngoruBaseAlgorithm):
    YILLAR = "YILLAR"
    NUFUSLAR = "NUFUSLAR"
    TABLO = "TABLO"
    YIL_ALANI = "YIL_ALANI"
    NUFUS_ALANI = "NUFUS_ALANI"
    HEDEF_YIL = "HEDEF_YIL"
    YONTEMLER = "YONTEMLER"
    IB_ALT = "IB_ALT"
    IB_UST = "IB_UST"
    DOYUM_K = "DOYUM_K"
    PEARL_REED = "PEARL_REED"
    K_ARAMA_UST = "K_ARAMA_UST"
    YENI_ISTIHDAM = "YENI_ISTIHDAM"
    CALISAN_BASINA = "CALISAN_BASINA"
    OUTPUT = "OUTPUT"
    SERI = "SERI"

    def name(self):
        return "nufus_projeksiyonu"

    def displayName(self):
        return "1. Nüfus Projeksiyonu (Eğilim Yöntemleri)"

    def shortHelpString(self):
        return (
            "Gözlenen (yıl, nüfus) serisinden hedef yıl nüfusunu altı yöntemle kestirir ve "
            "yöntemleri karşılaştırır.\n\n"
            "- Aritmetik: P = P_son + k(t − t_son), k = (P_son − P_ilk)/(t_son − t_ilk)\n"
            "- Geometrik: P = P_son (P_son/P_ilk)^((t − t_son)/(t_son − t_ilk))\n"
            "- İller Bankası: geometrik hız yıllık %1-%3 aralığına çekilir; çekildiğinde uyarı "
            "verilir.\n"
            "- Doğrusal regresyon ve 2. derece polinom: en küçük kareler (polinom en az 3 gözlem).\n"
            "- Lojistik: P = K/(1 + e^(a + b(t − t_ilk))); K verilmezse hatayı en küçükleyen K "
            "aranır, arama sınırına dayanırsa uyarı verilir. Pearl-Reed seçeneği ilk, orta ve "
            "son yılı (eşit aralıklı) kullanır.\n\n"
            "R²: modelin gözlem yıllarındaki uyumu. Geri test: son gözlem çıkarılıp kurulan "
            "modelin o yıl için yüzde hatası (+ fazla, − eksik tahmin).\n\n"
            "Ekonomik taban göçü (isteğe bağlı): yeni istihdam × çalışan başına nüfus kadar göç "
            "nüfusu her yöntemin sonucuna ayrıca eklenir. Varsayılan 2,7 kişi/çalışan, Türkiye "
            "nüfusunun istihdama oranına (2023, yaklaşık 85,4 milyon / 31,6 milyon) dayanır; "
            "yerel değerle değiştirin.\n\n"
            "Seri iki yoldan girilebilir: yıllar ve nüfuslar metin olarak (ör. '2007, 2010, 2015' "
            "ve '76327, 78372, 82102') ya da yıl/nüfus alanları olan bir tablo. Yıllar kesin "
            "artan, nüfuslar pozitif olmalıdır. Çıktılar: yöntem özet tablosu ve yıllık seri "
            "tablosu.\n\n" + ATTRIBUTION
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterString(
            self.YILLAR, "Gözlem yılları (virgülle; tablo kullanılmıyorsa)", "", optional=True))
        self.addParameter(QgsProcessingParameterString(
            self.NUFUSLAR, "Gözlenen nüfuslar (yıllarla aynı sırada)", "", optional=True))
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.TABLO, "Ya da: yıl-nüfus tablosu", [TYPE_VECTOR_ANY], optional=True))
        self.addParameter(QgsProcessingParameterField(
            self.YIL_ALANI, "Tablo yıl alanı", None, self.TABLO, FIELD_NUMERIC, optional=True))
        self.addParameter(QgsProcessingParameterField(
            self.NUFUS_ALANI, "Tablo nüfus alanı", None, self.TABLO, FIELD_NUMERIC,
            optional=True))
        self.addParameter(QgsProcessingParameterNumber(
            self.HEDEF_YIL, "Hedef yıl", NUM_INT, 2045, False, 1800, 2300))
        self.addParameter(QgsProcessingParameterEnum(
            self.YONTEMLER, "Yöntemler", [pj.METHOD_LABELS[m] for m in pj.METHODS],
            allowMultiple=True, defaultValue=list(range(len(pj.METHODS)))))
        adv = [
            QgsProcessingParameterNumber(self.IB_ALT, "İller Bankası alt sınır (%/yıl)",
                                         NUM_DOUBLE, 1.0, False, -10.0, 20.0),
            QgsProcessingParameterNumber(self.IB_UST, "İller Bankası üst sınır (%/yıl)",
                                         NUM_DOUBLE, 3.0, False, -10.0, 20.0),
            QgsProcessingParameterNumber(self.DOYUM_K, "Lojistik doyum nüfusu K (0 = kestir)",
                                         NUM_DOUBLE, 0.0, True, 0.0),
            QgsProcessingParameterBoolean(self.PEARL_REED, "Lojistikte Pearl-Reed üç nokta "
                                          "yöntemini kullan", False),
            QgsProcessingParameterNumber(self.K_ARAMA_UST, "K arama üst sınırı (en büyük "
                                         "nüfusun katı)", NUM_DOUBLE, 10.0, False, 1.01, 1000.0),
        ]
        for p in adv:
            p.setFlags(p.flags() | FLAG_ADVANCED)
            self.addParameter(p)
        self.addParameter(QgsProcessingParameterNumber(
            self.YENI_ISTIHDAM, "Ekonomik taban: yeni istihdam (kişi, 0 = kullanma)",
            NUM_DOUBLE, 0.0, True, 0.0))
        self.addParameter(QgsProcessingParameterNumber(
            self.CALISAN_BASINA, "Ekonomik taban: çalışan başına nüfus (kişi/çalışan)",
            NUM_DOUBLE, 2.7, True, 0.0))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, "Projeksiyon özeti (tablo)", QgsProcessing.SourceType.TypeVector))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.SERI, "Yıllık projeksiyon serisi (tablo)", QgsProcessing.SourceType.TypeVector,
            optional=True))

    def _series(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.TABLO, context)
        if source is not None:
            yf = self.parameterAsString(parameters, self.YIL_ALANI, context)
            pf = self.parameterAsString(parameters, self.NUFUS_ALANI, context)
            if not yf or not pf:
                raise QgsProcessingException("Tablo kullanılırken yıl ve nüfus alanları seçilmeli.")
            pairs, nulls = [], 0
            for f in source.getFeatures():
                check_cancel(feedback)
                y, p = as_float(f[yf]), as_float(f[pf])
                if y is None or p is None:
                    nulls += 1
                    continue
                pairs.append((y, p))
            if nulls:
                feedback.pushWarning(f"{nulls} satırda yıl ya da nüfus boş; atlandı.")
            pairs.sort(key=lambda t: t[0])
            return [a for a, _ in pairs], [b for _, b in pairs]
        try:
            years = pj.parse_number_list(self.parameterAsString(parameters, self.YILLAR, context))
            pops = pj.parse_number_list(self.parameterAsString(parameters, self.NUFUSLAR, context))
        except pj.ProjectionError as exc:
            raise QgsProcessingException(str(exc)) from None
        if not years and not pops:
            raise QgsProcessingException("Gözlem yıllarını ve nüfuslarını girin ya da bir tablo seçin.")
        return years, pops

    def processAlgorithm(self, parameters, context, feedback):
        years, pops = self._series(parameters, context, feedback)
        try:
            pj.validate_series(years, pops)
        except pj.ProjectionError as exc:
            raise QgsProcessingException(str(exc)) from None
        target = self.parameterAsInt(parameters, self.HEDEF_YIL, context)
        idx = self.parameterAsEnums(parameters, self.YONTEMLER, context)
        if not idx:
            raise QgsProcessingException("En az bir yöntem seçin.")
        methods = [pj.METHODS[i] for i in idx]
        k_user = self.parameterAsDouble(parameters, self.DOYUM_K, context)
        opts = {
            "ib_lower": self.parameterAsDouble(parameters, self.IB_ALT, context),
            "ib_upper": self.parameterAsDouble(parameters, self.IB_UST, context),
            "saturation": k_user if k_user and k_user > 0 else None,
            "pearl_reed": self.parameterAsBool(parameters, self.PEARL_REED, context),
            "k_search_max": self.parameterAsDouble(parameters, self.K_ARAMA_UST, context),
        }
        jobs = self.parameterAsDouble(parameters, self.YENI_ISTIHDAM, context)
        econ = None
        if jobs and jobs > 0:
            try:
                econ = pj.economic_base_migration(
                    self.parameterAsDouble(parameters, self.CALISAN_BASINA, context), new_jobs=jobs)
            except pj.ProjectionError as exc:
                raise QgsProcessingException(str(exc)) from None
            push_warnings(feedback, econ["warnings"])
            feedback.pushInfo(f"Ekonomik taban göçü: {econ['goc_ile_karsilanan_is']:.0f} iş × "
                              f"{econ['calisan_basina_nufus']:g} = {econ['goc_nufusu']:.0f} kişi.")
        results = []
        for i, method in enumerate(methods):
            check_cancel(feedback)
            results.extend(pj.project_all(years, pops, target, [method], **opts))
            feedback.setProgress(int(80 * (i + 1) / len(methods)))

        fields, _ = make_fields([
            ("yontem", "string"), ("yontem_adi", "string"), ("hedef_yil", "int"),
            ("tahmin", "double"), ("ekonomik_goc", "double"), ("tahmin_goc_dahil", "double"),
            ("r2", "double"), ("geri_test_yuzde", "double"), ("parametre", "string"),
            ("uyarilar", "string"), ("hata", "string"),
        ])
        sink, dest = self.parameterAsSink(parameters, self.OUTPUT, context, fields, NO_GEOMETRY)
        if sink is None:
            raise QgsProcessingException("Özet tablosu oluşturulamadı.")
        econ_pop = econ["goc_nufusu"] if econ else None
        summary = {}
        all_warn = []
        for r in results:
            f = QgsFeature(fields)
            value = r["value"]
            with_econ = (value + econ_pop) if (value is not None and econ_pop is not None) else value
            f.setAttributes([
                r["method"], r["label"], int(target), value, econ_pop, with_econ, r["r2"],
                r["backtest_pct"], r["params_text"], " | ".join(r["warnings"]) or None,
                r.get("error"),
            ])
            sink.addFeature(f, FAST_INSERT)
            if r.get("error"):
                feedback.pushWarning(f"{r['label']}: {r['error']}")
            else:
                summary[r["method"]] = with_econ
                for w in r["warnings"]:
                    all_warn.append(f"{r['label']}: {w}")
                bt = "-" if r["backtest_pct"] is None else f"%{r['backtest_pct']:+.2f}"
                r2 = "-" if r["r2"] is None else f"{r['r2']:.4f}"
                feedback.pushInfo(f"{r['label']}: {target} = {value:,.0f} (R² {r2}, geri test {bt})"
                                  .replace(",", "."))
        push_warnings(feedback, all_warn)
        out = {self.OUTPUT: dest, "TAHMINLER": summary, "UYARILAR": all_warn,
               "EKONOMIK_GOC": econ_pop}

        sfields, _ = make_fields([("yontem", "string"), ("yil", "double"), ("tahmin", "double"),
                                  ("gozlem", "double")])
        ssink, sdest = self.parameterAsSink(parameters, self.SERI, context, sfields, NO_GEOMETRY)
        if ssink is not None:
            observed = dict(zip(years, pops))
            for r in results:
                check_cancel(feedback)
                for y, v in r["series"]:
                    f = QgsFeature(sfields)
                    f.setAttributes([r["method"], float(y), v, observed.get(float(y))])
                    ssink.addFeature(f, FAST_INSERT)
            out[self.SERI] = sdest
        feedback.setProgress(100)
        return out
