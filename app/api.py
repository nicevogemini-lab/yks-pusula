# -*- coding: utf-8 -*-
"""YKS Pusula HTTP API'si."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .auth import kapi_acik
from .data import ALAN_AYT_DERSLERI, BECERI_ETIKET, TUM_DERSLER, alan_ders_kodlari
from .database import get_db
from .models import (
    AiMesaj,
    Ayar,
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
from .services import ai as ai_servis
from .services import analiz as analiz_servis
from .services import degerlendirme as degerlendirme_servis
from .services import hedef as hedef_servis
from .services import scoring
from .services.plan import (
    aylik_plan,
    aylik_plan_uret,
    gunluk_plan_uret,
    oncelikli_konular,
    plan_ozeti,
)
from .services.program import (
    beceri_dengesi,
    deneme_odagi,
    gun_akisi,
    gun_cercevesi,
    pdr_ilkeleri,
    zamanlari_yerlestir,
)

api = APIRouter(prefix="/api", tags=["pusula"])

GECERLI_ALANLAR = {"sayisal", "ea", "sozel"}
GECERLI_SINIFLAR = {11, 12, 0}  # 0 = mezun
TEKRAR_ARALIKLARI = [1, 3, 7, 21, 45]
# Gün akışı saatleri: HH:MM (00:00 - 23:59)
SAAT_DESENI = r"^([01]\d|2[0-3]):[0-5]\d$"
# Boş bırakılabilen saat: okuldan dönüş (boş = otomatik 35 dk yol)
SAAT_DESENI_BOS = r"^$|^([01]\d|2[0-3]):[0-5]\d$"

ALAN_BILGI = [
    {
        "kod": "sayisal",
        "ad": "Sayısal",
        "aciklama": "Tıp, mühendislik ve fen bilimleri hedefi",
        "vurgu": "Matematik · Fizik · Kimya · Biyoloji",
    },
    {
        "kod": "ea",
        "ad": "Eşit Ağırlık",
        "aciklama": "Hukuk, işletme, psikoloji, öğretmenlik hedefi",
        "vurgu": "Matematik · Edebiyat · Tarih-1 · Coğrafya-1",
    },
    {
        "kod": "sozel",
        "ad": "Sözel",
        "aciklama": "Sosyal bilimler, iletişim ve dil hedefi",
        "vurgu": "Edebiyat · Tarih · Coğrafya · Felsefe",
    },
]


# --------------------------------------------------------------------------
# Şemalar
# --------------------------------------------------------------------------
class ProfilGiris(BaseModel):
    ad: str = Field(default="Öğrenci", max_length=80)
    alan: str = "sayisal"
    sinif: int = 11
    hedef_siralama: int = 0
    gunluk_hedef_dk: int = 180
    uyanma_saati: str = Field(default="06:45", pattern=SAAT_DESENI)
    yatma_saati: str = Field(default="22:45", pattern=SAAT_DESENI)
    okul_baslangic: str = Field(default="08:20", pattern=SAAT_DESENI)
    okul_bitis: str = Field(default="15:20", pattern=SAAT_DESENI)
    okul_donus: str = Field(default="", pattern=SAAT_DESENI_BOS)


class ProfilGuncelle(BaseModel):
    ad: str | None = None
    alan: str | None = None
    sinif: int | None = None
    hedef_siralama: int | None = None
    gunluk_hedef_dk: int | None = None
    sinav_tarihi: date | None = None
    uyanma_saati: str | None = Field(default=None, pattern=SAAT_DESENI)
    yatma_saati: str | None = Field(default=None, pattern=SAAT_DESENI)
    okul_baslangic: str | None = Field(default=None, pattern=SAAT_DESENI)
    okul_bitis: str | None = Field(default=None, pattern=SAAT_DESENI)
    okul_donus: str | None = Field(default=None, pattern=SAAT_DESENI_BOS)


class KonuDurumGiris(BaseModel):
    profil_id: int
    konu_id: int
    durum: str = "tamam"
    guven: int = 3


class SonucSatiri(BaseModel):
    ders_kod: str
    dogru: int = 0
    yanlis: int = 0
    bos: int = 0


class KonuYanlis(BaseModel):
    """Denemede yanlış yapılan konu: konu bazlı açık tespiti için."""

    konu_id: int
    yanlis: int = 1


class DenemeGiris(BaseModel):
    profil_id: int
    tur: str = "TYT"
    ad: str = ""
    tarih: date | None = None
    sure_dk: int = 0
    notlar: str = ""
    sonuclar: list[SonucSatiri] = []
    konular: list[KonuYanlis] = []


class KonuYanlisGiris(BaseModel):
    """Kayıtlı denemenin yanlış konularını tazeler (boş liste temizler)."""

    konular: list[KonuYanlis] = []


class KocGiris(BaseModel):
    mesaj: str = Field(min_length=1, max_length=2000)


class AnahtarGiris(BaseModel):
    anahtar: str = ""
    model: str = "gemini-3.5-flash-lite"
    sil: bool = False


class AnahtarTest(BaseModel):
    """Kaydetmeden önce denemek için; boş bırakılan alan kayıtlı değeri kullanır."""

    anahtar: str = ""
    model: str = ""


class CalismaGiris(BaseModel):
    profil_id: int
    konu_id: int | None = None
    sure_dk: int = 60
    tur: str = "konu"
    dogru: int = 0
    yanlis: int = 0
    notlar: str = ""


# --------------------------------------------------------------------------
# Yardımcılar
# --------------------------------------------------------------------------
def _profil_getir(db: Session, profil_id: int) -> Profil:
    profil = db.get(Profil, profil_id)
    if not profil:
        raise HTTPException(status_code=404, detail="Profil bulunamadı")
    return profil


def _sinav_tarihi(sinif: int) -> date:
    """Yaklaşık YKS tarihi: 11. sınıf 2 yıl, 12. sınıf ve mezun 1 yıl sonra."""
    bugun = date.today()
    egitim_yili_basi = bugun.year if bugun.month >= 9 else bugun.year - 1
    yil = egitim_yili_basi + (2 if sinif == 11 else 1)
    cumartesiler = [date(yil, 6, g) for g in range(8, 25) if date(yil, 6, g).weekday() == 5]
    return cumartesiler[1] if len(cumartesiler) > 1 else date(yil, 6, 17)


def _alan_konulari(db: Session, profil: Profil) -> list[Konu]:
    kodlar = alan_ders_kodlari(profil.alan)
    return list(db.execute(select(Konu).where(Konu.ders_kod.in_(kodlar))).scalars())


def _durum_map(db: Session, profil_id: int) -> dict[int, KonuDurum]:
    return {
        d.konu_id: d
        for d in db.execute(select(KonuDurum).where(KonuDurum.profil_id == profil_id)).scalars()
    }


def _ders_map(db: Session) -> dict[str, Ders]:
    return {d.kod: d for d in db.execute(select(Ders)).scalars()}


def _saat_dk(saat: str | None) -> int:
    """'06:45' -> 405 (gece yarısından itibaren dakika)."""
    try:
        saat_kismi, dakika_kismi = (saat or "").split(":")
        return int(saat_kismi) * 60 + int(dakika_kismi)
    except (AttributeError, ValueError):
        return 0


def _saat_ekle(saat: str | None, sure_dk: int) -> str:
    """'16:15' + 50 dakika -> '17:05'."""
    toplam = (_saat_dk(saat) + max(0, sure_dk)) % (24 * 60)
    return f"{toplam // 60:02d}:{toplam % 60:02d}"


def _saat_farki(dilim: dict, tur: str) -> int:
    """Gün akışı dilimi istenen türdense süresini (dakika) döndürür."""
    if dilim.get("tur") != tur:
        return 0
    return max(0, _saat_dk(dilim.get("bitis")) - _saat_dk(dilim.get("baslangic")))


def _beceri_listesi(konu: Konu | None) -> list[str]:
    """Konunun Maarif beceri kodları (KB, AB, SD, OK)."""
    if konu is None:
        return []
    return [b for b in (konu.beceri or "").split(",") if b]


def _deneme_yanlis_map(db: Session, profil: Profil) -> dict[int, int]:
    """Denemelerde işaretlenen yanlış konular: konu_id -> yanlış sayısı."""
    satirlar = db.execute(
        select(DenemeKonu.konu_id, func.sum(DenemeKonu.yanlis))
        .join(Deneme, Deneme.id == DenemeKonu.deneme_id)
        .where(Deneme.profil_id == profil.id)
        .group_by(DenemeKonu.konu_id)
    ).all()
    return {konu_id: int(adet or 0) for konu_id, adet in satirlar if konu_id}


def _deneme_netleri(db: Session, deneme_id: int) -> list[DenemeSonuc]:
    return list(db.execute(select(DenemeSonuc).where(DenemeSonuc.deneme_id == deneme_id)).scalars())


def _deneme_konulari(db: Session, deneme_id: int) -> list[DenemeKonu]:
    return list(
        db.execute(
            select(DenemeKonu)
            .where(DenemeKonu.deneme_id == deneme_id)
            .order_by(DenemeKonu.ders_kod, DenemeKonu.id)
        ).scalars()
    )


def _deneme_konularini_yaz(
    db: Session, deneme_id: int, konular: list[KonuYanlis]
) -> int:
    """Denemenin yanlış konularını tazeler; geçersiz konu id'leri atlanır."""
    db.execute(delete(DenemeKonu).where(DenemeKonu.deneme_id == deneme_id))
    yazilan = 0
    for satir in konular:
        konu = db.get(Konu, satir.konu_id)
        if konu is None:
            continue
        db.add(
            DenemeKonu(
                deneme_id=deneme_id,
                konu_id=konu.id,
                ders_kod=konu.ders_kod,
                yanlis=max(1, satir.yanlis),
            )
        )
        yazilan += 1
    return yazilan


