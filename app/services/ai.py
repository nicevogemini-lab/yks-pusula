# -*- coding: utf-8 -*-
"""Yapay zekâ koç servisi.

İki katmanlı çalışır:

* **Gemini** anahtarı varsa (ortam değişkeni veya panelden girilen) gerçek
  model çağrılır. Sistem istemi; öğrencinin **alanı**, **sınıfı**, Maarif
  Modeli beceri çerçevesi ve 2028 beceri/bağlam temelli soru modeli bilgisiyle
  kurulur.
* Anahtar yoksa **yerel koç** devreye girer: veritabanındaki ilerleme,
  deneme netleri ve öncelikli konulardan somut bir çalışma önerisi üretir.
  Böylece program internetsiz de anlamlı çalışır.
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import date

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..data import alan_ders_kodlari
from ..models import Ayar, Deneme, DenemeSonuc, Konu, KonuDurum, Profil
from .analiz import en_cok_kazanc
from .hedef import hedef_ozeti
from .plan import oncelikli_konular

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
VARSAYILAN_MODEL = "gemini-3.5-flash-lite"
# Ücretsiz kotada ara sıra görülen geçici hatalar: bir kez yeniden denenir
GECICI_KODLAR = (429, 500, 502, 503, 504)
# 400 yanıtında geçen, aslında geçici olan API mesajları
GECICI_IFADELER = (
    "api key not valid",
    "resource exhausted",
    "overloaded",
    "try again",
    "internal error",
)


def _hata_notu(hata: Exception) -> str:
    """Öğrenciye gösterilecek kısa, anlaşılır hata notu."""
    if isinstance(hata, httpx.HTTPStatusError):
        kod = hata.response.status_code
        aciklama = {
            400: "istek reddedildi",
            401: "anahtar geçersiz",
            403: "anahtarın izni yok",
            404: "model bulunamadı",
            429: "kota/istek sınırı",
            500: "Google iç hatası",
            503: "Google geçici yoğunluk",
        }.get(kod, "hata")
        # API'nin kendi açıklaması varsa ekle: teşhis için kritik
        ayrinti = ""
        try:
            mesaj = (hata.response.json().get("error") or {}).get("message", "")
            ayrinti = " ".join(str(mesaj).split())[:140]
        except Exception:  # yanıt JSON değilse ayrıntı eklenmez
            ayrinti = ""
        not_ = f"Google {kod} · {aciklama}"
        return f"{not_} ({ayrinti})" if ayrinti else not_
    if isinstance(hata, httpx.HTTPError):
        return f"internet/ağ hatası ({type(hata).__name__})"
    return str(hata) or type(hata).__name__


def _ayar_oku(db: Session, anahtar: str) -> str:
    satir = db.get(Ayar, anahtar)
    return (satir.deger or "").strip() if satir else ""


def anahtar_getir(db: Session) -> tuple[str, str]:
    """(api_anahtari, model) döndürür. Panelde girilen değer .env'i geçersiz kılar."""
    anahtar = _ayar_oku(db, "gemini_api_key") or os.getenv("GEMINI_API_KEY", "").strip()
    model = _ayar_oku(db, "gemini_model") or os.getenv("GEMINI_MODEL", "").strip() or VARSAYILAN_MODEL
    return anahtar, model


def ai_aktif(db: Session) -> bool:
    return bool(anahtar_getir(db)[0])


# --------------------------------------------------------------------------
# Bağlam: modelin öğrenciyi tanıması için sayısal özet
# --------------------------------------------------------------------------
def ogrenci_baglami(db: Session, profil: Profil) -> dict:
    # Panel ile aynı kapsam: yalnızca öğrencinin alanına ait dersler
    kodlar = alan_ders_kodlari(profil.alan)
    konular = list(db.execute(select(Konu).where(Konu.ders_kod.in_(kodlar))).scalars())
    konu_idler = {k.id for k in konular}
    durumlar = [
        d
        for d in db.execute(select(KonuDurum).where(KonuDurum.profil_id == profil.id)).scalars()
        if d.konu_id in konu_idler
    ]
    tamam = sum(1 for d in durumlar if d.durum == "tamam")
    tekrar = sum(1 for d in durumlar if d.durum == "tekrar")
    calisiliyor = sum(1 for d in durumlar if d.durum == "calisiliyor")

    oncelik = oncelikli_konular(db, profil, limit=6)
    oncelik_listesi = [
        {"konu": k.ad, "ders": k.ders_kod, "sinif": k.sinif, "puan": round(p, 1)}
        for k, p in oncelik
    ]

    son_denemeler = list(
        db.execute(
            select(Deneme)
            .where(Deneme.profil_id == profil.id)
            .order_by(Deneme.tarih.desc())
            .limit(3)
        ).scalars()
    )
    deneme_ozet = []
    for d in son_denemeler:
        netler = list(
            db.execute(select(DenemeSonuc).where(DenemeSonuc.deneme_id == d.id)).scalars()
        )
        deneme_ozet.append(
            {
                "tur": d.tur,
                "tarih": d.tarih.isoformat(),
                "netler": {n.ders_kod: n.net for n in netler},
                "toplam_net": round(sum(n.net for n in netler), 2),
            }
        )

    return {
        "ad": profil.ad,
        "alan": profil.alan_etiketi,
        "sinif": profil.sinif_etiketi,
        "kalan_gun": (profil.sinav_tarihi - date.today()).days,
        "gunluk_hedef_dk": profil.gunluk_hedef_dk,
        "hedef_siralama": profil.hedef_siralama,
        "konu_toplam": len(konular),
        "tamam": tamam,
        "tekrar": tekrar,
        "calisiliyor": calisiliyor,
        "oncelikli_konular": oncelik_listesi,
        "agirlikli_aciklar": en_cok_kazanc(db, profil, limit=6),
        "son_denemeler": deneme_ozet,
        "hedef": hedef_ozeti(db, profil),
    }


