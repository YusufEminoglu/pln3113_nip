# -*- coding: utf-8 -*-
"""Tire NİP ve Kentsel Analiz Modülü: Standartlar, Yoğunluklar ve Parametreler.

DEÜ Mimarlık Fakültesi Şehir ve Bölge Planlama Bölümü
PLN3113 Şehir Planlama Projesi III - Tire Stüdyosu
"""
from __future__ import annotations

import re

# =====================================================================
# 1. TİRE NÜFUS VE PROJEKSİYON REFERANS VERİLERİ (GÖSTERGE PANELİ)
# =====================================================================
TIRE_POPULATION_BENCHMARKS = {
    "plan_1997_die": {
        "kapsam": "1997 Plan Raporu (1990 DİE Verisi)",
        "merkez": 37855,
        "kirsal": 39459,  # 65 köy dökümü
        "ilce": 77314,
        "kaynak": "1997 Onaylı Tire 1/5000 NİP Raporu (1990 DİE Sayımı)"
    },
    "hedef_2015_model": {
        "kapsam": "2015 Plan Projeksiyonu (Hedef)",
        "merkez": 53629,
        "kirsal": 46711,  # Üst Değerli Model projeksiyonu (100.340 - 53.629)
        "ilce": 100340,
        "kaynak": "1997 Planı Üst Değerli Model (Regresyon) Projeksiyonu"
    },
    "tuik_2015_kesin": {
        "kapsam": "2015 TÜİK ADNKS (Gerçekleşen)",
        "merkez": 57069,  # ~57.069 (Merkez mahalleler toplamı)
        "kirsal": 25033,  # ~25.033 (Kırsal mahalleler toplamı)
        "ilce": 82102,
        "kaynak": "2015 TÜİK Resmi ADNKS (Merkez Mahalleler Toplamı)"
    },
    "tuik_2026_guncel": {
        "kapsam": "Güncel TÜİK ADNKS (2025 Kütüğü / 2026 İlanı)",
        "merkez": 61738,  # ~61.738 (Merkez mahalleler toplamı)
        "kirsal": 25833,  # ~25.833 (Kırsal mahalleler toplamı)
        "ilce": 87571,    # 31 Aralık 2025 referanslı (Şubat 2026 ilanı)
        "kaynak": "Resmi TÜİK ADNKS Güncel İstatistikleri"
    }
}

# =====================================================================
# 2. NİP KONUT BRÜT YOĞUNLUK ARALIKLARI (KİŞİ / HEKTAR)
# =====================================================================
# Standart Tip Anahtarları: (ALT_SNR, UST_SNR, Kategori)
NIP_DENSITY_LOOKUP = {
    "GELISME_COK_YUKSEK": {"alt": 401, "ust": 600, "label": "Gelişme Konut Alanı (Çok Yüksek)", "pattern": r"GEL[İIİ]ŞME.*(ÇOK\s*Y[ÜU]KSEK|401\s*-\s*600)"},
    "GELISME_YUKSEK":     {"alt": 251, "ust": 400, "label": "Gelişme Konut Alanı (Yüksek)",     "pattern": r"GEL[İIİ]ŞME.*(Y[ÜU]KSEK|251\s*-\s*400)"},
    "GELISME_ORTA":       {"alt": 121, "ust": 250, "label": "Gelişme Konut Alanı (Orta)",       "pattern": r"GEL[İIİ]ŞME.*(ORTA|121\s*-\s*250)"},
    "GELISME_DUSUK":      {"alt": 51,  "ust": 120, "label": "Gelişme Konut Alanı (Düşük)",      "pattern": r"GEL[İIİ]ŞME.*(D[ÜU]Ş[ÜU]K|51\s*-\s*120)"},
    "GELISME_SEYREK":     {"alt": 25,  "ust": 50,  "label": "Gelişme Konut Alanı (Seyrek)",     "pattern": r"GEL[İIİ]ŞME.*(SEYREK|25\s*-\s*50)"},

    "MEVCUT_COK_YUKSEK":  {"alt": 601, "ust": 900, "label": "Mevcut Konut Alanı (Çok Yüksek)",  "pattern": r"MEVCUT.*(ÇOK\s*Y[ÜU]KSEK|601\s*-\s*900)"},
    "MEVCUT_YUKSEK":      {"alt": 301, "ust": 600, "label": "Mevcut Konut Alanı (Yüksek)",      "pattern": r"MEVCUT.*(Y[ÜU]KSEK|301\s*-\s*600)"},
    "MEVCUT_ORTA":        {"alt": 151, "ust": 300, "label": "Mevcut Konut Alanı (Orta)",        "pattern": r"MEVCUT.*(ORTA|151\s*-\s*300)"},
    "MEVCUT_DUSUK":       {"alt": 51,  "ust": 150, "label": "Mevcut Konut Alanı (Düşük)",       "pattern": r"MEVCUT.*(D[ÜU]Ş[ÜU]K|51\s*-\s*150)"},
    "MEVCUT_SEYREK":      {"alt": 25,  "ust": 50,  "label": "Mevcut Konut Alanı (Seyrek)",      "pattern": r"MEVCUT.*(SEYREK|25\s*-\s*50)"},
}

