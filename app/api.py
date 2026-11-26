# -*- coding: utf-8 -*-
"""A-KEY HTTP API'si."""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from . import auth, yetki
from . import seed as seed_servis
from .data import ALAN_AYT_DERSLERI, BECERI_ETIKET, TUM_DERSLER, alan_ders_kodlari
from .database import get_db
from .models import (
    ROL_ETIKET,
    AiMesaj,
    Ayar,
    Calisma,
    Deneme,
    DenemeKonu,
    DenemeSonuc,
    Ders,
    Konu,
    KonuDurum,
    Kullanici,
    PlanItem,
    Profil,
    VeliOgrenci,
)
from .services import ai as ai_servis
from .services import analiz as analiz_servis
from .services import degerlendirme as degerlendirme_servis
from .services import ders_programi as okul_servisi
from .services import hedef as hedef_servis
from .services import plan_analizi as plan_analiz_servisi
from .services import scoring
from .services import sinif as sinif_servisi
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

api = APIRouter(prefix="/api", tags=["a-key"])

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


class KonuGiris(BaseModel):
    """Müfredata yeni konu ekleme (yalnız yönetici)."""

    ders_kod: str = Field(min_length=2, max_length=16)
    ad: str = Field(min_length=2, max_length=160)
    sinif: int = 11
    agirlik: int = Field(default=1, ge=1, le=5)
    sure_dk: int = Field(default=90, ge=10, le=600)
    beceri: str = ""
    onkosul: str = ""


class KonuDuzenle(BaseModel):
    """Konu satırının alanlarını günceller; verilmeyen alan değişmez."""

    ders_kod: str | None = Field(default=None, min_length=2, max_length=16)
    ad: str | None = Field(default=None, min_length=2, max_length=160)
    sinif: int | None = None
    agirlik: int | None = Field(default=None, ge=1, le=5)
    sure_dk: int | None = Field(default=None, ge=10, le=600)
    beceri: str | None = None
    onkosul: str | None = None
    sira: int | None = Field(default=None, ge=0, le=9999)


class DersGiris(BaseModel):
    """Müfredata yeni ders ekleme (yalnız yönetici)."""

    kod: str = Field(min_length=2, max_length=16, pattern=r"^[A-Za-z0-9-]+$")
    ad: str = Field(min_length=2, max_length=80)
    sinav: str = "TYT"
    alanlar: str = "ortak"
    soru_sayisi: int = Field(default=0, ge=0, le=200)
    renk: str = Field(default="#ea580c", pattern=r"^#[0-9a-fA-F]{6}$")
    sira: int = Field(default=90, ge=0, le=999)


class DersDuzenle(BaseModel):
    ad: str | None = Field(default=None, min_length=2, max_length=80)
    sinav: str | None = None
    alanlar: str | None = None
    soru_sayisi: int | None = Field(default=None, ge=0, le=200)
    renk: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    sira: int | None = Field(default=None, ge=0, le=999)


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
    """Denemede konu bazlı doğru/yanlış/boş sayısı.

    Eski istemciler yalnız ``yanlis`` gönderir; doğru ve boş alanları 0 kalır ve
    konu tamamen yanlış sayılır (geriye uyum).
    """

    konu_id: int
    dogru: int = 0
    yanlis: int = 1
    bos: int = 0


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


class PlanMaddeGiris(BaseModel):
    """Analiz sayfasından açık konuyu plana ekleme."""

    konu_id: int
    tarih: date | None = None
    sure_dk: int = 0
    tur: str = "konu"


class CalismaGiris(BaseModel):
    profil_id: int
    konu_id: int | None = None
    sure_dk: int = 60
    tur: str = "konu"
    dogru: int = 0
    yanlis: int = 0
    notlar: str = ""


class YeniProfil(BaseModel):
    """Öğrenci hesabı açılırken oluşturulacak profil (sınıfı yönetici belirler)."""

    ad: str = Field(default="Öğrenci", max_length=80)
    sinif: int = 11
    alan: str = "sayisal"


class KullaniciGiris(BaseModel):
    """İlk kurulum ve kullanıcı ekleme gövdesi."""

    kullanici: str = Field(min_length=3, max_length=40)
    ad: str = ""
    sifre: str = Field(min_length=6, max_length=128)


class KullaniciKayit(BaseModel):
    """Yönetici panelinden veli/öğrenci tanımlama."""

    kullanici_adi: str = Field(min_length=3, max_length=40)
    ad_soyad: str = ""
    rol: str = "ogrenci"
    sifre: str = Field(min_length=6, max_length=128)
    profil_id: int | None = None       # öğrenci: bağlı olduğu profil
    profil_idler: list[int] = []       # veli: gördüğü öğrenciler
    # Öğrenci hesabıyla birlikte yeni öğrenci kaydı açılabilir
    yeni_profil: YeniProfil | None = None


class KullaniciGuncelle(BaseModel):
    """Kullanıcı düzenleme / şifre sıfırlama."""

    ad_soyad: str | None = None
    rol: str | None = None
    sifre: str | None = None
    profil_id: int | None = None
    profil_idler: list[int] | None = None
    aktif: bool | None = None


class SifreDegisiklik(BaseModel):
    """Oturum sahibinin kendi şifresini değiştirmesi."""

    mevcut: str = Field(min_length=1, max_length=128)
    yeni: str = Field(min_length=6, max_length=128)


class DersProgramiGiris(BaseModel):
    """Haftalık okul çizelgesi: hücre listesi ya da sınıf şablonu."""

    hucreler: list[dict] = []
    sablon_uygula: int | None = None   # 11 / 12: hazır çizelgeyi yükle


class IslenenKonuGiris(BaseModel):
    """Okulda o gün işlenen konular; boş liste günün girişini temizler."""

    tarih: date | None = None
    konu_idler: list[int] = []


# --------------------------------------------------------------------------
# Yardımcılar
# --------------------------------------------------------------------------
def _profil_getir(db: Session, profil_id: int) -> Profil:
    # Veri kapsamı tek noktadan uygulanır: veli yalnız kendi öğrencisini,
    # öğrenci yalnız kendini görür (yönetici ve kapısız mod sınırsız).
    yetki.profil_kontrol(db, profil_id)
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
    # Gömülü dersler (veri modülü) + yöneticinin eklediği dersler birlikte
    kodlar = set(alan_ders_kodlari(profil.alan))
    for ders in db.execute(select(Ders)).scalars():
        alanlar = [a.strip() for a in (ders.alanlar or "").split(",") if a.strip()]
        if "ortak" in alanlar or profil.alan in alanlar:
            kodlar.add(ders.kod)
    if not kodlar:
        return []
    return list(db.execute(select(Konu).where(Konu.ders_kod.in_(kodlar))).scalars())


