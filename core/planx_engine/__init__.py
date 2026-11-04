# -*- coding: utf-8 -*-
"""PlanX Gömülü Ulaşım ve Ağ Analitik Motoru (PLN3113 NİP Entegrasyonu).

PLN3113 - Tire NİP Analiz Stüdyosu

Saf NumPy çekirdeği ve opsiyonel SciPy hızlandırma yolu.
Dış eklenti bağımlılığı yoktur.

Kaynak: PlanX 4.23.0 (2026-11-04) ``engine`` paketi. Bu sürümle gelen
düzeltmeler: yönlü segment uçları üzerinde açısal seçim (çıkmaz sokak
seçimi 0), yayımlanmış NAIN normalleştirmesi ``NC^1.2 / (TD + 2)``, global
yarıçap için SciPy toplu yol ve iptal edildiğinde :class:`Cancelled`.
"""
from __future__ import annotations

import contextlib

HAS_SCIPY = False
with contextlib.suppress(Exception):
    import scipy  # noqa: F401
    from scipy.sparse import csgraph, csr_matrix  # noqa: F401
    HAS_SCIPY = True


class Cancelled(Exception):
    """Bir motor çekirdeğinin ``cancel()`` geri çağrısı tetiklendiğinde fırlatılır.

    ``partial`` o ana kadar hesaplananları taşır (ulaşılmayan satırlar
    "boş" değerleriyle doldurulur, asla başlatılmamış bellek değildir);
    yalnızca ilerleme bildirmek içindir, hiçbir zaman bitmiş bir sonuç
    değildir ve katmana yazılmamalıdır.
    """

    def __init__(self, partial=None, message="cancelled"):
        super().__init__(message)
        self.partial = partial


__all__ = ["HAS_SCIPY", "Cancelled"]
