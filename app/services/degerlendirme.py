# -*- coding: utf-8 -*-
"""Deneme sonuçlarının yapay zekâ değerlendirmesi ve deneme takvimi.

Akış:

1. ``analiz_ozeti`` ders ve konu tablosunu üretir (beklenen soru × başarı).
2. ``siklik_oner`` hedef açığına, kalan güne ve deneme geçmişine bakarak
   deneme sıklığını (**3** veya **7** gün) ve gerekçesini belirler.
3. ``degerlendir`` bu sayıları Gemini'ye yorumlatır; anahtar yoksa ya da
   bağlantı kurulamazsa aynı sayılardan yerel değerlendirme metni üretilir.
4. ``deneme_takvimi`` sınav günlerini, türünü (TYT / AYT / branş) ve odak
   konularını hesaplar; ``deneme_takvimi_uret`` bunları plana yazar.
"""
from __future__ import annotations

import json
from datetime import date, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import Ayar, Deneme, DenemeSonuc, PlanItem, Profil
from . import ai as ai_servis
from .analiz import analiz_ozeti
from .hedef import hedef_analizi
from .plan import MATEMATIK_DERSLER

AYAR_ONEKI = "degerlendirme_"
SIKLIKLAR = (3, 7)
DENEME_SURELERI = {"TYT": 165, "AYT": 180, "BRANS": 45}
ANALIZ_DK = 40
AYLAR = (
    "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
)
GUN_ADLARI = (
    "Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar",
)
# Haftalık programda her gün çözülecek paragraf soru sayısı
PARAGRAF_SORU = 20
MATEMATIK_SORU = 20


def _tarih_tr(iso: str) -> str:
    gun = date.fromisoformat(iso)
    return f"{gun.day} {AYLAR[gun.month - 1]}"


def _sayi(deger: float) -> str:
    """100.0 -> 100, 33.33 -> 33,33 gibi gereksiz sıfırları atar."""
    return f"{float(deger):.2f}".rstrip("0").rstrip(".").replace(".", ",")


def _deneme_gecmisi(db: Session, profil_id: int, limit: int = 5) -> list[dict]:
    """Son denemelerin toplam neti (yeniden eskiye)."""
    satirlar: list[dict] = []
    for deneme in db.execute(
        select(Deneme)
        .where(Deneme.profil_id == profil_id)
        .order_by(Deneme.tarih.desc(), Deneme.id.desc())
        .limit(limit)
    ).scalars():
        netler = list(
            db.execute(
                select(DenemeSonuc).where(DenemeSonuc.deneme_id == deneme.id)
            ).scalars()
        )
        satirlar.append(
            {
                "tarih": deneme.tarih.isoformat(),
                "tur": deneme.tur,
                "net": round(sum(n.net for n in netler), 2),
            }
        )
    return satirlar


def _acik_net(hedef: dict) -> float:
    return round(
        max(0.0, hedef["tyt_hedef_net"] - hedef["tyt_mevcut_net"])
        + max(0.0, hedef["ayt_hedef_net"] - hedef["ayt_mevcut_net"]),
        1,
    )