def _durum_map(db: Session, profil_id: int) -> dict[int, KonuDurum]:
    return {
        d.konu_id: d
        for d in db.execute(select(KonuDurum).where(KonuDurum.profil_id == profil_id)).scalars()
    }


def _ders_map(db: Session) -> dict[str, Ders]:
    return {d.kod: d for d in db.execute(select(Ders)).scalars()}


def _ders_getir(db: Session, kod: str) -> Ders | None:
    """Dersi koduyla bulur (``db.get`` birincil anahtar olan ``id`` ile arar)."""
    return db.execute(select(Ders).where(Ders.kod == kod)).scalars().first()


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
    db: Session, deneme_id: int, konular: list[KonuYanlis], dersler: set[str] | None = None
) -> int:
    """Denemenin konu satırlarını tazeler; geçersiz konu id'leri atlanır.

    ``dersler`` verilirse konu bu derslerden birine ait olmalıdır (denemede
    karşılığı olmayan dersin konusu sessizce atlanır). Üç değeri de boş olan
    satır kaydedilmez.
    """
    db.execute(delete(DenemeKonu).where(DenemeKonu.deneme_id == deneme_id))
    yazilan = 0
    for satir in konular:
        konu = db.get(Konu, satir.konu_id)
        if konu is None:
            continue
        if dersler is not None and konu.ders_kod not in dersler:
            continue  # denemede bu dersin satırı yok
        dogru = max(0, satir.dogru)
        yanlis = max(0, satir.yanlis)
        bos = max(0, satir.bos)
        if not (dogru or yanlis or bos):
            continue
        db.add(
            DenemeKonu(
                deneme_id=deneme_id,
                konu_id=konu.id,
                ders_kod=konu.ders_kod,
                dogru=dogru,
                yanlis=yanlis,
                bos=bos,
            )
        )
        yazilan += 1
    return yazilan


def _konu_toplamlarini_derslere_yaz(db: Session, deneme_id: int) -> list[str]:
    """Konusu girilip ders satırı boş bırakılan dersleri konu toplamıyla tamamlar.

    Ders satırı zaten girilmişse kullanıcının değeri korunur.
    """
    mevcut = {
        kod
        for (kod,) in db.execute(
            select(DenemeSonuc.ders_kod).where(DenemeSonuc.deneme_id == deneme_id)
        ).all()
    }
    toplamlar: dict[str, dict[str, int]] = {}
    for satir in db.execute(select(DenemeKonu).where(DenemeKonu.deneme_id == deneme_id)).scalars():
        kayit = toplamlar.setdefault(satir.ders_kod, {"dogru": 0, "yanlis": 0, "bos": 0})
        kayit["dogru"] += satir.dogru or 0
        kayit["yanlis"] += satir.yanlis or 0
        kayit["bos"] += satir.bos or 0
    eklenen: list[str] = []
    for ders_kod, toplam in toplamlar.items():
        if not ders_kod or ders_kod in mevcut:
            continue
        db.add(
            DenemeSonuc(
                deneme_id=deneme_id,
                ders_kod=ders_kod,
                dogru=toplam["dogru"],
                yanlis=toplam["yanlis"],
                bos=toplam["bos"],
                net=scoring.net_hesapla(toplam["dogru"], toplam["yanlis"]),
            )
        )
        eklenen.append(ders_kod)
    return eklenen


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
        "surum": "3.6.1",
        "alanlar": alanlar,
        "siniflar": [
            {"kod": 11, "ad": "11. sınıf", "not": "Kapsam: 9-10 TYT + 11. sınıf AYT"},
            {"kod": 12, "ad": "12. sınıf", "not": "Kapsam: 9-10 TYT + 11-12. sınıf AYT"},
            {"kod": 0, "ad": "Mezun", "not": "Kapsam: tüm TYT + AYT konuları"},
        ],
        "beceriler": BECERI_ETIKET,
        "toplam_ders": db.query(Ders).count(),
        "toplam_konu": db.query(Konu).count(),
        "ai_aktif": ai_servis.ai_aktif(db),
        "oturum": _oturum_bilgisi(db),
    }


@api.get("/profiller")
def profiller(db: Session = Depends(get_db)):
    """Oturum sahibinin görebildiği profiller (öğrenci yalnız kendini görür)."""
    izinli = yetki.erisilebilir_profil_idleri(db)
    satirlar = db.execute(select(Profil).order_by(Profil.id)).scalars()
    return [p.to_dict() for p in satirlar if izinli is None or p.id in izinli]


def _profil_kaydet(
    db: Session, ad: str, sinif: int, alan: str, **ek_alanlar
) -> Profil:
    """Profil satırını doğrulayıp ekler (commit ve plan üretimi çağıranın işi)."""
    if alan not in GECERLI_ALANLAR:
        raise HTTPException(400, "Geçersiz alan seçimi")
    if sinif not in GECERLI_SINIFLAR:
        raise HTTPException(400, "Geçersiz sınıf seçimi")
    profil = Profil(
        ad=(ad or "").strip() or "Öğrenci",
        alan=alan,
        sinif=sinif,
        sinav_tarihi=_sinav_tarihi(sinif),
        olusturma=datetime.now(),
        **ek_alanlar,
    )
    db.add(profil)
    db.flush()
    return profil


@api.post("/profil")
def profil_olustur(veri: ProfilGiris, db: Session = Depends(get_db)):
    # Öğrenci kaydını ve sınıfını yalnız yönetici açar (veli/öğrenci kapsamı dağıtamaz)
    yetki.yonetici_kontrol()
    profil = _profil_kaydet(
        db,
        veri.ad,
        veri.sinif,
        veri.alan,
        hedef_siralama=max(0, veri.hedef_siralama),
        gunluk_hedef_dk=max(30, min(720, veri.gunluk_hedef_dk)),
        uyanma_saati=veri.uyanma_saati,
        yatma_saati=veri.yatma_saati,
        okul_baslangic=veri.okul_baslangic,
        okul_bitis=veri.okul_bitis,
        okul_donus=veri.okul_donus,
    )
    db.commit()
    db.refresh(profil)
    gunluk_plan_uret(db, profil, gun_sayisi=7)
    return profil.to_dict()