def sistem_istemi(baglam: dict) -> str:
    """Moda ve müfredata uygun sistem istemi üretir."""
    return f"""Sen Türkiye'de YKS'ye hazırlanan bir lise öğrencisinin kişisel eğitim koçusun.
Adı: {baglam['ad']}. Alanı: {baglam['alan']}. Sınıfı: {baglam['sinif']}.
Sınava kalan gün: {baglam['kalan_gun']}. Günlük çalışma hedefi: {baglam['gunluk_hedef_dk']} dakika.
Hedef sıralama: {baglam['hedef']['hedef_siralama']:,}{' (varsayılan, öğrenci belirtmedi)' if baglam['hedef']['varsayilan'] else ''}.
Bu hedef için gereken yaklaşık netler: TYT {baglam['hedef']['tyt_hedef_net']} net, AYT {baglam['hedef']['ayt_hedef_net']} net.
Şu anki hedefe göre en büyük açıklar: {baglam['hedef']['en_buyuk_aciklar']}.

Müfredat çerçevesi: Millî Eğitim Bakanlığı **Türkiye Yüzyılı Maarif Modeli**.
Bu model; yetkin ve erdemli insan profili, erdem-değer-eylem çerçevesi ve
beceri temelli öğrenmeyi esas alır. Beceri boyutları: kavramsal beceriler,
alan becerileri, sosyal-duygusal beceriler ve okuryazarlık.
Önemli: 2028 YKS'den itibaren sorular **beceri ve bağlam temelli** olacak;
ezber değil, bilgiyi yeni durumlara uygulama ölçülecek. Cevaplarında bunu gözet.

Öğrencinin durumu:
- Toplam konu: {baglam['konu_toplam']}, tamamlanan: {baglam['tamam']}, tekrar gereken: {baglam['tekrar']}, çalışılıyor: {baglam['calisiliyor']}
- Öncelikli konular: {baglam['oncelikli_konular']}
- Ağırlıklı açıklar (beklenen soru × başarısızlık): {baglam['agirlikli_aciklar']}
- Son denemeler: {baglam['son_denemeler']}

Kurallar:
1. Türkçe, sıcak ama abartısız bir dille, kısa ve net yaz. Öğrenciye "sen" diye hitap et.
2. Somut ol: konu adı, süre, soru sayısı, gün ver. Genel tavsiye verme.
3. Cevabını en fazla 3 başlıkta topla ve sonunda **"Bugün yapacağın 3 şey"** listesi ver.
4. Ölçme önerisi ekle: bu konuyu nasıl test edeceğini (soru tipi, süre) söyle.
5. Tıbbi/psikolojik teşhis koyma; ağır kaygı belirtisinde rehber öğretmene yönlendir.
6. Uydurma kaynak, kitap veya istatistik verme. Emin olmadığında belirt.
7. Puan/sıralama tahmini yaparken "tahmini" olduğunu söyle.
8. Çalışma programını hedef sıralamadan türetilen ders netlerine göre kur: en büyük açığı olan derse
   önce ve daha çok yer ver; açık küçük derslerde sadece tekrar/bakım öner. Haftalık net artış hızını
   söyle ve gerçekçi ol.
9. Konu sıralamasında "ağırlıklı açık" listesini kullan: konunun YKS'de beklenen soru sayısı ile
   denemelerdeki doğru/yanlış oranını birlikte değerlendir. Az soru gelen ve zaten iyi olduğu konuya
   geniş yer ayırma; beklenen soru sayısı yüksek ve başarısı düşük konuya önce yer ver.
   Günlük/haftalık/aylık program istenirse üçünü ayrı ayrı ve dakika cinsinden yaz.
"""


