# -*- coding: utf-8 -*-
"""Tire NİP ve Kentsel Analiz DockWidget Arayüzü.

DEÜ Mimarlık Fakültesi Şehir ve Bölge Planlama Bölümü
PLN3113 - tire_nip
"""
from __future__ import annotations

import csv
import os
from qgis.PyQt.QtCore import Qt, QVariant, QUrl
from qgis.PyQt.QtGui import QColor, QDesktopServices, QFont, QIcon
from qgis.PyQt.QtWidgets import (
    QComboBox,
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget
)
from qgis.core import (
    QgsCategorizedSymbolRenderer,
    QgsDistanceArea,
    QgsFeature,
    QgsField,
    QgsFields,
    QgsFillSymbol,
    QgsGeometry,
    QgsGraduatedSymbolRenderer,
    QgsMapLayerProxyModel,
    QgsProject,
    QgsRendererCategory,
    QgsRendererRange,
    QgsVectorLayer,
    QgsWkbTypes
)
from qgis.gui import QgsMapLayerComboBox

from .core.cleaner import GeometryCleanerEngine
from .core.field_estimator import FieldEstimatorEngine
from .core.nip_calculator import NipCalculatorEngine
from .core.tire_constants import (
    TIRE_POPULATION_BENCHMARKS,
    get_default_dop_rule,
    get_default_employment_rule,
    get_default_trip_rule,
    norm_tr
)
from .ui_theme import NIP_STUDIO_QSS

PLUGIN_DIR = os.path.dirname(__file__)


