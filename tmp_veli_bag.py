# -*- coding: utf-8 -*-
"""Veli-ogrenci bagini kurar ve gercek yetki kod yoluyla dogrular (gecici)."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import text

KOK = Path(__file__).resolve().parent
load_dotenv(KOK / ".env.bulut")
os.environ.setdefault("PUSULA_DATABASE_URL", os.getenv("PUSULA_DATABASE_URL", "").strip())

from app.database import SessionLocal  # noqa: E402
from app import yetki  # noqa: E402
from app.models import Kullanici, VeliOgrenci  # noqa: E402

with SessionLocal() as db:
    veli = db.query(Kullanici).filter(Kullanici.kullanici_adi == "mehmet").one()
    ogrenci = db.query(Kullanici).filter(Kullanici.kullanici_adi == "şakir").one()

    bag = (
        db.query(VeliOgrenci)
        .filter(VeliOgrenci.veli_id == veli.id, VeliOgrenci.profil_id == ogrenci.profil_id)
        .first()
    )
    if bag is None:
        db.add(VeliOgrenci(veli_id=veli.id, profil_id=ogrenci.profil_id))
        db.commit()
        print(f"bag kuruldu: veli={veli.kullanici_adi}({veli.id}) -> profil={ogrenci.profil_id}")
    else:
        print(f"bag zaten var: veli={veli.kullanici_adi}({veli.id}) -> profil={ogrenci.profil_id}")

    for kisi in (veli, ogrenci):
        db.refresh(kisi)
        print(
            f"{kisi.kullanici_adi:8} rol={kisi.rol:8} profil_id={kisi.profil_id} "
            f"erisim={sorted(yetki.erisilebilir_profil_idleri(db, kisi))}"
        )

    satirlar = db.execute(text("SELECT * FROM veli_ogrenci")).mappings().all()
    print("veli_ogrenci:", [dict(s) for s in satirlar])