def haftalik_program(
    analiz: dict, gun_sayisi: int = 7, baslangic: date | None = None
) -> dict:
    """Konu açıklarına göre 7 günlük program taslağı.

    Her gün matematik ve paragraf soruları sabittir; günün odak konuları
    "açık konu" tablosundaki en yüksek etkin puanlı konulardan gelir. Aynı
    sıra günlük plan üretiminde de kullanılır, yapay zekâ bu taslağı yorumlar.
    """
    baslangic = baslangic or date.today()
    konular = [k for k in analiz["konular"] if k["beklenen_soru"] > 0]
    matematik = [k for k in konular if k["ders_kod"] in MATEMATIK_DERSLER][:3]
    paragraf = next((k for k in konular if k["ad"].lower().startswith("paragraf")), None)

    odak_havuzu: list[dict] = []
    for grup in analiz.get("konu_aciklari", []):
        for konu in grup["konular"]:
            odak_havuzu.append(
                {
                    "konu_id": konu["konu_id"],
                    "konu": konu["konu"],
                    "ders": grup["ders"],
                    "renk": grup["renk"],
                    "basari_yuzde": konu["basari_yuzde"],
                }
            )
    if not odak_havuzu:
        odak_havuzu = [
            {
                "konu_id": k["id"],
                "konu": k["ad"],
                "ders": k["ders_ad"],
                "renk": k["renk"],
                "basari_yuzde": k["basari_yuzde"],
            }
            for k in konular
        ]

    gunler: list[dict] = []
    for i in range(gun_sayisi):
        tarih = baslangic + timedelta(days=i)
        mat = matematik[i % len(matematik)] if matematik else None
        odak: list[dict] = []
        if odak_havuzu:
            for j in range(min(2, len(odak_havuzu))):
                odak.append(odak_havuzu[(2 * i + j) % len(odak_havuzu)])
        gunler.append(
            {
                "tarih": tarih.isoformat(),
                "tarih_tr": _tarih_tr(tarih.isoformat()),
                "gun_adi": GUN_ADLARI[tarih.weekday()],
                "matematik": (
                    {
                        "konu_id": mat["id"],
                        "konu": mat["ad"],
                        "ders": mat["ders_ad"],
                        "soru": MATEMATIK_SORU,
                    }
                    if mat
                    else None
                ),
                "paragraf": {
                    "konu_id": paragraf["id"] if paragraf else None,
                    "konu": paragraf["ad"] if paragraf else "Paragraf",
                    "soru": PARAGRAF_SORU,
                },
                "odak": odak,
            }
        )

    return {
        "baslangic": baslangic.isoformat(),
        "gun_sayisi": gun_sayisi,
        "gunler": gunler,
        "kural": (
            f"Her gün {MATEMATIK_SORU} matematik ve {PARAGRAF_SORU} paragraf sorusu; "
            "ardından günün odak konuları."
        ),
    }


def siklik_oner(db: Session, profil: Profil, analiz: dict) -> dict:
    """Deneme sıklığını (3 veya 7 gün) gerekçesiyle birlikte önerir."""
    hedef = analiz["hedef"]
    kalan = (profil.sinav_tarihi - date.today()).days
    acik = _acik_net(hedef)
    haftalik = hedef["haftalik_gereken_net"] or 0.0
    gecmis = _deneme_gecmisi(db, profil.id, 3)

    if analiz["deneme_sayisi"] == 0:
        return {
            "gun": 7,
            "gerekce": (
                "Henüz deneme yok: haftada 1 deneme ile başla. İlk 3 denemeden "
                "sonra net artışına göre aralık otomatik olarak 3 güne inebilir."
            ),
        }

    if len(gecmis) >= 3:
        artis = round((gecmis[0]["net"] - gecmis[2]["net"]) / 2, 1)
        if artis < max(0.5, haftalik / 2):
            return {
                "gun": 3,
                "gerekce": (
                    f"Son iki deneme arasındaki net artışı {artis} net; hedef haftada "
                    f"+{haftalik} net. Geri bildirim döngüsünü hızlandırmak için "
                    f"3 günde bir deneme önerilir."
                ),
            }

    if kalan <= 180 and acik >= 40:
        return {
            "gun": 3,
            "gerekce": (
                f"Sınava {kalan} gün kaldı ve {acik} net açık var: 3 günde bir "
                f"deneme ile eksik konular hızla sınanmalı."
            ),
        }

    return {
        "gun": 7,
        "gerekce": (
            f"Sınava {kalan} gün var; haftada +{haftalik} net hedefi haftalık "
            f"deneme temposuna uygun. Açık {acik} net."
        ),
    }


def _sinav_gunu(baslangic: date) -> date:
    """İlk deneme günü: en yakın cumartesi (bugün cumartesiyse bugün)."""
    return baslangic + timedelta(days=(5 - baslangic.weekday()) % 7)


