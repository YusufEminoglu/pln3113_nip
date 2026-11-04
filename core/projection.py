# -*- coding: utf-8 -*-
"""Eğilim temelli nüfus projeksiyonu ve ekonomik taban göçü (saf Python).

Sözleşme C1: ``project_trend(years, populations, method, target_year)``
-> ``dict(value, series, r2, backtest_pct, warnings, ...)``.

Yöntemler
---------
``aritmetik``      P(t) = P_son + k (t - t_son),  k = (P_son - P_ilk)/(t_son - t_ilk)
``geometrik``      P(t) = P_son (P_son/P_ilk)^((t - t_son)/(t_son - t_ilk))
``iller_bankasi``  Geometrik hız, yıllık %1 - %3 aralığına sınırlanır (sınırlanınca uyarı).
``regresyon``      En küçük kareler doğrusu P = a + b t (tüm gözlemler).
``polinom``        2. derece en küçük kareler eğrisi (en az 3 gözlem).
``lojistik``       P = K / (1 + exp(a + b (t - t_ilk))). K verilmezse SSE'yi en
                   küçükleyen K aranır (arama sınırına dayanırsa uyarı); istenirse
                   Pearl-Reed üç nokta yöntemi (eşit aralıklı üç gözlem).

"Üstel" yöntem alınmadı: iki noktadan kurulduğunda geometrik ile aynı sonucu verir.

R²: modelin gözlem yıllarındaki kestirimleri ile gözlemler arasında
1 - SS_hata / SS_toplam. Geri test: son gözlem çıkarılıp model yeniden
kurulur; son yılın kestirim hatası yüzde olarak verilir (+ fazla, - eksik).
"""
from __future__ import annotations

import math

METHODS = ("aritmetik", "geometrik", "iller_bankasi", "regresyon", "polinom", "lojistik")

METHOD_LABELS = {
    "aritmetik": "Aritmetik artış",
    "geometrik": "Geometrik artış",
    "iller_bankasi": "İller Bankası (%1-%3 sınırlı geometrik)",
    "regresyon": "Doğrusal regresyon (en küçük kareler)",
    "polinom": "2. derece polinom (en küçük kareler)",
    "lojistik": "Lojistik (doyumlu) büyüme",
}

MIN_POINTS = {
    "aritmetik": 2, "geometrik": 2, "iller_bankasi": 2,
    "regresyon": 2, "polinom": 3, "lojistik": 3,
}


class ProjectionError(ValueError):
    """Girdi ya da yöntem hatası (Türkçe ileti taşır)."""


# ---------------------------------------------------------------------------
# Girdi denetimi
# ---------------------------------------------------------------------------

def _as_float(value, what):
    if value is None:
        raise ProjectionError(f"{what} boş bırakılamaz.")
    if isinstance(value, str):
        value = value.strip().replace(" ", "")
        if value.count(",") == 1 and "." not in value:
            value = value.replace(",", ".")
    try:
        out = float(value)
    except (TypeError, ValueError):
        raise ProjectionError(f"{what} sayı olmalı: {value!r}") from None
    if math.isnan(out) or math.isinf(out):
        raise ProjectionError(f"{what} geçerli bir sayı değil: {value!r}")
    return out


def validate_series(years, populations):
    """Yıl/nüfus serisini denetler; (yıllar, nüfuslar) float listeleri döndürür."""
    years = list(years or [])
    populations = list(populations or [])
    if len(years) != len(populations):
        raise ProjectionError(
            f"Yıl sayısı ({len(years)}) ile nüfus sayısı ({len(populations)}) eşit olmalı.")
    if len(years) < 2:
        raise ProjectionError("Projeksiyon için en az iki (yıl, nüfus) gözlemi gerekli.")
    ys = [_as_float(y, "Yıl") for y in years]
    ps = [_as_float(p, "Nüfus") for p in populations]
    for a, b in zip(ys, ys[1:]):
        if b <= a:
            raise ProjectionError(
                "Yıllar kesin artan sırada olmalı (aynı yıl iki kez ya da geriye giden "
                f"yıl var: {a:g} -> {b:g}).")
    for y, p in zip(ys, ps):
        if p <= 0:
            raise ProjectionError(f"Nüfus pozitif olmalı ({y:g} yılı: {p:g}).")
    return ys, ps