def _seri_hesapla(db: Session, profil_id: int) -> int:
    """Ardışık çalışılan gün sayısı (bugünden geriye)."""
    tamam_gunler = {
        t for (t,) in db.execute(
            select(PlanItem.tarih).where(
                PlanItem.profil_id == profil_id, PlanItem.durum == "tamam"
            )
        ).all()
    }
    tamam_gunler |= {
        t for (t,) in db.execute(
            select(Calisma.tarih).where(Calisma.profil_id == profil_id)
        ).all()
    }
    seri, gun = 0, date.today()
    while gun in tamam_gunler:
        seri += 1
        gun -= timedelta(days=1)
    return seri


# --------------------------------------------------------------------------
# Meta / profiller
# --------------------------------------------------------------------------
@api.get("/meta")
def meta(db: Session = Depends(get_db)):
    ders_map = _ders_map(db)
    alanlar = []
    for bilgi in ALAN_BILGI:
        kodlar = ALAN_AYT_DERSLERI.get(bilgi["kod"], [])
        alanlar.append(
            {
                **bilgi,
                "ayt_dersleri": [ders_map[k].ad for k in kodlar if k in ders_map],
            }
        )
    return {
        "surum": "0.1.0",
        "alanlar": alanlar,
        "siniflar": [
            {"kod": 11, "ad": "11. sınıf", "not": "Sınav yılı: 2028"},
            {"kod": 12, "ad": "12. sınıf", "not": "Son sınıf"},
            {"kod": 0, "ad": "Mezun", "not": "Okul bitti, sınav hazırlığı"},
        ],
        "beceriler": BECERI_ETIKET,
        "toplam_ders": db.query(Ders).count(),
        "toplam_konu": db.query(Konu).count(),
        "ai_aktif": ai_servis.ai_aktif(db),
        "giris_acik": kapi_acik(),
    }


