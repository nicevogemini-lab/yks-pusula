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

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..data import BECERI_ETIKET, alan_ders_kodlari
from ..models import (
    Calisma,
    Deneme,
    DenemeKonu,
    DenemeSonuc,
    Ders,
    Konu,
    KonuDurum,
    PlanItem,
    Profil,
)
from . import sinif as sinif_servisi
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
    """Denemelerde konu bazlı doğru/yanlış/boş toplamı (konu kanıtı)."""
    deneme_idleri = list(
        db.execute(select(Deneme.id).where(Deneme.profil_id == profil_id)).scalars()
    )
    if not deneme_idleri:
        return {}
    sonuc: dict[int, dict] = {}
    for kayit in db.execute(
        select(DenemeKonu).where(DenemeKonu.deneme_id.in_(deneme_idleri))
    ).scalars():
        satir = sonuc.setdefault(
            kayit.konu_id, {"dogru": 0, "yanlis": 0, "bos": 0, "deneme": 0}
        )
        satir["dogru"] += kayit.dogru or 0
        satir["yanlis"] += kayit.yanlis or 0
        satir["bos"] += kayit.bos or 0
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
        d_dogru = deneme.get("dogru", 0)
        d_yanlis = deneme.get("yanlis", 0)
        d_bos = deneme.get("bos", 0)
        d_toplam = d_dogru + d_yanlis + d_bos
        d_sinav = deneme.get("deneme", 0)

        if c_toplam >= KONU_VERI_ESIGI or d_dogru + d_yanlis:
            # Denemede işaretlenen konu satırı da konu için gerçek kanıttır;
            # yalnız yanlış işaretlenmiş eski kayıtlar tamamen yanlış sayılır.
            toplam_soru = c_toplam + d_toplam
            # Laplace düzeltmesi: az soruda %0 / %100 gibi uçlara savrulmayı önler
            basari = (c_dogru + d_dogru + 1) / (toplam_soru + 2)
            if d_dogru + d_yanlis and c_toplam:
                kaynak = "deneme+çalışma"
            elif d_dogru + d_yanlis:
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
                "kapsam_disi": sinif_servisi.kapsam_disi(konu.sinif, profil.sinif),
                "beklenen_soru": round(beklenen, 2),
                "agirlik_payi": round(pay, 4),
                "basari": round(basari, 3),
                "basari_yuzde": round(basari * 100),
                "kaynak": kaynak,
                "durum": durum_adi,
                "guven": guven,
                "calisma_dogru": c_dogru,
                "calisma_yanlis": c_yanlis,
                "deneme_dogru": d_dogru,
                "deneme_yanlis": d_yanlis,
                "deneme_bos": d_bos,
                "deneme_sayisi": d_sinav,
                "etkin_puan": round(etkin, 2),
            }
        )

    satirlar.sort(key=lambda s: (-s["etkin_puan"], s["ders_kod"], s["sira"]))
    return satirlar


