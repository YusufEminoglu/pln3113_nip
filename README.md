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

## 🛠️ Modül ve Araç Envanteri (21 Processing Algoritması)

Eklenti paneli 8 sayfadan oluşur (Geometri, Veritabanı, Yol/Kavşak, Nüfus, NİP & DOP, Saha/Yapı, Network, Rehber). Hesaplar 7 grupta toplanan 21 QGIS Processing algoritmasıyla yapılır; hepsi `pln3113` sağlayıcısı altında Processing araç kutusunda ve model tasarımcısında da kullanılabilir.

### 1. 🧹 Geometri Onarımı ve Topolojik Temizlik
- **Self-Intersection & Geçersizlik Onarımı:** Dışarıdan içe aktarılan veya çizim sırasında bozulan plan poligonlarını GEOS `makeValid` ve hassas tampon toleranslarıyla topolojik olarak onarır.
- **SHA-256 Mükerrer (Duplike) Ayıklama:** Üst üste binen ada veya parsel çiftlerini katı koordinat ve SHA-256 geometri hash kontrolüyle tespit ederek mükerrer alan hesaplamalarını önler.
- **Topolojik Hata Noktaları:** Boşluk, çakışma ve geometri hatalarını harita üzerinde özel sembolojiyle raporlar.

### 2. 🗄️ NİP Çizim Veritabanı ve Şablon Kurulumu (GeoPackage)
- **Çift Şablon Mimarisi:**
  - **MPYY 1.1.7 Standart Veritabanı:** 87 resmî plan fonksiyon tablosu, MPGM kodlaması ve 1-tıkla resmî QML stil entegrasyonu.
  - **Yerel NİP İlişkisel Şablon:** 7 temel planlama tablosu (Arazi Kullanım, Ulaşım, Donatı, Kentsel Dönüşüm, Eşikler vb.), ilişkisel lookup indeksleri ve hazır tematik stiller.
- **Taşınabilirlik:** Tek bir `.gpkg` dosyası üzerinden tüm stüdyo ekibinin aynı veri standardında çalışmasını garanti eder.
- **⚠ Kontrol sütunu (MPYY 1.1.7):** Her çizim katmanının öznitelik tablosunun başında, nesnedeki sorunları yazan bir sanal alan bulunur: geçersiz geometri, 50 m²'den küçük parça, 1 m'den kısa çizgi, boş zorunlu öznitelik, aynı katmanda ya da başka bir arazi kullanımıyla/yol platformuyla çakışma (ortak alan ≥ 1 m²; kenar paylaşmak çakışma değildir), plan sınırı dışına taşma, platformu üretilmemiş Yolorta. Çizim engellenmez; sorunlu satırlar tabloda kırmızı, formda uyarı olarak görünür ve öğrenci tabloyu bu sütuna göre süzerek düzeltir. Kurallar katman stiliyle GeoPackage'a kaydedilir, XSD şemasına sütun eklenmez. Sınır, koruma, afet tehlike, havza ve mania gibi bindirme katmanları arazi kullanımıyla çakışabilir.
- **NİP Denetimi (`pln3113:nip_mpyy_denetim`):** Bütün GeoPackage'ı birlikte tarar; geçersiz geometrinin yerini, çakışan ortak alanı, plan sınırı içinde hiçbir kullanıma ayrılmamış boşlukları ve diğer bulguları tek bir katmana yazar. Kayıtlı veriyi okur.