# --------------------------------------------------------------------------
# Gemini çağrısı
# --------------------------------------------------------------------------
def _gemini_gonder(anahtar: str, model: str, govde: dict, *, json_modu: bool) -> httpx.Response:
    """İsteği atar; geçici hatalarda (429/5xx, anlık anahtar reddi) yeniden dener.

    Google bazen geçerli anahtar için de kısa süreliğine ``API key not valid``
    döndürüyor; bu yüzden 400 yanıtının metni de geçicilik için okunur.
    """
    yanit: httpx.Response | None = None
    for deneme in range(4):
        yanit = httpx.post(
            GEMINI_URL.format(model=model),
            params={"key": anahtar},
            json=govde,
            timeout=90.0 if json_modu else 40.0,
        )
        if not _gecici_yanit(yanit) or deneme == 3:
            break
        # anahtar reddi ve yoğunluk kısa süreli: artan bekleme ile yeniden dene
        bekle = 3.0 * (deneme + 1)
        try:
            bekle = max(bekle, float(yanit.headers.get("retry-after", 0)))
        except (TypeError, ValueError):
            pass
        time.sleep(min(bekle, 20.0))
    assert yanit is not None
    return yanit


def _gecici_yanit(yanit: httpx.Response) -> bool:
    """Yanıt geçici bir sorundan mı kaynaklı (tekrar denemeye değer mi)?"""
    if yanit.status_code in GECICI_KODLAR:
        return True
    if yanit.status_code == 400:
        govde = yanit.text.lower()
        return any(ifade in govde for ifade in GECICI_IFADELER)
    return False


def _gemini_cagir(
    anahtar: str,
    model: str,
    sistem: str,
    mesajlar: list[dict],
    *,
    json_modu: bool = False,
) -> str:
    """Gemini'ye istek atar ve düz metin döndürür.

    ``json_modu`` açıkken model ``application/json`` üretmeye zorlanır, düşünme
    jetonu kapatılır (JSON'u yiyip yanıtı boş bırakmasın) ve yanıt için daha
    büyük jeton bütçesi ayrılır.
    """
    contents = []
    for m in mesajlar:
        rol = "user" if m.get("rol") == "kullanici" else "model"
        contents.append({"role": rol, "parts": [{"text": m.get("icerik", "")}]})

    uretim: dict = {
        "temperature": 0.3 if json_modu else 0.6,
        "maxOutputTokens": 8192 if json_modu else 1400,
    }
    if json_modu:
        uretim["responseMimeType"] = "application/json"
        uretim["thinkingConfig"] = {"thinkingBudget": 0}

    govde = {
        "system_instruction": {"parts": [{"text": sistem}]},
        "contents": contents,
        "generationConfig": uretim,
    }
    yanit = _gemini_gonder(anahtar, model, govde, json_modu=json_modu)
    if yanit.status_code == 400 and "thinkingConfig" in uretim:
        # Model düşünme bütçesini tanımıyor: alanı çıkarıp tekrar dene
        uretim.pop("thinkingConfig", None)
        yanit = _gemini_gonder(anahtar, model, govde, json_modu=json_modu)
    yanit.raise_for_status()
    veri = yanit.json()
    adaylar = veri.get("candidates") or []
    if not adaylar:
        raise RuntimeError("Model yanıt üretmedi (aday boş).")
    aday = adaylar[0]
    parcalar = aday.get("content", {}).get("parts", [])
    metin = "".join(p.get("text", "") for p in parcalar).strip()
    if not metin:
        bitis = aday.get("finishReason") or "bilinmiyor"
        raise RuntimeError(f"Model boş yanıt döndürdü (bitiş: {bitis}).")
    return metin


# --------------------------------------------------------------------------
# Serbest metin üretimi (değerlendirme gibi tek seferlik işler)
# --------------------------------------------------------------------------
def model_cagir(db: Session, sistem: str, mesaj: str) -> dict:
    """Anahtar varsa Gemini'den serbest metin üretir.

    Dönen sözlük ``{ok, metin, kaynak, model}`` ya da hata durumunda
    ``{ok: False, sebep, model}`` alanlarını taşır; çağıran taraf yerel
    metne düşebilsin diye istisna fırlatmaz.
    """
    anahtar, model = anahtar_getir(db)
    if not anahtar:
        return {"ok": False, "sebep": "anahtar yok", "model": model}
    try:
        metin = _gemini_cagir(
            anahtar, model, sistem, [{"rol": "kullanici", "icerik": mesaj}]
        )
    except (httpx.HTTPError, RuntimeError) as hata:
        return {"ok": False, "sebep": _hata_notu(hata), "model": model}
    return {"ok": True, "metin": metin, "model": model, "kaynak": "gemini"}


