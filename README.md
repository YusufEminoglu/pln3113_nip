# PLN3113 NİP ve Kentsel Analiz Stüdyosu

> [!IMPORTANT]
> **SADECE TÜRKÇE (ONLY TR) & DEÜ ŞBP ÖĞRENCİLERİ İÇİN ÖZEL:**  
> Bu eklenti yalnızca **Türkçe** dilinde ve Türkiye mekânsal planlama mevzuatı/uygulaması için geliştirilmiştir. **Dokuz Eylül Üniversitesi Mimarlık Fakültesi Şehir ve Bölge Planlama Bölümü (DEÜ ŞBP)** lisans programı **PLN3113 Şehir Planlama Projesi III** öğrencileri ve stüdyo yürütücüleri için özel olarak tasarlanmıştır.

**Geliştirici:** Arş. Gör. Yusuf Eminoğlu (Dokuz Eylül Üniversitesi, Şehir ve Bölge Planlama Bölümü)  
**Akademik Profil:** [AVESIS](https://avesis.deu.edu.tr/yusuf.eminoglu) | [GitHub](https://github.com/YusufEminoglu)  
**Ders:** PLN3113 Şehir Planlama Projesi III — 1/5000 Nazım İmar Planı ve Saha Entegrasyonu  
**Lisans:** GPL-2.0-or-later  
**Kaynak Kod:** [https://github.com/YusufEminoglu/tire_nip](https://github.com/YusufEminoglu/tire_nip)

---

## 📌 Eklentinin Amacı ve Kapsamı
Bu eklenti; PLN3113 stüdyosu kapsamında öğrencilerin Tire 1/5000 Nazım İmar Planı (NİP) sayısal verilerini (`nipt_test.gpkg`), saha adası tespitlerini ve bina katmanlarını (`tire_bina.gpkg`) hızlı, hatasız ve bilimsel/yasal standartlara uygun olarak analiz etmelerini sağlamak amacıyla geliştirilmiştir.

Eklenti 3 temel analiz modülünden, 1-tıkla tematik harita motorundan ve dahili interaktif teorik rehberden oluşur:

---

### 1. Modül: 1/5000 NİP Nüfus, Donatı, DOP ve Mülkiyet Analizi
- **Yoğunluk Eşleme:** Lejanttaki fonksiyon adlarını (`Ort__Detay`, `Ort_Detay`, `nipfonksiyon`) tanıyarak `ALT_SNR` ve `UST_SNR` brüt yoğunluklarını (kişi/hektar) otomatik atar.
- **Karma Kullanım (Ticaret-Konut) Kuralı:** Mekânsal komşuluğundaki en yakın konut adalarının yoğunluğunun **%30'unu** karma konut yoğunluğu olarak atar.
- **Brüt Plan Nüfusu:** `ALT_NUFUS` (`AlanHa × ALT_SNR`) ve `UST_NUFUS` (`AlanHa × UST_SNR`) hesaplar.
- **Dinamik Kurallar Tablosu (9 Sütun):** Katmandan gelen tüm hücre değerleri için tek tek:
  1. *Plan Fonksiyonu*
  2. *DOP İçi (Dahil)?* &rarr; Onay kutusuyla düzenleme sahasına dahil etme veya nDOP (DOP Dışı - Harice Ayrılan) yapma imkanı.
  3. *DOP Türü* &rarr; "DOP İçi - Özel (Tahsis)" vs "DOP İçi - Kamu (Kesinti)" vs "nDOP - DOP Dışı (Hariç)".
  4. *İstihdam Dahil?*
  5. *m² / Çalışan Standartı*
  6. *Verim Oranı (0 - 1.0)*
  7. *Araç Dahil?*
  8. *Yaya Dahil?*
  9. *Araç Katsayısı (100 m² Başına PAU)*
- **3194 Sayılı Kanun md. 18 ve DOP Hesabı:** Plan Onama Sınırına veya ada geometrilerine göre net yol alanını, düzenleme sahasını, toplam özel tahsis ve kamu kesintisini hesaplar; yasal %45 tavanına uygunluğunu test eder.
- **MPYY Ek-2 Donatı Yeterliliği:** Eğitim, Sağlık, Kültürel/Sosyal, Açık ve Yeşil Alan, Teknik Altyapı ve İbadet donatıları için kişi başı m² değerlerini hesaplar ve yeterlilik tablosu üretir.
- **Tire Nüfus Karşılaştırma Göstergesi:** 1997 Plan Raporu (1990 DİE: 37.855 merkez / 77.314 ilçe), 2015 Plan Hedefi (53.629 merkez / 100.340 ilçe), 2015 TÜİK ADNKS (56.750 merkez / 82.102 ilçe), Güncel TÜİK ADNKS (61.738 merkez / 87.571 ilçe) verileri ile canlı kıyaslama sunar.
- **Dışa Aktarma:** 4 analiz tablosunu UTF-8 Excel CSV olarak kaydeder ve eksiksiz HTML raporu üretir.

---

### 2. Modül: Kentsel Veri ve Nüfus Projeksiyon Merkezi
- **Kendini Kesen Geometrilerin Onarımı:** Bozuk poligonları `makeValid` ve tampon toleransı ile onarır.
- **Mükerrer (Duplike) Poligon Ayıklama:** Üst üste binen çift poligonları hassas koordinat ve SHA-256 geometri hash kontrolüyle tekilleştirir.
- **Matematiksel Nüfus Projeksiyonları:** Doğrusal (Aritmetik), Geometrik (Bileşik Artış), Üstel (Eksponansiyel) ve İller Bankası Formülü ile hedef yıl nüfus projeksiyonları üretir.

---

### 3. Modül: Saha & Bina Morfolojisi ve Fiili Nüfus (PlanX Morfoloji Motoru & Spacematrix)
- Kadastro/Tapu adaları ile bina poligonlarını mekânsal olarak birleştirir (Spatial Join).
- **Planlama İlkesi Koruması:** Sanayi, OSB, depo, mezarlık, saf ticaret ve park alanlarında yaşayan nüfus kesinlikle **0** atanır (yalnızca istihdam ve araç/yaya çekimi hesaplanır).
- Konut ve Karma Kullanım adalarında bağımsız bölüm ve kat adetlerinden hareketle TÜİK hanehalkı büyüklüğü (~2.85 kişi) üzerinden ada bazında fiili yaşayan nüfus ve brüt yoğunluk (`FIILI_BRUT_YOGUNLUK_HA`) hesaplanır.
- **Kentsel Morfoloji Metrikleri:**
  - `FIILI_TAKS` (Ground Space Index - GSI): Zemin doluluk katsayısı ($\sum \text{Taban } m^2 / \text{Ada } m^2$).
  - `FIILI_KAKS` (Floor Space Index - FSI / Emsal): Kat alanı katsayısı ($\sum \text{İnşaat } m^2 / \text{Ada } m^2$).
  - `ORT_KAT` (Layers - L): Ağırlıklı ortalama kat adedi ($\text{İnşaat } m^2 / \text{Taban } m^2$).
  - `ACIK_ALAN_YUZDE`: Ada zeminindeki bahçe/avlu açık alan oranı ($\%$).
  - `SPACEMATRIX_OSR`: Open Space Ratio / Açık Alan Oranı ($(1 - GSI) / FSI$).
  - `BINA_YOGUNLUK_HA`: Hektar başına bina sayısı.
  - `ORT_KOMPAKLIK_IPQ`: Binaların izoperimetrik form kompaklığı ($4\pi \cdot Alan / Çevre^2$).
  - `YAPI_NIZAMI` (A4): PlanX kentsel morfoloji motoruna uygun olarak: **Ayrık**, **Bitişik / Blok**, **Karma (Ayrık + Bitişik)** veya **Boş Ada** tespiti (Disjoint-Set komşuluk grafı).
  - `MAX_BITISIK_DIZI`: Adadaki birbirine yapışık en uzun bina zincirinin (zarfın) parça sayısı.
  - `DOKU_TIPI`: Spacematrix kentsel tipoloji sınıflandırması (Seyrek Bahçeli, Orta Yoğunluk, Kompakt Blok, Nokta Kuleler, Geleneksel Doku).
- **🎨 1-Tıkla Tematik Harita Üretimi:**
  - `👥 Nüfus (k/ha)`
  - `🏗️ TAKS (GSI)`
  - `🏢 KAKS (FSI / Emsal)`
  - `📏 Kat Sayısı (L)`
  - `🌳 Açık Alan (%)`
  - `🏘️ Yapı Nizamı (A4)`
  - `📐 Doku / Spacematrix`

---

## 🚀 Kurulum

### Yöntem A (QGIS Eklenti Yöneticisi ile ZIP'ten Kurulum):
1. QGIS menüsünden **Eklentiler -> Eklentileri Yönet ve Kur...** seçeneğini açın.
2. Sol menüden **ZIP'ten Kur** sekmesine gelin.
3. `QGIS_Plugin_Releases/pln3113_nip.zip` dosyasını seçip **Eklentiyi Kur** butonuna tıklayın.

### Yöntem B (Doğrudan Klasör Kopyalama):
`pln3113_nip` klasörünü QGIS profilinizdeki `python/plugins/` dizinine kopyalayın:
`%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\pln3113_nip`  
Ardından QGIS'i yeniden başlatıp Eklenti Yöneticisi'nden aktif hale getirin.

---

## 📖 Metodoloji ve Dokümantasyon
Eklenti arayüzünün sağ üst köşesinde yer alan **"📚 Metodoloji Rehberi"** butonuna basarak, eklentinin arka planında çalışan tüm formülleri, MPYY Ek-2 katsayılarını, kurallar tablosunu ve morfoloji metodolojisini tane tane açıklayan detaylı interaktif HTML rehberini görüntüleyebilirsiniz.
