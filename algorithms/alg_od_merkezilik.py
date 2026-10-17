# -*- coding: utf-8 -*-
"""OD Maliyet Matrisi, Ağ Güzergâhı, Merkezilik ve Eğim Analizi Algoritması (QNEAT Bağımsız).

DEÜ Mimarlık Fakültesi Şehir ve Bölge Planlama Bölümü
PLN3113 - Tire NİP Analiz Stüdyosu
"""
from __future__ import annotations

import math
from qgis.core import (
    QgsFeature,
    QgsFeatureSink,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsPointXY,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterDistance,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterRasterLayer,
    QgsWkbTypes
)
from qgis.PyQt.QtCore import QVariant

from ..core.network_engine import (
    build_network_graph,
    compute_centrality_metrics,
    compute_road_slope_metrics
)


class OdMerkezilikAlgorithm(QgsProcessingAlgorithm):
    INPUT_ORIGINS = 'INPUT_ORIGINS'
    ORIGIN_ID_FIELD = 'ORIGIN_ID_FIELD'
    INPUT_DESTINATIONS = 'INPUT_DESTINATIONS'
    DEST_ID_FIELD = 'DEST_ID_FIELD'
    INPUT_ROADS = 'INPUT_ROADS'
    INPUT_DEM = 'INPUT_DEM'
    CUTOFF_DIST = 'CUTOFF_DIST'
    ROUTE_MODE = 'ROUTE_MODE'

    OUTPUT_ROUTES = 'OUTPUT_ROUTES'
    OUTPUT_DESIRE = 'OUTPUT_DESIRE'
    OUTPUT_CENTRALITY = 'OUTPUT_CENTRALITY'
    OUTPUT_SLOPE = 'OUTPUT_SLOPE'

    def name(self):
        return 'nip_od_merkezilik_egim'

    def displayName(self):
        return '3. OD Matrisi, Ağ Güzergâhı, Merkezilik ve Yol Eğimi Analizi'

    def group(self):
        return '05. Ulaşım ve Network Analizleri'

    def groupId(self):
        return '05_ulasim_network_analizleri'

    def shortHelpString(self):
        return (
            "Dış eklenti (QNEAT3 veya GRASS) gerektirmeden, saf Python/PyQGIS tabanlı "
            "graf ve Dijkstra motoru ile kapsamlı ulaşım ağı analizi gerçekleştirir:\n\n"
            "1. OD Maliyet Matrisi ve Ağ Güzergâhları: Başlangıç (Origin) ve Hedef (Destination) "
            "noktaları arasında hem gerçek yol ağı güzergâhlarını hem de kuşuçuşu istek hatlarını "
            "üretir. Her bağlantı için Ağ Mesafesi, Kuşuçuşu Mesafe ve Dolaylanma Oranı (Detour Ratio) hesaplar.\n"
            "2. Ağ Merkezilikleri: Sokak ağının Yakınlık (Closeness) ve Arasındalık (Betweenness) "
            "merkezilik değerlerini türetir.\n"
            "3. Yol Eğimi ve Kot Analizi: Sayısal Yükseklik Modeli (DEM) seçilirse, yol akslarının "
            "ortalama eğim yüzdesini ve eğim sınıfını hesaplar."
        )

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT_ORIGINS,
                'Başlangıç Noktaları (Origins - örn: Ada/Parsel Ön Cephe Noktaları)',
                [QgsProcessing.SourceType.TypeVectorPoint]
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.ORIGIN_ID_FIELD,
                'Başlangıç Kimlik / İsim Sütunu (Opsiyonel)',
                parentLayerParameterName=self.INPUT_ORIGINS,
                optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT_DESTINATIONS,
                'Hedef Noktaları (Destinations - örn: Okul, Sağlık, Çarşı vb.)',
                [QgsProcessing.SourceType.TypeVectorPoint]
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.DEST_ID_FIELD,
                'Hedef Kimlik / İsim Sütunu (Opsiyonel)',
                parentLayerParameterName=self.INPUT_DESTINATIONS,
                optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT_ROADS,
                'Ulaşım / Yol Ağı Çizgileri Katmanı',
                [QgsProcessing.SourceType.TypeVectorLine]
            )
        )
        self.addParameter(
            QgsProcessingParameterRasterLayer(
                self.INPUT_DEM,
                'Sayısal Yükseklik Modeli (DEM Rasterı - Eğim Analizi İçin Opsiyonel)',
                optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterDistance(
                self.CUTOFF_DIST,
                'Maksimum Ağ Mesafesi Eşik Değeri (m) (0 = Sınırsız / Tümü)',
                parentParameterName=self.INPUT_ROADS,
                defaultValue=0.0,
                minValue=0.0
            )
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                self.ROUTE_MODE,
                'Güzergâh Çıktı Kapsamı',
                options=['Yalnızca En Yakın Hedefe (Nearest Destination)', 'Tüm Başlangıç-Hedef Çiftleri (All OD Pairs)'],
                defaultValue=0
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_ROUTES,
                'Ağ Güzergâh Hatları (LineString - Gerçek Yol Rotası)',
                QgsProcessing.SourceType.TypeVectorLine
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_DESIRE,
                'Kuşuçuşu İstek Hatları (LineString - Düz Çizgiler)',
                QgsProcessing.SourceType.TypeVectorLine,
                optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_CENTRALITY,
                'Ağ Merkezilik Katmanı (Betweenness / Closeness)',
                QgsProcessing.SourceType.TypeVectorLine,
                optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_SLOPE,
                'Eğim ve Kot Bilgili Yol Ağı (DEM seçilmişse)',
                QgsProcessing.SourceType.TypeVectorLine,
                optional=True
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        source_orig = self.parameterAsSource(parameters, self.INPUT_ORIGINS, context)
        source_dest = self.parameterAsSource(parameters, self.INPUT_DESTINATIONS, context)
        source_roads = self.parameterAsSource(parameters, self.INPUT_ROADS, context)
        dem_layer = self.parameterAsRasterLayer(parameters, self.INPUT_DEM, context)
        cutoff = self.parameterAsDouble(parameters, self.CUTOFF_DIST, context)
        route_mode_idx = self.parameterAsEnum(parameters, self.ROUTE_MODE, context)
        nearest_only = (route_mode_idx == 0)

        col_orig_id = self.parameterAsString(parameters, self.ORIGIN_ID_FIELD, context)
        col_dest_id = self.parameterAsString(parameters, self.DEST_ID_FIELD, context)

        if not source_orig or not source_dest or not source_roads:
            raise QgsProcessingException("Gerekli girdi katmanları bulunamadı!")

        cutoff_val = cutoff if cutoff > 0 else None

        # 1. Ağ Grafını Kur
        feedback.pushInfo("1. Aşama: Ulaşım ağı düğüm-kenar topolojisi kuruluyor...")
        roads_layer = self.parameterAsVectorLayer(parameters, self.INPUT_ROADS, context)
        graph = build_network_graph(roads_layer, tolerance=0.5)
        feedback.pushInfo(f"Graf oluşturuldu: {graph.num_nodes} düğüm, {graph.num_edges} kenar.")

        if graph.num_nodes == 0 or graph.num_edges == 0:
            raise QgsProcessingException("Yol grafı oluşturulamadı. Çizgi katmanını kontrol edin!")

        # Çıktı alanları
        route_fields = QgsFields()
        route_fields.append(QgsField("origin_id", QVariant.String))
        route_fields.append(QgsField("dest_id", QVariant.String))
        route_fields.append(QgsField("ag_mesafe_m", QVariant.Double))
        route_fields.append(QgsField("kusucusu_m", QVariant.Double))
        route_fields.append(QgsField("detour_orani", QVariant.Double))
        route_fields.append(QgsField("hedef_sira", QVariant.Int))

        (sink_routes, dest_routes_id) = self.parameterAsSink(
            parameters,
            self.OUTPUT_ROUTES,
            context,
            route_fields,
            QgsWkbTypes.Type.LineString,
            source_roads.sourceCrs()
        )

        sink_desire = None
        dest_desire_id = None
        if self.OUTPUT_DESIRE in parameters and parameters[self.OUTPUT_DESIRE]:
            (sink_desire, dest_desire_id) = self.parameterAsSink(
                parameters,
                self.OUTPUT_DESIRE,
                context,
                route_fields,
                QgsWkbTypes.Type.LineString,
                source_roads.sourceCrs()
            )

        # Hedefleri düğümlere bağla
        dest_nodes = []
        for feat in source_dest.getFeatures():
            g = feat.geometry()
            if not g or g.isEmpty():
                continue
            pt = g.asPoint() if not g.isMultipart() else g.asMultiPoint()[0]
            nid = graph.find_nearest_node(pt)
            d_label = str(feat[col_dest_id]) if col_dest_id and feat[col_dest_id] is not None else str(feat.id())
            dest_nodes.append((nid, pt, d_label))

        feedback.pushInfo(f"2. Aşama: {source_orig.featureCount()} başlangıç noktasından rotalar çözülüyor...")

        total_orig = source_orig.featureCount()
        for idx_o, f_orig in enumerate(source_orig.getFeatures()):
            if feedback.isCanceled():
                break

            g_o = f_orig.geometry()
            if not g_o or g_o.isEmpty():
                continue

            pt_o = g_o.asPoint() if not g_o.isMultipart() else g_o.asMultiPoint()[0]
            o_node = graph.find_nearest_node(pt_o)
            o_label = str(f_orig[col_orig_id]) if col_orig_id and f_orig[col_orig_id] is not None else str(f_orig.id())

            dist_arr, pred_node, pred_edge = graph.dijkstra_tree(o_node, cutoff=cutoff_val)

            # Hedefleri mesafe sırasına diz
            matched = []
            for d_node, pt_d, d_label in dest_nodes:
                d_cost = float(dist_arr[d_node])
                if math.isinf(d_cost):
                    continue
                euclidean = math.hypot(pt_o.x() - pt_d.x(), pt_o.y() - pt_d.y())
                matched.append((d_cost, euclidean, d_node, pt_d, d_label))

            matched.sort(key=lambda x: x[0])
            if nearest_only and matched:
                matched = [matched[0]]

            for rank, (cost_val, euc_val, d_node, pt_d, d_label) in enumerate(matched, 1):
                detour = round(cost_val / max(1.0, euc_val), 2)
                edge_indices = graph.reconstruct_route(pred_node, pred_edge, o_node, d_node)

                # Gerçek yol geometrisini kenarlardan birleştir
                route_pts = [pt_o]
                for e_idx in edge_indices:
                    e_geom = graph.edge_geoms[e_idx]
                    e_abs = e_geom.constGet()
                    if e_abs:
                        for p_i in range(e_abs.numPoints()):
                            route_pts.append(QgsPointXY(e_abs.pointN(p_i).x(), e_abs.pointN(p_i).y()))
                route_pts.append(pt_d)

                if len(route_pts) >= 2:
                    rf = QgsFeature(route_fields)
                    rf.setGeometry(QgsGeometry.fromPolylineXY(route_pts))
                    rf.setAttributes([o_label, d_label, round(cost_val, 2), round(euc_val, 2), detour, rank])
                    sink_routes.addFeature(rf, QgsFeatureSink.Flag.FastInsert)

                if sink_desire:
                    df = QgsFeature(route_fields)
                    df.setGeometry(QgsGeometry.fromPolylineXY([pt_o, pt_d]))
                    df.setAttributes([o_label, d_label, round(cost_val, 2), round(euc_val, 2), detour, rank])
                    sink_desire.addFeature(df, QgsFeatureSink.Flag.FastInsert)

            if total_orig > 0 and idx_o % 25 == 0:
                feedback.setProgress(int(idx_o / total_orig * 100))

        # 3. Opsiyonel Merkezilik Analizi
        res_dict = {self.OUTPUT_ROUTES: dest_routes_id}
        if dest_desire_id:
            res_dict[self.OUTPUT_DESIRE] = dest_desire_id

        if self.OUTPUT_CENTRALITY in parameters and parameters[self.OUTPUT_CENTRALITY]:
            feedback.pushInfo("3. Aşama: Ağ merkezilik metrikleri (Closeness ve Betweenness) hesaplanıyor...")
            cent_metrics = compute_centrality_metrics(graph, radius=cutoff_val)
            cent_fields = QgsFields(source_roads.fields())
            cent_fields.append(QgsField("betweenness", QVariant.Double))

            (sink_cent, dest_cent_id) = self.parameterAsSink(
                parameters,
                self.OUTPUT_CENTRALITY,
                context,
                cent_fields,
                QgsWkbTypes.Type.MultiLineString,
                source_roads.sourceCrs()
            )
            for e_idx in range(graph.num_edges):
                cf = QgsFeature(cent_fields)
                eg = QgsGeometry(graph.edge_geoms[e_idx])
                if not eg.isMultipart():
                    eg.convertToMultiType()
                cf.setGeometry(eg)
                attrs = [None] * len(source_roads.fields())
                attrs.append(round(float(cent_metrics["edge_betweenness"][e_idx]), 2))
                cf.setAttributes(attrs)
                sink_cent.addFeature(cf, QgsFeatureSink.Flag.FastInsert)
            res_dict[self.OUTPUT_CENTRALITY] = dest_cent_id

        # 4. Opsiyonel Eğim ve Kot Analizi
        if dem_layer and self.OUTPUT_SLOPE in parameters and parameters[self.OUTPUT_SLOPE]:
            feedback.pushInfo("4. Aşama: DEM üzerinden yol aksı kotları ve eğim % hesaplanıyor...")
            slope_fields = QgsFields(source_roads.fields())
            slope_fields.append(QgsField("egim_yuzde", QVariant.Double))
            slope_fields.append(QgsField("egim_sinifi", QVariant.String))
            slope_fields.append(QgsField("delta_z_m", QVariant.Double))

            (sink_slope, dest_slope_id) = self.parameterAsSink(
                parameters,
                self.OUTPUT_SLOPE,
                context,
                slope_fields,
                source_roads.wkbType(),
                source_roads.sourceCrs()
            )
            for r_feat in source_roads.getFeatures():
                rg = r_feat.geometry()
                if not rg or rg.isEmpty():
                    continue
                s_met = compute_road_slope_metrics(rg, dem_layer)
                sf = QgsFeature(slope_fields)
                sf.setGeometry(rg)
                attrs = list(r_feat.attributes())
                attrs.extend([s_met["egim_yuzde"], s_met["egim_sinifi"], s_met["delta_z"]])
                sf.setAttributes(attrs)
                sink_slope.addFeature(sf, QgsFeatureSink.Flag.FastInsert)
            res_dict[self.OUTPUT_SLOPE] = dest_slope_id

        return res_dict

    def createInstance(self):
        return OdMerkezilikAlgorithm()
