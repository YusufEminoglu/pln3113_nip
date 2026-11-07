# -*- coding: utf-8 -*-
"""MPYY NİP yol çizme aracı: profil gir, orta aksı çiz, platform üç tabloya yazılsın.

planX CAD Drafting Toolset'teki yol aracının akışı: önce enkesit penceresi,
sonra haritada orta aks (sol tık nokta ekler, Backspace son noktayı siler,
sağ tık / Enter bitirir, Esc çizimi iptal eder). Çizim sırasında platform
önizlenir. Araç etkin kaldıkça aynı profille yeni yollar çizilebilir.
"""
from __future__ import annotations

from contextlib import suppress

from qgis.core import (
    QgsCoordinateTransform,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsWkbTypes,
)
from qgis.gui import QgsMapTool, QgsRubberBand
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)

from ..core.mpyy_road import YOL_TIPLERI, YolProfili, platform_uret, yol_ekle
from ..core.nip_workspace import find_mpyy_layer

GEREKLI = ("Yolorta", "DigerYolNesneleri", "AdaKenari")


class YolProfilDialog(QDialog):
    """Yol enkesiti penceresi; toplam genişlik canlı hesaplanır."""

    def __init__(self, parent=None, profil: YolProfili | None = None):
        super().__init__(parent)
        self.setWindowTitle("MPYY Yol Profili")
        profil = profil or YolProfili()
        lay = QVBoxLayout(self)
        form = QFormLayout()

        self.cmb_tip = QComboBox()
        for kod, ad in YOL_TIPLERI:
            self.cmb_tip.addItem(ad, kod)
        self.cmb_tip.setCurrentIndex(max(0, self.cmb_tip.findData(profil.yol_tipi)))
        form.addRow("Yol tipi (YolTip):", self.cmb_tip)

        self.chk_tek = QCheckBox("Tek yönlü")
        self.chk_tek.setChecked(profil.tek_yon)
        form.addRow("Yön:", self.chk_tek)

        self.spn_serit = QSpinBox()
        self.spn_serit.setRange(1, 6)
        self.spn_serit.setValue(profil.serit_sayisi)
        form.addRow("Şerit sayısı (her yön):", self.spn_serit)

        def metre(value, maximum=30.0):
            spin = QDoubleSpinBox()
            spin.setRange(0.0, maximum)
            spin.setSingleStep(0.25)
            spin.setDecimals(2)
            spin.setSuffix(" m")
            spin.setValue(value)
            return spin

        self.spn_serit_gen = metre(profil.serit_genisligi, 10.0)
        self.spn_serit_gen.setMinimum(1.0)
        form.addRow("Şerit genişliği:", self.spn_serit_gen)
        self.spn_refuj = metre(profil.refuj)
        form.addRow("Orta refüj:", self.spn_refuj)
        self.spn_sol = metre(profil.sol_kaldirim)
        form.addRow("Sol kaldırım:", self.spn_sol)
        self.spn_sag = metre(profil.sag_kaldirim)
        form.addRow("Sağ kaldırım:", self.spn_sag)
        self.spn_kose = metre(profil.kose_yaricapi, 50.0)
        self.spn_kose.setToolTip("Kavşakta ada köşesi yarıçapı; bordür bununla eş merkezli "
                                 "(yarıçap + kaldırım) yuvarlanır. 0: köşe yuvarlanmaz.")
        form.addRow("Kavşak köşe yarıçapı:", self.spn_kose)
        lay.addLayout(form)

        self.lbl_toplam = QLabel()
        self.lbl_toplam.setWordWrap(True)
        lay.addWidget(self.lbl_toplam)

        not_lbl = QLabel(
            "Yolorta'ya YolTip ve toplam genişlik (YolGenisligi), DigerYolNesneleri'ne taşıt yolu, "
            "refüj ve kaldırım poligonları, AdaKenari'na platformun dış kenarları yazılır. "
            "Var olan bir yolu kestiğinizde kavşak açılır ve köşeleri yuvarlanır."
        )
        not_lbl.setWordWrap(True)
        lay.addWidget(not_lbl)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

        for widget in (self.spn_serit, self.spn_serit_gen, self.spn_refuj, self.spn_sol, self.spn_sag):
            widget.valueChanged.connect(self._guncelle)
        self.chk_tek.toggled.connect(self._guncelle)
        self._guncelle()

    def profil(self) -> YolProfili:
        return YolProfili(
            yol_tipi=self.cmb_tip.currentData(),
            serit_sayisi=self.spn_serit.value(),
            serit_genisligi=self.spn_serit_gen.value(),
            refuj=self.spn_refuj.value(),
            sol_kaldirim=self.spn_sol.value(),
            sag_kaldirim=self.spn_sag.value(),
            tek_yon=self.chk_tek.isChecked(),
            kose_yaricapi=self.spn_kose.value(),
        )

    def _guncelle(self, *_):
        self.spn_refuj.setEnabled(not self.chk_tek.isChecked())
        p = self.profil()
        self.lbl_toplam.setText(
            f"<b>Toplam platform: {p.toplam_genislik:.2f} m</b> "
            f"(taşıt yolu {p.tasit_genisligi:.2f} m"
            + ("" if p.tek_yon else f" + refüj {p.refuj:.2f} m")
            + f" + kaldırım {p.sol_kaldirim:.2f} + {p.sag_kaldirim:.2f} m)"
        )


