# -*- coding: utf-8 -*-
"""Konu ağırlığı ve deneme analizi.

İki katman birleştirilir:

1. **Sınav ağırlığı (blueprint)** — dersin YKS'deki soru sayısı, konuların
   ``Konu.agirlik`` (1-3 soru yoğunluğu) değerine göre paylaştırılır. Böylece
   her konunun gerçek sınavdaki **beklenen soru sayısı** çıkar.
2. **Öğrenci başarısı** — denemelerdeki doğru/yanlış/boş toplamı ders bazında,
   çalışma günlüğündeki doğru/yanlış ise konu bazında başarı oranına çevrilir.
   Denemede yanlış yapılan konu işaretlenmişse (``DenemeKonu``) o konu da
   kanıt sayılır; "açık konu" tablosu ders adıyla sınırlı kalmaz.

``etkin_puan = beklenen_soru × (1 - başarı) × hedef çarpanı``

Puanı yüksek konu "bu konuyu çalışırsan bu hafta en çok net kazanırsın"
demektir; günlük/haftalık/aylık programlar bu sıraya göre kurulur.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..data import alan_ders_kodlari
from ..models import Calisma, Deneme, DenemeKonu, DenemeSonuc, Ders, Konu, KonuDurum, Profil
from .hedef import ders_agirliklari, hedef_ozeti

# Konu bazında yorum yapmak için gereken en az soru sayısı
KONU_VERI_ESIGI = 4
# Başarısı bu oranın altında kalan konu "açık konu" sayılır
KONU_ACIK_ESIGI = 0.70
# Açık konu tablosunda ders başına gösterilecek konu ve ders sayısı
KONU_ACIK_DERS_BASI = 3
KONU_ACIK_DERS_SAYISI = 6


def _sinirla(deger: float, alt: float, ust: float) -> float:
    return max(alt, min(ust, deger))


def _seviye(basari: float | None) -> str:
    if basari is None:
        return "veri yok"
    if basari < 0.45:
        return "zayıf"
    if basari < 0.70:
        return "orta"
    return "iyi"


def _deneme_toplamlari(db: Session, profil_id: int) -> dict[str, dict]:
    """Profilin tüm denemelerindeki ders bazlı doğru/yanlış/boş toplamı."""
    deneme_idleri = list(
        db.execute(select(Deneme.id).where(Deneme.profil_id == profil_id)).scalars()
    )
    if not deneme_idleri:
        return {}

    toplam: dict[str, dict] = {}
    for sonuc in db.execute(
        select(DenemeSonuc).where(DenemeSonuc.deneme_id.in_(deneme_idleri))
    ).scalars():
        satir = toplam.setdefault(
            sonuc.ders_kod, {"deneme": 0, "dogru": 0, "yanlis": 0, "bos": 0}
        )
        satir["deneme"] += 1
        satir["dogru"] += sonuc.dogru or 0
        satir["yanlis"] += sonuc.yanlis or 0
        satir["bos"] += sonuc.bos or 0
    return toplam


def _calisma_konulari(db: Session, profil_id: int) -> dict[int, dict]:
    """Çalışma günlüğünden konu bazlı doğru/yanlış toplamı."""
    sonuc: dict[int, dict] = {}
    for kayit in db.execute(
        select(Calisma).where(Calisma.profil_id == profil_id, Calisma.konu_id.is_not(None))
    ).scalars():
        satir = sonuc.setdefault(kayit.konu_id, {"dogru": 0, "yanlis": 0, "sure_dk": 0})
        satir["dogru"] += kayit.dogru or 0
        satir["yanlis"] += kayit.yanlis or 0
        satir["sure_dk"] += kayit.sure_dk or 0
    return sonuc


def _deneme_konu_verisi(db: Session, profil_id: int) -> dict[int, dict]:
    """Denemelerde yanlış yapılan konuların toplamı (konu bazlı kanıt)."""
    deneme_idleri = list(
        db.execute(select(Deneme.id).where(Deneme.profil_id == profil_id)).scalars()
    )
    if not deneme_idleri:
        return {}
    sonuc: dict[int, dict] = {}
    for kayit in db.execute(
        select(DenemeKonu).where(DenemeKonu.deneme_id.in_(deneme_idleri))
    ).scalars():
        satir = sonuc.setdefault(kayit.konu_id, {"yanlis": 0, "deneme": 0})
        satir["yanlis"] += kayit.yanlis or 1
        satir["deneme"] += 1
    return sonuc


def _durum_haritasi(db: Session, profil_id: int) -> dict[int, KonuDurum]:
    return {
        d.konu_id: d
        for d in db.execute(
            select(KonuDurum).where(KonuDurum.profil_id == profil_id)
        ).scalars()
    }


def ders_tablosu(db: Session, profil: Profil) -> list[dict]:
    """Denemelerdeki ders bazlı doğru/yanlış tablosu."""
    dersler = {d.kod: d for d in db.execute(select(Ders)).scalars()}
    toplamlar = _deneme_toplamlari(db, profil.id)
    satirlar: list[dict] = []

    for kod in sorted(
        alan_ders_kodlari(profil.alan),
        key=lambda k: (dersler[k].sira if k in dersler else 99, k),
    ):
        ders = dersler.get(kod)
        if ders is None:
            continue
        t = toplamlar.get(kod, {})
        dogru = t.get("dogru", 0)
        yanlis = t.get("yanlis", 0)
        bos = t.get("bos", 0)
        soru = dogru + yanlis + bos
        basari = dogru / soru if soru else None
        net = round(dogru - yanlis / 4, 2)
        satirlar.append(
            {
                "kod": kod,
                "ad": ders.ad,
                "sinav": ders.sinav,
                "renk": ders.renk,
                "soru_sayisi": ders.soru_sayisi,
                "deneme_sayisi": t.get("deneme", 0),
                "dogru": dogru,
                "yanlis": yanlis,
                "bos": bos,
                "net": net,
                "basari": round(basari, 3) if basari is not None else None,
                "basari_yuzde": round(basari * 100) if basari is not None else None,
                "net_orani": (
                    round(_sinirla(net / ders.soru_sayisi, 0.0, 1.0), 3)
                    if ders.soru_sayisi
                    else None
                ),
                "seviye": _seviye(basari),
            }
        )
    return satirlar


def konu_tablosu(
    db: Session, profil: Profil, ders_satirlari: list[dict] | None = None
) -> list[dict]:
    """Konuların beklenen soru sayısı + başarısı + etkin puanı."""
    ders_satirlari = ders_satirlari if ders_satirlari is not None else ders_tablosu(db, profil)
    ders_map = {d["kod"]: d for d in ders_satirlari}
    konular = list(
        db.execute(select(Konu).where(Konu.ders_kod.in_(alan_ders_kodlari(profil.alan)))).scalars()
    )
    durumlar = _durum_haritasi(db, profil.id)
    calismalar = _calisma_konulari(db, profil.id)
    deneme_konulari = _deneme_konu_verisi(db, profil.id)
    agirliklar = ders_agirliklari(db, profil)
    en_yuksek_agirlik = max(agirliklar.values()) if agirliklar else 0.0

    # Dersin toplam yoğunluğu: beklenen soru sayısı bu orana göre paylaştırılır
    ders_agirlik_toplami: dict[str, int] = {}
    for konu in konular:
        ders_agirlik_toplami[konu.ders_kod] = (
            ders_agirlik_toplami.get(konu.ders_kod, 0) + max(1, konu.agirlik)
        )

    satirlar: list[dict] = []
    for konu in konular:
        ders = ders_map.get(konu.ders_kod)
        if ders is None:
            continue

        pay = max(1, konu.agirlik) / max(1, ders_agirlik_toplami.get(konu.ders_kod, 1))
        beklenen = pay * (ders["soru_sayisi"] or 0)

        durum = durumlar.get(konu.id)
        durum_adi = durum.durum if durum else "yok"
        guven = durum.guven if durum else 0

        calisma = calismalar.get(konu.id) or {}
        c_dogru = calisma.get("dogru", 0)
        c_yanlis = calisma.get("yanlis", 0)
        c_toplam = c_dogru + c_yanlis

        deneme = deneme_konulari.get(konu.id) or {}
        d_yanlis = deneme.get("yanlis", 0)
        d_sinav = deneme.get("deneme", 0)

        if c_toplam >= KONU_VERI_ESIGI or d_yanlis:
            # Denemede işaretlenen yanlış da konu için gerçek kanıttır
            toplam_soru = c_toplam + d_yanlis
            # Laplace düzeltmesi: az soruda %0 / %100 gibi uçlara savrulmayı önler
            basari = (c_dogru + 1) / (toplam_soru + 2)
            if d_yanlis and c_toplam:
                kaynak = "deneme+çalışma"
            elif d_yanlis:
                kaynak = "deneme"
            else:
                kaynak = "çalışma"
        elif ders["basari"] is not None:
            basari = float(ders["basari"])
            kaynak = "deneme"
        else:
            basari = 0.5
            kaynak = "tahmin"

        if durum_adi == "tamam" and guven >= 4:
            basari += 0.08
        elif durum_adi == "tamam":
            basari += 0.03
        elif durum_adi == "tekrar":
            basari -= 0.08
        basari = _sinirla(basari, 0.05, 0.95)

        carpan = (
            0.7 + 0.9 * (agirliklar.get(konu.ders_kod, 0.0) / en_yuksek_agirlik)
            if en_yuksek_agirlik
            else 1.0
        )
        etkin = beklenen * (1 - basari) * carpan

        satirlar.append(
            {
                "id": konu.id,
                "kod": konu.kod,
                "ad": konu.ad,
                "ders_kod": konu.ders_kod,
                "ders_ad": ders["ad"],
                "sinav": ders["sinav"],
                "renk": ders["renk"],
                "sinif": konu.sinif,
                "sira": konu.sira,
                "beklenen_soru": round(beklenen, 2),
                "agirlik_payi": round(pay, 4),
                "basari": round(basari, 3),
                "basari_yuzde": round(basari * 100),
                "kaynak": kaynak,
                "durum": durum_adi,
                "guven": guven,
                "calisma_dogru": c_dogru,
                "calisma_yanlis": c_yanlis,
                "deneme_yanlis": d_yanlis,
                "deneme_sayisi": d_sinav,
                "etkin_puan": round(etkin, 2),
            }
        )

    satirlar.sort(key=lambda s: (-s["etkin_puan"], s["ders_kod"], s["sira"]))
    return satirlar


def _konu_kaniti(konu: dict) -> bool:
    """Konuya özgü veri var mı? (denemede işaretlenen yanlış ya da çalışma)"""
    return bool(konu["deneme_yanlis"]) or (
        konu["calisma_dogru"] + konu["calisma_yanlis"] >= KONU_VERI_ESIGI
    )


def konu_aciklari(
    konular: list[dict],
    esik: float = KONU_ACIK_ESIGI,
    ders_basi: int = KONU_ACIK_DERS_BASI,
    ders_sayisi: int = KONU_ACIK_DERS_SAYISI,
) -> list[dict]:
    """Başarısı eşiğin altındaki konuları derslere göre gruplar.

    ``konular`` etkin puana göre sıralı gelir; bu yüzden her dersin en çok net
    kazandıracak açık konuları başa düşer.
    """
    gruplar: dict[str, dict] = {}
    for konu in konular:
        if konu["beklenen_soru"] <= 0 or konu["basari"] >= esik:
            continue
        # Ders ortalamasından türetilen tahmin, konu ayrımı taşımaz; açık
        # konu listesine yalnız konuya özgü kanıt (deneme işareti/çalışma) girer.
        if not _konu_kaniti(konu):
            continue
        grup = gruplar.setdefault(
            konu["ders_kod"],
            {
                "ders_kod": konu["ders_kod"],
                "ders": konu["ders_ad"],
                "sinav": konu["sinav"],
                "renk": konu["renk"],
                "acik_sayisi": 0,
                "konular": [],
            },
        )
        grup["acik_sayisi"] += 1
        if len(grup["konular"]) < ders_basi:
            grup["konular"].append(
                {
                    "konu_id": konu["id"],
                    "konu": konu["ad"],
                    "basari_yuzde": konu["basari_yuzde"],
                    "beklenen_soru": konu["beklenen_soru"],
                    "etkin_puan": konu["etkin_puan"],
                    "deneme_yanlis": konu["deneme_yanlis"],
                    "durum": konu["durum"],
                    "kaynak": konu["kaynak"],
                }
            )
    return sorted(
        gruplar.values(), key=lambda g: -max(k["etkin_puan"] for k in g["konular"])
    )[:ders_sayisi]


def analiz_ozeti(db: Session, profil: Profil) -> dict:
    """Deneme tablosu + konu ağırlıkları + en çok kazandıracak konular."""
    dersler = ders_tablosu(db, profil)
    konular = konu_tablosu(db, profil, dersler)
    hedef = hedef_ozeti(db, profil)
    deneme_sayisi = int(
        db.execute(
            select(func.count(Deneme.id)).where(Deneme.profil_id == profil.id)
        ).scalar()
        or 0
    )

    return {
        "profil": profil.to_dict(),
        "hedef": hedef,
        "deneme_sayisi": deneme_sayisi,
        "dersler": dersler,
        "konular": konular,
        "en_cok_kazanc": konular[:8],
        "konu_aciklari": konu_aciklari(konular),
        "acik_konu_sayisi": sum(
            1
            for k in konular
            if k["beklenen_soru"] > 0
            and k["basari"] < KONU_ACIK_ESIGI
            and _konu_kaniti(k)
        ),
        "toplam_beklenen_soru": round(sum(k["beklenen_soru"] for k in konular), 1),
        "toplam_etkin_puan": round(sum(k["etkin_puan"] for k in konular), 1),
        "veri_notu": (
            f"Beklenen soru sayısı dersin YKS soru sayısından, konuların 1-3 arası "
            f"soru yoğunluğuna göre paylaştırılır. Başarı oranı denemelerdeki "
            f"doğru/yanlış toplamından; konu bazında çalışma günlüğü ya da denemede "
            f"işaretlenen yanlış konular kullanılır."
        ),
    }


def en_cok_kazanc(db: Session, profil: Profil, limit: int = 6) -> list[dict]:
    """Koç bağlamı için en yüksek etkin puanlı konular."""
    satirlar = konu_tablosu(db, profil)
    return [
        {
            "konu": s["ad"],
            "ders": s["ders_ad"],
            "beklenen_soru": s["beklenen_soru"],
            "basari_yuzde": s["basari_yuzde"],
            "etkin_puan": s["etkin_puan"],
        }
        for s in satirlar[:limit]
    ]
