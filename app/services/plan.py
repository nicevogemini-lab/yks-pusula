# -*- coding: utf-8 -*-
"""Plan üretimi ve konu önceliklendirme.

Öncelik motoru beş sinyali birleştirir:

1. **Hedef ağırlığı** (hedef sıralamadan türetilen ders payı) — hedefe göre en
   çok net kapatılması gereken ders öne çıkar.
2. **Sınav ağırlığı** (``Konu.agirlik``) — çok soru gelen konu önce gelir.
3. **Özgüven açığı** (``KonuDurum.guven``) — 0-5 arası; düşükse önce gelir.
4. **Durum** — "tekrar" ve "başlanmadı" konuları öne alınır.
5. **Ön koşul** — ön koşulu tamamlanmamış konu, tamamlanmış olanın arkasına düşer.

Günlük plan, derslerin hedef payına göre **kota** ile dağıtılır: hedef sıralama
20.000 ise matematik günde 2 blok alırken din kültürü 1 blok alır veya hiç
almaz. Böylece program öğrencinin hedefinden türetilir.

Her gün ayrıca **zorunlu iki blok** yazılır: matematik soruları ve paragraf
soruları. Matematik derslerinin kota payı ``MATEMATIK_KATSAYI`` ile yükseltilir.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..data import alan_ders_kodlari
from ..models import Ders, IslenenKonu, Konu, KonuDurum, PlanItem, Profil
from . import ders_programi as okul_programi
from . import sinif as sinif_servisi
from .analiz import konu_tablosu
from .hedef import ders_agirliklari, hedef_ozeti
from .program import (
    BLOK_AZAMI_DK,
    OKUL_GUNU_AZAMI_DK,
    gun_cercevesi,
    pencere_bosluklari,
    sigiyor_mu,
    zamanlari_yerlestir,
)

# Günlük programda ağırlığı artırılan matematik dersleri
MATEMATIK_DERSLER = ("TYT-MAT", "AYT-MAT")
MATEMATIK_KATSAYI = 1.35
# Her gün çözülecek paragraf konusu bu ada göre bulunur
PARAGRAF_ARAMA = "paragraf"
# Pencere sonunda bu kadar boşluk kalırsa ek soru bloğu yazılır
EK_BLOK_ESIGI_DK = 15
# Bir güne yazılabilecek en fazla ek blok sayısı
EK_BLOK_SAYISI = 3
# Ek bloklar günlük hedefi en fazla bu kadar dakika aşabilir
EK_BLOK_PAYI_DK = 30
# Okulda işlenen bir konunun tekrar/pekiştirme bloğuna ayrılan süre
OKUL_TEKRAR_DK = 25
# Bir güne yazılabilecek en fazla okul tekrarı bloğu
OKUL_TEKRAR_AZAMI = 3


def _durum_haritasi(db: Session, profil_id: int) -> dict[int, KonuDurum]:
    satirlar = db.execute(
        select(KonuDurum).where(KonuDurum.profil_id == profil_id)
    ).scalars()
    return {d.konu_id: d for d in satirlar}


def plan_agirliklari(db: Session, profil: Profil) -> dict[str, float]:
    """Plan kotası için ders payları; matematik dersleri öne çıkarılır."""
    agirliklar = ders_agirliklari(db, profil)
    puanlar = {
        kod: deger * (MATEMATIK_KATSAYI if kod in MATEMATIK_DERSLER else 1.0)
        for kod, deger in agirliklar.items()
    }
    toplam = sum(puanlar.values()) or 1.0
    return {kod: deger / toplam for kod, deger in puanlar.items()}


def oncelikli_konular(db: Session, profil: Profil, limit: int = 40) -> list[tuple[Konu, float]]:
    """Profil için öncelik sırasına dizilmiş konu listesi döndürür."""
    dersler = alan_ders_kodlari(profil.alan)
    konular = list(
        db.execute(select(Konu).where(Konu.ders_kod.in_(dersler))).scalars()
    )
    durumlar = _durum_haritasi(db, profil.id)
    tamam_olan = {kid for kid, d in durumlar.items() if d.durum == "tamam"}

    # Hedef sıralamadan türetilen ders payları: en ağır ders 2.3x, en hafif ~0.7x
    agirliklar = ders_agirliklari(db, profil)
    en_yuksek = max(agirliklar.values()) if agirliklar else 0.0

    def ders_carpani(kod: str) -> float:
        if not en_yuksek:
            return 1.0
        return 0.7 + 1.6 * (agirliklar.get(kod, 0.0) / en_yuksek)

    # Konu bazlı açık tablosu: denemede yanlış çıkan ya da başarısı düşük konu
    # etkin puanıyla öne geçer, program doğrudan açığa göre kurulur.
    satirlar = {s["id"]: s for s in konu_tablosu(db, profil)}

    # konu kodu -> id eşlemesi (ön koşul kontrolü için)
    kod_id = {k.kod: k.id for k in konular}
    onkosul_kodlari = {k.id: [o for o in (k.onkosul or "").split(",") if o] for k in konular}

    puanli: list[tuple[Konu, float]] = []
    for konu in konular:
        # Sınıf kapsamı dışındaki konu plana aday olmaz (analizde görünür)
        if sinif_servisi.kapsam_disi(konu.sinif, profil.sinif):
            continue
        durum = durumlar.get(konu.id)
        durum_adi = durum.durum if durum else "yok"
        guven = durum.guven if durum else 0

        if durum_adi == "tamam" and guven >= 4 and konu.sinif < 11:
            # 9-10. sınıf konusu sağlam biliniyorsa arka plana at
            puan = -5.0
        else:
            satir = satirlar.get(konu.id)
            if satir:
                puan = satir["etkin_puan"] * 6.0
                # Denemede işaretlenen her yanlış, konuyu daha da öne çeker
                puan += 2.0 * satir["deneme_yanlis"]
            else:
                puan = float(konu.agirlik) * 3.0 * ders_carpani(konu.ders_kod)
            if durum_adi == "yok":
                puan += 2.5
            elif durum_adi == "tekrar":
                puan += 4.0
            elif durum_adi == "calisiliyor":
                puan += 1.5
            if durum_adi == "tamam":
                puan -= 3.0
            puan -= guven  # düşük özgüven = yüksek öncelik

        # ön koşulu tamamlanmamışsa sırayı geriye düşür (ama engelleme)
        eksik_onkosul = [
            o for o in onkosul_kodlari.get(konu.id, [])
            if kod_id.get(o) is not None and kod_id[o] not in tamam_olan
        ]
        if eksik_onkosul:
            puan -= 2.0

        # Güncel sınıfın konuları öne alınır (11. sınıfta 11. sınıf konuları +%20)
        puan *= sinif_servisi.oncelik_carpani(konu.sinif, profil.sinif)

        puanli.append((konu, puan))

    puanli.sort(key=lambda ikili: (-ikili[1], ikili[0].sira))
    return puanli[:limit]


def _deneme_yanlis_haritasi(db: Session, profil: Profil) -> dict[int, int]:
    """Denemede yanlış çıkan konular: konu_id -> yanlış sayısı."""
    return {
        satir["id"]: int(satir["deneme_yanlis"])
        for satir in konu_tablosu(db, profil)
        if satir["deneme_yanlis"]
    }


def _konu_basligi(konu: Konu, yanlislar: dict[int, int]) -> str:
    """Konu maddesinin başlığı; deneme kanıtı varsa görünür olur."""
    yanlis = yanlislar.get(konu.id) or 0
    if yanlis:
        return f"{konu.ad} konu çalışması · denemede {yanlis} yanlış"
    return f"{konu.ad} konu çalışması"


def _gunluk_hedef(profil: Profil) -> int:
    """Günlük çalışma hedefi; okula giden öğrenciye PDR üst sınırı uygulanır.

    Okul gününde 4,5 saatten fazla çalışmak akşam bloklarını gece yarısına
    taşıdığı için hedef kırpılır; mezun öğrencide sınır uygulanmaz.
    """
    hedef = max(60, min(600, profil.gunluk_hedef_dk))
    if profil.sinif:
        return min(hedef, OKUL_GUNU_AZAMI_DK)
    return hedef


def _blok_olculeri(hedef_dk: int) -> tuple[int, int, int, int, int, int]:
    """(konu bloğu sayısı, konu dk, soru dk, tekrar dk, matematik dk, paragraf dk).

    Matematik ve paragraf blokları günlük hedeften düşülür; toplam süre yine
    öğrencinin günlük hedefine yakın kalır.
    """
    hedef = max(60, min(600, hedef_dk))
    mat_dk = max(20, min(45, round(hedef * 0.14)))
    par_dk = max(15, min(35, round(hedef * 0.10)))
    kalan = max(40, hedef - mat_dk - par_dk)
    konu_sayisi = max(1, round(kalan * 0.55 / 50))
    # Tek blok PDR sınırını aşmaz: 50 dakikadan uzun kesintisiz oturum önerilmez
    konu_dk = max(20, min(BLOK_AZAMI_DK, int(kalan * 0.55 / konu_sayisi)))
    soru_dk = max(15, int(kalan * 0.30 / konu_sayisi))
    tekrar_dk = kalan - konu_sayisi * (konu_dk + soru_dk)
    return konu_sayisi, konu_dk, soru_dk, tekrar_dk, mat_dk, par_dk


def _olcu_listesi(
    olculer: tuple[int, int, int, int, int, int],
    ek: list[int] | None = None,
    adet_farki: int = 0,
) -> list[int]:
    """Blok ölçülerinden maddelerin süre listesi (yazılma sırasıyla)."""
    konu_sayisi, konu_dk, soru_dk, tekrar_dk, mat_dk, par_dk = olculer
    sureler = [max(20, mat_dk), max(15, par_dk)]
    for _ in range(max(1, konu_sayisi + adet_farki)):
        sureler.extend([max(20, konu_dk), max(15, soru_dk)])
    if tekrar_dk >= 15:
        sureler.append(tekrar_dk)
    return (ek or []) + sureler


def _gun_olculeri(
    profil: Profil,
    tarih: date,
    ek: list[int] | None = None,
    adet_farki: int = 0,
    hedef_dk: int | None = None,
) -> tuple[int, int, int, int, int, int]:
    """Günün pencerelerine sığan en yüksek hedefin blok ölçüleri.

    Hafta içi akşam penceresi sınırlı olduğu için hedef, gün akışına
    sığana kadar 10'ar dakika düşürülür; böylece hiçbir madde yatışa
    hazırlık ya da günü kapatma bloğunun üstüne taşmaz. ``ek`` o gün
    korunan (tamamlanmış) maddelerin süreleridir; ``hedef_dk`` ile kalan
    günlük hedef verilir.
    """
    pencereler = gun_cercevesi(tarih, profil)["pencereler"]
    ust = _gunluk_hedef(profil)
    hedef = ust if hedef_dk is None else max(60, min(ust, hedef_dk))
    while hedef >= 90:
        olculer = _blok_olculeri(hedef)
        if sigiyor_mu(_olcu_listesi(olculer, ek, adet_farki), pencereler):
            return olculer
        hedef -= 10
    return _blok_olculeri(90)


def _tamamlananlar(db: Session, profil: Profil, tarih: date) -> list[PlanItem]:
    """O gün tamamlanmış maddeler (yeniden üretimde korunur)."""
    return list(
        db.execute(
            select(PlanItem).where(
                PlanItem.profil_id == profil.id,
                PlanItem.tarih == tarih,
                PlanItem.durum == "tamam",
            )
        ).scalars()
    )


def _gun_durumu(
    db: Session, profil: Profil, tarih: date
) -> tuple[list[PlanItem], list[int], int, int]:
    """(tamamlananlar, süreleri, kalan hedef dakikası, son sıra numarası)."""
    mevcut = _tamamlananlar(db, profil, tarih)
    sureler = [m.sure_dk or 0 for m in mevcut]
    kalan = max(60, _gunluk_hedef(profil) - sum(sureler))
    sira = max((m.sira or 0 for m in mevcut), default=0)
    return mevcut, sureler, kalan, sira


def _ders_kuyrugu(kuyruk: list[Konu]) -> dict[str, list[Konu]]:
    """Öncelik sırasını ders bazında gruplar (sıra korunur)."""
    gruplar: dict[str, list[Konu]] = {}
    for konu in kuyruk:
        gruplar.setdefault(konu.ders_kod, []).append(konu)
    return gruplar


def _okul_konulari(
    db: Session, profil: Profil, tarih: date
) -> list[tuple[Konu, int]]:
    """Okulda işlenen ve o gün tekrar edilecek konular: (konu, kaç gün önce).

    Aralıklı tekrar takvimi ``ders_programi.TEKRAR_GUNLERI``: konu işlendiği
    gün (0), ertesi gün (1), üçüncü ve yedinci günde yeniden öne gelir. Aynı
    gün işlenen konu listenin başındadır.
    """
    gunler = {tarih - timedelta(days=k): k for k in okul_programi.TEKRAR_GUNLERI}
    satirlar = list(
        db.execute(
            select(IslenenKonu)
            .where(
                IslenenKonu.profil_id == profil.id,
                IslenenKonu.tarih.in_(list(gunler)),
            )
            .order_by(IslenenKonu.tarih.desc(), IslenenKonu.id)
        ).scalars()
    )
    if not satirlar:
        return []
    konular = {
        k.id: k
        for k in db.execute(
            select(Konu).where(Konu.id.in_([s.konu_id for s in satirlar]))
        ).scalars()
    }
    return [
        (konular[s.konu_id], gunler[s.tarih])
        for s in satirlar
        if s.konu_id in konular
    ]


def _okul_tekrarlari(
    db: Session,
    profil: Profil,
    tarih: date,
    sira: int,
    konular: list[tuple[Konu, int]],
) -> tuple[int, int]:
    """Okulda görülen konuları o günün ilk bloklarına yazar.

    Tekrar okulun hemen ardından yapılır: aynı gün işlenen konu
    "tekrar ve pekiştirme", önceki günler "tekrar", daha eskiler
    "aralıklı tekrar" olarak adlandırılır.
    """
    eklenen = 0
    for konu, once in konular[:OKUL_TEKRAR_AZAMI]:
        if once == 0:
            baslik = f"Tekrar ve pekiştirme: {konu.ad} (bugün okulda işlendi)"
        elif once == 1:
            baslik = f"Tekrar: {konu.ad} (dün okulda işlendi)"
        else:
            baslik = f"Aralıklı tekrar: {konu.ad} ({once} gün önce okulda işlendi)"
        sira += 1
        db.add(
            PlanItem(
                profil_id=profil.id,
                tarih=tarih,
                ders_kod=konu.ders_kod,
                konu_id=konu.id,
                baslik=baslik,
                tur="tekrar",
                sure_dk=OKUL_TEKRAR_DK,
                durum="bekliyor",
                sira=sira,
            )
        )
        eklenen += 1
    return eklenen, sira


def _sabit_blok_konulari(
    db: Session, kuyruk: list[Konu]
) -> dict[str, list[Konu] | Konu | None]:
    """Her gün yazılan matematik ve paragraf bloklarının konuları."""
    matematik = [k for k in kuyruk if k.ders_kod in MATEMATIK_DERSLER][:3]
    if not matematik:
        matematik = list(
            db.execute(
                select(Konu)
                .where(Konu.ders_kod.in_(MATEMATIK_DERSLER))
                .order_by(Konu.sira)
            ).scalars()
        )[:3]

    paragraf = next(
        (k for k in kuyruk if k.ad.lower().startswith(PARAGRAF_ARAMA)), None
    )
    if paragraf is None:
        paragraf = db.execute(
            select(Konu)
            .where(Konu.ad.like("Paragraf%"), Konu.ders_kod == "TYT-TUR")
            .order_by(Konu.sira)
        ).scalars().first()
    return {"matematik": matematik, "paragraf": paragraf}


def _gunluk_secim(
    gruplar: dict[str, list[Konu]],
    agirliklar: dict[str, float],
    adet: int,
    paylar: dict[str, float],
    haric: set[int] | None = None,
) -> list[Konu]:
    """Hedef payına göre günlük konu seçimi (açık kotalı adil dağıtım).

    Her ders gün başına ``payı × adet`` kadar alacak biriktirir; her seçim
    1 birim harcar. Böylece hafta boyunca dersler hedef oranında temsil
    edilir ve düşük paylı dersler tamamen dışlanmaz.

    ``haric`` okulda işlenmiş konulardır: bunlar yeni konu bloğu olarak
    yazılmaz, günün tekrar/pekiştirme bloklarında yer alır.
    """
    if haric:
        for kod in list(gruplar):
            if any(k.id in haric for k in gruplar[kod]):
                gruplar[kod] = [k for k in gruplar[kod] if k.id not in haric]
    uygun = {kod: liste for kod, liste in gruplar.items() if liste}
    if not uygun or adet <= 0:
        return []

    toplam = sum(agirliklar.get(kod, 0.0) for kod in uygun)
    if toplam <= 0:
        oranlar = {kod: 1.0 / len(uygun) for kod in uygun}
    else:
        oranlar = {kod: agirliklar.get(kod, 0.0) / toplam for kod in uygun}

    for kod, oran in oranlar.items():
        paylar[kod] = paylar.get(kod, 0.0) + oran * adet

    secim: list[Konu] = []
    for _ in range(adet):
        adaylar = [kod for kod in uygun if uygun[kod]]
        if not adaylar:
            break
        kod = max(adaylar, key=lambda k: paylar.get(k, 0.0))
        secim.append(uygun[kod].pop(0))
        paylar[kod] = paylar.get(kod, 0.0) - 1.0
    return secim


def _sabit_bloklari_ekle(
    db: Session,
    profil: Profil,
    tarih: date,
    sira: int,
    sabit: dict,
    mat_dk: int,
    par_dk: int,
    gun_no: int,
) -> tuple[int, int]:
    """Günlük matematik ve paragraf soru bloklarını yazar.

    Bu iki blok her gün koşulsuz yazılır: programın değişmez günlük alışkanlığı
    matematik ve paragraf sorusudur. Aynı konu o gün konu bloğunda da geçse
    "20 soru" maddesi ayrı bir iştir, silinmez.
    """
    eklenen = 0

    matematik = sabit.get("matematik") or []
    if matematik:
        konu = matematik[gun_no % len(matematik)]
        sira += 1
        db.add(
            PlanItem(
                profil_id=profil.id,
                tarih=tarih,
                ders_kod=konu.ders_kod,
                konu_id=konu.id,
                baslik=f"Günlük matematik: 20 soru ({konu.ad})",
                tur="soru",
                sure_dk=max(20, mat_dk),
                durum="bekliyor",
                sira=sira,
            )
        )
        eklenen += 1

    paragraf = sabit.get("paragraf")
    if paragraf is not None:
        sira += 1
        db.add(
            PlanItem(
                profil_id=profil.id,
                tarih=tarih,
                ders_kod=paragraf.ders_kod,
                konu_id=paragraf.id,
                baslik="Günlük paragraf: 20 soru",
                tur="soru",
                sure_dk=max(15, par_dk),
                durum="bekliyor",
                sira=sira,
            )
        )
        eklenen += 1

    return eklenen, sira


def _ek_blok_konusu(
    db: Session, parcalar: list[PlanItem], konum: int, yedek: list[Konu]
) -> Konu | None:
    """Ek bloğun konusu: penceredeki son maddenin konusu, yoksa günün ilk konusu."""
    for parca in reversed(parcalar[:konum]):
        if not parca.konu_id:
            continue
        konu = db.get(Konu, parca.konu_id)
        if konu is not None:
            return konu
    return yedek[0] if yedek else None


def _gun_sonu_doldur(
    db: Session, profil: Profil, tarih: date, sira: int, yedek: list[Konu]
) -> tuple[int, int]:
    """Pencere sonunda kalan boşluklara ek soru bloğu yazar.

    ``_gun_olculeri`` günü sığdırmak için hedefi 10'ar dakika küçültür; bu
    yüzden son bloktan sonra yarım saate varan görevsiz zaman kalabiliyordu.
    Boşluğa kalan hedef dakikası kadar (en fazla ``BLOK_AZAMI_DK``) ek soru
    bloğu yazılır; böylece gün akışında "Günü kapat" bloğuna kadar boş aralık
    kalmaz. Ek blok, penceredeki son maddenin konusunu sürdürür ve günlük
    hedefi ``EK_BLOK_PAYI_DK`` dakikadan fazla aşmaz.
    """
    # Bu oturumda autoflush kapalı: günün yeni maddeleri sorguda görünsün
    db.flush()
    maddeler = list(
        db.execute(
            select(PlanItem)
            .where(PlanItem.profil_id == profil.id, PlanItem.tarih == tarih)
            .order_by(PlanItem.sira, PlanItem.id)
        ).scalars()
    )
    if not maddeler:
        return 0, sira

    cerceve = gun_cercevesi(tarih, profil, any(m.tur == "deneme" for m in maddeler))
    # Ek bloklar hedefi EK_BLOK_PAYI_DK kadar aşabilir, günün tavanını aşamaz
    tavan = min(cerceve["azami_dk"], _gunluk_hedef(profil) + EK_BLOK_PAYI_DK)
    butce = tavan - sum(m.sure_dk or 30 for m in maddeler)
    parcalar: list[PlanItem] = list(maddeler)
    sureler = [m.sure_dk or 30 for m in maddeler]
    eklenen = 0

    for _ in range(EK_BLOK_SAYISI):
        if butce < EK_BLOK_ESIGI_DK:
            break
        uygun = next(
            (
                (konum, bosluk)
                for konum, bosluk in pencere_bosluklari(sureler, cerceve["pencereler"])
                if bosluk >= EK_BLOK_ESIGI_DK
            ),
            None,
        )
        if uygun is None:
            break
        konum, bosluk = uygun
        sure = min(BLOK_AZAMI_DK, bosluk, butce)
        konu = _ek_blok_konusu(db, parcalar, konum, yedek)
        if sure < EK_BLOK_ESIGI_DK or konu is None:
            break
        ek = PlanItem(
            profil_id=profil.id,
            tarih=tarih,
            ders_kod=konu.ders_kod,
            konu_id=konu.id,
            baslik=f"{konu.ad} soru çözümü (ek blok)",
            tur="soru",
            sure_dk=sure,
            durum="bekliyor",
            sira=0,
        )
        db.add(ek)
        # Ek blok pencerenin sonuna girer: akış sırası bozulmasın diye araya konur
        parcalar.insert(konum, ek)
        sureler.insert(konum, sure)
        butce -= sure
        eklenen += 1

    if not eklenen:
        return 0, sira

    for numara, madde in enumerate(parcalar, start=1):
        madde.sira = numara
    return eklenen, len(parcalar)


def gunluk_plan_uret(
    db: Session,
    profil: Profil,
    gun_sayisi: int = 7,
    baslangic: date | None = None,
) -> int:
    """Belirtilen aralık için plan üretir; eski bekleyen maddeleri tazeler.

    Dağıtım öğrencinin **hedef sıralamasından** türetilen ders paylarına göre
    yapılır: hedefi yüksek olan öğrencide matematik/fen daha çok blok alır.
    Maddeler okul, öğün, mola ve uyku saatleriyle kurulan gün akışına
    yerleştirilir (``program.py``).
    """
    baslangic = baslangic or date.today()
    bitis = baslangic + timedelta(days=gun_sayisi - 1)

    db.execute(
        delete(PlanItem).where(
            PlanItem.profil_id == profil.id,
            PlanItem.tarih >= baslangic,
            PlanItem.tarih <= bitis,
            PlanItem.durum == "bekliyor",
        )
    )
    db.commit()

    kuyruk = [k for k, _ in oncelikli_konular(db, profil, limit=max(40, gun_sayisi * 8))]
    if not kuyruk:
        return 0

    gruplar = _ders_kuyrugu(kuyruk)
    agirliklar = plan_agirliklari(db, profil)
    sabit = _sabit_blok_konulari(db, kuyruk)
    yanlislar = _deneme_yanlis_haritasi(db, profil)
    paylar: dict[str, float] = {}
    haric: set[int] = set()
    eklenen = 0

    for gun in range(gun_sayisi):
        tarih = baslangic + timedelta(days=gun)
        _, ek, kalan_hedef, sira = _gun_durumu(db, profil, tarih)
        # Okulda işlenen konular: günün ilk bloklarına tekrar/pekiştirme yazılır
        okul_konulari = _okul_konulari(db, profil, tarih)
        okul_ek = [OKUL_TEKRAR_DK] * min(len(okul_konulari), OKUL_TEKRAR_AZAMI)
        haric.update(k.id for k, _ in okul_konulari)
        if ek and not sigiyor_mu(
            ek + okul_ek, gun_cercevesi(tarih, profil)["pencereler"]
        ):
            # Günün tamamlanmış maddeleri pencereleri doldurmuşsa yeni madde yazılmaz
            continue
        konu_sayisi, konu_dk, soru_dk, tekrar_dk, mat_dk, par_dk = _gun_olculeri(
            profil,
            tarih,
            ek=ek + okul_ek,
            hedef_dk=kalan_hedef - sum(okul_ek),
        )
        secilen = _gunluk_secim(gruplar, agirliklar, konu_sayisi, paylar, haric)
        if not secilen:
            # Konu havuzu tükendi: tekrar çalışması için baştan doldur
            gruplar = _ders_kuyrugu(kuyruk)
            secilen = _gunluk_secim(gruplar, agirliklar, konu_sayisi, paylar, haric)

        yazilan, sira = _okul_tekrarlari(db, profil, tarih, sira, okul_konulari)
        eklenen += yazilan
        yazilan, sira = _sabit_bloklari_ekle(
            db, profil, tarih, sira, sabit, mat_dk, par_dk, gun
        )
        eklenen += yazilan

        for konu in secilen:
            sira += 1
            db.add(
                PlanItem(
                    profil_id=profil.id,
                    tarih=tarih,
                    ders_kod=konu.ders_kod,
                    konu_id=konu.id,
                    baslik=_konu_basligi(konu, yanlislar),
                    tur="konu",
                    sure_dk=max(20, konu_dk),
                    durum="bekliyor",
                    sira=sira,
                )
            )
            sira += 1
            db.add(
                PlanItem(
                    profil_id=profil.id,
                    tarih=tarih,
                    ders_kod=konu.ders_kod,
                    konu_id=konu.id,
                    baslik=f"{konu.ad} soru çözümü",
                    tur="soru",
                    sure_dk=max(15, soru_dk),
                    durum="bekliyor",
                    sira=sira,
                )
            )
            eklenen += 2

        if tekrar_dk >= 15:
            konu = secilen[0]
            sira += 1
            db.add(
                PlanItem(
                    profil_id=profil.id,
                    tarih=tarih,
                    ders_kod=konu.ders_kod,
                    konu_id=konu.id,
                    baslik=f"{konu.ad} tekrarı",
                    tur="tekrar",
                    sure_dk=tekrar_dk,
                    durum="bekliyor",
                    sira=sira,
                )
            )
            eklenen += 1

        # Pencerelerin sonunda kalan görevsiz süre ek soru bloğuyla doldurulur
        yazilan, sira = _gun_sonu_doldur(db, profil, tarih, sira, secilen)
        eklenen += yazilan

    db.commit()
    # Maddeler günün gerçek saatlerine (okul, öğün, mola, uyku) yerleştirilir
    zamanlari_yerlestir(db, profil, baslangic, bitis)
    return eklenen


def _aralik_maddeleri(
    db: Session, profil_id: int, baslangic: date, bitis: date
) -> list[PlanItem]:
    return list(
        db.execute(
            select(PlanItem)
            .where(
                PlanItem.profil_id == profil_id,
                PlanItem.tarih >= baslangic,
                PlanItem.tarih <= bitis,
            )
            .order_by(PlanItem.tarih, PlanItem.sira)
        ).scalars()
    )


def _ders_dagilimi(maddeler: list[PlanItem], ders_map: dict[str, Ders]) -> list[dict]:
    """Plan maddelerini ders bazında dakika/tamamlanma olarak toplar."""
    gruplar: dict[str, dict] = {}
    for madde in maddeler:
        kod = madde.ders_kod or "deneme"
        ders = ders_map.get(kod)
        grup = gruplar.setdefault(
            kod,
            {
                "kod": kod,
                "ad": ders.ad if ders else "Deneme / tekrar",
                "sinav": ders.sinav if ders else "",
                "renk": ders.renk if ders else "#b45309",
                "madde": 0,
                "dk": 0,
                "tamam": 0,
                "tamam_dk": 0,
            },
        )
        grup["madde"] += 1
        grup["dk"] += madde.sure_dk or 0
        if madde.durum == "tamam":
            grup["tamam"] += 1
            grup["tamam_dk"] += madde.sure_dk or 0
    return sorted(gruplar.values(), key=lambda g: -g["dk"])


def plan_ozeti(
    db: Session, profil: Profil, gun_sayisi: int = 7, baslangic: date | None = None
) -> dict:
    """Bir aralığın plan özeti: ders dakikaları, tamamlanma, deneme günleri."""
    baslangic = baslangic or date.today()
    bitis = baslangic + timedelta(days=gun_sayisi - 1)
    maddeler = _aralik_maddeleri(db, profil.id, baslangic, bitis)
    ders_map = {d.kod: d for d in db.execute(select(Ders)).scalars()}
    hedef = hedef_ozeti(db, profil)

    toplam_dk = sum(m.sure_dk or 0 for m in maddeler)
    tamam_dk = sum(m.sure_dk or 0 for m in maddeler if m.durum == "tamam")

    return {
        "baslangic": baslangic.isoformat(),
        "bitis": bitis.isoformat(),
        "gun_sayisi": gun_sayisi,
        "madde_sayisi": len(maddeler),
        "toplam_dk": toplam_dk,
        "tamam_dk": tamam_dk,
        "tamam_orani": round(100 * tamam_dk / toplam_dk) if toplam_dk else 0,
        "deneme_gunleri": sorted(
            {m.tarih.isoformat() for m in maddeler if m.tur == "deneme"}
        ),
        "dersler": _ders_dagilimi(maddeler, ders_map),
        "hedef": {
            "hedef_siralama": hedef["hedef_siralama"],
            "tyt_hedef_net": hedef["tyt_hedef_net"],
            "ayt_hedef_net": hedef["ayt_hedef_net"],
            "haftalik_gereken_net": hedef["haftalik_gereken_net"],
        },
    }


def _odak_konu(satir: dict) -> dict:
    return {
        "konu": satir["ad"],
        "ders": satir["ders_ad"],
        "ders_kod": satir["ders_kod"],
        "renk": satir["renk"],
        "beklenen_soru": satir["beklenen_soru"],
        "basari_yuzde": satir["basari_yuzde"],
        "etkin_puan": satir["etkin_puan"],
        "kaynak": satir["kaynak"],
    }


def aylik_plan(
    db: Session,
    profil: Profil,
    hafta_sayisi: int = 4,
    baslangic: date | None = None,
) -> dict:
    """Aylık program: hafta hafta odak konular, dakika dağılımı ve deneme günleri."""
    baslangic = baslangic or date.today()
    hafta_sayisi = max(1, min(8, hafta_sayisi))
    ders_map = {d.kod: d for d in db.execute(select(Ders)).scalars()}
    hedef = hedef_ozeti(db, profil)
    konular = [s for s in konu_tablosu(db, profil) if s["beklenen_soru"] > 0]
    haftalik_net = hedef["haftalik_gereken_net"] or 0.0
    gunluk_hedef = max(60, min(600, profil.gunluk_hedef_dk))

    haftalar: list[dict] = []
    for i in range(hafta_sayisi):
        h_bas = baslangic + timedelta(days=7 * i)
        h_bit = h_bas + timedelta(days=6)
        maddeler = _aralik_maddeleri(db, profil.id, h_bas, h_bit)
        odak = konular[4 * i : 4 * i + 4] or konular[:4]
        haftalar.append(
            {
                "hafta": i + 1,
                "baslangic": h_bas.isoformat(),
                "bitis": h_bit.isoformat(),
                "odak_konular": [_odak_konu(s) for s in odak],
                "deneme_tarihleri": sorted(
                    {m.tarih.isoformat() for m in maddeler if m.tur == "deneme"}
                ),
                "madde_sayisi": len(maddeler),
                "toplam_dk": sum(m.sure_dk or 0 for m in maddeler),
                "tamam_dk": sum(
                    m.sure_dk or 0 for m in maddeler if m.durum == "tamam"
                ),
                "dersler": _ders_dagilimi(maddeler, ders_map),
                "hedef_net": round(haftalik_net * (i + 1), 1),
                "hedef_dk": gunluk_hedef * 7,
            }
        )

    return {
        "baslangic": baslangic.isoformat(),
        "bitis": (baslangic + timedelta(days=7 * hafta_sayisi - 1)).isoformat(),
        "hafta_sayisi": hafta_sayisi,
        "gunluk_hedef_dk": profil.gunluk_hedef_dk,
        "uretilmis": any(h["deneme_tarihleri"] for h in haftalar),
        "hedef": {
            "hedef_siralama": hedef["hedef_siralama"],
            "tyt_hedef_net": hedef["tyt_hedef_net"],
            "ayt_hedef_net": hedef["ayt_hedef_net"],
            "haftalik_gereken_net": hedef["haftalik_gereken_net"],
            "toplam_acik_net": round(
                max(0.0, hedef["tyt_hedef_net"] - hedef["tyt_mevcut_net"])
                + max(0.0, hedef["ayt_hedef_net"] - hedef["ayt_mevcut_net"]),
                1,
            ),
        },
        "haftalar": haftalar,
    }


def aylik_plan_uret(
    db: Session,
    profil: Profil,
    hafta_sayisi: int = 4,
    baslangic: date | None = None,
) -> int:
    """4 haftalık takvimi üretir: hafta içi konu blokları, cumartesi deneme, pazar tekrar."""
    baslangic = baslangic or date.today()
    hafta_sayisi = max(1, min(8, hafta_sayisi))
    gun_sayisi = hafta_sayisi * 7
    bitis = baslangic + timedelta(days=gun_sayisi - 1)

    db.execute(
        delete(PlanItem).where(
            PlanItem.profil_id == profil.id,
            PlanItem.tarih >= baslangic,
            PlanItem.tarih <= bitis,
            PlanItem.durum == "bekliyor",
        )
    )
    db.commit()

    kuyruk = [k for k, _ in oncelikli_konular(db, profil, limit=max(80, gun_sayisi * 6))]
    if not kuyruk:
        return 0

    gruplar = _ders_kuyrugu(kuyruk)
    agirliklar = plan_agirliklari(db, profil)
    sabit = _sabit_blok_konulari(db, kuyruk)
    yanlislar = _deneme_yanlis_haritasi(db, profil)
    paylar: dict[str, float] = {}
    haric: set[int] = set()
    eklenen = 0

    def ekle(
        tarih: date,
        sira: int,
        baslik: str,
        tur: str,
        sure_dk: int,
        ders_kod: str = "",
        konu_id: int | None = None,
    ) -> int:
        db.add(
            PlanItem(
                profil_id=profil.id,
                tarih=tarih,
                ders_kod=ders_kod,
                konu_id=konu_id,
                baslik=baslik,
                tur=tur,
                sure_dk=max(15, sure_dk),
                durum="bekliyor",
                sira=sira,
            )
        )
        return 1

    for gun in range(gun_sayisi):
        tarih = baslangic + timedelta(days=gun)
        hafta_no = gun // 7
        mevcut, ek, kalan_hedef, sira = _gun_durumu(db, profil, tarih)

        # Cumartesi: tam süreli deneme sınavı (haftalar arasında TYT/AYT dönüşümlü)
        # Tamamlanmış deneme günü yeniden yazılmaz (maddeler ikilenmesin).
        if tarih.weekday() == 5:
            if mevcut:
                continue
            tur = "TYT" if hafta_no % 2 == 0 else "AYT"
            sira += 1
            eklenen += ekle(
                tarih, sira, "Isınma: 20 kolay soru (sınav öncesi ritim)", "soru", 55
            )
            sira += 1
            eklenen += ekle(
                tarih, sira, f"{tur} denemesi (tam süre)", "deneme", 165 if tur == "TYT" else 180
            )
            sira += 1
            eklenen += ekle(
                tarih, sira, "Deneme analizi: yanlış konuları işaretle", "tekrar", 40
            )
            sira += 1
            eklenen += ekle(
                tarih, sira, "Telafi: yanlış konulardan 20 soru", "soru", 75
            )
            continue

        # Pazar: haftalık tekrar + hata defteri
        pazar = tarih.weekday() == 6
        haftalik_dk = max(45, profil.gunluk_hedef_dk // 3)
        haftalik_var = pazar and any(
            (m.baslik or "").startswith("Haftalık tekrar") for m in mevcut
        )
        # Okulda işlenen konular o günün ilk işi: tekrar/pekiştirme bloğu
        okul_konulari = _okul_konulari(db, profil, tarih)
        okul_ek = [OKUL_TEKRAR_DK] * min(len(okul_konulari), OKUL_TEKRAR_AZAMI)
        haric.update(k.id for k, _ in okul_konulari)
        ek_sureler = (
            ([haftalik_dk] if pazar and not haftalik_var else []) + ek + okul_ek
        )
        if ek and not sigiyor_mu(ek_sureler, gun_cercevesi(tarih, profil)["pencereler"]):
            continue
        # Ölçüler günün kendi pencerelerine göre belirlenir (pazar günü ek blok)
        konu_sayisi, konu_dk, soru_dk, tekrar_dk, mat_dk, par_dk = _gun_olculeri(
            profil,
            tarih,
            ek=ek_sureler,
            adet_farki=-1 if pazar else 0,
            hedef_dk=kalan_hedef
            - sum(okul_ek)
            - (haftalik_dk if pazar and not haftalik_var else 0),
        )
        if pazar and not haftalik_var:
            sira += 1
            eklenen += ekle(
                tarih,
                sira,
                "Haftalık tekrar ve hata defteri",
                "tekrar",
                haftalik_dk,
            )

        # Pazar günü tekrar bloğu ayrıldığı için bir konu eksik alınır
        adet = max(1, konu_sayisi - 1) if pazar else konu_sayisi
        secilen = _gunluk_secim(gruplar, agirliklar, adet, paylar, haric)
        if not secilen:
            gruplar = _ders_kuyrugu(kuyruk)
            secilen = _gunluk_secim(gruplar, agirliklar, adet, paylar, haric)

        # Okulda işlenen konular tekrar ve pekiştirme olarak ilk sıraya yazılır
        yazilan, sira = _okul_tekrarlari(db, profil, tarih, sira, okul_konulari)
        eklenen += yazilan

        # Her gün matematik ve paragraf soruları
        yazilan, sira = _sabit_bloklari_ekle(
            db, profil, tarih, sira, sabit, mat_dk, par_dk, gun
        )
        eklenen += yazilan

        for konu in secilen:
            sira += 1
            eklenen += ekle(
                tarih,
                sira,
                _konu_basligi(konu, yanlislar),
                "konu",
                konu_dk,
                konu.ders_kod,
                konu.id,
            )
            sira += 1
            eklenen += ekle(
                tarih,
                sira,
                f"{konu.ad} soru çözümü",
                "soru",
                soru_dk,
                konu.ders_kod,
                konu.id,
            )

        if tekrar_dk >= 15 and secilen:
            konu = secilen[-1]
            sira += 1
            eklenen += ekle(
                tarih,
                sira,
                f"{konu.ad} tekrarı",
                "tekrar",
                tekrar_dk,
                konu.ders_kod,
                konu.id,
            )

        # Pencere sonunda kalan görevsiz süre ek soru bloğuyla doldurulur
        yazilan, sira = _gun_sonu_doldur(db, profil, tarih, sira, secilen)
        eklenen += yazilan

    db.commit()
    # 4 haftalık takvim de gün akışına (okul, öğün, mola, uyku) yerleştirilir
    zamanlari_yerlestir(db, profil, baslangic, bitis)
    return eklenen