### 3. 🛣️ Yol Platformu, Bordür ve Kavşak Geometrisi
- **MPYY Yol Çiz (planX CAD yol aracı mantığıyla):** Yol tipi, şerit sayısı ve genişliği, refüj ve kaldırım girilir, orta aks haritada çizilir (Backspace geri alır, sağ tık/Enter bitirir). Ek-1e'de NİP yolları üç tabloya birlikte çizilir: `Yolorta` (YolTip, YolGenisligi = toplam platform), `DigerYolNesneleri` (taşıt yolu, refüj, kaldırım poligonları) ve `AdaKenari` (platformun dış kenarları). Var olan bir yolu kesen yeni yolda kavşak açılır: platform parçaları birbiriyle çakışmaz, ada kenarları karşı platformda kesilir. Kavşak köşeleri yuvarlanır: ada kenarı "Kavşak köşe yarıçapı" R ile (varsayılan 8 m, 0 yazılırsa yuvarlanmaz), bordür onunla eş merkezli R + kaldırım yarıçapıyla; köşedeki kaldırım eşit genişlikte bir halka olarak kalır. Yuvarlama her açıda çalışır (morfolojik kapanış). Kavşak bölgesine sığmayan dolgular, örneğin iki yakın yol arasındaki dar bir adayı yutacak olanlar, uygulanmaz.
- **Yolorta'dan Platform (`pln3113:nip_mpyy_yol_platform`):** Daha önce çizilmiş Yolorta akslarından, YolGenisligi ve verilen kaldırım/refüj ile platformu toplu üretir; platformu olan aksları atlar.
- **Aks Hiyerarşisi:** 7m, 10m, 12m, 15m, 20m, 25m, 30m, 35m ve 50m'lik yol akslarına göre yol gövdesi, tretuvar, refüj ve bordür sınırlarını parametrik üretir.
- **Teğet Yaylı (Fillet) Kavşak Yayları:** Kesişen yol akslarında EasyFillet motoruyla dönüş yarıçaplarına ($R=3m, 5m, 8m, 10m, 12m$) uygun pürüzsüz kavşak kavisleri çizer.
- **Ada Sınırına Kapatma & Poligonlaştırma:** Çizilen yol bordür çizgilerinden imar adalarını otomatik poligonlaştırır (`Polygonize`).

### 4. 🏙️ NİP Nüfus, Donatı (MPYY Ek-2) ve DOP Analizi
- **Dinamik Yoğunluk Eşleme:** Plan lejantındaki fonksiyonları (`Ort__Detay`, `Ort_Detay`, `nipfonksiyon`) tanıyarak `ALT_SNR` ve `UST_SNR` brüt yoğunluklarını (kişi/hektar) otomatik atar.
- **Karma Kullanım (Ticaret-Konut) Kuralı:** Mekânsal komşuluğundaki en yakın konut adalarının yoğunluğunun %30'unu karma konut yoğunluğu olarak modele katar.
- **Dinamik Kurallar Tablosu (9 Sütun):** Plan fonksiyonu, DOP Dahil?, DOP Türü (Özel Tahsis / Kamu Kesintisi / nDOP), İstihdam Dahil?, m²/Çalışan, Verim Oranı, Araç/Yaya Katsayılarını hücre bazında düzenleme imkanı.
- **3194 / Madde 18 DOP Dengesi:** Düzenleme ortaklık payını hesaplar ve yasal %45 tavanını aşıp aşmadığını gösterir. Panelde %45 "yasal tavan" olarak yazılır: bir hedef değil, aşılmaması gereken üst sınırdır.
- **Plan Sınırı Olmadan DOP:** Plan onama sınırı katmanı verilmezse yol alanı adalar toplamının belirli bir payı olarak tahmin edilir (varsayılan 0,18; parametre olarak değiştirilebilir). Sonuç "TAHMİNİ DOP ORANI" olarak etiketlenir ve yasal uygunluk kararı verilmez.
- **MPYY Ek-2 Asgari Donatı Karnesi:** Eğitim, Sağlık, Sosyal/Kültürel, Yeşil Alan, Teknik Altyapı ve İbadet donatıları için kişi başı düşen m² miktarını Mekânsal Planlar Yapım Yönetmeliği EK-2 tablosuyla kıyaslar. Standart, ilçe projeksiyon nüfusunun EK-2 grubuna göre seçilir (0-75.000, 75.001-150.000, 150.001-500.000, 501.000+; EK-2 Açıklama 1): eğitim 6,5 / 6,5 / 6,6 / 6,6; sağlık 1,5 / 1,5 / 1,5 / 1,6; sosyal ve kültürel 0,75 / 1 / 1,25 / 1,5; açık ve yeşil alan 10; teknik altyapı (yol ve otopark hariç) 1 / 1,25 / 1,5 / 2; ibadet 0,5 / 0,5 / 0,75 / 0,75 m²/kişi. Semt spor alanı açık-yeşil alan standardına dahildir (Açıklama 9); genel spor alanı ve pasif yeşil/refüj için EK-2'de kişi başı satır yoktur. Adında "ÖZEL" geçen eğitim, sağlık, sosyal ve kültürel tesisler kişi başı standarda sayılır (Açıklama 8) ama DOP hesabında özel tahsistir. Açık-yeşil alanlarda kamuya ait, DOP'a tabi alanların payı %75'in altındaysa uyarı verilir. İl bütünü planlamasına özgü +5 m²/kişi (hayvanat bahçesi, kent ormanı vb., Açıklama 10) NİP ölçeğinde uygulanmaz.
- **Bölgeye Özgü Ayarlar:** Kırsal nüfus eki ve nüfus kıyaslama değerleri sabit değildir, parametre olarak girilir (kırsal nüfus eki varsayılanı 0). Tire yalnızca örnek ön ayar olarak durur.
- **Boş Değerler ve Elenen Adalar:** Boş ya da geçersiz geometri, sıfır alan veya plan sınırı dışında kaldığı için hesaptan çıkarılan adalar ve fonksiyon değeri boş olan adalar sayılıp uyarı olarak bildirilir. 2SFCA donatı yeterliliği aracında nüfusu boş (NULL) olan talep noktaları 0 kişi, kapasitesi boş olan donatılar varsayılan kapasiteyle hesaba girer; her iki durumda kayıt sayısı uyarı olarak verilir.

