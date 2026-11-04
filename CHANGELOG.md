# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.2] - 2026-11-04

Bu sürüm Ek-2 donatı bilançosunun sonuçlarını değiştirir. 1.2.x ile üretilmiş Ek-2 tablolarını yeniden hesaplayın.

### Düzeltildi
- Ek-2 değerleri Mekânsal Planlar Yapım Yönetmeliği (RG 14.06.2014/29030) md. 11 ve EK-2 tablosunun (Değişik: RG 17.05.2017/30069) mevzuat.gov.tr'deki resmî metniyle karşılaştırıldı ve nüfus gruplarına bağlandı. Standart, ilçe projeksiyon nüfusunun grubundan alınır (EK-2 Açıklama 1; 0-75.000, 75.001-150.000, 150.001-500.000, 501.000+): eğitim 6,5 / 6,5 / 6,6 / 6,6; sağlık 1,5 / 1,5 / 1,5 / 1,6; sosyal ve kültürel 0,75 / 1 / 1,25 / 1,5 (önceden her nüfusta 1,0); açık ve yeşil alan 10; teknik altyapı 1 / 1,25 / 1,5 / 2 (önceden her nüfusta 1,25); ibadet 0,5 / 0,5 / 0,75 / 0,75 m²/kişi. Önceki sabit değerler yalnız 75.001-150.000 grubuna denk geliyordu.
- Semt spor alanı artık açık ve yeşil alan standardına sayılır (EK-2 Açıklama 9). Genel spor alanı, spor kompleksi ve pasif yeşil/refüj için EK-2'de kişi başı satır yoktur; bilançoya girmez.
- Adında "ÖZEL" geçen eğitim, sağlık, sosyal ve kültürel tesisler kişi başı standarda sayılır (EK-2 Açıklama 8); DOP hesabında bu alanlar yine özel tahsistir. Sayıldıklarında uyarı verilir ve Ek-2 tablosunda özel alan ayrıca gösterilir.
- Otopark teknik altyapı standardına sayılmaz (EK-2: "yol ve otopark hariç"). Yalın "Otopark" fonksiyonu yanlışlıkla park/yeşil alan olarak tanınıyordu.
- Açık ve yeşil alanlarda kamuya ait, DOP'a tabi alanların payı %75'in altına düştüğünde uyarı verilir (EK-2 Açıklama 9).
- NİP hesap motoruna isteğe bağlı ilçe projeksiyon nüfusu (`ek2_nufus`) eklendi; verilmezse projeksiyon nüfusu kullanılır. Ek-2 raporu nüfus grubunu yazar.

### Değişti
- Kohort aracının varsayılan değerleri resmî TÜİK tablolarından hesaplandı (Türkiye geneli): Sx ve doğumdan 0-4'e yaşama oranı "Hayat Tabloları, 2023-2025" bülteninin (no. 58232) "Cinsiyete göre Türkiye tek yaş hayat tablosu" tablosundan; yaşa özel doğurganlık hızları "Doğum İstatistikleri, 2025" bülteninin (no. 58018) "Yaşa özel doğurganlık hızları" tablosundan (TDH 1,42); doğumda cinsiyet oranı aynı bültenin "Cinsiyet ve aya göre doğumlar" tablosundan (105,62). Kaynak, tablo adı, yıl ve adres `core/data/kohort_varsayilan.json` içindedir. Göç yaş profili model değeri olarak kaldı.
- Kırılganlık endeksinin pay/payda yöntemi için kaynak gösterildi: UNDRR terminolojisi (afet riski tehlike, maruziyet, kırılganlık ve kapasitenin fonksiyonu; BM Genel Kurulu A/71/644, 2016; Sendai Çerçevesi 2015-2030) ve OECD/JRC (2008) "Handbook on Constructing Composite Indicators: Methodology and User Guide". Yöntem için kişi ya da stüdyo atfı kaldırıldı; Kent Öngörü v1.0.0 (Berkay Memiş, GPL-2.0-or-later) atfı yeniden yazılan özellikler için sürüyor.

## [1.2.1] - 2026-11-04

### Değişti
- Qt6 / QGIS 4 uyumluluğu: Qt ve QGIS enum değerleri hem QGIS 3.28+ hem QGIS 4'ün kabul ettiği kapsamlı biçimde yazıldı (örneğin `QgsUnitTypes.DistanceUnit.DistanceMeters`), QGIS 4'te bulunmayan `QVariant.Type` dalları kaldırıldı; davranış değişmedi.

## [1.2.0] - 2026-11-04

Bu sürüm, Space Syntax ve nüfus hesaplarında sonuçları değiştiren düzeltmeler içerir. 1.1.6 ile üretilmiş NAIN, NACH, senaryo farkı ve nüfus çıktılarını yeniden hesaplayın.

