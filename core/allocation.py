# -*- coding: utf-8 -*-
"""Hedef nüfusun mahallelere (alt bölgelere) dağıtımı (saf Python).

Yöntemler
---------
``oransal``   Hedef nüfus, mevcut nüfus payıyla dağıtılır.
``bolge``     Artışın payı planlama bölgesine göre verilir (ör. gelişme aksı
              %75, kırsal %20, koruma %5); bölge içinde mevcut nüfusla orantılı
              (bölgede nüfus yoksa eşit) dağıtılır. Bölge adları ``norm_tr``
              ile eşleşir ("Kırsal" = "KIRSAL").
``kapasite``  Artış boş plan kapasitesiyle (kapasite − mevcut) orantılı
              dağıtılır; dolan mahalle kapasitede tutulur, artan pay diğerlerine
              yeniden dağıtılır. Hiçbir yere sığmayan nüfus "dağıtılamayan"
              olarak raporlanır.

Sonuçlar en büyük kalan yöntemiyle tam sayıya yuvarlanır: mahalle toplamı
(dağıtılamayan dışında) hedefe birebir eşittir. Satırlar anahtarla döner;
katmana geri yazım sırayla değil anahtarla yapılmalıdır.
"""
from __future__ import annotations

import math

import numpy as np

from .tire_constants import norm_tr

METHODS = ("oransal", "bolge", "kapasite")
METHOD_LABELS = {
    "oransal": "Oransal (mevcut nüfus payı)",
    "bolge": "Planlama bölgesi payı",
    "kapasite": "Kapasite sınırlı (taşan pay yeniden dağıtılır)",
}

# PLN3113 stüdyosunda kullanılan bölge payı ön ayarı (düzenlenebilir).
STUDIO_ZONE_SHARES = {
    "Kentsel gelişme aksı": 0.75,
    "Kırsal / çevre yerleşim": 0.20,
    "Tarihi merkez / koruma": 0.05,
}


class AllocationError(ValueError):
    """Dağıtım girdisi hatası (Türkçe ileti)."""


def largest_remainder(values, total, caps=None):
    """Negatif olmayan değerleri toplamı ``total`` olan tam sayılara yuvarlar.

    ``caps`` verilirse yukarı yuvarlama bir mahalleyi kapasitesinin üstüne
    çıkarmaz (mümkün olduğu sürece).
    """
    total = int(round(total))
    whole = [int(math.floor(v + 1e-9)) for v in values]
    rem = total - sum(whole)
    fracs = [v - fl for v, fl in zip(values, whole)]

    def room(i):
        if caps is None or caps[i] is None:
            return True
        return whole[i] + 1 <= caps[i] + 1e-9

    if rem > 0:
        order = sorted(range(len(values)), key=lambda i: (not room(i), -fracs[i], i))
        k = 0
        while rem > 0 and order:
            whole[order[k % len(order)]] += 1
            rem -= 1
            k += 1
    elif rem < 0:
        order = sorted(range(len(values)), key=lambda i: (fracs[i], i))
        order = [i for i in order if whole[i] > 0]
        k = 0
        while rem < 0 and order:
            i = order[k % len(order)]
            if whole[i] > 0:
                whole[i] -= 1
                rem += 1
            k += 1
    return whole


def _split_by_weight(weights, amount):
    """``amount`` miktarını ağırlıklarla orantılı böler; ağırlık toplamı sıfırsa eşit böler."""
    if not weights:
        return []
    w = np.asarray(weights, dtype=float)
    total_w = w.sum()
    fractions = w / total_w if total_w > 0 else np.full(w.size, 1.0 / w.size)
    return (fractions * amount).tolist()