@api.get("/profil/{profil_id}")
def profil_getir(profil_id: int, db: Session = Depends(get_db)):
    return _profil_getir(db, profil_id).to_dict()


@api.patch("/profil/{profil_id}")
def profil_guncelle(profil_id: int, veri: ProfilGuncelle, db: Session = Depends(get_db)):
    yetki.yazma_kontrol("profil")
    profil = _profil_getir(db, profil_id)
    # Sınıf; müfredat kapsamını ve planı belirlediği için yalnız yöneticiye açık
    if veri.sinif is not None and veri.sinif != profil.sinif and not yetki.yonetici_mi():
        raise HTTPException(403, "Sınıf bilgisini yalnız yönetici değiştirebilir.")
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


@api.delete("/profil/{profil_id}")
def profil_sil(profil_id: int, db: Session = Depends(get_db)):
    """Öğrenci kaydını ve bağlı verilerini siler (yalnız yönetici)."""
    yetki.yonetici_kontrol()
    profil = db.get(Profil, profil_id)
    if profil is None:
        raise HTTPException(404, "Profil bulunamadı")
    bagli = db.execute(
        select(func.count(Kullanici.id)).where(Kullanici.profil_id == profil_id)
    ).scalar()
    if bagli:
        raise HTTPException(
            400, "Bu öğrenciye bağlı giriş hesabı var; önce hesabı sil veya başka öğrenciye taşı"
        )
    # Yabancı anahtarlar SQLite'ta zorlanmaz ama Postgres'te zorlanır: elle temizlenir
    denemeler = select(Deneme.id).where(Deneme.profil_id == profil_id)
    db.execute(delete(DenemeKonu).where(DenemeKonu.deneme_id.in_(denemeler)))
    db.execute(delete(DenemeSonuc).where(DenemeSonuc.deneme_id.in_(denemeler)))
    db.execute(delete(Deneme).where(Deneme.profil_id == profil_id))
    for model in (PlanItem, Calisma, KonuDurum, AiMesaj):
        db.execute(delete(model).where(model.profil_id == profil_id))
    db.execute(delete(VeliOgrenci).where(VeliOgrenci.profil_id == profil_id))
    db.delete(profil)
    db.commit()
    return {"ok": True}


# --------------------------------------------------------------------------
# Oturum ve kullanıcı tanımları
# --------------------------------------------------------------------------
def _oturum_bilgisi(db: Session) -> dict:
    """Üst bar ve menü için oturum sahibinin kimliği ve kapsamı."""
    kullanici = yetki.mevcut_kullanici()
    if kullanici is None:
        # Giriş kapısı kapalı (yerel deneme/test): tam yetkili varsayılır
        return {
            "ad": "Yerel",
            "kullanici_adi": "yerel",
            "rol": "yonetici",
            "rol_etiketi": "Yönetici",
            "profil_id": None,
            "profil_idler": None,
            "giris_zorunlu": False,
        }
    izinli = yetki.erisilebilir_profil_idleri(db, kullanici)
    return {
        "ad": kullanici.ad_soyad or kullanici.kullanici_adi,
        "kullanici_adi": kullanici.kullanici_adi,
        "rol": kullanici.rol,
        "rol_etiketi": kullanici.rol_etiketi,
        "profil_id": kullanici.profil_id,
        "profil_idler": sorted(izinli) if izinli is not None else None,
        "giris_zorunlu": True,
    }


def _veli_profilleri(db: Session, veli_id: int) -> list[int]:
    return sorted(
        db.execute(
            select(VeliOgrenci.profil_id).where(VeliOgrenci.veli_id == veli_id)
        ).scalars()
    )


def _kullanici_dict(db: Session, kullanici: Kullanici) -> dict:
    d = kullanici.to_dict()
    d["profil_idler"] = _veli_profilleri(db, kullanici.id) if kullanici.rol == "veli" else []
    if kullanici.profil_id:
        profil = db.get(Profil, kullanici.profil_id)
        d["profil_adi"] = profil.ad if profil else ""
    else:
        d["profil_adi"] = ""
    return d


def _veli_baglantilarini_yaz(db: Session, veli_id: int, profil_idler: list[int]) -> None:
    """Velinin gördüğü öğrenci listesini baştan yazar."""
    db.execute(delete(VeliOgrenci).where(VeliOgrenci.veli_id == veli_id))
    for profil_id in dict.fromkeys(profil_idler):
        if db.get(Profil, profil_id) is None:
            raise HTTPException(400, f"Öğrenci bulunamadı: {profil_id}")
        db.add(VeliOgrenci(veli_id=veli_id, profil_id=profil_id))


@api.post("/kurulum")
def kurulum_yap(veri: KullaniciGiris, db: Session = Depends(get_db)):
    """İlk yönetici hesabını oluşturur (yalnız hesap yokken)."""
    if not auth.kurulum_gerekli(db):
        raise HTTPException(409, "Kurulum zaten yapılmış")
    hata = auth.kullanici_adi_uygun(veri.kullanici) or auth.sifre_uygun(veri.sifre)
    if hata:
        raise HTTPException(400, hata)
    kullanici = Kullanici(
        kullanici_adi=veri.kullanici.strip(),
        ad_soyad=veri.ad.strip() or "Yönetici",
        sifre_hash=auth.sifre_ozetle(veri.sifre),
        rol="yonetici",
        aktif=True,
    )
    db.add(kullanici)
    db.commit()
    return {"ok": True, "kullanici": kullanici.to_dict()}


@api.get("/oturum")
def oturum(db: Session = Depends(get_db)):
    return _oturum_bilgisi(db)


