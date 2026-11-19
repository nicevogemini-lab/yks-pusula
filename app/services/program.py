# -*- coding: utf-8 -*-
"""Gün akışı: okul, öğün, mola ve uyku saatleriyle günlük zaman çizelgesi.

Plan motoru (``plan.py``) *hangi konunun* çalışılacağını deneme sonuçlarına ve
hedefe göre belirler; bu modül çalışmayı **gerçek gün içine** yerleştirir.

Çerçevenin dayanakları:

* **PDR (rehberlik) önerileri** — sabit kalkış/yatış saati (≈8 saat uyku),
  okuldan dönüşte 20 dakikalık geçiş molası, 40-50 dakikalık bloklar, bloklar
  arası 10 dakika ekransız mola, yatmadan 45 dakika önce çalışmanın bitmesi,
  haftada bir yarım gün serbest zaman, denemenin gerçek sınav saatinde (10.15)
  çözülmesi.
* **Maarif Modeli** — her konu KB (kavramsal), AB (alan), SD (sosyal-duygusal),
  OK (okuryazarlık) beceri kodlarıyla eşleşir; haftalık beceri dengesi
  raporlanır ve pazar günü SD öz değerlendirme bloğu yer alır.
* **Deneme sonuçları** — denemede yanlış çıkan konuya ayrılan dakika payı
  hesaplanır (``deneme_odagi``).

Okul saatleri, uyanış ve yatış saati profilden gelir; öğrenci gerçek düzenine
göre Ayarlar'dan değiştirebilir.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..data import BECERI_ETIKET
from ..models import Konu, PlanItem, Profil

# --------------------------------------------------------------- PDR sabitleri
MOLA_DK = 10  # iki çalışma maddesi arası mola
BLOK_AZAMI_DK = 50  # tek blokta kesintisiz çalışma üst sınırı
GECIS_MOLA_DK = 20  # okuldan dönüş sonrası zihinsel geçiş molası
AKSAM_YEMEGI_DK = 45
YEMEK_SONRASI_MOLA_DK = 15
ARA_MOLA_DK = 10
KAPANIS_DK = 30  # günü kapatma: plan kontrolü, çanta, yarın
YATIS_HAZIRLIK_DK = 15
UYKU_ONCESI_BOSLUK_DK = 45  # yatmadan önce çalışmanın bittiği süre
OKUL_GUNU_AZAMI_DK = 285  # okul gününde önerilen üst sınır (~4,5 saat)

VARSAYILAN_UYANMA = "06:45"
VARSAYILAN_YATMA = "22:45"
VARSAYILAN_OKUL_BASLANGIC = "08:20"
VARSAYILAN_OKUL_BITIS = "15:20"
VARSAYILAN_DONUS_DK = 35  # okuldan eve dönüş süresi (girilmezse)

GUN_ADLARI = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
TIP_ETIKET = {
    "okul": "Okul günü",
    "deneme": "Deneme günü",
    "hafta_sonu": "Hafta sonu",
}


def _dk(saat: str | None, varsayilan: str = "") -> int:
    """'06:45' -> 405 (gece yarısından itibaren dakika)."""
    metin = (saat or varsayilan or "").strip()
    try:
        saat_kismi, dakika_kismi = metin.split(":")
        toplam = int(saat_kismi) * 60 + int(dakika_kismi)
    except (AttributeError, ValueError):
        return -1
    if not 0 <= toplam < 24 * 60:
        return -1
    return toplam


def _ss(dakika: int) -> str:
    """405 -> '06:45'."""
    dakika = max(0, min(24 * 60 - 1, int(dakika)))
    return f"{dakika // 60:02d}:{dakika % 60:02d}"


def _profil_saati(profil: Profil | None, alan: str, varsayilan: str) -> int:
    deger = getattr(profil, alan, None) if profil is not None else None
    dakika = _dk(deger)
    return dakika if dakika >= 0 else _dk(varsayilan)


def _dilim(bas: int, bit: int, baslik: str, tur: str, aciklama: str = "") -> dict:
    return {
        "baslangic": _ss(bas),
        "bitis": _ss(bit),
        "baslik": baslik,
        "tur": tur,
        "aciklama": aciklama,
    }


def _pencere(bas: int, bit: int, baslik: str) -> dict:
    return {
        "baslangic": _ss(bas),
        "bitis": _ss(bit),
        "baslik": baslik,
        "kapasite_dk": max(0, bit - bas),
    }


# ------------------------------------------------------------ gün çerçeveleri
def _okul_cercevesi(
    uyanma: int, yatis: int, okul_bas: int, okul_bit: int, donus: int
) -> tuple[list[dict], list[dict]]:
    """Hafta içi: okul, öğünler ve akşam çalışma pencereleri.

    ``donus`` öğrencinin okuldan **eve varış** saatidir; aradaki süre yol +
    atıştırma olarak işaretlenir.
    """
    rutin: list[dict] = []

    # Sabah hazırlığı okul saatine göre sıkışır (uyanış geçse bile taşmaz)
    sabah = max(45, okul_bas - uyanma)
    hazirlik = min(20, max(10, sabah // 3))
    kahvalti = min(25, max(10, sabah // 3))
    if hazirlik + kahvalti > sabah:
        kahvalti = max(10, sabah - hazirlik)

    rutin.append(
        _dilim(uyanma, uyanma + hazirlik, "Uyanış ve hazırlık", "hazirlik",
               "Sabit kalkış saati biyolojik saati düzenler; alarmı erteleme.")
    )
    rutin.append(
        _dilim(uyanma + hazirlik, uyanma + hazirlik + kahvalti, "Kahvaltı", "yemek",
               "Protein + tam tahıl. Ağır ya da şekerli kahvaltı ilk blokta uyku getirir.")
    )
    rutin.append(
        _dilim(uyanma + hazirlik + kahvalti, okul_bas, "Yol ve okula varış", "ulasim")
    )

    if okul_bit - okul_bas >= 300:
        ogle = okul_bas + 200
        rutin.append(
            _dilim(okul_bas, ogle, "Okul (1. yarı)", "okul",
                   "Derste aktif dinle; anlamadığın yeri işaretle, akşam oraya dön.")
        )
        rutin.append(
            _dilim(ogle, ogle + 40, "Öğle arası: yemek + dinlenme", "yemek",
                   "Yemekten sonra 10 dk yürüyüş. Öğle arasında ders çalışılmaz.")
        )
        rutin.append(_dilim(ogle + 40, okul_bit, "Okul (2. yarı)", "okul"))
    else:
        rutin.append(_dilim(okul_bas, okul_bit, "Okul", "okul"))

    gecis = donus + GECIS_MOLA_DK
    rutin.append(_dilim(okul_bit, donus, "Eve dönüş + atıştırma", "ulasim",
                        "Girilen dönüş saatine göre eve varış; çantayı bırak, telefonu bir kenara koy."))
    rutin.append(
        _dilim(donus, gecis, "Geçiş molası: ekransız dinlenme", "mola",
               "Okuldan çıkar çıkmaz masaya oturmak verimi düşürür; 20 dakika nefes al.")
    )

    pencereler: list[dict] = []
    kapanis_bas = yatis - (KAPANIS_DK + YATIS_HAZIRLIK_DK)
    kalan = kapanis_bas - gecis

    if kalan < 90:
        # Okul geç bitiyorsa tek kısa blok yeterli
        sure = max(30, kalan - AKSAM_YEMEGI_DK)
        pencereler.append(_pencere(gecis, gecis + sure, "Çalışma bloğu"))
        yemek_bas = gecis + sure
        rutin.append(_dilim(yemek_bas, yemek_bas + AKSAM_YEMEGI_DK, "Akşam yemeği + aile", "yemek"))
    else:
        net = kalan - AKSAM_YEMEGI_DK - YEMEK_SONRASI_MOLA_DK - ARA_MOLA_DK
        w1 = max(35, round(net * 0.38))
        w2 = max(30, round(net * 0.32))
        w3 = max(30, net - w1 - w2)

        p1 = gecis
        pencereler.append(_pencere(p1, p1 + w1, "1. blok"))
        yemek_bas = p1 + w1
        rutin.append(
            _dilim(yemek_bas, yemek_bas + AKSAM_YEMEGI_DK, "Akşam yemeği + aile", "yemek",
                   "Yemekte ekran yok; bu ara beynin dinlenme penceresi.")
        )
        p2 = yemek_bas + AKSAM_YEMEGI_DK + YEMEK_SONRASI_MOLA_DK
        rutin.append(
            _dilim(p2 - YEMEK_SONRASI_MOLA_DK, p2, "Yemek sonrası mola", "mola",
                   "Ağır yemekten hemen sonra derse oturma; 15 dakika yürü.")
        )
        pencereler.append(_pencere(p2, p2 + w2, "2. blok"))
        p3 = p2 + w2
        rutin.append(
            _dilim(p3, p3 + ARA_MOLA_DK, "Mola: hareket, su, ekran yok", "mola")
        )
        p3 += ARA_MOLA_DK
        pencereler.append(_pencere(p3, p3 + w3, "3. blok"))

    rutin.append(
        _dilim(kapanis_bas, kapanis_bas + KAPANIS_DK,
               "Günü kapat: plan kontrolü, çanta, yarının listesi", "hazirlik",
               "Yarının maddelerini işaretle; yetişmeyen bloğu yarına taşı.")
    )
    rutin.append(
        _dilim(kapanis_bas + KAPANIS_DK, yatis, "Ekranı kapat, yatışa hazırlık", "hazirlik",
               f"Yatmadan {UYKU_ONCESI_BOSLUK_DK} dakika önce çalışma bitmiş olmalı.")
    )
    rutin.append(
        _dilim(yatis, yatis, "Yatış — ışıklar kapalı", "uyku",
               "Ergen için 8 saat uyku hedef; telefonu odadan çıkar.")
    )
    return rutin, pencereler


def _cumartesi_cercevesi(
    uyanma: int, yatis: int, deneme_var: bool
) -> tuple[list[dict], list[dict]]:
    """Cumartesi: gerçek sınav saatinde deneme + analiz."""
    rutin: list[dict] = []
    pencereler: list[dict] = []
    rutin.append(
        _dilim(uyanma, uyanma + 45, "Uyanış + kahvaltı", "yemek",
               "Hafta sonu 1 saat fazla uyumak uyku borcunu kapatmaya yeter; daha fazlası düzeni bozar.")
    )
    isinma = uyanma + 45
    pencereler.append(_pencere(isinma, isinma + 55, "Isınma"))
    sinav = isinma + 60
    sinav_baslik = "Deneme sınavı (gerçek sınav saati)" if deneme_var else "Uzun soru seti (deneme formatında)"
    pencereler.append(_pencere(sinav, sinav + 180, sinav_baslik))
    if not deneme_var:
        rutin.append(
            _dilim(sinav, sinav + 180, "Deneme benzeri uzun set", "calisma",
                   "Bugün takvimde deneme yok; aynı saatte 180 dakikalık set çöz.")
        )
    ogle = sinav + 180
    rutin.append(
        _dilim(ogle, ogle + 60, "Öğle yemeği + dinlenme", "yemek",
               "Sınav sonrası 1 saat tam dinlenme; analize hemen başlama.")
    )
    analiz = ogle + 60
    pencereler.append(_pencere(analiz, analiz + 90, "Deneme analizi"))
    mola = analiz + 90
    rutin.append(_dilim(mola, mola + 30, "Mola: yürüyüş, açık hava", "mola"))
    telafi = mola + 30
    pencereler.append(_pencere(telafi, telafi + 75, "Telafi"))
    serbest = telafi + 75
    aksam = max(serbest + 90, yatis - 300)
    rutin.append(
        _dilim(serbest, aksam, "Serbest zaman: aile, spor, hobi", "serbest",
               "Haftada bir yarım gün dinlenme programın parçasıdır, kayıp değil.")
    )
    rutin.append(_dilim(aksam, aksam + 45, "Akşam yemeği", "yemek"))
    rutin.append(_dilim(aksam + 45, yatis - YATIS_HAZIRLIK_DK, "Serbest akşam", "serbest"))
    rutin.append(
        _dilim(yatis - YATIS_HAZIRLIK_DK, yatis, "Ekranı kapat, yatışa hazırlık", "hazirlik")
    )
    rutin.append(_dilim(yatis, yatis, "Yatış — ışıklar kapalı", "uyku"))
    return rutin, pencereler


def _pazar_cercevesi(uyanma: int, yatis: int) -> tuple[list[dict], list[dict]]:
    """Pazar: haftalık tekrar, hata defteri ve SD öz değerlendirme."""
    rutin: list[dict] = []
    pencereler: list[dict] = []
    rutin.append(
        _dilim(uyanma, uyanma + 45, "Uyanış + kahvaltı", "yemek",
               "Pazar da aynı saatte kalk: pazartesi sendromunun sebebi geç kalkmaktır.")
    )
    w1 = uyanma + 60
    pencereler.append(_pencere(w1, w1 + 90, "Haftalık tekrar"))
    mola1 = w1 + 90
    rutin.append(_dilim(mola1, mola1 + 30, "Mola: çay, hava, esneme", "mola"))
    ogle = mola1 + 30
    rutin.append(_dilim(ogle, ogle + 60, "Öğle yemeği", "yemek"))
    w2 = ogle + 60
    pencereler.append(_pencere(w2, w2 + 90, "Zayıf konu telafisi"))
    serbest = w2 + 90
    rutin.append(
        _dilim(serbest, serbest + 120, "Serbest zaman: açık hava, aile", "serbest",
               "Beynin öğrendiği bilgiyi dinlenme sırasında işler; bu blok atlanmaz.")
    )
    w3 = serbest + 120
    pencereler.append(_pencere(w3, w3 + 60, "Haftaya hazırlık"))
    sd = w3 + 60
    rutin.append(
        _dilim(sd, sd + 15, "Sosyal-duygusal öz değerlendirme (SD)", "gelisim",
               "Haftanın hedefi gerçekleşti mi? Stresini ne yükseltti? 3 satır yaz.")
    )
    aksam = max(sd + 45, yatis - 300)
    rutin.append(_dilim(sd + 15, aksam, "Serbest zaman", "serbest"))
    rutin.append(_dilim(aksam, aksam + 45, "Akşam yemeği", "yemek"))
    pencereler.append(_pencere(aksam + 45, aksam + 105, "Hafif tekrar"))
    rutin.append(
        _dilim(yatis - YATIS_HAZIRLIK_DK, yatis, "Ekranı kapat, yatışa hazırlık", "hazirlik")
    )
    rutin.append(_dilim(yatis, yatis, "Yatış — ışıklar kapalı", "uyku"))
    return rutin, pencereler


def gun_cercevesi(
    tarih: date, profil: Profil | None = None, deneme_var: bool = False
) -> dict:
    """Bir günün sabit çerçevesi: rutin dilimler ve çalışma pencereleri."""
    uyanma = _profil_saati(profil, "uyanma_saati", VARSAYILAN_UYANMA)
    yatis = _profil_saati(profil, "yatma_saati", VARSAYILAN_YATMA)
    if yatis <= uyanma + 600:
        yatis = uyanma + 16 * 60  # en az 8 saatlik uyanık dönem
    hafta_sonu = tarih.weekday() >= 5

    okul: dict | None = None
    donus_dk = 0
    if not hafta_sonu:
        okul_bas = _profil_saati(profil, "okul_baslangic", VARSAYILAN_OKUL_BASLANGIC)
        okul_bit = _profil_saati(profil, "okul_bitis", VARSAYILAN_OKUL_BITIS)
        if okul_bit <= okul_bas:
            okul_bas, okul_bit = _dk(VARSAYILAN_OKUL_BASLANGIC), _dk(VARSAYILAN_OKUL_BITIS)
        # Okula yetişmek için uyanışla okul başlangıcı arasında en az 45 dk kalmalı
        if okul_bas - uyanma < 45:
            okul_bas = uyanma + 45
        # Eve varış saati öğrenciden gelir; girilmediyse 35 dakikalık yol varsayılır
        donus_dk = _dk(getattr(profil, "okul_donus", "") or "")
        if donus_dk <= okul_bit:
            donus_dk = okul_bit + VARSAYILAN_DONUS_DK
        # Akşam en az bir blok + kapanış kalsın; çok geç dönüşte sınırla
        ust = yatis - (KAPANIS_DK + YATIS_HAZIRLIK_DK + 60)
        if donus_dk > ust:
            donus_dk = max(okul_bit + 15, ust)
        rutin, pencereler = _okul_cercevesi(
            uyanma, yatis, okul_bas, okul_bit, donus_dk
        )
        tip = "okul"
        okul = {
            "baslangic": _ss(okul_bas),
            "bitis": _ss(okul_bit),
            "donus": _ss(donus_dk),
        }
    elif tarih.weekday() == 5:
        rutin, pencereler = _cumartesi_cercevesi(uyanma + 105, yatis, deneme_var)
        tip = "deneme" if deneme_var else "hafta_sonu"
    else:
        rutin, pencereler = _pazar_cercevesi(uyanma + 135, yatis)
        tip = "hafta_sonu"

    kapasite = sum(p["kapasite_dk"] for p in pencereler)
    notlar: list[str] = []
    if tip == "okul":
        notlar.append(
            "Okul saati çalışma süresine sayılmaz; program okul dışındaki saatlere kuruldu."
        )
        if kapasite > OKUL_GUNU_AZAMI_DK:
            notlar.append(
                f"Okul gününde önerilen üst sınır {OKUL_GUNU_AZAMI_DK} dakika; "
                "daha uzun süre verimi düşürdüğü için pencereler buna göre sınırlandı."
            )
    if tip == "deneme":
        notlar.append("Deneme gerçek sınav saatiyle aynı saatte (10.15) çözülür.")
    if tip == "hafta_sonu" and tarih.weekday() == 6:
        notlar.append("Pazar öğleden sonra serbest; haftalık öz değerlendirme (SD) akşamüstü.")
    notlar.append(
        f"Çalışma blokları en fazla {BLOK_AZAMI_DK} dakika, aralarda {MOLA_DK} dakika mola."
    )

    return {
        "tarih": tarih.isoformat(),
        "gun_adi": GUN_ADLARI[tarih.weekday()],
        "tip": tip,
        "tip_etiketi": TIP_ETIKET[tip],
        "uyanma": _ss(uyanma),
        "yatis": _ss(yatis),
        "okul": okul,
        "okul_donus": _ss(donus_dk) if donus_dk else "",
        "rutin": rutin,
        "pencereler": pencereler,
        "kapasite_dk": kapasite,
        "azami_dk": OKUL_GUNU_AZAMI_DK if tip == "okul" else kapasite,
        "notlar": notlar,
    }


# ------------------------------------------------------------------ yerleştirme
def yerlesim(sureler: list[int], pencereler: list[dict], mola: int = MOLA_DK) -> list[int]:
    """Maddeleri pencerelere sırayla yerleştirir; her maddenin başlangıç dakikası.

    Pencere bitmeden sığmayan madde bir sonrakine geçer. Hiçbir pencereye
    sığmayan madde son pencerenin ardına eklenir (program kısalmaz).
    """
    if not pencereler:
        return [0 for _ in sureler]

    baslangiclar: list[int] = []
    indeks = 0
    for pencere in pencereler:
        imlec = _dk(pencere["baslangic"])
        bitis = _dk(pencere["bitis"])
        while indeks < len(sureler):
            sure = max(10, sureler[indeks])
            if imlec + sure <= bitis:
                baslangiclar.append(imlec)
                imlec += sure + mola
                indeks += 1
            else:
                break

    if indeks < len(sureler):
        son = _dk(pencereler[-1]["bitis"])
        for _ in range(len(sureler) - indeks):
            baslangiclar.append(son)
            son += max(10, sureler[indeks]) + mola
            indeks += 1
    return baslangiclar


def sigiyor_mu(sureler: list[int], pencereler: list[dict]) -> bool:
    """Tüm maddeler molalarıyla birlikte pencerelere sığıyor mu?

    ``yerlesim`` ile aynı yerleştirme kuralını izler; sığmayan madde kalırsa
    program gün sonundaki çalışma sınırını aşacağı için üretim buna göre
    küçültülür.
    """
    if not pencereler:
        return not sureler
    indeks = 0
    for pencere in pencereler:
        imlec = _dk(pencere["baslangic"])
        bitis = _dk(pencere["bitis"])
        while indeks < len(sureler):
            sure = max(10, sureler[indeks])
            if imlec + sure <= bitis:
                imlec += sure + MOLA_DK
                indeks += 1
            else:
                break
    return indeks >= len(sureler)


def pencere_bosluklari(
    sureler: list[int], pencereler: list[dict], mola: int = MOLA_DK
) -> list[tuple[int, int]]:
    """Her pencerenin sonunda kalan boşluk: ``(konum, boş dakika)``.

    ``konum``, boşluğa yazılacak ek maddenin süre listesindeki indeksidir;
    boşluk ise o penceredeki son maddeden ve molasından sonra pencere bitişine
    kadar kalan dakikadır. Yerleştirme ``yerlesim`` ile aynı kuralı izler.
    Pencerede hiç madde yoksa (tamamen boş blok) boşluk raporlanmaz; oradaki
    eksiklik gün akışında ayrıca işaretlenir.
    """
    bosluklar: list[tuple[int, int]] = []
    indeks = 0
    for pencere in pencereler:
        imlec = _dk(pencere["baslangic"])
        bitis = _dk(pencere["bitis"])
        yerlesen = 0
        while indeks < len(sureler):
            sure = max(10, sureler[indeks])
            if imlec + sure <= bitis:
                imlec += sure + mola
                indeks += 1
                yerlesen += 1
            else:
                break
        if yerlesen:
            bosluklar.append((indeks, max(0, bitis - imlec)))
    return bosluklar


def zamanlari_yerlestir(
    db: Session,
    profil: Profil,
    baslangic: date | None = None,
    bitis: date | None = None,
) -> int:
    """Aralıktaki plan maddelerine saat verir; değişen madde sayısını döndürür."""
    baslangic = baslangic or date.today()
    bitis = bitis or baslangic + timedelta(days=6)
    degisen = 0
    for sira in range((bitis - baslangic).days + 1):
        tarih = baslangic + timedelta(days=sira)
        maddeler = list(
            db.execute(
                select(PlanItem)
                .where(PlanItem.profil_id == profil.id, PlanItem.tarih == tarih)
                .order_by(PlanItem.sira, PlanItem.id)
            ).scalars()
        )
        if not maddeler:
            continue
        cerceve = gun_cercevesi(tarih, profil, any(m.tur == "deneme" for m in maddeler))
        baslangiclar = yerlesim([m.sure_dk or 30 for m in maddeler], cerceve["pencereler"])
        for madde, dakika in zip(maddeler, baslangiclar):
            saat = _ss(dakika)
            if madde.baslangic != saat:
                madde.baslangic = saat
                degisen += 1
    if degisen:
        db.commit()
    return degisen


def _madde_suresi(madde: PlanItem) -> int:
    return max(10, madde.sure_dk or 30)


def gun_akisi(
    cerceve: dict, maddeler: list[PlanItem], ders_renk: dict[str, str] | None = None
) -> list[dict]:
    """Rutin dilimlerle plan maddelerini saat sırasına göre birleştirir."""
    ders_renk = ders_renk or {}
    akis = [dict(dilim, kaynak="rutin") for dilim in cerceve["rutin"]]

    baslangiclar = yerlesim([_madde_suresi(m) for m in maddeler], cerceve["pencereler"])
    dolu: set[int] = set()
    for madde, dakika in zip(maddeler, baslangiclar):
        bas = _ss(dakika)
        bit = _ss(dakika + _madde_suresi(madde))
        for i, pencere in enumerate(cerceve["pencereler"]):
            if _dk(pencere["baslangic"]) <= dakika < _dk(pencere["bitis"]):
                dolu.add(i)
                break
        akis.append(
            {
                "baslangic": bas,
                "bitis": bit,
                "baslik": madde.baslik,
                "tur": madde.tur,
                "aciklama": "",
                "kaynak": "plan",
                "madde_id": madde.id,
                "ders_kod": madde.ders_kod,
                "renk": ders_renk.get(madde.ders_kod, "#ea580c"),
                "sure_dk": madde.sure_dk,
                "durum": madde.durum,
            }
        )

    # Hiç madde düşmeyen pencere boş görünmesin: tekrar ya da soru önerilir
    for i, pencere in enumerate(cerceve["pencereler"]):
        if i in dolu:
            continue
        akis.append(
            {
                "baslangic": pencere["baslangic"],
                "bitis": pencere["bitis"],
                "baslik": f"Boş blok: {pencere['baslik'].lower()} (tekrar veya soru)",
                "tur": "bos",
                "aciklama": "Bu blokta plan maddesi yok; hata defterinden tekrar yapabilirsin.",
                "kaynak": "rutin",
            }
        )

    akis.sort(key=lambda dilim: (_dk(dilim["baslangic"]), 0 if dilim["kaynak"] == "rutin" else 1))
    return akis


# --------------------------------------------------------------------- analiz
def beceri_dengesi(
    maddeler: list[PlanItem],
    konu_map: dict[int, Konu],
    ek: dict[str, int] | None = None,
) -> list[dict]:
    """Haftalık dakikaların Maarif beceri kodlarına dağılımı.

    ``ek`` ile plan maddesi olmayan rütin bloklar (ör. pazar SD öz
    değerlendirmesi) dengeye katılır.
    """
    toplam: dict[str, float] = {}
    for madde in maddeler:
        konu = konu_map.get(madde.konu_id) if madde.konu_id else None
        kodlar = [k for k in ((konu.beceri or "").split(",") if konu else []) if k]
        if not kodlar:
            toplam["-"] = toplam.get("-", 0.0) + (madde.sure_dk or 0)
            continue
        pay = (madde.sure_dk or 0) / len(kodlar)
        for kod in kodlar:
            toplam[kod] = toplam.get(kod, 0.0) + pay

    for kod, deger in (ek or {}).items():
        if deger:
            toplam[kod] = toplam.get(kod, 0.0) + deger

    tumu = sum(toplam.values()) or 1.0
    satirlar = [
        {
            "kod": kod,
            "ad": BECERI_ETIKET.get(kod, "Becerisiz / deneme"),
            "dk": round(deger),
            "pay": round(100 * deger / tumu),
        }
        for kod, deger in toplam.items()
    ]
    return sorted(satirlar, key=lambda s: -s["dk"])


def deneme_odagi(
    maddeler: list[PlanItem], konu_map: dict[int, Konu], yanlislar: dict[int, int]
) -> dict:
    """Denemede yanlış çıkan konulara ayrılan dakika payı."""
    toplam = sum(m.sure_dk or 0 for m in maddeler) or 0
    odak = [m for m in maddeler if m.konu_id and yanlislar.get(m.konu_id)]
    odak_dk = sum(m.sure_dk or 0 for m in odak)
    konular: dict[int, dict] = {}
    for madde in odak:
        konu = konu_map.get(madde.konu_id)
        if konu is None:
            continue
        kayit = konular.setdefault(
            konu.id, {"konu": konu.ad, "ders_kod": konu.ders_kod, "yanlis": yanlislar[konu.id], "dk": 0}
        )
        kayit["dk"] += madde.sure_dk or 0
    return {
        "pay": round(100 * odak_dk / toplam) if toplam else 0,
        "konu_sayisi": len(konular),
        "dakika": odak_dk,
        "konular": sorted(konular.values(), key=lambda k: (-k["yanlis"], -k["dk"]))[:3],
    }


def pdr_ilkeleri() -> list[dict]:
    """Programın dayandığı PDR (rehberlik) ilkeleri — arayüzde açıklanır."""
    return [
        {
            "baslik": "Uyku düzeni sabit",
            "metin": "Aynı saatte kalk, aynı saatte yat. Ergen için hedef 8 saat; "
                     "hafta sonu en fazla 1 saat fazla uyku.",
        },
        {
            "baslik": f"{BLOK_AZAMI_DK} dakika çalış, {MOLA_DK} dakika dinlen",
            "metin": "Kesintisiz uzun oturumlar dikkati düşürür. Molada telefon yerine "
                     "su, esneme, kısa yürüyüş.",
        },
        {
            "baslik": "Okuldan sonra geçiş molası",
            "metin": "Eve gelir gelmez masaya oturma; yemek ve 20 dakikalık dinlenmeden "
                     "sonra ilk bloka başla.",
        },
        {
            "baslik": "Öğünler atlanmaz",
            "metin": "Kahvaltı, öğle ve akşam yemeği programın parçası. Ağır yemekten "
                     "hemen sonra derse oturulmaz.",
        },
        {
            "baslik": f"Yatmadan {UYKU_ONCESI_BOSLUK_DK} dakika önce çalışma biter",
            "metin": "Uyarılmış beyin uykuya geçemez. Kapanışta plan kontrolü ve çanta "
                     "hazırlığı yapılır, ekran kapatılır.",
        },
        {
            "baslik": "Haftada bir yarım gün serbest",
            "metin": "Pazar öğleden sonrası dinlenmeye ayrılır; tükenmişlik programı "
                     "bozar, dinlenme programı korur.",
        },
        {
            "baslik": "Deneme gerçek koşulda",
            "metin": "Deneme, gerçek sınav saati ve süresiyle (cumartesi 10.15) çözülür; "
                     "analiz aynı gün yapılır.",
        },
        {
            "baslik": "Beceri temelli denge (Maarif Modeli)",
            "metin": "Konular KB, AB, SD ve OK becerileriyle etiketlenir; haftalık dağılım "
                     "izlenir, sosyal-duygusal beceri için ayrı blok ayrılır.",
        },
    ]
