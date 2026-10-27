# -*- coding: utf-8 -*-
"""Erişilebilirlik ve MPYY Hizmet Etki Çapı Havzaları Algoritması.

PLN3113 - Tire NİP Analiz Stüdyosu

Yol ağı üzerinden Network Service Area (Isochrone / Convex Hull) ve
MPYY Mevzuat Etki Çapı (Dairesel Tampon) hesaplar.
"""
from __future__ import annotations

import contextlib
import math

try:
    import processing
except ImportError:
    processing = None

from qgis.PyQt.QtCore import QVariant
from qgis.core import (
    QgsFeature,
    QgsFeatureSink,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterDistance,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingUtils,
    QgsVectorLayer,
    QgsWkbTypes
)


class ErismeHavzasiAlgorithm(QgsProcessingAlgorithm):
    INPUT_FACILITIES = 'INPUT_FACILITIES'
    INPUT_ROADS = 'INPUT_ROADS'
    DISTANCE = 'DISTANCE'
    HULL_METHOD = 'HULL_METHOD'
    DISSOLVE_POLYGONS = 'DISSOLVE_POLYGONS'
    SPLIT_SEGMENT_LENGTH = 'SPLIT_SEGMENT_LENGTH'
    TOLERANCE = 'TOLERANCE'
    CALCULATE_NETWORK = 'CALCULATE_NETWORK'
    CALCULATE_BUFFER = 'CALCULATE_BUFFER'
    OUTPUT_SERVICE_ROADS = 'OUTPUT_SERVICE_ROADS'
    OUTPUT_SERVICE_POLYGONS = 'OUTPUT_SERVICE_POLYGONS'
    OUTPUT_DISSOLVED_POLYGONS = 'OUTPUT_DISSOLVED_POLYGONS'
    OUTPUT_MPYY_BUFFER = 'OUTPUT_MPYY_BUFFER'
    OUTPUT_MPYY_INDIVIDUAL = 'OUTPUT_MPYY_INDIVIDUAL'

    def name(self):
        return 'nip_erisme_ve_mpyy_etki_capi'

    def displayName(self):
        return '2. Donatı Erişilebilirlik ve MPYY Etki Çapı Havzaları'

    def group(self):
        return '05. Ulaşım ve Network Analizleri'

    def groupId(self):
        return '05_ulasim_network_analizleri'

    def shortHelpString(self):
        return (
            "Sosyal ve teknik altyapı donatıları (Eğitim, Sağlık, Park, İbadet vb.) için "
            "iki farklı yaklaşımla etki ve erişim havzası üretir:\n\n"
            "1. Ağ Tabanlı Gerçek Servis Yolları ve Erişim Havzası: Yol ağı üzerinden yürüyüş mesafesi "
            "boyunca ulaşılan sokakları (Service Area from Layer) ve gerçek yürüme havzası sınır poligonunu "
            "(Convex Hull / Isochrone) üretir.\n"
            "2. MPYY Mevzuat Geometrik Etki Çapı: Mekânsal Planlar Yapım Yönetmeliği standart yarıçaplarına "
            "göre (örn: 500m yürüme mesafesi) dairesel ve çözülmüş (dissolved) servis etki poligonları üretir.\n\n"
            "Çıktı poligonlarında Pedshed Kapsama Oranı (Ağ Alanı / MPYY Dairesel Alanı %), "
            "erişilen yol uzunluğu ve donatı bilgileri yer alır."
        )

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT_FACILITIES,
                'Donatı / Hizmet Noktaları veya Poligonları (Okul, Sağlık, Park vb.)',
                [QgsProcessing.SourceType.TypeVectorPoint, QgsProcessing.SourceType.TypeVectorPolygon]
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT_ROADS,
                'Ulaşım / Yol Aksları Katmanı (Line)',
                [QgsProcessing.SourceType.TypeVectorLine]
            )
        )
        self.addParameter(
            QgsProcessingParameterDistance(
                self.DISTANCE,
                'Erişim / Hizmet Etki Mesafesi (Metre)',
                parentParameterName=self.INPUT_ROADS,
                defaultValue=500.0,
                minValue=50.0,
                maxValue=10000.0
            )
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                self.HULL_METHOD,
                'Erişim Havza Poligonu Tipi',
                options=[
                    'Dışbükey Gövde (Convex Hull - Model ve Standart Havza)',
                    'İçbükey Gövde (Concave Hull / Alfa Şekli)',
                    'Yol Koridoru Tamponu (Ribbon Buffer)'
                ],
                defaultValue=0
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.DISSOLVE_POLYGONS,
                'Tüm Donatıların Erişim Havzalarını Birleştir (Dissolve)',
                defaultValue=True
            )
        )
        self.addParameter(
            QgsProcessingParameterDistance(
                self.SPLIT_SEGMENT_LENGTH,
                'Ağ Hassasiyeti / Yol Bölme Uzunluğu (Metre, 0=Bölme)',
                parentParameterName=self.INPUT_ROADS,
                defaultValue=25.0,
                minValue=0.0,
                maxValue=200.0
            )
        )
        self.addParameter(
            QgsProcessingParameterDistance(
                self.TOLERANCE,
                'Donatı Yola Kenetlenme Toleransı (Metre)',
                parentParameterName=self.INPUT_ROADS,
                defaultValue=50.0,
                minValue=1.0,
                maxValue=500.0
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.CALCULATE_NETWORK,
                'Yol Ağı Üzerinden Gerçek Servis Yollarını ve Havzayı Hesapla',
                defaultValue=True
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.CALCULATE_BUFFER,
                'MPYY Mevzuat Dairesel Etki Çapını (Buffer) Hesapla',
                defaultValue=True
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_SERVICE_ROADS,
                'Ağ Servis Yolları (Line)',
                QgsProcessing.SourceType.TypeVectorLine,
                optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_SERVICE_POLYGONS,
                'Ağ Tabanlı Erişim Havza Poligonu (Polygon)',
                QgsProcessing.SourceType.TypeVectorPolygon,
                optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_DISSOLVED_POLYGONS,
                'Ağ Tabanlı Çözülmüş / Birleşik Havza (Polygon)',
                QgsProcessing.SourceType.TypeVectorPolygon,
                optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_MPYY_BUFFER,
                'MPYY Mevzuat Etki Çapı Çözülmüş Tamponu (Polygon)',
                QgsProcessing.SourceType.TypeVectorPolygon,
                optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_MPYY_INDIVIDUAL,
                'MPYY Mevzuat Bireysel Tamponları (Polygon)',
                QgsProcessing.SourceType.TypeVectorPolygon,
                optional=True
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        source_fac = self.parameterAsSource(parameters, self.INPUT_FACILITIES, context)
        source_roads = self.parameterAsSource(parameters, self.INPUT_ROADS, context)
        distance = self.parameterAsDouble(parameters, self.DISTANCE, context)
        hull_method = self.parameterAsEnum(parameters, self.HULL_METHOD, context)
        do_dissolve = self.parameterAsBool(parameters, self.DISSOLVE_POLYGONS, context)
        split_len = self.parameterAsDouble(parameters, self.SPLIT_SEGMENT_LENGTH, context)
        tolerance = self.parameterAsDouble(parameters, self.TOLERANCE, context)
        do_network = self.parameterAsBool(parameters, self.CALCULATE_NETWORK, context)
        do_buffer = self.parameterAsBool(parameters, self.CALCULATE_BUFFER, context)

        if not source_fac or not source_roads:
            raise QgsProcessingException("Gerekli girdi katmanları bulunamadı!")

        roads_crs = source_roads.sourceCrs()

        # Eğer girdi poligon ise centroid noktalarına dönüştür
        fac_geom_type = source_fac.wkbType()
        fac_input = parameters[self.INPUT_FACILITIES]
        if QgsWkbTypes.geometryType(fac_geom_type) == QgsWkbTypes.GeometryType.PolygonGeometry:
            feedback.pushInfo("Donatı poligonlarının ağırlık merkezleri (centroid) türetiliyor...")
            cent_res = processing.run("native:centroids", {
                'INPUT': fac_input,
                'ALL_PARTS': False,
                'OUTPUT': 'TEMPORARY_OUTPUT'
            }, context=context, feedback=feedback, is_child_algorithm=True)
            fac_points = cent_res['OUTPUT']
        else:
            fac_points = fac_input

        results = {}

        # 1. MPYY Mevzuat Tamponu
        if do_buffer:
            if self.OUTPUT_MPYY_BUFFER in parameters and parameters[self.OUTPUT_MPYY_BUFFER]:
                feedback.pushInfo(f"MPYY {distance}m çözülmüş dairesel etki çapı tamponu hesaplanıyor...")
                buff_res = processing.run("native:buffer", {
                    'INPUT': fac_points,
                    'DISTANCE': distance,
                    'SEGMENTS': 64,
                    'END_CAP_STYLE': 0,
                    'JOIN_STYLE': 0,
                    'MITER_LIMIT': 2.0,
                    'DISSOLVE': True,
                    'OUTPUT': parameters[self.OUTPUT_MPYY_BUFFER]
                }, context=context, feedback=feedback, is_child_algorithm=True)
                results[self.OUTPUT_MPYY_BUFFER] = buff_res['OUTPUT']

            if self.OUTPUT_MPYY_INDIVIDUAL in parameters and parameters[self.OUTPUT_MPYY_INDIVIDUAL]:
                feedback.pushInfo(f"MPYY {distance}m bireysel dairesel etki çapı tamponları hesaplanıyor...")
                buff_ind_res = processing.run("native:buffer", {
                    'INPUT': fac_points,
                    'DISTANCE': distance,
                    'SEGMENTS': 64,
                    'END_CAP_STYLE': 0,
                    'JOIN_STYLE': 0,
                    'MITER_LIMIT': 2.0,
                    'DISSOLVE': False,
                    'OUTPUT': parameters[self.OUTPUT_MPYY_INDIVIDUAL]
                }, context=context, feedback=feedback, is_child_algorithm=True)
                results[self.OUTPUT_MPYY_INDIVIDUAL] = buff_ind_res['OUTPUT']

        # 2. Yol Ağı Tabanlı Servis Alanı ve Erişim Havzası
        if do_network:
            # Gerekirse yol akslarını hassas ağ analizi için böl
            if split_len > 0:
                feedback.pushInfo(f"Ulaşım ağı {split_len}m uzunlukta hassas segmentlere bölünüyor...")
                split_res = processing.run("native:splitlinesbylength", {
                    'INPUT': parameters[self.INPUT_ROADS],
                    'LENGTH': split_len,
                    'OUTPUT': 'TEMPORARY_OUTPUT'
                }, context=context, feedback=feedback, is_child_algorithm=True)
                net_input = split_res['OUTPUT']
            else:
                net_input = parameters[self.INPUT_ROADS]

            feedback.pushInfo(f"Yol ağı üzerinden {distance}m servis yolları (Service Area from Layer) hesaplanıyor...")
            service_res = processing.run("native:serviceareafromlayer", {
                'INPUT': net_input,
                'STRATEGY': 0,  # En kısa mesafe
                'DIRECTION_FIELD': '',
                'VALUE_FORWARD': '',
                'VALUE_BACKWARD': '',
                'VALUE_BOTH': '',
                'DEFAULT_DIRECTION': 2,
                'SPEED_FIELD': '',
                'DEFAULT_SPEED': 50.0,
                'TOLERANCE': 0.00015,
                'POINT_TOLERANCE': tolerance,
                'START_POINTS': fac_points,
                'TRAVEL_COST': distance,
                'TRAVEL_COST2': distance,
                'INCLUDE_BOUNDS': False,
                'OUTPUT_LINES': parameters[self.OUTPUT_SERVICE_ROADS] if (self.OUTPUT_SERVICE_ROADS in parameters and parameters[self.OUTPUT_SERVICE_ROADS]) else 'TEMPORARY_OUTPUT'
            }, context=context, feedback=feedback, is_child_algorithm=True)

            srv_lines_lyr = service_res['OUTPUT_LINES']
            if self.OUTPUT_SERVICE_ROADS in parameters and parameters[self.OUTPUT_SERVICE_ROADS]:
                results[self.OUTPUT_SERVICE_ROADS] = srv_lines_lyr

            # Erişim Havzası Poligonları (Convex / Concave Hull by start facility)
            need_polys = (self.OUTPUT_SERVICE_POLYGONS in parameters and parameters[self.OUTPUT_SERVICE_POLYGONS]) or \
                         (self.OUTPUT_DISSOLVED_POLYGONS in parameters and parameters[self.OUTPUT_DISSOLVED_POLYGONS])

            if need_polys:
                feedback.pushInfo("Ağ servis hatlarından gerçek yürüme erişim havzası poligonları türetiliyor...")
                fields = QgsFields()
                fields.append(QgsField("start", QVariant.Type.String if hasattr(QVariant, 'Type') else QVariant.String))
                fields.append(QgsField("mesafe_m", QVariant.Type.Double if hasattr(QVariant, 'Type') else QVariant.Double))
                fields.append(QgsField("ag_alan_ha", QVariant.Type.Double if hasattr(QVariant, 'Type') else QVariant.Double))
                fields.append(QgsField("mpyy_alan_ha", QVariant.Type.Double if hasattr(QVariant, 'Type') else QVariant.Double))
                fields.append(QgsField("pedshed_orani", QVariant.Type.Double if hasattr(QVariant, 'Type') else QVariant.Double))
                fields.append(QgsField("ag_yol_uzunluk_m", QVariant.Type.Double if hasattr(QVariant, 'Type') else QVariant.Double))

                temp_hulls_layer = QgsVectorLayer(f"Polygon?crs={roads_crs.authid()}", "temp_hulls", "memory")
                dp = temp_hulls_layer.dataProvider()
                dp.addAttributes(fields)
                temp_hulls_layer.updateFields()

                if isinstance(srv_lines_lyr, str):
                    lines_source = QgsProcessingUtils.mapLayerFromString(srv_lines_lyr, context)
                    if lines_source is None:
                        lines_source = context.getMapLayer(srv_lines_lyr)
                    if lines_source is None:
                        lines_source = QgsVectorLayer(srv_lines_lyr, "temp_srv", "ogr")
                else:
                    lines_source = srv_lines_lyr

                grouped = {}
                if lines_source and lines_source.isValid():
                    for feat in lines_source.getFeatures():
                        s_key = str(feat["start"]) if "start" in feat.fields().names() else "facility_1"
                        if s_key not in grouped:
                            grouped[s_key] = []
                        grouped[s_key].append(feat)

                mpyy_circle_ha = (math.pi * (distance ** 2)) / 10000.0
                hull_feats = []

                for s_key, feats in grouped.items():
                    geoms = [f.geometry() for f in feats if f.hasGeometry()]
                    if not geoms:
                        continue
                    merged = QgsGeometry.unaryUnion(geoms)
                    if hull_method == 0:
                        hull = merged.convexHull()
                        if hull.type() != QgsWkbTypes.GeometryType.PolygonGeometry:
                            hull = hull.buffer(15.0, 8)
                    elif hull_method == 1:
                        # Concave Hull
                        hull = None
                        with contextlib.suppress(Exception):
                            pts_res = processing.run("native:extractvertices", {
                                'INPUT': merged,
                                'OUTPUT': 'TEMPORARY_OUTPUT'
                            }, context=context, feedback=feedback, is_child_algorithm=True)
                            conc_res = processing.run("native:concavehull", {
                                'INPUT': pts_res['OUTPUT'],
                                'ALPHA': 0.3,
                                'HOLES': False,
                                'OUTPUT': 'TEMPORARY_OUTPUT'
                            }, context=context, feedback=feedback, is_child_algorithm=True)
                            conc_lyr = conc_res['OUTPUT']
                            for cf in conc_lyr.getFeatures():
                                hull = cf.geometry()
                                break
                        if hull is None or hull.isEmpty() or hull.type() != QgsWkbTypes.GeometryType.PolygonGeometry:
                            hull = merged.convexHull()
                            if hull.type() != QgsWkbTypes.GeometryType.PolygonGeometry:
                                hull = hull.buffer(15.0, 8)
                    else:
                        # Koridor Tamponu
                        hull = merged.buffer(30.0, 8)

                    total_road_len = sum(f.geometry().length() for f in feats)
                    area_m2 = hull.area()
                    area_ha = area_m2 / 10000.0
                    pedshed = (area_ha / mpyy_circle_ha) * 100.0 if mpyy_circle_ha > 0 else 0.0

                    poly_feat = QgsFeature(temp_hulls_layer.fields())
                    poly_feat.setGeometry(hull)
                    poly_feat.setAttribute("start", s_key)
                    poly_feat.setAttribute("mesafe_m", float(distance))
                    poly_feat.setAttribute("ag_alan_ha", round(area_ha, 2))
                    poly_feat.setAttribute("mpyy_alan_ha", round(mpyy_circle_ha, 2))
                    poly_feat.setAttribute("pedshed_orani", round(pedshed, 1))
                    poly_feat.setAttribute("ag_yol_uzunluk_m", round(total_road_len, 1))
                    hull_feats.append(poly_feat)

                dp.addFeatures(hull_feats)
                temp_hulls_layer.updateExtents()

                if self.OUTPUT_SERVICE_POLYGONS in parameters and parameters[self.OUTPUT_SERVICE_POLYGONS]:
                    if do_dissolve and len(hull_feats) > 0:
                        diss_res = processing.run("native:dissolve", {
                            'INPUT': temp_hulls_layer,
                            'OUTPUT': parameters[self.OUTPUT_SERVICE_POLYGONS]
                        }, context=context, feedback=feedback, is_child_algorithm=True)
                        results[self.OUTPUT_SERVICE_POLYGONS] = diss_res['OUTPUT']
                    else:
                        (sink_poly, dest_poly_id) = self.parameterAsSink(
                            parameters, self.OUTPUT_SERVICE_POLYGONS, context,
                            temp_hulls_layer.fields(), QgsWkbTypes.Type.MultiPolygon, roads_crs
                        )
                        for feat in temp_hulls_layer.getFeatures():
                            g = feat.geometry()
                            if not g.isMultipart():
                                g.convertToMultiType()
                            feat.setGeometry(g)
                            sink_poly.addFeature(feat, QgsFeatureSink.Flag.FastInsert)
                        results[self.OUTPUT_SERVICE_POLYGONS] = dest_poly_id

                if self.OUTPUT_DISSOLVED_POLYGONS in parameters and parameters[self.OUTPUT_DISSOLVED_POLYGONS]:
                    diss_res2 = processing.run("native:dissolve", {
                        'INPUT': temp_hulls_layer,
                        'OUTPUT': parameters[self.OUTPUT_DISSOLVED_POLYGONS]
                    }, context=context, feedback=feedback, is_child_algorithm=True)
                    results[self.OUTPUT_DISSOLVED_POLYGONS] = diss_res2['OUTPUT']

        return results

    def createInstance(self):
        return ErismeHavzasiAlgorithm()