def parse_number_list(text, allow_thousands=True):
    """'2007, 2010; 2015' ya da '76.327 78.372' biçimindeki metni sayılara çevirir.

    Ayırıcılar: virgül, noktalı virgül, boşluk, satır sonu; ondalık işareti nokta.
    ``allow_thousands`` açıkken Türkçe binlik yazımı (76.327 = 76327) kabul
    edilir: tam kısmı sıfır olmayan ve her noktadan sonra tam üç hane gelen
    değerler binlik sayılır. Oran listelerinde (Sx, ASFR) kapatın.
    """
    out = []
    raw = (text or "").replace("\n", ";").replace("\t", ";")
    for chunk in raw.replace(";", " ").replace(",", " ").split():
        token = chunk.strip()
        if not token:
            continue
        parts = token.split(".")
        if (allow_thousands and len(parts) > 1 and parts[0].lstrip("-+").isdigit()
                and int(parts[0].lstrip("-+")) != 0
                and all(len(p) == 3 and p.isdigit() for p in parts[1:])):
            token = token.replace(".", "")
        out.append(_as_float(token, "Değer"))
    return out


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------

def r_squared(observed, predicted):
    n = len(observed)
    if n < 2:
        return None
    mean = sum(observed) / n
    ss_tot = sum((o - mean) ** 2 for o in observed)
    if ss_tot <= 0:
        return None
    ss_res = sum((o - p) ** 2 for o, p in zip(observed, predicted))
    return 1.0 - ss_res / ss_tot


def _solve(matrix, vector):
    """Kısmi pivotlu Gauss eliminasyonu (küçük sistemler için)."""
    n = len(vector)
    a = [list(map(float, row)) + [float(v)] for row, v in zip(matrix, vector)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(a[r][col]))
        if abs(a[pivot][col]) < 1e-12:
            raise ProjectionError("Denklem sistemi tekil; gözlem yılları yeterince farklı değil.")
        a[col], a[pivot] = a[pivot], a[col]
        for r in range(col + 1, n):
            f = a[r][col] / a[col][col]
            for c in range(col, n + 1):
                a[r][c] -= f * a[col][c]
    x = [0.0] * n
    for r in range(n - 1, -1, -1):
        x[r] = (a[r][n] - sum(a[r][c] * x[c] for c in range(r + 1, n))) / a[r][r]
    return x


def _least_squares_poly(xs, ys, degree):
    m = degree + 1
    s = [sum(x ** k for x in xs) for k in range(2 * degree + 1)]
    t = [sum(y * x ** k for x, y in zip(xs, ys)) for k in range(m)]
    return _solve([[s[i + j] for j in range(m)] for i in range(m)], t)


def _linear_fit(xs, ys):
    n = len(xs)
    xm, ym = sum(xs) / n, sum(ys) / n
    sxx = sum((x - xm) ** 2 for x in xs)
    if sxx <= 0:
        raise ProjectionError("Doğru uydurulamadı: yıllar farklı olmalı.")
    b = sum((x - xm) * (y - ym) for x, y in zip(xs, ys)) / sxx
    return ym - b * xm, b


def _fmt(n):
    return f"{n:,.0f}".replace(",", ".")


# ---------------------------------------------------------------------------
# Modeller: her biri (predict, params, params_text, warnings) döndürür
# ---------------------------------------------------------------------------

def _m_aritmetik(ys, ps, opts):
    k = (ps[-1] - ps[0]) / (ys[-1] - ys[0])
    y1, p1 = ys[-1], ps[-1]
    return (lambda t: p1 + k * (t - y1)), {"k": k}, f"k = {k:.1f} kişi/yıl", []


def _m_geometrik(ys, ps, opts):
    r = (ps[-1] / ps[0]) ** (1.0 / (ys[-1] - ys[0])) - 1.0
    y1, p1 = ys[-1], ps[-1]
    return (lambda t: p1 * (1.0 + r) ** (t - y1)), {"r": r}, f"r = %{100 * r:.3f} / yıl", []


def _m_iller_bankasi(ys, ps, opts):
    lower = float(opts.get("ib_lower", 1.0))
    upper = float(opts.get("ib_upper", 3.0))
    if lower > upper:
        raise ProjectionError("İller Bankası alt sınırı üst sınırdan büyük olamaz.")
    raw = ((ps[-1] / ps[0]) ** (1.0 / (ys[-1] - ys[0])) - 1.0) * 100.0
    rate = min(upper, max(lower, raw))
    warnings = []
    text = f"a = %{rate:.2f} / yıl"
    if abs(rate - raw) > 1e-12:
        warnings.append(
            f"İller Bankası: hesaplanan yıllık artış hızı %{raw:.3f}, "
            f"%{lower:g}-%{upper:g} aralığına çekildi (%{rate:.2f} kullanıldı).")
        text += f" (hesaplanan %{raw:.3f} sınırlandı)"
    y1, p1 = ys[-1], ps[-1]
    params = {"a_yuzde": rate, "a_hesaplanan_yuzde": raw, "sinirlandi": abs(rate - raw) > 1e-12}
    return (lambda t: p1 * (1.0 + rate / 100.0) ** (t - y1)), params, text, warnings