# --------------------------------------------------------------------------
# Yapılandırılmış (JSON) yanıt: plan analizi gibi sayısal kararlar
# --------------------------------------------------------------------------
def json_cagir(db: Session, sistem: str, mesaj: str) -> dict:
    """Modelden JSON nesnesi ister.

    Dönen sözlük ``{ok, veri, kaynak, model}`` ya da hata durumunda
    ``{ok: False, sebep, model}`` alanlarını taşır. Çağıran taraf kendi
    doğrulamasını yapar; burada yalnızca geçerli bir JSON nesnesi olması
    garanti edilir. İstisna fırlatılmaz.
    """
    anahtar, model = anahtar_getir(db)
    if not anahtar:
        return {"ok": False, "sebep": "anahtar yok", "model": model}
    try:
        metin = _gemini_cagir(
            anahtar,
            model,
            sistem,
            [{"rol": "kullanici", "icerik": mesaj}],
            json_modu=True,
        )
    except (httpx.HTTPError, RuntimeError) as hata:
        return {"ok": False, "sebep": _hata_notu(hata), "model": model}
    try:
        veri = json.loads(metin)
    except json.JSONDecodeError:
        return {"ok": False, "sebep": "Model geçerli JSON üretmedi", "model": model}
    if not isinstance(veri, dict):
        return {"ok": False, "sebep": "Model JSON nesnesi üretmedi", "model": model}
    return {"ok": True, "veri": veri, "model": model, "kaynak": "gemini"}


# --------------------------------------------------------------------------
# Bağlantı testi (anahtar doğrulama)
# --------------------------------------------------------------------------
def baglanti_test(anahtar: str, model: str) -> dict:
    """Anahtarın Gemini'ye bağlanabildiğini küçük bir istekle doğrular.

    Anahtarı kaydetmeden önce denenebilmesi için ayrı tutuldu; dönen sözlük
    ``{ok, kod, model, mesaj}`` alanlarını taşır ve arayüzde olduğu gibi
    gösterilir.
    """
    try:
        metin = _gemini_cagir(
            anahtar,
            model,
            "Yalnızca istenen kısa yanıtı ver.",
            [{"rol": "kullanici", "icerik": "Sadece OK yaz."}],
        )
    except httpx.HTTPStatusError as hata:
        kod = hata.response.status_code
        govde = (hata.response.text or "")[:500]
        if "API_KEY_INVALID" in govde or "API key not valid" in govde:
            mesaj = "Anahtar geçersiz: Google bu anahtarı tanımıyor (API_KEY_INVALID). Anahtarı kopyalarken eksik karakter olmadığından emin ol."
        elif kod == 400:
            mesaj = "İstek reddedildi (400). Anahtarı ve model adını kontrol et."
        elif kod == 403:
            mesaj = "Bu anahtarın izni yok (403). Google AI Studio'da Generative Language API'nin açık olduğundan emin ol."
        elif kod == 404:
            mesaj = f"“{model}” modeli bulunamadı (404). Model adını kontrol et (ör. gemini-3.5-flash-lite)."
        elif kod == 429:
            mesaj = "Kota aşıldı (429). Birkaç dakika sonra tekrar dene veya ücretsiz kota durumunu kontrol et."
        else:
            mesaj = f"Google hata döndürdü (HTTP {kod})."
        return {"ok": False, "kod": kod, "model": model, "mesaj": mesaj}
    except httpx.HTTPError as hata:
        return {
            "ok": False,
            "kod": 0,
            "model": model,
            "mesaj": f"İnternete bağlanılamadı ({type(hata).__name__}). Anahtar kayıtlı kalır, bağlantı gelince denenir.",
        }
    except RuntimeError as hata:
        return {"ok": False, "kod": 0, "model": model, "mesaj": f"Model yanıtı okunamadı: {hata}"}
    return {
        "ok": True,
        "kod": 200,
        "model": model,
        "mesaj": f"Bağlantı başarılı — {model} yanıt veriyor.",
        "ornek": metin[:60],
    }


