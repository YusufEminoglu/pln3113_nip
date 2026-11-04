# -*- coding: utf-8 -*-
"""1/5000 NİP Nüfus, Donatı, Kamu-Özel, DOP ve Ulaşım Hesaplama Motoru.

PLN3113 - NİP Analiz Stüdyosu (Türkiye geneli; Tire yalnız örnek ön ayardır)
"""
from __future__ import annotations

from qgis.core import (
    QgsCoordinateTransform,
    QgsCsException,
    QgsDistanceArea,
    QgsFeature,
    QgsFields,
    QgsGeometry,
    QgsPointXY,
    QgsSpatialIndex,
    QgsWkbTypes
)

from .tire_constants import (
    resolve_nip_density,
    identify_facility_category,
    MPYY_DONATI_STANDARTLARI,
    get_employment_for_function,
    get_trips_for_function,
    norm_tr,
    get_tucbs_info,
    OZEL_TAHSIS_ANAHTARLAR,
    DOP_DISI_ANAHTARLAR,
    DOP_YASAL_SINIR_YUZDE,
    ada_nufusu,
    dop_orani_hesapla,
    dop_uygunluk_metni,
    ek2_degerlendir,
    ek2_nufus_grubu_etiketi,
    ek2_standart,
    EK2_YESIL_KAMU_DOP_ASGARI_YUZDE,
)

# Projede elipsoit tanımlı değilken ("NONE") QgsDistanceArea düzlemsel ölçer;
# coğrafi veride alanlar derece² olur (TRAPS §5.8/§5.13). Sabit elipsoit kullanılır.
ELIPSOIT_YER_TUTUCULARI = ("", "NONE", "UNDEFINED")
VARSAYILAN_ELIPSOIT = "EPSG:7030"  # WGS 84 elipsoidi
VARSAYILAN_TAHMINI_YOL_PAYI = 0.18
DOP_YASAL_SINIR = DOP_YASAL_SINIR_YUZDE


class HesapIptalEdildi(Exception):
    """Kullanıcı işlemi iptal etti; hiçbir çıktı yazılmamalıdır."""


def build_distance_area(crs, transform_context, project_ellipsoid=None):
    """Kaynak KRS için her zaman elipsoit üzerinde ölçen bir QgsDistanceArea döndürür.

    Sıra: projenin elipsoidi (tanımlıysa) -> KRS'nin kendi elipsoidi -> EPSG:7030.
    Dönüş: (QgsDistanceArea, kullanılan_elipsoit, sabit_elipsoit_kullanildi_mi)
    """
    da = QgsDistanceArea()
    da.setSourceCrs(crs, transform_context)
    adaylar = [project_ellipsoid or "", crs.ellipsoidAcronym() if crs.isValid() else ""]
    for ell in adaylar:
        ell = (ell or "").strip()
        if ell.upper() in ELIPSOIT_YER_TUTUCULARI:
            continue
        da.setEllipsoid(ell)
        if da.willUseEllipsoid():
            return da, ell, False
    da.setEllipsoid(VARSAYILAN_ELIPSOIT)
    return da, VARSAYILAN_ELIPSOIT, True


def ensure_ellipsoidal(distance_area, transform_context=None):
    """Elipsoit kullanmayan bir QgsDistanceArea'yı KRS elipsoidi / EPSG:7030 ile değiştirir.

    Dönüş: (QgsDistanceArea, uyarı_metni_veya_None)
    """
    if distance_area is None or distance_area.willUseEllipsoid():
        return distance_area, None
    crs = distance_area.sourceCrs()
    if transform_context is None:
        from qgis.core import QgsProject
        transform_context = QgsProject.instance().transformContext()
    da, ell, _ = build_distance_area(crs, transform_context)
    uyari = None
    if crs.isValid() and crs.isGeographic():
        uyari = ("Proje elipsoidi tanımsız ('NONE'): coğrafi veride alanlar derece² olacaktı; "
                 f"alanlar {ell} elipsoidi üzerinde m² olarak ölçüldü.")
    return da, uyari