def _m_regresyon(ys, ps, opts):
    x0 = ys[-1]
    a, b = _linear_fit([y - x0 for y in ys], ps)
    text = f"P = {a:.1f} {b:+.2f}·(t − {x0:g})"
    return (lambda t: a + b * (t - x0)), {"a": a - b * x0, "b": b}, text, []


def _m_polinom(ys, ps, opts):
    x0 = ys[-1]
    c0, c1, c2 = _least_squares_poly([y - x0 for y in ys], ps, 2)
    warnings = []
    if c2 < 0:
        warnings.append("Polinom eğrisi aşağı bükülüyor (c2 < 0): uzun vadede nüfus düşer; "
                        "hedef yıl uzaksa dikkatle kullanın.")
    text = f"P = {c0:.1f} {c1:+.2f}·u {c2:+.4f}·u² (u = t − {x0:g})"
    return ((lambda t: c0 + c1 * (t - x0) + c2 * (t - x0) ** 2),
            {"c0": c0, "c1": c1, "c2": c2, "t0": x0}, text, warnings)


def _logit_fit(ys, ps, k):
    x0 = ys[0]
    zs = [math.log(k / p - 1.0) for p in ps]
    a, b = _linear_fit([y - x0 for y in ys], zs)
    return a, b


def _logistic_predict(k, a, b, x0):
    def predict(t):
        e = a + b * (t - x0)
        if e > 700:
            return 0.0
        return k / (1.0 + math.exp(e))
    return predict


def _sse(ys, ps, predict):
    return sum((p - predict(y)) ** 2 for y, p in zip(ys, ps))


def pearl_reed_k(p0, p1, p2):
    """Pearl-Reed üç nokta doyum nüfusu: K = (2 P0 P1 P2 - P1²(P0+P2)) / (P0 P2 - P1²)."""
    den = p0 * p2 - p1 * p1
    if den >= 0:
        raise ProjectionError(
            "Pearl-Reed uygulanamaz: P0·P2 < P1² olmalı (büyüme yavaşlamıyor).")
    k = (2.0 * p0 * p1 * p2 - p1 * p1 * (p0 + p2)) / den
    if k <= max(p0, p1, p2):
        raise ProjectionError("Pearl-Reed doyum nüfusu gözlenen en büyük nüfustan küçük çıktı.")
    return k


