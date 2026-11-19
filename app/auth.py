# -*- coding: utf-8 -*-
"""Tek kodlu giriş kapısı.

Uygulama internete açık bir adresten kullanıldığında verileri korumak için
basit bir oturum kapısı vardır. ``PUSULA_SIFRE`` ortam değişkeni boşsa kapı
kapalıdır (yerel kullanım); dolu olduğunda ``/giris`` dışındaki tüm sayfalar ve
``/api`` uçları imzalı çerez ister.

Çerez, şifreden türetilen bir HMAC anahtarıyla imzalanır: şifre değişmedikçe
sunucu yeniden başlasa da oturumlar geçerli kalır, şifre değişince eski
çerezler kendiliğinden düşer.
"""
from __future__ import annotations

import hashlib
import hmac
import html
import os
import time

from starlette.requests import Request
from starlette.responses import Response

COOKIE_AD = "pusula_oturum"
# Oturum ve çerez ömrü (gün cinsinden): 90 gün boyunca kod yeniden sorulmaz
OTURUM_SURE_SN = 90 * 24 * 60 * 60
# Çerez ömrünün son üçte birine girince kendiliğinden tazelenir
TAZELEME_ESIGI_SN = OTURUM_SURE_SN // 3
# Hatalı deneme sınırı: 10 dakikada 6 yanlış koddan sonra kısa süre kilit
HATA_PENCERE_SN = 10 * 60
HATA_SINIRI = 6

# Başarısız denemeler: {istemci: [zaman damgası, ...]}
_hatalar: dict[str, list[float]] = {}


# ------------------------------------------------------------------ durum
def sifre() -> str:
    """Ortam değişkenindeki giriş kodu (boşsa kapı kapalı)."""
    return os.getenv("PUSULA_SIFRE", "").strip()


def kapi_acik() -> bool:
    return bool(sifre())


# ------------------------------------------------------------------ çerez
def _anahtar() -> bytes:
    return hashlib.sha256(f"pusula|{sifre()}".encode("utf-8")).digest()


def _imza(mesaj: str) -> str:
    return hmac.new(_anahtar(), mesaj.encode("utf-8"), hashlib.sha256).hexdigest()[:40]


def oturum_degeri() -> str:
    """Yeni oturum çerezi değeri: ``bitis.imza``."""
    bitis = int(time.time()) + OTURUM_SURE_SN
    return f"{bitis}.{_imza(str(bitis))}"


def oturum_gecerli(deger: str | None) -> bool:
    if not deger or not kapi_acik():
        return False
    bitis, ayirici, imza = deger.partition(".")
    if not ayirici or not bitis.isdigit() or not imza:
        return False
    if int(bitis) < time.time():
        return False
    return hmac.compare_digest(imza, _imza(bitis))


def kalan_sn(deger: str | None) -> int:
    """Çerezin kalan ömrü (saniye); okunamıyorsa 0."""
    if not deger:
        return 0
    bitis, _, _ = deger.partition(".")
    try:
        return int(bitis) - int(time.time())
    except ValueError:
        return 0


def guvenli_mi(request: Request) -> bool:
    """Çerez ``Secure`` olarak işaretlensin mi (https ya da tünel arkası)."""
    if request.url.scheme == "https":
        return True
    return request.headers.get("x-forwarded-proto", "").split(",")[0].strip() == "https"


def oturum_kur(yanit: Response, request: Request) -> Response:
    yanit.set_cookie(
        COOKIE_AD,
        oturum_degeri(),
        max_age=OTURUM_SURE_SN,
        httponly=True,
        samesite="lax",
        secure=guvenli_mi(request),
        path="/",
    )
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


_SAYFA = """<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#23262e">
<meta name="robots" content="noindex">
<title>Giriş · YKS Pusula</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; }}
  html, body {{ height: 100%; }}
  body {{
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
  }}
  .kart {{
    width: 100%;
    max-width: 372px;
    background: #ffffff;
    border-radius: 20px;
    padding: 28px 24px 22px;
    box-shadow: 0 28px 60px -28px rgba(0, 0, 0, .6), 0 2px 0 rgba(255, 255, 255, .06) inset;
  }}
  .marka {{ display: flex; align-items: center; gap: 12px; margin-bottom: 22px; }}
  .isaret {{
    width: 42px; height: 42px; border-radius: 13px;
    background: #ea580c; display: grid; place-items: center;
    box-shadow: 0 12px 22px -14px rgba(234, 88, 12, 1);
  }}
  .marka b {{ display: block; font-size: 16px; letter-spacing: -.2px; }}
  .marka small {{ display: block; font-size: 11.5px; color: #6b7280; margin-top: 1px; }}
  h1 {{ font-size: 19px; letter-spacing: -.35px; margin: 0 0 6px; }}
  .alt {{ margin: 0 0 20px; font-size: 12.5px; line-height: 1.55; color: #6b7280; }}
  label {{ display: block; font-size: 12px; font-weight: 600; color: #374151; margin-bottom: 6px; }}
  input[type="password"] {{
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
  }}
  input[type="password"]:focus {{
    background: #ffffff;
    border-color: #ea580c;
    box-shadow: 0 0 0 4px rgba(234, 88, 12, .16);
  }}
  button {{
    width: 100%;
    margin-top: 16px;
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
  }}
  button:hover {{ background: #c2410c; }}
  button:active {{ transform: translateY(1px); }}
  .hata {{
    margin: 14px 0 0;
    padding: 10px 12px;
    font-size: 12.5px;
    color: #b91c1c;
    background: #fdecec;
    border: 1px solid #f6c9c9;
    border-radius: 10px;
  }}
  .dip {{ margin: 18px 0 0; font-size: 11px; line-height: 1.5; color: #9aa1ad; text-align: center; }}
</style>
</head>
<body>
  <main class="kart">
    <div class="marka">
      <span class="isaret">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="22" height="22"
             fill="none" stroke="#ffffff" stroke-width="1.9" stroke-linecap="round"
             stroke-linejoin="round" aria-hidden="true">
          <path d="M12 2l8 5v10l-8 5-8-5V7z"/>
          <path d="M12 8l3 7-3-1.6L9 15z"/>
        </svg>
      </span>
      <div>
        <b>YKS Pusula</b>
        <small>Eğitim koçluğu platformu</small>
      </div>
    </div>
    <h1>Devam etmek için giriş yap</h1>
    <p class="alt">Bu alan aileye özel. Kodu bir kez gir; bu cihaz 90 gün boyunca açık kalır.</p>
    <form method="post" action="/giris">
      <input type="hidden" name="next" value="{hedef}">
      <label for="kod">Giriş kodu</label>
      <input id="kod" name="kod" type="password" autocomplete="current-password"
             autofocus required spellcheck="false" placeholder="&#8226;&#8226;&#8226;&#8226;&#8226;&#8226;">
      <button type="submit">Giriş yap</button>
    </form>
    {hata}
    <p class="dip">Kodu bilmiyorsan velinden iste.</p>
  </main>
</body>
</html>
"""


def giris_sayfasi(hata: str = "", hedef: str = "/") -> str:
    """Giriş ekranı (kendi içinde stilli, mobil öncelikli)."""
    hata_kutusu = f'<p class="hata">{html.escape(hata)}</p>' if hata else ""
    return _SAYFA.format(hedef=html.escape(guvenli_hedef(hedef)), hata=hata_kutusu)
