# -*- coding: utf-8 -*-
"""Hesap tabanlı giriş kapısı.

Panele yönetici, veli ve öğrenci hesaplarıyla girilir. Şifreler
``pbkdf2_hmac`` ile özetlenir (ek bağımlılık yok). Oturum çerezi
``kullanici_id|rol|bitis|imza`` biçimindedir ve ``ayarlar`` tablosundaki
oturum anahtarı + kullanıcının şifre özetiyle imzalanır:

* sunucu yeniden başlasa da oturumlar geçerli kalır,
* şifresi değişen kullanıcının eski çerezleri kendiliğinden düşer.

Hesap yokken uygulama kurulum ekranını gösterir: ilk yönetici oradaki formdan
oluşturulur. ``PUSULA_GIRIS_ZORUNLU=0`` verilirse kapı kapanır (yalnız yerel
deneme ve testler için).
"""
from __future__ import annotations

import hashlib
import hmac
import html
import os
import secrets
import time
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.requests import Request
from starlette.responses import Response

from .models import Ayar, Kullanici

COOKIE_AD = "pusula_oturum"
# Oturum ve çerez ömrü (gün cinsinden): 90 gün boyunca şifre yeniden sorulmaz
OTURUM_SURE_SN = 90 * 24 * 60 * 60
# Çerez ömrünün son üçte birine girince kendiliğinden tazelenir
TAZELEME_ESIGI_SN = OTURUM_SURE_SN // 3
# Hatalı deneme sınırı: 10 dakikada 6 yanlış girişten sonra kısa süre kilit
HATA_PENCERE_SN = 10 * 60
HATA_SINIRI = 6
# Şifre özeti turu (pbkdf2)
OZET_TUR = 240_000

# Başarısız denemeler: {istemci: [zaman damgası, ...]}
_hatalar: dict[str, list[float]] = {}


# ------------------------------------------------------------------ durum
def giris_zorunlu() -> bool:
    """Giriş kapısı açık mı? (Testlerde ve yerel denemede kapatılabilir.)"""
    return os.getenv("PUSULA_GIRIS_ZORUNLU", "1").strip() != "0"


def kurulum_gerekli(db: Session) -> bool:
    """Hiç yönetici yoksa ilk kurulum ekranı gösterilir."""
    return db.execute(select(Kullanici.id).where(Kullanici.rol == "yonetici")).first() is None


# ------------------------------------------------------------------ şifre
def sifre_ozetle(sifre: str) -> str:
    """Şifreyi tuzlu pbkdf2 özetine çevirir: ``pbkdf2$tur$tuz$ozet``."""
    tuz = secrets.token_hex(16)
    ozet = hashlib.pbkdf2_hmac("sha256", sifre.encode("utf-8"), tuz.encode("utf-8"), OZET_TUR)
    return f"pbkdf2${OZET_TUR}${tuz}${ozet.hex()}"


def sifre_dogrula(sifre: str, kayit: str) -> bool:
    try:
        tur, tuz, ozet = kayit.split("$")[1:]
        hesaplanan = hashlib.pbkdf2_hmac(
            "sha256", sifre.encode("utf-8"), tuz.encode("utf-8"), int(tur)
        )
    except (ValueError, AttributeError):
        return False
    return hmac.compare_digest(hesaplanan.hex(), ozet)


def sifre_uygun(sifre: str) -> str:
    """Şifre kuralını denetler; hata varsa mesaj döndürür."""
    if len(sifre) < 6:
        return "Şifre en az 6 karakter olmalı."
    return ""


def kullanici_adi_uygun(ad: str) -> str:
    ad = ad.strip()
    if len(ad) < 3:
        return "Kullanıcı adı en az 3 karakter olmalı."
    if len(ad) > 40:
        return "Kullanıcı adı en fazla 40 karakter olabilir."
    if not all(k.isalnum() or k in "._-" for k in ad):
        return "Kullanıcı adında yalnız harf, rakam, nokta, tire ve alt çizgi olabilir."
    return ""