def _m_lojistik(ys, ps, opts):
    warnings = []
    pmax = max(ps)
    x0 = ys[0]
    if ps[-1] < ps[0]:
        warnings.append("Seri azalıyor; lojistik eğri azalan bir doyum eğrisi olarak kuruldu.")
    if opts.get("pearl_reed"):
        y0, y2 = ys[0], ys[-1]
        mid = (y0 + y2) / 2.0
        if mid not in ys:
            raise ProjectionError(
                "Pearl-Reed için ilk ve son yılın tam ortasında bir gözlem gerekli "
                f"(ör. {y0:g}, {mid:g}, {y2:g}).")
        p0, p1, p2 = ps[0], ps[ys.index(mid)], ps[-1]
        k = pearl_reed_k(p0, p1, p2)
        n = mid - y0
        a = math.log((k - p0) / p0)
        b = math.log(p0 * (k - p1) / (p1 * (k - p0))) / n
        text = f"K = {_fmt(k)} kişi (Pearl-Reed: {y0:g}, {mid:g}, {y2:g})"
        return (_logistic_predict(k, a, b, x0), {"K": k, "a": a, "b": b, "t0": x0,
                                                 "yontem": "pearl_reed"}, text, warnings)
    saturation = opts.get("saturation")
    if saturation:
        k = float(saturation)
        if k <= pmax:
            raise ProjectionError(
                f"Doyum nüfusu K ({_fmt(k)}) gözlenen en büyük nüfustan ({_fmt(pmax)}) büyük olmalı.")
        a, b = _logit_fit(ys, ps, k)
        text = f"K = {_fmt(k)} kişi (kullanıcı)"
        return (_logistic_predict(k, a, b, x0), {"K": k, "a": a, "b": b, "t0": x0,
                                                 "yontem": "kullanici"}, text, warnings)
    kmax_ratio = float(opts.get("k_search_max", 10.0))
    if kmax_ratio <= 1.001:
        raise ProjectionError("K arama üst sınırı (en büyük nüfusun katı) 1'den büyük olmalı.")
    lo_l, hi_l = math.log(pmax * 1.0005), math.log(pmax * kmax_ratio)
    steps = 400

    def sse_at(logk):
        k = math.exp(logk)
        a, b = _logit_fit(ys, ps, k)
        return _sse(ys, ps, _logistic_predict(k, a, b, x0))

    grid = [lo_l + (hi_l - lo_l) * i / steps for i in range(steps + 1)]
    values = [sse_at(g) for g in grid]
    best = min(range(len(grid)), key=lambda i: values[i])
    left = grid[max(0, best - 1)]
    right = grid[min(steps, best + 1)]
    # Altın oran araması ile inceltme
    gr = (math.sqrt(5.0) - 1.0) / 2.0
    c = right - gr * (right - left)
    d = left + gr * (right - left)
    fc, fd = sse_at(c), sse_at(d)
    for _ in range(80):
        if fc < fd:
            right, d, fd = d, c, fc
            c = right - gr * (right - left)
            fc = sse_at(c)
        else:
            left, c, fc = c, d, fd
            d = left + gr * (right - left)
            fd = sse_at(d)
    logk = (left + right) / 2.0
    if sse_at(logk) > values[best]:
        logk = grid[best]
    k = math.exp(logk)
    if best >= steps - 1:
        warnings.append(
            f"Lojistik: K arama üst sınırına ({kmax_ratio:g} × en büyük nüfus) dayandı; "
            "seri doyum göstermiyor (üstel büyüme gibi). K'yı kendiniz verin ya da başka "
            "yöntem seçin.")
    elif best <= 1:
        warnings.append(
            "Lojistik: K gözlenen en büyük nüfusa dayandı; seri doyuma ulaşmış ya da "
            "azalıyor görünüyor.")
    a, b = _logit_fit(ys, ps, k)
    text = f"K = {_fmt(k)} kişi (en küçük kareler)"
    return (_logistic_predict(k, a, b, x0), {"K": k, "a": a, "b": b, "t0": x0,
                                             "yontem": "kestirim"}, text, warnings)


_MODELS = {
    "aritmetik": _m_aritmetik,
    "geometrik": _m_geometrik,
    "iller_bankasi": _m_iller_bankasi,
    "regresyon": _m_regresyon,
    "polinom": _m_polinom,
    "lojistik": _m_lojistik,
}


def _fit(ys, ps, method, opts):
    need = MIN_POINTS[method]
    if len(ys) < need:
        raise ProjectionError(f"{METHOD_LABELS[method]} için en az {need} gözlem gerekli.")
    return _MODELS[method](ys, ps, opts)


# ---------------------------------------------------------------------------
# Sözleşme C1
# ---------------------------------------------------------------------------

def project_trend(years, populations, method, target_year, ib_lower=1.0, ib_upper=3.0,
                  saturation=None, pearl_reed=False, k_search_max=10.0):
    """Tek yöntemle projeksiyon.

    Döndürür: ``{method, label, target_year, value, series, fitted, r2,
    backtest_pct, params, params_text, warnings}``. ``series`` gözlenen ilk
    yıldan hedef yıla kadar her tam yıl için ``(yıl, kestirim)`` listesidir.
    Hatalı girdi ya da yetersiz gözlemde ``ProjectionError`` (ValueError) atar.
    """
    method = str(method or "").strip().lower()
    if method not in _MODELS:
        raise ProjectionError(
            f"Bilinmeyen yöntem: {method!r}. Geçerli yöntemler: {', '.join(METHODS)}.")
    ys, ps = validate_series(years, populations)
    target = _as_float(target_year, "Hedef yıl")
    opts = {"ib_lower": ib_lower, "ib_upper": ib_upper, "saturation": saturation,
            "pearl_reed": pearl_reed, "k_search_max": k_search_max}
    predict, params, text, warnings = _fit(ys, ps, method, opts)
    warnings = list(warnings)
    if target < ys[-1]:
        warnings.append(f"Hedef yıl ({target:g}) son gözlemden ({ys[-1]:g}) önce; değer "
                        "projeksiyon değil model kestirimidir.")
    value = predict(target)
    if value <= 0:
        warnings.append("Kestirilen nüfus sıfır ya da negatif; yöntem bu seri için uygun değil.")
    fitted = [predict(y) for y in ys]
    r2 = r_squared(ps, fitted)
    backtest = None
    if len(ys) - 1 >= MIN_POINTS[method] and len(ys) >= 3:
        sub_opts = dict(opts)
        try:
            sub_predict = _fit(ys[:-1], ps[:-1], method, sub_opts)[0]
        except (ProjectionError, ZeroDivisionError, OverflowError, ValueError):
            sub_predict = None
            warnings.append("Geri test yapılamadı: son gözlem çıkarılınca model kurulamıyor.")
        if sub_predict is not None:
            backtest = 100.0 * (sub_predict(ys[-1]) - ps[-1]) / ps[-1]
    first = int(math.floor(ys[0]))
    last = int(math.ceil(max(target, ys[-1])))
    series = [(float(y), predict(float(y))) for y in range(first, last + 1)]
    if float(target) != int(target):
        series.append((target, value))
    return {
        "method": method,
        "label": METHOD_LABELS[method],
        "target_year": target,
        "value": value,
        "series": series,
        "fitted": fitted,
        "r2": r2,
        "backtest_pct": backtest,
        "params": params,
        "params_text": text,
        "warnings": warnings,
    }


