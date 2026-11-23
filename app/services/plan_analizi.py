# -*- coding: utf-8 -*-
"""Planın yapay zekâ analizi: ders payları ve odak konular.

Plan motoru hedef net açıklarını, konu ağırlıklarını ve deneme kanıtını
deterministik kurallarla birleştiriyordu. Bu modül aynı veriyi modele
yorumlatır:

1. ``baglam`` hedef sıralamayı, deneme soru/net sayılarını, konuların beklenen
   soru ağırlığını, Maarif Modeli beceri kodlarını ve (11/12. sınıfta) okul
   çizelgesiyle işlenen konuları tek JSON'da toplar.
2. ``analiz_calistir`` bu veriyi Gemini'ye yorumlatır; model ders paylarını
   (yüzde) ve odak konuları gerekçeleriyle döndürür.
3. Sonuç ``Ayarlar`` tablosunda profil bazında saklanır. Plan motoru payları
   kendi hesabıyla harmanlar (``plan.plan_agirliklari``) ve odak konuları öne
   alır (``plan.oncelikli_konular``).
4. Anahtar yoksa ya da model yanıt vermezse plan deterministik kurallarla
   üretilmeye devam eder; arayüz bunu açıkça yazar. Mezun profilde okul
   çizelgesi yoktur: paylar TYT ve AYT konularına göre kurulur.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..data import BECERI_ETIKET, alan_ders_kodlari
from ..models import Ayar, Deneme, Ders, Konu, Profil
from . import ai as ai_servis
from . import ders_programi as okul_servisi
from . import sinif as sinif_servisi
from .analiz import ders_tablosu, konu_tablosu
from .hedef import hedef_analizi

ONEK = "plan_analizi_"
# Analiz bu süreden eskiyse plan üretiminde kendiliğinden yenilenir
GECERLIK_SAAT = 12
# Modele gösterilecek en fazla konu adayı ve kabul edilecek odak konu sayısı
AZAMI_ADAY = 30
AZAMI_ODAK = 8
AZAMI_GEREKCE = 160

_SISTEM = """Sen Türkiye'de YKS'ye hazırlanan bir öğrenci için çalışma planı analistisin.
Sana hedef sıralama, deneme netleri, derslerin sınavdaki soru sayısı, konuların
beklenen soru ağırlığı ve başarı oranları, Maarif Modeli beceri kodları ve
(varsa) okul ders programı verilir.
Görevin: günlük çalışma süresinin derslere dağılımını ve önce çalışılacak
konuları belirlemek.

Kurallar:
1. Türkiye Yüzyılı Maarif Modeli'ni gözet: 2028 YKS beceri ve bağlam
   temellidir; KB kavramsal, AB alan, SD sosyal-duygusal, OK okuryazarlık
   becerileri dengelenir, ezber değil uygulama ölçülür.
2. Hedef sıralamanın gerektirdiği net ile mevcut net arasındaki açığı en büyük
   derse daha çok süre ver; hiçbir dersi tamamen dışlama (en az %2).
3. Sınavdaki soru sayısı yüksek ve deneme başarısı düşük ders öne çıkar.
   Beklenen soru sayısı yüksek, başarısı düşük konu odak listesine girer;
   başarısı zaten yüksek konuya geniş yer ayırma.
4. Yalnız verilen ders kodlarını ve konu adaylarını kullan; kapsam dışı konu
   önerme.
5. Öğrenci mezunsa okul çizelgesi yoktur; payları TYT ve AYT konularına göre
   kur. Okulluysa okulda işlenen konular akşam tekrar bloğunda ele alınır;
   paylarda bu tekrara ayrılan süreyi hesaba kat.
6. "ders_paylari" toplamı 100 olmalı; anahtar ders kodu, değer yüzde.
   "odak_konular" en fazla 8 konu içerir ve her biri gerekçelidir.
