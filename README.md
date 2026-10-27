# PLN3113 NİP ve Kentsel Analiz Stüdyosu

> [!NOTE]
> **[TR ONLY] Universal Turkish Master Plan (NİP) Studio Toolset:**  
> Bu eklenti Türkçe dilinde ve Türkiye mekânsal planlama mevzuatı/uygulamaları için geliştirilmiştir. **PLN3113 Şehir Planlama Projesi III** stüdyosu başta olmak üzere; Türkiye'deki tüm üniversitelerin Şehir ve Bölge Planlama bölümlerinde 1/5000 Nazım İmar Planı, analitik etüt, kentsel morfoloji ve ulaşım ağı çalışmaları yürüten lisans/lisansüstü öğrencileri ile şehir plancıları için evrensel uyumlu bir stüdyo laboratuvarıdır.

**Geliştirici:** Geophilo  
**Akademik Profil:** [AVESIS](https://avesis.deu.edu.tr/yusuf.eminoglu) | [GitHub](https://github.com/YusufEminoglu)  
**Lisans:** GPL-2.0-or-later  
**Kaynak Kod:** [https://github.com/YusufEminoglu/pln3113_nip](https://github.com/YusufEminoglu/pln3113_nip)

---

## 📌 Eklentinin Vizyonu ve Mimari Kapsamı

1/5000 ölçekli Nazım İmar Planı (NİP) hazırlık süreçleri; nüfus yoğunluk dağılımından donatı dengesine, Düzenleme Ortaklık Payı (DOP) hesaplarından cadde-sokak morfolojisi ve yaya erişilebilirliğine kadar çok boyutlu mekânsal analizler gerektirir. 

**PLN3113 NİP ve Kentsel Analiz Stüdyosu**, bu iş akışlarını parçalı scriptlerden çıkarıp; Mekânsal Planlar Yapım Yönetmeliği (MPYY) normları, 3194 sayılı İmar Kanunu md. 18 ilkeleri ve gömülü **PlanX** kentsel analitik motoruyla tek bir panelde birleştiren profesyonel bir CBS stüdyosudur.

---

## 🛠️ Modül ve Araç Envanteri (7 Temel Sekme & 15 Processing Algoritması)

Eklenti arayüzü 7 ana navigasyon sekmesinden oluşur ve arka planda 15 bağımsız QGIS Processing algoritması barındırır:

### 1. 🧹 Geometri Onarımı ve Topolojik Temizlik
- **Self-Intersection & Geçersizlik Onarımı:** Dışarıdan içe aktarılan veya çizim sırasında bozulan plan poligonlarını GEOS `makeValid` ve hassas tampon toleranslarıyla topolojik olarak onarır.
- **SHA-256 Mükerrer (Duplike) Ayıklama:** Üst üste binen ada veya parsel çiftlerini katı koordinat ve SHA-256 geometri hash kontrolüyle tespit ederek mükerrer alan hesaplamalarını önler.
- **Topolojik Hata Noktaları:** Boşluk, çakışma ve geometri hatalarını harita üzerinde özel sembolojiyle raporlar.

### 2. 🗄️ NİP Çizim Veritabanı ve Şablon Kurulumu (GeoPackage)
- **Çift Şablon Mimarisi:**
  - **MPYY 1.1.7 Standart Veritabanı:** 87 resmî plan fonksiyon tablosu, MPGM kodlaması ve 1-tıkla resmî QML stil entegrasyonu.
  - **Yerel NİP İlişkisel Şablon:** 7 temel planlama tablosu (Arazi Kullanım, Ulaşım, Donatı, Kentsel Dönüşüm, Eşikler vb.), ilişkisel lookup indeksleri ve hazır tematik stiller.
- **Taşınabilirlik:** Tek bir `.gpkg` dosyası üzerinden tüm stüdyo ekibinin aynı veri standardında çalışmasını garanti eder.

### 3. 🛣️ Yol Platformu, Bordür ve Kavşak Geometrisi
- **Aks Hiyerarşisi:** 7m, 10m, 12m, 15m, 20m, 25m, 30m, 35m ve 50m'lik yol akslarına göre yol gövdesi, tretuvar, refüj ve bordür sınırlarını parametrik üretir.
- **Teğet Yaylı (Fillet) Kavşak Yayları:** Kesişen yol akslarında EasyFillet motoruyla dönüş yarıçaplarına ($R=3m, 5m, 8m, 10m, 12m$) uygun pürüzsüz kavşak kavisleri çizer.
- **Ada Sınırına Kapatma & Poligonlaştırma:** Çizilen yol bordür çizgilerinden imar adalarını otomatik poligonlaştırır (`Polygonize`).

### 4. 🏙️ NİP Nüfus, Donatı (MPYY Ek-2) ve DOP Analizi
- **Dinamik Yoğunluk Eşleme:** Plan lejantındaki fonksiyonları (`Ort__Detay`, `Ort_Detay`, `nipfonksiyon`) tanıyarak `ALT_SNR` ve `UST_SNR` brüt yoğunluklarını (kişi/hektar) otomatik atar.
- **Karma Kullanım (Ticaret-Konut) Kuralı:** Mekânsal komşuluğundaki en yakın konut adalarının yoğunluğunun %30'unu karma konut yoğunluğu olarak modele katar.
- **Dinamik Kurallar Tablosu (9 Sütun):** Plan fonksiyonu, DOP Dahil?, DOP Türü (Özel Tahsis / Kamu Kesintisi / nDOP), İstihdam Dahil?, m²/Çalışan, Verim Oranı, Araç/Yaya Katsayılarını hücre bazında düzenleme imkanı.
- **3194 / Madde 18 DOP Dengesi:** Düzenleme ortaklık payını hesaplar, yasal %45 tavanına uygunluğunu test eder.
- **MPYY Ek-2 Asgari Donatı Karnesi:** Eğitim, Sağlık, Sosyal/Kültürel, Yeşil Alan, Teknik Altyapı ve İbadet donatıları için kişi başı düşen m² miktarını yasal eşiklerle kıyaslar.
- **Demografik Projeksiyon Motoru:** Doğrusal (Aritmetik), Geometrik (Bileşik), Üstel ve İller Bankası formülüyle hedef yıl projeksiyonları sunar.

### 5. 🏠 Saha Morfolojisi, Bina Tipolojisi ve Fiili Nüfus
- **Kadastro & Bina Entegrasyonu:** Adalar ile bina kütlelerini mekânsal birleştirir (`Spatial Join`).
- **Planlama İlkesi Koruması:** Sanayi, OSB, park, mezarlık gibi konut dışı fonksiyonlarda yaşayan nüfus kesinlikle 0 atanır (yalnızca istihdam ve yolculuk çekimi hesaplanır).
- **Kentsel Morfoloji & Spacematrix Metrikleri:**
  - `FIILI_TAKS` (Ground Space Index - GSI): Zemin doluluk katsayısı.
  - `FIILI_KAKS` (Floor Space Index - FSI / Emsal): Kat alanı katsayısı.
  - `ORT_KAT` (Layers - L): Ağırlıklı ortalama kat yüksekliği.
  - `ACIK_ALAN_YUZDE` & `SPACEMATRIX_OSR`: Açık alan oranı ve açık hava hacmi.
  - `YAPI_NIZAMI` (A4): PlanX kentsel morfoloji grafı ile **Ayrık**, **Bitişik/Blok**, **Karma** veya **Boş Ada** tespiti.
  - `DOKU_TIPI`: Spacematrix kentsel doku tipolojisi (Seyrek Bahçeli, Kompakt Blok, Nokta Blok vb.).
- **1-Tıkla Tematik Harita Motoru:** Nüfus, TAKS, KAKS, Kat Sayısı, Açık Alan ve Yapı Nizamı tematik paftalarını anında stillendirir.

### 6. 🚶 Kentsel Ağ, Yaya Erişimi ve Space Syntax Suiti
- **Space Syntax (Aksiyel Entegrasyon):** NACH (Normalized Angular Choice) ve NAIN (Normalized Angular Integration) metrikleri ile kentin omurga koridorlarını modeller.
- **Primal Ağ Merkeziliği:** Closeness (Yakınlık) ve Betweenness (Aradalık) merkezilik analizleri.
- **Yol Eğimi Analizi:** DEM rasterından her yol segmentinin eğim yüzdesini hesaplar ve engelli/yaya erişilebilirlik sınırlarını kademelendirir.
- **Bina Ön Cephe & Servis Noktası:** Ada veya bina poligonlarının yol ağına en uygun cephe/giriş kapı noktalarını otomatik bulur.
- **OD Arzu Hatları ve Dijkstra Rotalama:** Konut odaklarından donatılara en kısa yol ve kuş uçuşu arzu hatlarını çizer; 1.35 üzerindeki Detour Ratio değerlerini bariyerli aks olarak raporlar.
- **Dinamik Yürüme İzokronları (Concave Hull Pedshed):** Kullanıcı tanımlı eşiklerle (örn: 200m, 400m, 600m veya 400m, 800m, 1200m) yürüyüş havzaları üretir. Büyük poligonların küçükleri örtmesini engelleyen çizim sırası ve collinear dejenere geometri koruması barındırır.
- **2SFCA (İki Aşamalı Yüzen Havza Modeli):** Donatı kapasiteleri ve nüfus talebini ağ mesafesiyle ağırlıklandırarak donatı yeterliliğini (Yeterli, Aşırı Yüklü, Kullanılmayan) hem nokta hem bina/ada poligonu düzeyinde modeller.
- **A/B Senaryo Karşılaştırması:** Yeni açılan yol veya donatı senaryolarının erişim farklarını delta metrikleriyle ortaya koyar.

### 7. 📚 İnteraktif Teorik & Metodolojik El Kitabı
- Eklenti panelinden doğrudan tarayıcıda açılabilen 70+ KB zengin içerikli teorik kılavuz:
  - Formüller, MPYY Ek-2 katsayıları, DOP hesaplama tabloları, jüri sunum stratejileri ve 15 analitik aracın adım adım uygulama senaryoları.

---

## 🚀 Kurulum

### Yöntem A: QGIS Plugin Hub (Resmî Depo)
1. QGIS menüsünden **Eklentiler &rarr; Eklentileri Yönet ve Kur...** penceresini açın.
2. Arama çubuğuna **PLN3113** veya **NİP** yazın.
3. **PLN3113 NİP ve Kentsel Analiz Stüdyosu** eklentisini seçip **Eklentiyi Kur** butonuna tıklayın.

### Yöntem B: ZIP Paketinden Kurulum
1. `QGIS_Plugin_Releases/pln3113_nip.zip` dosyasını indirin.
2. QGIS'te **Eklentiler &rarr; Eklentileri Yönet ve Kur &rarr; ZIP'ten Kur** sekmesine gidin ve zip dosyasını gösterip kurun.

---

## 🏛️ Akademik Dayanak ve Yasal Mevzuat
* **3194 Sayılı İmar Kanunu** (Madde 18 Düzenleme Ortaklık Payı ve Parselasyon Esasları)
* **Mekânsal Planlar Yapım Yönetmeliği (MPYY)** (Ek-2 Kentsel Sosyal ve Teknik Altyapı Standartları)
* **Planlı Alanlar İmar Yönetmeliği (PAİY)** (Yapılaşma şartları, TAKS, KAKS ve çekme mesafeleri)
* **PlanX Kentsel Analitik Motoru** (Açık kaynak mekânsal analiz ve morfoloji algoritmaları)