def metre_birimli_mi(crs) -> bool:
    """KRS'nin harita birimi metre mi? (coğrafi ve feet KRS'ler False)."""
    if crs is None or not crs.isValid() or crs.isGeographic():
        return False
    try:
        from qgis.core import Qgis
        metre = Qgis.DistanceUnit.Meters
    except AttributeError:  # QGIS < 3.30
        from qgis.core import QgsUnitTypes
        metre = QgsUnitTypes.DistanceUnit.DistanceMeters
    return crs.mapUnits() == metre


def transform_layer_geometries(layer, target_crs, transform_context):
    """Katman geometrilerini hedef KRS'ye dönüştürür. Dönüş: (geometriler, başarısız_sayısı)."""
    xform = None
    if layer.crs().isValid() and target_crs.isValid() and layer.crs() != target_crs:
        xform = QgsCoordinateTransform(layer.crs(), target_crs, transform_context)
    geoms, basarisiz = [], 0
    for f in layer.getFeatures():
        g = f.geometry()
        if g is None or g.isEmpty():
            continue
        g = QgsGeometry(g)
        if xform is not None:
            try:
                g.transform(xform)
            except QgsCsException:
                basarisiz += 1
                continue
        geoms.append(g)
    return geoms, basarisiz


def prepare_boundary_and_roads(target_crs, transform_context, distance_area,
                               sinir_layer=None, yol_layer=None):
    """Plan onama sınırını ve yol akslarını ada katmanının KRS'sine taşır (dock da kullanabilir).

    Dönüş: (sinir_geom_veya_None, yol_uzunlugu_m, uyarılar)
    """
    uyarilar = []
    sinir_geom = None
    if sinir_layer is not None:
        geoms, bas = transform_layer_geometries(sinir_layer, target_crs, transform_context)
        if bas:
            uyarilar.append(f"Plan onama sınırının {bas} geometrisi ada KRS'sine dönüştürülemedi ve atlandı.")
        if geoms:
            sinir_geom = QgsGeometry.unaryUnion(geoms)
        if sinir_layer.crs() != target_crs:
            uyarilar.append(
                f"Plan onama sınırı {sinir_layer.crs().authid()} -> {target_crs.authid()} KRS'sine dönüştürüldü.")
    yol_uzunlugu_m = 0.0
    if yol_layer is not None:
        geoms, bas = transform_layer_geometries(yol_layer, target_crs, transform_context)
        if bas:
            uyarilar.append(f"Yol katmanının {bas} geometrisi ada KRS'sine dönüştürülemedi ve atlandı.")
        for g in geoms:
            yol_uzunlugu_m += distance_area.measureLength(g) if distance_area else g.length()
        if yol_layer.crs() != target_crs:
            uyarilar.append(
                f"Yol aksları {yol_layer.crs().authid()} -> {target_crs.authid()} KRS'sine dönüştürüldü.")
    return sinir_geom, yol_uzunlugu_m, uyarilar


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
        analysis_mode: str = "nip",
        sinir_modu: str = "clip",
        kirsal_nufus: int = 0,
        kiyas_referanslari: dict | None = None,
        tahmini_yol_payi: float = VARSAYILAN_TAHMINI_YOL_PAYI,
        feedback=None,
        ek2_nufus: int | None = None
    ) -> tuple[list[dict], dict]:
        """Tüm öznitelikleri, Kamu-Özel dengesini, DOP ve kent karakter tablolarını üretir.

        kirsal_nufus: NİP nüfusuna eklenen kırsal nüfus (varsayılan 0, Türkiye geneli).
        kiyas_referanslari: tarihsel nüfus kıyas satırları (varsayılan yok; Tire örneği
            için tire_constants.NUFUS_KIYAS_ONAYARLARI["tire"]).
        tahmini_yol_payi: plan onama sınırı yokken yol alanı tahmini (adalar toplamına oran).
        ek2_nufus: MPYY EK-2 nüfus grubunu belirleyen ilçe projeksiyon nüfusu (EK-2
            Açıklama 1). Verilmezse projeksiyon_nufus kullanılır.
        feedback: iptal denetimi; iptal edilirse HesapIptalEdildi yükseltilir.
        """
        rules_config = rules_config or {}
        uyarilar = []
        distance_area, el_uyari = ensure_ellipsoidal(distance_area)
        if el_uyari:
            uyarilar.append(el_uyari)
        elenen = {"bos_geometri": 0, "sifir_alan": 0, "sinir_disi": 0, "fonksiyonu_bos": 0}
        dop_rules = rules_config.get("dop", {})
        emp_rules = rules_config.get("employment", {})
        trip_rules = rules_config.get("trips", {})
        
        # 1. Alan ve Fonksiyon Ön Taraması
        parsed_items = []
        residential_features = [] # (geom, alt_snr, ust_snr)
        
        sinir_kullanildi = (sinir_geom is not None and not sinir_geom.isEmpty())
        sinir_stats = {
            "aktif": sinir_kullanildi,
            "mod": sinir_modu,
            "sinir_modu": sinir_modu,
            "toplam_girdi": len(features),
            "toplam_girdi_ada": len(features),
            "tamamen_icinde": 0,
            "kesisen_kirpilan": 0,
            "kesisen_dahil": 0,
            "kesisen_elenen": 0,
            "kesisen_islenen": 0,
            "sinir_disi_elenen": 0,
            "isleme_alinan": 0,
            "islenen_ada_sayisi": 0
        }

        idx_fonk = source_fields.indexOf(fonksiyon_col) if fonksiyon_col else -1
        idx_sec = source_fields.indexOf(secondary_fonk_col) if secondary_fonk_col else -1
        idx_grup = source_fields.indexOf("grup_no") if "grup_no" in source_fields.names() else -1

        def _alan(g):
            return distance_area.measureArea(g) if distance_area else g.area()

        for feat in features:
            if feedback is not None and feedback.isCanceled():
                raise HesapIptalEdildi()
            geom = feat.geometry()
            if not geom or geom.isEmpty():
                elenen["bos_geometri"] += 1
                continue

            # 1.0 Plan Onama Sınırı Filtreleme ve Kırpma / Kesişim Yönetimi
            if sinir_kullanildi:
                if sinir_geom.disjoint(geom):
                    sinir_stats["sinir_disi_elenen"] += 1
                    continue

                if sinir_geom.contains(geom):
                    sinir_stats["tamamen_icinde"] += 1
                else:
                    # Sınırla kısmen kesişiyor (dışarı taşma var)
                    if sinir_modu == "clip":
                        clipped = geom.intersection(sinir_geom)
                        if (
                            not clipped 
                            or clipped.isEmpty() 
                            or clipped.type() != QgsWkbTypes.GeometryType.PolygonGeometry 
                            or _alan(clipped) <= 0.001
                        ):
                            sinir_stats["sinir_disi_elenen"] += 1
                            continue
                        geom = clipped
                        sinir_stats["kesisen_kirpilan"] += 1
                        sinir_stats["kesisen_islenen"] += 1
                    elif sinir_modu == "intersect":
                        sinir_stats["kesisen_dahil"] += 1
                        sinir_stats["kesisen_islenen"] += 1
                    elif sinir_modu == "within":
                        sinir_stats["kesisen_elenen"] += 1
                        sinir_stats["sinir_disi_elenen"] += 1
                        continue
                    elif sinir_modu == "centroid":
                        c = geom.centroid()
                        if c and not c.isEmpty() and sinir_geom.contains(c):
                            sinir_stats["kesisen_dahil"] += 1
                            sinir_stats["kesisen_islenen"] += 1
                        else:
                            sinir_stats["sinir_disi_elenen"] += 1
                            continue

            if not geom.isMultipart():
                geom.convertToMultiType()

            sinir_stats["isleme_alinan"] += 1

            # Alan hesapla (elipsoit üzerinde m²; derece² geri dönüşü yok)
            alan_m2 = _alan(geom)

            if alan_m2 <= 0.001:
                elenen["sifir_alan"] += 1
                continue

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

            if fonk_val.upper() == "NULL":
                fonk_val = ""
            if not fonk_val:
                elenen["fonksiyonu_bos"] += 1

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
            alt_nufus, ust_nufus = ada_nufusu(item["alan_ha"], item["alt_snr"], item["ust_snr"])
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
        donati_ozel_m2 = {cat: 0.0 for cat in MPYY_DONATI_STANDARTLARI}
        yesil_kamu_dop_m2 = 0.0
        stats_fonksiyonlar = {}

        for item in parsed_items:
            fonk = item["fonk_raw"]
            cat = identify_facility_category(fonk)
            item["donati_kategori"] = cat

            if cat:
                donati_stats[cat] += item["alan_m2"]
                if "ÖZEL" in item["dop_turu"]:
                    donati_ozel_m2[cat] += item["alan_m2"]
                elif cat == "YESIL_ALAN" and "KAMU" in item["dop_turu"]:
                    yesil_kamu_dop_m2 += item["alan_m2"]
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
            hesaplanan_yol_m2 = max(0.0, adalar_toplam_m2 * float(tahmini_yol_payi))
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
        dop_orani = dop_orani_hesapla(toplam_kamu_poligon_m2, hesaplanan_yol_m2, dop_esas_alan_m2)
        kamu_ozel_orani = round((toplam_kamu_kesinti_m2 / max(1.0, toplam_ozel_tahsis_m2)) * 100.0, 2)

        dop_ozet = {
            "sinir_katmani_kullanildi": sinir_kullanildi,
            "sinir_modu": sinir_modu if sinir_kullanildi else None,
            "sinir_filtre_ozet": sinir_stats if sinir_kullanildi else None,
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
            "yasal_sinir": DOP_YASAL_SINIR,
            # Sınır yokken yol alanı varsayılan bir paydır: yasal hüküm verilmez.
            "tahmini": not sinir_kullanildi,
            "tahmini_yol_payi": None if sinir_kullanildi else float(tahmini_yol_payi),
            "dop_uygunluk": dop_uygunluk_metni(dop_orani, sinir_kullanildi)
        }
        if not sinir_kullanildi:
            uyarilar.append(
                "Plan onama sınırı verilmedi: yol alanı adalar toplamının "
                f"%{float(tahmini_yol_payi) * 100:.0f}'i olarak TAHMİN edildi; DOP oranı tahminidir "
                f"ve yasal sınır (%{DOP_YASAL_SINIR:.0f}) değerlendirmesi yapılmadı."
            )

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
        # Standart, EK-2 Açıklama 1 uyarınca ilçe projeksiyon nüfusunun grubundan alınır.
        ek2_grup_nufusu = projeksiyon_nufus if ek2_nufus is None else ek2_nufus
        ek2_grup = ek2_nufus_grubu_etiketi(ek2_grup_nufusu)
        ek2_rapor = []
        for cat_id, info in MPYY_DONATI_STANDARTLARI.items():
            toplam_m2 = donati_stats.get(cat_id, 0.0)
            std = ek2_standart(cat_id, ek2_grup_nufusu)

            e_alt = ek2_degerlendir(toplam_m2, std, toplam_alt_nufus)
            e_ust = ek2_degerlendir(toplam_m2, std, toplam_ust_nufus)
            e_proj = ek2_degerlendir(toplam_m2, std, projeksiyon_nufus)

            ek2_rapor.append({
                "kategori_id": cat_id,
                "kategori_adi": info["adi"],
                "toplam_m2": round(toplam_m2, 2),
                "standart_m2": std,
                "nufus_grubu": ek2_grup,
                "ozel_m2": round(donati_ozel_m2.get(cat_id, 0.0), 2),
                "kb_alt": e_alt["kisi_basi_m2"],
                "kb_ust": e_ust["kisi_basi_m2"],
                "kb_proj": e_proj["kisi_basi_m2"],
                "gerekli_alt": e_alt["gerekli_m2"],
                "gerekli_ust": e_ust["gerekli_m2"],
                "gerekli_proj": e_proj["gerekli_m2"],
                "durum_alt": e_alt["durum"],
                "durum_ust": e_ust["durum"],
                "durum_proj": e_proj["durum"],
                "fark_alt": e_alt["fark_m2"],
                "fark_ust": e_ust["fark_m2"],
                "fark_proj": e_proj["fark_m2"]
            })

        yesil_toplam = donati_stats.get("YESIL_ALAN", 0.0)
        yesil_kamu_payi = round(yesil_kamu_dop_m2 / yesil_toplam * 100.0, 2) if yesil_toplam > 0 else None
        for r in ek2_rapor:
            if r["kategori_id"] == "YESIL_ALAN":
                r["kamu_dop_payi_yuzde"] = yesil_kamu_payi
        if yesil_kamu_payi is not None and yesil_kamu_payi < EK2_YESIL_KAMU_DOP_ASGARI_YUZDE:
            uyarilar.append(
                f"Açık ve yeşil alanlarda kamuya ait, DOP'a tabi alanların payı %{yesil_kamu_payi:.1f}; "
                f"MPYY EK-2 Açıklama 9'a göre bu pay %{EK2_YESIL_KAMU_DOP_ASGARI_YUZDE:.0f}'in altına düşürülemez.")
        ozel_sayilan = sum(donati_ozel_m2.values())
        if ozel_sayilan > 0:
            ozel_metni = f"{ozel_sayilan:,.0f}".replace(",", ".")
            uyarilar.append(
                f"Adında 'ÖZEL' geçen eğitim/sağlık/sosyal/kültürel tesisler "
                f"({ozel_metni} m²) MPYY EK-2 Açıklama 8 uyarınca kişi başı "
                "standarda sayıldı; bu sayım kamu-özel oranının ilgili Bakanlıkça belirlenmiş olmasına "
                "bağlıdır. DOP hesabında bu alanlar özel tahsistir.")

        # 9. Nüfus Kıyaslama Raporu (referanslar ve kırsal nüfus parametredir)
        kiyaslama = []
        for b_info in (kiyas_referanslari or {}).values():
            kiyaslama.append({
                "kapsam": b_info["kapsam"],
                "merkez": b_info["merkez"],
                "ilce": b_info["ilce"],
                "kaynak": b_info["kaynak"]
            })

        kirsal = max(0, int(kirsal_nufus or 0))
        if kirsal > 0:
            ilce_metni = f"{(toplam_alt_nufus + kirsal):,} - {(toplam_ust_nufus + kirsal):,}".replace(",", ".")
            kaynak_metni = f"PLN3113 NİP Analiz Modeli (Alt - Üst Sınır; kırsal nüfus +{kirsal:,})".replace(",", ".")
        else:
            ilce_metni = "Kırsal nüfus girilmedi"
            kaynak_metni = "PLN3113 NİP Analiz Modeli (Alt - Üst Sınır)"
        kiyaslama.append({
            "kapsam": f"Hesaplanan 1/5000 NİP Nüfusu ({toplam_alt_nufus:,} - {toplam_ust_nufus:,})".replace(",", "."),
            "merkez": f"{toplam_alt_nufus:,} - {toplam_ust_nufus:,}".replace(",", "."),
            "ilce": ilce_metni,
            "kaynak": kaynak_metni
        })

        # 10. Elenen adalar ve NULL değerler sessizce kaybolmaz
        if elenen["bos_geometri"]:
            uyarilar.append(f"{elenen['bos_geometri']} ada boş/geçersiz geometri nedeniyle hesaba katılmadı.")
        if elenen["sifir_alan"]:
            uyarilar.append(f"{elenen['sifir_alan']} adanın alanı sıfır ölçüldü ve hesaba katılmadı.")
        if sinir_kullanildi and sinir_stats["sinir_disi_elenen"]:
            elenen["sinir_disi"] = sinir_stats["sinir_disi_elenen"]
            uyarilar.append(f"{elenen['sinir_disi']} ada plan onama sınırı dışında kaldığı için elendi.")
        if elenen["fonksiyonu_bos"]:
            uyarilar.append(
                f"{elenen['fonksiyonu_bos']} adanın fonksiyon değeri boş (NULL); bu adalarda nüfus ve donatı 0 sayıldı.")
        if features and not parsed_items:
            uyarilar.append("Hiçbir ada hesaba girmedi: KRS, plan onama sınırı ve fonksiyon sütununu kontrol edin.")

        sinir_stats["islenen_ada_sayisi"] = len(parsed_items)
        sinir_stats["isleme_alinan"] = len(parsed_items)

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
            "sinir_filtre_ozet": sinir_stats if sinir_kullanildi else {"aktif": False},
            "fonksiyon_dagilim": fonksiyon_dagilim_list,
            "kent_karakter": kent_karakter_list,
            "ek2_rapor": ek2_rapor,
            "ek2_nufus_grubu": ek2_grup,
            "ek2_grup_nufusu": ek2_grup_nufusu,
            "kiyaslama": kiyaslama,
            "kirsal_nufus": kirsal,
            "elenen_ada": elenen,
            "uyarilar": uyarilar
        }

        return parsed_items, summary