@api.post("/sifre")
def sifre_degistir(veri: SifreDegisiklik, db: Session = Depends(get_db)):
    """Oturum sahibi kendi şifresini değiştirir (mevcut şifre doğrulanır)."""
    kullanici = yetki.mevcut_kullanici()
    if kullanici is None:
        raise HTTPException(401, "Oturum gerekli")
    if not auth.sifre_dogrula(veri.mevcut, kullanici.sifre_hash):
        raise HTTPException(400, "Mevcut şifre yanlış.")
    hata = auth.sifre_uygun(veri.yeni)
    if hata:
        raise HTTPException(400, hata)
    if auth.sifre_dogrula(veri.yeni, kullanici.sifre_hash):
        raise HTTPException(400, "Yeni şifre mevcut şifreyle aynı olamaz.")
    kullanici.sifre_hash = auth.sifre_ozetle(veri.yeni)
    db.add(kullanici)
    db.commit()
    return {"ok": True}


@api.get("/kullanicilar")
def kullanici_listesi(db: Session = Depends(get_db)):
    yetki.yonetici_kontrol()
    satirlar = db.execute(select(Kullanici).order_by(Kullanici.rol, Kullanici.id)).scalars()
    return [_kullanici_dict(db, k) for k in satirlar]


@api.post("/kullanicilar")
def kullanici_ekle(veri: KullaniciKayit, db: Session = Depends(get_db)):
    yetki.yonetici_kontrol()
    if veri.rol not in ROL_ETIKET:
        raise HTTPException(400, "Geçersiz rol")
    hata = auth.kullanici_adi_uygun(veri.kullanici_adi) or auth.sifre_uygun(veri.sifre)
    if hata:
        raise HTTPException(400, hata)
    var = db.execute(
        select(Kullanici).where(Kullanici.kullanici_adi == veri.kullanici_adi.strip())
    ).scalar_one_or_none()
    if var is not None:
        raise HTTPException(409, "Bu kullanıcı adı zaten var")
    if veri.rol == "ogrenci" and veri.profil_id is None and veri.yeni_profil is None:
        raise HTTPException(
            400, "Öğrenci hesabı için var olan öğrenci seçilmeli ya da yeni öğrenci eklenmeli"
        )
    if veri.profil_id is not None and db.get(Profil, veri.profil_id) is None:
        raise HTTPException(400, "Seçilen profil bulunamadı")

    # Öğrenci hesabıyla birlikte yeni öğrenci kaydı açılıyorsa profil aynı işlemde yazılır
    yeni_profil: Profil | None = None
    if veri.rol == "ogrenci" and veri.yeni_profil is not None:
        yeni_profil = _profil_kaydet(
            db, veri.yeni_profil.ad, veri.yeni_profil.sinif, veri.yeni_profil.alan
        )

    kullanici = Kullanici(
        kullanici_adi=veri.kullanici_adi.strip(),
        ad_soyad=veri.ad_soyad.strip(),
        sifre_hash=auth.sifre_ozetle(veri.sifre),
        rol=veri.rol,
        profil_id=(
            yeni_profil.id
            if yeni_profil is not None
            else (veri.profil_id if veri.rol == "ogrenci" else None)
        ),
        aktif=True,
    )
    db.add(kullanici)
    db.flush()
    if veri.rol == "veli":
        _veli_baglantilarini_yaz(db, kullanici.id, veri.profil_idler)
    db.commit()
    if yeni_profil is not None:
        db.refresh(yeni_profil)
        gunluk_plan_uret(db, yeni_profil, gun_sayisi=7)
    return _kullanici_dict(db, kullanici)


@api.patch("/kullanicilar/{kullanici_id}")
def kullanici_guncelle(
    kullanici_id: int, veri: KullaniciGuncelle, db: Session = Depends(get_db)
):
    yetki.yonetici_kontrol()
    kullanici = db.get(Kullanici, kullanici_id)
    if kullanici is None:
        raise HTTPException(404, "Kullanıcı bulunamadı")
    alanlar = veri.model_fields_set

    if veri.rol is not None:
        if veri.rol not in ROL_ETIKET:
            raise HTTPException(400, "Geçersiz rol")
        if kullanici.rol == "yonetici" and veri.rol != "yonetici":
            kalan = db.execute(
                select(func.count(Kullanici.id)).where(Kullanici.rol == "yonetici")
            ).scalar()
            if (kalan or 0) <= 1:
                raise HTTPException(409, "Son yönetici kaldırılamaz")
        kullanici.rol = veri.rol
    if veri.ad_soyad is not None:
        kullanici.ad_soyad = veri.ad_soyad.strip()
    if veri.sifre:
        hata = auth.sifre_uygun(veri.sifre)
        if hata:
            raise HTTPException(400, hata)
        kullanici.sifre_hash = auth.sifre_ozetle(veri.sifre)
    if veri.aktif is not None:
        kullanici.aktif = veri.aktif
    if "profil_id" in alanlar:
        if veri.profil_id is not None and db.get(Profil, veri.profil_id) is None:
            raise HTTPException(400, "Seçilen profil bulunamadı")
        kullanici.profil_id = veri.profil_id
    if kullanici.rol != "ogrenci":
        kullanici.profil_id = None
    elif kullanici.profil_id is None:
        raise HTTPException(400, "Öğrenci hesabı bir profile bağlı olmalı")
    if veri.profil_idler is not None:
        _veli_baglantilarini_yaz(db, kullanici.id, veri.profil_idler)
    db.commit()
    return _kullanici_dict(db, kullanici)


