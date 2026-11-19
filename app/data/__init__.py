# -*- coding: utf-8 -*-
"""Müfredat verisi paketi: tüm ders ve konuları tek yerden sunar."""
from __future__ import annotations

from .mufredat import DERSLER, TYT_KONU_YENIDEN_ADLANDIRMA, TYT_KONULARI, konulari_uret
from .mufredat_ayt import (
    ALAN_AYT_DERSLERI,
    AYT_DERSLER,
    AYT_KONU_YENIDEN_ADLANDIRMA,
    AYT_KONULARI,
)

TUM_DERSLER: list[tuple] = DERSLER + AYT_DERSLER
TUM_KONULAR: dict[str, list[tuple]] = {**TYT_KONULARI, **AYT_KONULARI}

# Ders kodu -> {eski konu adı: yeni konu adı}. Ders kodları TYT ve AYT
# arasında çakışmadığı için iki harita tek sözlükte birleştirilir.
KONU_YENIDEN_ADLANDIRMA: dict[str, dict[str, str]] = {
    **TYT_KONU_YENIDEN_ADLANDIRMA,
    **AYT_KONU_YENIDEN_ADLANDIRMA,
}

BECERI_ETIKET = {
    "KB": "Kavramsal Beceri",
    "AB": "Alan Becerisi",
    "SD": "Sosyal-Duygusal Beceri",
    "OK": "Okuryazarlık",
}


def tum_konular_listesi() -> list[dict]:
    """Tüm derslerin konularını düz liste olarak döndürür."""
    sonuc: list[dict] = []
    for ders_kod, satirlar in TUM_KONULAR.items():
        sonuc.extend(konulari_uret(ders_kod, satirlar))
    return sonuc


def alan_ders_kodlari(alan: str) -> set[str]:
    """Bir alanın sorumlu olduğu ders kodları (TYT ortak + alan AYT)."""
    kodlar = {d[0] for d in TUM_DERSLER if d[3] == "ortak"}
    kodlar.update(ALAN_AYT_DERSLERI.get(alan, []))
    return kodlar


def ders_konu_sayisi() -> dict[str, int]:
    """Ders koduna göre konu sayısı."""
    return {k: len(v) for k, v in TUM_KONULAR.items()}
