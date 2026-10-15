# -*- coding: utf-8 -*-
"""Tire 1/5000 NİP Nüfus, Donatı, Kamu-Özel, DOP ve Ulaşım Hesaplama Motoru.

DEÜ Mimarlık Fakültesi Şehir ve Bölge Planlama Bölümü
PLN3113 - Tire NİP Analiz Stüdyosu
"""
from __future__ import annotations

from qgis.core import (
    QgsDistanceArea,
    QgsFeature,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsPointXY,
    QgsSpatialIndex,
    QgsVectorLayer,
    QgsWkbTypes
)
from qgis.PyQt.QtCore import QVariant

from .tire_constants import (
    TIRE_POPULATION_BENCHMARKS,
    resolve_nip_density,
    identify_facility_category,
    MPYY_DONATI_STANDARTLARI,
    get_employment_for_function,
    get_trips_for_function,
    norm_tr,
    get_tucbs_info,
    OZEL_TAHSIS_ANAHTARLAR,
    DOP_DISI_ANAHTARLAR,
    get_default_dop_rule
)

class NipCalculatorEngine:
    """NİP Plan ve Fiziki Mevcut Durum adalarında nüfus, donatı, Kamu-Özel dengesi, DOP ve ulaşım hesaplamalarını yürütür."""

    OZEL_TAHSIS_ANAHTARLAR = OZEL_TAHSIS_ANAHTARLAR
    DOP_DISI_ANAHTARLAR = DOP_DISI_ANAHTARLAR

    @staticmethod
    def calculate(
        features: list[QgsFeature],
        source_fields: QgsFields,
        fonksiyon_col: str,
        projeksiyon_nufus: int = 65000,
        distance_area: QgsDistanceArea = None,
        sinir_geom: QgsGeometry | None = None,
        yol_uzunlugu_m: float = 0.0,
        rules_config: dict | None = None,
        secondary_fonk_col: str = "",
        analysis_mode: str = "nip"
    ) -> tuple[list[dict], dict]:
        """Tüm öznitelikleri, Kamu-Özel dengesini, DOP ve kent karakter tablolarını üretir."""
        rules_config = rules_config or {}
        dop_rules = rules_config.get("dop", {})
        emp_rules = rules_config.get("employment", {})
        trip_rules = rules_config.get("trips", {})
        
        # 1. Alan ve Fonksiyon Ön Taraması
        parsed_items = []
        residential_features = [] # (geom, alt_snr, ust_snr)
        
        idx_fonk = source_fields.indexOf(fonksiyon_col) if fonksiyon_col else -1
        idx_sec = source_fields.indexOf(secondary_fonk_col) if secondary_fonk_col else -1
        idx_grup = source_fields.indexOf("grup_no") if "grup_no" in source_fields.names() else -1

        for feat in features:
            geom = feat.geometry()
            if not geom or geom.isEmpty():
                continue

            # Alan hesapla
            if distance_area:
                alan_m2 = distance_area.measureArea(geom)
                if alan_m2 <= 0.001:
                    alan_m2 = geom.area()
            else:
                alan_m2 = geom.area()

            alan_ha = alan_m2 / 10000.0

            # Fonksiyon değerini birincil sütundan al; boşsa ikincil (yedek) sütundan tamamla
            fonk_val = ""
            if idx_fonk != -1 and feat[idx_fonk] is not None:
                fonk_val = str(feat[idx_fonk]).strip()
            
            if not fonk_val and idx_sec != -1 and feat[idx_sec] is not None:
                fonk_val = str(feat[idx_sec]).strip()

            if not fonk_val and idx_grup != -1 and feat[idx_grup] is not None:
                grup_val = str(feat[idx_grup]).strip()
                if "OSB" in grup_val.upper():
                    fonk_val = "Organize Sanayi Bölgesi (OSB)"

            tucbs = get_tucbs_info(fonk_val)
            alt_snr, ust_snr, kategori = resolve_nip_density(fonk_val)

            # DOP ve Kamu - Özel Sınıflandırması (Kullanıcı Kuralı veya Varsayılan)
            fn = norm_tr(fonk_val)
            dop_rule = dop_rules.get(fn) or dop_rules.get(fonk_val)
            if dop_rule is not None:
                inc_dop = dop_rule.get("include", True)
                if not inc_dop:
                    dop_durumu = "DOP DIŞI"
                    dop_turu = "DOP DIŞI (HARİÇ)"
                else:
                    dop_durumu = "DOP İÇİ"
                    custom_turu = dop_rule.get("dop_turu")
                    if custom_turu and "HARİÇ" not in custom_turu.upper() and "HARIC" not in norm_tr(custom_turu):
                        dop_turu = custom_turu
                    else:
                        if tucbs and "ÖZEL" in tucbs["dop_turu"]:
                            dop_turu = "DOP İÇİ - ÖZEL (TAHSİS)"
                        elif any(k in fn for k in NipCalculatorEngine.OZEL_TAHSIS_ANAHTARLAR):
                            dop_turu = "DOP İÇİ - ÖZEL (TAHSİS)"
                        else:
                            dop_turu = "DOP İÇİ - KAMU (KESİNTİ)"
            else:
                if tucbs:
                    dop_durumu = tucbs["dop_durumu"]
                    dop_turu = tucbs["dop_turu"]
                else:
                    is_dop_disi = any(k in fn for k in NipCalculatorEngine.DOP_DISI_ANAHTARLAR)
                    is_ozel = any(k in fn for k in NipCalculatorEngine.OZEL_TAHSIS_ANAHTARLAR)

                    if is_dop_disi:
                        dop_durumu = "DOP DIŞI"
                        dop_turu = "DOP DIŞI (HARİÇ)"
                    elif is_ozel:
                        dop_durumu = "DOP İÇİ"
                        dop_turu = "DOP İÇİ - ÖZEL (TAHSİS)"
                    else:
                        dop_durumu = "DOP İÇİ"
                        dop_turu = "DOP İÇİ - KAMU (KESİNTİ)"

            item = {
                "feat": feat,
                "geom": geom,
                "fonk_raw": fonk_val,
                "alan_m2": alan_m2,
                "alan_ha": alan_ha,
                "alt_snr": alt_snr,
                "ust_snr": ust_snr,
                "kategori": kategori,
                "dop_durumu": dop_durumu,
                "dop_turu": dop_turu,
                "is_mixed": (kategori == "KARMA_KONUT"),
                "is_konut": (alt_snr is not None and alt_snr > 0)
            }
            parsed_items.append(item)

            if item["is_konut"]:
                residential_features.append((geom, alt_snr, ust_snr))

        # 2. Karma Kullanımlar (Ticaret - Konut vb.) için Mekânsal Komşuluk Hesabı
        res_index = QgsSpatialIndex()
        res_geoms_map = {}
        for r_id, (r_geom, r_alt, r_ust) in enumerate(residential_features):
            res_feat = QgsFeature(r_id)
            res_feat.setGeometry(r_geom)
            res_index.addFeature(res_feat)
            res_geoms_map[r_id] = (r_alt, r_ust)

        for item in parsed_items:
            if item["is_mixed"]:
                geom = item["geom"]
                nearest_ids = res_index.nearestNeighbor(geom.centroid().asPoint() if geom.centroid() else QgsPointXY(0,0), 3)
                if nearest_ids and nearest_ids[0] in res_geoms_map:
                    min_alt = min(res_geoms_map[nid][0] for nid in nearest_ids if nid in res_geoms_map)
                    min_ust = min(res_geoms_map[nid][1] for nid in nearest_ids if nid in res_geoms_map)
                    item["alt_snr"] = round(min_alt * 0.3, 1)
                    item["ust_snr"] = round(min_ust * 0.3, 1)
                else:
                    item["alt_snr"] = round(51.0 * 0.3, 1)
                    item["ust_snr"] = round(120.0 * 0.3, 1)
            elif item["alt_snr"] is None:
                item["alt_snr"] = 0.0
                item["ust_snr"] = 0.0

        # 3. Nüfus, İstihdam ve Yolculuk Hesapları
        toplam_alt_nufus = 0.0
        toplam_ust_nufus = 0.0
        toplam_plan_alani_ha = 0.0
        toplam_konut_alani_ha = 0.0

        for item in parsed_items:
            toplam_plan_alani_ha += item["alan_ha"]
            alt_nufus = item["alan_ha"] * item["alt_snr"]
            ust_nufus = item["alan_ha"] * item["ust_snr"]
            item["alt_nufus"] = round(alt_nufus, 1)
            item["ust_nufus"] = round(ust_nufus, 1)

            if item["alt_snr"] > 0 or item["is_mixed"]:
                toplam_alt_nufus += alt_nufus
                toplam_ust_nufus += ust_nufus
                toplam_konut_alani_ha += item["alan_ha"]

            # İstihdam ve Yolculuk (Kural tabanlı dahil/hariç mekanizması)
            fonk_str = item["fonk_raw"]
            fn = norm_tr(fonk_str)

            emp_rule = emp_rules.get(fn) or emp_rules.get(fonk_str)
            if emp_rule is not None:
                if not emp_rule.get("include", True):
                    item["istihdam"] = 0
                else:
                    c_std = emp_rule.get("m2_per_worker")
                    c_eff = emp_rule.get("eff", 1.0)
                    if c_std and c_std > 0:
                        item["istihdam"] = max(0, int((item["alan_m2"] * c_eff) / c_std))
                    else:
                        item["istihdam"] = get_employment_for_function(fonk_str, item["alan_m2"], item["kategori"])
            else:
                item["istihdam"] = get_employment_for_function(fonk_str, item["alan_m2"], item["kategori"])

            tr_rule = trip_rules.get(fn) or trip_rules.get(fonk_str)
            if tr_rule is not None:
                inc_arac = tr_rule.get("include_arac", True)
                inc_yaya = tr_rule.get("include_yaya", True)
                r_arac = tr_rule.get("rate_arac")
                r_yaya = tr_rule.get("rate_yaya")
                def_arac, def_yaya = get_trips_for_function(fonk_str, item["alan_m2"], item["kategori"])
                units = item["alan_m2"] / 100.0

                item["gunluk_arac"] = round(units * r_arac, 1) if (inc_arac and r_arac is not None) else (def_arac if inc_arac else 0.0)
                item["gunluk_yaya"] = round(units * r_yaya, 1) if (inc_yaya and r_yaya is not None) else (def_yaya if inc_yaya else 0.0)
            else:
                arac, yaya = get_trips_for_function(fonk_str, item["alan_m2"], item["kategori"])
                item["gunluk_arac"] = arac
                item["gunluk_yaya"] = yaya

        toplam_alt_nufus = int(round(toplam_alt_nufus))
        toplam_ust_nufus = int(round(toplam_ust_nufus))
        adalar_toplam_m2 = toplam_plan_alani_ha * 10000.0
        adalar_toplam_ha = toplam_plan_alani_ha

        # 4. Donatı Alanları için Kişi Başı Metrekareler
        donati_stats = {cat: 0.0 for cat in MPYY_DONATI_STANDARTLARI}
        stats_fonksiyonlar = {}

        for item in parsed_items:
            fonk = item["fonk_raw"]
            cat = identify_facility_category(fonk)
            item["donati_kategori"] = cat

            if cat:
                donati_stats[cat] += item["alan_m2"]
                item["km2_alt_nufus"] = round((item["alan_ha"] * 10000.0) / max(1, toplam_alt_nufus), 4)
                item["km2_ust_nufus"] = round((item["alan_ha"] * 10000.0) / max(1, toplam_ust_nufus), 4)
            else:
                item["km2_alt_nufus"] = None
                item["km2_ust_nufus"] = None

            # Fonksiyon Dağılım İstatistiği
            if fonk not in stats_fonksiyonlar:
                stats_fonksiyonlar[fonk] = {
                    "fonksiyon": fonk,
                    "dop_durumu": item["dop_durumu"],
                    "dop_turu": item["dop_turu"],
                    "adet": 0,
                    "alan_m2": 0.0,
                    "alan_ha": 0.0
                }
            stats_fonksiyonlar[fonk]["adet"] += 1
            stats_fonksiyonlar[fonk]["alan_m2"] += item["alan_m2"]
            stats_fonksiyonlar[fonk]["alan_ha"] += item["alan_ha"]

        # 5. PLAN ONAMA SINIRI, GERÇEK YOL ALANI, KAMU-ÖZEL DENGESİ VE DOP HESABI
        sinir_kullanildi = False
        if sinir_geom is not None and not sinir_geom.isEmpty():
            toplam_plan_alani_m2 = distance_area.measureArea(sinir_geom) if distance_area else sinir_geom.area()
            toplam_plan_alani_ha = toplam_plan_alani_m2 / 10000.0
            # Plan onama sınırı içindeki imar adaları dışındaki alan net yoldur
            hesaplanan_yol_m2 = max(0.0, toplam_plan_alani_m2 - adalar_toplam_m2)
            sinir_kullanildi = True
        else:
            toplam_plan_alani_m2 = adalar_toplam_m2
            toplam_plan_alani_ha = adalar_toplam_ha
            # Sınır verilmediğinde varsayılan tahmini yol payı (%18 standart planlama payı)
            hesaplanan_yol_m2 = max(0.0, adalar_toplam_m2 * 0.18)
            sinir_kullanildi = False

        hesaplanan_yol_ha = round(hesaplanan_yol_m2 / 10000.0, 2)
        yol_orani = round((hesaplanan_yol_m2 / max(1.0, toplam_plan_alani_m2 if sinir_kullanildi else (adalar_toplam_m2 + hesaplanan_yol_m2))) * 100.0, 2)
        kisi_basi_yol_m2 = round(hesaplanan_yol_m2 / max(1, toplam_ust_nufus), 2)

        # Yol aksları uzunluğu ve genişlik analizi
        if yol_uzunlugu_m > 0 and hesaplanan_yol_m2 > 0:
            ortalama_yol_genisligi_m = round(hesaplanan_yol_m2 / yol_uzunlugu_m, 2)
            yol_agi_uzunlugu_km = round(yol_uzunlugu_m / 1000.0, 2)
        else:
            ortalama_yol_genisligi_m = None
            yol_agi_uzunlugu_km = round(yol_uzunlugu_m / 1000.0, 2) if yol_uzunlugu_m > 0 else None

        # DOP Dışı Alanlar (Harice Ayrılanlar: Orman, Tarım, Su vb.)
        toplam_dop_disi_m2 = sum(it["alan_m2"] for it in parsed_items if it["dop_durumu"] == "DOP DIŞI")
        dop_esas_alan_m2 = max(0.0, (toplam_plan_alani_m2 if sinir_kullanildi else (adalar_toplam_m2 + hesaplanan_yol_m2)) - toplam_dop_disi_m2)

        toplam_ozel_tahsis_m2 = sum(it["alan_m2"] for it in parsed_items if "ÖZEL" in it["dop_turu"])
        toplam_kamu_poligon_m2 = sum(it["alan_m2"] for it in parsed_items if "KAMU" in it["dop_turu"])

        toplam_kamu_kesinti_m2 = toplam_kamu_poligon_m2 + hesaplanan_yol_m2
        dop_orani = round((toplam_kamu_kesinti_m2 / max(1.0, dop_esas_alan_m2)) * 100.0, 2)
        kamu_ozel_orani = round((toplam_kamu_kesinti_m2 / max(1.0, toplam_ozel_tahsis_m2)) * 100.0, 2)

        dop_ozet = {
            "sinir_katmani_kullanildi": sinir_kullanildi,
            "toplam_plan_alani_m2": round(toplam_plan_alani_m2 if sinir_kullanildi else (adalar_toplam_m2 + hesaplanan_yol_m2), 2),
            "toplam_plan_alani_ha": round(toplam_plan_alani_ha if sinir_kullanildi else ((adalar_toplam_m2 + hesaplanan_yol_m2)/10000.0), 2),
            "adalar_toplam_m2": round(adalar_toplam_m2, 2),
            "adalar_toplam_ha": round(adalar_toplam_ha, 2),
            "dop_disi_alan_m2": round(toplam_dop_disi_m2, 2),
            "dop_esas_alan_m2": round(dop_esas_alan_m2, 2),
            "toplam_ozel_tahsis_m2": round(toplam_ozel_tahsis_m2, 2),
            "toplam_kamu_kesinti_m2": round(toplam_kamu_kesinti_m2, 2),
            "kamu_poligonlar_m2": round(toplam_kamu_poligon_m2, 2),
            "hesaplanan_yol_m2": round(hesaplanan_yol_m2, 2),
            "hesaplanan_yol_ha": hesaplanan_yol_ha,
            "yol_orani_yuzde": yol_orani,
            "kisi_basi_yol_m2": kisi_basi_yol_m2,
            "yol_agi_uzunlugu_km": yol_agi_uzunlugu_km,
            "ortalama_yol_genisligi_m": ortalama_yol_genisligi_m,
            "dop_orani": dop_orani,
            "kamu_ozel_orani": kamu_ozel_orani,
            "yasal_sinir": 45.0,
            "dop_uygunluk": "YASAL SINIRDA (UYGUN)" if dop_orani <= 45.0 else "YASAL SINIRI AŞIYOR"
        }

        # 6. Fonksiyon Dağılım Tablosu
        fonksiyon_dagilim_list = []
        for f_name, f_data in stats_fonksiyonlar.items():
            f_m2 = f_data["alan_m2"]
            tum_pay = round((f_m2 / max(1.0, toplam_plan_alani_m2)) * 100.0, 2)
            dop_pay = round((f_m2 / max(1.0, dop_esas_alan_m2)) * 100.0, 2) if f_data["dop_durumu"] == "DOP İÇİ" else 0.0
            kb_m2 = round(f_m2 / max(1, toplam_ust_nufus), 2)
            fonksiyon_dagilim_list.append({
                "fonksiyon": f_name,
                "dop_durumu": f_data["dop_durumu"],
                "dop_turu": f_data["dop_turu"],
                "adet": f_data["adet"],
                "alan_m2": round(f_m2, 2),
                "alan_ha": round(f_data["alan_ha"], 2),
                "kisi_basi_m2": kb_m2,
                "tum_plan_yuzdesi": tum_pay,
                "dop_ici_yuzde": dop_pay
            })

        # 7. Kent Karakter Tablosu (Kentsel Donatılar ve Kullanımlar Kişi Başı Metrikleri)
        kent_karakter_list = []
        for f_name, f_data in stats_fonksiyonlar.items():
            f_m2 = f_data["alan_m2"]
            kb_alt = round(f_m2 / max(1, toplam_alt_nufus), 2)
            kb_ust = round(f_m2 / max(1, toplam_ust_nufus), 2)
            kb_proj = round(f_m2 / max(1, projeksiyon_nufus), 2)
            kent_karakter_list.append({
                "fonksiyon": f_name,
                "toplam_m2": round(f_m2, 2),
                "alt_nufus_m2_kisi": kb_alt,
                "ust_nufus_m2_kisi": kb_ust,
                "proj_nufus_m2_kisi": kb_proj
            })

        # 8. MPYY Ek-2 Yeterlilik Tablosu
        ek2_rapor = []
        for cat_id, info in MPYY_DONATI_STANDARTLARI.items():
            toplam_m2 = donati_stats.get(cat_id, 0.0)
            std = info["standart_m2_kisi"]
            
            kb_alt = round(toplam_m2 / max(1, toplam_alt_nufus), 2)
            kb_ust = round(toplam_m2 / max(1, toplam_ust_nufus), 2)
            kb_proj = round(toplam_m2 / max(1, projeksiyon_nufus), 2)

            gerekli_alt = round(toplam_alt_nufus * std, 1)
            gerekli_ust = round(toplam_ust_nufus * std, 1)
            gerekli_proj = round(projeksiyon_nufus * std, 1)

            fark_alt = round(toplam_m2 - gerekli_alt, 1)
            fark_ust = round(toplam_m2 - gerekli_ust, 1)
            fark_proj = round(toplam_m2 - gerekli_proj, 1)

            ek2_rapor.append({
                "kategori_id": cat_id,
                "kategori_adi": info["adi"],
                "toplam_m2": round(toplam_m2, 2),
                "standart_m2": std,
                "kb_alt": kb_alt,
                "kb_ust": kb_ust,
                "kb_proj": kb_proj,
                "durum_alt": "YETERLİ" if fark_alt >= 0 else "YETERSİZ",
                "durum_ust": "YETERLİ" if fark_ust >= 0 else "YETERSİZ",
                "durum_proj": "YETERLİ" if fark_proj >= 0 else "YETERSİZ",
                "fark_alt": fark_alt,
                "fark_ust": fark_ust,
                "fark_proj": fark_proj
            })

        # 9. Tire Nüfus Kıyaslama Raporu
        kiyaslama = []
        for b_key, b_info in TIRE_POPULATION_BENCHMARKS.items():
            kiyaslama.append({
                "kapsam": b_info["kapsam"],
                "merkez": b_info["merkez"],
                "ilce": b_info["ilce"],
                "kaynak": b_info["kaynak"]
            })
        
        kiyaslama.append({
            "kapsam": f"Hesaplanan 1/5000 NİP Nüfusu ({toplam_alt_nufus:,} - {toplam_ust_nufus:,})".replace(",", "."),
            "merkez": f"{toplam_alt_nufus:,} - {toplam_ust_nufus:,}".replace(",", "."),
            "ilce": f"{(toplam_alt_nufus + 26000):,} - {(toplam_ust_nufus + 26000):,}".replace(",", "."),
            "kaynak": "PLN3113 Tire NİP Analiz Modeli (Alt - Üst Sınır)"
        })

        summary = {
            "toplam_plan_alani_ha": round(toplam_plan_alani_ha, 2),
            "toplam_konut_alani_ha": round(toplam_konut_alani_ha, 2),
            "toplam_alt_nufus": toplam_alt_nufus,
            "toplam_ust_nufus": toplam_ust_nufus,
            "projeksiyon_nufus": projeksiyon_nufus,
            "toplam_istihdam": sum(it["istihdam"] for it in parsed_items),
            "toplam_gunluk_arac": int(sum(it["gunluk_arac"] for it in parsed_items)),
            "toplam_gunluk_yaya": int(sum(it["gunluk_yaya"] for it in parsed_items)),
            "dop_ozet": dop_ozet,
            "fonksiyon_dagilim": fonksiyon_dagilim_list,
            "kent_karakter": kent_karakter_list,
            "ek2_rapor": ek2_rapor,
            "kiyaslama": kiyaslama
        }

        return parsed_items, summary