7. Yanıtı yalnız şu JSON şemasıyla ver; JSON dışında metin yazma:
{"ozet": "kısa gerekçe, en fazla 2 cümle",
 "ders_paylari": {"DERS-KOD": 25},
 "odak_konular": [{"kod": "KONU-KOD", "gerekce": "neden önce"}],
 "strateji": ["haftalık uygulama notu"],
 "riskler": ["dikkat edilecek nokta"]}"""


def _anahtar(profil_id: int) -> str:
    return f"{ONEK}{profil_id}"


def _kisa(deger, sinir: int) -> str:
    return " ".join(str(deger or "").split())[:sinir]


def _liste(ham, adet: int) -> list[str]:
    if not isinstance(ham, list):
        return []
    return [metin for metin in (_kisa(s, 220) for s in ham) if metin][:adet]


def _yaz(db: Session, profil_id: int, veri: dict) -> None:
    anahtar = _anahtar(profil_id)
    metin = json.dumps(veri, ensure_ascii=False)
    satir = db.get(Ayar, anahtar)
    if satir is None:
        db.add(Ayar(anahtar=anahtar, deger=metin))
    else:
        satir.deger = metin
    db.commit()


def son_analiz(db: Session, profil: Profil) -> dict | None:
    """Kaydedilmiş son analiz (yoksa ``None``)."""
    satir = db.get(Ayar, _anahtar(profil.id))
    if satir is None or not (satir.deger or "").strip():
        return None
    try:
        veri = json.loads(satir.deger)
    except json.JSONDecodeError:
        return None
    return veri if isinstance(veri, dict) else None


def taze_mi(kayit: dict | None) -> bool:
    """Analiz ``GECERLIK_SAAT`` içinde üretildi mi?"""
    if not kayit:
        return False
    try:
        zaman = datetime.fromisoformat(str(kayit.get("zaman", "")))
    except ValueError:
        return False
    return datetime.now() - zaman < timedelta(hours=GECERLIK_SAAT)


def durum(db: Session, profil: Profil) -> dict:
    """Arayüzün analiz kartını çizmesi için özet."""
    kayit = son_analiz(db, profil)
    return {
        "ai": ai_servis.ai_aktif(db),
        "analiz": kayit,
        "taze": taze_mi(kayit),
        "gecerlilik_saat": GECERLIK_SAAT,
    }


def paylari(db: Session, profil: Profil) -> dict[str, float]:
    """Ders kodu -> pay (toplamı 1). Analiz yoksa boş sözlük."""
    kayit = son_analiz(db, profil)
    if not kayit:
        return {}
    ham: dict[str, float] = {}
    for satir in kayit.get("paylar") or []:
        if not isinstance(satir, dict):
            continue
        kod = str(satir.get("kod") or "")
        try:
            pay = float(satir.get("pay") or 0)
        except (TypeError, ValueError):
            continue
        if kod and pay > 0:
            ham[kod] = ham.get(kod, 0.0) + pay
    toplam = sum(ham.values())
    if toplam <= 0:
        return {}
    return {kod: pay / toplam for kod, pay in ham.items()}


def odak_idleri(db: Session, profil: Profil) -> set[int]:
    """Analizin öne aldığı konuların kimlikleri."""
    kayit = son_analiz(db, profil)
    if not kayit:
        return set()
    kimlikler: set[int] = set()
    for satir in kayit.get("odak") or []:
        if not isinstance(satir, dict):
            continue
        try:
            kimlikler.add(int(satir.get("konu_id")))
        except (TypeError, ValueError):
            continue
    return kimlikler


def baglam(db: Session, profil: Profil) -> dict:
    """Modele verilecek sayısal özet: hedef, deneme, konu ağırlığı, okul."""
    hedef = hedef_analizi(db, profil)
    ders_satirlari = ders_tablosu(db, profil)
    deneme_map = {s["kod"]: s for s in ders_satirlari}
    dersler = []
    for satir in hedef["dersler"]:
        deneme = deneme_map.get(satir["ders_kod"], {})
        dersler.append(
            {
                "kod": satir["ders_kod"],
                "ad": satir["ad"],
                "sinav": satir["sinav"],
                "sinavdaki_soru": satir["soru"],
                "hedef_net": satir["hedef_net"],
                "mevcut_net": satir["mevcut_net"],
                "acik_net": satir["acik"],
                "hedef_orani": satir["oran"],
                "deneme_neti": deneme.get("net"),
                "deneme_basari_yuzde": deneme.get("basari_yuzde"),
                "seviye": deneme.get("seviye"),
            }
        )

    konular = konu_tablosu(db, profil, ders_satirlari)
    kayitlar = {
        k.id: k
        for k in db.execute(
            select(Konu).where(Konu.ders_kod.in_(alan_ders_kodlari(profil.alan)))
        ).scalars()
    }
    adaylar = []
    for satir in konular:
        # Kapsam dışı konu (ör. 11. sınıfta 12. sınıf konusu) önerilmez
        if satir["kapsam_disi"] or satir["beklenen_soru"] <= 0:
            continue
        kayit = kayitlar.get(satir["id"])
        beceriler = [b for b in ((kayit.beceri if kayit else "") or "").split(",") if b]
        adaylar.append(
            {
                "kod": satir["kod"],
                "konu_id": satir["id"],
                "konu": satir["ad"],
                "ders": satir["ders_ad"],
                "ders_kod": satir["ders_kod"],
                "sinif": satir["sinif"],
                "beklenen_soru": satir["beklenen_soru"],
                "agirlik_payi": satir["agirlik_payi"],
                "basari_yuzde": satir["basari_yuzde"],
                "deneme_yanlis": satir["deneme_yanlis"],
                "durum": satir["durum"],
                "beceri": [BECERI_ETIKET.get(b, b) for b in beceriler],
            }
        )
        if len(adaylar) >= AZAMI_ADAY:
            break

    okul: dict = {"okul_var": bool(profil.sinif)}
    if profil.sinif:
        program = okul_servisi.program_oku(db, profil.id)
        bugun = okul_servisi.gunun_dersleri(program, date.today())
        okul["bugun_dersleri"] = [okul_servisi.ders_adi(anahtar) for anahtar in bugun]
        okul["islenen"] = [
            {"konu": konu["ad"], "ders": konu["ders_ad"]}
            for grup in okul_servisi.son_islenenler(db, profil, 7)[:7]
            for konu in grup["konular"]
        ][:12]
    else:
        okul["not"] = (
            "Mezun öğrenci: okul çizelgesi yok; plan TYT ve AYT konularına göre kurulur."
        )

    deneme_sayisi = int(
        db.execute(
            select(func.count(Deneme.id)).where(Deneme.profil_id == profil.id)
        ).scalar()
        or 0
    )
    return {
        "ogrenci": {
            "sinif": profil.sinif_etiketi,
            "alan": profil.alan_etiketi,
            "durum": "mezun" if not profil.sinif else "okullu",
            "hedef_siralama": hedef["hedef_siralama"],
            "kalan_gun": hedef["kalan_gun"],
            "gunluk_hedef_dk": profil.gunluk_hedef_dk,
        },
        "kapsam": sinif_servisi.kapsam_etiketi(profil.sinif),
        "hedef_netler": {
            "tyt_hedef": hedef["tyt_hedef_net"],
            "tyt_mevcut": hedef["tyt_mevcut_net"],
            "tyt_acik": hedef["tyt_acik"],
            "ayt_hedef": hedef["ayt_hedef_net"],
            "ayt_mevcut": hedef["ayt_mevcut_net"],
            "ayt_acik": hedef["ayt_acik"],
            "haftalik_gereken_net": hedef["haftalik_gereken_net"],
            "tamamlanma_yuzde": hedef["tamamlanma"],
        },
        "deneme_sayisi": deneme_sayisi,
        "dersler": dersler,
        "konu_adaylari": adaylar,
        "okul": okul,
    }


def _temizle(ham: dict, veri: dict, ders_map: dict[str, Ders]) -> dict | None:
    """Model yanıtını doğrular: geçersiz ders/konu atılır, paylar 100'e çekilir."""
    kodlar = {d["kod"] for d in veri["dersler"]}
    ham_paylar = ham.get("ders_paylari")
    if not isinstance(ham_paylar, dict):
        return None

    paylar = []
    for kod, deger in ham_paylar.items():
        ders = ders_map.get(str(kod))
        if ders is None or str(kod) not in kodlar:
            continue
        try:
            pay = float(deger)
        except (TypeError, ValueError):
            continue
        if pay <= 0:
            continue
        paylar.append(
            {
                "kod": ders.kod,
                "ad": ders.ad,
                "sinav": ders.sinav,
                "renk": ders.renk,
                "pay": pay,
            }
        )
    toplam = sum(satir["pay"] for satir in paylar)
    if toplam <= 0:
        return None
    for satir in paylar:
        satir["pay"] = round(100 * satir["pay"] / toplam, 1)
    paylar.sort(key=lambda satir: -satir["pay"])

    adaylar = {a["kod"]: a for a in veri["konu_adaylari"]}
    odak = []
    gorulen: set[str] = set()
    for satir in ham.get("odak_konular") or []:
        if not isinstance(satir, dict):
            continue
        kod = str(satir.get("kod") or "")
        konu = adaylar.get(kod)
        if konu is None or kod in gorulen:
            continue
        gorulen.add(kod)
        odak.append(
            {
                "konu_id": konu["konu_id"],
                "kod": kod,
                "konu": konu["konu"],
                "ders": konu["ders"],
                "ders_kod": konu["ders_kod"],
                "gerekce": _kisa(satir.get("gerekce"), AZAMI_GEREKCE),
            }
        )
        if len(odak) >= AZAMI_ODAK:
            break

    return {
        "ozet": _kisa(ham.get("ozet"), 400),
        "paylar": paylar,
        "odak": odak,
        "strateji": _liste(ham.get("strateji"), 4),
        "riskler": _liste(ham.get("riskler"), 3),
    }