class TireNipDockWidget(QDockWidget):
    """Tire NİP ve Kentsel Analiz Stüdyosu Ana Dock Paneli."""

    def __init__(self, iface, parent=None):
        super().__init__("Tire NİP Analiz Stüdyosu (PLN3113)", parent)
        self.iface = iface
        self.setObjectName("TireNipDockWidget")
        self.setStyleSheet(NIP_STUDIO_QSS)

        self._last_nip_summary = None
        self._last_nip_html = ""
        self.last_field_out_layer = None

        self._setup_ui()

    def _setup_ui(self):
        container = QWidget()
        container.setObjectName("TireNipDockBody")
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        # 1. HEADER BANNER
        header_widget = QWidget()
        header_widget.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0f766e, stop:1 #0d9488); "
            "border-radius: 8px; padding: 8px;"
        )
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(8, 6, 8, 6)

        icon_label = QLabel()
        icon_path = os.path.join(PLUGIN_DIR, "icons", "icon.png")
        if os.path.exists(icon_path):
            icon_label.setPixmap(QIcon(icon_path).pixmap(40, 40))
        header_layout.addWidget(icon_label)

        title_layout = QVBoxLayout()
        lbl_title = QLabel("PLN3113 NİP ve Kentsel Analiz Stüdyosu")
        lbl_title.setObjectName("HeaderTitle")
        lbl_sub = QLabel("Dokuz Eylül Üniversitesi | PLN3113 Şehir Planlama Projesi III")
        lbl_sub.setObjectName("HeaderSubtitle")
        title_layout.addWidget(lbl_title)
        title_layout.addWidget(lbl_sub)
        header_layout.addLayout(title_layout)
        header_layout.addStretch()

        self.btn_open_guide = QPushButton("  📚 Metodoloji Rehberi")
        self.btn_open_guide.setCursor(Qt.PointingHandCursor)
        self.btn_open_guide.setToolTip("A'dan Z'ye NİP nüfus, donatı, DOP ve ulaşım teorik metodoloji el kitabını tarayıcıda açar.")
        self.btn_open_guide.setStyleSheet(
            "QPushButton { background: rgba(255, 255, 255, 0.22); color: white; font-weight: bold; "
            "border: 1px solid rgba(255, 255, 255, 0.45); border-radius: 6px; padding: 6px 12px; font-size: 12px; } "
            "QPushButton:hover { background: rgba(255, 255, 255, 0.35); border-color: white; }"
        )
        self.btn_open_guide.clicked.connect(self._open_theoretical_guide)
        header_layout.addWidget(self.btn_open_guide)

        main_layout.addWidget(header_widget)

        # 2. TAB WIDGET
        self.tabs = QTabWidget()
        self.tabs.addTab(self._create_tab_cleaner(), "1. Geometri Temizleme")
        self.tabs.addTab(self._create_tab_nip(), "2. NİP Nüfus, Donatı & DOP")
        self.tabs.addTab(self._create_tab_field(), "3. Saha & Bina Fiili Nüfus")
        main_layout.addWidget(self.tabs)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(container)
        self.setWidget(scroll)

    def _open_theoretical_guide(self):
        """A'dan Z'ye teorik metodoloji el kitabını kullanıcının varsayılan tarayıcısında açar."""
        guide_path = os.path.join(PLUGIN_DIR, "docs", "teorik_rehber.html")
        if os.path.exists(guide_path):
            from qgis.PyQt.QtCore import QUrl
            from qgis.PyQt.QtGui import QDesktopServices
            QDesktopServices.openUrl(QUrl.fromLocalFile(guide_path))
        else:
            QMessageBox.warning(self, "Uyarı", f"Metodoloji rehberi dosyası bulunamadı:\n{guide_path}")

    # -----------------------------------------------------------------
    # SEKME 1: GEOMETRİ & DUPLİKE TEMİZLEME
    # -----------------------------------------------------------------
    def _create_tab_cleaner(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        box_input = QGroupBox("Girdi Katmanı Seçimi")
        box_layout = QVBoxLayout(box_input)

        lbl = QLabel("Temizlenecek Poligon Katmanı (Örn: nipt_test.gpkg):")
        box_layout.addWidget(lbl)

        self.cmb_clean_layer = QgsMapLayerComboBox()
        self.cmb_clean_layer.setFilters(QgsMapLayerProxyModel.PolygonLayer)
        box_layout.addWidget(self.cmb_clean_layer)

        info_lbl = QLabel(
            "<b>İşlem Kapsamı:</b><br>"
            "• Kendini kesen veya hatalı halkaları (Self-intersection / Ring-crossing) <code>makeValid</code> ile onarır.<br>"
            "• Üst üste binen aynı geometriye sahip mükerrer (duplike) poligonları tespit edip tekilleştirir.<br>"
            "• Orijinal katmanınıza dokunmaz, temiz ve analiz hazır yeni bir katman üretir."
        )
        info_lbl.setWordWrap(True)
        info_lbl.setStyleSheet("color: #475569; font-size: 11px; background: #f1f5f9; padding: 8px; border-radius: 4px;")
        box_layout.addWidget(info_lbl)

        layout.addWidget(box_input)

        self.btn_run_clean = QPushButton("  Geometriyi Onar ve Duplikeleri Ayıkla")
        self.btn_run_clean.setObjectName("CleanButton")
        clean_icon_path = os.path.join(PLUGIN_DIR, "icons", "clean.png")
        if os.path.exists(clean_icon_path):
            self.btn_run_clean.setIcon(QIcon(clean_icon_path))
        self.btn_run_clean.clicked.connect(self._run_geometry_clean)
        layout.addWidget(self.btn_run_clean)

        self.clean_progress = QProgressBar()
        self.clean_progress.setVisible(False)
        layout.addWidget(self.clean_progress)

        self.txt_clean_log = QTextEdit()
        self.txt_clean_log.setReadOnly(True)
        self.txt_clean_log.setMaximumHeight(160)
        self.txt_clean_log.setPlaceholderText("Temizleme işlem sonuçları burada listelenecektir...")
        layout.addWidget(self.txt_clean_log)

        layout.addStretch()
        return tab

    def _run_geometry_clean(self):
        layer = self.cmb_clean_layer.currentLayer()
        if not layer or not isinstance(layer, QgsVectorLayer):
            QMessageBox.warning(self, "Uyarı", "Lütfen geçerli bir poligon katmanı seçin!")
            return

        orig_layer_name = layer.name()

        self.btn_run_clean.setEnabled(False)
        self.clean_progress.setVisible(True)
        self.clean_progress.setRange(0, 0)
        self.txt_clean_log.clear()
        self.txt_clean_log.append(f"<b>Katman taranıyor:</b> {orig_layer_name} ({layer.featureCount():,} obje)...")

        try:
            cleaned_feats, stats = GeometryCleanerEngine.clean_layer(layer)

            # Yeni Memory Katmanı oluştur
            uri = f"MultiPolygon?crs={layer.crs().authid()}"
            out_name = f"{orig_layer_name}_TEMIZLENMIS"
            out_layer = QgsVectorLayer(uri, out_name, "memory")
            out_prov = out_layer.dataProvider()
            out_prov.addAttributes(layer.fields())
            out_layer.updateFields()
            out_prov.addFeatures(cleaned_feats)
            out_layer.updateExtents()

            QgsProject.instance().addMapLayer(out_layer)

            # cmb_clean_layer'ın yeni katmana otomatik kaymasını önle:
            # Orijinal girdi katmanını listede seçili tutuyoruz
            self.cmb_clean_layer.setLayer(layer)

            # 2. Sekmedeki NİP analiz katmanını ise otomatik olarak yeni temiz katmana geçir
            self.cmb_nip_layer.setLayer(out_layer)

            dup_oran = stats.get('duplike_orani', round((stats['duplike_elenen']/max(1, stats['toplam_girdi']))*100, 1))

            log_text = (
                f"✅ <b>Temizleme Başarıyla Tamamlandı!</b><br>"
                f"• Girdi Katmanı: <b>{orig_layer_name}</b><br>"
                f"• Toplam Taranan Obje: <b>{stats['toplam_girdi']:,}</b><br>"
                f"• Ayıklanan Mükerrer (Duplike) Poligon: <b style='color:#dc2626;'>{stats['duplike_elenen']:,}</b> (%{dup_oran})<br>"
                f"• Onarılan Geçersiz Geometri: <b>{stats['gecersiz_onarilan']:,}</b><br>"
                f"• Temiz Çıktı Obje Sayısı: <b style='color:#16a34a;'>{stats['temiz_cikan']:,}</b><br>"
                f"Yeni katman <i>'{out_name}'</i> haritaya eklendi ve 2. Sekme (NİP Analiz) için seçildi."
            )
            self.txt_clean_log.setHtml(log_text)

            if stats['duplike_elenen'] > 0 or stats['gecersiz_onarilan'] > 0:
                QMessageBox.information(
                    self, "Geometri Temizleme Başarılı",
                    f"Girdi Katmanı: {orig_layer_name} ({stats['toplam_girdi']:,} obje)\n\n"
                    f"✅ {stats['duplike_elenen']:,} adet mükerrer (duplike) poligon ayıklandı (%{dup_oran}).\n"
                    f"✅ {stats['gecersiz_onarilan']:,} adet geçersiz geometri onarıldı.\n\n"
                    f"Temiz Çıktı: {stats['temiz_cikan']:,} adet tekil ada içeren '{out_name}' katmanı oluşturuldu."
                )
            else:
                extra = ""
                if "_TEMIZLENMIS" in orig_layer_name:
                    extra = "\n\n(Not: Seçili katman zaten daha önce temizlenmiş bir katmandır. Orijinal ham katmanı temizlemek için lütfen açılır kutudan ham katmanı seçiniz.)"
                QMessageBox.information(
                    self, "Mükerrer Bulunamadı",
                    f"'{orig_layer_name}' katmanında ({stats['toplam_girdi']:,} obje) herhangi bir mükerrer poligon veya geçersiz geometriye rastlanmadı.{extra}"
                )

        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Temizleme sırasında hata: {str(e)}")
            self.txt_clean_log.append(f"<span style='color:red;'>Hata: {str(e)}</span>")
        finally:
            self.btn_run_clean.setEnabled(True)
            self.clean_progress.setVisible(False)

    # -----------------------------------------------------------------
    # SEKME 2: NİP PLAN NÜFUSU, DONATI, KAMU-ÖZEL & DOP ANALİZİ
    # -----------------------------------------------------------------
    def _create_tab_nip(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        # Bilgi Barı
        info_banner = QWidget()
        info_banner.setStyleSheet("background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 6px; padding: 4px;")
        info_l = QHBoxLayout(info_banner)
        info_l.setContentsMargins(6, 4, 6, 4)
        lbl_hint = QLabel("💡 <b>Tire NİP Metodolojisi:</b> Nüfus aralıkları, MPYY Ek-2 standartları, DOP ve yol formülleri.")
        lbl_hint.setStyleSheet("color: #1e40af; font-size: 11px;")
        btn_hint_guide = QPushButton("📖 Metodoloji El Kitabı")
        btn_hint_guide.setCursor(Qt.PointingHandCursor)
        btn_hint_guide.setStyleSheet("background: #2563eb; color: white; border-radius: 4px; padding: 3px 8px; font-size: 11px; font-weight: bold;")
        btn_hint_guide.clicked.connect(self._open_theoretical_guide)
        info_l.addWidget(lbl_hint)
        info_l.addStretch()
        info_l.addWidget(btn_hint_guide)
        layout.addWidget(info_banner)

        # 1. Girdi Kutusu
        box_nip = QGroupBox("NİP & Fiziki Mevcut Durum Katmanı ve Parametreler")
        f_layout = QFormLayout(box_nip)

        self.cmb_analysis_mode = QComboBox()
        self.cmb_analysis_mode.addItem("Nazım İmar Planı (NİP - Öneri / Revizyon)")
        self.cmb_analysis_mode.addItem("Fiziki Mevcut Durum (TUCBS / Arazi Kullanımı)")
        self.cmb_analysis_mode.currentIndexChanged.connect(self._on_analysis_mode_changed)
        f_layout.addRow("Analiz Modu / Kapsam:", self.cmb_analysis_mode)

        self.cmb_nip_layer = QgsMapLayerComboBox()
        self.cmb_nip_layer.setFilters(QgsMapLayerProxyModel.PolygonLayer)
        self.cmb_nip_layer.layerChanged.connect(self._on_nip_layer_changed)
        f_layout.addRow("Analiz Katmanı (Poligon):", self.cmb_nip_layer)

        self.cmb_fonk_field = QComboBox()
        self.cmb_fonk_field.currentTextChanged.connect(self._on_fonk_col_changed)
        f_layout.addRow("Birincil Fonksiyon / TUCBS Sütunu:", self.cmb_fonk_field)

        self.cmb_secondary_fonk_field = QComboBox()
        self.cmb_secondary_fonk_field.currentTextChanged.connect(self._on_fonk_col_changed)
        f_layout.addRow("Tamamlayıcı / İkincil Sütun (Opsiyonel):", self.cmb_secondary_fonk_field)

        self.cmb_sinir_layer = QgsMapLayerComboBox()
        self.cmb_sinir_layer.setFilters(QgsMapLayerProxyModel.PolygonLayer)
        self.cmb_sinir_layer.setAllowEmptyLayer(True)
        f_layout.addRow("Plan Onama Sınırı (Opsiyonel):", self.cmb_sinir_layer)

        self.cmb_yol_layer = QgsMapLayerComboBox()
        self.cmb_yol_layer.setFilters(QgsMapLayerProxyModel.LineLayer)
        self.cmb_yol_layer.setAllowEmptyLayer(True)
        f_layout.addRow("Yol Aksları Katmanı (Opsiyonel):", self.cmb_yol_layer)

        self.spn_proj_nufus = QSpinBox()
        self.spn_proj_nufus.setRange(1000, 500000)
        self.spn_proj_nufus.setValue(65000)
        self.spn_proj_nufus.setSingleStep(1000)
        self.spn_proj_nufus.setSuffix(" Kişi")
        f_layout.addRow("Projeksiyon Hedef Nüfusu:", self.spn_proj_nufus)

        layout.addWidget(box_nip)

        # 2. Planlama, DOP, İstihdam & Yolculuk Kuralları (Dahil / Hariç) - Açılır Kutu
        self.box_rules = QGroupBox("⚙️ İstihdam, Yolculuk & DOP Kuralları (Dahil / Hariç ve Katsayılar)")
        self.box_rules.setCheckable(True)
        self.box_rules.setChecked(False)  # Başlangıçta derli toplu dursun
        rules_layout = QVBoxLayout(self.box_rules)

        lbl_rules_info = QLabel(
            "<b>Dahil / Hariç Düzeni:</b> Varsayılan planlama katsayıları ve DOP kapsamı aktiftir. "
            "İstediğiniz fonksiyonu DOP içi (düzenlemeye dahil) veya nDOP / DOP Dışı (harice ayrılan) olarak seçebilir; "
            "istihdam veya yolculuktan hariç tutabilir ya da katsayılarını değiştirebilirsiniz."
        )
        lbl_rules_info.setWordWrap(True)
        lbl_rules_info.setStyleSheet("color: #0f766e; font-size: 11px; background: #f0fdfa; padding: 6px; border-radius: 4px;")
        rules_layout.addWidget(lbl_rules_info)

        btn_rules_bar = QHBoxLayout()
        self.btn_load_fonks = QPushButton("🔄 Katmandan Fonksiyonları Oku")
        self.btn_load_fonks.clicked.connect(self._load_rules_table_from_layer)
        self.btn_reset_rules = QPushButton("Varsayılanlara Sıfırla")
        self.btn_reset_rules.clicked.connect(self._reset_rules_to_defaults)
        btn_rules_bar.addWidget(self.btn_load_fonks)
        btn_rules_bar.addWidget(self.btn_reset_rules)
        rules_layout.addLayout(btn_rules_bar)

        self.tbl_rules = QTableWidget()
        self.tbl_rules.setColumnCount(9)
        self.tbl_rules.setHorizontalHeaderLabels([
            "Plan Fonksiyonu", "DOP İçi (Dahil)?", "DOP Türü",
            "İstihdam Dahil?", "m²/Çalışan", "Verim (0-1)",
            "Araç Dahil?", "Yaya Dahil?", "Araç (100m²)"
        ])
        self.tbl_rules.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tbl_rules.horizontalHeader().setStretchLastSection(True)
        self.tbl_rules.verticalHeader().setVisible(False)
        self.tbl_rules.setMinimumHeight(150)
        self.tbl_rules.setMaximumHeight(230)
        self.tbl_rules.itemChanged.connect(self._on_rules_table_item_changed)
        rules_layout.addWidget(self.tbl_rules)

        layout.addWidget(self.box_rules)

        # 3. Nüfus Gösterge & Kıyaslama Tablosu
        box_bench = QGroupBox("Tire Tarihsel Nüfus ve Projeksiyon Gösterge Paneli")
        bench_layout = QVBoxLayout(box_bench)

        self.tbl_benchmark = QTableWidget(5, 4)
        self.tbl_benchmark.setHorizontalHeaderLabels([
            "Nüfus Niteliği / Kapsam", "Kentsel Merkez", "Kırsal Nüfus", "İlçe Toplamı"
        ])
        self.tbl_benchmark.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_benchmark.verticalHeader().setVisible(False)
        self.tbl_benchmark.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl_benchmark.setMaximumHeight(140)

        bench_rows = [
            ("1997 Plan Raporu (1990 DİE)", "37.855", "39.459 (65 Köy)", "77.314"),
            ("2015 Plan Projeksiyonu (Hedef)", "53.629", "46.711 (Model)", "100.340"),
            ("2015 TÜİK ADNKS (Gerçekleşen)", "~57.069", "~25.033", "82.102"),
            ("Güncel TÜİK ADNKS (2025/2026)", "~61.738", "~25.833", "87.571"),
            ("Hesaplanan 1/5000 NİP Kapasitesi", "Hesaplanmadı", "-", "Hesaplanmadı")
        ]
        for r_idx, (k, m, r, i) in enumerate(bench_rows):
            self.tbl_benchmark.setItem(r_idx, 0, QTableWidgetItem(k))
            self.tbl_benchmark.setItem(r_idx, 1, QTableWidgetItem(m))
            self.tbl_benchmark.setItem(r_idx, 2, QTableWidgetItem(r))
            self.tbl_benchmark.setItem(r_idx, 3, QTableWidgetItem(i))

        font = QFont()
        font.setBold(True)
        for c in range(4):
            item = self.tbl_benchmark.item(4, c)
            if item:
                item.setFont(font)
                item.setForeground(QColor("#0f766e"))

        bench_layout.addWidget(self.tbl_benchmark)

        lbl_bench_note = QLabel(
            "<small style='color:#64748b;'>📌 <i>6360 sayılı yasa sonrası köyler mahalleye dönüştüğünden 2015 ve güncel kentsel merkez, "
            "yerleşik leke içindeki mahalleler toplamıdır. Kırsal nüfus farktan elde edilmiştir. "
            "Güncel resmi veri 31 Aralık 2025 referanslı kütüktür (87.571 kişi).</i></small>"
        )
        lbl_bench_note.setWordWrap(True)
        bench_layout.addWidget(lbl_bench_note)
        layout.addWidget(box_bench)

        # 4. Çalıştır Butonu
        self.btn_run_nip = QPushButton("  PLN3113 NİP Nüfus, Donatı, Kamu-Özel ve DOP Analizini Başlat")
        self.btn_run_nip.setObjectName("PrimaryButton")
        plan_icon_path = os.path.join(PLUGIN_DIR, "icons", "plan.png")
        if os.path.exists(plan_icon_path):
            self.btn_run_nip.setIcon(QIcon(plan_icon_path))
        self.btn_run_nip.clicked.connect(self._run_nip_analysis)
        layout.addWidget(self.btn_run_nip)

        # 5. Dışa Aktarma Buton Çubuğu
        export_bar = QHBoxLayout()
        self.btn_export_csv = QPushButton("  Tabloları CSV (Excel) Kaydet")
        self.btn_export_csv.clicked.connect(self._export_nip_tables_csv)
        self.btn_export_csv.setEnabled(False)

        self.btn_export_html = QPushButton("  Raporu HTML Kaydet")
        self.btn_export_html.clicked.connect(self._export_nip_report_html)
        self.btn_export_html.setEnabled(False)

        export_bar.addWidget(self.btn_export_csv)
        export_bar.addWidget(self.btn_export_html)
        layout.addLayout(export_bar)

        # 6. Sonuç Sekmeleri (Tab Widget)
        self.tabs_nip_results = QTabWidget()
        self.tabs_nip_results.setMinimumHeight(280)

        # 1. Alt Sekme: ⚖️ Kamu-Özel & DOP Dengesi
        self.tbl_dop = QTableWidget()
        self.tbl_dop.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl_dop.verticalHeader().setVisible(False)
        self.tabs_nip_results.addTab(self.tbl_dop, "⚖️ Kamu-Özel & DOP")

        # 2. Alt Sekme: 🏛️ Kent Karakteri Tablosu
        self.tbl_kent_karakter = QTableWidget()
        self.tbl_kent_karakter.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl_kent_karakter.verticalHeader().setVisible(False)
        self.tabs_nip_results.addTab(self.tbl_kent_karakter, "🏛️ Kent Karakteri")

        # 3. Alt Sekme: 📋 MPYY Ek-2 Donatı Dengesi
        self.tbl_ek2 = QTableWidget()
        self.tbl_ek2.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl_ek2.verticalHeader().setVisible(False)
        self.tabs_nip_results.addTab(self.tbl_ek2, "📋 Ek-2 Donatı")

        # 4. Alt Sekme: 📊 Fonksiyon Dağılım Tablosu
        self.tbl_fonk_dagilim = QTableWidget()
        self.tbl_fonk_dagilim.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl_fonk_dagilim.verticalHeader().setVisible(False)
        self.tabs_nip_results.addTab(self.tbl_fonk_dagilim, "📊 Fonksiyon Dağılımı")

        # 5. Alt Sekme: 📑 Detaylı HTML Konsol Özeti
        self.txt_nip_results = QTextEdit()
        self.txt_nip_results.setReadOnly(True)
        self.txt_nip_results.setPlaceholderText("Analiz sonuçları, DOP hesabı, kent karakteri ve donatı dengesi burada görüntülenecektir...")
        self.tabs_nip_results.addTab(self.txt_nip_results, "📑 Detaylı Rapor")

        layout.addWidget(self.tabs_nip_results)

        layout.addStretch()
        self._on_nip_layer_changed()
        return tab

    def _on_analysis_mode_changed(self, idx: int):
        self._load_rules_table_from_layer()

    def _on_nip_layer_changed(self):
        layer = self.cmb_nip_layer.currentLayer()
        self.cmb_fonk_field.clear()
        self.cmb_secondary_fonk_field.clear()
        self.cmb_secondary_fonk_field.addItem("<Yok / İkincil Sütun Yok>")
        if not layer or not isinstance(layer, QgsVectorLayer):
            return

        fields = [f.name() for f in layer.fields()]
        self.cmb_fonk_field.addItems(fields)
        self.cmb_secondary_fonk_field.addItems(fields)

        fields_lower = {f.lower(): f for f in fields}
        layer_name_lower = layer.name().lower()

        # Otomatik Mod ve Sütun Tespiti
        is_fiziki = (
            "tucbs_sinifi" in fields_lower
            or "arazi_kullanim_tanimi" in fields_lower
            or "kadastro" in layer_name_lower
            or "fiziki" in layer_name_lower
            or "mevcut" in layer_name_lower
        )

        if is_fiziki:
            # Fiziki Mevcut Durum Modu (TUCBS)
            self.cmb_analysis_mode.setCurrentIndex(1)
            if "tucbs_sinifi" in fields_lower:
                self.cmb_fonk_field.setCurrentText(fields_lower["tucbs_sinifi"])
            elif "arazi_kullanim_tanimi" in fields_lower:
                self.cmb_fonk_field.setCurrentText(fields_lower["arazi_kullanim_tanimi"])

            if "arazi_kullanim_tanimi" in fields_lower and self.cmb_fonk_field.currentText() != fields_lower["arazi_kullanim_tanimi"]:
                self.cmb_secondary_fonk_field.setCurrentText(fields_lower["arazi_kullanim_tanimi"])
        else:
            # Standart NİP Modu
            self.cmb_analysis_mode.setCurrentIndex(0)
            priority = ["Ort__Detay", "Ort_Detay", "nipfonksiyon", "plan_fonksiyon", "fonksiyon", "Kullan__m_"]
            for p in priority:
                if p in fields:
                    self.cmb_fonk_field.setCurrentText(p)
                    break
            self.cmb_secondary_fonk_field.setCurrentIndex(0)

        # Fonksiyon tablosunu katmandan otomatik doldur
        self._load_rules_table_from_layer()

    def _on_fonk_col_changed(self, col_name: str = ""):
        self._load_rules_table_from_layer(preserve_custom=False)

    def _load_rules_table_from_layer(self, preserve_custom: bool = True):
        """Seçili katmandaki fonksiyonları okuyup kurallar tablosuna doldurur.
        Daha önce yapılmış kullanıcı özelleştirmeleri varsa korur, yeni fonksiyonlar için varsayılanları atar.
        """
        layer = self.cmb_nip_layer.currentLayer()
        col = self.cmb_fonk_field.currentText()
        if not layer or not isinstance(layer, QgsVectorLayer) or not col:
            return

        idx = layer.fields().indexOf(col)
        if idx == -1:
            return

        sec_col = self.cmb_secondary_fonk_field.currentText() if hasattr(self, 'cmb_secondary_fonk_field') else ""
        sec_idx = layer.fields().indexOf(sec_col) if sec_col and not sec_col.startswith("<") else -1

        unique_fonks_set = set()
        for feat in layer.getFeatures():
            val1 = feat[idx]
            val = None
            if val1 is not None and str(val1).strip() not in ("", "NULL", "None"):
                val = str(val1).strip()
            elif sec_idx != -1:
                val2 = feat[sec_idx]
                if val2 is not None and str(val2).strip() not in ("", "NULL", "None"):
                    val = str(val2).strip()
            if val:
                unique_fonks_set.add(val)

        unique_fonks = sorted(list(unique_fonks_set))
        if not unique_fonks:
            return

        # Mevcut kullanıcı düzenlemelerini fonksiyon adına göre sakla
        existing_custom = {}
        if preserve_custom and self.tbl_rules.rowCount() > 0:
            for r in range(self.tbl_rules.rowCount()):
                f_item = self.tbl_rules.item(r, 0)
                if not f_item:
                    continue
                f_txt = f_item.text().strip()
                d_item = self.tbl_rules.item(r, 1)
                c_dop = self.tbl_rules.cellWidget(r, 2)
                e_item = self.tbl_rules.item(r, 3)
                s_item = self.tbl_rules.item(r, 4)
                ef_item = self.tbl_rules.item(r, 5)
                a_item = self.tbl_rules.item(r, 6)
                y_item = self.tbl_rules.item(r, 7)
                ra_item = self.tbl_rules.item(r, 8)
                existing_custom[f_txt] = {
                    "dop_inc": (d_item.checkState() == Qt.Checked) if d_item else True,
                    "dop_combo_idx": c_dop.currentIndex() if (c_dop and isinstance(c_dop, QComboBox)) else 0,
                    "emp_inc": (e_item.checkState() == Qt.Checked) if e_item else True,
                    "std_m2": s_item.text().strip() if s_item else "50.0",
                    "eff": ef_item.text().strip() if ef_item else "0.50",
                    "tr_arac": (a_item.checkState() == Qt.Checked) if a_item else True,
                    "tr_yaya": (y_item.checkState() == Qt.Checked) if y_item else True,
                    "r_arac": ra_item.text().strip() if ra_item else "1.0",
                }

        self.tbl_rules.blockSignals(True)
        self.tbl_rules.setRowCount(len(unique_fonks))
        for r_idx, fonk in enumerate(unique_fonks):
            # 0. Fonksiyon adı (Salt okunur)
            item_f = QTableWidgetItem(fonk)
            item_f.setFlags(item_f.flags() & ~Qt.ItemIsEditable)
            self.tbl_rules.setItem(r_idx, 0, item_f)

            if fonk in existing_custom:
                saved = existing_custom[fonk]
                dop_inc = saved["dop_inc"]
                combo_idx = saved["dop_combo_idx"]
                emp_inc = saved["emp_inc"]
                std_m2_str = saved["std_m2"]
                eff_str = saved["eff"]
                tr_arac = saved["tr_arac"]
                tr_yaya = saved["tr_yaya"]
                r_arac_str = saved["r_arac"]
            else:
                dop_inc, dop_durumu, dop_turu = get_default_dop_rule(fonk)
                if not dop_inc or "HARİÇ" in dop_turu.upper() or "HARIC" in norm_tr(dop_turu):
                    combo_idx = 2
                elif "ÖZEL" in dop_turu.upper():
                    combo_idx = 0
                else:
                    combo_idx = 1

                emp_inc, std_m2, eff = get_default_employment_rule(fonk)
                std_m2_str = str(std_m2) if std_m2 > 0 else "50.0"
                eff_str = str(eff) if eff > 0 else "0.50"

                tr_arac, tr_yaya, r_arac, _ = get_default_trip_rule(fonk)
                r_arac_str = str(r_arac) if r_arac > 0 else "1.0"

            # 1-2. DOP Dahil / Hariç ve DOP Türü
            item_dop = QTableWidgetItem("DOP İçi" if dop_inc else "nDOP (Hariç)")
            item_dop.setFlags(item_dop.flags() | Qt.ItemIsUserCheckable)
            item_dop.setCheckState(Qt.Checked if dop_inc else Qt.Unchecked)
            item_dop.setToolTip("İşaretli ise Düzenleme Sahasına Dahil (DOP İçi) edilir. İşaretsiz ise Harice Ayrılan (nDOP / DOP Dışı) alandır.")
            self.tbl_rules.setItem(r_idx, 1, item_dop)

            combo_dop = QComboBox()
            combo_dop.addItems([
                "DOP İçi - Özel (Tahsis)",
                "DOP İçi - Kamu (Kesinti)",
                "nDOP - DOP Dışı (Hariç)"
            ])
            combo_dop.setCurrentIndex(combo_idx)
            combo_dop.currentIndexChanged.connect(lambda idx, row=r_idx: self._on_dop_combo_changed(row, idx))
            self.tbl_rules.setCellWidget(r_idx, 2, combo_dop)

            # 3-5. İstihdam varsayılanları
            item_emp = QTableWidgetItem("Dahil" if emp_inc else "Hariç")
            item_emp.setFlags(item_emp.flags() | Qt.ItemIsUserCheckable)
            item_emp.setCheckState(Qt.Checked if emp_inc else Qt.Unchecked)
            self.tbl_rules.setItem(r_idx, 3, item_emp)

            item_std = QTableWidgetItem(std_m2_str)
            self.tbl_rules.setItem(r_idx, 4, item_std)

            item_eff = QTableWidgetItem(eff_str)
            self.tbl_rules.setItem(r_idx, 5, item_eff)

            # 6-8. Yolculuk varsayılanları
            item_arac = QTableWidgetItem("Dahil" if tr_arac else "Hariç")
            item_arac.setFlags(item_arac.flags() | Qt.ItemIsUserCheckable)
            item_arac.setCheckState(Qt.Checked if tr_arac else Qt.Unchecked)
            self.tbl_rules.setItem(r_idx, 6, item_arac)

            item_yaya = QTableWidgetItem("Dahil" if tr_yaya else "Hariç")
            item_yaya.setFlags(item_yaya.flags() | Qt.ItemIsUserCheckable)
            item_yaya.setCheckState(Qt.Checked if tr_yaya else Qt.Unchecked)
            self.tbl_rules.setItem(r_idx, 7, item_yaya)

            item_r_arac = QTableWidgetItem(r_arac_str)
            self.tbl_rules.setItem(r_idx, 8, item_r_arac)

        self.tbl_rules.blockSignals(False)

    def _on_rules_table_item_changed(self, item: QTableWidgetItem):
        """Kullanıcı kurallar tablosunda onay kutusunu değiştirdiğinde ilgili metin ve kontrolleri senkronize eder."""
        col = item.column()
        row = item.row()

        if col == 1:  # DOP İçi (Dahil)?
            is_checked = (item.checkState() == Qt.Checked)
            self.tbl_rules.blockSignals(True)
            item.setText("DOP İçi" if is_checked else "nDOP (Hariç)")
            self.tbl_rules.blockSignals(False)

            combo = self.tbl_rules.cellWidget(row, 2)
            if combo and isinstance(combo, QComboBox):
                combo.blockSignals(True)
                if not is_checked:
                    combo.setCurrentIndex(2)  # nDOP - DOP Dışı (Hariç)
                else:
                    if combo.currentIndex() == 2:
                        f_item = self.tbl_rules.item(row, 0)
                        fonk = f_item.text().strip() if f_item else ""
                        _, _, def_turu = get_default_dop_rule(fonk)
                        combo.setCurrentIndex(0 if "ÖZEL" in def_turu.upper() else 1)
                combo.blockSignals(False)

        elif col == 3:  # İstihdam Dahil?
            self.tbl_rules.blockSignals(True)
            item.setText("Dahil" if item.checkState() == Qt.Checked else "Hariç")
            self.tbl_rules.blockSignals(False)

        elif col == 6:  # Araç Dahil?
            self.tbl_rules.blockSignals(True)
            item.setText("Dahil" if item.checkState() == Qt.Checked else "Hariç")
            self.tbl_rules.blockSignals(False)

        elif col == 7:  # Yaya Dahil?
            self.tbl_rules.blockSignals(True)
            item.setText("Dahil" if item.checkState() == Qt.Checked else "Hariç")
            self.tbl_rules.blockSignals(False)

    def _on_dop_combo_changed(self, row: int, index: int):
        """DOP Türü açılır kutusu değiştiğinde DOP İçi (Dahil)? onay kutusunu senkronize eder."""
        item_dop = self.tbl_rules.item(row, 1)
        if not item_dop:
            return
        self.tbl_rules.blockSignals(True)
        if index == 2:  # nDOP - DOP Dışı (Hariç)
            item_dop.setCheckState(Qt.Unchecked)
            item_dop.setText("nDOP (Hariç)")
        else:
            item_dop.setCheckState(Qt.Checked)
            item_dop.setText("DOP İçi")
        self.tbl_rules.blockSignals(False)

    def _reset_rules_to_defaults(self):
        """Kurallar tablosunu sıfırlayıp katmandan varsayılanlarla yeniden doldurur."""
        self._load_rules_table_from_layer(preserve_custom=False)

    def _get_rules_config(self) -> dict | None:
        """Kullanıcının kurallar tablosundaki seçimlerini dict olarak çıkarır."""
        if not self.box_rules.isChecked() or self.tbl_rules.rowCount() == 0:
            return None

        dop_rules = {}
        emp_rules = {}
        trip_rules = {}

        for r in range(self.tbl_rules.rowCount()):
            f_item = self.tbl_rules.item(r, 0)
            if not f_item:
                continue
            fonk = f_item.text().strip()
            fn = norm_tr(fonk)

            # 1. DOP Kuralı (DOP İçi vs nDOP / Harice Ayrılan)
            dop_item = self.tbl_rules.item(r, 1)
            inc_dop = (dop_item.checkState() == Qt.Checked) if dop_item else True
            combo_dop = self.tbl_rules.cellWidget(r, 2)
            if combo_dop and isinstance(combo_dop, QComboBox):
                c_idx = combo_dop.currentIndex()
                if c_idx == 0:
                    dop_durumu_val = "DOP İÇİ"
                    dop_turu_val = "DOP İÇİ - ÖZEL (TAHSİS)"
                elif c_idx == 1:
                    dop_durumu_val = "DOP İÇİ"
                    dop_turu_val = "DOP İÇİ - KAMU (KESİNTİ)"
                else:
                    dop_durumu_val = "DOP DIŞI"
                    dop_turu_val = "DOP DIŞI (HARİÇ)"
                    inc_dop = False
            else:
                dop_durumu_val = "DOP İÇİ" if inc_dop else "DOP DIŞI"
                dop_turu_val = "DOP İÇİ - ÖZEL (TAHSİS)" if inc_dop else "DOP DIŞI (HARİÇ)"

            if not inc_dop:
                dop_durumu_val = "DOP DIŞI"
                dop_turu_val = "DOP DIŞI (HARİÇ)"

            dop_rules[fn] = {
                "include": inc_dop,
                "dop_durumu": dop_durumu_val,
                "dop_turu": dop_turu_val
            }

            # 2. İstihdam Kuralı
            emp_item = self.tbl_rules.item(r, 3)
            inc_emp = (emp_item.checkState() == Qt.Checked) if emp_item else True
            try:
                std_m2 = float(self.tbl_rules.item(r, 4).text().strip())
            except (ValueError, AttributeError):
                std_m2 = 50.0
            try:
                eff = float(self.tbl_rules.item(r, 5).text().strip())
            except (ValueError, AttributeError):
                eff = 0.5

            emp_rules[fn] = {"include": inc_emp, "m2_per_worker": std_m2, "eff": eff}

            # 3. Yolculuk Kuralı
            arac_item = self.tbl_rules.item(r, 6)
            yaya_item = self.tbl_rules.item(r, 7)
            inc_arac = (arac_item.checkState() == Qt.Checked) if arac_item else True
            inc_yaya = (yaya_item.checkState() == Qt.Checked) if yaya_item else True
            try:
                r_arac = float(self.tbl_rules.item(r, 8).text().strip())
            except (ValueError, AttributeError):
                r_arac = 1.0

            trip_rules[fn] = {
                "include_arac": inc_arac,
                "include_yaya": inc_yaya,
                "rate_arac": r_arac,
                "rate_yaya": 2.0
            }

        return {"dop": dop_rules, "employment": emp_rules, "trips": trip_rules}

    def _populate_table(self, tbl: QTableWidget, headers: list[str], rows: list[list]):
        """QTableWidget tablosunu verilen başlık ve satırlarla doldurur."""
        tbl.clear()
        tbl.setColumnCount(len(headers))
        tbl.setRowCount(len(rows))
        tbl.setHorizontalHeaderLabels(headers)
        for r_idx, row in enumerate(rows):
            for c_idx, val in enumerate(row):
                item = QTableWidgetItem(str(val))
                tbl.setItem(r_idx, c_idx, item)
        tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        tbl.horizontalHeader().setStretchLastSection(True)

    def _populate_dop_table(self, dop: dict):
        """DOP ve Kamu-Özel Dengesi Tablosunu oluşturur ve biçimlendirir."""
        headers = ["Parametre", "Alan (m²)", "Alan (ha)", "Oran (%)", "Açıklama / Yasal Durum"]
        p_m2 = dop["toplam_plan_alani_m2"]
        e_m2 = dop["dop_esas_alan_m2"]
        sinir_aciklama = "Plan Onama Sınırına Göre Kesin" if dop.get("sinir_katmani_kullanildi") else "İmar Adaları Toplamı Esas Alındı"

        rows = [
            ["Plan Onama Sınırı / Toplam Alan", f"{p_m2:,.0f} m²", f"{dop['toplam_plan_alani_ha']:.2f} ha", "100.0 %", sinir_aciklama],
            ["İmar Adaları (Kullanım Poligonları)", f"{dop['adalar_toplam_m2']:,.0f} m²", f"{dop['adalar_toplam_ha']:.2f} ha", f"{(dop['adalar_toplam_m2']/max(1, p_m2)*100.0):.2f} %", "Plan Fonksiyon Blokları"],
            ["Net Yol ve Ulaşım Ağı Alanı", f"{dop['hesaplanan_yol_m2']:,.0f} m²", f"{dop['hesaplanan_yol_ha']:.2f} ha", f"% {dop['yol_orani_yuzde']:.2f}", "Plan Sınırı - İmar Adaları Boşluğu"],
            ["Kişi Başına Düşen Yol Standardı", "-", "-", f"{dop['kisi_basi_yol_m2']:.2f} m²/k", "Üst Plan Nüfusuna Göre Yol Standardı"],
            ["DOP Dışı Alanlar (Harice Ayrılan)", f"{dop['dop_disi_alan_m2']:,.0f} m²", f"{(dop['dop_disi_alan_m2']/10000.0):.2f} ha", f"{(dop['dop_disi_alan_m2']/max(1, p_m2)*100.0):.2f} %", "Orman, Tarım, Su vb."],
            ["Düzenleme Sahası (DOP Esas Alan)", f"{e_m2:,.0f} m²", f"{(e_m2/10000.0):.2f} ha", f"{(e_m2/max(1, p_m2)*100.0):.2f} %", "Düzenlemeye Giren Net Saha"],
            ["Toplam Özel Mülkiyet (Tahsis)", f"{dop['toplam_ozel_tahsis_m2']:,.0f} m²", f"{(dop['toplam_ozel_tahsis_m2']/10000.0):.2f} ha", f"{(dop['toplam_ozel_tahsis_m2']/max(1, e_m2)*100.0):.2f} %", "Konut, Ticaret, Sanayi vb."],
            ["Kamu Poligon Donatıları", f"{dop['kamu_poligonlar_m2']:,.0f} m²", f"{(dop['kamu_poligonlar_m2']/10000.0):.2f} ha", f"{(dop['kamu_poligonlar_m2']/max(1, e_m2)*100.0):.2f} %", "Eğitim, Sağlık, Yeşil vb."],
            ["Toplam Kamu Kesintisi (DOP)", f"{dop['toplam_kamu_kesinti_m2']:,.0f} m²", f"{(dop['toplam_kamu_kesinti_m2']/10000.0):.2f} ha", f"% {dop['dop_orani']:.2f}", "Donatılar + Gerçek Yol Ağı"],
            ["Kamu / Özel Mülkiyet Oranı", "-", "-", f"% {dop['kamu_ozel_orani']:.2f}", "Kamu Kesintisi / Özel Tahsis Oranı"],
            ["HESAPLANAN DOP ORANI (%)", "-", "-", f"% {dop['dop_orani']:.2f}", dop['dop_uygunluk']]
        ]
        if dop.get("ortalama_yol_genisligi_m"):
            rows.insert(4, ["Ortalama Fiili Yol Genişliği", "-", f"{dop['yol_agi_uzunlugu_km']:.2f} km Yol", f"{dop['ortalama_yol_genisligi_m']:.2f} m", "Yol Alanı / Hat Uzunluğu"])

        self._populate_table(self.tbl_dop, headers, rows)
        bold_font = QFont()
        bold_font.setBold(True)
        color = QColor("#16a34a") if dop["dop_orani"] <= 45.0 else QColor("#dc2626")
        last_idx = len(rows) - 1
        for col in range(5):
            it = self.tbl_dop.item(last_idx, col)
            if it:
                it.setFont(bold_font)
                it.setForeground(color)

    def _populate_kk_table(self, kk_list: list):
        """Kent Karakteri Tablosunu oluşturur."""
        headers = ["Plan Fonksiyonu", "Toplam Alan (m²)", "Alt Nüfus (m²/k)", "Üst Nüfus (m²/k)", "Projeksiyon (m²/k)"]
        rows = []
        for it in kk_list:
            rows.append([
                it["fonksiyon"],
                f"{it['toplam_m2']:,.0f} m²",
                f"{it['alt_nufus_m2_kisi']:.2f} m²/k",
                f"{it['ust_nufus_m2_kisi']:.2f} m²/k",
                f"{it['proj_nufus_m2_kisi']:.2f} m²/k"
            ])
        self._populate_table(self.tbl_kent_karakter, headers, rows)

    def _populate_ek2_table(self, ek2_list: list):
        """MPYY Ek-2 Donatı Dengesi Tablosunu oluşturur."""
        headers = ["Donatı Grubu", "Mevcut Alan", "Ek-2 Std", "Mevcut (Üst Nüfus)", "Durum"]
        rows = []
        for ek in ek2_list:
            rows.append([
                ek["kategori_adi"],
                f"{ek['toplam_m2']:,.0f} m²",
                f"{ek['standart_m2']:.2f} m²/k",
                f"{ek['kb_ust']:.2f} m²/k",
                ek["durum_ust"]
            ])
        self._populate_table(self.tbl_ek2, headers, rows)
        font = QFont()
        font.setBold(True)
        for r_idx, ek in enumerate(ek2_list):
            it = self.tbl_ek2.item(r_idx, 4)
            if it:
                it.setForeground(QColor("#16a34a") if ek["durum_ust"] == "YETERLİ" else QColor("#dc2626"))
                it.setFont(font)

    def _populate_fd_table(self, fd_list: list):
        """Detaylı Fonksiyon Dağılım Tablosunu oluşturur."""
        headers = ["Plan Fonksiyonu", "DOP Durumu", "Alan Türü", "Adet", "Alan (ha)", "Kişi Başı (m²)", "Plan Payı (%)"]
        rows = []
        for fd in fd_list:
            rows.append([
                fd["fonksiyon"],
                fd["dop_durumu"],
                fd["dop_turu"],
                str(fd["adet"]),
                f"{fd['alan_ha']:.2f} ha",
                f"{fd['kisi_basi_m2']:.2f} m²/k",
                f"% {fd['tum_plan_yuzdesi']:.2f}"
            ])
        self._populate_table(self.tbl_fonk_dagilim, headers, rows)

    def _run_nip_analysis(self):
        layer = self.cmb_nip_layer.currentLayer()
        fonk_col = self.cmb_fonk_field.currentText()
        proj_nufus = self.spn_proj_nufus.value()

        sec_col_text = self.cmb_secondary_fonk_field.currentText() if hasattr(self, 'cmb_secondary_fonk_field') else ""
        secondary_fonk_col = sec_col_text if sec_col_text and not sec_col_text.startswith("<") else None

        mode_idx = self.cmb_analysis_mode.currentIndex() if hasattr(self, 'cmb_analysis_mode') else 0
        analysis_mode = "TUCBS" if mode_idx == 1 else "NIP"
        mode_title = "Fiziki Mevcut Durum (TUCBS)" if analysis_mode == "TUCBS" else "1/5000 NİP"

        if not layer or not isinstance(layer, QgsVectorLayer):
            QMessageBox.warning(self, "Uyarı", "Lütfen bir analiz katmanı seçin!")
            return
        if not fonk_col:
            QMessageBox.warning(self, "Uyarı", "Lütfen birincil fonksiyon veya TUCBS sütununu seçin!")
            return

        self.btn_run_nip.setEnabled(False)
        self.txt_nip_results.clear()
        self.txt_nip_results.append(f"<i>{mode_title} Analizi hesaplanıyor, lütfen bekleyiniz...</i>")

        try:
            da = QgsDistanceArea()
            da.setSourceCrs(layer.sourceCrs(), QgsProject.instance().transformContext())
            da.setEllipsoid(QgsProject.instance().ellipsoid() or 'WGS84')

            # 1. Plan Onama Sınırı Geometrisi
            sinir_layer = self.cmb_sinir_layer.currentLayer()
            sinir_geom = None
            if sinir_layer and isinstance(sinir_layer, QgsVectorLayer):
                geoms = [f.geometry() for f in sinir_layer.getFeatures() if f.geometry() and not f.geometry().isEmpty()]
                if geoms:
                    sinir_geom = QgsGeometry.unaryUnion(geoms)

            # 2. Yol Aksları Uzunluğu
            yol_layer = self.cmb_yol_layer.currentLayer()
            yol_uzunlugu_m = 0.0
            if yol_layer and isinstance(yol_layer, QgsVectorLayer):
                for yf in yol_layer.getFeatures():
                    yg = yf.geometry()
                    if yg and not yg.isEmpty():
                        yol_uzunlugu_m += da.measureLength(yg)

            # 3. Özel İstihdam ve Yolculuk Kuralları
            rules_config = self._get_rules_config()

            # Otomatik duplike kontrolü ve geometri temizliği
            cleaned_feats, clean_stats = GeometryCleanerEngine.clean_layer(layer)
            if clean_stats["duplike_elenen"] > 0:
                feats = cleaned_feats
                self.txt_nip_results.append(
                    f"<p style='color:#b45309;'>ℹ️ <i>Katmanda tespit edilen <b>{clean_stats['duplike_elenen']:,} adet mükerrer poligon</b> otomatik olarak ayıklandı; hesaplama <b>{clean_stats['temiz_cikan']:,} tekil ada</b> üzerinden yapıldı.</i></p>"
                )
            else:
                feats = cleaned_feats

            parsed_items, summary = NipCalculatorEngine.calculate(
                feats, layer.fields(), fonk_col, proj_nufus, da,
                sinir_geom=sinir_geom,
                yol_uzunlugu_m=yol_uzunlugu_m,
                rules_config=rules_config,
                secondary_fonk_col=secondary_fonk_col,
                analysis_mode=analysis_mode
            )

            # 4. Ana Poligon Analiz Katmanı
            uri = f"MultiPolygon?crs={layer.crs().authid()}"
            out_layer = QgsVectorLayer(uri, f"{layer.name()}_{analysis_mode}_ANALIZ", "memory")
            out_prov = out_layer.dataProvider()

            out_fields = QgsFields(layer.fields())
            out_fields.append(QgsField('AlanHa', QVariant.Double))
            out_fields.append(QgsField('ALT_SNR', QVariant.Double))
            out_fields.append(QgsField('UST_SNR', QVariant.Double))
            out_fields.append(QgsField('ALT_NUFUS', QVariant.Double))
            out_fields.append(QgsField('UST_NUFUS', QVariant.Double))
            out_fields.append(QgsField('k_m2_ALT_NUFUS', QVariant.Double))
            out_fields.append(QgsField('k_m2_UST_NUFUS', QVariant.Double))
            out_fields.append(QgsField('T_ISTIHDAM', QVariant.Int))
            out_fields.append(QgsField('GUNLUK_ARAC', QVariant.Double))
            out_fields.append(QgsField('GUNLUK_YAYA', QVariant.Double))
            out_fields.append(QgsField('DOP_DURUMU', QVariant.String))
            out_fields.append(QgsField('DOP_TURU', QVariant.String))
            out_fields.append(QgsField('DONATI_KATEGORI', QVariant.String))

            out_prov.addAttributes(out_fields)
            out_layer.updateFields()

            new_feats = []
            for it in parsed_items:
                feat = it["feat"]
                nf = QgsFeature(out_fields)
                nf.setGeometry(it["geom"])
                attrs = feat.attributes()
                attrs.extend([
                    round(it["alan_ha"], 4),
                    it["alt_snr"] if it["alt_snr"] is not None else 0.0,
                    it["ust_snr"] if it["ust_snr"] is not None else 0.0,
                    it["alt_nufus"],
                    it["ust_nufus"],
                    it["km2_alt_nufus"] if it["km2_alt_nufus"] is not None else QVariant(),
                    it["km2_ust_nufus"] if it["km2_ust_nufus"] is not None else QVariant(),
                    it["istihdam"],
                    it["gunluk_arac"],
                    it["gunluk_yaya"],
                    it["dop_durumu"],
                    it["dop_turu"],
                    it["donati_kategori"] or ""
                ])
                nf.setAttributes(attrs)
                new_feats.append(nf)

            out_prov.addFeatures(new_feats)
            out_layer.updateExtents()
            self._apply_nip_styling(out_layer)

            # 5. DOP ve Kamu-Özel Dengesi Tablosu Katmanı (NoGeometry)
            tbl_dop_layer = QgsVectorLayer("None", f"PLN3113_{analysis_mode}_2_DOP_ve_Kamu_Ozel_Dengesi", "memory")
            tbl_dop_pr = tbl_dop_layer.dataProvider()
            tbl_dop_fields = [
                QgsField('parametre', QVariant.String),
                QgsField('alan_m2', QVariant.Double),
                QgsField('alan_ha', QVariant.Double),
                QgsField('oran_yuzde', QVariant.Double),
                QgsField('aciklama', QVariant.String)
            ]
            tbl_dop_pr.addAttributes(tbl_dop_fields)
            tbl_dop_layer.updateFields()

            dop = summary["dop_ozet"]
            p_m2 = dop["toplam_plan_alani_m2"]
            e_m2 = dop["dop_esas_alan_m2"]
            sinir_aciklama = "Plan Onama Sınırına Göre Kesin" if dop.get("sinir_katmani_kullanildi") else "İmar Adaları Toplamı Esas Alındı"

            dop_raw_rows = [
                ("Plan Onama Sınırı / Toplam Alan", p_m2, dop["toplam_plan_alani_ha"], 100.0, sinir_aciklama),
                ("İmar Adaları (Kullanım Poligonları)", dop["adalar_toplam_m2"], dop["adalar_toplam_ha"], round(dop["adalar_toplam_m2"]/max(1, p_m2)*100.0, 2), "Plan Fonksiyon Blokları"),
                ("Net Yol ve Ulaşım Ağı Alanı", dop["hesaplanan_yol_m2"], dop["hesaplanan_yol_ha"], dop["yol_orani_yuzde"], "Plan Sınırı - İmar Adaları Boşluğu"),
                ("DOP Dışı Alanlar (Harice Ayrılan)", dop["dop_disi_alan_m2"], round(dop["dop_disi_alan_m2"]/10000.0, 2), round(dop["dop_disi_alan_m2"]/max(1, p_m2)*100.0, 2), "Orman, Tarım, Su, Sit vb."),
                ("Düzenleme Sahası (DOP Esas Alan)", e_m2, round(e_m2/10000.0, 2), round(e_m2/max(1, p_m2)*100.0, 2), "Düzenlemeye Giren Net Saha"),
                ("Toplam Özel Mülkiyet (Tahsis)", dop["toplam_ozel_tahsis_m2"], round(dop["toplam_ozel_tahsis_m2"]/10000.0, 2), round(dop["toplam_ozel_tahsis_m2"]/max(1, e_m2)*100.0, 2), "Konut, Ticaret, Sanayi vb."),
                ("Kamu Poligon Donatıları", dop["kamu_poligonlar_m2"], round(dop["kamu_poligonlar_m2"]/10000.0, 2), round(dop["kamu_poligonlar_m2"]/max(1, e_m2)*100.0, 2), "Eğitim, Sağlık, Yeşil vb."),
                ("Toplam Kamu Kesintisi (DOP)", dop["toplam_kamu_kesinti_m2"], round(dop["toplam_kamu_kesinti_m2"]/10000.0, 2), dop["dop_orani"], "Donatılar + Gerçek Yol Ağı"),
                ("Kamu / Özel Mülkiyet Oranı", 0.0, 0.0, dop["kamu_ozel_orani"], "Kamu Kesintisi / Özel Tahsis Oranı"),
                ("HESAPLANAN DOP ORANI (%)", 0.0, 0.0, dop["dop_orani"], dop["dop_uygunluk"])
            ]
            if dop.get("ortalama_yol_genisligi_m"):
                dop_raw_rows.insert(3, ("Ortalama Fiili Yol Genişliği (m)", 0.0, 0.0, dop["ortalama_yol_genisligi_m"], f"{dop['yol_agi_uzunlugu_km']} km Yol Ağı / Yol Alanı"))

            dop_feats = []
            for r in dop_raw_rows:
                df = QgsFeature(tbl_dop_layer.fields())
                df.setAttributes(list(r))
                dop_feats.append(df)
            tbl_dop_pr.addFeatures(dop_feats)

            # 6. Kent Karakteri Tablosu Katmanı (NoGeometry)
            tbl_kk_layer = QgsVectorLayer("None", f"PLN3113_{analysis_mode}_3_Kent_Karakter_Tablosu", "memory")
            tbl_kk_pr = tbl_kk_layer.dataProvider()
            tbl_kk_fields = [
                QgsField('nip_fonksiyon', QVariant.String),
                QgsField('toplam_m2', QVariant.Double),
                QgsField('alt_nufus_m2_kisi', QVariant.Double),
                QgsField('ust_nufus_m2_kisi', QVariant.Double),
                QgsField('proj_nufus_m2_kisi', QVariant.Double)
            ]
            tbl_kk_pr.addAttributes(tbl_kk_fields)
            tbl_kk_layer.updateFields()
            kk_feats = []
            for kk in summary["kent_karakter"]:
                kf = QgsFeature(tbl_kk_layer.fields())
                kf.setAttributes([kk["fonksiyon"], kk["toplam_m2"], kk["alt_nufus_m2_kisi"], kk["ust_nufus_m2_kisi"], kk["proj_nufus_m2_kisi"]])
                kk_feats.append(kf)
            tbl_kk_pr.addFeatures(kk_feats)

            # 7. MPYY Ek-2 Donatı Tablosu Katmanı (NoGeometry)
            tbl_ek2_layer = QgsVectorLayer("None", f"PLN3113_{analysis_mode}_4_Ek2_Donati_Dengesi", "memory")
            tbl_ek2_pr = tbl_ek2_layer.dataProvider()
            tbl_ek2_fields = [
                QgsField('donati_turu', QVariant.String),
                QgsField('toplam_m2', QVariant.Double),
                QgsField('mpyy_standart_m2', QVariant.Double),
                QgsField('mevcut_m2_alt_nufus', QVariant.Double),
                QgsField('mevcut_m2_ust_nufus', QVariant.Double),
                QgsField('durum_ust_nufus', QVariant.String)
            ]
            tbl_ek2_pr.addAttributes(tbl_ek2_fields)
            tbl_ek2_layer.updateFields()
            ek2_feats = []
            for ek in summary["ek2_rapor"]:
                ef = QgsFeature(tbl_ek2_layer.fields())
                ef.setAttributes([ek["kategori_adi"], ek["toplam_m2"], ek["standart_m2"], ek["kb_alt"], ek["kb_ust"], ek["durum_ust"]])
                ek2_feats.append(ef)
            tbl_ek2_pr.addFeatures(ek2_feats)

            # 8. Detaylı Fonksiyon Dağılım Tablosu Katmanı (NoGeometry)
            tbl_fd_layer = QgsVectorLayer("None", f"PLN3113_{analysis_mode}_5_Fonksiyon_Dagilim_Tablosu", "memory")
            tbl_fd_pr = tbl_fd_layer.dataProvider()
            tbl_fd_fields = [
                QgsField('nip_fonksiyon', QVariant.String),
                QgsField('dop_durumu', QVariant.String),
                QgsField('alan_turu', QVariant.String),
                QgsField('adet', QVariant.Int),
                QgsField('alan_m2', QVariant.Double),
                QgsField('alan_ha', QVariant.Double),
                QgsField('kisi_basi_m2', QVariant.Double),
                QgsField('tum_plan_yuzdesi', QVariant.Double),
                QgsField('dop_ici_yuzde', QVariant.Double)
            ]
            tbl_fd_pr.addAttributes(tbl_fd_fields)
            tbl_fd_layer.updateFields()
            fd_feats = []
            for fd in summary["fonksiyon_dagilim"]:
                ff = QgsFeature(tbl_fd_layer.fields())
                ff.setAttributes([
                    fd["fonksiyon"], fd["dop_durumu"], fd["dop_turu"], fd["adet"],
                    fd["alan_m2"], fd["alan_ha"], fd["kisi_basi_m2"], fd["tum_plan_yuzdesi"], fd["dop_ici_yuzde"]
                ])
                fd_feats.append(ff)
            tbl_fd_pr.addFeatures(fd_feats)

            # Katmanları QGIS Projesinde Düzenli Bir Gruba Ekle
            root = QgsProject.instance().layerTreeRoot()
            grp_name = f"PLN3113 {mode_title} Analiz Çıktıları ({layer.name()})"
            grp = root.findGroup(grp_name)
            if not grp:
                grp = root.insertGroup(0, grp_name)

            for lyr in [out_layer, tbl_dop_layer, tbl_kk_layer, tbl_ek2_layer, tbl_fd_layer]:
                QgsProject.instance().addMapLayer(lyr, False)
                grp.addLayer(lyr)

            # DockWidget Tablolarını Doldur
            self._populate_dop_table(summary["dop_ozet"])
            self._populate_kk_table(summary["kent_karakter"])
            self._populate_ek2_table(summary["ek2_rapor"])
            self._populate_fd_table(summary["fonksiyon_dagilim"])

            # Gösterge Tablosunu Güncelle (Son Satır)
            alt_str = f"{summary['toplam_alt_nufus']:,}".replace(",", ".")
            ust_str = f"{summary['toplam_ust_nufus']:,}".replace(",", ".")
            kirsal_sabit = 25833
            ilce_alt_str = f"{(summary['toplam_alt_nufus'] + kirsal_sabit):,}".replace(",", ".")
            ilce_ust_str = f"{(summary['toplam_ust_nufus'] + kirsal_sabit):,}".replace(",", ".")

            self.tbl_benchmark.setItem(4, 0, QTableWidgetItem(f"Hesaplanan {mode_title} Kapasitesi"))
            self.tbl_benchmark.setItem(4, 1, QTableWidgetItem(f"{alt_str} - {ust_str}"))
            self.tbl_benchmark.setItem(4, 2, QTableWidgetItem(f"~{kirsal_sabit:,}".replace(",", ".")))
            self.tbl_benchmark.setItem(4, 3, QTableWidgetItem(f"{ilce_alt_str} - {ilce_ust_str}"))

            font = QFont()
            font.setBold(True)
            for c in range(4):
                item = self.tbl_benchmark.item(4, c)
                if item:
                    item.setFont(font)
                    item.setForeground(QColor("#0f766e"))

            # HTML Rapor Hazırla
            dop_durum_color = "#16a34a" if dop["dop_orani"] <= 45.0 else "#dc2626"
            yol_genislik_tr = f"<tr><td><b>Ortalama Fiili Yol Genişliği</b></td><td colspan='2'><b>{dop['ortalama_yol_genisligi_m']} m</b> ({dop['yol_agi_uzunlugu_km']} km Yol Ağı)</td></tr>" if dop.get("ortalama_yol_genisligi_m") else ""

            report_html = f"""
            <h3>🏙️ TİRE {mode_title.upper()} ANALİZ VE KAPASİTE RAPORU</h3>
            
            <h4>0. 👥 Demografik Göstergeler ve Tarihsel Kıyaslama</h4>
            <table border="1" cellpadding="4" style="border-collapse:collapse; width:100%; margin-bottom:12px;">
                <tr style="background:#0f766e; color:white;">
                    <th>Nüfus Niteliği / Kapsam</th><th>Kentsel Merkez</th><th>Kırsal Nüfus</th><th>İlçe Toplamı</th>
                </tr>
                <tr><td><b>1997 Plan Raporu (1990 DİE)</b></td><td>37.855</td><td>39.459 (65 Köy)</td><td>77.314</td></tr>
                <tr><td><b>2015 Plan Projeksiyonu (Hedef)</b></td><td>53.629</td><td>46.711 (Model)</td><td>100.340</td></tr>
                <tr><td><b>2015 TÜİK ADNKS (Gerçekleşen)</b></td><td>~57.069 (Merkez Mahalleler)</td><td>~25.033</td><td>82.102</td></tr>
                <tr><td><b>Güncel TÜİK ADNKS (2025/2026)</b></td><td>~61.738 (Merkez Mahalleler)</td><td>~25.833</td><td>87.571</td></tr>
                <tr style="background:#ecfdf5; font-weight:bold; color:#0f766e;">
                    <td><b>Hesaplanan {mode_title} Kapasitesi</b></td><td>{alt_str} - {ust_str}</td><td>~25.833 (Kırsal Sabit)</td><td>{ilce_alt_str} - {ilce_ust_str}</td>
                </tr>
            </table>
            <div style="font-size:11px; color:#475569; margin-bottom:14px; background:#f1f5f9; padding:8px; border-left:3px solid #0f766e; border-radius:3px;">
                <b>Metodolojik Açıklamalar ve Veri Kısıtları:</b><br>
                • <b>1997 Plan Raporu (1990 DİE Sayımı):</b> Raporda kırsal nüfus 65 köyün tek tek dökümüyle (39.459 kişi) verilmiş; kentsel merkez nüfusu 37.855 kişi aktarılmıştır.<br>
                • <b>2015 Plan Projeksiyonu:</b> Üst Değerli Model (Regresyon) projeksiyonuna göre kentsel nüfus 53.629, toplam ilçe 100.340 kişidir. Kırsal nüfus farktan türetilmiştir (46.711).<br>
                • <b>6360 Sayılı Kanun Etkisi:</b> 2012'de kabul edilen yasa uyarınca İzmir genelinde tüm köyler ve beldeler mahalleye dönüştüğünden resmi ADNKS bültenlerinde idari kır/kent ayrımı bulunmamaktadır.<br>
                • <b>Merkez / Kırsal Ayrıştırması:</b> Kentsel merkez, kentsel makroform ve yerleşik leke içindeki mahalleler toplamıdır; kırsal nüfus ilçe toplamından bu değer düşülerek elde edilmiştir.<br>
                • <b>Güncel TÜİK Verisi:</b> En güncel resmi sayım 31 Aralık 2025 referanslı (Şubat 2026'da ilan edilen) ADNKS kütüğüdür (87.571 kişi).<br>
                • <b>Planlama Uyumu:</b> Hesaplanan kentsel üst sınır nüfusu ({ust_str} kişi), 1997 planının 2015 hedefi (53.629 kişi) ile %99.6 oranında birebir örtüşmektedir.
            </div>

            <h4>1. Genel Nüfus, Alan ve Ulaşım Göstergeleri</h4>
            <table border="1" cellpadding="4" style="border-collapse:collapse; width:100%;">
                <tr style="background:#0f766e; color:white;">
                    <th>Metrik</th><th>Alt Sınır (Kişi/Birim)</th><th>Üst Sınır (Kişi/Birim)</th>
                </tr>
                <tr><td><b>Toplam Plan Nüfusu</b></td><td style="color:#0f766e; font-weight:bold;">{alt_str} Kişi</td><td style="color:#0f766e; font-weight:bold;">{ust_str} Kişi</td></tr>
                <tr><td><b>Toplam Konut & Karma Alanı</b></td><td colspan="2">{summary['toplam_konut_alani_ha']:.2f} Hektar</td></tr>
                <tr><td><b>Toplam İmar Adaları Alanı</b></td><td colspan="2">{dop['adalar_toplam_ha']:.2f} Hektar ({dop['adalar_toplam_m2']:,.0f} m²)</td></tr>
                <tr><td><b>Net Yol ve Ulaşım Alanı</b></td><td colspan="2"><b>{dop['hesaplanan_yol_ha']:.2f} Hektar</b> (% {dop['yol_orani_yuzde']:.2f} - {dop['kisi_basi_yol_m2']:.2f} m²/kişi)</td></tr>
                {yol_genislik_tr}
                <tr><td><b>Toplam Plan Alanı ({sinir_aciklama})</b></td><td colspan="2"><b>{dop['toplam_plan_alani_ha']:.2f} Hektar</b> ({p_m2:,.0f} m²)</td></tr>
                <tr><td><b>Tahmini İstihdam Kapasitesi</b></td><td colspan="2"><b>{summary['toplam_istihdam']:,}</b> Çalışan</td></tr>
                <tr><td><b>Günlük Araç Yolculuk Yükü</b></td><td colspan="2"><b>{summary['toplam_gunluk_arac']:,}</b> Araç (PAU)</td></tr>
                <tr><td><b>Günlük Yaya Yolculuk Yükü</b></td><td colspan="2"><b>{summary['toplam_gunluk_yaya']:,}</b> Yaya</td></tr>
            </table>

            <h4>2. ⚖️ Kamu - Özel Mülkiyet Dengesi ve DOP Hesabı</h4>
            <table border="1" cellpadding="4" style="border-collapse:collapse; width:100%;">
                <tr style="background:#0f766e; color:white;">
                    <th>Parametre</th><th>Alan (m²)</th><th>Alan (ha)</th><th>Oran (%)</th><th>Açıklama</th>
                </tr>
                <tr><td><b>Plan Onama Sınırı / Toplam Alan</b></td><td>{p_m2:,.0f} m²</td><td>{dop['toplam_plan_alani_ha']:.2f} ha</td><td>100.0 %</td><td>{sinir_aciklama}</td></tr>
                <tr><td><b>İmar Adaları (Kullanım Poligonları)</b></td><td>{dop['adalar_toplam_m2']:,.0f} m²</td><td>{dop['adalar_toplam_ha']:.2f} ha</td><td>{(dop['adalar_toplam_m2']/max(1, p_m2)*100.0):.2f} %</td><td>Plan Fonksiyon Blokları</td></tr>
                <tr><td><b>Net Yol ve Ulaşım Alanı</b></td><td>{dop['hesaplanan_yol_m2']:,.0f} m²</td><td>{dop['hesaplanan_yol_ha']:.2f} ha</td><td>% {dop['yol_orani_yuzde']:.2f}</td><td>Plan Sınırı - İmar Adaları Farkı</td></tr>
                <tr><td><b>DOP Dışı Alanlar</b></td><td>{dop['dop_disi_alan_m2']:,.0f} m²</td><td>{(dop['dop_disi_alan_m2']/10000.0):.2f} ha</td><td>{(dop['dop_disi_alan_m2']/max(1, p_m2)*100.0):.2f} %</td><td>Orman, Tarım, Su vb.</td></tr>
                <tr><td><b>Düzenleme Sahası (DOP Esas)</b></td><td>{e_m2:,.0f} m²</td><td>{(e_m2/10000.0):.2f} ha</td><td>{(e_m2/max(1, p_m2)*100.0):.2f} %</td><td>Düzenlemeye Giren Net Saha</td></tr>
                <tr><td><b>Toplam Özel Mülkiyet (Tahsis)</b></td><td>{dop['toplam_ozel_tahsis_m2']:,.0f} m²</td><td>{(dop['toplam_ozel_tahsis_m2']/10000.0):.2f} ha</td><td>{(dop['toplam_ozel_tahsis_m2']/max(1, e_m2)*100.0):.2f} %</td><td>Konut, Ticaret vb.</td></tr>
                <tr><td><b>Toplam Kamu Kesintisi (DOP)</b></td><td>{dop['toplam_kamu_kesinti_m2']:,.0f} m²</td><td>{(dop['toplam_kamu_kesinti_m2']/10000.0):.2f} ha</td><td>% {dop['dop_orani']:.2f}</td><td>Donatılar + Gerçek Yol Ağı</td></tr>
                <tr><td><b>Kamu Poligon Donatıları</b></td><td>{dop['kamu_poligonlar_m2']:,.0f} m²</td><td>{(dop['kamu_poligonlar_m2']/10000.0):.2f} ha</td><td>{(dop['kamu_poligonlar_m2']/max(1, e_m2)*100.0):.2f} %</td><td>Eğitim, Sağlık, Yeşil vb.</td></tr>
                <tr style="background:#fef08a;">
                    <td><b>HESAPLANAN DOP ORANI (%)</b></td><td>-</td><td>-</td>
                    <td style="color:{dop_durum_color}; font-weight:bold; font-size:14px;">% {dop['dop_orani']:.2f}</td>
                    <td style="color:{dop_durum_color}; font-weight:bold;">{dop['dop_uygunluk']}</td>
                </tr>
            </table>

            <h4>3. 📋 MPYY Ek-2 Donatı Yeterlilik Dengesi:</h4>
            <table border="1" cellpadding="3" style="border-collapse:collapse; width:100%;">
                <tr style="background:#e2e8f0; font-size:11px;">
                    <th>Donatı Grubu</th><th>Mevcut Alan</th><th>Ek-2 Std</th><th>Mevcut (Üst Nüfus)</th><th>Durum</th>
                </tr>
            """
            for ek in summary["ek2_rapor"]:
                durum_color = "#16a34a" if ek["durum_ust"] == "YETERLİ" else "#dc2626"
                report_html += f"""
                <tr>
                    <td>{ek['kategori_adi']}</td>
                    <td>{ek['toplam_m2']:,.0f} m²</td>
                    <td>{ek['standart_m2']} m²/k</td>
                    <td>{ek['kb_ust']:.2f} m²/k</td>
                    <td style="color:{durum_color}; font-weight:bold;">{ek['durum_ust']}</td>
                </tr>
                """
            report_html += "</table>"

            self.txt_nip_results.setHtml(report_html)

            # Durumu Sakla ve Dışa Aktarmayı Etkinleştir
            self._last_nip_summary = summary
            self._last_nip_html = report_html
            self.btn_export_csv.setEnabled(True)
            self.btn_export_html.setEnabled(True)

            QMessageBox.information(
                self, f"{mode_title} Analizi Tamamlandı",
                f"Hesaplanan {mode_title} Nüfusu:\nAlt Sınır: {alt_str} Kişi\nÜst Sınır: {ust_str} Kişi\n\n"
                f"Hesaplanan DOP Oranı: %{dop['dop_orani']:.2f} ({dop['dop_uygunluk']})\n"
                f"Net Yol Ağı Alanı: {dop['hesaplanan_yol_ha']:.2f} ha (%{dop['yol_orani_yuzde']:.2f})\n\n"
                f"Analiz katmanı ve 4 adet detaylı tablo (DOP, Kent Karakteri, Ek-2 ve Fonksiyon Dağılımı) "
                f"harita projenize 'PLN3113 {mode_title} Analiz Çıktıları' grubu altında eklendi."
            )

        except Exception as e:
            QMessageBox.critical(self, "Hata", f"NİP Analizi sırasında hata: {str(e)}")
            self.txt_nip_results.append(f"<span style='color:red;'>Hata: {str(e)}</span>")
        finally:
            self.btn_run_nip.setEnabled(True)

    def _export_nip_tables_csv(self):
        """Tüm hesaplanan analiz tablolarını UTF-8-BOM formatında CSV olarak dışa aktarır."""
        if not self._last_nip_summary:
            QMessageBox.warning(self, "Uyarı", "Lütfen önce NİP analizini çalıştırın!")
            return

        folder = QFileDialog.getExistingDirectory(self, "Tabloların Kaydedileceği Klasörü Seçin")
        if not folder:
            return

        summary = self._last_nip_summary
        dop = summary["dop_ozet"]
        p_m2 = dop["toplam_plan_alani_m2"]
        e_m2 = dop["dop_esas_alan_m2"]
        sinir_aciklama = "Plan Onama Sınırına Göre Kesin" if dop.get("sinir_katmani_kullanildi") else "İmar Adaları Toplamı Esas Alındı"

        try:
            # 1. DOP CSV
            dop_csv = os.path.join(folder, "pln3113_nip_dop_kamu_ozel_dengesi.csv")
            with open(dop_csv, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f, delimiter=";")
                w.writerow(["Parametre", "Alan (m²)", "Alan (ha)", "Oran (%)", "Açıklama / Değerlendirme"])
                dop_rows = [
                    ["Plan Onama Sınırı / Toplam Alan", dop["toplam_plan_alani_m2"], dop["toplam_plan_alani_ha"], 100.0, sinir_aciklama],
                    ["İmar Adaları (Kullanım Poligonları)", dop["adalar_toplam_m2"], dop["adalar_toplam_ha"], round(dop["adalar_toplam_m2"]/max(1, p_m2)*100.0, 2), "Plan Fonksiyon Blokları"],
                    ["Net Yol ve Ulaşım Ağı Alanı", dop["hesaplanan_yol_m2"], dop["hesaplanan_yol_ha"], dop["yol_orani_yuzde"], "Plan Sınırı - İmar Adaları Boşluğu"],
                    ["Kişi Başına Düşen Yol Standardı", "-", "-", f"{dop['kisi_basi_yol_m2']:.2f} m²/k", "Üst Nüfusa Göre Yol Alanı"],
                    ["DOP Dışı Alanlar", dop["dop_disi_alan_m2"], round(dop["dop_disi_alan_m2"]/10000.0, 2), round(dop["dop_disi_alan_m2"]/max(1, p_m2)*100.0, 2), "Orman, Tarım, Su, Sit vb."],
                    ["Düzenleme Sahası (DOP Esas Alan)", dop["dop_esas_alan_m2"], round(dop["dop_esas_alan_m2"]/10000.0, 2), round(dop["dop_esas_alan_m2"]/max(1, p_m2)*100.0, 2), "Düzenlemeye Giren Net Saha"],
                    ["Toplam Özel Mülkiyet (Tahsis)", dop["toplam_ozel_tahsis_m2"], round(dop["toplam_ozel_tahsis_m2"]/10000.0, 2), round(dop["toplam_ozel_tahsis_m2"]/max(1, e_m2)*100.0, 2), "Konut, Ticaret, Sanayi vb."],
                    ["Toplam Kamu Alanı (Kesinti + Yol)", dop["toplam_kamu_kesinti_m2"], round(dop["toplam_kamu_kesinti_m2"]/10000.0, 2), dop["dop_orani"], "Donatılar + Hesaplanan Yol Payı"],
                    ["Kamu Poligon Donatıları", dop["kamu_poligonlar_m2"], round(dop["kamu_poligonlar_m2"]/10000.0, 2), round(dop["kamu_poligonlar_m2"]/max(1, e_m2)*100.0, 2), "Eğitim, Sağlık, Yeşil vb."],
                    ["Kamu / Özel Mülkiyet Oranı", "-", "-", dop["kamu_ozel_orani"], "Kamu Kesintisi / Özel Tahsis Oranı"],
                    ["HESAPLANAN DOP ORANI (%)", "-", "-", dop["dop_orani"], dop["dop_uygunluk"]]
                ]
                if dop.get("ortalama_yol_genisligi_m"):
                    dop_rows.insert(4, ["Ortalama Fiili Yol Genişliği (m)", "-", f"{dop['yol_agi_uzunlugu_km']} km Yol", dop["ortalama_yol_genisligi_m"], "Yol Alanı / Hat Uzunluğu"])
                w.writerows(dop_rows)

            # 2. Kent Karakteri CSV
            kk_csv = os.path.join(folder, "pln3113_nip_kent_karakter_tablosu.csv")
            with open(kk_csv, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f, delimiter=";")
                w.writerow(["Plan Fonksiyonu", "Toplam Alan (m²)", "Alt Nüfus Kişi Başı (m²)", "Üst Nüfus Kişi Başı (m²)", "Projeksiyon Kişi Başı (m²)"])
                for kk in summary["kent_karakter"]:
                    w.writerow([kk["fonksiyon"], kk["toplam_m2"], kk["alt_nufus_m2_kisi"], kk["ust_nufus_m2_kisi"], kk["proj_nufus_m2_kisi"]])

            # 3. MPYY Ek-2 CSV
            ek2_csv = os.path.join(folder, "pln3113_nip_mpyy_ek2_donati_dengesi.csv")
            with open(ek2_csv, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f, delimiter=";")
                w.writerow(["Donatı Grubu", "Mevcut Alan (m²)", "Ek-2 Standart (m²/k)", "Mevcut Alt Nüfus (m²/k)", "Mevcut Üst Nüfus (m²/k)", "Durum (Üst Nüfus)"])
                for ek in summary["ek2_rapor"]:
                    w.writerow([ek["kategori_adi"], ek["toplam_m2"], ek["standart_m2"], ek["kb_alt"], ek["kb_ust"], ek["durum_ust"]])

            # 4. Fonksiyon Dağılımı CSV
            fd_csv = os.path.join(folder, "pln3113_nip_fonksiyon_dagilimi.csv")
            with open(fd_csv, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f, delimiter=";")
                w.writerow(["Fonksiyon", "DOP Durumu", "Alan Türü", "Poligon Adedi", "Alan (m²)", "Alan (ha)", "Kişi Başı (m²)", "Plan Payı (%)", "DOP İçi Payı (%)"])
                for fd in summary["fonksiyon_dagilim"]:
                    w.writerow([fd["fonksiyon"], fd["dop_durumu"], fd["dop_turu"], fd["adet"], fd["alan_m2"], fd["alan_ha"], fd["kisi_basi_m2"], fd["tum_plan_yuzdesi"], fd["dop_ici_yuzde"]])

            QMessageBox.information(
                self, "Başarılı",
                f"Tüm analiz tabloları CSV (Excel uyumlu UTF-8) formatında kaydedildi:\n\n{folder}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"CSV dışa aktarım hatası: {str(e)}")

    def _export_nip_report_html(self):
        """Oluşturulan HTML analiz raporunu dosyaya kaydeder."""
        if not self._last_nip_html:
            QMessageBox.warning(self, "Uyarı", "Lütfen önce NİP analizini çalıştırın!")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "HTML Raporunu Kaydet", "pln3113_nip_analiz_raporu.html", "HTML Dosyaları (*.html)"
        )
        if not file_path:
            return

        try:
            full_html = f"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<title>PLN3113 1/5000 NİP Kentsel Analiz Raporu</title>
<style>
body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 30px; color: #1e293b; background: #f8fafc; line-height: 1.5; }}
h3 {{ color: #0f766e; border-bottom: 2px solid #0f766e; padding-bottom: 6px; }}
h4 {{ color: #0d9488; margin-top: 24px; }}
table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; background: white; box-shadow: 0 1px 3px rgba(0,0,0,0.1); border-radius: 4px; overflow: hidden; }}
th, td {{ border: 1px solid #cbd5e1; padding: 8px 12px; text-align: left; font-size: 13px; }}
th {{ background: #0f766e; color: white; font-weight: 600; }}
tr:nth-child(even) {{ background: #f8fafc; }}
tr:hover {{ background: #f1f5f9; }}
</style>
</head>
<body>
{self._last_nip_html}
</body>
</html>"""
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(full_html)
            QMessageBox.information(self, "Başarılı", f"HTML Raporu kaydedildi:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"HTML raporu kaydedilirken hata: {str(e)}")

    def _apply_nip_styling(self, layer: QgsVectorLayer):
        """UST_SNR yoğunluk değerlerine göre katmana şık bir graduated semboloji atar."""
        ranges = [
            QgsRendererRange(0, 0, QgsFillSymbol.createSimple({'color': '#94a3b8', 'outline_color': '#64748b'}), "Donatı / Çalışma"),
            QgsRendererRange(1, 50, QgsFillSymbol.createSimple({'color': '#fef08a', 'outline_color': '#ca8a04'}), "Seyrek Konut (25-50 k/ha)"),
            QgsRendererRange(51, 150, QgsFillSymbol.createSimple({'color': '#fde047', 'outline_color': '#ca8a04'}), "Düşük Konut (51-150 k/ha)"),
            QgsRendererRange(151, 300, QgsFillSymbol.createSimple({'color': '#fb923c', 'outline_color': '#ea580c'}), "Orta Konut (151-300 k/ha)"),
            QgsRendererRange(301, 600, QgsFillSymbol.createSimple({'color': '#f87171', 'outline_color': '#dc2626'}), "Yüksek Konut (301-600 k/ha)"),
            QgsRendererRange(601, 1200, QgsFillSymbol.createSimple({'color': '#b91c1c', 'outline_color': '#7f1d1d'}), "Çok Yüksek (601-900 k/ha)")
        ]
        renderer = QgsGraduatedSymbolRenderer("UST_SNR", ranges)
        layer.setRenderer(renderer)
        layer.triggerRepaint()

    # -----------------------------------------------------------------
    # SEKME 3: SAHA & BİNA BAZLI FİİLİ NÜFUS
    # -----------------------------------------------------------------
    def _create_tab_field(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Bilgi Barı
        info_banner = QWidget()
        info_banner.setStyleSheet("background: #fefce8; border: 1px solid #fef08a; border-radius: 6px; padding: 4px;")
        info_l = QHBoxLayout(info_banner)
        info_l.setContentsMargins(6, 4, 6, 4)
        lbl_hint = QLabel("💡 <b>Mevcut Durum Fiili Nüfus Metodolojisi:</b> Bina kat, taban alanı, TÜİK hanehalkı ve fiili istihdam hesabı.")
        lbl_hint.setStyleSheet("color: #854d0e; font-size: 11px;")
        btn_hint_guide = QPushButton("📖 Rehberde İncele")
        btn_hint_guide.setCursor(Qt.PointingHandCursor)
        btn_hint_guide.setStyleSheet("background: #d97706; color: white; border-radius: 4px; padding: 3px 8px; font-size: 11px; font-weight: bold;")
        btn_hint_guide.clicked.connect(self._open_theoretical_guide)
        info_l.addWidget(lbl_hint)
        info_l.addStretch()
        info_l.addWidget(btn_hint_guide)
        layout.addWidget(info_banner)

        box_field = QGroupBox("Mevcut Durum Katmanları")
        f_layout = QFormLayout(box_field)

        self.cmb_ada_layer = QgsMapLayerComboBox()
        self.cmb_ada_layer.setFilters(QgsMapLayerProxyModel.PolygonLayer)
        f_layout.addRow("Kadastro / Saha Adaları:", self.cmb_ada_layer)

        self.cmb_bina_layer = QgsMapLayerComboBox()
        self.cmb_bina_layer.setFilters(QgsMapLayerProxyModel.PolygonLayer)
        f_layout.addRow("Bina Katmanı (tire_bina):", self.cmb_bina_layer)

        self.spn_hh = QDoubleSpinBox()
        self.spn_hh.setRange(1.0, 8.0)
        self.spn_hh.setValue(2.85)
        self.spn_hh.setSingleStep(0.05)
        f_layout.addRow("Ortalama Hanehalkı Büyüklüğü:", self.spn_hh)

        self.spn_daire_m2 = QDoubleSpinBox()
        self.spn_daire_m2.setRange(40.0, 300.0)
        self.spn_daire_m2.setValue(110.0)
        self.spn_daire_m2.setSuffix(" m²")
        f_layout.addRow("Ortalama Daire Alanı:", self.spn_daire_m2)

        self.spn_net_oran = QDoubleSpinBox()
        self.spn_net_oran.setRange(0.5, 1.0)
        self.spn_net_oran.setValue(0.85)
        self.spn_net_oran.setSingleStep(0.05)
        f_layout.addRow("İnşaat Net Alan Oranı:", self.spn_net_oran)

        layout.addWidget(box_field)

        lbl_kural = QLabel(
            "<b>Planlama İlkesi Koruması:</b><br>"
            "Sanayi, OSB, depo, mezarlık, saf ticaret ve park alanlarında yaşayan nüfus kesinlikle <b>0</b> atanır. "
            "Yalnızca Konut ve Karma Kullanım (TİCK) alanlarında yaşayan nüfus toplanır."
        )
        lbl_kural.setWordWrap(True)
        lbl_kural.setStyleSheet("color: #0369a1; font-size: 11px; background: #e0f2fe; padding: 8px; border-radius: 4px;")
        layout.addWidget(lbl_kural)

        self.btn_run_field = QPushButton("  Saha ve Bina Bazlı Fiili Nüfus ve Morfolojiyi Hesapla")
        self.btn_run_field.setObjectName("FieldButton")
        field_icon_path = os.path.join(PLUGIN_DIR, "icons", "field.png")
        if os.path.exists(field_icon_path):
            self.btn_run_field.setIcon(QIcon(field_icon_path))
        self.btn_run_field.clicked.connect(self._run_field_analysis)
        layout.addWidget(self.btn_run_field)

        self.field_progress = QProgressBar()
        self.field_progress.setVisible(False)
        layout.addWidget(self.field_progress)

        # 1-Tıkla Tematik Harita ve Morfoloji Görselleştirme Kutusu
        self.box_field_styles = QGroupBox("🎨 1-Tıkla Tematik Harita ve Morfoloji Stilleri")
        self.box_field_styles.setStyleSheet("QGroupBox { font-weight: bold; color: #0f766e; }")
        self.box_field_styles.setVisible(False)
        st_layout = QVBoxLayout(self.box_field_styles)
        st_layout.setSpacing(4)

        lbl_style_desc = QLabel("Hesaplanan ada katmanını tek tıkla mekânsal ve tematik olarak renklendirin:")
        lbl_style_desc.setStyleSheet("font-size: 11px; color: #64748b;")
        st_layout.addWidget(lbl_style_desc)

        btn_row1 = QHBoxLayout()
        self.btn_style_pop = QPushButton("👥 Nüfus (k/ha)")
        self.btn_style_pop.setToolTip("Brüt nüfus yoğunluğu kademeleri (0, 1-50, 51-150, 151-300, 301-600, 600+)")
        self.btn_style_pop.clicked.connect(self._apply_style_pop)
        btn_row1.addWidget(self.btn_style_pop)

        self.btn_style_taks = QPushButton("🏗️ TAKS (GSI)")
        self.btn_style_taks.setToolTip("Taban Alanı Katsayısı / Zemin Doluluk Oranı (GSI: <0.20, 0.20-0.40, 0.40-0.60, >0.60)")
        self.btn_style_taks.clicked.connect(self._apply_style_taks)
        btn_row1.addWidget(self.btn_style_taks)

        self.btn_style_kaks = QPushButton("🏢 KAKS (FSI / Emsal)")
        self.btn_style_kaks.setToolTip("Kat Alanı Katsayısı / Emsal (FSI: <0.60, 0.60-1.20, 1.20-2.0, 2.0-3.5, >3.5)")
        self.btn_style_kaks.clicked.connect(self._apply_style_kaks)
        btn_row1.addWidget(self.btn_style_kaks)
        st_layout.addLayout(btn_row1)

        btn_row2 = QHBoxLayout()
        self.btn_style_kat = QPushButton("📏 Kat Sayısı (L)")
        self.btn_style_kat.setToolTip("Ağırlıklı Ortalama Kat Adedi (L = İnşaat Alanı / Taban Alanı)")
        self.btn_style_kat.clicked.connect(self._apply_style_ort_kat)
        btn_row2.addWidget(self.btn_style_kat)

        self.btn_style_open = QPushButton("🌳 Açık Alan (%)")
        self.btn_style_open.setToolTip("Ada Zeminindeki Açık / Boş Alan Yüzdesi (100 - TAKS*100)")
        self.btn_style_open.clicked.connect(self._apply_style_open)
        btn_row2.addWidget(self.btn_style_open)

        self.btn_style_nizam = QPushButton("🏘️ Yapı Nizamı (A4)")
        self.btn_style_nizam.setToolTip("PlanX Morfoloji Motoru (A4): Ayrık, Bitişik / Blok, Karma, Boş Ada")
        self.btn_style_nizam.clicked.connect(self._apply_style_nizam)
        btn_row2.addWidget(self.btn_style_nizam)

        self.btn_style_doku = QPushButton("📐 Doku / Spacematrix")
        self.btn_style_doku.setToolTip("Spacematrix Morfolojik Tipolojisi: Seyrek Bahçeli, Orta Yoğunluk, Kompakt Blok, Kule Blok, Geleneksel Doku")
        self.btn_style_doku.clicked.connect(self._apply_style_doku)
        btn_row2.addWidget(self.btn_style_doku)
        st_layout.addLayout(btn_row2)

        layout.addWidget(self.box_field_styles)

        self.txt_field_results = QTextEdit()
        self.txt_field_results.setReadOnly(True)
        self.txt_field_results.setMinimumHeight(200)
        self.txt_field_results.setPlaceholderText("Ada bazında fiili bina sayısı, TAKS, KAKS, konut birimleri ve nüfus sonuçları burada listelenecektir...")
        layout.addWidget(self.txt_field_results)

        layout.addStretch()
        return tab

    def _run_field_analysis(self):
        ada_layer = self.cmb_ada_layer.currentLayer()
        bina_layer = self.cmb_bina_layer.currentLayer()
        hh = self.spn_hh.value()
        daire_m2 = self.spn_daire_m2.value()
        net_oran = self.spn_net_oran.value()

        if not ada_layer or not bina_layer:
            QMessageBox.warning(self, "Uyarı", "Lütfen hem ada hem de bina katmanını seçin!")
            return

        self.btn_run_field.setEnabled(False)
        self.field_progress.setVisible(True)
        self.field_progress.setRange(0, 0)
        self.txt_field_results.clear()
        self.txt_field_results.append("<i>Binalar adalarla mekânsal eşleştiriliyor, morfolojik metrikler ve fiili nüfus modelleniyor...</i>")

        try:
            result_items, stats = FieldEstimatorEngine.estimate_ada_population(
                ada_layer, bina_layer, hh, daire_m2, net_oran
            )

            # Çıktı Katmanı
            uri = f"MultiPolygon?crs={ada_layer.crs().authid()}"
            out_layer = QgsVectorLayer(uri, f"{ada_layer.name()}_FIILI_NUFUS", "memory")
            out_prov = out_layer.dataProvider()

            out_fields = QgsFields(ada_layer.fields())
            out_fields.append(QgsField('FIILI_BINA_SAYISI', QVariant.Int))
            out_fields.append(QgsField('FIILI_KONUT_SAYISI', QVariant.Int))
            out_fields.append(QgsField('FIILI_TAHMINI_NUFUS', QVariant.Int))
            out_fields.append(QgsField('FIILI_BRUT_YOGUNLUK_HA', QVariant.Double))
            out_fields.append(QgsField('FIILI_TAKS', QVariant.Double))
            out_fields.append(QgsField('FIILI_KAKS', QVariant.Double))
            out_fields.append(QgsField('ORT_KAT', QVariant.Double))
            out_fields.append(QgsField('ACIK_ALAN_YUZDE', QVariant.Double))
            out_fields.append(QgsField('SPACEMATRIX_OSR', QVariant.Double))
            out_fields.append(QgsField('BINA_YOGUNLUK_HA', QVariant.Double))
            out_fields.append(QgsField('ORT_KOMPAKLIK_IPQ', QVariant.Double))
            out_fields.append(QgsField('YAPI_NIZAMI', QVariant.String))
            out_fields.append(QgsField('MAX_BITISIK_DIZI', QVariant.Int))
            out_fields.append(QgsField('DOKU_TIPI', QVariant.String))
            out_fields.append(QgsField('FIILI_ISTIHDAM', QVariant.Int))
            out_fields.append(QgsField('FIILI_ARAC_YOLCULUK', QVariant.Int))
            out_fields.append(QgsField('FIILI_YAYA_YOLCULUK', QVariant.Int))

            out_prov.addAttributes(out_fields)
            out_layer.updateFields()

            new_feats = []
            for item in result_items:
                feat = item["feat"]
                nf = QgsFeature(out_fields)
                nf.setGeometry(item["geom"])
                attrs = feat.attributes()
                attrs.extend([
                    item["bina_sayisi"],
                    item["konut_birim_sayisi"],
                    item["tahmini_nufus"],
                    item["fiili_brut_yogunluk_ha"],
                    item.get("fiili_taks", 0.0),
                    item.get("fiili_kaks", 0.0),
                    item.get("ort_kat", 0.0),
                    item.get("acik_alan_yuzde", 0.0),
                    item.get("spacematrix_osr", 0.0),
                    item.get("bina_yogunluk_ha", 0.0),
                    item.get("ort_kompaklik_ipq", 0.0),
                    str(item.get("yapi_nizami", "")),
                    item.get("max_bitisik_dizi", 0),
                    str(item.get("doku_tipi", "")),
                    item["istihdam"],
                    item["gunluk_arac"],
                    item["gunluk_yaya"]
                ])
                nf.setAttributes(attrs)
                new_feats.append(nf)

            out_prov.addFeatures(new_feats)
            out_layer.updateExtents()

            self.last_field_out_layer = out_layer
            self._apply_style_pop()

            QgsProject.instance().addMapLayer(out_layer)
            self.box_field_styles.setVisible(True)

            # Raporlama
            report_text = f"""
            <h3>🏠 MEVCUT DURUM FİİLİ NÜFUS VE MORFOLOJİ RAPORU</h3>
            <table border="1" cellpadding="4" style="border-collapse:collapse; width:100%; margin-bottom:8px;">
                <tr style="background:#d97706; color:white;"><th colspan="2">1. Demografi & Yapılaşma Kapasitesi</th></tr>
                <tr><td><b>Toplam İncelenen Kadastro Adası</b></td><td>{stats['toplam_ada_sayisi']:,} Adet</td></tr>
                <tr><td><b>Eşleşen Toplam Bina Sayısı</b></td><td>{stats['toplam_eslesen_bina']:,} Adet</td></tr>
                <tr><td><b>Tahmini Konut Birim Sayısı</b></td><td>{stats['toplam_konut_birimi']:,} Bağımsız Bölüm</td></tr>
                <tr><td><b>Tahmini Fiili Yaşayan Nüfus</b></td><td style="color:#b45309; font-weight:bold; font-size:13px;">{stats['toplam_fiili_nufus']:,} Kişi</td></tr>
                <tr><td><b>Tahmini Fiili İstihdam</b></td><td><b>{stats['toplam_fiili_istihdam']:,}</b> Çalışan</td></tr>
                <tr><td><b>Ortalama Hanehalkı Büyüklüğü</b></td><td>{stats['ortalama_hanehalki']} Kişi/Hane (Daire: {stats['ortalama_daire_m2']} m²)</td></tr>
            </table>

            <table border="1" cellpadding="4" style="border-collapse:collapse; width:100%;">
                <tr style="background:#0f766e; color:white;"><th colspan="2">2. Kentsel Morfoloji, TAKS / KAKS ve Spacematrix Göstergeleri</th></tr>
                <tr><td><b>Toplam Bina Taban Alanı (m²)</b></td><td>{stats['toplam_taban_m2']:,.1f} m²</td></tr>
                <tr><td><b>Toplam İnşaat Alanı (m²)</b></td><td>{stats['toplam_insaat_m2']:,.1f} m²</td></tr>
                <tr style="background:#fefce8;"><td><b>Ortalama Fiili TAKS (GSI)</b></td><td style="font-weight:bold; color:#0f766e;">{stats['ortalama_taks']:.3f}</td></tr>
                <tr style="background:#fefce8;"><td><b>Ortalama Fiili KAKS (Emsal / FSI)</b></td><td style="font-weight:bold; color:#0f766e;">{stats['ortalama_kaks']:.3f}</td></tr>
                <tr><td><b>Ortalama Kat Adedi (L)</b></td><td><b>{stats['ortalama_kat']:.1f}</b> Kat</td></tr>
                <tr><td><b>Ortalama Açık Alan Oranı (%)</b></td><td><b>%{stats['ortalama_acik_alan_yuzde']:.1f}</b></td></tr>
            </table>
            <div style="font-size:10px; color:#475569; margin-top:6px; background:#f1f5f9; padding:6px; border-radius:3px;">
                <i>* PlanX kentsel morfoloji motoru ve Spacematrix (Berghauser Pont & Haupt) analitik kütüphanesi ile hesaplanmıştır. Yukarıdaki 1-tıkla stil butonlarıyla tematik analiz haritaları üretebilirsiniz.</i>
            </div>
            """
            self.txt_field_results.setHtml(report_text)

            QMessageBox.information(
                self, "Mevcut Durum Analizi Tamamlandı",
                f"Tahmini Fiili Yaşayan Nüfus: {stats['toplam_fiili_nufus']:,} Kişi\n"
                f"Ortalama TAKS: {stats['ortalama_taks']:.3f} | KAKS: {stats['ortalama_kaks']:.3f}\n"
                f"Tahmini İstihdam: {stats['toplam_fiili_istihdam']:,} Çalışan\n\n"
                f"Fiili nüfus ve ada morfolojisi katmanı haritanıza eklendi. "
                f"Arayüzdeki butonlarla tematik harita görünümlerini anında değiştirebilirsiniz."
            )

        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Mevcut Durum Analizi sırasında hata: {str(e)}")
            self.txt_field_results.append(f"<span style='color:red;'>Hata: {str(e)}</span>")
        finally:
            self.btn_run_field.setEnabled(True)
            self.field_progress.setVisible(False)

    def _apply_style_pop(self):
        if not self.last_field_out_layer or not self.last_field_out_layer.isValid():
            QMessageBox.warning(self, "Uyarı", "Geçerli bir saha analiz çıktısı katmanı bulunamadı! Lütfen önce analizi çalıştırın.")
            return
        ranges = [
            QgsRendererRange(0.0, 0.0, QgsFillSymbol.createSimple({'color': '#cbd5e1', 'outline_color': '#94a3b8'}), "0 (Konut Dışı / Boş)"),
            QgsRendererRange(0.1, 50.0, QgsFillSymbol.createSimple({'color': '#d9f99d', 'outline_color': '#65a30d'}), "1 - 50 k/ha (Seyrek)"),
            QgsRendererRange(50.1, 150.0, QgsFillSymbol.createSimple({'color': '#fde047', 'outline_color': '#ca8a04'}), "51 - 150 k/ha (Düşük)"),
            QgsRendererRange(150.1, 300.0, QgsFillSymbol.createSimple({'color': '#fb923c', 'outline_color': '#ea580c'}), "151 - 300 k/ha (Orta)"),
            QgsRendererRange(300.1, 600.0, QgsFillSymbol.createSimple({'color': '#f87171', 'outline_color': '#dc2626'}), "301 - 600 k/ha (Yüksek)"),
            QgsRendererRange(600.1, 5000.0, QgsFillSymbol.createSimple({'color': '#991b1b', 'outline_color': '#450a0a'}), "600+ k/ha (Çok Yüksek)")
        ]
        self.last_field_out_layer.setRenderer(QgsGraduatedSymbolRenderer("FIILI_BRUT_YOGUNLUK_HA", ranges))
        self.last_field_out_layer.triggerRepaint()
        if self.iface and hasattr(self.iface, "layerTreeView") and self.iface.layerTreeView():
            self.iface.layerTreeView().refreshLayerSymbology(self.last_field_out_layer.id())

    def _apply_style_taks(self):
        if not self.last_field_out_layer or not self.last_field_out_layer.isValid():
            QMessageBox.warning(self, "Uyarı", "Geçerli bir saha analiz çıktısı katmanı bulunamadı! Lütfen önce analizi çalıştırın.")
            return
        ranges = [
            QgsRendererRange(0.0, 0.0, QgsFillSymbol.createSimple({'color': '#f1f5f9', 'outline_color': '#cbd5e1'}), "0.00 (Taban Yok / Boş)"),
            QgsRendererRange(0.001, 0.20, QgsFillSymbol.createSimple({'color': '#dcfce7', 'outline_color': '#16a34a'}), "0.01 - 0.20 (Çok Düşük Doluluk)"),
            QgsRendererRange(0.201, 0.40, QgsFillSymbol.createSimple({'color': '#fef08a', 'outline_color': '#ca8a04'}), "0.21 - 0.40 (Düşük/Orta Doluluk)"),
            QgsRendererRange(0.401, 0.60, QgsFillSymbol.createSimple({'color': '#fdba74', 'outline_color': '#ea580c'}), "0.41 - 0.60 (Orta/Yüksek Doluluk)"),
            QgsRendererRange(0.601, 1.00, QgsFillSymbol.createSimple({'color': '#ef4444', 'outline_color': '#b91c1c'}), "0.61 - 1.00 (Bitişik / Yoğun Doluluk)")
        ]
        self.last_field_out_layer.setRenderer(QgsGraduatedSymbolRenderer("FIILI_TAKS", ranges))
        self.last_field_out_layer.triggerRepaint()
        if self.iface and hasattr(self.iface, "layerTreeView") and self.iface.layerTreeView():
            self.iface.layerTreeView().refreshLayerSymbology(self.last_field_out_layer.id())

    def _apply_style_kaks(self):
        if not self.last_field_out_layer or not self.last_field_out_layer.isValid():
            QMessageBox.warning(self, "Uyarı", "Geçerli bir saha analiz çıktısı katmanı bulunamadı! Lütfen önce analizi çalıştırın.")
            return
        ranges = [
            QgsRendererRange(0.0, 0.0, QgsFillSymbol.createSimple({'color': '#f1f5f9', 'outline_color': '#cbd5e1'}), "0.00 (İnşaat Yok / Boş)"),
            QgsRendererRange(0.001, 0.60, QgsFillSymbol.createSimple({'color': '#dbeafe', 'outline_color': '#2563eb'}), "0.01 - 0.60 (Düşük Emsal)"),
            QgsRendererRange(0.601, 1.20, QgsFillSymbol.createSimple({'color': '#93c5fd', 'outline_color': '#1d4ed8'}), "0.61 - 1.20 (Orta-Düşük Emsal)"),
            QgsRendererRange(1.201, 2.00, QgsFillSymbol.createSimple({'color': '#fde047', 'outline_color': '#ca8a04'}), "1.21 - 2.00 (Orta Emsal)"),
            QgsRendererRange(2.001, 3.50, QgsFillSymbol.createSimple({'color': '#fb923c', 'outline_color': '#ea580c'}), "2.01 - 3.50 (Yüksek Emsal)"),
            QgsRendererRange(3.501, 25.0, QgsFillSymbol.createSimple({'color': '#dc2626', 'outline_color': '#991b1b'}), "3.50+ (Çok Yüksek Emsal)")
        ]
        self.last_field_out_layer.setRenderer(QgsGraduatedSymbolRenderer("FIILI_KAKS", ranges))
        self.last_field_out_layer.triggerRepaint()
        if self.iface and hasattr(self.iface, "layerTreeView") and self.iface.layerTreeView():
            self.iface.layerTreeView().refreshLayerSymbology(self.last_field_out_layer.id())

    def _apply_style_ort_kat(self):
        if not self.last_field_out_layer or not self.last_field_out_layer.isValid():
            QMessageBox.warning(self, "Uyarı", "Geçerli bir saha analiz çıktısı katmanı bulunamadı! Lütfen önce analizi çalıştırın.")
            return
        ranges = [
            QgsRendererRange(0.0, 0.0, QgsFillSymbol.createSimple({'color': '#f1f5f9', 'outline_color': '#cbd5e1'}), "0 (Yapısız Ada)"),
            QgsRendererRange(0.1, 1.5, QgsFillSymbol.createSimple({'color': '#e0e7ff', 'outline_color': '#4338ca'}), "1 Katlı"),
            QgsRendererRange(1.51, 2.5, QgsFillSymbol.createSimple({'color': '#a5b4fc', 'outline_color': '#4338ca'}), "2 Katlı"),
            QgsRendererRange(2.51, 4.5, QgsFillSymbol.createSimple({'color': '#818cf8', 'outline_color': '#3730a3'}), "3 - 4 Katlı"),
            QgsRendererRange(4.51, 6.5, QgsFillSymbol.createSimple({'color': '#f59e0b', 'outline_color': '#b45309'}), "5 - 6 Katlı"),
            QgsRendererRange(6.51, 50.0, QgsFillSymbol.createSimple({'color': '#dc2626', 'outline_color': '#991b1b'}), "7+ Katlı")
        ]
        self.last_field_out_layer.setRenderer(QgsGraduatedSymbolRenderer("ORT_KAT", ranges))
        self.last_field_out_layer.triggerRepaint()
        if self.iface and hasattr(self.iface, "layerTreeView") and self.iface.layerTreeView():
            self.iface.layerTreeView().refreshLayerSymbology(self.last_field_out_layer.id())

    def _apply_style_open(self):
        if not self.last_field_out_layer or not self.last_field_out_layer.isValid():
            QMessageBox.warning(self, "Uyarı", "Geçerli bir saha analiz çıktısı katmanı bulunamadı! Lütfen önce analizi çalıştırın.")
            return
        ranges = [
            QgsRendererRange(0.0, 25.0, QgsFillSymbol.createSimple({'color': '#ef4444', 'outline_color': '#b91c1c'}), "% 0 - 25 (Çok Az Açık Alan / Bitişik)"),
            QgsRendererRange(25.01, 50.0, QgsFillSymbol.createSimple({'color': '#f97316', 'outline_color': '#c2410c'}), "% 25 - 50 (Düşük Açık Alan)"),
            QgsRendererRange(50.01, 70.0, QgsFillSymbol.createSimple({'color': '#facc15', 'outline_color': '#a16207'}), "% 50 - 70 (Orta Açık Alan)"),
            QgsRendererRange(70.01, 85.0, QgsFillSymbol.createSimple({'color': '#86efac', 'outline_color': '#16a34a'}), "% 70 - 85 (Yüksek Açık Alan)"),
            QgsRendererRange(85.01, 100.0, QgsFillSymbol.createSimple({'color': '#22c55e', 'outline_color': '#15803d'}), "% 85 - 100 (Geniş Açık Alan / Bahçeli)")
        ]
        self.last_field_out_layer.setRenderer(QgsGraduatedSymbolRenderer("ACIK_ALAN_YUZDE", ranges))
        self.last_field_out_layer.triggerRepaint()
        if self.iface and hasattr(self.iface, "layerTreeView") and self.iface.layerTreeView():
            self.iface.layerTreeView().refreshLayerSymbology(self.last_field_out_layer.id())

    def _apply_style_nizam(self):
        if not self.last_field_out_layer or not self.last_field_out_layer.isValid():
            QMessageBox.warning(self, "Uyarı", "Geçerli bir saha analiz çıktısı katmanı bulunamadı! Lütfen önce analizi çalıştırın.")
            return
        categories = [
            QgsRendererCategory("Ayrık", QgsFillSymbol.createSimple({'color': '#3b82f6', 'outline_color': '#1d4ed8'}), "Ayrık"),
            QgsRendererCategory("Bitişik / Blok", QgsFillSymbol.createSimple({'color': '#ef4444', 'outline_color': '#b91c1c'}), "Bitişik / Blok"),
            QgsRendererCategory("Karma (Ayrık + Bitişik)", QgsFillSymbol.createSimple({'color': '#f59e0b', 'outline_color': '#b45309'}), "Karma (Ayrık + Bitişik)"),
            QgsRendererCategory("Boş Ada", QgsFillSymbol.createSimple({'color': '#94a3b8', 'outline_color': '#64748b'}), "Boş Ada")
        ]
        self.last_field_out_layer.setRenderer(QgsCategorizedSymbolRenderer("YAPI_NIZAMI", categories))
        self.last_field_out_layer.triggerRepaint()
        if self.iface and hasattr(self.iface, "layerTreeView") and self.iface.layerTreeView():
            self.iface.layerTreeView().refreshLayerSymbology(self.last_field_out_layer.id())

    def _apply_style_doku(self):
        if not self.last_field_out_layer or not self.last_field_out_layer.isValid():
            QMessageBox.warning(self, "Uyarı", "Geçerli bir saha analiz çıktısı katmanı bulunamadı! Lütfen önce analizi çalıştırın.")
            return
        categories = [
            QgsRendererCategory("Seyrek / Az Katlı Bahçeli", QgsFillSymbol.createSimple({'color': '#10b981', 'outline_color': '#047857'}), "Seyrek / Az Katlı Bahçeli"),
            QgsRendererCategory("Orta Yoğunluklu Doku", QgsFillSymbol.createSimple({'color': '#3b82f6', 'outline_color': '#1d4ed8'}), "Orta Yoğunluklu Doku"),
            QgsRendererCategory("Yüksek Yoğunluklu / Kompakt Blok", QgsFillSymbol.createSimple({'color': '#ef4444', 'outline_color': '#b91c1c'}), "Yüksek Yoğunluklu / Kompakt Blok"),
            QgsRendererCategory("Nokta / Kule Bloklar", QgsFillSymbol.createSimple({'color': '#8b5cf6', 'outline_color': '#6d28d9'}), "Nokta / Kule Bloklar"),
            QgsRendererCategory("Geleneksel / Karma Kentsel Doku", QgsFillSymbol.createSimple({'color': '#f59e0b', 'outline_color': '#b45309'}), "Geleneksel / Karma Kentsel Doku"),
            QgsRendererCategory("Boş / Yapılaşmamış Ada", QgsFillSymbol.createSimple({'color': '#94a3b8', 'outline_color': '#64748b'}), "Boş / Yapılaşmamış Ada")
        ]
        self.last_field_out_layer.setRenderer(QgsCategorizedSymbolRenderer("DOKU_TIPI", categories))
        self.last_field_out_layer.triggerRepaint()
        if self.iface and hasattr(self.iface, "layerTreeView") and self.iface.layerTreeView():
            self.iface.layerTreeView().refreshLayerSymbology(self.last_field_out_layer.id())

    def _open_theoretical_guide(self):
        """Metodoloji ve stüdyo el kitabını (HTML) varsayılan tarayıcıda açar."""
        guide_path = os.path.join(PLUGIN_DIR, "docs", "teorik_rehber.html")
        if os.path.exists(guide_path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(guide_path))
        else:
            QMessageBox.warning(
                self, "Rehber Bulunamadı",
                f"Metodoloji rehberi dosyası bulunamadı:\n{guide_path}"
            )


