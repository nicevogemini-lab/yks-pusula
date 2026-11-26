# -*- coding: utf-8 -*-
"""Sınıfa göre müfredat kapsamı.

TYT konuları 9-10. sınıf, AYT konuları 11-12. sınıf müfredatından gelir.
Öğrencinin sınıfı hangi konuların çalışma kapsamında olduğunu belirler:

* 11. sınıf -> 9-10. sınıf TYT + 11. sınıf AYT konuları
* 12. sınıf -> 9-10. sınıf TYT + 11-12. sınıf AYT konuları
* mezun (0) -> tüm YKS müfredatı

Kapsam; müfredat sayfası, plan adayları ve analiz tablosunda aynı yerden
uygulanır; böylece "plana girmeyen konu analizde görünsün, plana sızmasın"
kuralı tek noktadan korunur.
"""
from __future__ import annotations

# TYT 9-10. sınıf, AYT 11-12. sınıf konularını kapsar
TYT_SINIFLARI = (9, 10)
AYT_SINIFLARI = (11, 12)

# Güncel sınıf konularını plan önceliğinde öne alan çarpan
GUNCEL_SINIF_CARPANI = 1.2


def kapsam_siniflari(sinif: int | None, sinav: str | None = None) -> tuple[int, ...] | None:
    """Sınıfın kapsadığı sınıf düzeyleri.

    ``sinav`` verilirse kural sınava göre daralır (TYT yalnız 9-10, AYT yalnız
    11-12). ``None`` dönerse sınır yok (mezun).
    """
    if not sinif:
        return None
    if sinav == "TYT":
        if sinif in (9, 10):
            return tuple(range(9, sinif + 1))
        return TYT_SINIFLARI
    if sinav == "AYT":
        if sinif in (9, 10):
            return ()
        return (11,) if sinif == 11 else AYT_SINIFLARI
    # Sınav bilinmiyorsa iki sınavın birleşimi
    if sinif in (9, 10):
        return tuple(range(9, sinif + 1))
    if sinif == 11:
        return (9, 10, 11)
    return (9, 10, 11, 12)


def konu_kapsami(sinif: int | None) -> tuple[int, int] | None:
    """Kapsamın en geniş sınıf aralığı; ``None`` ise sınır yok."""
    siniflar = kapsam_siniflari(sinif)
    if not siniflar:
        return None
    return (siniflar[0], siniflar[-1])


def kapsam_disi(konu_sinif: int | None, sinif: int | None, sinav: str | None = None) -> bool:
    """Konu bu sınıfın (ve varsa sınavın) kapsamı dışında mı?"""
    izinli = kapsam_siniflari(sinif, sinav)
    if izinli is None:
        return False
    return (konu_sinif or 0) not in izinli


def kapsam_etiketi(sinif: int | None) -> str:
    if not sinif:
        return "Tüm YKS müfredatı"
    if sinif in (9, 10):
        return f"9-{sinif}. sınıf TYT konuları"
    if sinif == 11:
        return "9-10. sınıf TYT + 11. sınıf AYT konuları"
    return "9-10. sınıf TYT + 11-12. sınıf AYT konuları"


def kapsam_cizelgesi(sinif: int | None) -> dict[str, list[int]]:
    """Arayüz için sınav bazlı sınıf listeleri (mezunda boş = sınır yok)."""
    return {
        "tyt": list(kapsam_siniflari(sinif, "TYT") or ()),
        "ayt": list(kapsam_siniflari(sinif, "AYT") or ()),
    }


def oncelik_carpani(konu_sinif: int | None, sinif: int | None) -> float:
    """Güncel sınıfın konuları plan önceliğinde bir miktar öne alınır."""
    if not sinif or not konu_sinif:
        return 1.0
    return GUNCEL_SINIF_CARPANI if konu_sinif == sinif else 1.0