@api.get("/profiller")
def profiller(db: Session = Depends(get_db)):
    return [p.to_dict() for p in db.execute(select(Profil).order_by(Profil.id)).scalars()]


@api.post("/profil")
def profil_olustur(veri: ProfilGiris, db: Session = Depends(get_db)):
    if veri.alan not in GECERLI_ALANLAR:
        raise HTTPException(400, "Geçersiz alan seçimi")
    if veri.sinif not in GECERLI_SINIFLAR:
        raise HTTPException(400, "Geçersiz sınıf seçimi")

    profil = Profil(
        ad=veri.ad.strip() or "Öğrenci",
        alan=veri.alan,
        sinif=veri.sinif,
        hedef_siralama=max(0, veri.hedef_siralama),
        gunluk_hedef_dk=max(30, min(720, veri.gunluk_hedef_dk)),
        sinav_tarihi=_sinav_tarihi(veri.sinif),
        uyanma_saati=veri.uyanma_saati,
        yatma_saati=veri.yatma_saati,
        okul_baslangic=veri.okul_baslangic,
        okul_bitis=veri.okul_bitis,
        okul_donus=veri.okul_donus,
        olusturma=datetime.now(),
    )
    db.add(profil)
    db.commit()
    db.refresh(profil)
    gunluk_plan_uret(db, profil, gun_sayisi=7)
    return profil.to_dict()


@api.get("/profil/{profil_id}")
def profil_getir(profil_id: int, db: Session = Depends(get_db)):
    return _profil_getir(db, profil_id).to_dict()


@api.patch("/profil/{profil_id}")
def profil_guncelle(profil_id: int, veri: ProfilGuncelle, db: Session = Depends(get_db)):
    profil = _profil_getir(db, profil_id)
    degisti = False
    for alan_adi, deger in veri.model_dump(exclude_none=True).items():
        if alan_adi == "alan" and deger not in GECERLI_ALANLAR:
            raise HTTPException(400, "Geçersiz alan seçimi")
        if alan_adi == "sinif" and deger not in GECERLI_SINIFLAR:
            raise HTTPException(400, "Geçersiz sınıf seçimi")
        setattr(profil, alan_adi, deger)
        degisti = True
    db.commit()
    if degisti:
        db.refresh(profil)
    # Plan; alan, sınıf, süre, hedef sıralama ve gün akışı saatlerine bağlı
    if (
        veri.alan is not None
        or veri.sinif is not None
        or veri.gunluk_hedef_dk is not None
        or veri.hedef_siralama is not None
        or veri.uyanma_saati is not None
        or veri.yatma_saati is not None
        or veri.okul_baslangic is not None
        or veri.okul_bitis is not None
        or veri.okul_donus is not None
    ):
        gunluk_plan_uret(db, profil, gun_sayisi=7)
    return profil.to_dict()