def _konu_kaniti(konu: dict) -> bool:
    """Konuya özgü veri var mı? (denemede doğru/yanlış işareti ya da çalışma)"""
    return bool(konu["deneme_dogru"] + konu["deneme_yanlis"]) or (
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
        # Kapsam dışı konu analizde görünür ama plan önceliğine girmez
        if konu.get("kapsam_disi"):
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


def mufredat_yorumu(
    db: Session, profil: Profil, konular: list[dict] | None = None, sinir: int = 40
) -> dict:
    """Açık konuları beceri, ağırlık, ön koşul ve deneme kanıtıyla yorumlar.

    Ders bazında "müfredat açığı" sayısı da buradan çıkar; analiz sayfasındaki
    yorum kartı ile plan uyumu aynı veriyi kullanır.
    """
    satirlar = konular if konular is not None else konu_tablosu(db, profil)
    kayitlar = {
        k.id: k
        for k in db.execute(
            select(Konu).where(Konu.ders_kod.in_(alan_ders_kodlari(profil.alan)))
        ).scalars()
    }
    kod_map = {k.kod: k for k in kayitlar.values()}
    durumlar = _durum_haritasi(db, profil.id)

    acik = [
        s
        for s in satirlar
        if s["beklenen_soru"] > 0
        and s["basari"] < KONU_ACIK_ESIGI
        and _konu_kaniti(s)
        and not s.get("kapsam_disi")
    ]
    acik.sort(key=lambda s: -s["etkin_puan"])

    def onkosul_durumu(ham: str) -> list[dict]:
        sonuc = []
        for kod in [k for k in (ham or "").split(",") if k]:
            kayit = kod_map.get(kod)
            durum = durumlar.get(kayit.id) if kayit else None
            sonuc.append(
                {
                    "kod": kod,
                    "ad": kayit.ad if kayit else kod,
                    "durum": durum.durum if durum else "yok",
                    "hazir": bool(durum and durum.durum in {"tamam", "tekrar"}),
                }
            )
        return sonuc

    yorumlanan = []
    for s in acik[: max(1, sinir)]:
        kayit = kayitlar.get(s["id"])
        beceriler = [b for b in ((kayit.beceri if kayit else "") or "").split(",") if b]
        onkosullar = onkosul_durumu(kayit.onkosul if kayit else "")
        yorumlanan.append(
            {
                "konu_id": s["id"],
                "konu": s["ad"],
                "ders_kod": s["ders_kod"],
                "ders": s["ders_ad"],
                "sinav": s["sinav"],
                "renk": s["renk"],
                "sinif": s["sinif"],
                "beceri": beceriler,
                "beceri_etiket": [BECERI_ETIKET.get(b, b) for b in beceriler],
                "agirlik": kayit.agirlik if kayit else 0,
                "beklenen_soru": s["beklenen_soru"],
                "etkin_puan": s["etkin_puan"],
                "basari_yuzde": s["basari_yuzde"],
                "deneme_dogru": s["deneme_dogru"],
                "deneme_yanlis": s["deneme_yanlis"],
                "deneme_bos": s["deneme_bos"],
                "kaynak": s["kaynak"],
                "onkosul": onkosullar,
                "onkosul_hazir": all(o["hazir"] for o in onkosullar),
                "tahmini_dk": kayit.sure_dk if kayit else 0,
            }
        )

    # Ders bazında müfredat açığı: kapsam içi konu sayısına göre açık oranı
    dersler: dict[str, dict] = {}
    for s in satirlar:
        ders = dersler.setdefault(
            s["ders_kod"],
            {
                "ders_kod": s["ders_kod"],
                "ders": s["ders_ad"],
                "sinav": s["sinav"],
                "renk": s["renk"],
                "konu_sayisi": 0,
                "acik_sayisi": 0,
                "kapsam_disi": 0,
            },
        )
        if s.get("kapsam_disi"):
            ders["kapsam_disi"] += 1
            continue
        ders["konu_sayisi"] += 1
    acik_idler = {s["id"] for s in acik}
    for s in satirlar:
        if s["id"] in acik_idler:
            dersler[s["ders_kod"]]["acik_sayisi"] += 1
    ders_listesi = []
    for ders in dersler.values():
        ders["acik_oran"] = (
            round(100 * ders["acik_sayisi"] / ders["konu_sayisi"])
            if ders["konu_sayisi"]
            else 0
        )
        ders_listesi.append(ders)
    ders_listesi.sort(key=lambda d: (-d["acik_sayisi"], d["ders_kod"]))

    kapsam_ici = sum(d["konu_sayisi"] for d in ders_listesi)
    etiket = sinif_servisi.kapsam_etiketi(profil.sinif)
    yorum = (
        f"{etiket}: {kapsam_ici} konunun {len(acik)} tanesi açık. "
        if kapsam_ici
        else "Kapsam içinde konu bulunamadı. "
    )
    if ders_listesi and ders_listesi[0]["acik_sayisi"]:
        ilk = ders_listesi[0]
        yorum += f"En büyük açık {ilk['ders']} dersinde ({ilk['acik_sayisi']} konu)."
    eksik_onkosul = sum(1 for k in yorumlanan if not k["onkosul_hazir"])
    if eksik_onkosul:
        yorum += f" {eksik_onkosul} konunun ön koşulu henüz tamamlanmadı."

    return {
        "kapsam_etiketi": etiket,
        "kapsam_ici_konu": kapsam_ici,
        "acik_konu_sayisi": len(acik),
        "dersler": ders_listesi,
        "konular": yorumlanan,
        "yorum": yorum,
    }


def plan_uyumu(
    db: Session, profil: Profil, gun: int = 7, konular: list[dict] | None = None
) -> dict:
    """Yaklaşan plan maddelerini açık konularla karşılaştırır.

    ``planda_olmayan_aciklar``: açık olduğu halde planda hiç bloğu olmayan konular.
    ``planda_gereksiz``: planda yer alan ama açık olmayan, üstelik sağlam
    bilinen (tekrar gerektirmeyen) konular.
    """
    gun = max(1, min(30, gun))
    bugun = date.today()
    bitis = bugun + timedelta(days=gun - 1)
    satirlar = konular if konular is not None else konu_tablosu(db, profil)
    acik = {
        s["id"]: s
        for s in satirlar
        if s["beklenen_soru"] > 0
        and s["basari"] < KONU_ACIK_ESIGI
        and _konu_kaniti(s)
        and not s.get("kapsam_disi")
    }
    durumlar = _durum_haritasi(db, profil.id)

    maddeler = list(
        db.execute(
            select(PlanItem).where(
                PlanItem.profil_id == profil.id,
                PlanItem.tarih >= bugun,
                PlanItem.tarih <= bitis,
            )
        ).scalars()
    )
    plan_konulari: dict[int, PlanItem] = {}
    gereksiz = []
    for madde in maddeler:
        if madde.konu_id is None:
            continue
        plan_konulari.setdefault(madde.konu_id, madde)
        if madde.konu_id in acik:
            continue
        durum = durumlar.get(madde.konu_id)
        if durum and durum.durum == "tamam" and (durum.guven or 0) >= 4:
            gereksiz.append(
                {
                    "madde_id": madde.id,
                    "baslik": madde.baslik,
                    "ders_kod": madde.ders_kod,
                    "tarih": madde.tarih.isoformat(),
                    "sure_dk": madde.sure_dk,
                    "tur": madde.tur,
                }
            )

    eksikler = [
        {
            "konu_id": s["id"],
            "konu": s["ad"],
            "ders_kod": s["ders_kod"],
            "ders": s["ders_ad"],
            "renk": s["renk"],
            "sinif": s["sinif"],
            "etkin_puan": s["etkin_puan"],
            "basari_yuzde": s["basari_yuzde"],
        }
        for s in sorted(acik.values(), key=lambda s: -s["etkin_puan"])
        if s["id"] not in plan_konulari
    ]
    kapsanan = len(set(acik) & set(plan_konulari))
    kapsam_orani = round(100 * kapsanan / len(acik)) if acik else 100

    yorum = (
        f"Önümüzdeki {gun} günde {len(plan_konulari)} konu planda. "
        f"Açık konuların %{kapsam_orani}'i programda yer alıyor."
    )
    if eksikler:
        yorum += f" {len(eksikler)} açık konu planda yok."
    if gereksiz:
        yorum += f" {len(gereksiz)} blok artık tekrar gerektirmeyen konularda."

    return {
        "gun": gun,
        "baslangic": bugun.isoformat(),
        "bitis": bitis.isoformat(),
        "plan_madde_sayisi": len(maddeler),
        "plan_konu_sayisi": len(plan_konulari),
        "acik_konu_sayisi": len(acik),
        "kapsanan_acik": kapsanan,
        "kapsam_orani": kapsam_orani,
        "planda_olmayan_aciklar": eksikler[:10],
        "planda_gereksiz": gereksiz[:10],
        "yorum": yorum,
    }


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
            and not k.get("kapsam_disi")
        ),
        "mufredat": mufredat_yorumu(db, profil, konular),
        "plan_uyumu": plan_uyumu(db, profil, 7, konular),
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