@api.delete("/kullanicilar/{kullanici_id}")
def kullanici_sil(kullanici_id: int, db: Session = Depends(get_db)):
    yetki.yonetici_kontrol()
    kullanici = db.get(Kullanici, kullanici_id)
    if kullanici is None:
        raise HTTPException(404, "Kullanıcı bulunamadı")
    if kullanici.rol == "yonetici":
        kalan = db.execute(
            select(func.count(Kullanici.id)).where(Kullanici.rol == "yonetici")
        ).scalar()
        if (kalan or 0) <= 1:
            raise HTTPException(409, "Son yönetici silinemez")
    db.execute(delete(VeliOgrenci).where(VeliOgrenci.veli_id == kullanici.id))
    db.delete(kullanici)
    db.commit()
    return {"ok": True}


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
def mufredat(profil_id: int, hepsi: bool = False, db: Session = Depends(get_db)):
    profil = _profil_getir(db, profil_id)
    ders_map = _ders_map(db)
    konular = _alan_konulari(db, profil)
    durumlar = _durum_map(db, profil.id)
    # Yönetici ?hepsi=1 ile kapsam dışı konuları da görür (düzenleme için)
    tumunu_goster = hepsi and yetki.yonetici_mi()

    gruplu: dict[str, dict] = {}
    for konu in sorted(konular, key=lambda k: (k.ders_kod, k.sira)):
        ders = ders_map.get(konu.ders_kod)
        # Sınıf kapsamı dışındaki konular listelenmez:
        # 11. sınıf -> 9-10 TYT + 11 AYT, 12. sınıf -> 9-10 TYT + 11-12 AYT
        disinda = sinif_servisi.kapsam_disi(
            konu.sinif, profil.sinif, ders.sinav if ders else None
        )
        if disinda and not tumunu_goster:
            continue
        grup = gruplu.setdefault(
            konu.ders_kod,
            {
                "kod": konu.ders_kod,
                "ad": ders.ad if ders else konu.ders_kod,
                "sinav": ders.sinav if ders else "",
                "renk": ders.renk if ders else "#ea580c",
                "soru_sayisi": ders.soru_sayisi if ders else 0,
                "ozel": bool(ders.ozel) if ders else False,
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
                "kapsam_disi": disinda,
            }
        )

    # Yöneticinin yeni açtığı dersin henüz konusu olmayabilir: kart yine de
    # listelenir, böylece altındaki "Konu ekle"ye ulaşılabilir. Öğrenci/veli
    # tarafında içi boş ders gizli kalır.
    if yetki.yonetici_mi():
        for kod, ders in ders_map.items():
            alanlar = [a.strip() for a in (ders.alanlar or "").split(",") if a.strip()]
            if "ortak" not in alanlar and profil.alan not in alanlar:
                continue
            gruplu.setdefault(
                kod,
                {
                    "kod": kod,
                    "ad": ders.ad,
                    "sinav": ders.sinav,
                    "renk": ders.renk,
                    "soru_sayisi": ders.soru_sayisi,
                    "ozel": bool(ders.ozel),
                    "konular": [],
                },
            )

    sirali = sorted(gruplu.values(), key=lambda g: (ders_map[g["kod"]].sira if g["kod"] in ders_map else 99, g["kod"]))
    return {
        "profil": profil.to_dict(),
        "dersler": sirali,
        "kapsam": {
            "etiket": sinif_servisi.kapsam_etiketi(profil.sinif),
            "sinif": profil.sinif,
            "aralik": list(sinif_servisi.konu_kapsami(profil.sinif) or []),
            **sinif_servisi.kapsam_cizelgesi(profil.sinif),
        },
    }


# --------------------------------------------------------------------------
# Müfredat düzenleme (yalnız yönetici): konu ve ders ekle / düzenle / sil
# --------------------------------------------------------------------------
GECERLI_KONU_SINIFLARI = {9, 10, 11, 12}


def _beceri_dogrula(beceri: str) -> str:
    """Virgüllü beceri kodlarını doğrular ('KB,AB,SD,OK')."""
    kodlar = [b.strip().upper() for b in (beceri or "").split(",") if b.strip()]
    bilinmeyen = [k for k in kodlar if k not in BECERI_ETIKET]
    if bilinmeyen:
        raise HTTPException(
            400, f"Geçersiz beceri kodu: {', '.join(bilinmeyen)} (geçerli: KB, AB, SD, OK)"
        )
    return ",".join(kodlar)


def _onkosul_dogrula(db: Session, onkosul: str) -> str:
    """Virgüllü konu kodlarının gerçekten var olduğunu doğrular."""
    kodlar = [o.strip() for o in (onkosul or "").split(",") if o.strip()]
    if not kodlar:
        return ""
    var = set(db.execute(select(Konu.kod).where(Konu.kod.in_(kodlar))).scalars())
    eksik = [k for k in kodlar if k not in var]
    if eksik:
        raise HTTPException(400, f"Ön koşul konusu bulunamadı: {', '.join(eksik)}")
    return ",".join(kodlar)


def _alanlar_dogrula(alanlar: str) -> str:
    """Dersin hizmet ettiği alanlar: 'ortak' ya da sayisal/ea/sozel listesi."""
    parcalar = [a.strip() for a in (alanlar or "").split(",") if a.strip()]
    if parcalar == ["ortak"]:
        return "ortak"
    gecersiz = [a for a in parcalar if a not in GECERLI_ALANLAR]
    if gecersiz or not parcalar:
        raise HTTPException(400, "Alan listesi 'ortak' ya da sayisal/ea/sozel olmalı")
    return ",".join(parcalar)


def _konu_kod_uret(db: Session, ders_kod: str) -> str:
    """Yönetici konuları için benzersiz kod: <DERS>-OZ<n>."""
    n = 1
    while True:
        kod = f"{ders_kod}-OZ{n}"
        if db.execute(select(Konu.id).where(Konu.kod == kod)).first() is None:
            return kod[:24]
        n += 1


def _konu_sil(db: Session, konu: Konu) -> None:
    """Konuyu bağımlılıklarıyla siler; gömülü konuyu eşitlemeye karşı işaretler."""
    kod = konu.kod
    seed_servis._konu_bagimliliklarini_temizle(db, konu.id)
    if not konu.ozel:
        seed_servis.kod_silindi_olarak_isle(db, "konu", kod)
    # Diğer konuların ön koşul listesinden de çıkar
    for diger in db.execute(select(Konu).where(Konu.onkosul.like(f"%{kod}%"))).scalars():
        kalanlar = [o for o in (diger.onkosul or "").split(",") if o and o != kod]
        diger.onkosul = ",".join(kalanlar)
    db.delete(konu)


@api.post("/mufredat/konu")
def mufredat_konu_ekle(veri: KonuGiris, db: Session = Depends(get_db)):
    """Müfredata konu ekler (yalnız yönetici)."""
    yetki.yonetici_kontrol()
    if _ders_getir(db, veri.ders_kod) is None:
        raise HTTPException(400, "Ders bulunamadı")
    if veri.sinif not in GECERLI_KONU_SINIFLARI:
        raise HTTPException(400, "Sınıf 9, 10, 11 veya 12 olmalı")
    sira = (
        db.execute(select(func.max(Konu.sira)).where(Konu.ders_kod == veri.ders_kod)).scalar()
        or 0
    ) + 1
    konu = Konu(
        kod=_konu_kod_uret(db, veri.ders_kod),
        ders_kod=veri.ders_kod,
        ad=veri.ad.strip(),
        sinif=veri.sinif,
        agirlik=veri.agirlik,
        sure_dk=veri.sure_dk,
        beceri=_beceri_dogrula(veri.beceri),
        onkosul=_onkosul_dogrula(db, veri.onkosul),
        sira=sira,
        ozel=True,
    )
    db.add(konu)
    db.commit()
    db.refresh(konu)
    return konu.to_dict()