def _zayif_ders(analiz: dict) -> dict | None:
    for acik in analiz["hedef"]["en_buyuk_aciklar"]:
        if acik["hedef"] > 0:
            return acik
    adaylar = [d for d in analiz["dersler"] if d["soru_sayisi"]]
    if not adaylar:
        return None
    en_iyi = min(adaylar, key=lambda d: (d["basari"] if d["basari"] is not None else 0.5))
    return {"ders_kod": en_iyi["kod"], "ders": en_iyi["ad"], "hedef": 0, "mevcut": 0}


def _odak_konular(
    analiz: dict, kapsam: str, ders_kod: str | None = None, adet: int = 3
) -> list[dict]:
    """Etkin puanı en yüksek konular; sınav geneli için ders başına bir tane."""
    if ders_kod:
        satirlar = [k for k in analiz["konular"] if k["ders_kod"] == ders_kod]
    else:
        satirlar = [k for k in analiz["konular"] if k["ders_kod"].startswith(kapsam)]

    secilen: list[dict] = []
    kullanilan: set[str] = set()
    for konu in satirlar:
        if not ders_kod and konu["ders_kod"] in kullanilan:
            continue
        kullanilan.add(konu["ders_kod"])
        secilen.append(
            {
                "konu": konu["ad"],
                "ders": konu["ders_ad"],
                "beklenen_soru": konu["beklenen_soru"],
                "basari_yuzde": konu["basari_yuzde"],
                "etkin_puan": konu["etkin_puan"],
            }
        )
        if len(secilen) >= adet:
            break
    return secilen


def _ders_hedefleri(db: Session, profil: Profil) -> dict[str, float]:
    return {
        d["ders_kod"]: d["hedef_net"] for d in hedef_analizi(db, profil)["dersler"]
    }


