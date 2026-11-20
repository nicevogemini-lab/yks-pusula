# -*- coding: utf-8 -*-
"""Müfredat tohumlama (seed).

Program ilk açıldığında ders ve konu tabloları bu modülden doldurulur.
İşlem idempotenttir: dersler yalnızca eksikse eklenir, konular ise veri
modülündeki listeyle eşitlenir (yeniden adlandır / ekle / çıkarılanı sil).
"""
from __future__ import annotations

from sqlalchemy import delete, inspect, select, text, update
from sqlalchemy.orm import Session

from .data import KONU_YENIDEN_ADLANDIRMA, TUM_DERSLER, tum_konular_listesi
from .models import Ayar, Calisma, DenemeKonu, Ders, Konu, KonuDurum, PlanItem

# Yöneticinin müfredattan kaldırdığı gömülü kayıtların kodları bu ayarlarda
# tutulur: eşitleme bir daha eklemez (konuları elle silmek boşa gitmesin).
SILINEN_KONU_AYARI = "mufredat_silinen_konular"
SILINEN_DERS_AYARI = "mufredat_silinen_dersler"


def silinen_kodlar(db: Session, tur: str) -> set[str]:
    """Yöneticinin kaldırdığı kodlar (``tur`` = "konu" ya da "ders")."""
    anahtar = SILINEN_KONU_AYARI if tur == "konu" else SILINEN_DERS_AYARI
    kayit = db.get(Ayar, anahtar)
    return {k for k in (kayit.deger or "").split(",") if k} if kayit else set()


def kod_silindi_olarak_isle(db: Session, tur: str, kod: str) -> None:
    """Gömülü kaydı silindiler listesine yazar; commit çağıranın işi."""
    anahtar = SILINEN_KONU_AYARI if tur == "konu" else SILINEN_DERS_AYARI
    kodlar = silinen_kodlar(db, tur)
    kodlar.add(kod)
    kayit = db.get(Ayar, anahtar)
    deger = ",".join(sorted(kodlar))
    if kayit is None:
        db.add(Ayar(anahtar=anahtar, deger=deger))
    else:
        kayit.deger = deger

# Var olan SQLite dosyasına sonradan eklenen sütunlar (tablo -> sütun tanımı)
YENI_KOLONLAR: dict[str, dict[str, str]] = {
    "profiller": {
        "uyanma_saati": "VARCHAR(5) DEFAULT '06:45'",
        "yatma_saati": "VARCHAR(5) DEFAULT '22:45'",
        "okul_baslangic": "VARCHAR(5) DEFAULT '08:20'",
        "okul_bitis": "VARCHAR(5) DEFAULT '15:20'",
        "okul_donus": "VARCHAR(5) DEFAULT ''",
    },
    "plan_maddeleri": {"baslangic": "VARCHAR(5) DEFAULT ''"},
    # Konu bazlı deneme girişi: doğru/yanlış/boş
    "deneme_konulari": {"dogru": "INTEGER DEFAULT 0", "bos": "INTEGER DEFAULT 0"},
    # Yöneticinin eklediği/düzenlediği müfredat satırları
    "dersler": {"ozel": "BOOLEAN NOT NULL DEFAULT FALSE"},
    "konular": {"ozel": "BOOLEAN NOT NULL DEFAULT FALSE"},
}


def sema_guncelle(db: Session) -> list[str]:
    """Mevcut veritabanına eksik sütunları ekler; eklenenleri döndürür.

    ``create_all`` var olan tabloları değiştirmediği için gün akışı saatleri
    gibi sonradan eklenen alanlar burada tamamlanır. Sütun listesi SQLAlchemy
    denetçisinden okunur; böylece SQLite ve PostgreSQL aynı kodla çalışır.
    """
    eklenen: list[str] = []
    denetci = inspect(db.get_bind())
    for tablo, kolonlar in YENI_KOLONLAR.items():
        if not denetci.has_table(tablo):
            continue  # tablo henüz yok: create_all oluşturacak
        mevcut = {kolon["name"] for kolon in denetci.get_columns(tablo)}
        for kolon, tanim in kolonlar.items():
            if kolon in mevcut:
                continue
            db.execute(text(f"ALTER TABLE {tablo} ADD COLUMN {kolon} {tanim}"))
            eklenen.append(f"{tablo}.{kolon}")
    if eklenen:
        db.commit()
    return eklenen


def _konu_bagimliliklarini_temizle(db: Session, konu_id: int) -> None:
    """Silinecek konuya bağlı kayıtları güvenli biçimde boşaltır."""
    db.execute(delete(DenemeKonu).where(DenemeKonu.konu_id == konu_id))
    db.execute(delete(KonuDurum).where(KonuDurum.konu_id == konu_id))
    db.execute(update(Calisma).where(Calisma.konu_id == konu_id).values(konu_id=None))
    db.execute(update(PlanItem).where(PlanItem.konu_id == konu_id).values(konu_id=None))