@api.patch("/mufredat/konu/{konu_id}")
def mufredat_konu_duzenle(konu_id: int, veri: KonuDuzenle, db: Session = Depends(get_db)):
    """Konu alanlarını günceller (yalnız yönetici)."""
    yetki.yonetici_kontrol()
    konu = db.get(Konu, konu_id)
    if konu is None:
        raise HTTPException(404, "Konu bulunamadı")
    if veri.ders_kod is not None and veri.ders_kod != konu.ders_kod:
        if _ders_getir(db, veri.ders_kod) is None:
            raise HTTPException(400, "Ders bulunamadı")
        konu.ders_kod = veri.ders_kod
    if veri.ad is not None:
        konu.ad = veri.ad.strip()
    if veri.sinif is not None:
        if veri.sinif not in GECERLI_KONU_SINIFLARI:
            raise HTTPException(400, "Sınıf 9, 10, 11 veya 12 olmalı")
        konu.sinif = veri.sinif
    if veri.agirlik is not None:
        konu.agirlik = veri.agirlik
    if veri.sure_dk is not None:
        konu.sure_dk = veri.sure_dk
    if veri.beceri is not None:
        konu.beceri = _beceri_dogrula(veri.beceri)
    if veri.onkosul is not None:
        konu.onkosul = _onkosul_dogrula(db, veri.onkosul)
    if veri.sira is not None:
        konu.sira = veri.sira
    # Düzenlenen satır artık yöneticiye aittir: gömülü veri güncellemesi ezmez
    konu.ozel = True
    db.commit()
    db.refresh(konu)
    return konu.to_dict()


@api.delete("/mufredat/konu/{konu_id}")
def mufredat_konu_sil(konu_id: int, db: Session = Depends(get_db)):
    """Konuyu müfredattan kaldırır; öğrenci durum kayıtları da temizlenir."""
    yetki.yonetici_kontrol()
    konu = db.get(Konu, konu_id)
    if konu is None:
        raise HTTPException(404, "Konu bulunamadı")
    kod = konu.kod
    _konu_sil(db, konu)
    db.commit()
    return {"ok": True, "kod": kod}


@api.post("/mufredat/ders")
def mufredat_ders_ekle(veri: DersGiris, db: Session = Depends(get_db)):
    """Müfredata ders ekler (yalnız yönetici)."""
    yetki.yonetici_kontrol()
    kod = veri.kod.strip().upper()
    if _ders_getir(db, kod) is not None:
        raise HTTPException(400, "Bu ders kodu zaten var")
    if veri.sinav not in {"TYT", "AYT"}:
        raise HTTPException(400, "Sınav TYT veya AYT olmalı")
    ders = Ders(
        kod=kod,
        ad=veri.ad.strip(),
        sinav=veri.sinav,
        alanlar=_alanlar_dogrula(veri.alanlar),
        soru_sayisi=veri.soru_sayisi,
        renk=veri.renk,
        sira=veri.sira,
        ozel=True,
    )
    db.add(ders)
    db.commit()
    db.refresh(ders)
    return ders.to_dict()


@api.patch("/mufredat/ders/{ders_kod}")
def mufredat_ders_duzenle(ders_kod: str, veri: DersDuzenle, db: Session = Depends(get_db)):
    """Dersin adı, soru sayısı, rengi gibi alanları günceller (yalnız yönetici)."""
    yetki.yonetici_kontrol()
    ders = _ders_getir(db, ders_kod)
    if ders is None:
        raise HTTPException(404, "Ders bulunamadı")
    if veri.ad is not None:
        ders.ad = veri.ad.strip()
    if veri.sinav is not None:
        if veri.sinav not in {"TYT", "AYT"}:
            raise HTTPException(400, "Sınav TYT veya AYT olmalı")
        ders.sinav = veri.sinav
    if veri.alanlar is not None:
        ders.alanlar = _alanlar_dogrula(veri.alanlar)
    if veri.soru_sayisi is not None:
        ders.soru_sayisi = veri.soru_sayisi
    if veri.renk is not None:
        ders.renk = veri.renk
    if veri.sira is not None:
        ders.sira = veri.sira
    # Renk gibi alanlar gömülü paletle ezilmesin
    ders.ozel = True
    db.commit()
    db.refresh(ders)
    return ders.to_dict()


@api.delete("/mufredat/ders/{ders_kod}")
def mufredat_ders_sil(ders_kod: str, db: Session = Depends(get_db)):
    """Dersi ve altındaki tüm konuları kaldırır (yalnız yönetici)."""
    yetki.yonetici_kontrol()
    ders = _ders_getir(db, ders_kod)
    if ders is None:
        raise HTTPException(404, "Ders bulunamadı")
    konular = list(db.execute(select(Konu).where(Konu.ders_kod == ders_kod)).scalars())
    for konu in konular:
        _konu_sil(db, konu)
    if not ders.ozel:
        # Gömülü ders açılışta geri eklenmesin
        seed_servis.kod_silindi_olarak_isle(db, "ders", ders_kod)
    db.delete(ders)
    db.commit()
    return {"ok": True, "konu": len(konular)}


@api.post("/konu-durum")
def konu_durum_guncelle(veri: KonuDurumGiris, db: Session = Depends(get_db)):
    yetki.yazma_kontrol("mufredat")
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
        "kapsam": {
            "etiket": sinif_servisi.kapsam_etiketi(profil.sinif),
            "sinif": profil.sinif,
            "aralik": list(sinif_servisi.konu_kapsami(profil.sinif) or []),
            **sinif_servisi.kapsam_cizelgesi(profil.sinif),
        },
        "gunler": sonuc,
        "beceri_dengesi": beceri_dengesi(tum_maddeler, konu_map, ek={"SD": sd_dk}),
        "deneme_odagi": deneme_odagi(tum_maddeler, konu_map, yanlislar),
        "pdr_ilkeleri": pdr_ilkeleri(),
    }


