# -*- coding: utf-8 -*-
"""Hedef başarı sıralamasından ders bazlı net hedefleri üretir.

Mantık:

1. Öğrencinin **hedef sıralaması** (ör. 20.000) alanına göre yaklaşık bir
   **gereken net** çiftine çevrilir (TYT net, AYT net). Eşik değerleri gerçek
   YKS yerleştirme verilerinden türetilmiş yaklaşık değerlerdir; sıralama
   logaritmik ölçekte ara değerlenir.
2. Gereken netler, derslerin **soru sayısı payına** göre derslere dağıtılır.
   Böylece "TYT 90 net" gibi soyut bir hedef, "Matematik 24 net, Türkçe 30 net"
   gibi uygulanabilir hedeflere dönüşür.
3. Deneme sonuçlarındaki en iyi netlerle karşılaştırılır; **açık** (hedef −
   mevcut) ders bazında çıkar. Plan motoru bu açığı kullanır: açığı büyük ders,
   günlük planda daha çok blok alır.

Tüm değerler yaklaşıktır; programda "hedef" olarak sunulur, resmî puan iddiası
taşımaz.
"""
from __future__ import annotations

import math
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..data import ALAN_AYT_DERSLERI
from ..models import Deneme, DenemeSonuc, Ders, Profil

WSIRALAMA_VARSAYILAN = 100_000

# (sıralama, gereken TYT net, gereken AYT net) — yaklaşık eşikler
ESIKLER: dict[str, list[tuple[int, float, float]]] = {
    "sayisal": [
        (1_000, 105, 75),
        (5_000, 100, 70),
        (10_000, 96, 66),
        (20_000, 90, 60),
        (30_000, 85, 55),
        (50_000, 78, 48),
        (75_000, 72, 42),
        (100_000, 66, 36),
        (150_000, 58, 28),
        (200_000, 52, 22),
        (300_000, 43, 15),
        (500_000, 32, 8),
    ],
    "ea": [
        (1_000, 100, 72),
        (5_000, 96, 67),
        (10_000, 92, 62),
        (20_000, 86, 56),
        (30_000, 81, 51),
        (50_000, 74, 45),
        (75_000, 68, 39),
        (100_000, 62, 34),
        (150_000, 54, 26),
        (200_000, 48, 20),
        (300_000, 40, 14),
        (500_000, 30, 7),
    ],
    "sozel": [
        (1_000, 92, 68),
        (5_000, 86, 61),
        (10_000, 82, 56),
        (20_000, 76, 50),
        (30_000, 72, 46),
        (50_000, 65, 40),
        (75_000, 60, 35),
        (100_000, 55, 30),
        (150_000, 48, 23),
        (200_000, 43, 18),
        (300_000, 36, 12),
        (500_000, 27, 6),
    ],
}


def _arada(noktalar: list[tuple[int, float, float]], siralama: int) -> tuple[float, float]:
    """Sıralamayı logaritmik ölçekte ara değerler."""
    s = max(1, int(siralama))
    if s <= noktalar[0][0]:
        return float(noktalar[0][1]), float(noktalar[0][2])
    if s >= noktalar[-1][0]:
        return float(noktalar[-1][1]), float(noktalar[-1][2])
    for i in range(1, len(noktalar)):
        if s <= noktalar[i][0]:
            s0, t0, a0 = noktalar[i - 1]
            s1, t1, a1 = noktalar[i]
            oran = (math.log(s) - math.log(s0)) / (math.log(s1) - math.log(s0))
            return t0 + (t1 - t0) * oran, a0 + (a1 - a0) * oran
    return float(noktalar[-1][1]), float(noktalar[-1][2])


def hedef_netler(alan: str, siralama: int) -> tuple[float, float, bool]:
    """(tyt_net, ayt_net, varsayilan_mi) döndürür."""
    varsayilan = not siralama or siralama <= 0
    s = WSIRALAMA_VARSAYILAN if varsayilan else siralama
    tyt, ayt = _arada(ESIKLER.get(alan, ESIKLER["sayisal"]), s)
    return round(tyt, 1), round(ayt, 1), varsayilan