# --------------------------------------------------------------------------
# Panel
# --------------------------------------------------------------------------
@api.get("/panel/{profil_id}")
def panel(profil_id: int, db: Session = Depends(get_db)):
    profil = _profil_getir(db, profil_id)
    ders_map = _ders_map(db)
    konular = _alan_konulari(db, profil)
    konu_map = {k.id: k for k in konular}
    durumlar = _durum_map(db, profil.id)

    # Ders bazlı ilerleme
    ders_ozet: dict[str, dict] = {}
    for konu in konular:
        ders = ders_map.get(konu.ders_kod)
        kayit = ders_ozet.setdefault(
            konu.ders_kod,
            {
                "kod": konu.ders_kod,
                "ad": ders.ad if ders else konu.ders_kod,
                "sinav": ders.sinav if ders else "",
                "renk": ders.renk if ders else "#ea580c",
                "toplam": 0,
                "tamam": 0,
                "tekrar": 0,
            },
        )
        kayit["toplam"] += 1
        durum = durumlar.get(konu.id)
        if durum and durum.durum == "tamam":
            kayit["tamam"] += 1
        elif durum and durum.durum == "tekrar":
            kayit["tekrar"] += 1

    for kayit in ders_ozet.values():
        kayit["yuzde"] = round(100 * kayit["tamam"] / kayit["toplam"]) if kayit["toplam"] else 0
    ders_listesi = sorted(
        ders_ozet.values(), key=lambda d: (ders_map[d["kod"]].sira if d["kod"] in ders_map else 99)
    )

    bugun = date.today()
    # Bugünün maddelerine saat ver (eski planlar da gün akışına oturur)
    zamanlari_yerlestir(db, profil, bugun, bugun)
    plan_bugun = list(
        db.execute(
            select(PlanItem)
            .where(PlanItem.profil_id == profil.id, PlanItem.tarih == bugun)
            .order_by(PlanItem.sira)
        ).scalars()
    )
    bugun_tamam_dk = sum(i.sure_dk for i in plan_bugun if i.durum == "tamam")

    hafta = []
    for i in range(6, -1, -1):
        gun = bugun - timedelta(days=i)
        maddeler = list(
            db.execute(
                select(PlanItem).where(
                    PlanItem.profil_id == profil.id, PlanItem.tarih == gun
                )
            ).scalars()
        )
        hafta.append(
            {
                "tarih": gun.isoformat(),
                "gun": ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"][gun.weekday()],
                "plan_dk": sum(m.sure_dk for m in maddeler),
                "tamam_dk": sum(m.sure_dk for m in maddeler if m.durum == "tamam"),
            }
        )

    son_denemeler = []
    for d in db.execute(
        select(Deneme).where(Deneme.profil_id == profil.id).order_by(Deneme.tarih.desc()).limit(5)
    ).scalars():
        netler = _deneme_netleri(db, d.id)
        son_denemeler.append(
            {
                "id": d.id,
                "tur": d.tur,
                "ad": d.ad,
                "tarih": d.tarih.isoformat(),
                "toplam_net": round(sum(n.net for n in netler), 2),
                "tyt_net": round(sum(n.net for n in netler if n.ders_kod.startswith("TYT-")), 2),
                "ayt_net": round(sum(n.net for n in netler if n.ders_kod.startswith("AYT-")), 2),
                "puan": scoring.puan_tahmini({n.ders_kod: n.net for n in netler}),
            }
        )

    zayif_konular = []
    for konu in konular:
        durum = durumlar.get(konu.id)
        if durum and durum.durum in {"calisiliyor", "tekrar", "tamam"} and durum.guven <= 2:
            zayif_konular.append(
                {
                    "konu_id": konu.id,
                    "ad": konu.ad,
                    "ders_kod": konu.ders_kod,
                    "ders": ders_map[konu.ders_kod].ad if konu.ders_kod in ders_map else "",
                    "durum": durum.durum,
                    "guven": durum.guven,
                    "sinif": konu.sinif,
                }
            )
    zayif_konular.sort(key=lambda k: (k["guven"], -k["sinif"]))

    oncelik = [
        {
            "konu_id": k.id,
            "ad": k.ad,
            "ders_kod": k.ders_kod,
            "ders": ders_map[k.ders_kod].ad if k.ders_kod in ders_map else "",
            "sinif": k.sinif,
            "puan": round(p, 1),
        }
        for k, p in oncelikli_konular(db, profil, limit=6)
    ]

    toplam = len(konular)
    tamam = sum(1 for k in konular if (durumlar.get(k.id) and durumlar[k.id].durum == "tamam"))

    return {
        "profil": profil.to_dict(),
        "kalan_gun": (profil.sinav_tarihi - bugun).days,
        "ilerleme": {
            "toplam": toplam,
            "tamam": tamam,
            "yuzde": round(100 * tamam / toplam) if toplam else 0,
        },
        "dersler": ders_listesi,
        "bugun": {
            "tarih": bugun.isoformat(),
            "hedef_dk": profil.gunluk_hedef_dk,
            "tamam_dk": bugun_tamam_dk,
            "plan": [
                {
                    "id": i.id,
                    "baslik": i.baslik,
                    "tur": i.tur,
                    "sure_dk": i.sure_dk,
                    "durum": i.durum,
                    "ders_kod": i.ders_kod,
                    "renk": ders_map[i.ders_kod].renk if i.ders_kod in ders_map else "#ea580c",
                    "baslangic": i.baslangic or "",
                    "bitis": _saat_ekle(i.baslangic, i.sure_dk or 0),
                    "beceri": _beceri_listesi(konu_map.get(i.konu_id)),
                }
                for i in plan_bugun
            ],
        },
        "hafta": hafta,
        "son_denemeler": son_denemeler,
        "zayif_konular": zayif_konular[:8],
        "oncelikli": oncelik,
        "seri": _seri_hesapla(db, profil.id),
        "hedef": hedef_servis.hedef_ozeti(db, profil),
        "ai_aktif": ai_servis.ai_aktif(db),
    }


@api.get("/hedef/{profil_id}")
def hedef_analizi(profil_id: int, db: Session = Depends(get_db)):
    """Hedef sıralama -> gereken netler -> ders bazlı açık tablosu."""
    profil = _profil_getir(db, profil_id)
    return hedef_servis.hedef_analizi(db, profil)


@api.get("/analiz/{profil_id}")
def analiz(profil_id: int, db: Session = Depends(get_db)):
    """Denemelerdeki doğru/yanlış + konuların YKS ağırlığı -> etkin puan tablosu."""
    profil = _profil_getir(db, profil_id)
    return analiz_servis.analiz_ozeti(db, profil)