@api.post("/plan/{profil_id}/uret")
def plan_uret(profil_id: int, gun: int = 7, db: Session = Depends(get_db)):
    """Günlük planı üretir; yapay zekâ analizi varsa ders payları ondan gelir."""
    yetki.yazma_kontrol("plan")
    profil = _profil_getir(db, profil_id)
    # Analiz 12 saatten eskiyse ya da hiç yoksa yenilenir; başarısız olsa da
    # plan deterministik kurallarla üretilmeye devam eder.
    analiz = plan_analiz_servisi.analiz_calistir(db, profil)
    eklenen = gunluk_plan_uret(db, profil, gun_sayisi=max(1, min(30, gun)))
    return {"eklenen": eklenen, "analiz": analiz}


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
    yetki.yazma_kontrol("plan")
    profil = _profil_getir(db, profil_id)
    analiz = plan_analiz_servisi.analiz_calistir(db, profil)
    eklenen = aylik_plan_uret(db, profil, hafta_sayisi=max(1, min(8, hafta)))
    return {"eklenen": eklenen, "analiz": analiz}


@api.get("/plan/{profil_id}/analiz")
def plan_analiz_durum(profil_id: int, db: Session = Depends(get_db)):
    """Yapay zekâ plan analizi: son ders payları, odak konular ve tazelik."""
    profil = _profil_getir(db, profil_id)
    return plan_analiz_servisi.durum(db, profil)


@api.post("/plan/{profil_id}/analiz")
def plan_analiz_yenile(
    profil_id: int, zorla: bool = True, db: Session = Depends(get_db)
):
    """Hedef netleri, deneme sonuçlarını ve konu ağırlıklarını modele yorumlatır."""
    yetki.yazma_kontrol("plan")
    profil = _profil_getir(db, profil_id)
    return plan_analiz_servisi.analiz_calistir(db, profil, zorla=zorla)


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


@api.post("/plan/{profil_id}/madde")
def plan_madde_ekle(profil_id: int, veri: PlanMaddeGiris, db: Session = Depends(get_db)):
    """Açık konuyu plana tek tıkla ekler (analiz → plan uyumu kartı)."""
    yetki.yazma_kontrol("plan")
    profil = _profil_getir(db, profil_id)
    konu = db.get(Konu, veri.konu_id)
    if konu is None:
        raise HTTPException(404, "Konu bulunamadı")
    ders = _ders_getir(db, konu.ders_kod)
    if sinif_servisi.kapsam_disi(konu.sinif, profil.sinif, ders.sinav if ders else None):
        raise HTTPException(400, f"Bu konu {sinif_servisi.kapsam_etiketi(profil.sinif)} dışında")
    tarih = veri.tarih or date.today()
    if veri.tur not in {"konu", "tekrar", "soru"}:
        raise HTTPException(400, "Geçersiz çalışma türü")

    # Aynı konu aynı gün planda varsa ikinci blok yazılmaz
    var = db.execute(
        select(PlanItem).where(
            PlanItem.profil_id == profil.id,
            PlanItem.tarih == tarih,
            PlanItem.konu_id == konu.id,
        )
    ).scalars().first()
    if var is not None:
        return {"ok": True, "madde_id": var.id, "zaten_var": True, "tarih": tarih.isoformat()}

    ders = _ders_getir(db, konu.ders_kod)
    son_sira = db.execute(
        select(func.max(PlanItem.sira)).where(
            PlanItem.profil_id == profil.id, PlanItem.tarih == tarih
        )
    ).scalar()
    madde = PlanItem(
        profil_id=profil.id,
        tarih=tarih,
        ders_kod=konu.ders_kod,
        konu_id=konu.id,
        baslik=f"{ders.ad if ders else konu.ders_kod} · {konu.ad}",
        tur=veri.tur,
        sure_dk=max(15, veri.sure_dk or konu.sure_dk or 45),
        durum="bekliyor",
        sira=int(son_sira or 0) + 1,
        baslangic="",
    )
    db.add(madde)
    db.commit()
    db.refresh(madde)
    # Gün akışı saatleri yeniden yerleştirilir
    zamanlari_yerlestir(db, profil, tarih, tarih)
    return {"ok": True, "madde_id": madde.id, "zaten_var": False, "tarih": tarih.isoformat()}


# --------------------------------------------------------------------------
# Okul ders programı ve o gün işlenen konular
# --------------------------------------------------------------------------
@api.get("/profil/{profil_id}/ders-programi")
def ders_programi_getir(profil_id: int, db: Session = Depends(get_db)):
    """Haftalık okul çizelgesi, bugünün dersleri ve ders başına konu listesi."""
    profil = _profil_getir(db, profil_id)
    return okul_servisi.ozet(db, profil)


@api.put("/profil/{profil_id}/ders-programi")
def ders_programi_kaydet(
    profil_id: int, veri: DersProgramiGiris, db: Session = Depends(get_db)
):
    """Çizelgeyi kaydeder; ``sablon_uygula`` verilirse 11/12 çizelgesi yüklenir."""
    yetki.yazma_kontrol("plan")
    profil = _profil_getir(db, profil_id)
    if not profil.sinif:
        # Mezun öğrencide okul yok: plan TYT/AYT konularına göre kurulur
        raise HTTPException(
            400,
            "Mezun öğrencide okul ders programı tutulmaz; plan TYT ve AYT konularına göre kurulur.",
        )
    hucreler = veri.hucreler
    if veri.sablon_uygula is not None:
        if veri.sablon_uygula not in (11, 12):
            raise HTTPException(400, "Hazır çizelge yalnız 11. ve 12. sınıf için var")
        hucreler = okul_servisi.sablon(veri.sablon_uygula, profil.alan)
        if not hucreler:
            raise HTTPException(400, "Bu sınıf için hazır çizelge bulunamadı")
    yazilan = okul_servisi.program_yaz(db, profil.id, hucreler)
    return {"ok": True, "hucre": yazilan, "ozet": okul_servisi.ozet(db, profil)}


