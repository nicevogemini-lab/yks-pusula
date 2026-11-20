# -*- coding: utf-8 -*-
"""Canli tanimlari duzeltir: Sakir (mezun) kendi profiline, velisi Mehmet.

Yusuf'un profiline (11. sinif, velisi Muslum) dokunulmaz; Sakir'in hesabi ve
veli bagi oradan alinip yeni "Sakir" profilinine tasinir. Uygulamanin kendi
kaydetme ve plan uretme kodlari kullanilir.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

KOK = Path(__file__).resolve().parent
load_dotenv(KOK / ".env.bulut")
os.environ.setdefault("PUSULA_DATABASE_URL", os.getenv("PUSULA_DATABASE_URL", "").strip())

from app.api import _profil_kaydet  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app import yetki  # noqa: E402
from app.models import SINIF_MEZUN, Kullanici, Profil, VeliOgrenci  # noqa: E402
from app.services.plan import gunluk_plan_uret  # noqa: E402

AD_SAKIR = "Şakir"
ALAN_SAKIR = "sayisal"  # ayarlardan tek tikla degistirilebilir

with SessionLocal() as db:
    ogrenci = db.query(Kullanici).filter(Kullanici.kullanici_adi == "şakir").one()
    veli = db.query(Kullanici).filter(Kullanici.kullanici_adi == "mehmet").one()
    yusuf = db.get(Profil, 5)
    print(f"baslangic: sakir.profil_id={ogrenci.profil_id} | yusuf profil={yusuf.ad}({yusuf.sinif})")

    sakir = db.query(Profil).filter(Profil.ad == AD_SAKIR).first()
    if sakir is None:
        sakir = _profil_kaydet(
            db,
            AD_SAKIR,
            SINIF_MEZUN,
            ALAN_SAKIR,
            hedef_siralama=0,
            gunluk_hedef_dk=180,
        )
        db.commit()
        db.refresh(sakir)
        eklenen = gunluk_plan_uret(db, sakir, gun_sayisi=7)
        print(f"profil acildi: {sakir.ad} (id={sakir.id}, sinif={sakir.sinif}, alan={sakir.alan}) plan={eklenen}")
    else:
        print(f"profil zaten var: {sakir.ad} (id={sakir.id}, sinif={sakir.sinif})")

    if ogrenci.profil_id != sakir.id:
        ogrenci.profil_id = sakir.id
        db.commit()
        print(f"ogrenci hesabi tasindi: sakir -> profil {sakir.id}")

    # Veli bagi: mehmet yalniz Sakir'in velisi
    db.query(VeliOgrenci).filter(VeliOgrenci.veli_id == veli.id).delete()
    if not db.query(VeliOgrenci).filter(
        VeliOgrenci.veli_id == veli.id, VeliOgrenci.profil_id == sakir.id
    ).first():
        db.add(VeliOgrenci(veli_id=veli.id, profil_id=sakir.id))
    db.commit()

    print("\n--- dogrulama (uygulamanin yetki kodu)")
    for kisi in (veli, ogrenci):
        db.refresh(kisi)
        izinli = sorted(yetki.erisilebilir_profil_idleri(db, kisi))
        adlar = [db.get(Profil, i).ad for i in izinli]
        print(f"{kisi.kullanici_adi:8} rol={kisi.rol:8} profil_id={kisi.profil_id} erisim={adlar}")

    print("\n--- profiller")
    for p in db.query(Profil).order_by(Profil.id):
        print(f"  id={p.id} ad={p.ad} sinif={p.sinif_etiketi} alan={p.alan_etiketi}")
    print("\n--- veli_ogrenci")
    for bag in db.query(VeliOgrenci):
        veli_ad = db.get(Kullanici, bag.veli_id).kullanici_adi
        print(f"  veli={veli_ad} -> profil={db.get(Profil, bag.profil_id).ad}")