# --------------------------------------------------------------------------
# Müfredat ve konu durumu
# --------------------------------------------------------------------------
@api.get("/mufredat/{profil_id}")
def mufredat(profil_id: int, db: Session = Depends(get_db)):
    profil = _profil_getir(db, profil_id)
    ders_map = _ders_map(db)
    konular = _alan_konulari(db, profil)
    durumlar = _durum_map(db, profil.id)

    gruplu: dict[str, dict] = {}
    for konu in sorted(konular, key=lambda k: (k.ders_kod, k.sira)):
        ders = ders_map.get(konu.ders_kod)
        grup = gruplu.setdefault(
            konu.ders_kod,
            {
                "kod": konu.ders_kod,
                "ad": ders.ad if ders else konu.ders_kod,
                "sinav": ders.sinav if ders else "",
                "renk": ders.renk if ders else "#ea580c",
                "soru_sayisi": ders.soru_sayisi if ders else 0,
                "konular": [],
            },
        )
        durum = durumlar.get(konu.id)
        grup["konular"].append(
            {
                **konu.to_dict(),
                "durum": durum.durum if durum else "yok",
                "guven": durum.guven if durum else 0,
                "tekrar_sayisi": durum.tekrar_sayisi if durum else 0,
                "beceri_etiket": [BECERI_ETIKET.get(b, b) for b in (konu.beceri or "").split(",") if b],
            }
        )

    sirali = sorted(gruplu.values(), key=lambda g: (ders_map[g["kod"]].sira if g["kod"] in ders_map else 99, g["kod"]))
    return {"profil": profil.to_dict(), "dersler": sirali}


@api.post("/konu-durum")
def konu_durum_guncelle(veri: KonuDurumGiris, db: Session = Depends(get_db)):
    _profil_getir(db, veri.profil_id)
    if veri.durum not in {"yok", "calisiliyor", "tamam", "tekrar"}:
        raise HTTPException(400, "Geçersiz durum")
    konu = db.get(Konu, veri.konu_id)
    if not konu:
        raise HTTPException(404, "Konu bulunamadı")

    durum = db.execute(
        select(KonuDurum).where(
            KonuDurum.profil_id == veri.profil_id, KonuDurum.konu_id == veri.konu_id
        )
    ).scalar_one_or_none()
    if durum is None:
        durum = KonuDurum(profil_id=veri.profil_id, konu_id=veri.konu_id)
        db.add(durum)

    durum.durum = veri.durum
    durum.guven = max(0, min(5, veri.guven))
    durum.son_calisma = datetime.now()
    if veri.durum == "tamam":
        durum.tekrar_sayisi = (durum.tekrar_sayisi or 0) + 1
        aralik = TEKRAR_ARALIKLARI[min(durum.tekrar_sayisi - 1, len(TEKRAR_ARALIKLARI) - 1)]
        durum.tekrar_tarihi = date.today() + timedelta(days=aralik)
    db.commit()
    return {"ok": True, "durum": durum.durum, "tekrar_tarihi": durum.tekrar_tarihi.isoformat() if durum.tekrar_tarihi else None}


# --------------------------------------------------------------------------
# Plan
# --------------------------------------------------------------------------
@api.get("/plan/{profil_id}")
def plan_getir(profil_id: int, gun: int = 7, db: Session = Depends(get_db)):
    """7 günlük program: her gün rütin + çalışma maddeleriyle gün akışı."""
    profil = _profil_getir(db, profil_id)
    ders_map = _ders_map(db)
    baslangic = date.today()
    gun = max(1, min(30, gun))
    bitis = baslangic + timedelta(days=gun - 1)

    # Daha önce üretilmiş planların saatleri de tamamlanır (idempotent)
    zamanlari_yerlestir(db, profil, baslangic, bitis)

    konu_map = {k.id: k for k in _alan_konulari(db, profil)}
    ders_renk = {kod: d.renk for kod, d in ders_map.items()}
    tum_maddeler: list[PlanItem] = []
    sonuc = []
    for i in range(gun):
        tarih = baslangic + timedelta(days=i)
        maddeler = list(
            db.execute(
                select(PlanItem)
                .where(PlanItem.profil_id == profil.id, PlanItem.tarih == tarih)
                .order_by(PlanItem.sira, PlanItem.id)
            ).scalars()
        )
        tum_maddeler.extend(maddeler)
        cerceve = gun_cercevesi(tarih, profil, any(m.tur == "deneme" for m in maddeler))
        okul_dk = sum(_saat_farki(d, "okul") for d in cerceve["rutin"])
        mola_dk = sum(_saat_farki(d, "mola") for d in cerceve["rutin"])
        calisma_dk = sum(m.sure_dk or 0 for m in maddeler)
        uyku_dk = 24 * 60 - (_saat_dk(cerceve["yatis"]) - _saat_dk(cerceve["uyanma"]))
        sonuc.append(
            {
                "tarih": tarih.isoformat(),
                "gun_adi": cerceve["gun_adi"],
                "bugun": tarih == baslangic,
                "gun_tipi": cerceve["tip"],
                "gun_tipi_etiketi": cerceve["tip_etiketi"],
                "uyanma": cerceve["uyanma"],
                "yatis": cerceve["yatis"],
                "okul": cerceve["okul"],
                "okul_donus": cerceve.get("okul_donus", ""),
                "akis": gun_akisi(cerceve, maddeler, ders_renk),
                "maddeler": [
                    {
                        "id": m.id,
                        "baslik": m.baslik,
                        "tur": m.tur,
                        "sure_dk": m.sure_dk,
                        "durum": m.durum,
                        "ders_kod": m.ders_kod,
                        "ders": ders_map[m.ders_kod].ad if m.ders_kod in ders_map else "",
                        "renk": ders_map[m.ders_kod].renk if m.ders_kod in ders_map else "#ea580c",
                        "baslangic": m.baslangic or "",
                        "bitis": _saat_ekle(m.baslangic, m.sure_dk or 0),
                        "beceri": _beceri_listesi(konu_map.get(m.konu_id)),
                        "beceri_etiket": [
                            BECERI_ETIKET.get(b, b)
                            for b in _beceri_listesi(konu_map.get(m.konu_id))
                        ],
                    }
                    for m in maddeler
                ],
                "ozet": {
                    "calisma_dk": calisma_dk,
                    "okul_dk": okul_dk,
                    "mola_dk": mola_dk,
                    "uyku_saat": round(uyku_dk / 60, 1),
                },
                "notlar": cerceve["notlar"],
            }
        )
    yanlislar = _deneme_yanlis_map(db, profil)
    # Pazar SD öz değerlendirmesi rütinde yer aldığı için dengeye ayrıca eklenir
    sd_dk = sum(
        _saat_farki(dilim, "gelisim")
        for gun in sonuc
        for dilim in gun["akis"]
        if dilim.get("kaynak") == "rutin"
    )
    return {
        "zaman_cercevesi": {
            "uyanma": sonuc[0]["uyanma"] if sonuc else "",
            "yatis": sonuc[0]["yatis"] if sonuc else "",
            "okul_baslangic": profil.okul_baslangic or "",
            "okul_bitis": profil.okul_bitis or "",
            "okul_donus": sonuc[0].get("okul_donus", "") if sonuc else "",
            "okul_donus_girildi": bool(profil.okul_donus),
        },
        "gunler": sonuc,
        "beceri_dengesi": beceri_dengesi(tum_maddeler, konu_map, ek={"SD": sd_dk}),
        "deneme_odagi": deneme_odagi(tum_maddeler, konu_map, yanlislar),
        "pdr_ilkeleri": pdr_ilkeleri(),
    }