def resolve_nip_density(fonk_str: str) -> tuple[float | None, float | None, str]:
    """Verilen fonksiyon metninden (örn. Ort_Detay) alt ve üst sınırları bulur."""
    if not fonk_str:
        return None, None, "TANIMSIZ"
    
    clean = fonk_str.strip().upper()
    # Türkçe I/İ dönüşüm toleransı
    clean = clean.replace("İ", "I").replace("ı", "I").replace("Ğ", "G").replace("Ü", "U").replace("Ş", "S").replace("Ö", "O")

    # 1. Karma Kullanım Kontrolü
    if any(k in clean for k in ["TICARET - KONUT", "TICARET-KONUT", "TICARET TURIZM KONUT", "TICARET-TURIZM- KONUT", "TICARET VE KONUT"]):
        return None, None, "KARMA_KONUT"

    # 2. Konut Yoğunluk Kontrolleri (Öncelikli Çok Yüksek, Yüksek, vb.)
    is_gelisme = "GELISME" in clean
    is_meskun = ("MEVCUT" in clean) or ("MESKUN" in clean)

    if is_gelisme:
        if "COK YUKSEK" in clean or "401" in clean:
            return 401.0, 600.0, "GELİŞME KONUT ALANI (ÇOK YÜKSEK)"
        elif "YUKSEK" in clean or "251" in clean:
            return 251.0, 400.0, "GELİŞME KONUT ALANI (YÜKSEK)"
        elif "ORTA" in clean or "121" in clean:
            return 121.0, 250.0, "GELİŞME KONUT ALANI (ORTA)"
        elif "DUSUK" in clean or "51" in clean:
            return 51.0, 120.0, "GELİŞME KONUT ALANI (DÜŞÜK)"
        elif "SEYREK" in clean or "25" in clean:
            return 25.0, 50.0, "GELİŞME KONUT ALANI (SEYREK)"
        else:
            # Genel gelişme varsayılan orta yoğunluk
            return 121.0, 250.0, "GELİŞME KONUT ALANI (ORTA)"

    if is_meskun:
        if "COK YUKSEK" in clean or "601" in clean:
            return 601.0, 900.0, "MEVCUT KONUT ALANI (ÇOK YÜKSEK)"
        elif "YUKSEK" in clean or "301" in clean:
            return 301.0, 600.0, "MEVCUT KONUT ALANI (YÜKSEK)"
        elif "ORTA" in clean or "151" in clean:
            return 151.0, 300.0, "MEVCUT KONUT ALANI (ORTA)"
        elif "DUSUK" in clean or "51" in clean:
            return 51.0, 150.0, "MEVCUT KONUT ALANI (DÜŞÜK)"
        elif "SEYREK" in clean or "25" in clean:
            return 25.0, 50.0, "MEVCUT KONUT ALANI (SEYREK)"
        else:
            return 151.0, 300.0, "MEVCUT KONUT ALANI (ORTA)"

    # Diğer kullanımlar nüfus dışıdır
    return 0.0, 0.0, "DONATI_VEYA_CALISMA"