# ------------------------------------------------------------------ çerez
def _oturum_anahtari(db: Session) -> str:
    """Sunucuya özgü imza anahtarı; ilk kullanımda üretilip saklanır."""
    kayit = db.get(Ayar, "oturum_anahtari")
    if kayit is None or len(kayit.deger) < 32:
        kayit = Ayar(anahtar="oturum_anahtari", deger=secrets.token_hex(32))
        db.merge(kayit)
        db.commit()
    return kayit.deger


def _imza(db: Session, kullanici: Kullanici, govde: str) -> str:
    anahtar = f"{_oturum_anahtari(db)}|{kullanici.sifre_hash}".encode("utf-8")
    return hmac.new(anahtar, govde.encode("utf-8"), hashlib.sha256).hexdigest()[:40]


def oturum_degeri(db: Session, kullanici: Kullanici) -> str:
    """Yeni oturum çerezi değeri: ``id|rol|bitis|imza``."""
    bitis = int(time.time()) + OTURUM_SURE_SN
    govde = f"{kullanici.id}|{kullanici.rol}|{bitis}"
    return f"{govde}|{_imza(db, kullanici, govde)}"


def oturum_kullanici(db: Session, deger: str | None) -> Kullanici | None:
    """Çerezden kullanıcıyı çözer; geçersizse ``None``."""
    if not deger:
        return None
    parcalar = deger.split("|")
    if len(parcalar) != 4:
        return None
    kimlik, _rol, bitis, imza = parcalar
    if not kimlik.isdigit() or not bitis.isdigit():
        return None
    if int(bitis) < time.time():
        return None
    kullanici = db.get(Kullanici, int(kimlik))
    if kullanici is None or not kullanici.aktif:
        return None
    govde = f"{kimlik}|{kullanici.rol}|{bitis}"
    if not hmac.compare_digest(imza, _imza(db, kullanici, govde)):
        return None
    return kullanici


def kalan_sn(deger: str | None) -> int:
    """Çerezin kalan ömrü (saniye); okunamıyorsa 0."""
    if not deger:
        return 0
    parcalar = deger.split("|")
    if len(parcalar) != 4 or not parcalar[2].isdigit():
        return 0
    return int(parcalar[2]) - int(time.time())


def guvenli_mi(request: Request) -> bool:
    """Çerez ``Secure`` olarak işaretlensin mi (https ya da tünel arkası)."""
    if request.url.scheme == "https":
        return True
    return request.headers.get("x-forwarded-proto", "").split(",")[0].strip() == "https"


def oturum_kur(yanit: Response, request: Request, db: Session, kullanici: Kullanici) -> Response:
    yanit.set_cookie(
        COOKIE_AD,
        oturum_degeri(db, kullanici),
        max_age=OTURUM_SURE_SN,
        httponly=True,
        samesite="lax",
        secure=guvenli_mi(request),
        path="/",
    )
    return yanit


def oturum_sil(yanit: Response) -> Response:
    yanit.delete_cookie(COOKIE_AD, path="/")
    return yanit


# ------------------------------------------------------------ hatalı deneme
def _istemci(request: Request) -> str:
    ileten = request.headers.get("x-forwarded-for", "")
    if ileten:
        return ileten.split(",")[0].strip()
    return request.client.host if request.client else "-"


def cok_hata(request: Request) -> bool:
    simdi = time.time()
    kayitlar = [t for t in _hatalar.get(_istemci(request), []) if simdi - t < HATA_PENCERE_SN]
    _hatalar[_istemci(request)] = kayitlar
    return len(kayitlar) >= HATA_SINIRI


def hata_ekle(request: Request) -> None:
    _hatalar.setdefault(_istemci(request), []).append(time.time())


def hata_temizle(request: Request) -> None:
    _hatalar.pop(_istemci(request), None)


