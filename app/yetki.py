# -*- coding: utf-8 -*-
"""Rol yetkileri ve profil erişim kapsamı.

Üç rol vardır:

* ``yonetici`` — her ekranı açar, kullanıcı tanımlar.
* ``veli`` — kullanıcı tanımlama dışında her şeyi yapar, yalnız kendi
  öğrencilerinin verisini görür. Müfredatı (ders/konu) da düzenleyebilir.
* ``ogrenci`` — deneme girişi ve ayarlar dışındaki ekranları kullanır,
  yalnız kendi profilini görür.

Kapsam tek yerden uygulanır: istek işlenirken o anki kullanıcı bir
``ContextVar`` içinde tutulur; ``api._profil_getir`` her çağrıda buradan
kontrol eder. Böylece profil kimliği alan bütün uçlar ayrı ayrı düzenlenmeden
korunur. Kullanıcı yoksa (giriş kapısı kapalı kurulum ya da testler) kapsam
uygulanmaz.
"""
from __future__ import annotations

from contextvars import ContextVar

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Kullanici, VeliOgrenci

TUM_ROLLER = ("yonetici", "veli", "ogrenci")

# Sol menüdeki her sayfa için onu görebilen roller
SAYFA_YETKI: dict[str, set[str]] = {
    "panel": set(TUM_ROLLER),
    "mufredat": set(TUM_ROLLER),
    "plan": set(TUM_ROLLER),
    "okul": set(TUM_ROLLER),
    "analiz": set(TUM_ROLLER),
    "koc": set(TUM_ROLLER),
    "deneme": {"yonetici", "veli"},
    "ayarlar": {"yonetici", "veli"},
    "kullanicilar": {"yonetici"},
}

# Rolün yazamadığı işlem grupları. Okuma her rolde serbesttir.
YAZMA_KAPALI: dict[str, set[str]] = {
    "ogrenci": {"deneme", "profil", "ayar"},
}

_aktif: ContextVar[Kullanici | None] = ContextVar("pusula_kullanici", default=None)


# ------------------------------------------------------------- o anki kullanıcı
def kullanici_ayarla(kullanici: Kullanici | None) -> None:
    """İsteğin kalanında geçerli olacak kullanıcıyı belirler."""
    _aktif.set(kullanici)


def mevcut_kullanici() -> Kullanici | None:
    return _aktif.get()


def rol() -> str | None:
    kullanici = mevcut_kullanici()
    return kullanici.rol if kullanici else None


# ------------------------------------------------------------------- yetkiler
def sayfa_gorunur(sayfa: str, kullanici: Kullanici | None = None) -> bool:
    kullanici = kullanici if kullanici is not None else mevcut_kullanici()
    if kullanici is None:
        return True
    return kullanici.rol in SAYFA_YETKI.get(sayfa, set())


def yazabilir(islem: str, kullanici: Kullanici | None = None) -> bool:
    """``islem``: deneme, profil, ayar, plan, mufredat, koc..."""
    kullanici = kullanici if kullanici is not None else mevcut_kullanici()
    if kullanici is None:
        return True
    return islem not in YAZMA_KAPALI.get(kullanici.rol, set())


def yazma_kontrol(islem: str) -> None:
    if not yazabilir(islem):
        raise HTTPException(403, "Bu işlem için yetkin yok.")


def yonetici_mi(kullanici: Kullanici | None = None) -> bool:
    """Yönetici mi? Kapısız (yerel) modda tam yetki sayılır."""
    kullanici = kullanici if kullanici is not None else mevcut_kullanici()
    return kullanici is None or kullanici.rol == "yonetici"


def yonetici_kontrol() -> None:
    if not yonetici_mi():
        raise HTTPException(403, "Bu işlemi yalnız yönetici yapabilir.")


# Müfredat (ders/konu) düzenleme: yönetici ve veli
MUFREDAT_ROLLERI = {"yonetici", "veli"}


def mufredat_yetkisi(kullanici: Kullanici | None = None) -> bool:
    """Müfredatta ders/konu ekleme-silme yetkisi var mı? Kapısız modda evet."""
    kullanici = kullanici if kullanici is not None else mevcut_kullanici()
    return kullanici is None or kullanici.rol in MUFREDAT_ROLLERI


def mufredat_kontrol() -> None:
    if not mufredat_yetkisi():
        raise HTTPException(
            403, "Bu işlemi yalnız yönetici ve veli yapabilir."
        )


# ------------------------------------------------------------- veri kapsamı
def erisilebilir_profil_idleri(db: Session, kullanici: Kullanici | None = None) -> set[int] | None:
    """Kullanıcının görebildiği profil kimlikleri; ``None`` = tümü."""
    kullanici = kullanici if kullanici is not None else mevcut_kullanici()
    if kullanici is None or kullanici.rol == "yonetici":
        return None
    if kullanici.rol == "ogrenci":
        return {kullanici.profil_id} if kullanici.profil_id else set()
    return set(
        db.execute(
            select(VeliOgrenci.profil_id).where(VeliOgrenci.veli_id == kullanici.id)
        ).scalars()
    )


def profil_kontrol(db: Session, profil_id: int) -> None:
    """Yetkisiz profil isteğini 403 ile keser."""
    izinli = erisilebilir_profil_idleri(db)
    if izinli is not None and profil_id not in izinli:
        raise HTTPException(403, "Bu öğrencinin verisine erişimin yok.")


def veli_baglantisi(db: Session, veli_id: int, profil_id: int) -> VeliOgrenci | None:
    return db.execute(
        select(VeliOgrenci).where(
            VeliOgrenci.veli_id == veli_id, VeliOgrenci.profil_id == profil_id
        )
    ).scalar_one_or_none()