@api.post("/plan/{profil_id}/uret")
def plan_uret(profil_id: int, gun: int = 7, db: Session = Depends(get_db)):
    profil = _profil_getir(db, profil_id)
    eklenen = gunluk_plan_uret(db, profil, gun_sayisi=max(1, min(30, gun)))
    return {"eklenen": eklenen}


@api.get("/plan/{profil_id}/ozet")
def plan_ozet(profil_id: int, gun: int = 7, db: Session = Depends(get_db)):
    """Haftalık özet: ders başına dakika, tamamlanma ve deneme günleri."""
    profil = _profil_getir(db, profil_id)
    return plan_ozeti(db, profil, gun_sayisi=max(1, min(31, gun)))


@api.get("/plan/{profil_id}/aylik")
def plan_aylik(profil_id: int, hafta: int = 4, db: Session = Depends(get_db)):
    """Aylık program görünümü: hafta hafta odak konular ve dağılım."""
    profil = _profil_getir(db, profil_id)
    return aylik_plan(db, profil, hafta_sayisi=max(1, min(8, hafta)))


@api.post("/plan/{profil_id}/aylik-uret")
def plan_aylik_uret(profil_id: int, hafta: int = 4, db: Session = Depends(get_db)):
    """4 haftalık takvimi doldurur (cumartesi deneme, pazar tekrar)."""
    profil = _profil_getir(db, profil_id)
    eklenen = aylik_plan_uret(db, profil, hafta_sayisi=max(1, min(8, hafta)))
    return {"eklenen": eklenen}


@api.post("/plan-madde/{madde_id}")
def plan_madde_durum(madde_id: int, durum: str = "tamam", db: Session = Depends(get_db)):
    madde = db.get(PlanItem, madde_id)
    if not madde:
        raise HTTPException(404, "Plan maddesi bulunamadı")
    if durum not in {"bekliyor", "tamam"}:
        raise HTTPException(400, "Geçersiz durum")

    onceki = madde.durum
    madde.durum = durum

    if durum == "tamam" and onceki != "tamam":
        db.add(
            Calisma(
                profil_id=madde.profil_id,
                konu_id=madde.konu_id,
                tarih=madde.tarih,
                tur=madde.tur,
                sure_dk=madde.sure_dk,
            )
        )
        if madde.konu_id and madde.tur in {"konu", "tekrar"}:
            kayit = db.execute(
                select(KonuDurum).where(
                    KonuDurum.profil_id == madde.profil_id, KonuDurum.konu_id == madde.konu_id
                )
            ).scalar_one_or_none()
            if kayit is None:
                kayit = KonuDurum(profil_id=madde.profil_id, konu_id=madde.konu_id)
                db.add(kayit)
            if madde.tur == "tekrar":
                kayit.guven = min(5, (kayit.guven or 0) + 1)
                kayit.durum = "tamam"
            else:
                kayit.durum = "calisiliyor"
                kayit.guven = max(kayit.guven or 0, 2)
            kayit.son_calisma = datetime.now()
    db.commit()
    return {"ok": True, "durum": madde.durum}


# --------------------------------------------------------------------------
# Denemeler
# --------------------------------------------------------------------------
@api.post("/deneme")
def deneme_ekle(veri: DenemeGiris, db: Session = Depends(get_db)):
    profil = _profil_getir(db, veri.profil_id)
    if not veri.sonuclar:
        raise HTTPException(400, "En az bir ders sonucu girilmeli")

    deneme = Deneme(
        profil_id=profil.id,
        tur=veri.tur,
        ad=veri.ad,
        tarih=veri.tarih or date.today(),
        sure_dk=veri.sure_dk,
        notlar=veri.notlar,
    )
    db.add(deneme)
    db.commit()
    db.refresh(deneme)

    satirlar = []
    for s in veri.sonuclar:
        net = scoring.net_hesapla(s.dogru, s.yanlis)
        db.add(
            DenemeSonuc(
                deneme_id=deneme.id,
                ders_kod=s.ders_kod,
                dogru=s.dogru,
                yanlis=s.yanlis,
                bos=s.bos,
                net=net,
            )
        )
        satirlar.append(
            {"ders_kod": s.ders_kod, "dogru": s.dogru, "yanlis": s.yanlis, "bos": s.bos, "net": net}
        )
    db.commit()

    # Ders sonuçları yazıldıktan sonra işaretlenen yanlış konular eklenir
    _deneme_konularini_yaz(db, deneme.id, veri.konular)
    db.commit()

    ozet = scoring.deneme_ozeti(satirlar, profil.alan)
    return {"id": deneme.id, "ozet": ozet}