# ------------------------------------------------------------------- sayfa
def guvenli_hedef(yol: str | None) -> str:
    """Giriş sonrası dönülecek yol: yalnızca site içi adres kabul edilir."""
    if not yol or not yol.startswith("/") or yol.startswith("//") or "\\" in yol:
        return "/"
    return yol


_CSS = """
  *, *::before, *::after { box-sizing: border-box; }
  html, body { height: 100%; }
  body {
    margin: 0;
    min-height: 100dvh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px 18px calc(24px + env(safe-area-inset-bottom));
    background:
      radial-gradient(1200px 600px at 50% -10%, rgba(234, 88, 12, .22), transparent 60%),
      linear-gradient(160deg, #23262e 0%, #2b303a 55%, #23262e 100%);
    color: #171b22;
    font-family: "Segoe UI Variable Text", "Segoe UI", system-ui, -apple-system,
      Roboto, "Helvetica Neue", Arial, sans-serif;
    -webkit-font-smoothing: antialiased;
  }
  .kart {
    width: 100%;
    max-width: 392px;
    background: #ffffff;
    border-radius: 20px;
    padding: 28px 24px 22px;
    box-shadow: 0 28px 60px -28px rgba(0, 0, 0, .6), 0 2px 0 rgba(255, 255, 255, .06) inset;
  }
  .marka { display: flex; align-items: center; gap: 12px; margin-bottom: 22px; }
  .isaret {
    width: 42px; height: 42px; border-radius: 13px;
    background: #ea580c; display: grid; place-items: center;
    box-shadow: 0 12px 22px -14px rgba(234, 88, 12, 1);
  }
  .marka b { display: block; font-size: 16px; letter-spacing: -.2px; }
  .marka small { display: block; font-size: 11.5px; color: #6b7280; margin-top: 1px; }
  h1 { font-size: 19px; letter-spacing: -.35px; margin: 0 0 6px; }
  .alt { margin: 0 0 20px; font-size: 12.5px; line-height: 1.55; color: #6b7280; }
  label { display: block; font-size: 12px; font-weight: 600; color: #374151; margin-bottom: 6px; }
  input[type="text"], input[type="password"] {
    width: 100%;
    padding: 13px 14px;
    font-size: 16px;
    font-family: inherit;
    color: #171b22;
    background: #f5f6f8;
    border: 1px solid #e6e8ee;
    border-radius: 12px;
    outline: none;
    transition: border-color .18s ease, box-shadow .18s ease, background .18s ease;
  }
  input[type="text"]:focus, input[type="password"]:focus {
    background: #ffffff;
    border-color: #ea580c;
    box-shadow: 0 0 0 4px rgba(234, 88, 12, .16);
  }
  .alan { margin-bottom: 14px; }
  button {
    width: 100%;
    margin-top: 6px;
    padding: 13px 16px;
    font: inherit;
    font-size: 14.5px;
    font-weight: 700;
    color: #ffffff;
    background: #ea580c;
    border: 0;
    border-radius: 12px;
    cursor: pointer;
    transition: background .18s ease, transform .06s ease;
  }
  button:hover { background: #c2410c; }
  button:active { transform: translateY(1px); }
  .hata {
    margin: 14px 0 0;
    padding: 10px 12px;
    font-size: 12.5px;
    color: #b91c1c;
    background: #fdecec;
    border: 1px solid #f6c9c9;
    border-radius: 10px;
  }
  .dip { margin: 18px 0 0; font-size: 11px; line-height: 1.5; color: #9aa1ad; text-align: center; }
"""

_ISARET = """
      <span class="isaret">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="22" height="22"
             fill="none" stroke="#ffffff" stroke-width="1.9" stroke-linecap="round"
             stroke-linejoin="round" aria-hidden="true">
          <path d="M12 2l8 5v10l-8 5-8-5V7z"/>
          <path d="M12 8l3 7-3-1.6L9 15z"/>
        </svg>
      </span>
"""