# =====================================================================
# 3. MEKÂNSAL PLANLAR YAPIM YÖNETMELİĞİ (MPYY EK-2) DONATI GRUPLARI
# =====================================================================
MPYY_DONATI_STANDARTLARI = {
    "EGITIM": {
        "adi": "Eğitim Tesisleri Alanı",
        "standart_m2_kisi": 6.5,
        "anahtarlar": ["EĞİTİM", "EGITIM", "OKUL", "LİSE", "İLKOKUL", "ORTAOKUL", "ANAOKULU"]
    },
    "SAGLIK": {
        "adi": "Sağlık Tesisleri Alanı",
        "standart_m2_kisi": 1.5,
        "anahtarlar": ["SAĞLIK", "SAGLIK", "HASTANE", "AİLE SAĞLIĞI", "POLİKLİNİK", "ÖZEL SAĞLIK"]
    },
    "SOSYAL_KULTUREL": {
        "adi": "Sosyal ve Kültürel Tesisler",
        "standart_m2_kisi": 1.0,
        "anahtarlar": ["SOSYAL TESİS", "KÜLTÜREL TESİS", "KÜLTÜR MERKEZİ", "KREŞ", "YURT", "SOSYAL ALTYAPI"]
    },
    "YESIL_ALAN": {
        "adi": "Açık ve Yeşil Alanlar (Park/Rekreasyon)",
        "standart_m2_kisi": 10.0,
        "anahtarlar": ["PARK VE YEŞİL", "PARK VE YESIL", "PARK ALANI", "MİLLET BAHÇESİ", "MILLET BAHCESI", "MESİRE", "MESIRE", "SEMT SPOR", "SPOR ALANI", "PASİF YEŞİL", "PASIF YESIL", "REKREASYON"]
    },
    "TEKNIK_ALTYAPI": {
        "adi": "Teknik Altyapı Alanları",
        "standart_m2_kisi": 1.25,
        "anahtarlar": ["TEKNİK ALTYAPI", "TEKNIK ALTYAPI", "TRAFO", "ARITMA", "TERFİ", "İÇME SUYU TESİSİ", "ICME SUYU"]
    },
    "IBADET": {
        "adi": "İbadet Alanları",
        "standart_m2_kisi": 0.5,
        "anahtarlar": ["İBADET", "IBADET", "CAMİ", "CAMI", "MESCİT", "MESCIT"]
    }
}

def identify_facility_category(fonk_str: str) -> str | None:
    """Verilen fonksiyonun hangi MPYY Ek-2 donatı grubuna girdiğini döndürür."""
    if not fonk_str:
        return None
    upper = fonk_str.strip().upper()
    # Otopark ve makine parkını yeşil alandan kesinlikle koru
    if "OTOPARK" in upper or "MAKİNE PARKI" in upper or "MAKINE PARKI" in upper:
        return None

    for cat_id, info in MPYY_DONATI_STANDARTLARI.items():
        if any(k in upper for k in info["anahtarlar"]):
            return cat_id
    
    # Yalın 'PARK' kelimesi kontrolü
    if "PARK" in upper and "OTOPARK" not in upper and "MAKİNE" not in upper:
        return "YESIL_ALAN"

    return None

# =====================================================================
# 4. İSTİHDAM KAPASİTESİ MODELİ PARAMETRELERİ (TİRE ÖLÇEĞİ)
# =====================================================================
# (m2_per_worker, verimlilik_katsayisi)
EMPLOYMENT_RATES = {
    "TİCARET ALANI": (30.0, 0.75),
    "TİCARET - KONUT ALANI": (40.0, 0.30),
    "TİCARET - TURİZM ALANI": (45.0, 0.60),
    "MERKEZİ İŞ ALANI (MİA)": (25.0, 0.85),
    "SANAYİ ALANI": (90.0, 0.50),
    "ORGANİZE SANAYİ BÖLGESİ": (95.0, 0.55),
    "KÜÇÜK SANAYİ ALANI": (50.0, 0.60),
    "KONUT DIŞI KENTSEL ÇALIŞMA ALANI": (60.0, 0.55),
    "DEPOLAMA ALANI": (150.0, 0.40),
    "AKARYAKIT VE SERVİS İSTASYONU ALANI": (100.0, 0.20),
    "TIR, KAMYON, MAKİNE PARKI VE GARAJ ALANI": (200.0, 0.10),
    "TURİZM ALANI": (60.0, 0.45),
    "TERMİNAL (OTOGAR)": (100.0, 0.30),
    "EĞİTİM ALANI": (70.0, 0.35),
    "SAĞLIK ALANI": (60.0, 0.45),
    "ÖZEL SAĞLIK ALANI": (50.0, 0.50),
    "BELEDİYE HİZMET ALANI": (45.0, 0.50),
    "KAMU HİZMET ALANI": (45.0, 0.50),
    "KÜLTÜREL TESİS ALANI": (60.0, 0.40),
    "SOSYAL TESİS ALANI": (70.0, 0.30),
    "İBADET ALANI": (250.0, 0.10),
    "SPOR ALANI": (300.0, 0.15),
    "PAZAR ALANI": (100.0, 0.20)
}