@api.get("/denemeler/{profil_id}")
def denemeler(profil_id: int, db: Session = Depends(get_db)):
    _profil_getir(db, profil_id)
    ders_map = _ders_map(db)
    konu_adlari = {k.id: k.ad for k in db.execute(select(Konu)).scalars()}
    sonuc = []
    for d in db.execute(
        select(Deneme).where(Deneme.profil_id == profil_id).order_by(Deneme.tarih.desc(), Deneme.id.desc())
    ).scalars():
        netler = _deneme_netleri(db, d.id)
        konu_yanlislari = _deneme_konulari(db, d.id)
        ozet = scoring.deneme_ozeti(
            [{"ders_kod": n.ders_kod, "net": n.net, "dogru": n.dogru, "yanlis": n.yanlis, "bos": n.bos} for n in netler],
            "",
        )
        sonuc.append(
            {
                "id": d.id,
                "tur": d.tur,
                "ad": d.ad,
                "tarih": d.tarih.isoformat(),
                "sure_dk": d.sure_dk,
                "notlar": d.notlar,
                "toplam_net": round(sum(n.net for n in netler), 2),
                "puan": ozet["puan"],
                "zayif_dersler": [
                    {"kod": k, "ad": ders_map[k].ad if k in ders_map else k} for k in ozet["zayif_dersler"]
                ],
                "konular": [
                    {
                        "konu_id": k.konu_id,
                        "ders_kod": k.ders_kod,
                        "ders": ders_map[k.ders_kod].ad if k.ders_kod in ders_map else k.ders_kod,
                        "konu": konu_adlari.get(k.konu_id, ""),
                        "yanlis": k.yanlis,
                    }
                    for k in konu_yanlislari
                ],
                "satirlar": [
                    {
                        "ders_kod": n.ders_kod,
                        "ders": ders_map[n.ders_kod].ad if n.ders_kod in ders_map else n.ders_kod,
                        "renk": ders_map[n.ders_kod].renk if n.ders_kod in ders_map else "#ea580c",
                        "dogru": n.dogru,
                        "yanlis": n.yanlis,
                        "bos": n.bos,
                        "net": n.net,
                    }
                    for n in netler
                ],
            }
        )
    return sonuc


@api.delete("/deneme/{deneme_id}")
def deneme_sil(deneme_id: int, db: Session = Depends(get_db)):
    deneme = db.get(Deneme, deneme_id)
    if not deneme:
        raise HTTPException(404, "Deneme bulunamadı")
    db.execute(delete(DenemeSonuc).where(DenemeSonuc.deneme_id == deneme_id))
    db.execute(delete(DenemeKonu).where(DenemeKonu.deneme_id == deneme_id))
    db.delete(deneme)
    db.commit()
    return {"ok": True}


@api.post("/deneme/{deneme_id}/konular")
def deneme_konulari_guncelle(
    deneme_id: int, veri: KonuYanlisGiris, db: Session = Depends(get_db)
):
    """Denemenin yanlış konularını tazeler; konu bazlı analiz buradan beslenir."""
    deneme = db.get(Deneme, deneme_id)
    if not deneme:
        raise HTTPException(404, "Deneme bulunamadı")
    yazilan = _deneme_konularini_yaz(db, deneme_id, veri.konular)
    db.commit()
    return {"ok": True, "konu_sayisi": yazilan}


# --------------------------------------------------------------------------
# Deneme değerlendirmesi ve takvimi
# --------------------------------------------------------------------------
@api.get("/analiz/{profil_id}/degerlendirme")
def analiz_degerlendirme(profil_id: int, db: Session = Depends(get_db)):
    """Saklanan son yapay zekâ değerlendirmesi; yoksa {"var": false}."""
    return degerlendirme_servis.kayitli_degerlendirme(db, _profil_getir(db, profil_id))


@api.post("/analiz/{profil_id}/degerlendir")
def analiz_degerlendir(profil_id: int, siklik: int = 0, db: Session = Depends(get_db)):
    """Deneme + konu analizini yorumlar, deneme sıklığını ve takvimini önerir.

    ``siklik=3`` ya da ``7`` verilirse öneri yerine bu aralık kullanılır;
    ``0`` bırakılırsa hedef açığına göre otomatik seçilir.
    """
    return degerlendirme_servis.degerlendir(db, _profil_getir(db, profil_id), siklik)


@api.get("/deneme-takvimi/{profil_id}")
def deneme_takvimi_onizle(
    profil_id: int, siklik: int = 7, hafta: int = 4, db: Session = Depends(get_db)
):
    """Deneme günlerini plana yazmadan gösterir."""
    return degerlendirme_servis.deneme_takvimi(
        db, _profil_getir(db, profil_id), siklik=siklik, hafta=hafta
    )