> [!IMPORTANT]
> **Ek-2 kaynağı.** Değerler Mekânsal Planlar Yapım Yönetmeliği (RG 14.06.2014/29030) md. 11 ve EK-2 tablosunun (Değişik: RG 17.05.2017/30069; sonraki değişiklikler EK-2'yi değiştirmedi) mevzuat.gov.tr'deki resmî metniyle satır satır karşılaştırılmıştır (erişim 4 Kasım 2026). Yönetmelik değişirse yürürlükteki metni esas alın; çevre düzeni planı kentsel asgari standartları ayrıca belirleyebilir (md. 11/2).

### 4a. 📈 Nüfus Projeksiyonu, Kohort, Mahalle Dağıtımı ve Kırılganlık
Bu dört araç Processing araç kutusunda "07. Nüfus Projeksiyonu, Dağıtım ve Kırılganlık" grubundadır ve paneldeki Nüfus sayfasından açılabilir.

- **Trend Projeksiyonu** (`pln3113:nufus_projeksiyonu`): Aritmetik, geometrik, İller Bankası, en küçük kareler (doğrusal regresyon), 2. derece polinom ve lojistik yöntemler. Her yöntem için R² ve geriye dönük sınama hatası (son gözlem çıkarılarak kurulan modelin o yıldaki yüzde hatası) verilir; sonuçlar özet tablo ve yıllık seri tablosu olarak yazılır.
  İller Bankası yönteminde yıllık artış hızı varsayılan olarak %1-%3 aralığına çekilir ve çekildiğinde uyarı verilir. Lojistik yöntemde doygunluk nüfusu (K) verilmezse hatayı en küçükleyen K aranır; arama sınırına dayanırsa uyarı verilir. Pearl-Reed üç nokta biçimi isteğe bağlıdır.
  "Üstel" yöntem yoktur: iki gözlem noktasında geometrik yöntemle aynı sonucu verir.
- **Panelle Bağlantı:** Paneldeki Nüfus sayfasında hesaplanan projeksiyon sonucu NİP hedef nüfus kutusuna (50 milyona kadar) aktarılabilir; hedef nüfusu elle girmek de mümkündür.
- **Kohort-Bileşen Projeksiyonu** (`pln3113:kohort_projeksiyonu`): 17 beş yaşlık grup (0-4 ... 80+), iki cinsiyet ve beşer yıllık adımlarla çalışır. Doğumlar 0-4 yaş grubuna doğumdan 0-4'e yaşama oranıyla aktarılır; hedef yıl beşlik adıma düşmüyorsa komşu adımlar arasında ara değer hesaplanır.
  Varsayılan sağkalım oranları (Sx), yaşa özel doğurganlık hızları (ASFR) ve göç yaş profili kaynak notlarıyla birlikte `core/data/kohort_varsayilan.json` dosyasındadır. Sx ve doğumdan 0-4'e yaşama oranı TÜİK "Hayat Tabloları, 2023-2025" bülteninin "Cinsiyete göre Türkiye tek yaş hayat tablosu" tablosundan (T(x) = l(x)·e(x) ile beşli gruplara), ASFR TÜİK "Doğum İstatistikleri, 2025" bülteninin "Yaşa özel doğurganlık hızları" tablosundan (2025; TDH 1,42), doğumda cinsiyet oranı aynı bültenin "Cinsiyet ve aya göre doğumlar" tablosundan (2025; 105,62) alınmıştır. Değerler Türkiye geneli içindir; göç yaş profili model değeridir. İl/ilçe verisi varsa araçta kendi değerlerinizi girin.
  Net göç yıllık oran ya da yıllık kişi sayısı olarak girilir ve yaş profiline göre dağıtılır. Çıktılar: yaş piramidi tablosu (her adım ve hedef yıl için yaş grubu × cinsiyet) ve gösterge tablosu (bağımlılık oranları, yaşlanma endeksi, medyan yaş, doğum, net göç).
- **Ekonomik Taban Göçü:** Trend projeksiyonu aracında isteğe bağlıdır. Yeni istihdam "çalışan başına nüfus" katsayısıyla (varsayılan 2,7 kişi/çalışan) göç eden nüfusa çevrilir ve her yöntemin sonucuna ayrıca eklenir.
- **Mahalle Dağıtımı** (`pln3113:mahalle_dagitimi`): Hedef nüfus mahallelere oransal, planlama bölgesi payına göre ya da kapasite sınırlı olarak dağıtılır; kapasitesi dolan mahalleye düşen fazla pay diğer mahallelere yeniden dağıtılır, hiçbir yere sığmayan nüfus "dağıtılamayan" olarak bildirilir.
  En büyük kalan yöntemiyle yapılan tam sayı yuvarlaması toplamı korur; sonuç seçilen anahtar alanla mahalle katmanına bağlanır.
- **Kırılganlık Endeksi** (`pln3113:kirilganlik_endeksi`): Her gösterge 1-5 puanlanır; kırılganlığı artıran göstergeler (maruziyet, hassasiyet) pay, uyum kapasitesini gösterenler paydada yer alır (pay/payda yöntemi). Deprem (K_D), sel ve taşkın (K_Y) ve aşırı sıcak (K_S) için hazır endeksler vardır; eşikleri Tire örneğine göre seçilmiştir, başka yerleşimde gözden geçirin. Kendi göstergelerinizle özel endeks (varsayılan kodu K_O) de tanımlanabilir.
  Endeksler 0-100 aralığına ölçeklenip ağırlıklı ortalamayla bileşik endeks hesaplanır; varsayılan ağırlıklar K_D 0,40, K_Y 0,35, K_S 0,25 ve K_O 0,25'tir ve değiştirilebilir.
  Kategori değerleri Türkçe karakter ve büyük/küçük harften bağımsız eşleşir ("YIĞMA" = "yığma"). Bir bölgede göstergenin değeri yoksa uydurma değer konmaz: puan 1 (çarpımda etkisiz) alınır ve bölgenin eksik gösterge sayısına yazılır.
  Nüfus göstergesi mutlak kişi sayısıyla değil yoğunlukla (kişi/ha) puanlanır. Sel ve taşkın endeksinde dereye yakınlık, düşük göreli yükseklik ve düşük eğim kırılganlığı artırır.
  Sınıflar Jenks (doğal kırılma), eşit sayılı (quantile), eşit aralıklı ya da geometrik aralıklı olarak ayrılır; sonuç anahtar alanla katmana bağlanır. İsteğe bağlı HTML raporundaki metinler kaçışlanarak (escape) yazılır.

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
- **Space Syntax (Segment Açısal Analiz):** Yol ağını segmentlere ayırarak açısal NACH (Normalized Angular Choice) ve NAIN (Normalized Angular Integration) değerlerini hesaplar.
  Motor PlanX 4.23.0 ile aynıdır: NAIN = NC^1.2 / (TD + 2) ve seçim (choice) yönlü segment uçları üzerinden sayılır, bu yüzden çıkmaz sokak segmentleri seçim değeri almaz. Analiz yarıçapları yer metresidir.
  1.1.6 ve öncesiyle üretilen değerler bu sürümle karşılaştırılamaz; yeniden hesaplayın. İşlem iptal edilirse yarım sonuç yazılmaz.
- **Primal Ağ Merkeziliği:** Closeness (Yakınlık) ve Betweenness (Aradalık) merkezilik analizleri.
- **Yol Eğimi Analizi:** DEM rasterından her yol segmentinin eğim yüzdesini hesaplar ve engelli/yaya erişilebilirlik sınırlarını kademelendirir.
- **Bina Ön Cephe & Servis Noktası:** Ada veya bina poligonlarının yol ağına en uygun cephe/giriş kapı noktalarını otomatik bulur.
- **OD Arzu Hatları ve Dijkstra Rotalama:** Konut odaklarından donatılara en kısa yol ve kuş uçuşu arzu hatlarını çizer; 1.35 üzerindeki Detour Ratio değerlerini bariyerli aks olarak raporlar.
- **Dinamik Yürüme İzokronları (Concave Hull Pedshed):** Kullanıcı tanımlı eşiklerle (örn: 200m, 400m, 600m veya 400m, 800m, 1200m) yürüyüş havzaları üretir. Büyük poligonların küçükleri örtmesini engelleyen çizim sırası ve collinear dejenere geometri koruması barındırır.
- **2SFCA (İki Aşamalı Yüzen Havza Modeli):** Donatı kapasiteleri ve nüfus talebini ağ mesafesiyle ağırlıklandırarak donatı yeterliliğini (Yeterli, Aşırı Yüklü, Kullanılmayan) hem nokta hem bina/ada poligonu düzeyinde modeller.
- **A/B Senaryo Karşılaştırması:** Yeni açılan yol veya donatı senaryolarının erişim farklarını delta metrikleriyle ortaya koyar; sınıflama eşikleri yeni NACH ve NAIN ölçeğine göre yeniden belirlenmiştir (|ΔNACH| 0,077, |ΔNAIN| 0,047; yeni yol için NACH 0,734 ve NAIN 0,391).

### 7. 📚 Teorik ve Metodolojik Kılavuz
- Paneldeki Yardım düğmesi çevrimiçi kılavuzu açar: [geophilo.com/pln3113_nip](https://geophilo.com/pln3113_nip/). Kılavuz eklenti paketinde yer almaz.
  - Formüller, MPYY Ek-2 katsayıları, DOP hesaplama tabloları, jüri sunum stratejileri ve analitik araçların adım adım uygulama senaryoları.

---

## 📐 Birimler ve Koordinat Sistemi Kuralları
- **Metre birimli projeksiyon kullanın.** Ağ analizleri (Space Syntax, merkezilik, OD, izokron, 2SFCA, senaryo farkı), erişim havzası ve saha/bina analizi metre birimli projeksiyonlu bir koordinat sistemi (örneğin TUREF/TM dilimleri) ister; coğrafi (derece) ve fit (feet) birimli sistemler reddedilir.
- **Katmanlar aynı sistemde olmak zorunda değildir.** NİP nüfus aracında plan sınırı ve yol katmanı ada katmanından farklı bir koordinat sistemindeyse ada katmanının sistemine dönüştürülür.
- **Coğrafi (derece) koordinatlı veri:** NİP nüfus aracı alanları her zaman elipsoid üzerinde m² olarak ölçer. Proje elipsoidi "Yok" ise koordinat sisteminin kendi elipsoidi, o da yoksa WGS 84 elipsoidi (EPSG:7030) kullanılır.
  Diğer araçlar için verileri metre birimli projeksiyona aktarmanız gerekir.
- **Birimler:** Alanlar m² ve hektar, mesafeler metre, brüt yoğunluklar kişi/hektar, donatı standartları kişi başına m² olarak verilir.

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

---

## 🙏 Teşekkür ve Kaynak
Nüfus projeksiyonu, dağıtım ve kırılganlık özellikleri [Kent Öngörü](https://github.com/berkaymemis/kent_ongoru) v1.0.0 (Berkay Memiş, GPL-2.0-or-later) temel alınarak yeniden yazıldı.

Kırılganlık endeksinin pay/payda yöntemi standart risk/kırılganlık uygulamasıdır: kırılganlığı artıran (maruziyet, hassasiyet) etkenler pay tarafında, azaltıcı (uyum kapasitesi) etkenler payda tarafında yer alır. Dayanakları:

* UNDRR, *Sendai Framework Terminology on Disaster Risk Reduction* — afet riski "tehlike, maruziyet, kırılganlık ve kapasitenin fonksiyonu" olarak tanımlanır (BM Genel Kurulu, A/71/644, 1 Aralık 2016; 71/276 sayılı kararla 2 Şubat 2017'de kabul edildi): https://www.undrr.org/terminology/disaster-risk
* UNISDR (2015), *Sendai Framework for Disaster Risk Reduction 2015-2030*; UNISDR (2017), *Words into Action Guidelines: National Disaster Risk Assessment*.
* OECD/JRC (2008), *Handbook on Constructing Composite Indicators: Methodology and User Guide*, OECD Publishing, Paris — normalleştirme (min-max), ağırlıklandırma ve birleştirme adımları: https://doi.org/10.1787/9789264043466-en
Kent Öngörü'nün kodu kopyalanmamıştır; yöntemler bu eklentinin yapısına göre baştan yazılmış ve sayısal sınamalarla (`tests/test_projection.py`, `tests/test_new_algorithms_qgis.py`) denetlenmiştir.
