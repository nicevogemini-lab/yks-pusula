# -*- coding: utf-8 -*-
"""Canlida Gemini deneme analizini uctan uca dener (gecici).

Geçici yonetici hesabi ve geçici ogrenci profili acar, HTTP uzerinden gercek
akis calistirir (giris -> AI test -> deneme kaydi -> AI degerlendirme -> soru
uretimi), sonunda actigi tum kayitlari siler.
"""
from __future__ import annotations

import os
import sys
import time
import traceback
from pathlib import Path

import httpx
from dotenv import load_dotenv
from sqlalchemy import text

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

KOK = Path(__file__).resolve().parent
load_dotenv(KOK / ".env.bulut")
os.environ.setdefault("PUSULA_DATABASE_URL", os.getenv("PUSULA_DATABASE_URL", "").strip())

from app import auth, yetki  # noqa: E402
from app.api import _profil_kaydet  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    AiMesaj,
    Ayar,
    Calisma,
    Deneme,
    DenemeKonu,
    DenemeSonuc,
    KonuDurum,
    Kullanici,
    PlanItem,
    Profil,
    VeliOgrenci,
)

TABAN = "https://yks-pusula.onrender.com"
KULLANICI = "_test_yonetici"
SIFRE = "GeciciTest!2026"
PROFIL_ADI = "_Test Ogrenci"


def hazirla() -> tuple[int, int]:
    """Geçici yonetici ve ogrenci profilini olusturur."""
    with SessionLocal() as db:
        kisi = db.query(Kullanici).filter(Kullanici.kullanici_adi == KULLANICI).first()
        if kisi is None:
            kisi = Kullanici(
                kullanici_adi=KULLANICI,
                ad_soyad="Gecici Test",
                rol="yonetici",
                sifre_hash=auth.sifre_ozetle(SIFRE),
            )
            db.add(kisi)
            db.commit()
            db.refresh(kisi)

        profil = db.query(Profil).filter(Profil.ad == PROFIL_ADI).first()
        if profil is None:
            profil = _profil_kaydet(db, PROFIL_ADI, 11, "sayisal", gunluk_hedef_dk=180)
            db.commit()
            db.refresh(profil)
        return kisi.id, profil.id


def temizle(kullanici_id: int, profil_id: int) -> None:
    """Geçici kayitlari siler (profil_sil ile ayni temizlik + ayar anahtari)."""
    with SessionLocal() as db:
        denemeler = db.query(Deneme).filter(Deneme.profil_id == profil_id).all()
        for deneme in denemeler:
            db.query(DenemeKonu).filter(DenemeKonu.deneme_id == deneme.id).delete()
            db.query(DenemeSonuc).filter(DenemeSonuc.deneme_id == deneme.id).delete()
            db.delete(deneme)
        for model in (PlanItem, Calisma, KonuDurum, AiMesaj):
            db.query(model).filter(model.profil_id == profil_id).delete()
        db.query(VeliOgrenci).filter(VeliOgrenci.profil_id == profil_id).delete()
        db.query(Profil).filter(Profil.id == profil_id).delete()
        db.query(Kullanici).filter(Kullanici.id == kullanici_id).delete()
        db.commit()
        for anahtar in (f"degerlendirme_{profil_id}", f"degerlendirme_{profil_id}_zaman"):
            db.execute(text("DELETE FROM ayarlar WHERE anahtar = :a"), {"a": anahtar})
        db.commit()
        kalan_ayar = db.get(Ayar, f"degerlendirme_{profil_id}")
        print(f"temizlik: deneme={len(denemeler)} ayar_kaldi={bool(kalan_ayar)}")


def calistir(kullanici_id: int, profil_id: int) -> int:
    hatalar = 0
    with httpx.Client(timeout=180, follow_redirects=True) as web:
        giris = web.post(f"{TABAN}/giris", data={"kullanici": KULLANICI, "sifre": SIFRE})
        print(f"1) giris: {giris.status_code}")
        if "api" in giris.headers.get("content-type", "") or giris.status_code >= 400:
            print("   govde:", giris.text[:120])
            return 1

        ben = web.get(f"{TABAN}/api/oturum")
        rol = ben.json().get("rol") if ben.status_code == 200 else None
        print(f"2) oturum: {ben.status_code} rol={rol}")
        hatalar += 0 if rol == "yonetici" else 1

        durum = web.get(f"{TABAN}/api/ai/durum")
        print(f"3) ai/durum: {durum.status_code} {durum.text[:120]}")

        basla = time.time()
        test = web.post(f"{TABAN}/api/ai/test", json={"anahtar": "", "model": ""})
        sure = time.time() - basla
        print(f"4) ai/test: {test.status_code} ({sure:.1f} sn) {test.text[:200]}")
        hatalar += 0 if test.status_code == 200 else 1

        deneme = web.post(
            f"{TABAN}/api/deneme",
            json={
                "profil_id": profil_id,
                "tur": "TYT",
                "ad": "Gecici dogrulama denemesi",
                "sure_dk": 165,
                "sonuclar": [
                    {"ders_kod": "TYT-TUR", "dogru": 28, "yanlis": 6, "bos": 6},
                    {"ders_kod": "TYT-MAT", "dogru": 18, "yanlis": 9, "bos": 13},
                    {"ders_kod": "TYT-FEN", "dogru": 12, "yanlis": 6, "bos": 2},
                ],
            },
        )
        print(f"5) deneme kaydi: {deneme.status_code} {deneme.text[:120]}")
        hatalar += 0 if deneme.status_code in (200, 201) else 1

        basla = time.time()
        deger = web.post(f"{TABAN}/api/analiz/{profil_id}/degerlendir", params={"siklik": 7})
        sure = time.time() - basla
        govde = deger.json() if deger.status_code == 200 else {}
        print(f"6) AI degerlendirme: {deger.status_code} ({sure:.1f} sn)")
        yorum = (govde.get("yorum") or govde.get("metin") or govde.get("degerlendirme") or "")
        print(f"   anahtarlar: {list(govde)[:8]}")
        print(f"   yorum ilk 220: {str(yorum)[:220]}")
        hatalar += 0 if deger.status_code == 200 and yorum else 1

        kayit = web.get(f"{TABAN}/api/analiz/{profil_id}/degerlendirme")
        var = kayit.json().get("var") if kayit.status_code == 200 else None
        print(f"7) saklanan degerlendirme: {kayit.status_code} var={var}")
        hatalar += 0 if var else 1

        soru = web.post(f"{TABAN}/api/koc/{profil_id}/soru", params={"konu": "Türev", "adet": 1})
        sorular = soru.json().get("sorular", []) if soru.status_code == 200 else []
        print(f"8) soru uretimi: {soru.status_code} adet={len(sorular)}")
        if sorular:
            ilk = sorular[0]
            print(f"   soru: {str(ilk.get('soru', ''))[:120]}")
            print(f"   dogru cevap: {ilk.get('dogru_cevap')}")
        hatalar += 0 if sorular else 1
    return hatalar


def main() -> int:
    kullanici_id = profil_id = None
    try:
        kullanici_id, profil_id = hazirla()
        print(f"gecici kayitlar: kullanici={kullanici_id} profil={profil_id}\n")
        hatalar = calistir(kullanici_id, profil_id)
        print(f"\nhatali adim sayisi: {hatalar}")
        return 0 if hatalar == 0 else 1
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        return 1
    finally:
        if kullanici_id and profil_id:
            temizle(kullanici_id, profil_id)


if __name__ == "__main__":
    sys.exit(main())
