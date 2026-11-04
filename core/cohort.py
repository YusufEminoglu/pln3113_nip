# -*- coding: utf-8 -*-
"""Kohort-bileşen (kuşak-bileşen) nüfus projeksiyonu (saf Python).

17 beş yaşlık grup (0-4 ... 80+), iki cinsiyet, beş yıllık adımlar.

Bir adım (t -> t+5):

1. Yaşlanma: P[i+1](t+5) = P[i](t) · Sx[i]  (i = 0..15; Sx[15] = T80/T75);
   açık grup: P[80+](t+5) += P[80+](t) · Sx[16]  (Sx[16] = T85/T80).
2. Doğumlar: B = 5 · Σ ASFR[a] · (K[a](t) + K[a](t+5)) / 2   (15-49 yaş kadın).
   0-4 grubu = B · cinsiyet payı · L0/(5·l0)  -- doğumdan 0-4'e yaşama oranı;
   (0-4 -> 5-9 yaşama oranı Sx[0] burada KULLANILMAZ).
3. Göç: dönemlik net göçmen sayısı yaş profiline ve cinsiyet payına göre
   eklenir. Oran olarak: N = P(t)·((1+r)^5 − 1); kişi olarak: N = 5 · yıllık.

TDH yolu: ``tfr_target`` verilirse TDH, başlangıç yılındaki değerden
``tfr_target_year`` yılına doğrusal değişir (sonra sabit); her adımın orta
noktasındaki TDH'ye göre ASFR ölçeklenir.

Hedef yıl 5'in katı adımda değilse, iki komşu adım arasında her yaş grubu
geometrik (bir uç sıfırsa doğrusal) enterpole edilir.

Varsayılan Sx / ASFR / göç profili ``core/data/kohort_varsayilan.json``
dosyasındadır; kaynak notları dosyanın içindedir ve hepsi düzenlenebilir
yer tutuculardır (resmî TÜİK tablosu değildir).
"""
from __future__ import annotations

import copy
import json
import math
import os

import numpy as np

AGE_GROUPS = (
    "0-4", "5-9", "10-14", "15-19", "20-24", "25-29", "30-34", "35-39",
    "40-44", "45-49", "50-54", "55-59", "60-64", "65-69", "70-74", "75-79", "80+",
)
N_GROUPS = len(AGE_GROUPS)
FERTILE = tuple(range(3, 10))          # 15-19 ... 45-49
STEP = 5

_DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "kohort_varsayilan.json")
_DEFAULTS_CACHE = {}


class CohortError(ValueError):
    """Kohort girdisi hatası (Türkçe ileti)."""


