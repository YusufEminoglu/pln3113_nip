# -*- coding: utf-8 -*-
"""PLN3113 1/5000 NİP & DOP İnteraktif HTML Dashboard Builder.

Mekânsal Planlar Yapım Yönetmeliği (MPYY), 3194 sayılı İmar Kanunu Md. 18 (DOP)
ve PAİY Md. 9 standartlarını içeren; Plotly.js + Leaflet.js tabanlı,
yayın kalitesinde zengin interaktif analiz dashboard raporu üretir.

DEÜ Mimarlık Fakültesi Şehir ve Bölge Planlama Bölümü
PLN3113 - tire_nip
Geliştirici: Arş. Gör. Yusuf Eminoğlu
"""
from __future__ import annotations

import contextlib
from datetime import datetime
import json
import os
import tempfile

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsGeometry,
    QgsProject
)
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtGui import QDesktopServices

PLOTLY_URL = "https://cdn.plot.ly/plotly-2.27.0.min.js"
LEAFLET_JS_URL = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
LEAFLET_CSS_URL = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"


def build_nip_dashboard_html(summary: dict, parsed_items: list[dict],
                             sinir_geom: QgsGeometry = None,
                             crs: QgsCoordinateReferenceSystem = None,
                             ideal_dop: float = 45.0) -> str:
    """Tüm NİP ve DOP analiz verilerini interaktif HTML dashboard şablonuna dönüştürür."""
    if crs is None or not crs.isValid():
        crs = QgsCoordinateReferenceSystem("EPSG:5637")

    wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
    xform = QgsCoordinateTransform(crs, wgs84, QgsProject.instance())

    def to_geojson(geom: QgsGeometry):
        if geom is None or geom.isEmpty():
            return None
        g = QgsGeometry(geom)
        with contextlib.suppress(Exception):
            g.transform(xform)
        try:
            return json.loads(g.asJson())
        except Exception:
            return None

    # 1. GeoJSON Özellikleri (Plan Fonksiyon Adaları)
    ada_features = []
    category_colors = {
        "KONUT": "#fbbf24",
        "TICARET": "#ef4444",
        "SANAYI": "#a855f7",
        "TURIZM": "#f97316",
        "EGITIM": "#3b82f6",
        "SAGLIK": "#ec4899",
        "PARK": "#22c55e",
        "IBADET": "#14b8a6",
        "SOSYAL": "#6366f1",
        "RESMI": "#0284c7",
        "ALTYAPI": "#64748b",
        "TARIM": "#84cc16",
        "ORMAN": "#15803d",
        "SU": "#06b6d4",
        "DIGER": "#94a3b8"
    }

    for item in parsed_items:
        geom = item.get("geom")
        gj = to_geojson(geom)
        if gj is None:
            continue

        cat = item.get("donati_kategori") or "DIGER"
        fonk_u = item.get("fonk_raw", "").upper()
        if "KONUT" in fonk_u:
            cat = "KONUT"
        elif "TİCARET" in fonk_u or "TICARET" in fonk_u:
            cat = "TICARET"
        elif "SANAYİ" in fonk_u or "SANAYI" in fonk_u:
            cat = "SANAYI"
        elif "TURİZM" in fonk_u or "TURIZM" in fonk_u:
            cat = "TURIZM"

        ada_features.append({
            "type": "Feature",
            "properties": {
                "fid": item.get("fid", 0),
                "fonksiyon": item.get("fonk_raw", "-"),
                "kategori": cat,
                "alan_m2": round(item.get("alan_m2", 0.0), 1),
                "alan_ha": round(item.get("alan_ha", 0.0), 3),
                "dop_durumu": item.get("dop_durumu", "-"),
                "dop_turu": item.get("dop_turu", "-"),
                "alt_nufus": item.get("alt_nufus", 0),
                "ust_nufus": item.get("ust_nufus", 0),
                "color": category_colors.get(cat, "#0f766e")
            },
            "geometry": gj
        })

    plan_sinir_gj = to_geojson(sinir_geom)

    # 2. Metrikler ve Veri Paketi
    dop = summary.get("dop_ozet", {})
    ek2 = summary.get("ek2_rapor", [])
    fonk_list = summary.get("fonksiyon_dagilim", [])

    # Açık ve Yeşil Alan Payı Hesaplama (9. Madde: Park / Toplam Kamu Donatısı)
    toplam_kamu_donati_m2 = dop.get("kamu_poligonlar_m2", 0.0)
    yesil_alan_m2 = 0.0
    for it in parsed_items:
        fu = it.get("fonk_raw", "").upper()
        if any(k in fu for k in ["PARK", "YEŞİL", "YESIL", "ÇOCUK", "COCUK", "MEYDAN", "REKREASYON", "SPOR"]):
            if it.get("dop_durumu") == "DOP İÇİ":
                yesil_alan_m2 += it.get("alan_m2", 0.0)

    acik_yesil_dop_pct = round((yesil_alan_m2 / max(1.0, toplam_kamu_donati_m2)) * 100.0, 1)

    # En Büyük 12 Fonksiyon
    sorted_fonk = sorted(fonk_list, key=lambda x: -x.get("alan_m2", 0.0))[:12]

    # Ek-2 Karşılaştırmalı Grafikler Verisi
    ek2_kategoriler = []
    ek2_planlanan = []
    ek2_standart = []
    ek2_fark = []
    ek2_durum = []

    for r in ek2:
        ek2_kategoriler.append(r["kategori_adi"])
        ek2_planlanan.append(round(r.get("kb_ust", 0.0), 2))
        ek2_standart.append(round(r.get("standart_m2", 0.0), 2))
        ek2_fark.append(round(r.get("fark_ust", 0.0), 1))
        ek2_durum.append(r.get("durum_ust", "YETERLİ"))

    # Akıllı Öneri Metni Derleme
    oneri_metinleri = []
    dop_pct = dop.get("dop_orani", 0.0)
    if dop_pct > ideal_dop:
        fazla_m2 = (dop_pct - ideal_dop) / 100.0 * dop.get("dop_esas_alan_m2", 1.0)
        oneri_metinleri.append(
            f"⚠️ <b>DOP Oranı Aşımı Uyarısı:</b> Plan genelindeki DOP kesinti oranı (%{dop_pct:.2f}), "
            f"3194 sayılı Kanun 18. maddesindeki yasal üst sınır olan %{ideal_dop:.1f}'in üzerindedir. "
            f"Fazlalık miktarı yaklaşık <b>{fazla_m2:,.0f} m²</b>'dir.<br/>"
            f"<i>Tavsiye:</i> Planlı Alanlar İmar Yönetmeliği 9. maddesi gereğince, plandaki bazı kamu donatılarının "
            f"(Özel Eğitim, Özel Sağlık, Özel Sosyal Tesis vb.) %25'i geçmeyecek biçimde özel mülkiyet niteliğinde "
            f"tahsis edilmesi veya konut adaları yoğunluğunun revize edilmesi önerilir."
        )
    elif dop_pct < 40.0:
        oneri_metinleri.append(
            f"ℹ️ <b>Düşük DOP Kesintisi:</b> Hesaplanan DOP oranı (%{dop_pct:.2f}) yasal sınırın oldukça altındadır. "
            f"Bölgedeki kamusal donatı, park ve yol alanlarının artırılması plan kalitesini yükseltecektir."
        )
    else:
        oneri_metinleri.append(
            f"✅ <b>Yasal DOP Uyumu:</b> Hesaplanan DOP oranı (%{dop_pct:.2f}), %40.0 - %45.0 ideal aralığında olup "
            f"3194 sayılı Kanun Md. 18 hükümlerine tam uyumludur."
        )

    if acik_yesil_dop_pct < 75.0:
        oneri_metinleri.append(
            f"⚠️ <b>PAİY Md. 9 Açık ve Yeşil Alan Eşiği:</b> Kamusal donatılar içindeki açık ve yeşil alan payı "
            f"(%{acik_yesil_dop_pct:.1f}), yönetmelikte hedeflenen <b>%75.0</b> eşiğinin altındadır. "
            f"Park, çocuk bahçesi, meydan ve rekreasyon alanlarının oranının artırılması mevzuat açısından zorunludur."
        )
    else:
        oneri_metinleri.append(
            f"✅ <b>PAİY Md. 9 Açık ve Yeşil Alan Uyumu:</b> Açık ve yeşil alan oranı (%{acik_yesil_dop_pct:.1f}) "
            f"yasal %75.0 asgari koşulunu karşılamaktadır."
        )

    yetersiz_donatilar = [r["kategori_adi"] for r in ek2 if r.get("durum_ust") == "YETERSİZ"]
    if yetersiz_donatilar:
        oneri_metinleri.append(
            f"❗ <b>MPYY Ek-2 Asgari Standart Açığı:</b> Üst sınır nüfusa ({summary.get('toplam_ust_nufus', 0):,} kişi) göre "
            f"şu donatılarda yasal asgari m²/kişi standardı karşılanamamaktadır:<br/>"
            f"• <b>{', '.join(yetersiz_donatilar)}</b><br/>"
            f"Planlama kararlarında bu donatıların büyüklüklerinin genişletilmesi gerekmektedir."
        )
    else:
        oneri_metinleri.append(
            f"✅ <b>MPYY Ek-2 Tam Yeterlilik:</b> Hesaplanan plan nüfusu için MPYY Ek-2 tablosundaki tüm donatı grupları "
            f"yasal asgari standartları sağlamaktadır."
        )

    data_payload = {
        "summary": summary,
        "dop": dop,
        "acik_yesil_dop_pct": acik_yesil_dop_pct,
        "yesil_alan_m2": round(yesil_alan_m2, 1),
        "ideal_dop": ideal_dop,
        "ek2_kategoriler": ek2_kategoriler,
        "ek2_planlanan": ek2_planlanan,
        "ek2_standart": ek2_standart,
        "ek2_fark": ek2_fark,
        "ek2_durum": ek2_durum,
        "top_fonk_isim": [f.get("fonksiyon", "") for f in sorted_fonk],
        "top_fonk_alan": [f.get("alan_m2", 0.0) for f in sorted_fonk],
        "top_fonk_yuzde": [f.get("tum_plan_yuzdesi", 0.0) for f in sorted_fonk],
        "oneri_html": "<br/><br/>".join(oneri_metinleri),
        "rapor_zamani": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
        "ada_geojson": {"type": "FeatureCollection", "features": ada_features},
        "plan_sinir_geojson": {"type": "Feature", "geometry": plan_sinir_gj, "properties": {}} if plan_sinir_gj else None
    }

    data_json = json.dumps(data_payload, ensure_ascii=False).replace("</", "<\\/")
    return _RENDER_DASHBOARD_HTML(data_json, ideal_dop)