class MpyyYolCizimAraci(QgsMapTool):
    mesaj = pyqtSignal(str)

    def __init__(self, iface, profil: YolProfili):
        super().__init__(iface.mapCanvas())
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.profil = profil
        self.noktalar: list[QgsPointXY] = []
        self.katmanlar = {}
        self.rb_aks = None
        self.rb_onizleme = None

    # -- yaşam döngüsü -------------------------------------------------
    @staticmethod
    def katmanlari_bul():
        katmanlar = {ad: find_mpyy_layer(ad) for ad in GEREKLI}
        eksik = [ad for ad, katman in katmanlar.items() if katman is None]
        return katmanlar, eksik

    def activate(self):
        super().activate()
        self.katmanlar, eksik = self.katmanlari_bul()
        if eksik:
            self.iface.messageBar().pushWarning(
                "MPYY Yol", "Projede bulunamayan katman: " + ", ".join(eksik)
                + ". MPYY 1.1.7 NİP veritabanını panelden yükleyin.")
            self.canvas.unsetMapTool(self)
            return
        self.rb_aks = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.LineGeometry)
        self.rb_aks.setColor(QColor(220, 38, 38))
        self.rb_aks.setWidth(2)
        self.rb_onizleme = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.PolygonGeometry)
        self.rb_onizleme.setColor(QColor(220, 38, 38, 160))
        self.rb_onizleme.setFillColor(QColor(220, 38, 38, 50))
        self.rb_onizleme.setWidth(1)
        self._durum()

    def deactivate(self):
        self._temizle()
        for rb in (self.rb_aks, self.rb_onizleme):
            if rb is not None:
                self.canvas.scene().removeItem(rb)
        self.rb_aks = self.rb_onizleme = None
        super().deactivate()

    # -- olaylar -------------------------------------------------------
    def _nokta(self, event) -> QgsPointXY:
        match = self.canvas.snappingUtils().snapToMap(event.pos())
        return QgsPointXY(match.point()) if match.isValid() else self.toMapCoordinates(event.pos())

    def canvasPressEvent(self, event):
        if self.rb_aks is None:
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self.noktalar.append(self._nokta(event))
            self._ciz()
            self._durum()
        elif event.button() == Qt.MouseButton.RightButton:
            self._bitir()

    def canvasMoveEvent(self, event):
        if self.noktalar and self.rb_aks is not None:
            self._ciz(self._nokta(event))

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self._temizle()
            self.mesaj.emit("🛣 Çizim iptal edildi.")
        elif key == Qt.Key.Key_Backspace and self.noktalar:
            self.noktalar.pop()
            self._ciz()
            self._durum()
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._bitir()
        else:
            return
        event.accept()

    # -- çizim -----------------------------------------------------------
    def _donusum(self):
        return QgsCoordinateTransform(
            self.canvas.mapSettings().destinationCrs(), self.katmanlar["Yolorta"].crs(), QgsProject.instance())

    def _ciz(self, imlec: QgsPointXY | None = None):
        noktalar = self.noktalar + ([imlec] if imlec is not None else [])
        self.rb_aks.reset(QgsWkbTypes.GeometryType.LineGeometry)
        for n in noktalar:
            self.rb_aks.addPoint(n)
        self.rb_onizleme.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
        if len(noktalar) < 2:
            return
        with suppress(Exception):  # önizleme hatası çizimi engellememeli
            aks = QgsGeometry.fromPolylineXY(noktalar)
            ileri = self._donusum()
            aks.transform(ileri)
            parcalar = platform_uret(aks, self.profil)
            platform = QgsGeometry.unaryUnion(
                [g for k, g in parcalar.items() if k != "kenarlar" and g is not None])
            platform.transform(QgsCoordinateTransform(
                self.katmanlar["Yolorta"].crs(), self.canvas.mapSettings().destinationCrs(), QgsProject.instance()))
            self.rb_onizleme.setToGeometry(platform, None)

    def _durum(self):
        p = self.profil
        self.mesaj.emit(
            f"🛣 Yol çiz — {p.toplam_genislik:.2f} m | {len(self.noktalar)} nokta | "
            "Sol tık: nokta, Backspace: geri al, Sağ tık/Enter: bitir, Esc: iptal")

    def _temizle(self):
        self.noktalar = []
        if self.rb_aks is not None:
            self.rb_aks.reset(QgsWkbTypes.GeometryType.LineGeometry)
        if self.rb_onizleme is not None:
            self.rb_onizleme.reset(QgsWkbTypes.GeometryType.PolygonGeometry)

    def _bitir(self):
        if len(self.noktalar) < 2:
            self.mesaj.emit("🛣 En az iki nokta gerekli.")
            return
        aks = QgsGeometry.fromPolylineXY(self.noktalar)
        try:
            aks.transform(self._donusum())
            sayac = yol_ekle(aks, self.profil, self.katmanlar["Yolorta"],
                             self.katmanlar["DigerYolNesneleri"], self.katmanlar["AdaKenari"])
        except Exception as exc:  # öğrenciye hata çubuğunda gösterilir
            self.iface.messageBar().pushCritical("MPYY Yol", f"Yol üretilemedi: {exc}")
            self._temizle()
            return
        self.iface.messageBar().pushSuccess(
            "MPYY Yol",
            f"Yol eklendi ({self.profil.toplam_genislik:.2f} m): taşıt yolu {sayac['TasitYolu']}, "
            f"refüj {sayac['Refuj']}, kaldırım {sayac['Kaldirim']}, ada kenarı {sayac['AdaKenari']}"
            + (f"; {sayac['kavsak']} kavşak köşesi yuvarlandı" if sayac.get("kavsak") else ""))
        self._temizle()
        self._durum()
