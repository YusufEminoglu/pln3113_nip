# -*- coding: utf-8 -*-
"""Tire NİP ve Kentsel Analiz Modülü: Standartlar, Yoğunluklar ve Parametreler.

PLN3113 Şehir Planlama Projesi III - Tire Stüdyosu
"""
from __future__ import annotations

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

def clean_key(text: str) -> str:
    """Metni arama ve eşleme için küçük harfe ve noktalama/boşluksuz forma çevirir."""
    if not text:
        return ""
    t = norm_tr(text).lower()
    for ch in [" ", "_", "-", "(", ")", "/", "+", ".", ",", ":"]:
        t = t.replace(ch, "")
    return t

# =====================================================================
# TUCBS & FİZİKİ MEVCUT DURUM ARAZİ KULLANIM STANDART SÖZLÜĞÜ
# (std_fonksiyon, alt_snr, ust_snr, kategori, dop_durumu, dop_turu, donati, emp_dahil, std_m2, eff, trip_arac, trip_yaya)
# =====================================================================
_TUCBS_RAW_MAPPING = {
    # 1. Konut Alanları (Mevcut Durum Yoğunluk Aralıkları)
    "dusukyogunluktakonutalani": ("Mevcut Konut Alanı (Düşük)", 51.0, 150.0, "MEVCUT KONUT ALANI (DÜŞÜK)", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, False, 0.0, 0.0, 2.5, 4.0),
    "konutdusukyogunluk": ("Mevcut Konut Alanı (Düşük)", 51.0, 150.0, "MEVCUT KONUT ALANI (DÜŞÜK)", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, False, 0.0, 0.0, 2.5, 4.0),
    "konut (düşük yoğunluk)": ("Mevcut Konut Alanı (Düşük)", 51.0, 150.0, "MEVCUT KONUT ALANI (DÜŞÜK)", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, False, 0.0, 0.0, 2.5, 4.0),
    
    "ortayogunluktakonutalani": ("Mevcut Konut Alanı (Orta)", 151.0, 300.0, "MEVCUT KONUT ALANI (ORTA)", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, False, 0.0, 0.0, 2.5, 4.5),
    "konutortayogunluk": ("Mevcut Konut Alanı (Orta)", 151.0, 300.0, "MEVCUT KONUT ALANI (ORTA)", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, False, 0.0, 0.0, 2.5, 4.5),
    "konut (orta yoğunluk)": ("Mevcut Konut Alanı (Orta)", 151.0, 300.0, "MEVCUT KONUT ALANI (ORTA)", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, False, 0.0, 0.0, 2.5, 4.5),

    "yuksekyogunluktakonutalani": ("Mevcut Konut Alanı (Yüksek)", 301.0, 600.0, "MEVCUT KONUT ALANI (YÜKSEK)", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, False, 0.0, 0.0, 2.0, 5.5),
    "konutyuksekyogunluk": ("Mevcut Konut Alanı (Yüksek)", 301.0, 600.0, "MEVCUT KONUT ALANI (YÜKSEK)", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, False, 0.0, 0.0, 2.0, 5.5),
    "konut (yüksek yoğunluk)": ("Mevcut Konut Alanı (Yüksek)", 301.0, 600.0, "MEVCUT KONUT ALANI (YÜKSEK)", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, False, 0.0, 0.0, 2.0, 5.5),

    "cokyuksekyogunluktakonutalani": ("Mevcut Konut Alanı (Çok Yüksek)", 601.0, 900.0, "MEVCUT KONUT ALANI (ÇOK YÜKSEK)", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, False, 0.0, 0.0, 2.2, 6.0),
    "konut (çok yüksek yoğunluk)": ("Mevcut Konut Alanı (Çok Yüksek)", 601.0, 900.0, "MEVCUT KONUT ALANI (ÇOK YÜKSEK)", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, False, 0.0, 0.0, 2.2, 6.0),

    "seyrekyogunluktakonutalani": ("Mevcut Konut Alanı (Seyrek)", 25.0, 50.0, "MEVCUT KONUT ALANI (SEYREK)", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, False, 0.0, 0.0, 3.5, 2.0),
    "konut (seyrek / kırsal)": ("Mevcut Konut Alanı (Seyrek)", 25.0, 50.0, "MEVCUT KONUT ALANI (SEYREK)", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, False, 0.0, 0.0, 3.5, 2.0),
    "kırsal gelişme alanı": ("Mevcut Konut Alanı (Seyrek)", 25.0, 50.0, "MEVCUT KONUT ALANI (SEYREK)", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, False, 0.0, 0.0, 3.5, 2.0),

    # 2. Karma Kullanımlar (Ticaret + Konut)
    "karmakullanimalanlari": ("Karma Kullanım (Ticaret + Konut)", None, None, "KARMA_KONUT", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, True, 40.0, 0.35, 8.0, 8.0),
    "karmaticaretkonut": ("Karma Kullanım (Ticaret + Konut)", None, None, "KARMA_KONUT", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, True, 40.0, 0.35, 8.0, 8.0),
    "karma kullanım (ticaret + konut)": ("Karma Kullanım (Ticaret + Konut)", None, None, "KARMA_KONUT", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, True, 40.0, 0.35, 8.0, 8.0),

    # 3. Ticaret ve Çalışma Alanları
    "ticaretalani": ("Ticaret Alanı", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, True, 30.0, 0.75, 15.0, 12.0),
    "ticaretmerkezi": ("Ticaret Alanı (Çarşı / İş Merkezi)", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, True, 25.0, 0.85, 20.0, 15.0),
    "digerticaretalanlari": ("Ticaret Alanı (Tali / Hizmet)", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, True, 35.0, 0.70, 12.0, 10.0),
    "ticaret alanı (çarşı / iş merkezi)": ("Ticaret Alanı (Çarşı / İş Merkezi)", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, True, 25.0, 0.85, 20.0, 15.0),
    "ticaret alanı (tali / hizmet)": ("Ticaret Alanı (Tali / Hizmet)", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, True, 35.0, 0.70, 12.0, 10.0),

    # 4. Sanayi, İmalat, Depolama ve Akaryakıt
    "sanayialani": ("Sanayi Alanı", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, True, 90.0, 0.50, 2.5, 0.8),
    "sanayi alanı": ("Sanayi Alanı", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, True, 90.0, 0.50, 2.5, 0.8),
    "sanayi / imalathane": ("Sanayi Alanı", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, True, 80.0, 0.50, 3.0, 1.0),
    "organizesanayibolgesi": ("Organize Sanayi Bölgesi (OSB)", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, True, 95.0, 0.55, 2.8, 0.9),
    "organize sanayi bölgesi (osb)": ("Organize Sanayi Bölgesi (OSB)", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, True, 95.0, 0.55, 2.8, 0.9),
    "kucuksanayialani": ("Küçük Sanayi Sitesi", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, True, 50.0, 0.60, 5.0, 1.5),
    "küçük sanayi sitesi": ("Küçük Sanayi Sitesi", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, True, 50.0, 0.60, 5.0, 1.5),
    "imalathanetesisalani": ("İmalathane / Atölye", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, True, 50.0, 0.60, 5.0, 1.5),
    "imalathane / atölye": ("İmalathane / Atölye", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, True, 50.0, 0.60, 5.0, 1.5),
    "depolamaalani": ("Depolama Alanı", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, True, 150.0, 0.40, 1.2, 0.3),
    "depolama alanı": ("Depolama Alanı", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, True, 150.0, 0.40, 1.2, 0.3),
    "akaryakiturunleridepolamaalani": ("Akaryakıt ve Servis İstasyonu", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, True, 100.0, 0.20, 35.0, 1.0),
    "akaryakıt / depolama": ("Akaryakıt ve Servis İstasyonu", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, True, 100.0, 0.20, 35.0, 1.0),

    # 5. Turizm ve Konaklama
    "otelalani": ("Otel / Turizm Tesisi", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, True, 60.0, 0.45, 4.0, 5.0),
    "otel / turizm tesisi": ("Otel / Turizm Tesisi", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, True, 60.0, 0.45, 4.0, 5.0),

    # 6. Arsa, Şantiye ve Boş Parseller (Özel Mülkiyet Tahsis)
    "arsa": ("Boş Arsa / Yapılaşmamış Parsel", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, False, 0.0, 0.0, 0.0, 0.0),
    "bosarsa": ("Boş Arsa / Yapılaşmamış Parsel", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, False, 0.0, 0.0, 0.0, 0.0),
    "boş arsa / yapılaşmamış parsel": ("Boş Arsa / Yapılaşmamış Parsel", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, False, 0.0, 0.0, 0.0, 0.0),
    "ciplakarazi": ("Açık / Çıplak Arazi", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, False, 0.0, 0.0, 0.0, 0.0),
    "açık / çıplak arazi": ("Açık / Çıplak Arazi", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, False, 0.0, 0.0, 0.0, 0.0),
    "santiyesahalari": ("İnşaat / Şantiye Sahası", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, False, 0.0, 0.0, 0.5, 0.5),
    "inşaat / şantiye sahası": ("İnşaat / Şantiye Sahası", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, False, 0.0, 0.0, 0.5, 0.5),

    # 7. Kamu Donatıları - Eğitim
    "egitimalani": ("Eğitim Alanı / Okul", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - KAMU (KESİNTİ)", "EGITIM", True, 70.0, 0.35, 5.0, 10.0),
    "eğitim alanı / okul": ("Eğitim Alanı / Okul", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - KAMU (KESİNTİ)", "EGITIM", True, 70.0, 0.35, 5.0, 10.0),
    "ilkokul": ("İlkokul", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - KAMU (KESİNTİ)", "EGITIM", True, 70.0, 0.35, 5.0, 10.0),
    "ortaokul": ("Ortaokul", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - KAMU (KESİNTİ)", "EGITIM", True, 70.0, 0.35, 5.0, 10.0),
    "lise": ("Lise", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - KAMU (KESİNTİ)", "EGITIM", True, 70.0, 0.35, 5.0, 10.0),
    "meslekiteknikogretimtesisi": ("Mesleki ve Teknik Öğretim Tesis Alanı", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - KAMU (KESİNTİ)", "EGITIM", True, 70.0, 0.35, 5.0, 10.0),

    # 8. Kamu Donatıları - Sağlık
    "digersaglikalanlari": ("Sağlık Ocağı / ASM", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - KAMU (KESİNTİ)", "SAGLIK", True, 60.0, 0.45, 10.0, 8.0),
    "sağlık ocağı / asm": ("Sağlık Ocağı / ASM", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - KAMU (KESİNTİ)", "SAGLIK", True, 60.0, 0.45, 10.0, 8.0),

    # 9. Kamu Donatıları - Açık ve Yeşil Alanlar / Spor
    "park": ("Park ve Oyun Alanı", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - KAMU (KESİNTİ)", "YESIL_ALAN", False, 0.0, 0.0, 0.5, 3.0),
    "parkoyunalani": ("Park ve Oyun Alanı", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - KAMU (KESİNTİ)", "YESIL_ALAN", False, 0.0, 0.0, 0.5, 3.0),
    "park ve oyun alanı": ("Park ve Oyun Alanı", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - KAMU (KESİNTİ)", "YESIL_ALAN", False, 0.0, 0.0, 0.5, 3.0),
    "park ve rekreasyon alanı": ("Park ve Rekreasyon Alanı", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - KAMU (KESİNTİ)", "YESIL_ALAN", False, 0.0, 0.0, 1.0, 4.0),
    "pasifyesilalan": ("Pasif Yeşil Alan / Refüj", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - KAMU (KESİNTİ)", "YESIL_ALAN", False, 0.0, 0.0, 0.0, 0.0),
    "pasif yeşil alan / refüj": ("Pasif Yeşil Alan / Refüj", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - KAMU (KESİNTİ)", "YESIL_ALAN", False, 0.0, 0.0, 0.0, 0.0),
    "sporkompleksialani": ("Spor Kompleksi / Tesis", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - KAMU (KESİNTİ)", "YESIL_ALAN", False, 0.0, 0.0, 2.0, 4.0),
    "spor kompleksi / tesis": ("Spor Kompleksi / Tesis", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - KAMU (KESİNTİ)", "YESIL_ALAN", False, 0.0, 0.0, 2.0, 4.0),

    # 10. Kamu Donatıları - İbadet Alanları
    "ibadetalani": ("İbadet Alanı", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - KAMU (KESİNTİ)", "IBADET", False, 0.0, 0.0, 1.0, 3.0),
    "ibadet alanı": ("İbadet Alanı", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - KAMU (KESİNTİ)", "IBADET", False, 0.0, 0.0, 1.0, 3.0),

    # 11. Kamu Donatıları - Sosyal ve Kültürel Tesisler
    "sosyalkultureltesis": ("Sosyal ve Kültürel Tesis", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - KAMU (KESİNTİ)", "SOSYAL_KULTUREL", True, 60.0, 0.40, 3.0, 5.0),
    "sosyal ve kültürel tesis": ("Sosyal ve Kültürel Tesis", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - KAMU (KESİNTİ)", "SOSYAL_KULTUREL", True, 60.0, 0.40, 3.0, 5.0),
    "digersosyaltesisler": ("Sosyal ve Kültürel Tesis", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - KAMU (KESİNTİ)", "SOSYAL_KULTUREL", True, 60.0, 0.40, 3.0, 5.0),
    "muze": ("Müze / Sergi Alanı", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - KAMU (KESİNTİ)", "SOSYAL_KULTUREL", True, 100.0, 0.20, 2.0, 4.0),
    "müze / sergi alanı": ("Müze / Sergi Alanı", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - KAMU (KESİNTİ)", "SOSYAL_KULTUREL", True, 100.0, 0.20, 2.0, 4.0),
    "yurtlar": ("Öğrenci Yurdu", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - KAMU (KESİNTİ)", "SOSYAL_KULTUREL", True, 80.0, 0.25, 2.0, 8.0),
    "öğrenci yurdu": ("Öğrenci Yurdu", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - KAMU (KESİNTİ)", "SOSYAL_KULTUREL", True, 80.0, 0.25, 2.0, 8.0),

    # 12. Resmi Kurum ve Belediye Hizmet Alanları (Kamu)
    "belediyehizmetalani": ("Belediye Hizmet Alanı (BHA)", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - KAMU (KESİNTİ)", None, True, 45.0, 0.50, 10.0, 6.0),
    "belediyehizmetalanlari": ("Belediye Hizmet Alanı (BHA)", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - KAMU (KESİNTİ)", None, True, 45.0, 0.50, 10.0, 6.0),
    "belediye hizmet alanı (bha)": ("Belediye Hizmet Alanı (BHA)", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - KAMU (KESİNTİ)", None, True, 45.0, 0.50, 10.0, 6.0),
    "resmikurum": ("Resmi Kurum / Kamu Hizmet Alanı", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - KAMU (KESİNTİ)", None, True, 45.0, 0.50, 8.0, 5.0),
    "resmikurumalanlari": ("Resmi Kurum / Kamu Hizmet Alanı", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - KAMU (KESİNTİ)", None, True, 45.0, 0.50, 8.0, 5.0),
    "resmi kurum / kamu hizmet alanı": ("Resmi Kurum / Kamu Hizmet Alanı", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - KAMU (KESİNTİ)", None, True, 45.0, 0.50, 8.0, 5.0),

    # 13. Teknik Altyapı ve Genel Otopark
    "genelotopark": ("Genel Otopark Alanı", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - KAMU (KESİNTİ)", "TEKNIK_ALTYAPI", True, 500.0, 0.05, 15.0, 2.0),
    "genel otopark alanı": ("Genel Otopark Alanı", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - KAMU (KESİNTİ)", "TEKNIK_ALTYAPI", True, 500.0, 0.05, 15.0, 2.0),
    "enerjiuretimalani": ("Teknik Altyapı / Enerji", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - KAMU (KESİNTİ)", "TEKNIK_ALTYAPI", False, 0.0, 0.0, 0.5, 0.1),
    "teknik altyapı / enerji": ("Teknik Altyapı / Enerji", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - KAMU (KESİNTİ)", "TEKNIK_ALTYAPI", False, 0.0, 0.0, 0.5, 0.1),

    # 14. DOP DIŞI ALANLAR (Tarım, Orman, Mera, Askeri vb.)
    "askerialanlar": ("Askeri Alan (DOP Dışı)", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP DIŞI", "DOP DIŞI (HARİÇ)", None, False, 0.0, 0.0, 0.0, 0.0),
    "askeri alan": ("Askeri Alan (DOP Dışı)", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP DIŞI", "DOP DIŞI (HARİÇ)", None, False, 0.0, 0.0, 0.0, 0.0),
    "raylitoplutasimahatti": ("Ulaşım / Demiryolu", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP DIŞI", "DOP DIŞI (HARİÇ)", None, False, 0.0, 0.0, 0.0, 0.0),
    "ulaşım / demiryolu": ("Ulaşım / Demiryolu", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP DIŞI", "DOP DIŞI (HARİÇ)", None, False, 0.0, 0.0, 0.0, 0.0),
    "mezarlikalani": ("Mezarlık Alanı", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP DIŞI", "DOP DIŞI (HARİÇ)", None, False, 0.0, 0.0, 0.5, 0.5),
    "mezarlık alanı": ("Mezarlık Alanı", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP DIŞI", "DOP DIŞI (HARİÇ)", None, False, 0.0, 0.0, 0.5, 0.5),
    "karisiktarim": ("Tarım Alanı", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP DIŞI", "DOP DIŞI (HARİÇ)", None, False, 0.0, 0.0, 0.0, 0.0),
    "karisiktarimalanlari": ("Tarım Alanı", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP DIŞI", "DOP DIŞI (HARİÇ)", None, False, 0.0, 0.0, 0.0, 0.0),
    "kurumarjinaltarim": ("Tarım Alanı", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP DIŞI", "DOP DIŞI (HARİÇ)", None, False, 0.0, 0.0, 0.0, 0.0),
    "sulumarjinaltarim": ("Tarım Alanı", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP DIŞI", "DOP DIŞI (HARİÇ)", None, False, 0.0, 0.0, 0.0, 0.0),
    "tarım alanı": ("Tarım Alanı", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP DIŞI", "DOP DIŞI (HARİÇ)", None, False, 0.0, 0.0, 0.0, 0.0),
    "karışık tarım alanı": ("Tarım Alanı", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP DIŞI", "DOP DIŞI (HARİÇ)", None, False, 0.0, 0.0, 0.0, 0.0),
    "ormanlakarisiktarimalani": ("Ormanla Karışık Tarım", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP DIŞI", "DOP DIŞI (HARİÇ)", None, False, 0.0, 0.0, 0.0, 0.0),
    "ormanla karışık tarım": ("Ormanla Karışık Tarım", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP DIŞI", "DOP DIŞI (HARİÇ)", None, False, 0.0, 0.0, 0.0, 0.0),
    "zeytinlik": ("Zeytinlik", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP DIŞI", "DOP DIŞI (HARİÇ)", None, False, 0.0, 0.0, 0.0, 0.0),
    "zeytinlikler": ("Zeytinlik", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP DIŞI", "DOP DIŞI (HARİÇ)", None, False, 0.0, 0.0, 0.0, 0.0),
    "kentormani": ("Kent Ormanı", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP DIŞI", "DOP DIŞI (HARİÇ)", None, False, 0.0, 0.0, 0.0, 0.0),
    "kent ormanı": ("Kent Ormanı", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP DIŞI", "DOP DIŞI (HARİÇ)", None, False, 0.0, 0.0, 0.0, 0.0),
    "çayır mera": ("Çayır Mera", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP DIŞI", "DOP DIŞI (HARİÇ)", None, False, 0.0, 0.0, 0.0, 0.0),
    "digerkullanimlar": ("Diğer Kullanımlar", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - KAMU (KESİNTİ)", None, False, 0.0, 0.0, 1.0, 2.0),
    "diğer kullanımlar": ("Diğer Kullanımlar", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - KAMU (KESİNTİ)", None, False, 0.0, 0.0, 1.0, 2.0),
}

TUCBS_ARAZI_KULLANIM_LOOKUP = {clean_key(k): v for k, v in _TUCBS_RAW_MAPPING.items()}

def get_tucbs_info(fonk_str: str) -> dict | None:
    """TUCBS veya arazi kullanım sınıflandırmasını tanır ve standart planlama parametrelerini döndürür."""
    if not fonk_str:
        return None
    ck = clean_key(fonk_str)
    item = TUCBS_ARAZI_KULLANIM_LOOKUP.get(ck)
    if not item:
        # Patern tabanlı esnek yedek eşleşme
        if "gelisme" in ck and "konut" in ck:
            if "cokyuksek" in ck or "401" in ck:
                item = ("Gelişme Konut Alanı (Çok Yüksek)", 401.0, 600.0, "GELİŞME KONUT ALANI (ÇOK YÜKSEK)", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, False, 0.0, 0.0, 2.5, 5.0)
            elif "yuksek" in ck or "251" in ck:
                item = ("Gelişme Konut Alanı (Yüksek)", 251.0, 400.0, "GELİŞME KONUT ALANI (YÜKSEK)", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, False, 0.0, 0.0, 2.5, 4.5)
            elif "orta" in ck or "121" in ck:
                item = ("Gelişme Konut Alanı (Orta)", 121.0, 250.0, "GELİŞME KONUT ALANI (ORTA)", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, False, 0.0, 0.0, 2.5, 4.0)
            elif "dusuk" in ck or "51" in ck:
                item = ("Gelişme Konut Alanı (Düşük)", 51.0, 120.0, "GELİŞME KONUT ALANI (DÜŞÜK)", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, False, 0.0, 0.0, 2.5, 3.5)
            elif "seyrek" in ck or "25" in ck:
                item = ("Gelişme Konut Alanı (Seyrek)", 25.0, 50.0, "GELİŞME KONUT ALANI (SEYREK)", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, False, 0.0, 0.0, 3.5, 2.0)
            else:
                item = ("Gelişme Konut Alanı (Orta)", 121.0, 250.0, "GELİŞME KONUT ALANI (ORTA)", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, False, 0.0, 0.0, 2.5, 4.0)
        elif "konut" in ck:
            if "cokyuksek" in ck or "601" in ck:
                item = ("Mevcut Konut Alanı (Çok Yüksek)", 601.0, 900.0, "MEVCUT KONUT ALANI (ÇOK YÜKSEK)", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, False, 0.0, 0.0, 2.2, 6.0)
            elif "yuksek" in ck or "301" in ck:
                item = ("Mevcut Konut Alanı (Yüksek)", 301.0, 600.0, "MEVCUT KONUT ALANI (YÜKSEK)", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, False, 0.0, 0.0, 2.0, 5.5)
            elif "orta" in ck or "151" in ck:
                item = ("Mevcut Konut Alanı (Orta)", 151.0, 300.0, "MEVCUT KONUT ALANI (ORTA)", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, False, 0.0, 0.0, 2.5, 4.5)
            elif "dusuk" in ck or "51" in ck:
                item = ("Mevcut Konut Alanı (Düşük)", 51.0, 150.0, "MEVCUT KONUT ALANI (DÜŞÜK)", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, False, 0.0, 0.0, 2.5, 4.0)
            elif "seyrek" in ck or "kirsal" in ck or "25" in ck:
                item = ("Mevcut Konut Alanı (Seyrek)", 25.0, 50.0, "MEVCUT KONUT ALANI (SEYREK)", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, False, 0.0, 0.0, 3.5, 2.0)
            else:
                item = ("Mevcut Konut Alanı (Orta)", 151.0, 300.0, "MEVCUT KONUT ALANI (ORTA)", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, False, 0.0, 0.0, 2.5, 4.5)
        elif "karma" in ck or ("ticaret" in ck and "konut" in ck):
            item = ("Karma Kullanım (Ticaret + Konut)", None, None, "KARMA_KONUT", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, True, 40.0, 0.35, 8.0, 8.0)
        elif "ticaret" in ck or "carsi" in ck or "ismerkezi" in ck:
            item = ("Ticaret Alanı", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, True, 30.0, 0.75, 15.0, 12.0)
        elif "sanayi" in ck or "osb" in ck or "imalat" in ck:
            item = ("Sanayi Alanı", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, True, 90.0, 0.50, 2.5, 0.8)
        elif "depo" in ck or "akaryakit" in ck:
            item = ("Depolama Alanı", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, True, 150.0, 0.40, 1.2, 0.3)
        elif "otel" in ck or "turizm" in ck:
            item = ("Turizm / Otel Alanı", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, True, 60.0, 0.45, 4.0, 5.0)
        elif "arsa" in ck or "santiye" in ck or "ciplak" in ck:
            item = ("Boş Arsa / Yapılaşmamış Parsel", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)", None, False, 0.0, 0.0, 0.0, 0.0)
        elif "egitim" in ck or "okul" in ck or "lise" in ck or "ilkokul" in ck or "ortaokul" in ck:
            item = ("Eğitim Alanı", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - KAMU (KESİNTİ)", "EGITIM", True, 70.0, 0.35, 5.0, 10.0)
        elif "saglik" in ck or "asm" in ck or "hastane" in ck:
            item = ("Sağlık Alanı", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - KAMU (KESİNTİ)", "SAGLIK", True, 60.0, 0.45, 10.0, 8.0)
        elif "park" in ck or "yesil" in ck or "rekreasyon" in ck or "spor" in ck:
            item = ("Park ve Yeşil Alan", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - KAMU (KESİNTİ)", "YESIL_ALAN", False, 0.0, 0.0, 0.5, 3.0)
        elif "ibadet" in ck or "cami" in ck:
            item = ("İbadet Alanı", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - KAMU (KESİNTİ)", "IBADET", False, 0.0, 0.0, 1.0, 3.0)
        elif "sosyal" in ck or "kultur" in ck or "muze" in ck or "yurt" in ck:
            item = ("Sosyal ve Kültürel Tesis", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - KAMU (KESİNTİ)", "SOSYAL_KULTUREL", True, 60.0, 0.40, 3.0, 5.0)
        elif "tarim" in ck or "zeytin" in ck or "mera" in ck or "orman" in ck or "asker" in ck or "demiryol" in ck or "mezarlik" in ck:
            item = ("DOP Dışı Alan", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP DIŞI", "DOP DIŞI (HARİÇ)", None, False, 0.0, 0.0, 0.0, 0.0)
        elif "otopark" in ck or "enerji" in ck or "trafo" in ck:
            item = ("Teknik Altyapı / Otopark", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - KAMU (KESİNTİ)", "TEKNIK_ALTYAPI", True, 500.0, 0.05, 15.0, 2.0)
        elif "belediye" in ck or "bha" in ck or "resmi" in ck or "kamu" in ck:
            item = ("Belediye / Kamu Hizmet Alanı", 0.0, 0.0, "DONATI_VEYA_CALISMA", "DOP İÇİ", "DOP İÇİ - KAMU (KESİNTİ)", None, True, 45.0, 0.50, 8.0, 5.0)
        else:
            return None

    return {
        "std_fonksiyon": item[0],
        "alt": item[1],
        "ust": item[2],
        "kategori": item[3],
        "dop_durumu": item[4],
        "dop_turu": item[5],
        "donati": item[6],
        "emp_dahil": item[7],
        "std_m2": item[8],
        "eff": item[9],
        "trip_arac": item[10],
        "trip_yaya": item[11]
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
    """Verilen fonksiyon metninden (örn. Ort_Detay veya TUCBS) alt ve üst sınırları bulur."""
    if not fonk_str:
        return None, None, "TANIMSIZ"
    
    clean = fonk_str.strip().upper()
    # Türkçe I/İ dönüşüm toleransı
    clean = clean.replace("İ", "I").replace("ı", "I").replace("Ğ", "G").replace("Ü", "U").replace("Ş", "S").replace("Ö", "O")

    # 1. Karma Kullanım Kontrolü
    if any(k in clean for k in ["TICARET - KONUT", "TICARET-KONUT", "TICARET TURIZM KONUT", "TICARET-TURIZM- KONUT", "TICARET VE KONUT", "KARMA KULLANIM", "KARMA TICARET"]):
        return None, None, "KARMA_KONUT"

    # 2. Standart NİP Gelişme / Mevcut Konut Yoğunluk Kontrolleri
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
        elif "SEYREK" in clean or "25" in clean or "KIRSAL" in clean:
            return 25.0, 50.0, "MEVCUT KONUT ALANI (SEYREK)"
        else:
            return 151.0, 300.0, "MEVCUT KONUT ALANI (ORTA)"

    # 3. TUCBS / Arazi Kullanım Doğrudan Eşleşmesi
    tucbs = get_tucbs_info(fonk_str)
    if tucbs and tucbs["kategori"] != "DONATI_VEYA_CALISMA":
        return tucbs["alt"], tucbs["ust"], tucbs["kategori"]

    if "KONUT" in clean:
        if "COK YUKSEK" in clean or "601" in clean:
            return 601.0, 900.0, "MEVCUT KONUT ALANI (ÇOK YÜKSEK)"
        elif "YUKSEK" in clean or "301" in clean:
            return 301.0, 600.0, "MEVCUT KONUT ALANI (YÜKSEK)"
        elif "ORTA" in clean or "151" in clean:
            return 151.0, 300.0, "MEVCUT KONUT ALANI (ORTA)"
        elif "DUSUK" in clean or "51" in clean:
            return 51.0, 150.0, "MEVCUT KONUT ALANI (DÜŞÜK)"
        elif "SEYREK" in clean or "25" in clean or "KIRSAL" in clean:
            return 25.0, 50.0, "MEVCUT KONUT ALANI (SEYREK)"
        else:
            return 151.0, 300.0, "MEVCUT KONUT ALANI (ORTA)"

    if tucbs:
        return tucbs["alt"], tucbs["ust"], tucbs["kategori"]

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
    
    # 0. TUCBS / Arazi Kullanım Doğrudan Eşleşmesi
    tucbs = get_tucbs_info(fonk_str)
    if tucbs and tucbs["donati"]:
        return tucbs["donati"]

    upper = norm_tr(fonk_str)
    # Otopark ve makine parkını yeşil alandan kesinlikle koru
    if "OTOPARK" in upper or "MAKINE PARKI" in upper:
        return "TEKNIK_ALTYAPI" if "OTOPARK" in upper else None

    for cat_id, info in MPYY_DONATI_STANDARTLARI.items():
        if any(norm_tr(k) in upper for k in info["anahtarlar"]):
            return cat_id
    
    # Yalın 'PARK' kelimesi kontrolü
    if "PARK" in upper and "OTOPARK" not in upper and "MAKINE" not in upper:
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
    
    tucbs = get_tucbs_info(fonk_str)
    if tucbs and tucbs["emp_dahil"]:
        return max(0, int((alan_m2 * tucbs["eff"]) / tucbs["std_m2"]))

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
    
    tucbs = get_tucbs_info(fonk_str)
    if tucbs:
        units = alan_m2 / 100.0
        return round(units * tucbs["trip_arac"], 1), round(units * tucbs["trip_yaya"], 1)

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

    tucbs = get_tucbs_info(fonk_str)
    if tucbs:
        return tucbs["emp_dahil"], tucbs["std_m2"], tucbs["eff"]

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

    tucbs = get_tucbs_info(fonk_str)
    if tucbs:
        inc_arac = tucbs["trip_arac"] > 0
        inc_yaya = tucbs["trip_yaya"] > 0
        return inc_arac, inc_yaya, tucbs["trip_arac"], tucbs["trip_yaya"]

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


# =====================================================================
# 5. DOP DAHİL / HARİÇ VE KAMU-ÖZEL TAHSİS PARAMETRELERİ
# =====================================================================
OZEL_TAHSIS_ANAHTARLAR = [
    "KONUT", "TICARET", "SANAYI", "TURIZM", "AKARYAKIT", "DEPOLAMA", "OZEL",
    "BETON", "LIMAN", "TERSANE", "ENERJI", "YAPAY ADA", "SERBEST BOLGE", "TEKNE", "TIR", "REKREATIF",
    "ARSA", "BOS ARSA", "BOSARSA", "KARMA", "OTEL", "IMALATHANE", "SANTIYE", "CIPLAK"
]

DOP_DISI_ANAHTARLAR = [
    "ORMAN", "MERA", "TARIM", "ZEYTINLIK", "ZEYTINLIKLER", "SU YUZEYI", "ASKERI", "DEMIRYOLU",
    "SIT ALANI", "AGACLANDIRILACAK", "CAYIR", "MARJINAL"
]


def get_default_dop_rule(fonk_str: str) -> tuple[bool, str, str]:
    """Fonksiyon için varsayılan DOP dahil/hariç (DOP içi / nDOP) ve türünü döndürür.

    Dönüş: (dop_dahil_mi, dop_durumu, dop_turu)
      - dop_dahil_mi: True ise Düzenleme Sahasına Dahil (DOP İçi), False ise Harice Ayrılan (nDOP / DOP Dışı)
      - dop_durumu: "DOP İÇİ" veya "DOP DIŞI"
      - dop_turu: "DOP İÇİ - ÖZEL (TAHSİS)", "DOP İÇİ - KAMU (KESİNTİ)" veya "DOP DIŞI (HARİÇ)"
    """
    if not fonk_str:
        return False, "DOP DIŞI", "DOP DIŞI (HARİÇ)"

    tucbs = get_tucbs_info(fonk_str)
    if tucbs:
        is_ici = (tucbs["dop_durumu"] == "DOP İÇİ")
        return is_ici, tucbs["dop_durumu"], tucbs["dop_turu"]

    fn = norm_tr(fonk_str)
    is_dop_disi = any(k in fn for k in DOP_DISI_ANAHTARLAR)
    is_ozel = any(k in fn for k in OZEL_TAHSIS_ANAHTARLAR)

    if is_dop_disi:
        return False, "DOP DIŞI", "DOP DIŞI (HARİÇ)"
    elif is_ozel:
        return True, "DOP İÇİ", "DOP İÇİ - ÖZEL (TAHSİS)"
    else:
        return True, "DOP İÇİ", "DOP İÇİ - KAMU (KESİNTİ)"