def load_defaults():
    """Varsayılan parametreleri (kopya) döndürür."""
    if not _DEFAULTS_CACHE:
        with open(_DATA_PATH, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        _DEFAULTS_CACHE.update({
            "sx_male": [float(v) for v in raw["sx"]["erkek"]],
            "sx_female": [float(v) for v in raw["sx"]["kadin"]],
            "birth_survival_male": float(raw["dogum_yasama"]["erkek"]),
            "birth_survival_female": float(raw["dogum_yasama"]["kadin"]),
            "asfr": [float(v) for v in raw["asfr"]["degerler"]],
            "srb": float(raw["dogumda_cinsiyet_orani"]["deger"]),
            "migration_profile": [float(v) for v in raw["goc_profili"]["degerler"]],
            "sources": {
                "sx": raw["sx"]["_kaynak"],
                "dogum_yasama": raw["dogum_yasama"]["_kaynak"],
                "asfr": raw["asfr"]["_kaynak"],
                "goc_profili": raw["goc_profili"]["_kaynak"],
            },
        })
    return copy.deepcopy(_DEFAULTS_CACHE)


def tfr(asfr):
    """Toplam doğurganlık hızı = 5 · Σ ASFR."""
    return 5.0 * sum(float(v) for v in asfr)


def normalize_age_label(label):
    """'0-4', '0–4', '0 - 4', '80+', '80 ve üzeri' gibi etiketleri grup indeksine çevirir."""
    text = str(label or "").strip().lower()
    for dash in ("–", "—", "_", " "):
        text = text.replace(dash, "-" if dash != " " else "")
    text = text.replace("veüzeri", "+").replace("veuzeri", "+").replace("üstü", "+")
    text = text.replace("ustu", "+").replace("--", "-")
    if text.startswith("80"):
        return N_GROUPS - 1
    for i, g in enumerate(AGE_GROUPS):
        if text == g:
            return i
    return None


def _vector(values, what, n=N_GROUPS, allow_negative=False):
    vals = list(values or [])
    if len(vals) != n:
        raise CohortError(f"{what} {n} değer içermeli (verilen: {len(vals)}).")
    out = []
    for v in vals:
        if v is None:
            raise CohortError(f"{what} içinde boş değer var.")
        try:
            f = float(v)
        except (TypeError, ValueError):
            raise CohortError(f"{what} sayı olmalı: {v!r}") from None
        if math.isnan(f) or (f < 0 and not allow_negative):
            raise CohortError(f"{what} negatif ya da geçersiz olamaz: {v!r}")
        out.append(f)
    return out


def stationary_weights(sx):
    """Model hayat tablosundan durağan nüfus yaş payları (grup başı yaşayan oranı)."""
    w = [1.0]
    for i in range(N_GROUPS - 2):
        w.append(w[-1] * float(sx[i]))
    last = w[-1] * float(sx[N_GROUPS - 2])
    open_sx = float(sx[N_GROUPS - 1])
    w.append(last / (1.0 - open_sx) if open_sx < 1.0 else last)
    return w


def spread_broad_groups(male_broad, female_broad, params=None):
    """(0-14, 15-64, 65+) geniş gruplarını 17 gruba dağıtır.

    Grup içi paylar model hayat tablosunun durağan nüfus yapısından gelir
    (yaklaşımdır; gerçek 5'li yaş verisi varsa onu kullanın).
    """
    d = load_defaults()
    p = params or {}
    out = []
    for broad, key in ((male_broad, "sx_male"), (female_broad, "sx_female")):
        b = _vector(broad, "Geniş yaş grupları", n=3)
        w = stationary_weights(p.get(key) or d[key])
        vec = []
        for value, (lo, hi) in zip(b, ((0, 3), (3, 13), (13, 17))):
            part = w[lo:hi]
            tot = sum(part)
            vec.extend(value * x / tot for x in part)
        out.append(vec)
    return out[0], out[1]


def median_age(totals):
    """Gruplanmış veriden medyan yaş (grup içi doğrusal enterpolasyon)."""
    pop = sum(totals)
    if pop <= 0:
        return None
    half = pop / 2.0
    cum = 0.0
    for i, v in enumerate(totals):
        if v > 0 and cum + v >= half:
            return STEP * i + STEP * (half - cum) / v
        cum += v
    return float(STEP * (N_GROUPS - 1))


def indicators(male, female):
    """Bağımlılık oranları, yaşlanma endeksi, medyan yaş, cinsiyet oranı.

    Geniş gruplar: çocuk 0-14 (ilk 3 grup), çalışma çağı 15-64 (sonraki 10),
    yaşlı 65+ (son 4). Payda sıfırsa oran ``None``.
    """
    pyramid = np.asarray(male, dtype=float) + np.asarray(female, dtype=float)
    young, working, elderly = (float(part.sum()) for part in np.split(pyramid, [3, 13]))
    men, women = float(np.sum(male)), float(np.sum(female))
    everyone = float(pyramid.sum())

    def pct(numer, denom):
        return None if denom <= 0 else 100.0 * numer / denom

    return {
        "toplam": everyone,
        "erkek": men,
        "kadin": women,
        "cocuk_0_14": young,
        "calisma_15_64": working,
        "yasli_65": elderly,
        "cocuk_orani": pct(young, everyone),
        "yasli_orani": pct(elderly, everyone),
        "toplam_bagimlilik": pct(young + elderly, working),
        "genc_bagimlilik": pct(young, working),
        "yasli_bagimlilik": pct(elderly, working),
        "yaslanma_endeksi": pct(elderly, young),
        "cinsiyet_orani": pct(men, women),
        "medyan_yas": median_age(pyramid.tolist()),
    }


def _given(params, key, fallback):
    """Parametre verilmişse (0 dahil) onu, yoksa (None / boş metin) varsayılanı döndürür."""
    value = params.get(key)
    return fallback if value is None or (isinstance(value, str) and not value.strip()) else value


def _prepare_params(params):
    d = load_defaults()
    p = dict(params or {})
    out = {
        "sx_male": _vector(_given(p, "sx_male", d["sx_male"]), "Erkek Sx"),
        "sx_female": _vector(_given(p, "sx_female", d["sx_female"]), "Kadın Sx"),
        "asfr": _vector(_given(p, "asfr", d["asfr"]), "ASFR", n=len(FERTILE)),
        "migration_profile": _vector(_given(p, "migration_profile", d["migration_profile"]),
                                     "Göç profili"),
    }
    for key in ("sx_male", "sx_female"):
        if max(out[key]) > 1.0:
            raise CohortError("Sx yaşama oranları 0 ile 1 arasında olmalı.")
    for key in ("birth_survival_male", "birth_survival_female"):
        out[key] = float(_given(p, key, d[key]))
        if not 0.0 < out[key] <= 1.0:
            raise CohortError("Doğumdan 0-4'e yaşama oranı 0'dan büyük, 1'den küçük ya da eşit "
                              "olmalı.")
    out["srb"] = float(_given(p, "srb", d["srb"]))
    if out["srb"] <= 0:
        raise CohortError("Doğumda cinsiyet oranı pozitif olmalı (ör. 105).")
    if sum(out["migration_profile"]) <= 0:
        raise CohortError("Göç profilinin toplamı sıfırdan büyük olmalı.")
    mode = str(_given(p, "migration_mode", "yok")).strip().lower()
    mode = {"none": "yok", "rate": "oran", "absolute": "kisi", "kişi": "kisi"}.get(mode, mode)
    if mode not in ("yok", "oran", "kisi"):
        raise CohortError("Göç türü 'yok', 'oran' ya da 'kisi' olmalı.")
    out["migration_mode"] = mode
    out["migration_value"] = float(_given(p, "migration_value", 0.0))
    if mode == "oran" and out["migration_value"] <= -1.0:
        raise CohortError("Yıllık net göç hızı -1'den büyük olmalı (ör. 0.01 = %1).")
    out["migration_male_share"] = float(_given(p, "migration_male_share", 0.5))
    if not 0.0 <= out["migration_male_share"] <= 1.0:
        raise CohortError("Göçte erkek payı 0 ile 1 arasında olmalı.")
    target_tfr = _given(p, "tfr_target", None)
    out["tfr_target"] = None if target_tfr is None else float(target_tfr)
    if out["tfr_target"] is not None and out["tfr_target"] < 0:
        raise CohortError("Hedef TDH negatif olamaz.")
    out["tfr_target_year"] = _given(p, "tfr_target_year", None)
    return out


def _survive(vector, sx):
    """Yaşlanma: grup i -> i+1 (Sx[i]); açık grup kendi Sx'iyle kalır. 0-4 boş döner."""
    pop = np.asarray(vector, dtype=float)
    rates = np.asarray(sx, dtype=float)
    aged = np.zeros_like(pop)
    aged[1:] = pop[:-1] * rates[:-1]
    aged[-1] += pop[-1] * rates[-1]
    return aged


def _step(male, female, prm, asfr):
    """Tek beş yıllık adım -> (erkek, kadın, doğum, net göç, sıfırlanan grup sayısı)."""
    men = _survive(male, prm["sx_male"])
    women = _survive(female, prm["sx_female"])
    fertile = list(FERTILE)
    exposure = (np.asarray(female, dtype=float)[fertile] + women[fertile]) / 2.0
    births = float(STEP * np.dot(np.asarray(asfr, dtype=float), exposure))
    boy_share = prm["srb"] / (prm["srb"] + 100.0)
    men[0] = births * boy_share * prm["birth_survival_male"]
    women[0] = births * (1.0 - boy_share) * prm["birth_survival_female"]
    if prm["migration_mode"] == "oran":
        start = float(np.sum(male) + np.sum(female))
        net = start * ((1.0 + prm["migration_value"]) ** STEP - 1.0)
    elif prm["migration_mode"] == "kisi":
        net = prm["migration_value"] * STEP
    else:
        net = 0.0
    zeroed = 0
    if net != 0.0:
        profile = np.asarray(prm["migration_profile"], dtype=float)
        by_age = net * profile / profile.sum()
        men += by_age * prm["migration_male_share"]
        women += by_age * (1.0 - prm["migration_male_share"])
        zeroed = int((men < 0).sum() + (women < 0).sum())
        men = np.maximum(men, 0.0)
        women = np.maximum(women, 0.0)
    return men.tolist(), women.tolist(), births, net, zeroed


def _interp(a, b, frac):
    if a > 0 and b > 0:
        return a * (b / a) ** frac
    return a + (b - a) * frac


def project_cohort(base, params, target_year):
    """Kohort-bileşen projeksiyonu (Sözleşme C1).

    ``base``: ``{"year": 2025, "male": [17], "female": [17]}``.
    ``params``: isteğe bağlı anahtarlar -- ``sx_male``, ``sx_female`` (17),
    ``birth_survival_male/female``, ``asfr`` (7, yıllık), ``srb``,
    ``tfr_target``, ``tfr_target_year``, ``migration_mode`` ('yok' | 'oran'
    | 'kisi'), ``migration_value`` (oran: yıllık, ör. 0.01; kisi: yıllık net
    göçmen), ``migration_profile`` (17), ``migration_male_share``.

    Döndürür: ``{years, male, female, totals, births, migrants, tfr_path,
    indicators, target_year, target: {male, female, total, indicators},
    warnings, sources}``.
    """
    if not isinstance(base, dict):
        raise CohortError("Başlangıç nüfusu {'year', 'male', 'female'} sözlüğü olmalı.")
    try:
        base_year = int(round(float(base.get("year"))))
        target = float(target_year)
    except (TypeError, ValueError):
        raise CohortError("Başlangıç yılı ve hedef yıl sayı olmalı.") from None
    if target < base_year:
        raise CohortError(f"Hedef yıl ({target:g}) başlangıç yılından ({base_year}) önce olamaz.")
    male0 = _vector(base.get("male"), "Erkek başlangıç nüfusu")
    female0 = _vector(base.get("female"), "Kadın başlangıç nüfusu")
    if sum(male0) + sum(female0) <= 0:
        raise CohortError("Başlangıç nüfusu sıfır olamaz.")
    prm = _prepare_params(params)
    warnings = []
    base_tfr = tfr(prm["asfr"])
    tfr_year = prm["tfr_target_year"]
    tfr_year = float(tfr_year) if tfr_year not in (None, "", 0) else target
    if prm["tfr_target"] is not None and tfr_year <= base_year:
        raise CohortError("Hedef TDH yılı başlangıç yılından sonra olmalı.")

    n_steps = int(math.ceil((target - base_year) / float(STEP) - 1e-9))
    years = [base_year + STEP * k for k in range(n_steps + 1)]
    male = {base_year: male0}
    female = {base_year: female0}
    births, migrants, tfr_path = {}, {}, {}
    clamped_total = 0
    path_active = prm["tfr_target"] is not None and base_tfr > 0
    for start_year, end_year in zip(years[:-1], years[1:]):
        if path_active:
            progress = min(1.0, (start_year + STEP / 2.0 - base_year) / (tfr_year - base_year))
            step_tfr = base_tfr + progress * (prm["tfr_target"] - base_tfr)
        else:
            step_tfr = base_tfr
        scale = step_tfr / base_tfr if base_tfr > 0 else 1.0
        step_asfr = [rate * scale for rate in prm["asfr"]]
        out_m, out_f, born, net, zeroed = _step(male[start_year], female[start_year], prm,
                                                step_asfr)
        male[end_year], female[end_year] = out_m, out_f
        births[end_year], migrants[end_year], tfr_path[end_year] = born, net, step_tfr
        clamped_total += zeroed
    if prm["tfr_target"] is not None and base_tfr <= 0:
        warnings.append("Başlangıç TDH sıfır; hedef TDH uygulanamadı.")
    if clamped_total:
        warnings.append(f"Net göç çıkışı {clamped_total} yaş-cinsiyet grubunu negatife "
                        "düşürdü; bu gruplar sıfırda tutuldu (göç çıkışı abartılı olabilir).")

    if target in male:
        tm, tf = male[target], female[target]
    elif float(target).is_integer() and int(target) in male:
        tm, tf = male[int(target)], female[int(target)]
    else:
        lo_y = years[-2]
        hi_y = years[-1]
        frac = (target - lo_y) / float(hi_y - lo_y)
        tm = [_interp(a, b, frac) for a, b in zip(male[lo_y], male[hi_y])]
        tf = [_interp(a, b, frac) for a, b in zip(female[lo_y], female[hi_y])]
        warnings.append(f"Hedef yıl {target:g} beş yıllık adıma düşmüyor; {lo_y} ile {hi_y} "
                        "arasında her yaş grubu geometrik enterpole edildi.")
    totals = {y: sum(male[y]) + sum(female[y]) for y in years}
    return {
        "years": years,
        "male": male,
        "female": female,
        "totals": totals,
        "births": births,
        "migrants": migrants,
        "tfr_path": tfr_path,
        "base_tfr": base_tfr,
        "indicators": {y: indicators(male[y], female[y]) for y in years},
        "target_year": target,
        "target": {"male": tm, "female": tf, "total": sum(tm) + sum(tf),
                   "indicators": indicators(tm, tf)},
        "warnings": warnings,
        "sources": load_defaults()["sources"],
    }