def _paylastir(dersler: list[Ders], toplam_net: float) -> dict[str, float]:
    """Toplam neti derslerin soru sayısı payına göre böler."""
    if not dersler:
        return {}
    sorular = sum(max(0, d.soru_sayisi or 0) for d in dersler)
    if sorular <= 0:
        return {d.kod: round(toplam_net / len(dersler), 2) for d in dersler}
    return {
        d.kod: round(toplam_net * max(0, d.soru_sayisi or 0) / sorular, 2)
        for d in dersler
    }


def _ders_haritasi(db: Session) -> dict[str, Ders]:
    return {d.kod: d for d in db.execute(select(Ders)).scalars()}


def ders_hedefleri(db: Session, profil: Profil) -> dict[str, float]:
    """Ders kodu -> hedef net (alan kapsamlı)."""
    tyt_net, ayt_net, _ = hedef_netler(profil.alan, profil.hedef_siralama)
    ders_map = _ders_haritasi(db)
    tyt_dersleri = [d for d in ders_map.values() if d.sinav == "TYT"]
    ayt_kodlari = set(ALAN_AYT_DERSLERI.get(profil.alan, []))
    ayt_dersleri = [d for kod, d in ders_map.items() if kod in ayt_kodlari]

    hedef: dict[str, float] = {}
    hedef.update(_paylastir(tyt_dersleri, tyt_net))
    hedef.update(_paylastir(ayt_dersleri, ayt_net))
    return hedef


def ders_agirliklari(db: Session, profil: Profil) -> dict[str, float]:
    """Plan motoru için ders ağırlıkları (toplamı 1).

    İki bileşen birleşir:

    * ``sqrt(hedef net)`` — dersin hedefteki payı; böylece ham netlerin çok
      eğimli dağılımı yumuşar ve düşük netli dersler tamamen dışlanmaz.
    * **açık oranı** — hedefin ne kadarı henüz kapatılmamış (0..1). Açığı tam
      olan ders ~1.6 kat ağırlık alır, hedefe ulaşmış ders 0.4 katında kalır
      (bakım/tekrar için programdan düşmez).

    Böylece çalışma programı doğrudan hedef sıralamaya bağlanır: öğrenci bir
    derste hedefe yaklaştıkça bloklar diğer açıklara kayar.
    """
    hedefler = ders_hedefleri(db, profil)
    if not hedefler:
        return {}
    mevcut = en_iyi_netler(db, profil.id)
    puanlar: dict[str, float] = {}
    for kod, hedef_net in hedefler.items():
        if hedef_net <= 0:
            puanlar[kod] = 0.05
            continue
        acik_orani = max(0.0, hedef_net - mevcut.get(kod, 0.0)) / hedef_net
        puanlar[kod] = math.sqrt(hedef_net) * (0.4 + 1.2 * min(1.0, acik_orani))
    toplam = sum(puanlar.values()) or 1.0
    return {kod: deger / toplam for kod, deger in puanlar.items()}


def en_iyi_netler(db: Session, profil_id: int) -> dict[str, float]:
    """Ders bazında şimdiye kadarki en iyi net."""
    satirlar = db.execute(
        select(DenemeSonuc)
        .join(Deneme, Deneme.id == DenemeSonuc.deneme_id)
        .where(Deneme.profil_id == profil_id)
    ).scalars()
    en_iyi: dict[str, float] = {}
    for satir in satirlar:
        onceki = en_iyi.get(satir.ders_kod, 0.0)
        en_iyi[satir.ders_kod] = max(onceki, float(satir.net))
    return en_iyi