# --------------------------------------------------------------------------
# Yerel koç (anahtar yokken)
# --------------------------------------------------------------------------
def yerel_kocluk(db: Session, profil: Profil, mesaj: str) -> str:
    baglam = ogrenci_baglami(db, profil)
    oncelik = baglam["oncelikli_konular"][:3]
    satirlar = [
        f"**{profil.ad}** · {profil.alan_etiketi} · {profil.sinif_etiketi} · "
        f"sınava {baglam['kalan_gun']} gün",
        "",
        f"Sorunu aldım: “{mesaj.strip()[:160]}”",
        "",
        "### Durum özeti",
        f"- {baglam['konu_toplam']} konudan {baglam['tamam']} tanesi tamamlanmış, "
        f"{baglam['tekrar']} konu tekrar bekliyor.",
        f"- Günlük hedefin {profil.gunluk_hedef_dk} dakika.",
    ]
    if baglam["son_denemeler"]:
        son = baglam["son_denemeler"][0]
        satirlar.append(f"- Son deneme ({son['tur']}, {son['tarih']}): {son['toplam_net']} net.")
    else:
        satirlar.append("- Henüz deneme kaydı yok. İlk denemeyi girdiğinde analiz başlar.")

    # Hedef sıralama -> gereken netler (soru "başarı sıralaması nedir" ise asıl cevap burası)
    hedef = baglam["hedef"]
    satirlar += [
        "",
        "### Hedef sıralama ve gereken netler",
        f"- Hedef: **{hedef['hedef_siralama']:,}** sıralama"
        + (" (henüz girilmedi; varsayılan alındı)" if hedef["varsayilan"] else ""),
        f"- Bu sıralama için gereken yaklaşık netler: **TYT {hedef['tyt_hedef_net']}** · **AYT {hedef['ayt_hedef_net']}**",
        f"- Şu anki en iyin: TYT {hedef['tyt_mevcut_net']} · AYT {hedef['ayt_mevcut_net']} "
        f"(hedefin %{hedef['tamamlanma']} tamam)",
        f"- Kapatılacak net: TYT {hedef['tyt_acik']} · AYT {hedef['ayt_acik']}; "
        f"haftada ortalama {hedef['haftalik_gereken_net']} net hızı gerekiyor.",
    ]
    if hedef["en_buyuk_aciklar"]:
        satirlar += ["", "### Hedefe göre en büyük açıklar"]
        for i, acik in enumerate(hedef["en_buyuk_aciklar"][:4], start=1):
            satirlar.append(
                f"{i}. **{acik['ders']}**: hedef {acik['hedef']} net, en iyin {acik['mevcut']} net "
                f"→ {acik['acik']} net açık"
            )

    if oncelik:
        satirlar += ["", "### Şimdi odaklanman gereken konular"]
        for i, k in enumerate(oncelik, start=1):
            satirlar.append(f"{i}. **{k['konu']}** ({k['ders']}, {k['sinif']}. sınıf) — ağırlık puanı {k['puan']}")
    else:
        satirlar += ["", "### Şimdi odaklanman gereken konular", "Tüm konular tamam görünüyor; deneme analizine geç."]

    ilk_hedef = hedef["en_buyuk_aciklar"][0]["ders"] if hedef["en_buyuk_aciklar"] else None
    satirlar += [
        "",
        "### Bugün yapacağın 3 şey",
        f"1. {(ilk_hedef + ' dersinde') if ilk_hedef else (oncelik[0]['konu'] if oncelik else 'Tekrar listendeki ilk konu')}"
        f" en büyük açığın var: 40 dakika konu + 15 soru.",
        "2. Çözemediğin her soru için tek satır hata notu yaz (neden yanlış yaptım?).",
        "3. Günü 20 dakikalık aralıklı tekrarla kapat: dün ve geçen hafta çalıştığın iki konuyu gözden geçir.",
        "",
        "_Not: Yapay zekâ anahtarı eklenmediği için bu öneri programın yerel koç motorundan geldi. "
        "Ayarlardan Gemini anahtarı girerek kişiselleştirilmiş sohbeti açabilirsin._",
    ]
    return "\n".join(satirlar)


def koc_yanitla(db: Session, profil: Profil, mesaj: str, gecmis: list[dict]) -> dict:
    """Koç yanıtı üretir. Dönen sözlük: {metin, kaynak}."""
    anahtar, model = anahtar_getir(db)
    if not anahtar:
        return {"metin": yerel_kocluk(db, profil, mesaj), "kaynak": "yerel"}

    baglam = ogrenci_baglami(db, profil)
    mesajlar = (gecmis or [])[-8:] + [{"rol": "kullanici", "icerik": mesaj}]
    try:
        metin = _gemini_cagir(anahtar, model, sistem_istemi(baglam), mesajlar)
        return {"metin": metin, "kaynak": "gemini"}
    except Exception as hata:  # ağ/anahtar hatasında program çalışmaya devam eder
        yerel = yerel_kocluk(db, profil, mesaj)
        return {
            "metin": f"> Yapay zekâya ulaşılamadı: {_hata_notu(hata)}. Yerel koç devrede.\n\n{yerel}",
            "kaynak": "yerel",
        }