# =====================================================================
# 5. YOLCULUK ÜRETİM MODELİ (100 m2 ALAN BAŞINA GÜNLÜK ÇEKİM)
# =====================================================================
# (gunluk_arac_pau, gunluk_yaya)
TRIP_GENERATION_RATES = {
    "GELİŞME KONUT ALANI (ÇOK YÜKSEK)": (2.2, 5.5),
    "GELİŞME KONUT ALANI (YÜKSEK)": (2.0, 5.0),
    "GELİŞME KONUT ALANI (ORTA)": (2.5, 4.0),
    "GELİŞME KONUT ALANI (DÜŞÜK)": (3.0, 3.0),
    "GELİŞME KONUT ALANI (SEYREK)": (3.5, 2.0),
    "MEVCUT KONUT ALANI (ÇOK YÜKSEK)": (2.2, 6.0),
    "MEVCUT KONUT ALANI (YÜKSEK)": (2.0, 5.5),
    "MEVCUT KONUT ALANI (ORTA)": (2.5, 4.5),
    "MEVCUT KONUT ALANI (DÜŞÜK)": (3.0, 3.5),
    "MEVCUT KONUT ALANI (SEYREK)": (3.5, 2.0),
    "TİCARET ALANI": (15.0, 12.0),
    "MERKEZİ İŞ ALANI (MİA)": (20.0, 15.0),
    "TİCARET - KONUT ALANI": (8.0, 8.0),
    "PAZAR ALANI": (25.0, 35.0),
    "KAMU HİZMET ALANI": (8.0, 5.0),
    "BELEDİYE HİZMET ALANI": (10.0, 6.0),
    "TURİZM ALANI": (4.0, 5.0),
    "TİCARET - TURİZM ALANI": (10.0, 10.0),
    "GÜNÜBİRLİK TESİS ALANI": (5.0, 15.0),
    "SANAYİ ALANI": (2.5, 0.8),
    "ORGANİZE SANAYİ BÖLGESİ": (2.8, 0.9),
    "KÜÇÜK SANAYİ ALANI": (5.0, 1.5),
    "KONUT DIŞI KENTSEL ÇALIŞMA ALANI": (4.0, 2.0),
    "DEPOLAMA ALANI": (1.2, 0.3),
    "EĞİTİM ALANI": (5.0, 10.0),
    "SAĞLIK ALANI": (10.0, 8.0),
    "ÖZEL SAĞLIK ALANI": (12.0, 8.0),
    "İBADET ALANI": (1.0, 3.0),
    "KÜLTÜREL TESİS ALANI": (3.0, 5.0),
    "SOSYAL TESİS ALANI": (3.0, 5.0),
    "SPOR ALANI": (2.0, 4.0),
    "SEMT SPOR ALANI": (1.0, 8.0),
    "PARK VE YEŞİL ALAN": (0.5, 3.0),
    "MİLLET BAHÇESİ": (0.5, 3.0),
    "REKREASYON ALANI": (1.0, 4.0),
    "MEZARLIK ALANI": (0.5, 0.5),
    "AKARYAKIT VE SERVİS İSTASYONU ALANI": (35.0, 1.0),
    "TERMİNAL (OTOGAR)": (20.0, 20.0),
    "GENEL OTOPARK ALANI": (15.0, 2.0),
    "TEKNİK ALTYAPI ALANI": (0.5, 0.1)
}

def norm_tr(text: str) -> str:
    """Türkçe karakterleri ve boşlukları tek bir standart forma sokar."""
    if not text:
        return ""
    t = text.strip()
    for o, n in [
        ("İ", "I"), ("i", "I"), ("ı", "I"),
        ("Ğ", "G"), ("ğ", "G"),
        ("Ü", "U"), ("ü", "U"),
        ("Ş", "S"), ("ş", "S"),
        ("Ö", "O"), ("ö", "O"),
        ("Ç", "C"), ("ç", "C")
    ]:
        t = t.replace(o, n)
    return t.upper()

# Standart Normalleştirilmiş Anahtarlar
CANONICAL_EMPLOYMENT_RATES = {
    "TICARET": (30.0, 0.75),
    "SANAYI": (90.0, 0.50),
    "ORGANIZE SANAYI": (95.0, 0.55),
    "KUCUK SANAYI": (50.0, 0.60),
    "KONUT DISI": (60.0, 0.55),
    "DEPOLAMA": (150.0, 0.40),
    "AKARYAKIT": (100.0, 0.20),
    "OTOPARK": (500.0, 0.05),
    "TURIZM": (60.0, 0.45),
    "OTEL": (60.0, 0.45),
    "PANSIYON": (60.0, 0.45),
    "KONAKLAMA": (60.0, 0.45),
    "TERMINAL": (100.0, 0.30),
    "OTOGAR": (100.0, 0.30),
    "EGITIM": (70.0, 0.35),
    "ILKOKUL": (70.0, 0.35),
    "ORTAOKUL": (70.0, 0.35),
    "LISE": (70.0, 0.35),
    "OKUL": (70.0, 0.35),
    "SAGLIK": (60.0, 0.45),
    "HASTANE": (50.0, 0.55),
    "ASM": (60.0, 0.45),
    "BELEDIYE": (45.0, 0.50),
    "BHA": (45.0, 0.50),
    "KAMU": (45.0, 0.50),
    "RESMI": (45.0, 0.50),
    "SOSYAL": (70.0, 0.30),
    "KULTUREL": (60.0, 0.40),
    "MUZE": (100.0, 0.20),
    "IBADET": (250.0, 0.10),
    "CAMI": (250.0, 0.10),
    "PAZAR": (100.0, 0.20),
    "KARMA": (40.0, 0.35)
}