def hedef_analizi(db: Session, profil: Profil) -> dict:
    """Panel, plan ve koç için tam hedef analizi."""
    tyt_hedef, ayt_hedef, varsayilan = hedef_netler(profil.alan, profil.hedef_siralama)
    hedefler = ders_hedefleri(db, profil)
    mevcut = en_iyi_netler(db, profil.id)
    ders_map = _ders_haritasi(db)

    satirlar = []
    for kod, hedef_net in hedefler.items():
        ders = ders_map.get(kod)
        mevcut_net = round(mevcut.get(kod, 0.0), 2)
        satirlar.append(
            {
                "ders_kod": kod,
                "ad": ders.ad if ders else kod,
                "sinav": ders.sinav if ders else "",
                "renk": ders.renk if ders else "#ea580c",
                "soru": ders.soru_sayisi if ders else 0,
                "sira": ders.sira if ders else 99,
                "hedef_net": hedef_net,
                "mevcut_net": mevcut_net,
                "acik": round(max(0.0, hedef_net - mevcut_net), 2),
                "oran": round(100 * mevcut_net / hedef_net) if hedef_net else 0,
            }
        )

    satirlar.sort(key=lambda s: (-s["acik"], s["sira"]))

    tyt_mevcut = round(
        sum(mevcut.get(k, 0.0) for k, d in ders_map.items() if d.sinav == "TYT"), 2
    )
    ayt_mevcut = round(
        sum(
            mevcut.get(k, 0.0)
            for k in ALAN_AYT_DERSLERI.get(profil.alan, [])
            if k in ders_map
        ),
        2,
    )

    toplam_hedef = round(sum(s["hedef_net"] for s in satirlar), 1)
    toplam_acik = round(sum(s["acik"] for s in satirlar), 1)
    kalan_gun = max(0, (profil.sinav_tarihi - date.today()).days)
    hafta = max(1, kalan_gun // 7)

    return {
        "alan": profil.alan,
        "hedef_siralama": int(profil.hedef_siralama or 0),
        "gecerli_hedef": WSIRALAMA_VARSAYILAN if varsayilan else int(profil.hedef_siralama),
        "varsayilan": varsayilan,
        "tyt_hedef_net": tyt_hedef,
        "ayt_hedef_net": ayt_hedef,
        "tyt_mevcut_net": tyt_mevcut,
        "ayt_mevcut_net": ayt_mevcut,
        "tyt_acik": round(max(0.0, tyt_hedef - tyt_mevcut), 1),
        "ayt_acik": round(max(0.0, ayt_hedef - ayt_mevcut), 1),
        "toplam_hedef_net": toplam_hedef,
        "toplam_acik_net": toplam_acik,
        "tamamlanma": round(100 * (toplam_hedef - toplam_acik) / toplam_hedef) if toplam_hedef else 0,
        "kalan_gun": kalan_gun,
        "haftalik_gereken_net": round(toplam_acik / hafta, 1) if hafta else 0,
        "dersler": satirlar,
        "oncelikli_dersler": [s["ad"] for s in satirlar if s["acik"] > 0][:3],
    }


def hedef_ozeti(db: Session, profil: Profil) -> dict:
    """Panel ve koç bağlamı için kısa özet."""
    analiz = hedef_analizi(db, profil)
    return {
        "hedef_siralama": analiz["gecerli_hedef"],
        "varsayilan": analiz["varsayilan"],
        "tyt_hedef_net": analiz["tyt_hedef_net"],
        "ayt_hedef_net": analiz["ayt_hedef_net"],
        "tyt_mevcut_net": analiz["tyt_mevcut_net"],
        "ayt_mevcut_net": analiz["ayt_mevcut_net"],
        "tyt_acik": analiz["tyt_acik"],
        "ayt_acik": analiz["ayt_acik"],
        "tamamlanma": analiz["tamamlanma"],
        "haftalik_gereken_net": analiz["haftalik_gereken_net"],
        "oncelikli_dersler": analiz["oncelikli_dersler"],
        "en_buyuk_aciklar": [
            {
                "ders": s["ad"],
                "ders_kod": s["ders_kod"],
                "renk": s["renk"],
                "hedef": s["hedef_net"],
                "mevcut": s["mevcut_net"],
                "acik": s["acik"],
            }
            for s in analiz["dersler"][:5]
            if s["acik"] > 0
        ],
    }