### Eklendi
- Processing araç kutusunda yeni grup: "07. Nüfus Projeksiyonu, Dağıtım ve Kırılganlık". Dört aracın hepsi paneldeki Nüfus sayfasından da açılabilir.
- **Nüfus projeksiyonu** (`pln3113:nufus_projeksiyonu`): aritmetik, geometrik, İller Bankası, en küçük kareler (doğrusal regresyon), 2. derece polinom ve lojistik yöntemler; her yöntem için R² ve geriye dönük sınama hatası; sonuçlar özet tablo ve yıllık seri tablosu olarak yazılır.
- İller Bankası yönteminde yıllık artış hızı varsayılan olarak %1-%3 aralığına çekilir ve çekildiğinde uyarı verilir. Lojistik yöntemde K verilmezse hatayı en küçükleyen K aranır, arama sınırına dayanırsa uyarı verilir; Pearl-Reed üç nokta biçimi isteğe bağlıdır.
- Paneldeki Nüfus sayfasında projeksiyon hesaplanabilir ve sonuç NİP hedef nüfus kutusuna (50 milyona kadar) aktarılabilir; hedef nüfusu elle girmek de mümkündür.
- **Kohort-bileşen projeksiyonu** (`pln3113:kohort_projeksiyonu`): 17 beş yaşlık grup, iki cinsiyet, beşer yıllık adımlar; doğumlar 0-4 yaş grubuna doğumdan 0-4'e yaşama oranıyla aktarılır; beşlik adıma düşmeyen hedef yıllar için ara değer hesaplanır.
- Kohort aracının varsayılan Sx, ASFR ve göç yaş profili kaynak notlarıyla birlikte `core/data/kohort_varsayilan.json` dosyasındadır. Bunlar resmî TÜİK tablosu değil, model yer tutucularıdır (Sx: TÜİK doğumda beklenen yaşam süresine, erkek 75,9 ve kadın 81,3 yıl, ayarlanmış Gompertz-Makeham tablosu; ASFR: toplam doğurganlık hızı 1,51'e ölçeklenmiş desen) ve resmî tablolarla değiştirilmelidir.
- Kohort aracında net göç yıllık oran ya da yıllık kişi sayısı olarak girilir ve yaş profiline göre dağıtılır; çıktılar yaş piramidi tablosu ile bağımlılık oranları, yaşlanma endeksi, medyan yaş, doğum ve net göçü içeren gösterge tablosudur.
- **Ekonomik taban göçü**: nüfus projeksiyonu aracında yeni istihdam, "çalışan başına nüfus" katsayısıyla (varsayılan 2,7 kişi/çalışan) göç eden nüfusa çevrilir ve her yöntemin sonucuna eklenir.
- **Mahalle dağıtımı** (`pln3113:mahalle_dagitimi`): hedef nüfusun mahallelere oransal, planlama bölgesi payına göre ya da kapasite sınırlı (kapasitesi dolan mahallenin fazla payı diğer mahallelere yeniden dağıtılır) biçimde dağıtılması; en büyük kalan yöntemiyle tam sayıya yuvarlama toplamı korur; sonuç anahtar alanla katmana bağlanır.
- **Kırılganlık endeksi** (`pln3113:kirilganlik_endeksi`): göstergeler 1-5 puanlanır; kırılganlığı artıran göstergeler pay, uyum kapasitesini gösterenler paydada yer alır (pay/payda yöntemi). Deprem (K_D), sel ve taşkın (K_Y) ve aşırı sıcak (K_S) için hazır endeksler ile özel endeks (K_O) tanımlanabilir; bileşik endeksin varsayılan ağırlıkları K_D 0,40, K_Y 0,35, K_S 0,25 ve K_O 0,25'tir.
- Kırılganlık aracında kategori değerleri mevcut Türkçe ad eşleştirmesiyle (`norm_tr`) eşleşir; değeri olmayan gösterge 1 (çarpımda etkisiz) puan alır ve bölgenin eksik gösterge sayısına yazılır; nüfus göstergesi yoğunlukla (kişi/ha) puanlanır; sel endeksinde düşük göreli yükseklik ve düşük eğim kırılganlığı artıracak yönde puanlanır.
- Kırılganlık sınıfları Jenks (doğal kırılma), eşit sayılı (quantile), eşit aralıklı ya da geometrik aralıklı olarak ayrılabilir; sonuç anahtar alanla katmana bağlanır ve HTML raporundaki metinler kaçışlanır.

### Düzeltildi
- Space Syntax motoru PlanX 4.23.0 sürümüne güncellendi: NAIN artık NC^1.2/(TD+2) ile hesaplanır ve seçim (choice) yönlü segment uçları üzerinden sayılır, böylece çıkmaz sokak segmentleri seçim değeri almaz. A/B senaryo karşılaştırmasının eşikleri yeni ölçeğe göre yeniden belirlendi (|ΔNACH| 0,077, |ΔNAIN| 0,047, yeni yol NACH 0,734 ve NAIN 0,391).
- Space Syntax yarıçapları yer metresi olarak uygulanır.
- Space Syntax ve NİP nüfus araçları iptal edildiğinde yarım kalmış sonuç yazmaz.
- Ağ analizlerinde NULL, sıfır ya da negatif maliyet değeri uzunlukla değiştirilmez; işlem durur.
- NİP nüfus aracında plan sınırı ya da yol katmanı adalardan farklı bir koordinat sisteminde olduğunda ada katmanının koordinat sistemine dönüştürülür; daha önce bu durumda tüm adalar elenebiliyor ya da yol uzunlukları yanlış birimde hesaplanıyordu.
- NİP nüfus aracında alanlar her zaman elipsoid üzerinde m² olarak ölçülür: proje elipsoidi "Yok" ise koordinat sisteminin elipsoidi, o da yoksa WGS 84 elipsoidi (EPSG:7030) kullanılır.
- Hesaptan çıkarılan adaların sayısı (boş geometri, sıfır alan, plan sınırı dışı) ve fonksiyonu boş adalar uyarı olarak bildirilir. 2SFCA aracında nüfusu boş (NULL) talep noktaları 0 kişi, kapasitesi boş donatılar varsayılan kapasiteyle hesaba girer ve sayıları uyarı olarak verilir.
- Ağ analizleri, erişim havzası ve saha/bina analizi fit (feet) birimli projeksiyonları da reddeder; metre birimli projeksiyon gerekir.
- Plan sınırı verilmeden yasal DOP değerlendirmesi ("yasal sınırı aşıyor") yapılmaz; sınırsız hesap "TAHMİNİ DOP ORANI" olarak etiketlenir. Tahmini yol payı (varsayılan 0,18) parametre olarak değiştirilebilir.
- DOP için %45 değeri panelde hedef olarak değil "yasal tavan" olarak gösterilir.
- Erişim havzası aracında içbükey zarf (concave hull) seçeneği çalışmıyordu, her zaman dışbükey zarfa düşüyordu; artık seçilen zarf üretilir.
- OD matrisi rotaları ters yöndeki kenarlarda doğru yönde çizilir (önceden zikzak çiziyordu).
- Ek-2 bilançosunda spor alanları yeşil alan standardına, adında "ÖZEL" geçen tesisler (ör. özel sağlık) kamu donatı standardına sayılmaz; bu tesisler DOP hesabında da kamu donatısı değil özel tahsis olarak değerlendirilir, bu yüzden ÖZEL tesis içeren planlarda DOP oranı 1.1.6'ya göre düşebilir. Ek-2 değerleri değişmedi; yürürlükteki yönetmelik metniyle karşılaştırarak kullanın.
- Tire'ye özgü sabitler (kırsal nüfus eki, nüfus kıyaslama değerleri, "Tire NİP" adları) koddan çıkarıldı; kırsal nüfus eki ve kıyaslama ön ayarı parametre olarak girilir, Tire yalnızca örnek ön ayar olarak kalır.
- İnteraktif NİP & DOP raporunda katman ve fonksiyon adları HTML'e kaçışlanarak yazılır; panel, raporun plotly, Leaflet ve OpenStreetMap karolarını herkese açık sunuculardan yüklediğini belirtir.

### Değişti
- Panel ve menü adlarında PLN3113 adı kullanılır.
- Panel daraltıldı (en az genişlik yaklaşık 205 piksel; 340 piksel genişlikte hiçbir sayfa yatay kaydırma çubuğu istemez) ve renkler QGIS temasından alınır. QGIS'in varsayılan, Night Mapping ve Blend of Gray temalarında ölçülen metin kontrastı en az 5:1'dir.
- "Üstel" projeksiyon yöntemi kaldırıldı: iki gözlem noktasında geometrik yöntemle aynı sonucu verir.
- Processing araç sayısı 15'ten 19'a çıktı.
- Nüfus, DOP, Ek-2, projeksiyon ve Space Syntax değerleri için sayısal sınamalar eklendi.
- Nüfus projeksiyonu, dağıtım ve kırılganlık özellikleri Kent Öngörü v1.0.0 (Berkay Memiş, GPL-2.0-or-later) temel alınarak yeniden yazıldı.

## [1.1.6] - 2026-10-28

- Help opens the online guide on geophilo.com instead of a copy bundled in the plugin package; the plugin no longer ships documentation HTML.

## [1.1.5] - 2026-10-27

- Hub listing text rewritten; author Geophilo; university affiliation removed; documentation links use the standard geophilo.com pages (manual.html, guide/); manual HTML no longer ships in the plugin package.

## [1.1.4] - 2026-10-18
### Değişti
- GitHub depo adı ve tüm kaynak bağlantıları paket/klasör adıyla aynı olacak şekilde `YusufEminoglu/pln3113_nip` olarak güncellendi.

## [1.1.3] - 2026-10-18
### Değişti
- Metodoloji kılavuzu genişletildi: modüller ve analitik araçlar adım adım anlatıldı, çıktı sütunları için sözlük eklendi.
- Açıklama, etiketler ve README Türkiye'deki tüm şehir ve bölge planlama stüdyoları için genelleştirildi.

## [1.1.2] - 2026-10-18
### Düzeltildi
- Yürüme izokronlarında lejant ve renk skalası kullanıcının girdiği mesafe aralıklarıyla (örn. 200, 400, 600 m) birebir eşleşir.
- İçbükey gövde (Concave Hull) tek doğrultuda dizilmiş noktalarda bozuk geometri üretmez; büyük poligonlar küçükleri örtmeyecek sırayla çizilir.

## [1.1.1] - 2026-10-18
### Fixed
- Dışarıdan halihazır/CAD katmanı yüklendiğinde Windows GDI tanıtıcı sınırının (10.000 nesne) aşılmasını önleyen çökme koruması (`_load_rules_table_from_layer` benzersiz değer taraması sınırlandırıldı ve sinyal blokajı eklendi).
- Geometrisiz (NoGeometry) özet ve matris tablolarında (`alg_scenario_compare`, `alg_service_areas`, `alg_od_matrix`, `alg_nip_population`) projeksiyonlu CRS yerine boş `QgsCoordinateReferenceSystem()` atanarak katman ekleme anındaki harita kapsam dönüşüm çökmesi engellendi.
- Dock arayüzündeki sürüm rozeti `metadata.txt` dosyasından dinamik okunur hale getirildi (`v1.1.1`).
- Mükerrer katman kaydını önleyen `_safe_add_map_layer` koruması eklendi.

## [1.1.0] - 2026-10-17
### Added
- Kentsel Ağ ve Mekânsal Erişim Analizleri Süiti (PlanX Çekirdeği): Space Syntax (açısal segment NAIN/NACH), Primal Ağ Merkeziliği (Betweenness, Closeness, Straightness), OD Matrisi & Detour Engel Analizi, Hassas Yol Ağı Hizmet Alanları ve İzokronları (Pedshed), 2SFCA/E2SFCA Donatı Yeterliliği, A/B Senaryo Karşılaştırması (Mevcut vs Meri) ve Ön Cephe Servis Noktası Bulucu.
- 7 alt sekmeli gelişmiş Ağ ve Ulaşım Analizleri Dock arayüzü ve otomatik tematik harita sembolojileri.

## [1.0.0] - 2026-10-17
### Added
- İlk resmi sürüm (PLN3113 Şehir Planlama Projesi III Stüdyosu).
- 1/5000 Nazım İmar Planı (NİP) katmanlarında otomatik geometri onarımı ve mükerrer poligon ayıklama (QGIS Processing).
- Mekânsal Planlar Yapım Yönetmeliği (MPYY) Ek-2 donatı standartları uyarınca kişi başına asgari m² analizi ve açık/fazla hesaplaması.
- Dinamik kurallar tablosu: DOP içi / nDOP ve Kamu / Özel tahsis yönetimi.
- Kadastro ve bina bazlı TAKS, KAKS, Ortalama Kat Adedi, Açık Alan Oranı, Spacematrix (FSI, GSI, OSR) ve Yapı Nizamı (A4) metrikleri.
- Kentsel Ağ ve Mekânsal Erişim Analizleri Süiti (PlanX Çekirdeği): Space Syntax (açısal segment NAIN/NACH), Primal Ağ Merkeziliği (Betweenness, Closeness, Straightness), OD Matrisi & Detour Engel Analizi, Hassas Yol Ağı Hizmet Alanları ve İzokronları (Pedshed), 2SFCA/E2SFCA Donatı Yeterliliği, A/B Senaryo Karşılaştırması (Mevcut vs Meri) ve Ön Cephe Servis Noktası Bulucu.
- 1-tıkla otomatik tematik harita katmanları ve görsel stil motoru.
- Kapsamlı HTML formatında teorik metodoloji rehberi (`teorik_rehber.html`).
- God of War temalı stüdyo koordinatör avatarı ve modern ŞBP arayüz teması.