def _capacity(pops, caps, growth, warnings):
    """Artışı boş kapasiteyle orantılı dağıtır (kapalı biçim).

    Boş kapasite r_i = max(0, kapasite_i − mevcut_i) (kapasite boşsa 0). Artış
    r_i ile orantılı verilince her mahalle aynı doluluk oranına ulaşır, bu yüzden
    hiçbir mahalle tek başına taşmaz: artış Σr'den küçükse ek_i = artış·r_i/Σr;
    değilse herkes kapasitesine dolar ve artış − Σr dağıtılamayan kalır.
    Yinelemeli yeniden dağıtımla aynı sonucu verir.
    """
    free = np.array([0.0 if c is None else max(0.0, c - p) for c, p in zip(caps, pops)])
    capacity_left = float(free.sum())
    placed = min(growth, capacity_left)
    extra = free * (placed / capacity_left) if capacity_left > 0 else np.zeros(free.size)
    unplaced = max(0.0, growth - placed)
    if unplaced > 0.5:
        warnings.append(f"Kapasite yetersiz: {unplaced:,.0f} kişi hiçbir mahalleye sığmadı "
                        "(dağıtılamayan).".replace(",", "."))
    return (np.asarray(pops, dtype=float) + extra).tolist(), unplaced


def parse_zone_shares(text):
    """'Gelişme=0.75; Kırsal=0.20; Koruma=5%' metnini {ad: pay} sözlüğüne çevirir."""
    out = {}
    for part in (text or "").replace("\n", ";").split(";"):
        part = part.strip()
        if not part:
            continue
        if "=" not in part and ":" not in part:
            raise AllocationError(f"Bölge payı 'ad=pay' biçiminde olmalı: {part!r}")
        sep = "=" if "=" in part else ":"
        name, val = part.rsplit(sep, 1)
        val = val.strip().replace(",", ".")
        pct = val.endswith("%")
        try:
            share = float(val.rstrip("%").strip())
        except ValueError:
            raise AllocationError(f"Bölge payı sayı olmalı: {part!r}") from None
        if pct or share > 1.0:
            share /= 100.0
        if share < 0:
            raise AllocationError(f"Bölge payı negatif olamaz: {part!r}")
        out[name.strip()] = share
    return out