def project_all(years, populations, target_year, methods=None, **options):
    """Birden çok yöntem; kurulamayan yöntem ``error`` alanıyla döner (sessizce atlanmaz)."""
    validate_series(years, populations)
    out = []
    for method in (methods or METHODS):
        try:
            out.append(project_trend(years, populations, method, target_year, **options))
        except (ProjectionError, ZeroDivisionError, OverflowError) as exc:
            out.append({"method": method, "label": METHOD_LABELS.get(method, method),
                        "target_year": float(target_year), "value": None, "series": [],
                        "fitted": [], "r2": None, "backtest_pct": None, "params": {},
                        "params_text": "", "warnings": [], "error": str(exc)})
    return out


# ---------------------------------------------------------------------------
# Ekonomik taban göçü
# ---------------------------------------------------------------------------

def economic_base_migration(persons_per_worker, new_jobs=None, current_employment=None,
                            target_employment=None, basic_jobs=None, base_multiplier=1.0,
                            local_supply_jobs=0.0):
    """Yeni işlerden göçle gelecek nüfus.

    Yeni istihdam şu sırayla belirlenir: ``new_jobs`` verilmişse o; yoksa
    ``basic_jobs × base_multiplier`` (iktisadi temel çarpanı); yoksa
    ``target_employment − current_employment``. Yerel işgücüyle karşılanan
    iş (``local_supply_jobs``) düşülür.

        göç nüfusu = max(0, yeni iş − yerel karşılanan) × çalışan başına nüfus
    """
    ppw = _as_float(persons_per_worker, "Çalışan başına nüfus")
    if ppw <= 0:
        raise ProjectionError("Çalışan başına nüfus pozitif olmalı (ör. 2.8 kişi/çalışan).")
    warnings = []
    if new_jobs is not None:
        jobs = _as_float(new_jobs, "Yeni istihdam")
        source = "dogrudan"
    elif basic_jobs is not None:
        mult = _as_float(base_multiplier, "Taban çarpanı")
        if mult < 1.0:
            warnings.append("Taban çarpanı 1'den küçük; iktisadi temel kuramında çarpan ≥ 1'dir.")
        jobs = _as_float(basic_jobs, "Temel sektör yeni iş") * mult
        source = "taban_carpani"
    elif current_employment is not None and target_employment is not None:
        jobs = (_as_float(target_employment, "Hedef istihdam")
                - _as_float(current_employment, "Mevcut istihdam"))
        source = "istihdam_farki"
    else:
        raise ProjectionError("Yeni istihdam, temel sektör işi ya da mevcut/hedef istihdam verin.")
    local = max(0.0, _as_float(local_supply_jobs or 0.0, "Yerel karşılanan iş"))
    if jobs < 0:
        warnings.append("İstihdam azalıyor; göç nüfusu sıfır alındı (göç çıkışı modellenmedi).")
    migrant_jobs = max(0.0, jobs - local)
    return {
        "yeni_istihdam": jobs,
        "kaynak": source,
        "yerel_karsilanan": local,
        "goc_ile_karsilanan_is": migrant_jobs,
        "calisan_basina_nufus": ppw,
        "goc_nufusu": migrant_jobs * ppw,
        "warnings": warnings,
    }