def _sayfa(baslik: str, icerik: str, hata: str = "") -> str:
    """Giriş ve kurulum ekranlarının ortak iskeleti."""
    hata_kutusu = f'<p class="hata">{html.escape(hata)}</p>' if hata else ""
    return f"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#23262e">
<meta name="robots" content="noindex">
<title>{html.escape(baslik)} · YKS Pusula</title>
<style>{_CSS}</style>
</head>
<body>
  <main class="kart">
    <div class="marka">{_ISARET}
      <div>
        <b>YKS Pusula</b>
        <small>Eğitim koçluğu platformu</small>
      </div>
    </div>
    {icerik}
    {hata_kutusu}
  </main>
</body>
</html>
"""


def giris_sayfasi(hata: str = "", hedef: str = "/") -> str:
    """Giriş ekranı: kullanıcı adı + şifre."""
    icerik = f"""
    <h1>Devam etmek için giriş yap</h1>
    <p class="alt">Yönetici, veli ve öğrenci hesapları buradan girer. Bu cihaz 90 gün açık kalır.</p>
    <form method="post" action="/giris">
      <input type="hidden" name="next" value="{html.escape(guvenli_hedef(hedef))}">
      <div class="alan">
        <label for="kullanici">Kullanıcı adı</label>
        <input id="kullanici" name="kullanici" type="text" autocomplete="username"
               autofocus required spellcheck="false" autocapitalize="none">
      </div>
      <div class="alan">
        <label for="sifre">Şifre</label>
        <input id="sifre" name="sifre" type="password" autocomplete="current-password"
               required placeholder="&#8226;&#8226;&#8226;&#8226;&#8226;&#8226;">
      </div>
      <button type="submit">Giriş yap</button>
    </form>
    <p class="dip">Şifreni unuttuysan yöneticiden yeni şifre iste.</p>
"""
    return _sayfa("Giriş", icerik, hata)


def kurulum_sayfasi(hata: str = "", deger: dict | None = None) -> str:
    """İlk kurulum: yönetici hesabı oluşturma ekranı."""
    deger = deger or {}
    icerik = f"""
    <h1>İlk kurulum</h1>
    <p class="alt">Henüz hesap yok. Yönetici hesabını oluştur; ardından veli ve
    öğrenci hesaplarını Kullanıcılar sayfasından tanımlayacaksın.</p>
    <form method="post" action="/kurulum">
      <div class="alan">
        <label for="kullanici">Kullanıcı adı</label>
        <input id="kullanici" name="kullanici" type="text" autocomplete="username"
               autofocus required spellcheck="false" autocapitalize="none"
               value="{html.escape(str(deger.get('kullanici', '')))}">
      </div>
      <div class="alan">
        <label for="ad">Ad soyad</label>
        <input id="ad" name="ad" type="text" autocomplete="name"
               value="{html.escape(str(deger.get('ad', '')))}">
      </div>
      <div class="alan">
        <label for="sifre">Şifre</label>
        <input id="sifre" name="sifre" type="password" autocomplete="new-password" required>
      </div>
      <div class="alan">
        <label for="sifre2">Şifre (tekrar)</label>
        <input id="sifre2" name="sifre2" type="password" autocomplete="new-password" required>
      </div>
      <button type="submit">Yönetici hesabını oluştur</button>
    </form>
    <p class="dip">Bu ekran yalnız bir kez, ilk yönetici oluşturulurken görünür.</p>
"""
    return _sayfa("Kurulum", icerik, hata)


def yonlendirme_hedefi(next_yol: str | None) -> str:
    """Giriş sonrası adres (dış bağlantılar kök sayfaya çevrilir)."""
    return guvenli_hedef(next_yol)


def giris_yolu(yol: str) -> str:
    """Oturum yokken HTML isteğini giriş ekranına taşıyan adres."""
    if yol in ("", "/"):
        return "/giris"
    return f"/giris?next={quote(yol)}"
