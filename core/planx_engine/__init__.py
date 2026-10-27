# -*- coding: utf-8 -*-
"""PlanX Gömülü Ulaşım ve Ağ Analitik Motoru (PLN3113 NİP Entegrasyonu).

PLN3113 - Tire NİP Analiz Stüdyosu

Saf NumPy çekirdeği ve opsiyonel SciPy hızlandırma yolu.
Dış eklenti bağımlılığı yoktur.
"""
from __future__ import annotations

import contextlib

HAS_SCIPY = False
with contextlib.suppress(Exception):
    import scipy  # noqa: F401
    from scipy.sparse import csgraph, csr_matrix  # noqa: F401
    HAS_SCIPY = True

__all__ = ["HAS_SCIPY"]