def allocate(keys, populations, target, method="oransal", zones=None, zone_shares=None,
             capacities=None):
    """Hedef nüfusu dağıtır.

    Döndürür: ``{rows, by_key, total, unallocated, warnings, null_population,
    null_capacity}``; her satır ``{anahtar, mevcut, hedef, hedef_ham,
    net_artis, artis_yuzde, bolge, kapasite}``.
    """
    method = str(method or "oransal").strip().lower()
    if method not in METHODS:
        raise AllocationError(f"Bilinmeyen dağıtım yöntemi: {method!r}.")
    keys = list(keys)
    n = len(keys)
    if n == 0:
        raise AllocationError("Dağıtılacak mahalle yok.")
    seen = set()
    for k in keys:
        if k is None or str(k).strip() == "":
            raise AllocationError("Anahtar alanında boş değer var; her mahallenin anahtarı olmalı.")
        if k in seen:
            raise AllocationError(f"Anahtar tekrar ediyor: {k!r}. Anahtar alanı benzersiz olmalı.")
        seen.add(k)
    populations = list(populations)
    if len(populations) != n:
        raise AllocationError("Anahtar ve nüfus listeleri aynı uzunlukta olmalı.")
    try:
        target = float(target)
    except (TypeError, ValueError):
        raise AllocationError("Hedef nüfus sayı olmalı.") from None
    if target < 0:
        raise AllocationError("Hedef nüfus negatif olamaz.")
    warnings = []
    null_pop = 0
    pops = []
    for p in populations:
        try:
            v = float(p)
            if math.isnan(v):
                raise ValueError
        except (TypeError, ValueError):
            null_pop += 1
            v = 0.0
        if v < 0:
            raise AllocationError("Mevcut nüfus negatif olamaz.")
        pops.append(v)
    if null_pop:
        warnings.append(f"{null_pop} mahallede nüfus boş; 0 kabul edildi.")
    current = sum(pops)
    growth = target - current
    unallocated = 0.0  # kapasite yönteminde doldurulur
    caps = None
    null_cap = 0
    zones_out = [None] * n

    if growth < 0 and method != "oransal":
        warnings.append("Hedef nüfus mevcut toplamdan küçük; küçülme oransal dağıtıldı "
                        "(bölge payı ve kapasite yalnız artışa uygulanır).")
    if method == "oransal" or growth < 0:
        if current <= 0:
            warnings.append("Mevcut nüfus toplamı sıfır; hedef eşit dağıtıldı.")
        values = _split_by_weight(pops, target)
    elif method == "bolge":
        if zones is None or len(zones) != n:
            raise AllocationError("Bölge yöntemi için her mahallenin bölgesi verilmeli.")
        shares_in = dict(zone_shares or {})
        if not shares_in:
            raise AllocationError("Bölge yöntemi için bölge payları verilmeli.")
        norm_shares = {}
        for name, share in shares_in.items():
            norm_shares[norm_tr(str(name))] = norm_shares.get(norm_tr(str(name)), 0.0) + float(share)
        zone_keys = [norm_tr(str(z)) if z is not None else "" for z in zones]
        zones_out = list(zones)
        present = sorted(set(zone_keys))
        unknown = [z for z in present if z not in norm_shares]
        if unknown:
            cnt = sum(1 for z in zone_keys if z in unknown)
            warnings.append(f"{cnt} mahallenin bölgesi pay tablosunda yok "
                            f"({', '.join(z or '(boş)' for z in unknown)}); bu mahallelere artış "
                            "verilmedi.")
        empty = [z for z in norm_shares if z not in present]
        if empty:
            warnings.append(f"Pay verilen ama mahallesi olmayan bölge(ler): {', '.join(empty)}; "
                            "payları diğer bölgelere oransal aktarıldı.")
        used = {z: norm_shares[z] for z in present if z in norm_shares}
        tot_share = sum(used.values())
        if tot_share <= 0:
            raise AllocationError("Mahallesi olan bölgelerin pay toplamı sıfır.")
        if abs(sum(norm_shares.values()) - 1.0) > 1e-6:
            warnings.append(f"Bölge payları toplamı {sum(norm_shares.values()):.3f}; "
                            "1'e ölçeklendi.")
        values = list(pops)
        for z, share in used.items():
            idx = [i for i in range(n) if zone_keys[i] == z]
            for i, add in zip(idx, _split_by_weight([pops[i] for i in idx], growth * share / tot_share)):
                values[i] += add
    else:
        if capacities is None or len(capacities) != n:
            raise AllocationError("Kapasite yöntemi için her mahallenin kapasitesi verilmeli.")
        caps = []
        over = 0
        for c, p in zip(capacities, pops):
            try:
                v = float(c)
                if math.isnan(v):
                    raise ValueError
            except (TypeError, ValueError):
                null_cap += 1
                v = None
            if v is not None and v < p:
                over += 1
            caps.append(v)
        if null_cap:
            warnings.append(f"{null_cap} mahallede kapasite boş; bu mahallelere artış verilmedi.")
        if over:
            warnings.append(f"{over} mahallede mevcut nüfus kapasiteyi aşıyor; artış verilmedi.")
        values, unallocated = _capacity(pops, caps, growth, warnings)

    alloc_total = target - unallocated
    ints = largest_remainder(values, alloc_total,
                             caps=[None if c is None else max(c, p) for c, p in zip(caps, pops)]
                             if caps else None)
    rows = [
        {
            "anahtar": key,
            "mevcut": current_i,
            "hedef": target_i,
            "hedef_ham": raw_i,
            "net_artis": target_i - current_i,
            "artis_yuzde": 100.0 * (target_i / current_i - 1.0) if current_i > 0 else None,
            "bolge": zone_i,
            "kapasite": caps[i] if caps else None,
        }
        for i, (key, current_i, target_i, raw_i, zone_i)
        in enumerate(zip(keys, pops, ints, values, zones_out))
    ]
    return {
        "rows": rows,
        "by_key": {r["anahtar"]: r for r in rows},
        "total": sum(ints),
        "unallocated": unallocated,
        "warnings": warnings,
        "null_population": null_pop,
        "null_capacity": null_cap,
    }