def analiz_calistir(db: Session, profil: Profil, zorla: bool = False) -> dict:
    """Analizi üretir (gerekliyse) ve kaydeder.

    ``zorla=False`` iken ``GECERLIK_SAAT`` içinde üretilmiş kayıt yeniden
    kullanılır; plan üretimi her tıklamada modele gitmez.
    """
    mevcut = son_analiz(db, profil)
    if mevcut and not zorla and taze_mi(mevcut):
        return {"ok": True, "yenilendi": False, **mevcut}

    if not ai_servis.ai_aktif(db):
        return {
            "ok": False,
            "yenilendi": False,
            "sebep": "Yapay zekâ anahtarı tanımlı değil (Ayarlar → Yapay Zekâ).",
            "analiz": mevcut,
        }

    veri = baglam(db, profil)
    yanit = ai_servis.json_cagir(
        db,
        _SISTEM,
        json.dumps(veri, ensure_ascii=False, indent=None),
    )
    if not yanit.get("ok"):
        return {
            "ok": False,
            "yenilendi": False,
            "sebep": yanit.get("sebep") or "Model yanıt vermedi.",
            "analiz": mevcut,
        }

    temiz = _temizle(yanit["veri"], veri, {d.kod: d for d in db.execute(select(Ders)).scalars()})
    if temiz is None:
        return {
            "ok": False,
            "yenilendi": False,
            "sebep": "Model geçerli ders payı üretmedi.",
            "analiz": mevcut,
        }

    temiz.update(
        {
            "zaman": datetime.now().isoformat(timespec="seconds"),
            "model": yanit.get("model", ""),
            "kapsam": veri["kapsam"],
        }
    )
    _yaz(db, profil.id, temiz)
    return {"ok": True, "yenilendi": True, **temiz}
