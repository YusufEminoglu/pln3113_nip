# -*- coding: utf-8 -*-
"""Mevcut Durum Kentsel Morfoloji, Saha ve Bina Bazlı Fiili Nüfus/İstihdam Motoru.

DEÜ Mimarlık Fakültesi Şehir ve Bölge Planlama Bölümü
PLN3113 - nip_eklenti_01
"""
from __future__ import annotations

from qgis.core import (
    QgsSpatialIndex,
    QgsVectorLayer,
    QgsProcessingFeedback
)

from .tire_constants import get_employment_for_function, get_trips_for_function

class FieldEstimatorEngine:
    """Saha adaları ile bina katmanını mekânsal bütünleştirerek fiili nüfus ve morfoloji metriklerini hesaplar."""

    # Kesinlikle konut nüfusu yaşamayacak saf çalışma, altyapı ve kırsal sınıflar
    SIFIR_NUFUS_FONKSIYONLARI = {
        "organizesanayibolgesi", "sanayialani", "kucuksanayi", "depolamaalani",
        "ticaretalani", "digerticaretalanlari", "otopark", "mezarlik",
        "park", "pasifyesil", "zeytinlikler", "karisiktarimalanlari", "arsa",
        "tarim", "sanayi", "depo", "akaryakit", "trafo"
    }

    @staticmethod
    def estimate_ada_population(
        ada_layer: QgsVectorLayer,
        bina_layer: QgsVectorLayer,
        hanehalki_buyuklugu: float = 2.85,
        ortalama_daire_m2: float = 110.0,
        net_oran: float = 0.85,
        feedback: QgsProcessingFeedback = None
    ) -> tuple[list[dict], dict]:
        """Binaları adalarla mekânsal eşleştirir ve ada bazında fiili değerleri toplar."""

        # 1. Adaların spatial index'ini kur
        ada_index = QgsSpatialIndex()
        ada_dict = {}

        idx_tucbs = ada_layer.fields().indexOf("tucbs_sinifi")
        if idx_tucbs == -1:
            for alt in ["Ort__Detay", "Ort_Detay", "nipfonksiyon", "plan_fonksiyon", "fonk", "kullanim"]:
                idx_tucbs = ada_layer.fields().indexOf(alt)
                if idx_tucbs != -1:
                    break
        idx_tanim = ada_layer.fields().indexOf("arazi_kullanim_tanimi")
        if idx_tanim == -1:
            for alt in ["tanim", "aciklama", "detay"]:
                idx_tanim = ada_layer.fields().indexOf(alt)
                if idx_tanim != -1:
                    break
        idx_alan = ada_layer.fields().indexOf("ada_alani_m2")
        if idx_alan == -1:
            for alt in ["alan_m2", "alan", "Shape_Area"]:
                idx_alan = ada_layer.fields().indexOf(alt)
                if idx_alan != -1:
                    break
        idx_adano = ada_layer.fields().indexOf("adano")
        idx_kimlik = ada_layer.fields().indexOf("ada_kimlik")

        for f in ada_layer.getFeatures():
            geom = f.geometry()
            if not geom or geom.isEmpty():
                continue
            ada_index.addFeature(f)
            
            tucbs = str(f[idx_tucbs]).lower() if idx_tucbs != -1 and f[idx_tucbs] else ""
            tanim = str(f[idx_tanim]) if idx_tanim != -1 and f[idx_tanim] else ""
            kimlik = str(f[idx_kimlik]) if idx_kimlik != -1 and f[idx_kimlik] else str(f.id())
            adano = str(f[idx_adano]) if idx_adano != -1 and f[idx_adano] else ""
            
            alan_m2 = 0.0
            if idx_alan != -1 and f[idx_alan]:
                try:
                    alan_m2 = float(f[idx_alan])
                except (ValueError, TypeError):
                    alan_m2 = geom.area()
            else:
                alan_m2 = geom.area()

            # Nüfus yaşayabilir mi? Sadece konut ve karma kullanımda yaşayan nüfus hesaplanır
            is_karma = ("karma" in tucbs) or ("karma" in tanim.lower())
            is_pure_konut = (("konut" in tucbs or "konut" in tanim.lower()) and not is_karma)
            is_zero_pop = not (is_karma or is_pure_konut)

            ada_dict[f.id()] = {
                "feat": f,
                "geom": geom,
                "adano": adano,
                "kimlik": kimlik,
                "tucbs": tucbs,
                "tanim": tanim,
                "alan_m2": alan_m2,
                "alan_ha": alan_m2 / 10000.0,
                "is_karma": is_karma,
                "is_pure_konut": is_pure_konut,
                "is_zero_pop": is_zero_pop,
                "bina_sayisi": 0,
                "toplam_bina_taban_m2": 0.0,
                "toplam_insaat_m2": 0.0,
                "toplam_ipq": 0.0,
                "bina_geoms": [],
                "konut_birim_sayisi": 0,
                "tahmini_nufus": 0,
                "istihdam": 0,
                "gunluk_arac": 0.0,
                "gunluk_yaya": 0.0
            }

        # 2. Binaları ada index'i ile sorgula
        bina_fields = bina_layer.fields()
        idx_kat = bina_fields.indexOf("ZEMINUSTUKATSAYISI")
        if idx_kat == -1:
            for alt in ["KAT_ADEDI", "kat_adedi", "kat", "kat_sayisi", "floors"]:
                idx_kat = bina_fields.indexOf(alt)
                if idx_kat != -1:
                    break
        idx_bagimsiz = bina_fields.indexOf("BAGIMSIZBOLUMSAYI")
        if idx_bagimsiz == -1:
            for alt in ["bagimsiz_bolum", "bagimsiz", "konut_sayisi", "units"]:
                idx_bagimsiz = bina_fields.indexOf(alt)
                if idx_bagimsiz != -1:
                    break
        idx_bina_alan = bina_fields.indexOf("Shape_Area")
        if idx_bina_alan == -1:
            for alt in ["taban_alani", "taban_alani_m2", "alan_m2", "area"]:
                idx_bina_alan = bina_fields.indexOf(alt)
                if idx_bina_alan != -1:
                    break

        bina_count = bina_layer.featureCount()

        for b_idx, b_feat in enumerate(bina_layer.getFeatures()):
            if feedback and feedback.isCanceled():
                break

            b_geom = b_feat.geometry()
            if not b_geom or b_geom.isEmpty():
                continue

            # Bina centroid'i üzerinden hızlı nokta sorgusu
            c_pt = b_geom.centroid().asPoint() if b_geom.centroid() else None
            if not c_pt:
                continue

            matched_ada_ids = ada_index.intersects(b_geom.boundingBox())
            matched_ada_id = None
            for aid in matched_ada_ids:
                if ada_dict[aid]["geom"].contains(b_geom.centroid()):
                    matched_ada_id = aid
                    break

            if matched_ada_id is None:
                continue

            ada_info = ada_dict[matched_ada_id]
            ada_info["bina_sayisi"] += 1

            # Bina parametreleri
            taban_m2 = 0.0
            if idx_bina_alan != -1 and b_feat[idx_bina_alan]:
                try:
                    taban_m2 = float(b_feat[idx_bina_alan])
                except (ValueError, TypeError):
                    taban_m2 = b_geom.area()
            else:
                taban_m2 = b_geom.area()

            ada_info["toplam_bina_taban_m2"] += taban_m2

            kat = 1
            if idx_kat != -1 and b_feat[idx_kat]:
                try:
                    kat = max(1, int(b_feat[idx_kat]))
                except (ValueError, TypeError):
                    kat = 1

            bagimsiz = 0
            if idx_bagimsiz != -1 and b_feat[idx_bagimsiz]:
                try:
                    bagimsiz = int(b_feat[idx_bagimsiz])
                except (ValueError, TypeError):
                    bagimsiz = 0

            # 1. Küçük yapı filtresi: 35 m2 altındaki bağımsız bölümsüz yapılar sundurma/müştemilattır
            if taban_m2 < 35.0 and bagimsiz == 0:
                continue

            insaat_m2 = taban_m2 * kat * net_oran
            ada_info["toplam_insaat_m2"] += insaat_m2

            # Bina Kompaklığı (IPQ - Isoperimetric Quotient)
            perim = b_geom.length()
            if perim > 0:
                ipq = (4.0 * 3.141592653589793 * taban_m2) / (perim * perim)
                ada_info["toplam_ipq"] += max(0.0, min(1.0, ipq))
            else:
                ada_info["toplam_ipq"] += 0.75

            # Bitişiklik analizi için geometri referansı sakla (maks. 500 bina/ada)
            if len(ada_info["bina_geoms"]) < 500:
                ada_info["bina_geoms"].append(b_geom)

            # 2. Saf Çalışma / Sanayi / Ticaret / Donatı
            if ada_info["is_zero_pop"]:
                ada_info["istihdam"] += get_employment_for_function(ada_info["tanim"], insaat_m2, ada_info["tucbs"])
                arac, yaya = get_trips_for_function(ada_info["tanim"], insaat_m2, ada_info["tucbs"])
                ada_info["gunluk_arac"] += arac
                ada_info["gunluk_yaya"] += yaya
                continue

            # 3. Karma Kullanım (Ticaret + Konut): Zemin dükkan (istihdam), üst katlar konut
            if ada_info["is_karma"]:
                zemin_insaat = taban_m2 * net_oran
                ada_info["istihdam"] += get_employment_for_function("KARMA TİCARET", zemin_insaat, "KARMA")
                
                ust_kat = max(0, kat - 1)
                if ust_kat > 0:
                    max_units = max(1, int((taban_m2 * ust_kat * net_oran) / 50.0))
                    if bagimsiz > 1:
                        konut = min(bagimsiz - 1, max_units)
                    elif ust_kat == 1:
                        konut = 1
                    elif ust_kat == 2:
                        konut = 2
                    else:
                        konut = max(1, int(round((taban_m2 * ust_kat * net_oran) / ortalama_daire_m2)))

                    ada_info["konut_birim_sayisi"] += konut
                    ada_info["tahmini_nufus"] += int(round(konut * hanehalki_buyuklugu))

                arac, yaya = get_trips_for_function("TİCARET - KONUT ALANI", insaat_m2)
                ada_info["gunluk_arac"] += arac
                ada_info["gunluk_yaya"] += yaya
                continue

            # 4. Saf Konut Alanları
            if ada_info["is_pure_konut"]:
                max_units = max(1, int(insaat_m2 / 50.0))
                tanim_low = ada_info["tanim"].lower()
                if bagimsiz > 0:
                    konut = min(bagimsiz, max_units)
                elif "seyrek" in tanim_low or "dusuk" in tanim_low:
                    konut = 1 # Müstakil tek aile evi
                elif kat <= 2:
                    konut = kat # 1 katlı 1 hane, 2 katlı 2 hane
                else:
                    konut = max(1, int(round(insaat_m2 / ortalama_daire_m2)))

                ada_info["konut_birim_sayisi"] += konut
                ada_info["tahmini_nufus"] += int(round(konut * hanehalki_buyuklugu))

                arac, yaya = get_trips_for_function(ada_info["tanim"], insaat_m2, "KONUT")
                ada_info["gunluk_arac"] += arac
                ada_info["gunluk_yaya"] += yaya

            if feedback and b_idx % 1000 == 0:
                feedback.setProgress(int((b_idx / max(1, bina_count)) * 100))

        # 3. Ada bazlı brüt yoğunluk, TAKS, KAKS, Spacematrix morfoloji ve özetler
        toplam_fiili_nufus = 0
        toplam_fiili_bina = 0
        toplam_fiili_istihdam = 0
        toplam_fiili_konut = 0
        toplam_taban_tum = 0.0
        toplam_insaat_tum = 0.0
        toplam_alan_tum = 0.0

        result_list = []
        for aid, item in ada_dict.items():
            alan_m2 = max(1.0, item["alan_m2"])
            alan_ha = max(0.0001, item["alan_ha"])
            taban_m2 = item["toplam_bina_taban_m2"]
            insaat_m2 = item["toplam_insaat_m2"]
            b_count = item["bina_sayisi"]

            # 1. TAKS (GSI - Ground Space Index)
            fiili_taks = round(min(1.0, taban_m2 / alan_m2), 3)
            item["fiili_taks"] = fiili_taks

            # 2. KAKS (FSI - Floor Space Index / Emsal)
            fiili_kaks = round(insaat_m2 / alan_m2, 3)
            item["fiili_kaks"] = fiili_kaks

            # 3. Ortalama Kat Yüksekliği (L - Layers)
            ort_kat = round(insaat_m2 / max(1.0, taban_m2), 1) if taban_m2 > 0 else 0.0
            item["ort_kat"] = ort_kat

            # 4. Açık Alan Oranı (%)
            acik_alan_yuzde = round(max(0.0, (alan_m2 - taban_m2) / alan_m2 * 100.0), 1)
            item["acik_alan_yuzde"] = acik_alan_yuzde

            # 5. Spacematrix OSR (Open Space Ratio: (1 - GSI) / FSI)
            spacematrix_osr = round((1.0 - fiili_taks) / max(0.05, fiili_kaks), 2) if fiili_kaks > 0 else 0.0
            item["spacematrix_osr"] = spacematrix_osr

            # 6. Bina Yoğunluğu (Bina / Hektar)
            item["bina_yogunluk_ha"] = round(b_count / alan_ha, 1)

            # 7. Ortalama Bina Kompaklığı (IPQ)
            item["ort_kompaklik_ipq"] = round(item["toplam_ipq"] / max(1, b_count), 2) if b_count > 0 else 0.0

            # 8. Yapı Nizamı (A4) ve Zarf Büyüklüğü (Bitişik Dizi)
            b_geoms = item.get("bina_geoms", [])
            if b_count == 0:
                yapi_nizami = "Boş Ada"
                max_bitisik_dizi = 0
            elif b_count == 1:
                yapi_nizami = "Ayrık"
                max_bitisik_dizi = 1
            else:
                n = len(b_geoms)
                parent = list(range(n))
                def find(i):
                    path = []
                    while parent[i] != i:
                        path.append(i)
                        i = parent[i]
                    for node in path:
                        parent[node] = i
                    return i
                def union(i, j):
                    root_i = find(i)
                    root_j = find(j)
                    if root_i != root_j:
                        parent[root_i] = root_j

                for i in range(n):
                    gi = b_geoms[i]
                    for j in range(i + 1, n):
                        gj = b_geoms[j]
                        if gi.intersects(gj) or gi.distance(gj) <= 0.35:
                            union(i, j)

                comp_sizes = {}
                for i in range(n):
                    r = find(i)
                    comp_sizes[r] = comp_sizes.get(r, 0) + 1

                max_bitisik_dizi = max(comp_sizes.values()) if comp_sizes else 1
                if max_bitisik_dizi == 1:
                    yapi_nizami = "Ayrık"
                elif min(comp_sizes.values()) > 1:
                    yapi_nizami = "Bitişik / Blok"
                else:
                    yapi_nizami = "Karma (Ayrık + Bitişik)"

            item["yapi_nizami"] = yapi_nizami
            item["max_bitisik_dizi"] = max_bitisik_dizi

            # 9. Kentsel Doku / Spacematrix Tipolojisi
            if b_count == 0:
                doku_tipi = "Boş / Yapılaşmamış Ada"
            elif fiili_kaks < 0.60 and fiili_taks < 0.30:
                doku_tipi = "Seyrek / Az Katlı Bahçeli"
            elif fiili_kaks < 1.40 and fiili_taks < 0.45:
                doku_tipi = "Orta Yoğunluklu Doku"
            elif fiili_taks >= 0.45 or fiili_kaks >= 2.0:
                doku_tipi = "Yüksek Yoğunluklu / Kompakt Blok"
            elif ort_kat >= 5.0 and fiili_taks < 0.30:
                doku_tipi = "Nokta / Kule Bloklar"
            else:
                doku_tipi = "Geleneksel / Karma Kentsel Doku"

            item["doku_tipi"] = doku_tipi

            brut_yogunluk = round(item["tahmini_nufus"] / alan_ha, 1)
            item["fiili_brut_yogunluk_ha"] = brut_yogunluk
            item["gunluk_arac"] = int(round(item["gunluk_arac"]))
            item["gunluk_yaya"] = int(round(item["gunluk_yaya"]))

            toplam_fiili_nufus += item["tahmini_nufus"]
            toplam_fiili_bina += item["bina_sayisi"]
            toplam_fiili_istihdam += item["istihdam"]
            toplam_fiili_konut += item["konut_birim_sayisi"]
            toplam_taban_tum += taban_m2
            toplam_insaat_tum += insaat_m2
            toplam_alan_tum += alan_m2

            result_list.append(item)

        stats = {
            "toplam_ada_sayisi": len(result_list),
            "toplam_eslesen_bina": toplam_fiili_bina,
            "toplam_konut_birimi": toplam_fiili_konut,
            "toplam_fiili_nufus": toplam_fiili_nufus,
            "toplam_fiili_istihdam": toplam_fiili_istihdam,
            "toplam_taban_m2": round(toplam_taban_tum, 2),
            "toplam_insaat_m2": round(toplam_insaat_tum, 2),
            "ortalama_taks": round(toplam_taban_tum / max(1.0, toplam_alan_tum), 3),
            "ortalama_kaks": round(toplam_insaat_tum / max(1.0, toplam_alan_tum), 3),
            "ortalama_kat": round(toplam_insaat_tum / max(1.0, toplam_taban_tum), 1) if toplam_taban_tum > 0 else 0.0,
            "ortalama_acik_alan_yuzde": round(max(0.0, (toplam_alan_tum - toplam_taban_tum) / max(1.0, toplam_alan_tum) * 100.0), 1),
            "ortalama_hanehalki": hanehalki_buyuklugu,
            "ortalama_daire_m2": ortalama_daire_m2
        }

        return result_list, stats