@api.get("/profil/{profil_id}/islenen")
def islenen_listesi(profil_id: int, gun: int = 7, db: Session = Depends(get_db)):
    """Son günlerde okulda işlenen konular (tekrar takviminin kanıtı)."""
    profil = _profil_getir(db, profil_id)
    return okul_servisi.son_islenenler(db, profil, gun_sayisi=max(1, min(30, gun)))


@api.post("/profil/{profil_id}/islenen")
def islenen_kaydet(
    profil_id: int, veri: IslenenKonuGiris, db: Session = Depends(get_db)
):
    """Okulda işlenen konuları kaydeder, günlük planı tekrar bloklarıyla tazeler."""
    yetki.yazma_kontrol("plan")
    profil = _profil_getir(db, profil_id)
    if not profil.sinif:
        raise HTTPException(
            400,
            "Mezun öğrencide okul dersi işlenmez; plan TYT ve AYT konularına göre kurulur.",
        )
    tarih = veri.tarih or date.today()
    if tarih > date.today():
        raise HTTPException(400, "İleri tarih için konu girilemez")
    try:
        okul_servisi.islenen_yaz(db, profil, tarih, veri.konu_idler)
    except ValueError as hata:
        raise HTTPException(400, str(hata))
    # Plan tazelenir: işlenen konular bugünün tekrar/pekiştirme bloklarına girer
    eklenen = gunluk_plan_uret(db, profil, gun_sayisi=7)
    return {
        "ok": True,
        "tarih": tarih.isoformat(),
        "plan": eklenen,
        "ozet": okul_servisi.ozet(db, profil, tarih),
    }


# --------------------------------------------------------------------------
# Denemeler
# --------------------------------------------------------------------------
@api.post("/deneme")
def deneme_ekle(veri: DenemeGiris, db: Session = Depends(get_db)):
    yetki.yazma_kontrol("deneme")
    profil = _profil_getir(db, veri.profil_id)
    # Yalnız konu girilse bile deneme kaydedilir: ders satırı konu toplamından çıkar
    if not veri.sonuclar and not veri.konular:
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
    db.flush()

    for s in veri.sonuclar:
        db.add(
            DenemeSonuc(
                deneme_id=deneme.id,
                ders_kod=s.ders_kod,
                dogru=s.dogru,
                yanlis=s.yanlis,
                bos=s.bos,
                net=scoring.net_hesapla(s.dogru, s.yanlis),
            )
        )
    db.flush()

    # Ders sonuçları yazıldıktan sonra konu bazlı doğru/yanlış/boş eklenir
    konu_sayisi = _deneme_konularini_yaz(db, deneme.id, veri.konular)
    db.flush()
    # Ders satırı boş bırakılmışsa konu toplamları ders satırına yazılır
    eklenen_dersler = _konu_toplamlarini_derslere_yaz(db, deneme.id)
    db.flush()

    satirlar = [
        {"ders_kod": n.ders_kod, "dogru": n.dogru, "yanlis": n.yanlis, "bos": n.bos, "net": n.net}
        for n in _deneme_netleri(db, deneme.id)
    ]
    if not satirlar:
        # Yalnız sıfır değerli konu satırı geldiyse boş deneme kaydı açılmaz
        db.rollback()
        raise HTTPException(400, "En az bir ders ya da konu satırı girilmeli")
    db.commit()

    deneme_id = deneme.id
    ozet = scoring.deneme_ozeti(satirlar, profil.alan)
    return {
        "id": deneme_id,
        "ozet": ozet,
        "konu_sayisi": konu_sayisi,
        "eklenen_dersler": eklenen_dersler,
    }


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
                        "dogru": k.dogru,
                        "yanlis": k.yanlis,
                        "bos": k.bos,
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
    yetki.yazma_kontrol("deneme")
    deneme = db.get(Deneme, deneme_id)
    if not deneme:
        raise HTTPException(404, "Deneme bulunamadı")
    yetki.profil_kontrol(db, deneme.profil_id)
    db.execute(delete(DenemeSonuc).where(DenemeSonuc.deneme_id == deneme_id))
    db.execute(delete(DenemeKonu).where(DenemeKonu.deneme_id == deneme_id))
    db.delete(deneme)
    db.commit()
    return {"ok": True}


@api.post("/deneme/{deneme_id}/konular")
def deneme_konulari_guncelle(
    deneme_id: int, veri: KonuYanlisGiris, db: Session = Depends(get_db)
):
    """Denemenin konu satırlarını tazeler; konu bazlı analiz buradan beslenir.

    Eski ``{konular:[{konu_id, yanlis}]}`` gövdesi de çalışır; konu, denemenin
    ders satırlarından birine ait olmalıdır.
    """
    yetki.yazma_kontrol("deneme")
    deneme = db.get(Deneme, deneme_id)
    if not deneme:
        raise HTTPException(404, "Deneme bulunamadı")
    yetki.profil_kontrol(db, deneme.profil_id)
    dersler = {
        kod
        for (kod,) in db.execute(
            select(DenemeSonuc.ders_kod).where(DenemeSonuc.deneme_id == deneme_id)
        ).all()
    }
    yazilan = _deneme_konularini_yaz(db, deneme_id, veri.konular, dersler or None)
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
    # Anahtar ayarı Ayarlar sayfasının yönetici bölümündedir
    yetki.yonetici_kontrol()
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
    yetki.yonetici_kontrol()
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

    # Tüm kurumun verisi tek dosyada: indirme yalnız yöneticiye açık
    yetki.yonetici_kontrol()

    if DB_YOLU is None:
        raise HTTPException(
            409, "Bulut veritabanında dosya yedeği yok; Neon panosundan yedek alınabilir."
        )
    if not DB_YOLU.exists():
        raise HTTPException(404, "Veritabanı dosyası bulunamadı")
    return FileResponse(DB_YOLU, media_type="application/octet-stream", filename="a-key-yedek.db")


@api.get("/saglik")
def saglik(db: Session = Depends(get_db)):
    return {
        "durum": "calisiyor",
        # Render her yayina commit kimligini verir: hangi surumun ayakta
        # oldugu tek bakista gorunur, diske yazmadan
        "derleme": os.getenv("RENDER_GIT_COMMIT", "")[:7] or "yerel",
        "ders": db.query(Ders).count(),
        "konu": db.query(Konu).count(),
        "profil": db.query(Profil).count(),
    }