def get_employment_for_function(fonk_str: str, alan_m2: float, resolved_cat: str = "") -> int:
    """Fonksiyon adı ve alanına göre tahmini istihdam sayısını hesaplar."""
    if not fonk_str or alan_m2 <= 0:
        return 0
    fn = norm_tr(fonk_str)
    cat_fn = norm_tr(resolved_cat) if resolved_cat else ""

    # 1. Kanonik sözlük üzerinden hızlı arama
    for key, (std_m2, eff) in CANONICAL_EMPLOYMENT_RATES.items():
        if key in fn or (cat_fn and key in cat_fn):
            return max(0, int((alan_m2 * eff) / std_m2))

    # 2. Yedek sözlük
    for key, (std_m2, eff) in EMPLOYMENT_RATES.items():
        k_norm = norm_tr(key)
        if k_norm in fn or (cat_fn and k_norm in cat_fn):
            return max(0, int((alan_m2 * eff) / std_m2))
    return 0

def get_trips_for_function(fonk_str: str, alan_m2: float, resolved_cat: str = "") -> tuple[float, float]:
    """100 m2 başına günlük araç ve yaya yolculuğunu hesaplar."""
    if not fonk_str or alan_m2 <= 0:
        return 0.0, 0.0
    fn = norm_tr(fonk_str)
    cat_fn = norm_tr(resolved_cat) if resolved_cat else ""

    for key, (arac, yaya) in TRIP_GENERATION_RATES.items():
        k_norm = norm_tr(key)
        if k_norm in fn or (cat_fn and k_norm in cat_fn):
            units = alan_m2 / 100.0
            return round(units * arac, 1), round(units * yaya, 1)

    # Genel varsayılan konut/donatı çekimi
    units = alan_m2 / 100.0
    if "KONUT" in fn or "KONUT" in cat_fn:
        return round(units * 2.5, 1), round(units * 4.0, 1)
    if "TICARET" in fn or "SANAYI" in fn:
        return round(units * 10.0, 1), round(units * 8.0, 1)
    return round(units * 1.0, 1), round(units * 2.0, 1)


def get_default_employment_rule(fonk_str: str) -> tuple[bool, float, float]:
    """Fonksiyon için varsayılan istihdam dahil/hariç durumu ve katsayılarını döndürür.
    Dönüş: (dahil_mi, m2_per_worker, verimlilik)
    """
    if not fonk_str:
        return False, 0.0, 0.0
    fn = norm_tr(fonk_str)

    # 1. Kanonik sözlük
    for key, (std_m2, eff) in CANONICAL_EMPLOYMENT_RATES.items():
        if key in fn:
            return True, std_m2, eff

    # 2. Detaylı sözlük
    for key, (std_m2, eff) in EMPLOYMENT_RATES.items():
        if norm_tr(key) in fn:
            return True, std_m2, eff

    return False, 0.0, 0.0


def get_default_trip_rule(fonk_str: str) -> tuple[bool, bool, float, float]:
    """Fonksiyon için varsayılan araç ve yaya yolculuk dahil/hariç ve katsayılarını döndürür.
    Dönüş: (arac_dahil, yaya_dahil, rate_arac, rate_yaya)
    """
    if not fonk_str:
        return False, False, 0.0, 0.0
    fn = norm_tr(fonk_str)

    # Tarım, mera, orman, sit, su vb. koruma alanları varsayılan olarak yolculuk dışıdır
    if any(k in fn for k in ["TARIM", "ORMAN", "SIT", "MERA", "SU YUZEYI", "DERE", "BARAJ", "GOL"]):
        return False, False, 0.0, 0.0

    for key, (arac, yaya) in TRIP_GENERATION_RATES.items():
        if norm_tr(key) in fn:
            return True, True, arac, yaya

    if "KONUT" in fn:
        return True, True, 2.5, 4.0
    if "TICARET" in fn or "SANAYI" in fn:
        return True, True, 10.0, 8.0
    return True, True, 1.0, 2.0