SORU_SISTEMI = """Sen YKS'ye hazırlık için Türkiye Yüzyılı Maarif Modeli temelli ölçme-değerlendirme uzmanısın.
2028 YKS soru anlayışına uygun yazarsın: ezber tanım değil; günlük hayat, deney,
veri yorumu ve akıl yürütme içeren bağlam soruları.

ÖNEMLİ - ortam sadece metindir: Sorular düz metin olarak gösterilir, şekil/görsel
basılmaz. Bu yüzden:
- "şekildeki", "yukarıdaki grafik", "aşağıdaki tablo", "görselde" gibi ifadeler KULLANMA.
- Tablo ya da grafik gerekiyorsa veriyi sorunun içine yaz: tablo için "veri" alanına
  düz metin tablo koy (satırları "|" ile ayır, ilk satır başlık olsun); grafik
  gerekliyse eksen değerlerini/veri noktalarını metinle ver.
- Soru, sadece metni okuyan bir öğrencinin tam olarak çözebileceği kadar eksiksiz olsun.

Matematik yazımı: düz metin kullan. Üs için ^ işareti (2^10, x^-3, 5^2), karekök için
kök( ) yaz. LaTeX ($, \\frac, ^{}), Markdown veya HTML kullanma.

Zorunlu çıktı biçimi: YALNIZCA geçerli bir JSON dizisi döndür. Açıklama, başlık,
selamlama, markdown veya kod bloğu ekleme. Dizi her zaman şu şemada olsun:
[{{"soru": "...", "veri": "", "secenekler": {{"A": "...", "B": "...", "C": "...", "D": "...", "E": "..."}},
  "dogru": "A", "cozum": "...", "beceri": "KB", "kazanim": "..."}}]

- "veri" yalnızca tablo/grafik verisi gerekiyorsa doldurulur; gerekmiyorsa boş metin ("") olur.
- "dogru" yalnızca tek harf (A-E) olur ve seçeneklerden biriyle eşleşir.
- "beceri" şu dört koddan biri: KB (kavramsal), AB (alan), SD (sosyal-duygusal), OK (okuryazarlık).
- Her soru 5 seçenekli ve tek doğru cevaplıdır. "cozum" adım adım ve en fazla 3 cümle.
- Sayılan sorular birbirinden farklı olsun; aynı soruyu tekrar yazma."""

SECENEK_HARFLERI = ("A", "B", "C", "D", "E")
BECERI_KODLARI = ("KB", "AB", "SD", "OK")
# Tek istekte istenen en fazla soru: uzun yanıtlar jeton sınırında kesilmesin
SORU_PARTI = 5
SORU_AZAMI = 15
# Partiler arası kısa bekleme: dakika başına istek sınırına takılmamak için
PARTI_ARASI_BEKLEME = 3.0
# Geçici hatadan sonraki soluklanmalar (saniye)
BEKLEME_ORTA = 12.0
BEKLEME_UZUN = 30.0
# Seçili model yoğunluk/kota hatası verirse sırayla denenen yedekler
YEDEK_MODELLER = ("gemini-3.1-flash-lite", "gemini-2.5-flash-lite")
# Tek soru üretimi isteği için üst süre (saniye): 15 soru ~3 parti
SORU_SURE_SINIRI = 240.0


def _gecici_mi(hata: str) -> bool:
    """Hata geçici mi (yoğunluk, kota, ağ)? Yedek model denemesi buna bağlı."""
    if not hata:
        return False
    return any(f"Google {kod}" in hata for kod in GECICI_KODLAR) or "ağ hatası" in hata


def _tekrar_dene_mi(hata: str) -> bool:
    """Kullanıcıya 'biraz sonra tekrar dene' ipucu verilmeli mi?"""
    return _gecici_mi(hata) or any(ifade in hata.lower() for ifade in GECICI_IFADELER)


def _soru_anahtari(soru: dict) -> str:
    """Soruyu karşılaştırmak için sadeleştirilmiş kök metin (tekrarları ayıklar)."""
    metin = re.sub(r"\s+", " ", str(soru.get("soru") or "").lower()).strip()
    return metin[:120]


def _soru_istemi(konu_adi: str, adet: int, zorluk: str, baglam: dict) -> str:
    return f"""Öğrenci: {baglam['alan']} alanı, {baglam['sinif']}.
Konu: {konu_adi}. Zorluk: {zorluk}. Bu yanıtta istenen soru sayısı: {adet}.
Konu adı yazım hatası içerse bile bu sınıf düzeyine en yakın müfredat kazanımını seç.
Sorular metin tabanlı olsun; şekil, görsel veya fotoğraf referansı kullanma.
Tablo/grafik verisi gerekiyorsa "veri" alanına düz metin olarak yaz.
Yanıtı yalnızca JSON dizisi olarak ver; dizinin dışına hiçbir şey yazma."""


