# -*- coding: utf-8 -*-
"""Haftalık okul ders programı ve "bugün işlenen konular".

Okulda hangi gün hangi dersin olduğu ``ders_programi`` tablosunda tutulur.
Öğrenci gün içinde okulda işlenen konuları işaretler (``islenen_konular``);
günlük plan üretimi bu konuları tekrar ve pekiştirme bloğu olarak yazar.

Ders programı hücreleri YKS ders kodu değil, **okul dersi anahtarı** tutar
(``matematik``, ``fizik`` ...). Beden eğitimi gibi sınavda çıkmayan dersler de
çizelgede görünür ama konu seçeneği üretmez. Anahtar → YKS ders kodları eşlemesi
``OKUL_DERSLERI`` içindedir.

Sınıf şablonları (11/12 + alan) Türkiye'deki Anadolu lisesi haftalık ders
çizelgesine yakın bir başlangıç noktasıdır: 5 gün × 8 ders saati. Öğrenci veya
yönetici hücreleri kendi okulunun çizelgesine göre değiştirir.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import Ders, DersProgrami, IslenenKonu, Konu, KonuDurum, Profil
from . import sinif as sinif_servisi

GUN_ADLARI = (
    "Pazartesi",
    "Salı",
    "Çarşamba",
    "Perşembe",
    "Cuma",
    "Cumartesi",
    "Pazar",
)
# Bir güne yazılabilecek en fazla ders saati (arayüz ızgarası da bunu kullanır)
GUNLUK_DERS_SAATI = 8
HAFTA_GUNU = 5

# Okul dersi anahtarı → görünen ad + YKS ders kodları. Kodlar boşsa ders
# çizelgede görünür ama konu seçeneği ve plan bloğu üretmez.
OKUL_DERSLERI: list[dict] = [
    {"kod": "matematik", "ad": "Matematik", "ders": ["TYT-MAT", "AYT-MAT"]},
    {"kod": "geometri", "ad": "Geometri", "ders": ["TYT-GEO", "AYT-GEO"]},
    {"kod": "fizik", "ad": "Fizik", "ders": ["TYT-FIZ", "AYT-FIZ"]},
    {"kod": "kimya", "ad": "Kimya", "ders": ["TYT-KIM", "AYT-KIM"]},
    {"kod": "biyoloji", "ad": "Biyoloji", "ders": ["TYT-BIO", "AYT-BIO"]},
    {"kod": "tde", "ad": "Türk Dili ve Edebiyatı", "ders": ["TYT-TUR", "AYT-EDB"]},
    {"kod": "tarih", "ad": "Tarih", "ders": ["TYT-TAR", "AYT-TAR1", "AYT-TAR2"]},
    {"kod": "cografya", "ad": "Coğrafya", "ders": ["TYT-COG", "AYT-COG1", "AYT-COG2"]},
    {"kod": "felsefe", "ad": "Felsefe", "ders": ["TYT-FEL", "AYT-FEL"]},
    {"kod": "din", "ad": "Din Kültürü", "ders": ["TYT-DIN", "AYT-DIN"]},
    {"kod": "ingilizce", "ad": "İngilizce", "ders": []},
    {"kod": "beden", "ad": "Beden Eğitimi", "ders": []},
    {"kod": "etut", "ad": "Etüt / Rehberlik", "ders": []},
]
_DERS_MAP = {d["kod"]: d for d in OKUL_DERSLERI}

# Haftalık ders saatleri: (sınıf, alan) → {okul dersi anahtarı: saat}
DERS_SAATLERI: dict[tuple[int, str], dict[str, int]] = {
    (11, "sayisal"): {
        "matematik": 6, "fizik": 4, "kimya": 4, "biyoloji": 3, "tde": 5,
        "tarih": 2, "cografya": 2, "felsefe": 2, "din": 2, "ingilizce": 4,
        "beden": 2, "etut": 4,
    },
    (11, "ea"): {
        "matematik": 6, "geometri": 2, "tde": 6, "tarih": 4, "cografya": 4,
        "felsefe": 2, "din": 2, "ingilizce": 4, "beden": 2, "etut": 8,
    },
    (11, "sozel"): {
        "matematik": 4, "tde": 8, "tarih": 5, "cografya": 5, "felsefe": 3,
        "din": 2, "ingilizce": 4, "beden": 2, "etut": 7,
    },
    (12, "sayisal"): {
        "matematik": 6, "geometri": 2, "fizik": 3, "kimya": 3, "biyoloji": 3,
        "tde": 5, "tarih": 2, "cografya": 2, "felsefe": 2, "din": 2,
        "ingilizce": 4, "beden": 2, "etut": 4,
    },
    (12, "ea"): {
        "matematik": 6, "geometri": 2, "tde": 6, "tarih": 4, "cografya": 4,
        "felsefe": 2, "din": 2, "ingilizce": 4, "beden": 2, "etut": 8,
    },
    (12, "sozel"): {
        "matematik": 4, "tde": 8, "tarih": 5, "cografya": 5, "felsefe": 3,
        "din": 2, "ingilizce": 4, "beden": 2, "etut": 7,
    },
}

# İşlenen konular kaç gün geriye kadar tekrar bloğu üretir (aralıklı tekrar)
TEKRAR_GUNLERI = (0, 1, 3, 7)


def ders_adi(anahtar: str) -> str:
    kayit = _DERS_MAP.get(anahtar)
    return kayit["ad"] if kayit else ""


def _dagit(saatler: dict[str, int]) -> list[list[str]]:
    """Ders saatlerini haftaya yayar: her gün en çok kalan ders seçilir.

    Aynı dersin üst üste yığılmasını engellemek için o gün en az kullanılan
    ders öne alınır; böylece 6 saatlik matematik tek güne düşmez.
    """
    kalan = {k: v for k, v in saatler.items() if v > 0}
    hafta: list[list[str]] = []
    for _ in range(HAFTA_GUNU):
        gun: list[str] = []
        for _ in range(GUNLUK_DERS_SAATI):
            adaylar = [k for k, v in kalan.items() if v > 0]
            if not adaylar:
                gun.append("")
                continue
            secilen = max(adaylar, key=lambda k: (kalan[k], -gun.count(k)))
            gun.append(secilen)
            kalan[secilen] -= 1
        hafta.append(gun)
    return hafta


def sablon(sinif: int, alan: str) -> list[dict]:
    """Sınıf ve alana göre hazır haftalık çizelge hücreleri."""
    saatler = DERS_SAATLERI.get((sinif, alan))
    if not saatler:
        # Alan eşleşmesi yoksa sayısal çizelgesi varsayılır
        saatler = DERS_SAATLERI.get((sinif, "sayisal"))
    if not saatler:
        return []
    return [
        {"gun": gun, "sira": sira, "ders": anahtar}
        for gun, satir in enumerate(_dagit(saatler))
        for sira, anahtar in enumerate(satir, start=1)
        if anahtar
    ]


def program_oku(db: Session, profil_id: int) -> list[DersProgrami]:
    return list(
        db.execute(
            select(DersProgrami)
            .where(DersProgrami.profil_id == profil_id)
            .order_by(DersProgrami.gun, DersProgrami.sira)
        ).scalars()
    )


def program_yaz(db: Session, profil_id: int, hucreler: list[dict]) -> int:
    """Haftalık çizelgeyi baştan yazar (boş hücreler atlanır)."""
    db.execute(delete(DersProgrami).where(DersProgrami.profil_id == profil_id))
    yazilan = 0
    gorulen: set[tuple[int, int]] = set()
    for hucre in hucreler:
        anahtar = (hucre.get("ders") or "").strip()
        if not anahtar or anahtar not in _DERS_MAP:
            continue
        gun = int(hucre.get("gun", 0))
        sira = int(hucre.get("sira", 0))
        if not (0 <= gun <= 6 and 1 <= sira <= 12):
            continue
        if (gun, sira) in gorulen:
            continue
        gorulen.add((gun, sira))
        db.add(DersProgrami(profil_id=profil_id, gun=gun, sira=sira, ders=anahtar))
        yazilan += 1
    db.commit()
    return yazilan


def gunun_dersleri(program: list[DersProgrami], tarih: date) -> list[str]:
    """O günün ders anahtarları (tekrarsız, sıra korunur)."""
    anahtarlar: list[str] = []
    for hucre in program:
        if hucre.gun != tarih.weekday():
            continue
        if hucre.ders and hucre.ders not in anahtarlar:
            anahtarlar.append(hucre.ders)
    return anahtarlar


def gunun_plani(program: list[DersProgrami], tarih: date) -> list[dict]:
    """O günün ders saatleri: [{sira, ders, ad}]."""
    return [
        {"sira": h.sira, "ders": h.ders, "ad": ders_adi(h.ders)}
        for h in program
        if h.gun == tarih.weekday() and h.ders
    ]


def konu_secenekleri(db: Session, profil: Profil, anahtar: str) -> list[dict]:
    """Okul dersinin kapsamdaki konuları (sınıf süzgeciyle)."""
    kayit = _DERS_MAP.get(anahtar) or {}
    kodlar = [k for k in kayit.get("ders", []) if k]
    if not kodlar:
        return []
    ders_adlari = {
        d.kod: d.ad for d in db.execute(select(Ders).where(Ders.kod.in_(kodlar))).scalars()
    }
    konular = db.execute(
        select(Konu).where(Konu.ders_kod.in_(kodlar)).order_by(Konu.ders_kod, Konu.sira)
    ).scalars()
    return [
        {
            "id": k.id,
            "ad": k.ad,
            "ders_kod": k.ders_kod,
            "ders_ad": ders_adlari.get(k.ders_kod, k.ders_kod),
            "sinif": k.sinif,
        }
        for k in konular
        if not sinif_servisi.kapsam_disi(k.sinif, profil.sinif)
    ]


def islenen_oku(db: Session, profil_id: int, tarih: date) -> list[IslenenKonu]:
    return list(
        db.execute(
            select(IslenenKonu).where(
                IslenenKonu.profil_id == profil_id, IslenenKonu.tarih == tarih
            )
        ).scalars()
    )


def islenen_yaz(db: Session, profil: Profil, tarih: date, konu_idler: list[int]) -> int:
    """O günün işlenen konularını baştan yazar; konu durumunu ilerletir.

    İşaretlenen konu "çalışılıyor" durumuna geçer, son çalışma tarihi bugün
    olur ve tekrar tarihi ertesi güne kurulur: günlük plan bu tarihe göre
    tekrar bloğu üretir.
    """
    istenen = list(dict.fromkeys(int(k) for k in konu_idler))
    mevcut = {satir.konu_id: satir for satir in islenen_oku(db, profil.id, tarih)}

    for konu_id, satir in mevcut.items():
        if konu_id not in istenen:
            db.delete(satir)

    for konu_id in istenen:
        konu = db.get(Konu, konu_id)
        if konu is None:
            raise ValueError(f"Konu bulunamadı: {konu_id}")
        if sinif_servisi.kapsam_disi(konu.sinif, profil.sinif):
            raise ValueError(f"Konu {sinif_servisi.kapsam_etiketi(profil.sinif)} dışında: {konu.ad}")
        if konu_id not in mevcut:
            db.add(
                IslenenKonu(
                    profil_id=profil.id,
                    tarih=tarih,
                    konu_id=konu_id,
                    ders_kod=konu.ders_kod,
                )
            )
        durum = db.execute(
            select(KonuDurum).where(
                KonuDurum.profil_id == profil.id, KonuDurum.konu_id == konu_id
            )
        ).scalar_one_or_none()
        if durum is None:
            durum = KonuDurum(profil_id=profil.id, konu_id=konu_id, durum="calisiliyor")
            db.add(durum)
        elif durum.durum == "yok":
            durum.durum = "calisiliyor"
        durum.son_calisma = datetime.combine(tarih, datetime.min.time().replace(hour=18))
        durum.tekrar_tarihi = tarih + timedelta(days=1)

    db.commit()
    return len(istenen)


def son_islenenler(db: Session, profil: Profil, gun_sayisi: int = 7) -> list[dict]:
    """Son günlerde okulda işlenen konular (yeniden eskiye)."""
    baslangic = date.today() - timedelta(days=max(1, gun_sayisi) - 1)
    satirlar = list(
        db.execute(
            select(IslenenKonu)
            .where(
                IslenenKonu.profil_id == profil.id,
                IslenenKonu.tarih >= baslangic,
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
    ders_adlari = {
        d.kod: d.ad for d in db.execute(select(Ders)).scalars()
    }
    gruplar: dict[date, list[dict]] = {}
    for satir in satirlar:
        konu = konular.get(satir.konu_id)
        if konu is None:
            continue
        gruplar.setdefault(satir.tarih, []).append(
            {
                "id": konu.id,
                "ad": konu.ad,
                "ders_kod": konu.ders_kod,
                "ders_ad": ders_adlari.get(konu.ders_kod, konu.ders_kod),
            }
        )
    return [
        {"tarih": tarih.isoformat(), "gun_adi": GUN_ADLARI[tarih.weekday()], "konular": liste}
        for tarih, liste in sorted(gruplar.items(), reverse=True)
    ]


def ozet(db: Session, profil: Profil, tarih: date | None = None) -> dict:
    """Ders programı sayfasının tek çağrıda ihtiyaç duyduğu her şey."""
    tarih = tarih or date.today()
    program = program_oku(db, profil.id)
    bugun = gunun_dersleri(program, tarih)
    islenen = islenen_oku(db, profil.id, tarih)
    return {
        "profil_id": profil.id,
        "sinif": profil.sinif,
        "sinif_etiketi": profil.sinif_etiketi,
        "okul_var": bool(profil.sinif),
        "alan": profil.alan,
        "alan_etiketi": profil.alan_etiketi,
        "tarih": tarih.isoformat(),
        "gun": tarih.weekday(),
        "gun_adi": GUN_ADLARI[tarih.weekday()],
        "gunler": [
            {"gun": i, "ad": ad, "hafta_ici": i < HAFTA_GUNU}
            for i, ad in enumerate(GUN_ADLARI[:HAFTA_GUNU])
        ],
        "gunluk_saat": GUNLUK_DERS_SAATI,
        "dersler": OKUL_DERSLERI,
        "hucreler": [h.to_dict() for h in program],
        "sablon_var": bool(sablon(profil.sinif, profil.alan)),
        "bugun_dersleri": [
            {"ders": anahtar, "ad": ders_adi(anahtar)} for anahtar in bugun
        ],
        "islenen": [i.konu_id for i in islenen],
        "secenekler": {anahtar: konu_secenekleri(db, profil, anahtar) for anahtar in bugun},
    }
