# -*- coding: utf-8 -*-
"""Hedef nüfusun mahallelere dağıtımı Processing algoritması."""
from __future__ import annotations

from qgis.core import (
    QgsFeature,
    QgsProcessing,
    QgsProcessingException,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterNumber,
    QgsProcessingParameterString,
)

from ..core import allocation as al
from .alg_nufus_projeksiyonu import (
    ATTRIBUTION,
    FAST_INSERT,
    FIELD_ANY,
    FIELD_NUMERIC,
    NUM_DOUBLE,
    TYPE_VECTOR_ANY,
    OngoruBaseAlgorithm,
    as_float,
    as_value,
    check_cancel,
    make_fields,
    push_warnings,
)


def _key(value):
    v = as_value(value)
    if v is None:
        return None
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v


class MahalleDagitimiAlgorithm(OngoruBaseAlgorithm):
    GIRDI = "GIRDI"
    ANAHTAR = "ANAHTAR"
    NUFUS = "NUFUS"
    HEDEF = "HEDEF"
    YONTEM = "YONTEM"
    BOLGE_ALANI = "BOLGE_ALANI"
    BOLGE_PAYLARI = "BOLGE_PAYLARI"
    KAPASITE_ALANI = "KAPASITE_ALANI"
    OUTPUT = "OUTPUT"

    def name(self):
        return "mahalle_dagitimi"

    def displayName(self):
        return "3. Hedef Nüfusun Mahallelere Dağıtımı"

    def shortHelpString(self):
        return (
            "Hedef yıl toplam nüfusunu mahallelere (alt bölgelere) dağıtır.\n\n"
            "- Oransal: mevcut nüfus payıyla.\n"
            "- Planlama bölgesi payı: artış bölge paylarına göre (ör. 'Kentsel gelişme aksı=0.75; "
            "Kırsal=0.20; Koruma=0.05'), bölge içinde mevcut nüfusla orantılı. Bölge adları "
            "Türkçe büyük/küçük harften bağımsız eşleşir.\n"
            "- Kapasite sınırlı: artış boş kapasiteyle (kapasite − mevcut) orantılı; dolan "
            "mahallenin taşan payı diğerlerine aktarılır; sığmayan nüfus 'dağıtılamayan' olarak "
            "raporlanır.\n\n"
            "Hedef nüfuslar en büyük kalan yöntemiyle tam sayıya yuvarlanır; toplam hedefe "
            "birebir eşittir. Sonuçlar anahtar alanıyla eşleştirilerek yazılır (anahtar benzersiz "
            "ve dolu olmalı). Boş nüfus 0, boş kapasite 'artış yok' sayılır ve sayıları "
            "raporlanır.\n\n" + ATTRIBUTION
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.GIRDI, "Mahalle katmanı ya da tablosu", [TYPE_VECTOR_ANY]))
        self.addParameter(QgsProcessingParameterField(
            self.ANAHTAR, "Anahtar alanı (benzersiz: mahalle kodu / adı)", None, self.GIRDI,
            FIELD_ANY))
        self.addParameter(QgsProcessingParameterField(
            self.NUFUS, "Mevcut nüfus alanı", None, self.GIRDI, FIELD_NUMERIC))
        self.addParameter(QgsProcessingParameterNumber(
            self.HEDEF, "Hedef toplam nüfus", NUM_DOUBLE, 0.0, False, 0.0))
        self.addParameter(QgsProcessingParameterEnum(
            self.YONTEM, "Dağıtım yöntemi", [al.METHOD_LABELS[m] for m in al.METHODS],
            defaultValue=0))
        self.addParameter(QgsProcessingParameterField(
            self.BOLGE_ALANI, "Planlama bölgesi alanı (bölge yöntemi)", None, self.GIRDI,
            FIELD_ANY, optional=True))
        self.addParameter(QgsProcessingParameterString(
            self.BOLGE_PAYLARI, "Bölge payları (ad=pay; ...)", "", optional=True))
        self.addParameter(QgsProcessingParameterField(
            self.KAPASITE_ALANI, "Plan kapasitesi alanı (kapasite yöntemi)", None, self.GIRDI,
            FIELD_NUMERIC, optional=True))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, "Dağıtılmış nüfus", QgsProcessing.SourceType.TypeVector))

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.GIRDI, context)
        if source is None:
            raise QgsProcessingException("Mahalle katmanı okunamadı.")
        key_f = self.parameterAsString(parameters, self.ANAHTAR, context)
        pop_f = self.parameterAsString(parameters, self.NUFUS, context)
        target = self.parameterAsDouble(parameters, self.HEDEF, context)
        method = al.METHODS[self.parameterAsEnum(parameters, self.YONTEM, context)]
        zone_f = self.parameterAsString(parameters, self.BOLGE_ALANI, context)
        cap_f = self.parameterAsString(parameters, self.KAPASITE_ALANI, context)
        if method == "bolge" and not zone_f:
            raise QgsProcessingException("Bölge yöntemi için bölge alanı seçin.")
        if method == "kapasite" and not cap_f:
            raise QgsProcessingException("Kapasite yöntemi için kapasite alanı seçin.")
        try:
            shares = al.parse_zone_shares(
                self.parameterAsString(parameters, self.BOLGE_PAYLARI, context))
        except al.AllocationError as exc:
            raise QgsProcessingException(str(exc)) from None

        keys, pops, zones, caps = [], [], [], []
        for f in source.getFeatures():
            check_cancel(feedback)
            keys.append(_key(f[key_f]))
            pops.append(as_float(f[pop_f]))
            zones.append(as_value(f[zone_f]) if zone_f else None)
            caps.append(as_float(f[cap_f]) if cap_f else None)
        try:
            res = al.allocate(keys, pops, target, method,
                              zones=zones if zone_f else None,
                              zone_shares=shares,
                              capacities=caps if cap_f else None)
        except al.AllocationError as exc:
            raise QgsProcessingException(str(exc)) from None
        push_warnings(feedback, res["warnings"])

        fields, names = make_fields([("hedef_nufus", "int"), ("net_artis", "double"),
                                     ("artis_yuzde", "double"), ("dagitim_ham", "double")],
                                    base=source.fields())
        sink, dest = self.parameterAsSink(parameters, self.OUTPUT, context, fields,
                                          source.wkbType(), source.sourceCrs())
        if sink is None:
            raise QgsProcessingException("Çıktı katmanı oluşturulamadı.")
        by_key = res["by_key"]
        total = source.featureCount() or 1
        for i, f in enumerate(source.getFeatures()):
            check_cancel(feedback)
            row = by_key[_key(f[key_f])]
            nf = QgsFeature(fields)
            if f.hasGeometry():
                nf.setGeometry(f.geometry())
            nf.setAttributes(list(f.attributes()) + [
                int(row["hedef"]), float(row["net_artis"]), row["artis_yuzde"],
                float(row["hedef_ham"])])
            sink.addFeature(nf, FAST_INSERT)
            feedback.setProgress(int(100 * (i + 1) / total))
        feedback.pushInfo(f"Dağıtılan toplam: {res['total']}; dağıtılamayan: "
                          f"{res['unallocated']:.0f}.")
        return {self.OUTPUT: dest, "DAGITILAN": res["total"],
                "DAGITILAMAYAN": res["unallocated"], "UYARILAR": res["warnings"],
                "ALANLAR": names}
