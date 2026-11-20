# -*- coding: utf-8 -*-
"""Sınıfa göre müfredat kapsamı.

Öğrencinin sınıfı, hangi konuların çalışma kapsamında olduğunu belirler:

* 11. sınıf -> 9-11. sınıf konuları (YKS öncesi son iki yıl ağırlıklı)
* 12. sınıf -> 9-12. sınıf konuları
* mezun (0) -> tüm YKS müfredatı

Kapsam; müfredat sayfası, plan adayları ve analiz tablosunda aynı yerden
uygulanır; böylece "plana girmeyen konu analizde görünsün, plana sızmasın"
kuralı tek noktadan korunur.
"""
from __future__ import annotations

# Güncel sınıf konularını plan önceliğinde öne alan çarpan
GUNCEL_SINIF_CARPANI = 1.2


def konu_kapsami(sinif: int | None) -> tuple[int, int] | None:
    """Sınıfın konu kapsamı; ``None`` ise kapsam sınırı yok (tüm müfredat)."""
    if sinif == 11:
        return (9, 11)
    if sinif == 12:
        return (9, 12)
    return None


def kapsam_disi(konu_sinif: int | None, sinif: int | None) -> bool:
    """Konu bu sınıfın kapsamı dışında mı?"""
    kapsam = konu_kapsami(sinif)
    if kapsam is None:
        return False
    alt, ust = kapsam
    return not (alt <= (konu_sinif or 0) <= ust)


def kapsam_etiketi(sinif: int | None) -> str:
    kapsam = konu_kapsami(sinif)
    if kapsam is None:
        return "Tüm YKS müfredatı"
    return f"{kapsam[0]}-{kapsam[1]}. sınıf konuları"


def oncelik_carpani(konu_sinif: int | None, sinif: int | None) -> float:
    """Güncel sınıfın konuları plan önceliğinde bir miktar öne alınır."""
    if not sinif or not konu_sinif:
        return 1.0
    return GUNCEL_SINIF_CARPANI if konu_sinif == sinif else 1.0
