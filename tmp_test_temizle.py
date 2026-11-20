# -*- coding: utf-8 -*-
"""AI testinin biraktigi gecici kayitlari dogru FK sirasina gore siler (gecici)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import text

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

KOK = Path(__file__).resolve().parent
load_dotenv(KOK / ".env.bulut")
adres = os.getenv("PUSULA_DATABASE_URL", "").strip()

PROFILLER = "SELECT id, ad, sinif FROM profiller ORDER BY id"
KULLANICILAR = "SELECT id, kullanici_adi, rol FROM kullanicilar ORDER BY id"

from sqlalchemy import create_engine  # noqa: E402

motor = create_engine(adres)
with motor.begin() as bag:
    gecici = bag.execute(
        text("SELECT id FROM profiller WHERE ad LIKE '_Test%' OR ad LIKE 'Test Ogrenci%'")
    ).scalars().all()
    print("gecici profiller:", gecici)
    for pid in gecici:
        bag.execute(
            text(
                "DELETE FROM deneme_konulari WHERE deneme_id IN "
                "(SELECT id FROM denemeler WHERE profil_id = :p)"
            ),
            {"p": pid},
        )
        bag.execute(
            text(
                "DELETE FROM deneme_sonuclari WHERE deneme_id IN "
                "(SELECT id FROM denemeler WHERE profil_id = :p)"
            ),
            {"p": pid},
        )
        for tablo in ("denemeler", "plan_maddeleri", "calismalar", "konu_durumlari", "ai_mesajlari", "veli_ogrenci"):
            bag.execute(text(f"DELETE FROM {tablo} WHERE profil_id = :p"), {"p": pid})
        bag.execute(text("DELETE FROM profiller WHERE id = :p"), {"p": pid})
        bag.execute(text("DELETE FROM ayarlar WHERE anahtar LIKE :a"), {"a": f"degerlendirme_{pid}%"})

    bag.execute(text("DELETE FROM kullanicilar WHERE kullanici_adi LIKE :k"), {"k": "_test%"})

with motor.connect() as bag:
    print("\nprofiller:", bag.execute(text(PROFILLER)).all())
    print("kullanicilar:", bag.execute(text(KULLANICILAR)).all())
    print("denemeler:", bag.execute(text("SELECT count(*) FROM denemeler")).scalar())
    print("veli_ogrenci:", bag.execute(text("SELECT * FROM veli_ogrenci")).all())
    print("ayarlar:", bag.execute(text("SELECT anahtar FROM ayarlar ORDER BY anahtar")).scalars().all())
    print("plan_maddeleri:", bag.execute(text("SELECT profil_id, count(*) FROM plan_maddeleri GROUP BY profil_id")).all())
motor.dispose()