def _kesik_json_onar(parca: str, kapanis: str) -> list | None:
    """Kesilmiş (maxOutputTokens) JSON'u son tamamlanmış nesneden kapatır."""
    for yer in range(len(parca) - 1, 0, -1):
        if parca[yer] != "}":
            continue
        aday = parca[: yer + 1]
        if not aday.lstrip().startswith("[") and kapanis == "]":
            aday = "[" + aday
        try:
            veri = json.loads(aday + kapanis)
        except json.JSONDecodeError:
            continue
        if isinstance(veri, list) and veri:
            return veri
    return None


def _liste_yap(veri) -> list:
    """Köşeli parantez yerine nesne dönerse listeye indirger."""
    if isinstance(veri, list):
        return veri
    if isinstance(veri, dict):
        for anahtar in ("sorular", "questions", "items", "data", "sonuclar"):
            if isinstance(veri.get(anahtar), list):
                return veri[anahtar]
        if "soru" in veri or "question" in veri:
            return [veri]
    return []


def _sorulari_coz(ham: str) -> list:
    """Model çıktısından soru listesini çıkarır.

    Kod bloğu, baş/son açıklama, nesne sarmalı ve kesilmiş yanıt durumlarını
    tolere eder; tamamen bozuksa boş liste döner.
    """
    metin = re.sub(r"```(?:json)?", "", ham or "").replace("```", "").strip()
    if not metin:
        return []

    adaylar = []
    try:
        adaylar.append(json.loads(metin))
    except json.JSONDecodeError:
        pass

    for acilis, kapanis in (("[", "]"), ("{", "}")):
        yer = metin.find(acilis)
        if yer < 0:
            continue
        parca = metin[yer:]
        try:
            veri, _ = json.JSONDecoder().raw_decode(parca)
            adaylar.append(veri)
        except json.JSONDecodeError:
            onarilmis = _kesik_json_onar(parca, kapanis)
            if onarilmis is not None:
                adaylar.append(onarilmis)

    for aday in adaylar:
        liste = _liste_yap(aday)
        if liste:
            return liste
    return []


def _sorulari_duzenle(ham_liste: list) -> list[dict]:
    """Alan adlarını ve tipleri normalize eder; eksik/geçersiz soruları eler."""
    sorular: list[dict] = []
    for ham_soru in ham_liste or []:
        if not isinstance(ham_soru, dict):
            continue
        soru = str(ham_soru.get("soru") or ham_soru.get("question") or "").strip()
        secenekler = ham_soru.get("secenekler") or ham_soru.get("options") or {}
        if isinstance(secenekler, list):
            secenekler = dict(zip(SECENEK_HARFLERI, secenekler))
        if not isinstance(secenekler, dict):
            secenekler = {}

        temiz_secenekler: dict[str, str] = {}
        for harf, metin in secenekler.items():
            kod = str(harf).strip().upper()[:1]
            deger = str(metin).strip()
            if kod in SECENEK_HARFLERI and deger:
                temiz_secenekler[kod] = deger
        if not soru or len(temiz_secenekler) < 2:
            continue

        dogru = str(ham_soru.get("dogru") or ham_soru.get("answer") or "").strip().upper()[:1]
        if dogru not in temiz_secenekler:
            dogru = sorted(temiz_secenekler)[0]
        beceri = str(ham_soru.get("beceri") or "").strip().upper()
        if beceri not in BECERI_KODLARI:
            beceri = "KB"

        sorular.append(
            {
                "soru": soru,
                "veri": str(ham_soru.get("veri") or ham_soru.get("data") or "").strip()[:2000],
                "secenekler": dict(sorted(temiz_secenekler.items())),
                "dogru": dogru,
                "cozum": str(ham_soru.get("cozum") or ham_soru.get("solution") or "").strip(),
                "beceri": beceri,
                "kazanim": str(ham_soru.get("kazanim") or "").strip(),
            }
        )
    return sorular


def _parti_uret(
    anahtar: str,
    model: str,
    konu_adi: str,
    adet: int,
    zorluk: str,
    baglam: dict,
) -> tuple[list[dict], str, str]:
    """Tek istekte soru üretir; (sorular, hata_notu, ham_yanıt) döner.

    Yanıt bozuksa bir kez daha, bir soru eksik istenerek denenir; hata geçiciyse
    (kota/yoğunluk) araya kısa bir soluklanma girer.
    """
    son_ham = ""
    son_hata = "geçersiz JSON"
    for deneme in range(2):
        istenen = adet if deneme == 0 else max(1, adet - 1)
        istem = _soru_istemi(konu_adi, istenen, zorluk, baglam)
        try:
            ham = _gemini_cagir(
                anahtar,
                model,
                SORU_SISTEMI,
                [{"rol": "kullanici", "icerik": istem}],
                json_modu=True,
            )
        except Exception as hata:  # ağ/anahtar/kota hatası
            son_hata = _hata_notu(hata)
            if _tekrar_dene_mi(son_hata) and deneme == 0:
                time.sleep(BEKLEME_ORTA)  # kota/yoğunluk kısa sürede geçebilir
            continue
        son_ham = ham
        sorular = _sorulari_duzenle(_sorulari_coz(ham))
        if sorular:
            return sorular, "", ham
        son_hata = "geçersiz JSON"
    return [], son_hata, son_ham