def mufredati_yukle(db: Session) -> dict[str, int]:
    """Ders ve konuları veritabanına ekler; eklenen sayıları döndürür."""
    mevcut_ders = {k for (k,) in db.execute(select(Ders.kod)).all()}
    silinen_dersler = silinen_kodlar(db, "ders")
    eklenen_ders = 0
    for kod, ad, sinav, alanlar, soru, renk, sira in TUM_DERSLER:
        if kod in mevcut_ders or kod in silinen_dersler:
            continue
        db.add(
            Ders(
                kod=kod,
                ad=ad,
                sinav=sinav,
                alanlar=alanlar,
                soru_sayisi=soru,
                renk=renk,
                sira=sira,
            )
        )
        eklenen_ders += 1
    db.commit()

    # Renk yalnızca görsel bir alandır; palet tema ile değiştiğinde mevcut
    # derslerin rengi de güncellenir (veri kaybı olmadan).
    renkler = {kod: renk for kod, _ad, _sinav, _alanlar, _soru, renk, _sira in TUM_DERSLER}
    for ders in db.execute(select(Ders)).scalars():
        yeni_renk = renkler.get(ders.kod)
        if ders.ozel:
            continue  # yöneticinin düzenlediği ders kendi rengini korur
        if yeni_renk and ders.renk != yeni_renk:
            ders.renk = yeni_renk
    db.commit()

    senkron = _konulari_senkronla(db)
    return {"ders": eklenen_ders, "konu": senkron["eklenen"]}


def _konulari_senkronla(db: Session) -> dict[str, int]:
    """Konu tablosunu veri modülündeki listeyle eşitler.

    Kitap listeleri güncellendiğinde eski kayıtların kimliği korunarak yeni
    adlara taşınır; eksik konular eklenir, listeden çıkanlar bağımlı
    kayıtları temizlenerek silinir.
    """
    hedef: dict[str, list[dict]] = {}
    for veri in tum_konular_listesi():
        hedef.setdefault(veri["ders_kod"], []).append(veri)

    eklenen = guncellenen = silinen = 0
    silinen_kodlar_kumesi = silinen_kodlar(db, "konu")
    # Yöneticinin eklediği/düzenlediği satırlar eşitlemenin dışında tutulur:
    # adı değişen, taşınan ya da kaldırılan özel kayıt geri gelmez.
    ozel_konular = [k for k in db.execute(select(Konu)).scalars() if k.ozel]
    mevcut_konular = [
        k for k in db.execute(select(Konu)).scalars() if not k.ozel
    ]

    for ders_kod, satirlar in hedef.items():
        hedef_adlar = {s["ad"] for s in satirlar}
        ders_konulari = [k for k in mevcut_konular if k.ders_kod == ders_kod]
        # Aynı addan birden çok kayıt varsa ilki (eski kimlik) esas alınır.
        ad_haritasi: dict[str, Konu] = {}
        for konu in ders_konulari:
            ad_haritasi.setdefault(konu.ad, konu)

        # 1) Yeni kitap adları: kayıt kimliği ve bağımlı veriler korunur.
        for eski_ad, yeni_ad in KONU_YENIDEN_ADLANDIRMA.get(ders_kod, {}).items():
            konu = ad_haritasi.get(eski_ad)
            if konu is None or eski_ad in hedef_adlar:
                continue
            if yeni_ad in hedef_adlar and yeni_ad not in ad_haritasi:
                konu.ad = yeni_ad
                ad_haritasi.pop(eski_ad, None)
                ad_haritasi[yeni_ad] = konu
                guncellenen += 1

        # 2) Kodlar sıra numarasıyla yeniden dağıtıldığı için önce geçici kod.
        #    Kodlar zaten yerindeyse bu adım atlanır: bulut veritabanında her
        #    açılışta yüzlerce gereksiz UPDATE gönderilmez.
        kod_degisiyor = any(
            (konu := ad_haritasi.get(veri["ad"])) is not None and konu.kod != veri["kod"]
            for veri in satirlar
        )
        if kod_degisiyor:
            for konu in ders_konulari:
                konu.kod = f"~{konu.id}"
            db.flush()

        # 3) Hedef listeyi yaz: eşleşen güncellenir, eşleşmeyen eklenir.
        kullanilan: set[int] = set()
        for veri in satirlar:
            if veri["kod"] in silinen_kodlar_kumesi:
                continue  # yönetici bu konuyu müfredattan kaldırdı
            konu = ad_haritasi.get(veri["ad"])
            if konu is None:
                # Kod yöneticiye ait bir satırda duruyorsa ikinci kayıt açma
                if veri["kod"] in silinen_kodlar_kumesi or db.execute(
                    select(Konu.id).where(Konu.kod == veri["kod"])
                ).first() is not None:
                    continue
                db.add(Konu(**veri))
                eklenen += 1
                continue
            kullanilan.add(konu.id)
            konu.kod = veri["kod"]
            konu.sinif = veri["sinif"]
            konu.agirlik = veri["agirlik"]
            konu.sure_dk = veri["sure_dk"]
            konu.beceri = veri["beceri"]
            konu.onkosul = veri["onkosul"]
            konu.sira = veri["sira"]
            guncellenen += 1
        db.flush()

        # 4) Listede karşılığı kalmayan (artık/çift kayıt) konular kaldırılır.
        for konu in ders_konulari:
            if konu.id in kullanilan:
                continue
            _konu_bagimliliklarini_temizle(db, konu.id)
            db.delete(konu)
            silinen += 1

    db.commit()
    return {"eklenen": eklenen, "guncellenen": guncellenen, "silinen": silinen, "ozel": len(ozel_konular)}
