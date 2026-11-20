# -*- coding: utf-8 -*-
"""Canli veritabanindaki hesap ve profil iliskilerini okur (gecici, salt okunur)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

KOK = Path(__file__).resolve().parent
load_dotenv(KOK / ".env.bulut")
adres = os.getenv("PUSULA_DATABASE_URL", "").strip()
if not adres:
    sys.exit("PUSULA_DATABASE_URL yok")

motor = create_engine(adres)


def yaz(baslik: str, sorgu: str) -> None:
    print(f"\n== {baslik}")
    with motor.connect() as bag:
        for satir in bag.execute(text(sorgu)).mappings():
            print("  ", dict(satir))


yaz(
    "kullanicilar",
    "SELECT id, kullanici_adi, ad_soyad, rol, profil_id, "
    "length(coalesce(sifre_hash,'')) AS hash_uzunluk FROM kullanicilar ORDER BY id",
)
yaz("profiller", "SELECT * FROM profiller ORDER BY id")
yaz("veli_ogrenci", "SELECT * FROM veli_ogrenci")
yaz("plan_maddeleri ozet", "SELECT profil_id, count(*) FROM plan_maddeleri GROUP BY profil_id")
yaz("ayarlar anahtarlari", "SELECT anahtar, length(deger) AS uzunluk FROM ayarlar ORDER BY anahtar")
motor.dispose()
