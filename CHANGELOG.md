# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