def soru_uret(db: Session, profil: Profil, konu_adi: str, adet: int = 3, zorluk: str = "orta") -> dict:
    """Konuya özel, Maarif Modeli temelli çoktan seçmeli soru üretir (AI anahtarı gerekir).

    Sorular ``SORU_PARTI``lik parçalar hâlinde istenir: böylece 15 soruluk istekler
    jeton sınırında kesilmez, kesilse bile önceki partiler elde kalır. Seçili model
    yoğunluk hatası (503/429) verirse ``YEDEK_MODELLER`` sırayla denenir. Üretim
    ``SORU_SURE_SINIRI`` saniyeyi aşmaz; hiç soru yoksa hata döner.
    """
    anahtar, model = anahtar_getir(db)
    if not anahtar:
        return {"hata": "Yapay zekâ anahtarı yok. Ayarlar > Yapay Zekâ bölümünden ekleyin.", "sorular": []}

    adet = max(1, min(SORU_AZAMI, int(adet or 3)))
    baglam = ogrenci_baglami(db, profil)
    modeller = [model] + [m for m in YEDEK_MODELLER if m != model]
    model_sirasi = 0
    sorular: list[dict] = []
    gorulen: set[str] = set()
    son_ham = ""
    son_hata = "geçersiz JSON"
    bos_tur = 0
    bitis = time.time() + SORU_SURE_SINIRI
    # gereken parti sayısı + 2 yedek tur + her yedek model için bir şans
    hak = (adet + SORU_PARTI - 1) // SORU_PARTI + 2 + len(modeller) - 1

    while len(sorular) < adet and hak > 0 and time.time() < bitis:
        hak -= 1
        istenen = min(SORU_PARTI, adet - len(sorular))
        if sorular:
            time.sleep(PARTI_ARASI_BEKLEME)  # istek sınırına takılmamak için
        aktif = modeller[model_sirasi]
        parti, hata, ham = _parti_uret(anahtar, aktif, konu_adi, istenen, zorluk, baglam)
        son_ham = ham or son_ham
        if parti:
            # aynı partide ve önceki partilerde tekrar eden kökleri at
            yeni: list[dict] = []
            for s in parti:
                anahtar = _soru_anahtari(s)
                if anahtar in gorulen:
                    continue
                gorulen.add(anahtar)
                yeni.append(s)
            if yeni:
                bos_tur = 0
                sorular.extend(yeni)
                continue
            son_hata = "model aynı soruları tekrar etti"
        else:
            son_hata = hata or son_hata
        if not parti and _gecici_mi(son_hata) and model_sirasi + 1 < len(modeller):
            model_sirasi += 1  # model yoğun: yedeğe geç ve aynı partiyi tekrar iste
            continue
        bos_tur += 1
        if bos_tur >= 2:  # iki parti üst üste boş: üretimi bitir
            break
        # kota/yoğunluk ise uzun, içerik hatası ise kısa soluklan
        time.sleep(BEKLEME_UZUN if _tekrar_dene_mi(son_hata) else 3.0)

    if not sorular:
        mesaj = (
            "Model çağrısı başarısız: " + son_hata
            if son_hata != "geçersiz JSON"
            else "Model geçerli JSON döndürmedi"
        )
        return {
            "hata": f"{mesaj}. Tekrar dene; sorun sürerse soru sayısını düşür.",
            "sorular": [],
            "ham": son_ham[:1500],
        }

    sorular = sorular[:adet]
    sonuc = {
        "hata": None,
        "sorular": sorular,
        "kaynak": "gemini",
        "model": modeller[model_sirasi],
    }
    if len(sorular) < adet:
        neden = (
            son_hata
            if son_hata and son_hata != "geçersiz JSON"
            else "model geçerli JSON döndürmedi"
        )
        ipucu = " Biraz sonra tekrar dene." if _tekrar_dene_mi(neden) else ""
        sonuc["uyari"] = (
            f"{len(sorular)} soru üretilebildi (istenen {adet}). Son parti alınamadı: {neden}.{ipucu}"
        )
    return sonuc