def deneme_takvimi(
    db: Session,
    profil: Profil,
    siklik: int = 7,
    hafta: int = 4,
    baslangic: date | None = None,
    analiz: dict | None = None,
) -> dict:
    """Sıklığa göre deneme günlerini, türünü ve odak konularını hesaplar."""
    baslangic = baslangic or date.today()
    siklik = 3 if siklik == 3 else 7
    hafta = max(1, min(8, hafta))
    analiz = analiz or analiz_ozeti(db, profil)
    hedef = analiz["hedef"]
    ders_hedefleri = _ders_hedefleri(db, profil)
    zayif = _zayif_ders(analiz)
    adet = max(1, (hafta * 7) // siklik)
    ilk = _sinav_gunu(baslangic)

    denemeler: list[dict] = []
    for i in range(adet):
        tarih = ilk + timedelta(days=siklik * i)
        if siklik == 3:
            tur = ("TYT", "AYT", "BRANS")[i % 3]
        else:
            tur = ("TYT", "AYT")[i % 2]

        if tur == "BRANS" and zayif:
            kod = zayif["ders_kod"]
            denemeler.append(
                {
                    "tarih": tarih.isoformat(),
                    "tarih_tr": _tarih_tr(tarih.isoformat()),
                    "tur": "Branş",
                    "ad": f"{zayif['ders']} branş denemesi",
                    "ders_kod": kod,
                    "sure_dk": DENEME_SURELERI["BRANS"],
                    "hedef_net": round(ders_hedefleri.get(kod, 0.0), 1),
                    "odak": _odak_konular(analiz, "TYT", kod),
                }
            )
            continue

        denemeler.append(
            {
                "tarih": tarih.isoformat(),
                "tarih_tr": _tarih_tr(tarih.isoformat()),
                "tur": tur,
                "ad": f"{tur} denemesi",
                "ders_kod": "",
                "sure_dk": DENEME_SURELERI[tur],
                "hedef_net": round(
                    hedef["tyt_hedef_net"] if tur == "TYT" else hedef["ayt_hedef_net"], 1
                ),
                "odak": _odak_konular(analiz, tur),
            }
        )

    return {
        "siklik": siklik,
        "hafta": hafta,
        "baslangic": baslangic.isoformat(),
        "bitis": (ilk + timedelta(days=siklik * (adet - 1))).isoformat(),
        "adet": adet,
        "toplam_dk": sum(d["sure_dk"] + ANALIZ_DK for d in denemeler),
        "denemeler": denemeler,
    }


def deneme_takvimi_uret(
    db: Session,
    profil: Profil,
    siklik: int = 7,
    hafta: int = 4,
    baslangic: date | None = None,
) -> dict:
    """Takvimi plana yazar: sınav günleri + analiz bloğu, o günün konu blokları kalkar."""
    takvim = deneme_takvimi(db, profil, siklik, hafta, baslangic)
    tarihler = [date.fromisoformat(d["tarih"]) for d in takvim["denemeler"]]
    aralik = (tarihler[0], tarihler[-1])

    # Aynı aralıktaki bekleyen deneme/analiz maddeleri tazelenir
    silinen = db.execute(
        delete(PlanItem).where(
            PlanItem.profil_id == profil.id,
            PlanItem.tur == "deneme",
            PlanItem.durum == "bekliyor",
            PlanItem.tarih >= aralik[0],
            PlanItem.tarih <= aralik[1],
        )
    ).rowcount or 0

    # Aylık planın yazdığı "Deneme analizi" blokları da çiftlenmesin diye silinir
    silinen += (
        db.execute(
            delete(PlanItem).where(
                PlanItem.profil_id == profil.id,
                PlanItem.baslik.like("Deneme analizi%"),
                PlanItem.durum == "bekliyor",
                PlanItem.tarih >= aralik[0],
                PlanItem.tarih <= aralik[1],
            )
        ).rowcount
        or 0
    )

    # Sınav gününde konu/soru blokları yerine deneme yazılır
    silinen += (
        db.execute(
            delete(PlanItem).where(
                PlanItem.profil_id == profil.id,
                PlanItem.tur.in_(("konu", "soru")),
                PlanItem.durum == "bekliyor",
                PlanItem.tarih.in_(tarihler),
            )
        ).rowcount
        or 0
    )

    eklenen = 0
    for deneme in takvim["denemeler"]:
        tarih = date.fromisoformat(deneme["tarih"])
        db.add(
            PlanItem(
                profil_id=profil.id,
                tarih=tarih,
                ders_kod=deneme["ders_kod"],
                konu_id=None,
                baslik=f"{deneme['ad']} · hedef {deneme['hedef_net']} net",
                tur="deneme",
                sure_dk=deneme["sure_dk"],
                durum="bekliyor",
                sira=1,
            )
        )
        db.add(
            PlanItem(
                profil_id=profil.id,
                tarih=tarih,
                ders_kod=deneme["ders_kod"],
                konu_id=None,
                baslik="Deneme analizi: yanlış konuları işaretle",
                tur="tekrar",
                sure_dk=ANALIZ_DK,
                durum="bekliyor",
                sira=2,
            )
        )
        eklenen += 2
    db.commit()

    return {"eklenen": eklenen, "silinen": silinen, "takvim": takvim}


def _yerel_metin(
    analiz: dict, gecmis: list[dict], takvim: dict, karar: dict, program: dict
) -> str:
    """Anahtar yokken aynı sayılardan üretilen değerlendirme."""
    hedef = analiz["hedef"]
    acik = _acik_net(hedef)
    satirlar = [
        "### Genel durum",
        f"Hedef sıralama **{hedef['hedef_siralama']}** için TYT **{_sayi(hedef['tyt_hedef_net'])}** / "
        f"AYT **{_sayi(hedef['ayt_hedef_net'])}** net gerekiyor. En iyi denemelerin TYT "
        f"{_sayi(hedef['tyt_mevcut_net'])} / AYT {_sayi(hedef['ayt_mevcut_net'])} net; açık "
        f"**{_sayi(acik)}** net. Kayıtlı deneme: **{analiz['deneme_sayisi']}**.",
    ]
    if analiz["deneme_sayisi"] == 0:
        satirlar.append(
            "> Henüz deneme girilmediği için ders başarıları %50 varsayılıyor; "
            "ilk denemeden sonra sıralama gerçek doğru/yanlış oranlarına göre değişir."
        )

    if analiz.get("konu_aciklari"):
        satirlar.append("\n### Konu bazlı açıklar")
        for grup in analiz["konu_aciklari"][:4]:
            detay = "; ".join(
                f"{k['konu']} (%{k['basari_yuzde']}"
                + (f", {k['deneme_yanlis']} deneme yanlışı" if k["deneme_yanlis"] else "")
                + ")"
                for k in grup["konular"]
            )
            satirlar.append(
                f"- **{grup['ders']}** ({grup['acik_sayisi']} açık konu): {detay}"
            )

    satirlar.append("\n### Ders bazında açık netler")
    for acik_ders in hedef["en_buyuk_aciklar"][:3]:
        satirlar.append(
            f"- **{acik_ders['ders']}**: hedef {_sayi(acik_ders['hedef'])} net, "
            f"en iyin {_sayi(acik_ders['mevcut'])} net → açık {_sayi(acik_ders['acik'])} net"
        )

    satirlar.append("\n### Konu önceliği (beklenen soru × başarı)")
    for i, konu in enumerate(analiz["en_cok_kazanc"][:5], start=1):
        satirlar.append(
            f"{i}. **{konu['ad']}** ({konu['ders_ad']}) — YKS'de beklenen "
            f"{_sayi(konu['beklenen_soru'])} soru, başarın %{konu['basari_yuzde']} "
            f"→ etkin puan {_sayi(konu['etkin_puan'])}"
        )

    satirlar.append("\n### Haftalık program (her gün matematik + paragraf)")
    for gun in program["gunler"]:
        parcalar = []
        if gun["matematik"]:
            parcalar.append(
                f"Matematik {gun['matematik']['soru']} soru "
                f"({gun['matematik']['konu']})"
            )
        parcalar.append(f"Paragraf {gun['paragraf']['soru']} soru")
        if gun["odak"]:
            parcalar.append("Odak: " + ", ".join(k["konu"] for k in gun["odak"]))
        satirlar.append(f"- **{gun['gun_adi']}**: " + " · ".join(parcalar))

    satirlar.append(f"\n### Deneme planı ({takvim['siklik']} günde bir)")
    satirlar.append(karar["gerekce"])
    for deneme in takvim["denemeler"][:4]:
        odak = ", ".join(k["konu"] for k in deneme["odak"][:2])
        satirlar.append(
            f"- **{deneme['tarih_tr']}** · {deneme['ad']} ({deneme['sure_dk']} dk, "
            f"hedef {_sayi(deneme['hedef_net'])} net)" + (f" · odak: {odak}" if odak else "")
        )

    satirlar.append("\n### Bu hafta 3 adım")
    ilk = takvim["denemeler"][0] if takvim["denemeler"] else None
    if analiz["en_cok_kazanc"]:
        k1 = analiz["en_cok_kazanc"][0]
        satirlar.append(f"1. {k1['ders_ad']} - {k1['ad']} konusunu bitir, ardından 20 soru çöz.")
    if len(analiz["en_cok_kazanc"]) > 1:
        k2 = analiz["en_cok_kazanc"][1]
        satirlar.append(f"2. {k2['ders_ad']} - {k2['ad']} için hata defterine 10 yanlış yaz.")
    if ilk:
        satirlar.append(
            f"3. {ilk['tarih_tr']} günü {ilk['ad']} çöz; hedef {_sayi(ilk['hedef_net'])} net."
        )
    if gecmis:
        satirlar.append(
            f"\n> Son deneme: {_tarih_tr(gecmis[0]['tarih'])} · {gecmis[0]['tur']} · "
            f"{_sayi(gecmis[0]['net'])} net."
        )
    return "\n".join(satirlar)


def _istem(
    profil: Profil,
    analiz: dict,
    gecmis: list[dict],
    takvim: dict,
    karar: dict,
    program: dict,
) -> tuple[str, str]:
    hedef = analiz["hedef"]
    dersler = [
        {
            "ders": d["ad"],
            "sinav": d["sinav"],
            "basari_yuzde": d["basari_yuzde"],
            "net": d["net"],
            "seviye": d["seviye"],
        }
        for d in sorted(
            analiz["dersler"],
            key=lambda d: (d["basari"] if d["basari"] is not None else 1.0),
        )[:8]
    ]
    konular = [
        {
            "konu": k["ad"],
            "ders": k["ders_ad"],
            "beklenen_soru": k["beklenen_soru"],
            "basari_yuzde": k["basari_yuzde"],
            "etkin_puan": k["etkin_puan"],
        }
        for k in analiz["en_cok_kazanc"]
    ]
    takvim_ozet = [
        {
            "tarih": d["tarih_tr"],
            "sinav": d["ad"],
            "sure_dk": d["sure_dk"],
            "hedef_net": d["hedef_net"],
            "odak": [k["konu"] for k in d["odak"]],
        }
        for d in takvim["denemeler"]
    ]
    konu_aciklari = [
        {
            "ders": grup["ders"],
            "acik_sayisi": grup["acik_sayisi"],
            "konular": [
                {
                    "konu": k["konu"],
                    "basari_yuzde": k["basari_yuzde"],
                    "deneme_yanlis": k["deneme_yanlis"],
                }
                for k in grup["konular"]
            ],
        }
        for grup in analiz.get("konu_aciklari", [])
    ]
    program_ozet = [
        {
            "gun": gun["gun_adi"],
            "matematik": gun["matematik"]["konu"] if gun["matematik"] else "",
            "paragraf_soru": gun["paragraf"]["soru"],
            "odak": [k["konu"] for k in gun["odak"]],
        }
        for gun in program["gunler"]
    ]
    sistem = (
        "Sen Türkiye'de YKS'ye hazırlanan bir öğrencinin ölçme-değerlendirme koçusun. "
        "Sana deneme sonuçları, ders başarı oranları, derslerin içindeki açık konular, "
        "konuların YKS'de beklenen soru sayıları, hedef netler, hazırlanmış bir haftalık "
        "program ve deneme takvimi verilir. Yorumunu yalnızca bu sayılara dayandır; "
        "uydurma istatistik, kaynak, kitap veya tarih verme. Türkçe yaz, öğrenciye 'sen' "
        "diye hitap et, en fazla 300 kelime kullan. Ders adıyla yetinme, açığı konu "
        "adıyla söyle. Şu başlıkları sırayla kullan: '### Genel durum', '### Konu bazlı "
        "açıklar', '### Açığı en hızlı kapatan 3 hamle', '### Haftalık program', "
        "'### Deneme planı yorumu'. Haftalık programda her gün matematik ve paragraf "
        "soruları zorunludur; verilen programın mantığını açıkla, tarihleri ve sıklığı "
        "değiştirme."
    )
    mesaj = (
        f"Öğrenci: {profil.ad}, {profil.alan_etiketi}, {profil.sinif_etiketi}, "
        f"günlük {profil.gunluk_hedef_dk} dk, sınava {(profil.sinav_tarihi - date.today()).days} gün.\n"
        f"Hedef sıralama {hedef['hedef_siralama']}: TYT {hedef['tyt_hedef_net']} / "
        f"AYT {hedef['ayt_hedef_net']} net. En iyi denemeler: TYT {hedef['tyt_mevcut_net']} / "
        f"AYT {hedef['ayt_mevcut_net']} net. Açık {_acik_net(hedef)} net.\n"
        f"Deneme sayısı: {analiz['deneme_sayisi']}. Son denemeler: {gecmis}.\n"
        f"Zayıf dersler (yüzde): {dersler}.\n"
        f"Açık konu sayısı: {analiz.get('acik_konu_sayisi', 0)}. Ders bazında açık konular: {konu_aciklari}.\n"
        f"Öncelikli konular: {konular}.\n"
        f"Haftalık program (her gün matematik + paragraf): {program_ozet}.\n"
        f"Deneme sıklığı kararı: {karar['gun']} günde bir. Gerekçe: {karar['gerekce']}\n"
        f"Takvim: {takvim_ozet}."
    )
    if analiz["deneme_sayisi"] == 0:
        mesaj += (
            "\nNot: Henüz deneme girilmediği için ders başarı oranları %50 varsayımıdır; "
            "metinde bunu belirt ve ilk denemenin en kısa sürede girilmesini öner."
        )
    return sistem, mesaj


def degerlendir(db: Session, profil: Profil, siklik: int = 0) -> dict:
    """AI (varsa) + yerel yedek ile değerlendirme üretir ve sonucu saklar."""
    analiz = analiz_ozeti(db, profil)
    karar = siklik_oner(db, profil, analiz)
    if siklik in SIKLIKLAR and siklik != karar["gun"]:
        karar = {
            "gun": siklik,
            "gerekce": f"{karar['gerekce']} (aralık elle {siklik} gün seçildi.)",
        }
    takvim = deneme_takvimi(db, profil, siklik=karar["gun"], hafta=4, analiz=analiz)
    gecmis = _deneme_gecmisi(db, profil.id, 5)
    program = haftalik_program(analiz)

    ai_sonuc = ai_servis.model_cagir(
        db, *_istem(profil, analiz, gecmis, takvim, karar, program)
    )
    if ai_sonuc["ok"]:
        metin, kaynak, model, notu = ai_sonuc["metin"], "gemini", ai_sonuc["model"], ""
    else:
        metin = _yerel_metin(analiz, gecmis, takvim, karar, program)
        kaynak, model = "yerel", ai_sonuc.get("model", "")
        notu = f"Yapay zekâya ulaşılamadı: {ai_sonuc.get('sebep', 'bilinmeyen hata')}."

    kayit = {
        "var": True,
        "metin": metin,
        "kaynak": kaynak,
        "model": model,
        "not": notu,
        "siklik": karar["gun"],
        "gerekce": karar["gerekce"],
        "olusturma": date.today().isoformat(),
        "deneme_sayisi": analiz["deneme_sayisi"],
        "acik_net": _acik_net(analiz["hedef"]),
        "acik_konu_sayisi": analiz.get("acik_konu_sayisi", 0),
        "konu_aciklari": analiz.get("konu_aciklari", []),
        "program": program,
    }
    deger = json.dumps(kayit, ensure_ascii=False)
    db.merge(Ayar(anahtar=f"{AYAR_ONEKI}{profil.id}", deger=deger))
    db.commit()
    return {**kayit, "takvim": takvim}


def kayitli_degerlendirme(db: Session, profil: Profil) -> dict:
    """Saklanan son değerlendirme + güncel takvim ve program önizlemesi."""
    ayar = db.get(Ayar, f"{AYAR_ONEKI}{profil.id}")
    if not ayar or not ayar.deger:
        return {"var": False}
    try:
        kayit = json.loads(ayar.deger)
    except json.JSONDecodeError:
        return {"var": False}
    analiz = analiz_ozeti(db, profil)
    takvim = deneme_takvimi(db, profil, siklik=kayit.get("siklik", 7), hafta=4, analiz=analiz)
    return {
        **kayit,
        "var": True,
        "takvim": takvim,
        "program": haftalik_program(analiz),
        "konu_aciklari": analiz.get("konu_aciklari", []),
        "acik_konu_sayisi": analiz.get("acik_konu_sayisi", 0),
    }
