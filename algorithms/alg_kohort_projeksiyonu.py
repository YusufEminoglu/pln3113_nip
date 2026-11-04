# -*- coding: utf-8 -*-
"""Kohort-bileşen nüfus projeksiyonu Processing algoritması."""
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

from ..core import cohort as co
from ..core import projection as pj
from .alg_nufus_projeksiyonu import (
    ATTRIBUTION,
    FAST_INSERT,
    FIELD_ANY,
    FIELD_NUMERIC,
    FLAG_ADVANCED,
    NO_GEOMETRY,
    NUM_DOUBLE,
    NUM_INT,
    TYPE_VECTOR_ANY,
    OngoruBaseAlgorithm,
    as_float,
    as_value,
    check_cancel,
    make_fields,
    push_warnings,
)

MIGRATION_MODES = ("yok", "oran", "kisi")
MIGRATION_LABELS = ("Göç yok", "Yıllık net göç hızı (oran, ör. 0.01 = %1)",
                    "Yıllık net göçmen sayısı (kişi)")


def _float_list(text, what, allow_thousands=True):
    try:
        return pj.parse_number_list(text, allow_thousands=allow_thousands)
    except pj.ProjectionError as exc:
        raise QgsProcessingException(f"{what}: {exc}") from None


class KohortProjeksiyonuAlgorithm(OngoruBaseAlgorithm):
    BAZ_YIL = "BAZ_YIL"
    HEDEF_YIL = "HEDEF_YIL"
    ERKEK = "ERKEK"
    KADIN = "KADIN"
    GENIS = "GENIS"
    TABLO = "TABLO"
    YAS_ALANI = "YAS_ALANI"
    ERKEK_ALANI = "ERKEK_ALANI"
    KADIN_ALANI = "KADIN_ALANI"
    HEDEF_TDH = "HEDEF_TDH"
    HEDEF_TDH_YILI = "HEDEF_TDH_YILI"
    GOC_TURU = "GOC_TURU"
    GOC_DEGERI = "GOC_DEGERI"
    ASFR = "ASFR"
    SX_ERKEK = "SX_ERKEK"
    SX_KADIN = "SX_KADIN"
    CINSIYET_ORANI = "CINSIYET_ORANI"
    OUTPUT = "OUTPUT"
    GOSTERGELER = "GOSTERGELER"

    def name(self):
        return "kohort_projeksiyonu"

    def displayName(self):
        return "2. Kohort-Bileşen Nüfus Projeksiyonu (Yaş Piramidi)"

    def shortHelpString(self):
        d = co.load_defaults()
        return (
            "17 beş yaşlık grup (0-4 ... 80+) ve iki cinsiyet için beşer yıllık adımlarla "
            "kohort-bileşen projeksiyonu.\n\n"
            "Adım: yaşlanma P[i+1] = P[i]·Sx[i]; doğumlar B = 5·Σ ASFR·(kadın(t)+kadın(t+5))/2; "
            "0-4 grubu = B × cinsiyet payı × doğumdan 0-4'e yaşama oranı (L0/5l0); net göç yaş "
            "profiline göre eklenir (oran: P·((1+r)^5 − 1), kişi: 5 × yıllık).\n"
            "Hedef yıl beşlik adıma düşmüyorsa komşu adımlar arasında her yaş grubu geometrik "
            "enterpole edilir. Hedef TDH verilirse doğurganlık hedef TDH yılına doğrusal geçer.\n\n"
            "Başlangıç nüfusu: 17 erkek ve 17 kadın değeri (virgülle), ya da yaş grubu / erkek / "
            "kadın alanları olan bir tablo, ya da 6 geniş grup değeri (E 0-14, E 15-64, E 65+, "
            "K 0-14, K 15-64, K 65+; grup içi dağılım model hayat tablosundan, yaklaşık).\n\n"
            "Varsayılan değerler DÜZENLENEBİLİR yer tutuculardır, resmî TÜİK tablosu değildir:\n"
            f"- Sx: {d['sources']['sx']}\n"
            f"- ASFR: {d['sources']['asfr']}\n"
            f"- Göç profili: {d['sources']['goc_profili']}\n\n"
            "Çıktılar: yaş piramidi tablosu (her adım ve hedef yıl) ve gösterge tablosu "
            "(bağımlılık oranları, yaşlanma endeksi, medyan yaş, doğum, net göç).\n\n" + ATTRIBUTION
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterNumber(
            self.BAZ_YIL, "Başlangıç yılı", NUM_INT, 2025, False, 1900, 2300))
        self.addParameter(QgsProcessingParameterNumber(
            self.HEDEF_YIL, "Hedef yıl", NUM_INT, 2045, False, 1900, 2300))
        self.addParameter(QgsProcessingParameterString(
            self.ERKEK, "Erkek nüfus, 17 yaş grubu (0-4 ... 80+, virgülle)", "", optional=True))
        self.addParameter(QgsProcessingParameterString(
            self.KADIN, "Kadın nüfus, 17 yaş grubu (0-4 ... 80+, virgülle)", "", optional=True))
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.TABLO, "Ya da: yaş grubu tablosu", [TYPE_VECTOR_ANY], optional=True))
        self.addParameter(QgsProcessingParameterField(
            self.YAS_ALANI, "Tablo yaş grubu alanı (0-4 ... 80+)", None, self.TABLO, FIELD_ANY,
            optional=True))
        self.addParameter(QgsProcessingParameterField(
            self.ERKEK_ALANI, "Tablo erkek alanı", None, self.TABLO, FIELD_NUMERIC, optional=True))
        self.addParameter(QgsProcessingParameterField(
            self.KADIN_ALANI, "Tablo kadın alanı", None, self.TABLO, FIELD_NUMERIC, optional=True))
        self.addParameter(QgsProcessingParameterString(
            self.GENIS, "Ya da: 6 geniş grup (E0-14, E15-64, E65+, K0-14, K15-64, K65+)", "",
            optional=True))
        self.addParameter(QgsProcessingParameterEnum(
            self.GOC_TURU, "Net göç", list(MIGRATION_LABELS), defaultValue=0))
        self.addParameter(QgsProcessingParameterNumber(
            self.GOC_DEGERI, "Net göç değeri (oran ya da kişi/yıl)", NUM_DOUBLE, 0.0))
        adv = [
            QgsProcessingParameterNumber(self.HEDEF_TDH, "Hedef toplam doğurganlık hızı "
                                         "(0 = sabit)", NUM_DOUBLE, 0.0, True, 0.0, 10.0),
            QgsProcessingParameterNumber(self.HEDEF_TDH_YILI, "Hedef TDH yılı (0 = hedef yıl)",
                                         NUM_INT, 0, True, 0, 2300),
            QgsProcessingParameterString(self.ASFR, "Yaşa özel doğurganlık hızları, 7 değer "
                                         "(15-19 ... 45-49; boş = varsayılan)", "", optional=True),
            QgsProcessingParameterString(self.SX_ERKEK, "Erkek Sx, 17 değer (boş = varsayılan)",
                                         "", optional=True),
            QgsProcessingParameterString(self.SX_KADIN, "Kadın Sx, 17 değer (boş = varsayılan)",
                                         "", optional=True),
            QgsProcessingParameterNumber(self.CINSIYET_ORANI, "Doğumda cinsiyet oranı (100 kıza "
                                         "erkek)", NUM_DOUBLE, 105.0, False, 50.0, 200.0),
        ]
        for p in adv:
            p.setFlags(p.flags() | FLAG_ADVANCED)
            self.addParameter(p)
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, "Yaş piramidi (tablo)", QgsProcessing.SourceType.TypeVector))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.GOSTERGELER, "Demografik göstergeler (tablo)", QgsProcessing.SourceType.TypeVector,
            optional=True))

    def _base(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.TABLO, context)
        if source is not None:
            af = self.parameterAsString(parameters, self.YAS_ALANI, context)
            mf = self.parameterAsString(parameters, self.ERKEK_ALANI, context)
            ff = self.parameterAsString(parameters, self.KADIN_ALANI, context)
            if not (af and mf and ff):
                raise QgsProcessingException("Tablo kullanılırken yaş, erkek ve kadın alanları "
                                             "seçilmeli.")
            male = [None] * co.N_GROUPS
            female = [None] * co.N_GROUPS
            unknown, nulls = [], 0
            for f in source.getFeatures():
                check_cancel(feedback)
                i = co.normalize_age_label(as_value(f[af]))
                if i is None:
                    unknown.append(str(as_value(f[af])))
                    continue
                m, w = as_float(f[mf]), as_float(f[ff])
                if m is None or w is None:
                    nulls += 1
                male[i] = (male[i] or 0.0) + (m or 0.0)
                female[i] = (female[i] or 0.0) + (w or 0.0)
            if unknown:
                raise QgsProcessingException("Tanınmayan yaş grubu: " + ", ".join(unknown[:5]))
            missing = [co.AGE_GROUPS[i] for i in range(co.N_GROUPS) if male[i] is None]
            if missing:
                raise QgsProcessingException("Tabloda eksik yaş grubu: " + ", ".join(missing))
            if nulls:
                feedback.pushWarning(f"{nulls} satırda erkek ya da kadın nüfus boş; 0 alındı.")
            return male, female
        broad = _float_list(self.parameterAsString(parameters, self.GENIS, context), "Geniş gruplar")
        male = _float_list(self.parameterAsString(parameters, self.ERKEK, context), "Erkek nüfus")
        female = _float_list(self.parameterAsString(parameters, self.KADIN, context), "Kadın nüfus")
        if male or female:
            return male, female
        if broad:
            if len(broad) != 6:
                raise QgsProcessingException("Geniş grup girişi 6 değer olmalı.")
            feedback.pushWarning("Geniş gruplar 17 gruba model hayat tablosunun durağan yapısıyla "
                                 "dağıtıldı; bu bir yaklaşımdır.")
            try:
                return co.spread_broad_groups(broad[:3], broad[3:])
            except co.CohortError as exc:
                raise QgsProcessingException(str(exc)) from None
        raise QgsProcessingException("Başlangıç nüfusunu girin (17+17 değer, tablo ya da 6 geniş "
                                     "grup).")

    def processAlgorithm(self, parameters, context, feedback):
        male, female = self._base(parameters, context, feedback)
        base_year = self.parameterAsInt(parameters, self.BAZ_YIL, context)
        target = self.parameterAsInt(parameters, self.HEDEF_YIL, context)
        params = {
            "migration_mode": MIGRATION_MODES[self.parameterAsEnum(parameters, self.GOC_TURU,
                                                                   context)],
            "migration_value": self.parameterAsDouble(parameters, self.GOC_DEGERI, context),
            "srb": self.parameterAsDouble(parameters, self.CINSIYET_ORANI, context),
        }
        tdh = self.parameterAsDouble(parameters, self.HEDEF_TDH, context)
        if tdh and tdh > 0:
            params["tfr_target"] = tdh
            ty = self.parameterAsInt(parameters, self.HEDEF_TDH_YILI, context)
            if ty:
                params["tfr_target_year"] = ty
        for key, pname, what in (("asfr", self.ASFR, "ASFR"), ("sx_male", self.SX_ERKEK, "Erkek Sx"),
                                 ("sx_female", self.SX_KADIN, "Kadın Sx")):
            vals = _float_list(self.parameterAsString(parameters, pname, context), what,
                               allow_thousands=False)
            if vals:
                params[key] = vals
        check_cancel(feedback)
        try:
            res = co.project_cohort({"year": base_year, "male": male, "female": female},
                                    params, target)
        except co.CohortError as exc:
            raise QgsProcessingException(str(exc)) from None
        push_warnings(feedback, res["warnings"])

        fields, _ = make_fields([("yil", "double"), ("sira", "int"), ("yas_grubu", "string"),
                                 ("erkek", "double"), ("kadin", "double"), ("toplam", "double"),
                                 ("enterpole", "int")])
        sink, dest = self.parameterAsSink(parameters, self.OUTPUT, context, fields, NO_GEOMETRY)
        if sink is None:
            raise QgsProcessingException("Piramit tablosu oluşturulamadı.")
        snapshots = [(float(y), res["male"][y], res["female"][y], 0) for y in res["years"]]
        if float(target) not in [s[0] for s in snapshots]:
            snapshots.append((float(target), res["target"]["male"], res["target"]["female"], 1))
        for y, m, w, interp in snapshots:
            check_cancel(feedback)
            for i, g in enumerate(co.AGE_GROUPS):
                f = QgsFeature(fields)
                f.setAttributes([y, i, g, m[i], w[i], m[i] + w[i], interp])
                sink.addFeature(f, FAST_INSERT)

        ind_keys = ["toplam", "erkek", "kadin", "cocuk_0_14", "calisma_15_64", "yasli_65",
                    "cocuk_orani", "yasli_orani", "toplam_bagimlilik", "genc_bagimlilik",
                    "yasli_bagimlilik", "yaslanma_endeksi", "medyan_yas", "cinsiyet_orani"]
        gfields, _ = make_fields([("yil", "double")] + [(k, "double") for k in ind_keys]
                                 + [("dogum", "double"), ("net_goc", "double"), ("tdh", "double"),
                                    ("enterpole", "int")])
        gsink, gdest = self.parameterAsSink(parameters, self.GOSTERGELER, context, gfields,
                                            NO_GEOMETRY)
        out = {self.OUTPUT: dest, "TOPLAM_HEDEF": res["target"]["total"],
               "UYARILAR": res["warnings"]}
        if gsink is not None:
            for y, m, w, interp in snapshots:
                ind = co.indicators(m, w)
                key = int(y) if y.is_integer() else y
                births = res["births"].get(key)
                mig = res["migrants"].get(key)
                tfr_v = res["tfr_path"].get(key, res["base_tfr"] if y == base_year else None)
                f = QgsFeature(gfields)
                f.setAttributes([y] + [ind[k] for k in ind_keys] + [
                    None if interp else births, None if interp else mig,
                    None if interp else tfr_v, interp])
                gsink.addFeature(f, FAST_INSERT)
            out[self.GOSTERGELER] = gdest
        feedback.pushInfo(f"{target} toplam nüfus: {res['target']['total']:,.0f}".replace(",", "."))
        return out