def open_nip_dashboard(summary: dict, parsed_items: list[dict],
                       sinir_geom: QgsGeometry = None,
                       crs: QgsCoordinateReferenceSystem = None,
                       ideal_dop: float = 45.0,
                       output_path: str = None) -> str:
    """Dashboard HTML dosyasını oluşturur ve varsayılan sistem tarayıcısında açar."""
    html_content = build_nip_dashboard_html(summary, parsed_items, sinir_geom, crs, ideal_dop)

    if not output_path:
        tmp_dir = tempfile.gettempdir()
        output_path = os.path.join(tmp_dir, f"pln3113_nip_dashboard_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    QDesktopServices.openUrl(QUrl.fromLocalFile(output_path))
    return output_path


def _RENDER_DASHBOARD_HTML(data_json: str, ideal_dop: float) -> str:
    return _HTML_TEMPLATE.replace('__PLOTLY_URL__', PLOTLY_URL) \
        .replace('__LEAFLET_JS_URL__', LEAFLET_JS_URL) \
        .replace('__LEAFLET_CSS_URL__', LEAFLET_CSS_URL) \
        .replace('__IDEAL_DOP__', str(ideal_dop)) \
        .replace('"__DATA_JSON__"', data_json)


_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PLN3113 1/5000 NİP & DOP Kentsel Analiz Dashboard</title>
<link rel="stylesheet" href="__LEAFLET_CSS_URL__"/>
<script src="__PLOTLY_URL__"></script>
<script src="__LEAFLET_JS_URL__"></script>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: #f8fafc; color: #1e293b; line-height: 1.5; }
.header { background: linear-gradient(135deg, #0f766e 0%, #115e59 100%); color: #fff; padding: 22px 32px; box-shadow: 0 4px 12px rgba(15,118,110,0.15); }
.header h1 { font-size: 22px; font-weight: 700; margin-bottom: 4px; letter-spacing: -0.3px; display: flex; align-items: center; gap: 10px; }
.header .subtitle { opacity: 0.9; font-size: 13px; font-weight: 400; }
.container { padding: 20px; max-width: 1700px; margin: auto; }
.tab-bar { display: flex; gap: 4px; margin-bottom: 16px; border-bottom: 2px solid #e2e8f0; flex-wrap: wrap; }
.tab { padding: 10px 18px; background: #e2e8f0; border-radius: 8px 8px 0 0; cursor: pointer; font-size: 13.5px; color: #475569; font-weight: 600; transition: all .15s; }
.tab:hover { background: #cbd5e1; color: #0f766e; }
.tab.active { background: #fff; color: #0f766e; border: 2px solid #e2e8f0; border-bottom: 2px solid #fff; margin-bottom: -2px; }
.tab-content { display: none; }
.tab-content.active { display: block; animation: fadeIn .2s ease-in; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(2px); } to { opacity: 1; transform: none; } }
.row { display: grid; gap: 16px; margin-bottom: 16px; }
.row.cols-4 { grid-template-columns: repeat(4, 1fr); }
.row.cols-3 { grid-template-columns: repeat(3, 1fr); }
.row.cols-2 { grid-template-columns: 1fr 1fr; }
@media(max-width: 1024px) { .row.cols-4, .row.cols-3, .row.cols-2 { grid-template-columns: 1fr!important; } }
.card { background: #fff; border-radius: 10px; padding: 16px 20px; box-shadow: 0 1px 4px rgba(0,0,0,0.05); border: 1px solid #e2e8f0; }
.card h3 { font-size: 13px; color: #64748b; margin-bottom: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; border-bottom: 1px solid #f1f5f9; padding-bottom: 6px; }
.kpi { display: flex; flex-direction: column; justify-content: center; }
.kpi .val { font-size: 28px; font-weight: 800; color: #0f766e; line-height: 1.1; }
.kpi .lbl { font-size: 11.5px; color: #64748b; text-transform: uppercase; font-weight: 600; margin-top: 4px; }
.kpi .sub { font-size: 12px; color: #475569; margin-top: 6px; }
.status-pill { display: inline-block; padding: 4px 12px; border-radius: 12px; font-size: 12px; font-weight: 700; }
.status-pill.success { background: #dcfce7; color: #15803d; }
.status-pill.warning { background: #fef3c7; color: #b45309; }
.status-pill.danger { background: #fee2e2; color: #b91c1c; }
#map { height: 560px; border-radius: 8px; border: 1px solid #cbd5e1; }
.tbl { width: 100%; border-collapse: collapse; font-size: 13px; }
.tbl th { background: #f8fafc; color: #475569; padding: 10px 12px; text-align: left; font-weight: 700; border-bottom: 2px solid #e2e8f0; }
.tbl td { padding: 9px 12px; border-bottom: 1px solid #f1f5f9; }
.tbl tr:hover { background: #f1f5f9; }
.tbl td.num { text-align: right; font-variant-numeric: tabular-nums; }
.oneri-box { background: #fffbeb; border-left: 5px solid #f59e0b; padding: 16px 20px; border-radius: 6px; font-size: 14px; line-height: 1.7; color: #78350f; }
.legal-box { background: #f0fdf4; border-left: 5px solid #10b981; padding: 16px 20px; border-radius: 6px; font-size: 13.5px; line-height: 1.7; margin-bottom: 14px; }
.footer { text-align: center; color: #94a3b8; padding: 20px; font-size: 12px; border-top: 1px solid #e2e8f0; margin-top: 30px; }
</style>
</head>
<body>

<div class="header">
  <h1>🏛️ Dokuz Eylül Üniversitesi | PLN3113 1/5000 NİP & DOP Analiz Dashboard</h1>
  <div class="subtitle">3194 sayılı İmar Kanunu Md. 18 (DOP) · MPYY Ek-2 Kentsel Donatı Standartları · PAİY Md. 9 Açık-Yeşil Analizi · Rapor Tarihi: <span id="lbl_tarih"></span></div>
</div>

<div class="container">
  <div class="tab-bar">
    <div class="tab active" data-tab="genel">📊 1. Genel & DOP Analizi</div>
    <div class="tab" data-tab="ek2">🏫 2. MPYY Ek-2 Donatı Yeterliliği</div>
    <div class="tab" data-tab="harita">🗺️ 3. Mekânsal Plan Haritası</div>
    <div class="tab" data-tab="fonk">🏷️ 4. Fonksiyon Dağılımı</div>
    <div class="tab" data-tab="oneri">💡 5. Akıllı Öneriler & Mevzuat</div>
    <div class="tab" data-tab="kilavuz">📖 6. Yasal Metodoloji & Formüller</div>
  </div>

  <!-- SEKME 1: GENEL & DOP ANALİZİ -->
  <div class="tab-content active" data-tab="genel">
    <div class="row cols-4">
      <div class="card kpi">
        <div class="val" id="kpi_plan_alan">-</div>
        <div class="lbl">Plan Onama Alanı</div>
        <div class="sub" id="kpi_ada_sayisi">-</div>
      </div>
      <div class="card kpi">
        <div class="val" id="kpi_nufus">-</div>
        <div class="lbl">Plan Nüfusu (Alt - Üst)</div>
        <div class="sub" id="kpi_yogunluk">-</div>
      </div>
      <div class="card kpi">
        <div class="val" id="kpi_etkin_alan">-</div>
        <div class="lbl">DOP Esas Alan (Etkin)</div>
        <div class="sub" id="kpi_haric_alan">-</div>
      </div>
      <div class="card kpi">
        <div class="val" id="kpi_dop_orani">-</div>
        <div class="lbl">Hesaplanan DOP Oranı</div>
        <div class="sub"><span class="status-pill" id="pill_dop_durum">-</span></div>
      </div>
    </div>

    <div class="row cols-2">
      <div class="card">
        <h3>1. 3194 Sayılı Kanun Md. 18 — DOP Oranı Göstergesi (Yasal Eşik %__IDEAL_DOP__)</h3>
        <div id="chart_dop_gauge" style="height:320px;"></div>
      </div>
      <div class="card">
        <h3>2. Global 1/5000 NİP Alan Bileşimi</h3>
        <div id="chart_alan_donut" style="height:320px;"></div>
      </div>
    </div>

    <div class="row cols-2">
      <div class="card">
        <h3>3. PAİY Md. 9 — Açık ve Yeşil Alan Oranı (DOP İçinde Asgari Hedef %75)</h3>
        <div id="chart_yesil_gauge" style="height:300px;"></div>
      </div>
      <div class="card">
        <h3>4. m² / Kişi Dağılımı (Plan Bütünü)</h3>
        <div id="chart_m2_kisi_bar" style="height:300px;"></div>
      </div>
    </div>
  </div>

  <!-- SEKME 2: MPYY EK-2 DONATI YETERLİLİĞİ -->
  <div class="tab-content" data-tab="ek2">
    <div class="row cols-2">
      <div class="card">
        <h3>5. MPYY Ek-2: Planlanan vs. Yasal Asgari Donatı Karşılaştırması (m² / Kişi)</h3>
        <div id="chart_ek2_bar" style="height:360px;"></div>
      </div>
      <div class="card">
        <h3>6. Donatı Fazlası / Açığı (m² Alan Bazında)</h3>
        <div id="chart_ek2_fark" style="height:360px;"></div>
      </div>
    </div>
    <div class="card">
      <h3>MPYY Ek-2 Kentsel Donatı Standartları Detay Tablosu</h3>
      <div style="overflow-x:auto;">
        <table class="tbl" id="tbl_ek2"></table>
      </div>
    </div>
  </div>

  <!-- SEKME 3: MEKÂNSAL PLAN HARİTASI -->
  <div class="tab-content" data-tab="harita">
    <div class="card">
      <h3>🗺️ İnteraktif 1/5000 NİP Mekânsal Plan Haritası (Ada ve Donatı Sınırları)</h3>
      <div id="map"></div>
    </div>
  </div>

  <!-- SEKME 4: FONKSİYON DAĞILIMI -->
  <div class="tab-content" data-tab="fonk">
    <div class="card">
      <h3>7. En Büyük 12 NİP Fonksiyonunun Alan Büyüklüğü (m²)</h3>
      <div id="chart_top_fonk" style="height:440px;"></div>
    </div>
    <div class="card" style="margin-top:16px;">
      <h3>Tüm NİP Fonksiyonları Detay Tablosu</h3>
      <div style="overflow-x:auto;">
        <table class="tbl" id="tbl_fonksiyonlar"></table>
      </div>
    </div>
  </div>

  <!-- SEKME 5: AKILLI ÖNERİLER & MEVZUAT -->
  <div class="tab-content" data-tab="oneri">
    <div class="card">
      <h3>💡 Otomatik NİP & DOP Mevzuat ve Planlama Tavsiyeleri</h3>
      <div class="oneri-box" id="box_oneri"></div>
    </div>
  </div>

  <!-- SEKME 6: YASAL METODOLOJİ & FORMÜLLER -->
  <div class="tab-content" data-tab="kilavuz">
    <div class="card">
      <h3>3194 Sayılı İmar Kanunu Madde 18 — Düzenleme Ortaklık Payı (DOP) Formülü</h3>
      <div class="legal-box">
        <b>DOP Esas Alan (Etkin Alan)</b> = Toplam Plan Alanı − Hariç Alanlar (Tarım, Orman, Sit, Koruma vb.)<br/>
        <b>Toplam Kesinti (Kamu Payı)</b> = Kamu Donatı Alanları + Yol Terk Alanları<br/>
        <b>DOP Oranı (%)</b> = (Toplam Kesinti / DOP Esas Alan) × 100<br/>
        <br/>
        <b>Yasal Eşik:</b> 7181 sayılı Kanun ile 3194 sayılı İmar Kanunu 18. maddesinde yapılan değişiklik uyarınca azami DOP oranı <b>%45.0</b>'dir.
      </div>
      <h3>Planlı Alanlar İmar Yönetmeliği (PAİY) Madde 9 — Açık ve Yeşil Alan Kuralı</h3>
      <div class="legal-box">
        "Düzenleme ortaklık payına tabi çocuk bahçesi, oyun alanı, park, meydan ve semt spor alanları oranı toplamı <b>%75'in altına düşürülemez.</b>"
      </div>
      <h3>Mekânsal Planlar Yapım Yönetmeliği (MPYY) Ek-2 Standartları</h3>
      <div class="legal-box">
        Nüfus büyüklüğüne göre kişi başına ayrılması zorunlu asgari donatı alanları:<br/>
        • Eğitim Tesisleri Alanı: 5.00 m²/kişi<br/>
        • Sağlık Tesisleri Alanı: 2.00 m²/kişi<br/>
        • Açık ve Yeşil Alanlar (Park/Çocuk Bahçesi/Meydan): 10.00 m²/kişi<br/>
        • Sosyal ve Kültürel Tesis Alanı: 1.50 m²/kişi<br/>
        • İbadet Alanı: 0.50 m²/kişi<br/>
        • Teknik Altyapı: 0.50 m²/kişi
      </div>
    </div>
  </div>

  <div class="footer">
    Dokuz Eylül Üniversitesi Mimarlık Fakültesi Şehir ve Bölge Planlama Bölümü | PLN3113 Şehir Planlama Projesi III<br/>
    Hazırlayan: Arş. Gör. Yusuf Eminoğlu | PlanX QGIS Eklenti Ekosistemi
  </div>
</div>

<script>
const DATA = "__DATA_JSON__";
const IDEAL_DOP = DATA.ideal_dop || 45.0;

function fmt(n) { return (n || 0).toLocaleString('tr-TR', { maximumFractionDigits: 1 }); }

// Header & KPI
document.getElementById('lbl_tarih').innerText = DATA.rapor_zamani;
document.getElementById('kpi_plan_alan').innerText = fmt(DATA.dop.toplam_plan_alani_ha) + ' ha';
document.getElementById('kpi_ada_sayisi').innerText = fmt(DATA.dop.toplam_plan_alani_m2) + ' m² (' + (DATA.summary.sinir_filtre_ozet.islenen_ada_sayisi || DATA.ada_geojson.features.length) + ' ada)';
document.getElementById('kpi_nufus').innerText = fmt(DATA.summary.toplam_alt_nufus) + ' - ' + fmt(DATA.summary.toplam_ust_nufus);
const brutYog = DATA.dop.toplam_plan_alani_ha > 0 ? (DATA.summary.toplam_ust_nufus / DATA.dop.toplam_plan_alani_ha).toFixed(1) : 0;
document.getElementById('kpi_yogunluk').innerText = 'Brüt Yoğunluk: ' + brutYog + ' kişi/ha';
document.getElementById('kpi_etkin_alan').innerText = fmt(DATA.dop.dop_esas_alan_m2) + ' m²';
document.getElementById('kpi_haric_alan').innerText = 'Hariç: ' + fmt(DATA.dop.dop_disi_alan_m2) + ' m²';
document.getElementById('kpi_dop_orani').innerText = '%' + DATA.dop.dop_orani.toFixed(2);

const pill = document.getElementById('pill_dop_durum');
if (DATA.dop.dop_orani <= IDEAL_DOP) {
  pill.className = 'status-pill success';
  pill.innerText = 'YASAL SINIRDA (UYGUN)';
} else {
  pill.className = 'status-pill danger';
  pill.innerText = 'YASAL SINIRI AŞIYOR (+%' + (DATA.dop.dop_orani - IDEAL_DOP).toFixed(2) + ')';
}

document.getElementById('box_oneri').innerHTML = DATA.oneri_html;

// Tab Değiştirme
document.querySelectorAll('.tab').forEach(t => {
  t.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(x => x.classList.remove('active'));
    t.classList.add('active');
    document.querySelector('.tab-content[data-tab="' + t.dataset.tab + '"]').classList.add('active');
    setTimeout(() => {
      window.dispatchEvent(new Event('resize'));
      if (window._map) window._map.invalidateSize();
    }, 100);
  });
});

const cfg = { displayModeBar: false, responsive: true };

// 1. DOP GAUGE
Plotly.newPlot('chart_dop_gauge', [{
  type: 'indicator',
  mode: 'gauge+number+delta',
  value: DATA.dop.dop_orani,
  delta: { reference: IDEAL_DOP, increasing: { color: '#ef4444' }, decreasing: { color: '#10b981' } },
  gauge: {
    axis: { range: [0, 80], tickwidth: 1, tickcolor: '#64748b' },
    bar: { color: '#0f766e', thickness: 0.35 },
    steps: [
      { range: [0, 40], color: '#fef3c7' },
      { range: [40, IDEAL_DOP], color: '#dcfce7' },
      { range: [IDEAL_DOP, 80], color: '#fee2e2' }
    ],
    threshold: { line: { color: '#000', width: 3 }, thickness: 0.85, value: IDEAL_DOP }
  },
  number: { suffix: '%', valueformat: '.2f' }
}], { margin: { t: 30, b: 10, l: 30, r: 30 } }, cfg);

// 2. ALAN DONUT
const donutLabels = ['Özel Mülkiyet (Tahsis)', 'Yol Terkleri', 'Kamu Donatıları'];
const donutValues = [DATA.dop.toplam_ozel_tahsis_m2, DATA.dop.hesaplanan_yol_m2, DATA.dop.kamu_poligonlar_m2];
const donutColors = ['#3b82f6', '#94a3b8', '#10b981'];

if (DATA.dop.dop_disi_alan_m2 > 0) {
  donutLabels.push('Hariç / Plan Dışı');
  donutValues.push(DATA.dop.dop_disi_alan_m2);
  donutColors.push('#f59e0b');
}

Plotly.newPlot('chart_alan_donut', [{
  type: 'pie',
  hole: 0.55,
  labels: donutLabels,
  values: donutValues,
  marker: { colors: donutColors },
  textinfo: 'label+percent',
  insidetextorientation: 'radial'
}], { margin: { t: 20, b: 20, l: 20, r: 20 }, legend: { orientation: 'h', y: -0.1 } }, cfg);

// 3. AÇIK VE YEŞİL ALAN GAUGE
Plotly.newPlot('chart_yesil_gauge', [{
  type: 'indicator',
  mode: 'gauge+number',
  value: DATA.acik_yesil_dop_pct,
  gauge: {
    axis: { range: [0, 100], tickcolor: '#64748b' },
    bar: { color: '#16a34a', thickness: 0.35 },
    steps: [
      { range: [0, 75], color: '#fee2e2' },
      { range: [75, 100], color: '#dcfce7' }
    ],
    threshold: { line: { color: '#000', width: 3 }, thickness: 0.85, value: 75.0 }
  },
  number: { suffix: '%', valueformat: '.1f' }
}], { margin: { t: 25, b: 10, l: 30, r: 30 } }, cfg);

// 4. m² / KİŞİ BAR
const ustNufus = Math.max(1, DATA.summary.toplam_ust_nufus);
const m2_kamu = DATA.dop.kamu_poligonlar_m2 / ustNufus;
const m2_yol = DATA.dop.hesaplanan_yol_m2 / ustNufus;
const m2_ozel = DATA.dop.toplam_ozel_tahsis_m2 / ustNufus;
const m2_etkin = DATA.dop.dop_esas_alan_m2 / ustNufus;

Plotly.newPlot('chart_m2_kisi_bar', [{
  type: 'bar',
  orientation: 'h',
  y: ['Kamu Donatısı', 'Yol Terki', 'Özel Alan', 'Etkin Alan'],
  x: [m2_kamu, m2_yol, m2_ozel, m2_etkin],
  marker: { color: ['#10b981', '#94a3b8', '#3b82f6', '#0f766e'] },
  text: [m2_kamu.toFixed(2), m2_yol.toFixed(2), m2_ozel.toFixed(2), m2_etkin.toFixed(2)].map(v => v + ' m²/kişi'),
  textposition: 'outside'
}], { margin: { t: 10, b: 30, l: 120, r: 60 }, xaxis: { title: 'm² / Kişi (Üst Sınır Nüfusa Göre)' } }, cfg);

// 5. MPYY EK-2 BAR
Plotly.newPlot('chart_ek2_bar', [
  {
    type: 'bar',
    name: 'Planlanan (m²/kişi)',
    x: DATA.ek2_kategoriler,
    y: DATA.ek2_planlanan,
    marker: { color: '#0f766e' },
    text: DATA.ek2_planlanan.map(v => v.toFixed(2)),
    textposition: 'auto'
  },
  {
    type: 'bar',
    name: 'Yasal Asgari Standart (m²/kişi)',
    x: DATA.ek2_kategoriler,
    y: DATA.ek2_standart,
    marker: { color: '#f59e0b' },
    text: DATA.ek2_standart.map(v => v.toFixed(2)),
    textposition: 'auto'
  }
], { barmode: 'group', margin: { t: 20, b: 60, l: 40, r: 20 }, legend: { orientation: 'h', y: -0.2 } }, cfg);

// 6. MPYY EK-2 FARK BAR
Plotly.newPlot('chart_ek2_fark', [{
  type: 'bar',
  x: DATA.ek2_kategoriler,
  y: DATA.ek2_fark,
  marker: { color: DATA.ek2_fark.map(v => v >= 0 ? '#10b981' : '#ef4444') },
  text: DATA.ek2_fark.map(v => (v >= 0 ? '+' : '') + fmt(v) + ' m²'),
  textposition: 'outside'
}], { margin: { t: 20, b: 60, l: 60, r: 20 }, yaxis: { title: 'Fark (Planlanan - Gerekli m²)' } }, cfg);

// Tablo: Ek-2
let ek2Html = '<thead><tr><th>Donatı Kategorisi</th><th>Planlanan Alan (m²)</th><th>Standart (m²/kişi)</th><th>Planlanan (m²/kişi)</th><th>Fark (m²)</th><th>Yeterlilik Durumu</th></tr></thead><tbody>';
for (let i = 0; i < DATA.ek2_kategoriler.length; i++) {
  const isOk = DATA.ek2_durum[i] === 'YETERLİ';
  ek2Html += '<tr>' +
    '<td><b>' + DATA.ek2_kategoriler[i] + '</b></td>' +
    '<td class="num">' + fmt(DATA.summary.ek2_rapor[i].toplam_m2) + '</td>' +
    '<td class="num">' + DATA.ek2_standart[i].toFixed(2) + '</td>' +
    '<td class="num"><b>' + DATA.ek2_planlanan[i].toFixed(2) + '</b></td>' +
    '<td class="num" style="color:' + (DATA.ek2_fark[i] >= 0 ? '#15803d' : '#b91c1c') + ';font-weight:700;">' + (DATA.ek2_fark[i] >= 0 ? '+' : '') + fmt(DATA.ek2_fark[i]) + '</td>' +
    '<td><span class="status-pill ' + (isOk ? 'success' : 'danger') + '">' + DATA.ek2_durum[i] + '</span></td>' +
    '</tr>';
}
ek2Html += '</tbody>';
document.getElementById('tbl_ek2').innerHTML = ek2Html;

// 7. EN BÜYÜK 12 FONKSİYON
Plotly.newPlot('chart_top_fonk', [{
  type: 'bar',
  orientation: 'h',
  y: DATA.top_fonk_isim.slice().reverse(),
  x: DATA.top_fonk_alan.slice().reverse(),
  marker: { color: '#0f766e' },
  text: DATA.top_fonk_alan.slice().reverse().map(v => fmt(v) + ' m²'),
  textposition: 'outside'
}], { margin: { t: 20, b: 40, l: 240, r: 60 }, xaxis: { title: 'Alan (m²)' } }, cfg);

// Tablo: Fonksiyonlar
let fonkHtml = '<thead><tr><th>Fonksiyon</th><th>DOP Durumu</th><th>DOP Türü</th><th>Adet</th><th>Alan (m²)</th><th>Plan Payı (%)</th><th>Kişi Başı (m²)</th></tr></thead><tbody>';
DATA.summary.fonksiyon_dagilim.forEach(f => {
  fonkHtml += '<tr>' +
    '<td><b>' + f.fonksiyon + '</b></td>' +
    '<td>' + f.dop_durumu + '</td>' +
    '<td>' + f.dop_turu + '</td>' +
    '<td class="num">' + f.adet + '</td>' +
    '<td class="num">' + fmt(f.alan_m2) + '</td>' +
    '<td class="num">%' + f.tum_plan_yuzdesi.toFixed(2) + '</td>' +
    '<td class="num">' + (f.kisi_basi_m2 || 0).toFixed(2) + '</td>' +
    '</tr>';
});
fonkHtml += '</tbody>';
document.getElementById('tbl_fonksiyonlar').innerHTML = fonkHtml;

// 8. LEAFLET HARİTASI
const map = L.map('map');
window._map = map;
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '© OpenStreetMap katkıcıları',
  maxZoom: 19
}).addTo(map);

if (DATA.ada_geojson && DATA.ada_geojson.features.length > 0) {
  const adaLayer = L.geoJSON(DATA.ada_geojson, {
    style: f => ({
      color: f.properties.color || '#0f766e',
      weight: 1.5,
      fillColor: f.properties.color || '#0f766e',
      fillOpacity: 0.45
    }),
    onEachFeature: (f, layer) => {
      const p = f.properties;
      layer.bindTooltip('<b>' + p.fonksiyon + '</b><br/>' + fmt(p.alan_m2) + ' m²', { sticky: true });
      layer.bindPopup(
        '<div style="font-size:13px; min-width:180px;">' +
        '<b style="color:#0f766e; font-size:14px;">' + p.fonksiyon + '</b><hr style="margin:4px 0; border:none; border-top:1px solid #e2e8f0;"/>' +
        'Alan: <b>' + fmt(p.alan_m2) + ' m²</b> (' + p.alan_ha + ' ha)<br/>' +
        'DOP: <b>' + p.dop_durumu + '</b><br/>' +
        'Tür: ' + p.dop_turu + '<br/>' +
        'Nüfus (Alt-Üst): ' + p.alt_nufus + ' - ' + p.ust_nufus + ' kişi' +
        '</div>'
      );
    }
  }).addTo(map);

  if (DATA.plan_sinir_geojson) {
    L.geoJSON(DATA.plan_sinir_geojson, {
      style: { color: '#dc2626', weight: 3, dashArray: '6, 6', fillOpacity: 0 }
    }).addTo(map);
  }

  try { map.fitBounds(adaLayer.getBounds(), { padding: [20, 20] }); }
  catch (e) { map.setView([38.08, 27.73], 13); }
} else {
  map.setView([38.08, 27.73], 13);
}
</script>
</body>
</html>
"""