@api.post("/plan/{profil_id}/deneme-takvimi")
def deneme_takvimi_uret(
    profil_id: int, siklik: int = 7, hafta: int = 4, db: Session = Depends(get_db)
):
    """Sınav günlerini + deneme analizi bloklarını plana yazar."""
    return degerlendirme_servis.deneme_takvimi_uret(
        db, _profil_getir(db, profil_id), siklik=siklik, hafta=hafta
    )


# --------------------------------------------------------------------------
# Çalışma günlüğü
# --------------------------------------------------------------------------
@api.post("/calisma")
def calisma_ekle(veri: CalismaGiris, db: Session = Depends(get_db)):
    _profil_getir(db, veri.profil_id)
    db.add(
        Calisma(
            profil_id=veri.profil_id,
            konu_id=veri.konu_id,
            tarih=date.today(),
            tur=veri.tur,
            sure_dk=veri.sure_dk,
            dogru=veri.dogru,
            yanlis=veri.yanlis,
            notlar=veri.notlar,
        )
    )
    db.commit()
    return {"ok": True}


# --------------------------------------------------------------------------
# Yapay zekâ koç
# --------------------------------------------------------------------------
@api.get("/koc/{profil_id}")
def koc_gecmis(profil_id: int, db: Session = Depends(get_db)):
    _profil_getir(db, profil_id)
    mesajlar = list(
        db.execute(
            select(AiMesaj).where(AiMesaj.profil_id == profil_id).order_by(AiMesaj.id)
        ).scalars()
    )
    return [
        {
            "rol": m.rol,
            "icerik": m.icerik,
            "kaynak": m.kaynak,
            "tarih": m.olusturma.isoformat(timespec="minutes"),
        }
        for m in mesajlar
    ]


@api.post("/koc/{profil_id}")
def koc_mesaj(profil_id: int, veri: KocGiris, db: Session = Depends(get_db)):
    profil = _profil_getir(db, profil_id)
    gecmis = [
        {"rol": m.rol, "icerik": m.icerik}
        for m in db.execute(
            select(AiMesaj).where(AiMesaj.profil_id == profil_id).order_by(AiMesaj.id.desc()).limit(8)
        ).scalars()
    ][::-1]

    db.add(AiMesaj(profil_id=profil_id, rol="kullanici", icerik=veri.mesaj, kaynak="kullanici"))
    db.commit()

    yanit = ai_servis.koc_yanitla(db, profil, veri.mesaj, gecmis)
    db.add(AiMesaj(profil_id=profil_id, rol="koc", icerik=yanit["metin"], kaynak=yanit["kaynak"]))
    db.commit()
    return yanit


@api.post("/koc/{profil_id}/soru")
def koc_soru(profil_id: int, konu: str, adet: int = 3, zorluk: str = "orta", db: Session = Depends(get_db)):
    profil = _profil_getir(db, profil_id)
    return ai_servis.soru_uret(db, profil, konu, adet=adet, zorluk=zorluk)


@api.get("/ai/durum")
def ai_durum(db: Session = Depends(get_db)):
    anahtar, model = ai_servis.anahtar_getir(db)
    return {"aktif": bool(anahtar), "model": model, "anahtar_var": bool(anahtar)}


@api.post("/ai/anahtar")
def ai_anahtar_kaydet(veri: AnahtarGiris, db: Session = Depends(get_db)):
    """Anahtarı günceller. Boş anahtar gönderilirse mevcut anahtar korunur."""
    anahtar, model = ai_servis.anahtar_getir(db)
    yeni_anahtar = "" if veri.sil else (veri.anahtar.strip() or anahtar)
    yeni_model = veri.model.strip() or model

    for ad, deger in (("gemini_api_key", yeni_anahtar), ("gemini_model", yeni_model)):
        kayit = db.get(Ayar, ad)
        if kayit is None:
            db.add(Ayar(anahtar=ad, deger=deger))
        else:
            kayit.deger = deger
    db.commit()
    return {"aktif": bool(yeni_anahtar)}


@api.post("/ai/test")
def ai_test(veri: AnahtarTest, db: Session = Depends(get_db)):
    """Kayıtlı ya da yeni girilen anahtarla Gemini bağlantısını dener.

    Anahtar kaydedilmez; kullanıcı önce deneyip sonra kaydedebilir.
    """
    kayitli_anahtar, kayitli_model = ai_servis.anahtar_getir(db)
    anahtar = veri.anahtar.strip() or kayitli_anahtar
    model = veri.model.strip() or kayitli_model
    if not anahtar:
        return {
            "ok": False,
            "kod": 0,
            "model": model,
            "mesaj": "Önce bir API anahtarı gir (anahtarsız yerel koç çalışır).",
        }
    return ai_servis.baglanti_test(anahtar, model)


@api.get("/yedek")
def yedek_indir():
    """Veritabanı dosyasını indirir (yalnızca SQLite kurulumlarında)."""
    from fastapi.responses import FileResponse

    from .database import DB_YOLU

    if DB_YOLU is None:
        raise HTTPException(
            409, "Bulut veritabanında dosya yedeği yok; Neon panosundan yedek alınabilir."
        )
    if not DB_YOLU.exists():
        raise HTTPException(404, "Veritabanı dosyası bulunamadı")
    return FileResponse(DB_YOLU, media_type="application/octet-stream", filename="pusula-yedek.db")


@api.get("/saglik")
def saglik(db: Session = Depends(get_db)):
    return {
        "durum": "calisiyor",
        "ders": db.query(Ders).count(),
        "konu": db.query(Konu).count(),
        "profil": db.query(Profil).count(),
    }
