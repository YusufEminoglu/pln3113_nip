# Tire NİP ve Kentsel Analiz Stüdyosu (`nip_eklenti_01`)

**Dokuz Eylül Üniversitesi | Mimarlık Fakültesi | Şehir ve Bölge Planlama Bölümü**  
**PLN3113 Şehir Planlama Projesi III — Tire 1/5000 Nazım İmar Planı ve Saha Entegrasyonu**  
*Geliştirici:* Arş. Gör. Yusuf Eminoğlu

---

## 📌 Eklentinin Amacı ve Kapsamı
Bu eklenti; PLN3113 stüdyosu kapsamında öğrencilerin Tire 1/5000 Nazım İmar Planı (NİP) sayısal verilerini (`nipt_test.gpkg`), saha tespitlerini (`PLN3113_Tire_Saha_Master_Nihai`) ve bina katmanlarını (`tire_bina.gpkg`) hızlı, hatasız ve bilimsel standartlara uygun olarak analiz etmelerini sağlamak amacıyla geliştirilmiştir.

Eklenti 3 temel modülden oluşur:

### 1. Modül: Veri Doğrulama ve Geometri Temizleme
- **Kendini Kesen Geometrilerin Onarımı:** Bozuk poligonları `makeValid` ve tampon toleransı ile onarır.
- **Mükerrer (Duplike) Poligon Ayıklama:** Sayısallaştırma hatalarından kaynaklanan üst üste binen çift poligonları hassas koordinat/WKB hash kontrolüyle ayıklar ve tekilleştirir.

### 2. Modül: NİP Nüfus, Donatı ve Ulaşım Analizi
- **Yoğunluk Eşleme:** Lejanttaki fonksiyon adlarını (`Ort__Detay`, `Ort_Detay`, `nipfonksiyon`) tanıyarak `ALT_SNR` ve `UST_SNR` brüt yoğunluklarını (kişi/hektar) otomatik atar.
- **Karma Kullanım (Ticaret-Konut) Kuralı:** Mekânsal komşuluğundaki en yakın konut adalarının yoğunluğunun **%30'unu** karma konut yoğunluğu olarak atar.
- **Brüt Plan Nüfusu:** `ALT_NUFUS` (`AlanHa × ALT_SNR`) ve `UST_NUFUS` (`AlanHa × UST_SNR`) hesaplar.
- **Donatı Kişi Başı m²:** Eğitim, Sağlık, Kültürel/Sosyal, Açık ve Yeşil Alan, Teknik Altyapı ve İbadet donatıları için `k_m2_ALT_NUFUS` ve `k_m2_UST_NUFUS` değerlerini hesaplar.
- **Tire Nüfus Karşılaştırma Göstergesi:** 1997 Plan Raporu (1990 DİE: 37.855 merkez / 77.314 ilçe), 2015 Plan Hedefi (53.629 merkez / 100.340 ilçe), 2015 TÜİK ADNKS (56.750 merkez / 82.102 ilçe), Güncel TÜİK ADNKS (62.000 merkez / 87.571 ilçe) verileri ile canlı kıyaslama sunar.
- **İstihdam ve Ulaşım Modeli:** Fonksiyon bazında çalışan kapasitesi (`T_ISTIHDAM`) ile günlük araç (`GUNLUK_ARAC`) ve yaya (`GUNLUK_YAYA`) yolculuk çekim yükünü modeller.

### 3. Modül: Saha ve Bina Bazlı Fiili Nüfus/İstihdam Tahmini
- Kadastro/Tapu adaları (`PLN3113_Tire_Kadastro_Tapu_Master`) ile binaları (`tire_bina.gpkg`) mekânsal olarak birleştirir.
- **Planlama İlkesi Koruması:** Sanayi, OSB, depo, mezarlık, saf ticaret ve park alanlarında yaşayan nüfus kesinlikle **0** atanır (yalnızca istihdam ve araç/yaya çekimi hesaplanır).
- Konut ve Karma Kullanım adalarında bağımsız bölüm ve kat adetlerinden hareketle TÜİK hanehalkı büyüklüğü (~2.85 kişi) üzerinden ada bazında fiili yaşayan nüfus ve brüt yoğunluk (`FIILI_BRUT_YOGUNLUK_HA`) hesaplanır.

---

## 🚀 Kurulum

### Yöntem A (QGIS Eklenti Yöneticisi ile ZIP'ten Kurulum):
1. QGIS menüsünden **Eklentiler -> Eklentileri Yönet ve Kur...** seçeneğini açın.
2. Sol menüden **ZIP'ten Kur** sekmesine gelin.
3. Size iletilen `nip_eklenti_01.zip` dosyasını seçip **Eklentiyi Kur** butonuna tıklayın.

### Yöntem B (Doğrudan Klasör Kopyalama):
`nip_eklenti_01` klasörünü QGIS profilinizdeki `python/plugins/` dizinine kopyalayın:
`%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\nip_eklenti_01`
Ardından QGIS'i yeniden başlatıp Eklenti Yöneticisi'nden aktif hale getirin.
