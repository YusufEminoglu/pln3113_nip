# -*- coding: utf-8 -*-
"""Geometri Temizleme ve Çift (Duplike) Poligon Ayıklama Motoru.

DEÜ Mimarlık Fakültesi Şehir ve Bölge Planlama Bölümü
PLN3113 - tire_nip
"""
from __future__ import annotations

import contextlib
import hashlib
from qgis.core import (
    QgsFeature,
    QgsFeatureSink,
    QgsGeometry,
    QgsVectorLayer,
    QgsWkbTypes,
    QgsProcessingFeedback
)

class GeometryCleanerEngine:
    """Poligon katmanlarında geometri geçerliliği ve gelişmiş duplike denetimi yapar."""

    @staticmethod
    def check_validity(source_layer: QgsVectorLayer, feedback: QgsProcessingFeedback = None) -> dict:
        """Katmandaki geometrilerin geçerliliğini ve duplikelerini denetler, hata konumlarını ve türlerini listeler."""
        stats = {
            "toplam_girdi": 0,
            "gecersiz_adet": 0,
            "duplike_adet": 0,
            "bos_geometri": 0,
            "gecerli_adet": 0,
            "hatalar": []
        }

        seen_spatial_signatures = set()
        seen_wkb_hashes = set()

        total = source_layer.featureCount()
        stats["toplam_girdi"] = total

        for idx, feat in enumerate(source_layer.getFeatures()):
            if feedback and feedback.isCanceled():
                break

            fid = feat.id()
            geom = feat.geometry()

            if not geom or geom.isEmpty():
                stats["bos_geometri"] += 1
                stats["hatalar"].append({
                    "fid": fid,
                    "hata_turu": "Boş Geometri",
                    "detay": "Poligon geometrisi boş veya tanımsız",
                    "x": None,
                    "y": None,
                })
                continue

            # 1. Geometri Geçerlilik Kontrolü
            is_valid = True
            with contextlib.suppress(Exception):
                is_valid = geom.isGeosValid() and geom.isValid()

            if not is_valid:
                stats["gecersiz_adet"] += 1
                geom_errors = []
                with contextlib.suppress(Exception):
                    geom_errors = geom.validateGeometry()

                if geom_errors:
                    for err in geom_errors:
                        what = err.what()
                        what_tr = what
                        if "intersect" in what.lower():
                            what_tr = f"Kendi Kendini Kesen Halka (Self-intersection): {what}"
                        elif "ring" in what.lower():
                            what_tr = f"Halkalama Hatası: {what}"
                        elif "hole" in what.lower():
                            what_tr = f"İç Ada / Delik Hatası: {what}"

                        x = err.where().x() if err.hasWhere() else None
                        y = err.where().y() if err.hasWhere() else None
                        stats["hatalar"].append({
                            "fid": fid,
                            "hata_turu": "Geçersiz Geometri",
                            "detay": what_tr,
                            "x": x,
                            "y": y,
                        })
                else:
                    c = geom.centroid().asPoint() if geom.centroid() and not geom.centroid().isEmpty() else None
                    stats["hatalar"].append({
                        "fid": fid,
                        "hata_turu": "Geçersiz Geometri",
                        "detay": "Geometrik topoloji kuralı ihlali (isGeosValid=False)",
                        "x": c.x() if c else None,
                        "y": c.y() if c else None,
                    })

            # 2. Çok Kademeli Duplike Kontrolü
            wkb = geom.asWkb()
            wkb_hash = None
            if wkb:
                with contextlib.suppress(Exception):
                    wkb_bytes = bytes(wkb) if not isinstance(wkb, bytes) else wkb
                    wkb_hash = hashlib.sha256(wkb_bytes).hexdigest()

            bbox = geom.boundingBox()
            area_rounded = round(geom.area(), 1)
            perim_rounded = round(geom.length(), 1)
            c = geom.centroid().asPoint() if geom.centroid() and not geom.centroid().isEmpty() else None
            cx = round(c.x(), 1) if c else 0.0
            cy = round(c.y(), 1) if c else 0.0
            bx_min = round(bbox.xMinimum(), 1)
            by_min = round(bbox.yMinimum(), 1)
            bx_max = round(bbox.xMaximum(), 1)
            by_max = round(bbox.yMaximum(), 1)
            spatial_sig = f"{bx_min}_{by_min}_{bx_max}_{by_max}_{cx}_{cy}_{area_rounded}_{perim_rounded}"

            is_duplicate = False
            if wkb_hash and wkb_hash in seen_wkb_hashes:
                is_duplicate = True
            elif spatial_sig in seen_spatial_signatures:
                is_duplicate = True

            if is_duplicate:
                stats["duplike_adet"] += 1
                stats["hatalar"].append({
                    "fid": fid,
                    "hata_turu": "Mükerrer (Duplike) Poligon",
                    "detay": f"Başka bir poligonla birebir örtüşen kopya (Alan: {area_rounded:,.1f} m²)",
                    "x": c.x() if c else None,
                    "y": c.y() if c else None,
                })
            else:
                if wkb_hash:
                    seen_wkb_hashes.add(wkb_hash)
                seen_spatial_signatures.add(spatial_sig)

            if is_valid and not is_duplicate:
                stats["gecerli_adet"] += 1

            if feedback and idx % 250 == 0:
                feedback.setProgress(int((idx / max(1, total)) * 100))

        return stats

    @staticmethod
    def clean_layer(source_layer: QgsVectorLayer, feedback: QgsProcessingFeedback = None) -> tuple[list[QgsFeature], dict]:
        """Katmanı tarar, bozuk geometrileri onarır, çift/mükerrer poligonları eler."""
        stats = {
            "toplam_girdi": 0,
            "gecersiz_onarilan": 0,
            "duplike_elenen": 0,
            "temiz_cikan": 0,
            "bos_geometri": 0,
            "duplike_orani": 0.0
        }

        seen_spatial_signatures = set()
        seen_wkb_hashes = set()
        cleaned_features = []

        total = source_layer.featureCount()
        stats["toplam_girdi"] = total

        for idx, feat in enumerate(source_layer.getFeatures()):
            if feedback and feedback.isCanceled():
                break

            geom = feat.geometry()
            if not geom or geom.isEmpty():
                stats["bos_geometri"] += 1
                continue

            # 1. Geometri Geçerlilik Kontrolü & Otomatik Onarım
            was_invalid = False
            with contextlib.suppress(Exception):
                if not geom.isGeosValid() or not geom.isValid():
                    was_invalid = True
                    repaired = geom.makeValid()
                    if repaired and not repaired.isEmpty():
                        geom = repaired
                        stats["gecersiz_onarilan"] += 1
                    else:
                        buffered = geom.buffer(0, 5)
                        if buffered and not buffered.isEmpty():
                            geom = buffered
                            stats["gecersiz_onarilan"] += 1

            # 2. Çok Kademeli Sağlam Duplike Kontrolü
            # 2.A: WKB İkili Hash (Doğrudan byte-for-byte eşleşme)
            wkb = geom.asWkb()
            wkb_hash = None
            if wkb:
                with contextlib.suppress(Exception):
                    wkb_bytes = bytes(wkb) if not isinstance(wkb, bytes) else wkb
                    wkb_hash = hashlib.sha256(wkb_bytes).hexdigest()

            # 2.B: Mekânsal Geometrik İmza (Envelope + Centroid + Alan + Çevre)
            # İki poligonun sınır kutusu, ağırlık merkezi, alanı ve çevresi 10 cm hassasiyetle
            # aynıysa bunlar aynı imar adasıdır (nokta sırası veya yönü farklı olsa dahi).
            bbox = geom.boundingBox()
            area_rounded = round(geom.area(), 1)
            perim_rounded = round(geom.length(), 1)
            
            c = geom.centroid().asPoint() if geom.centroid() and not geom.centroid().isEmpty() else None
            cx = round(c.x(), 1) if c else 0.0
            cy = round(c.y(), 1) if c else 0.0

            bx_min = round(bbox.xMinimum(), 1)
            by_min = round(bbox.yMinimum(), 1)
            bx_max = round(bbox.xMaximum(), 1)
            by_max = round(bbox.yMaximum(), 1)

            spatial_sig = f"{bx_min}_{by_min}_{bx_max}_{by_max}_{cx}_{cy}_{area_rounded}_{perim_rounded}"

            # Duplike Denetimi: İki imzadan biri daha önce görüldüyse mükerrer kabul edilir
            is_duplicate = False
            if wkb_hash and wkb_hash in seen_wkb_hashes:
                is_duplicate = True
            elif spatial_sig in seen_spatial_signatures:
                is_duplicate = True

            if is_duplicate:
                stats["duplike_elenen"] += 1
                continue

            # Yeni tekil geometri olarak kaydet
            if wkb_hash:
                seen_wkb_hashes.add(wkb_hash)
            seen_spatial_signatures.add(spatial_sig)

            clean_feat = QgsFeature(feat)
            clean_feat.setGeometry(geom)
            cleaned_features.append(clean_feat)

            if feedback and idx % 250 == 0:
                feedback.setProgress(int((idx / max(1, total)) * 100))

        stats["temiz_cikan"] = len(cleaned_features)
        total_valid = max(1, stats["toplam_girdi"])
        stats["duplike_orani"] = round((stats["duplike_elenen"] / total_valid) * 100.0, 1)

        return cleaned_features, stats
