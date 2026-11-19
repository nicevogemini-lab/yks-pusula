# -*- coding: utf-8 -*-
"""YKS Pusula uygulama girişi.

Çalıştırma::

    python -m uvicorn app.main:app --host 0.0.0.0 --port 8317
    # veya
    python baslat.py
"""
from __future__ import annotations

import asyncio
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import parse_qs, quote

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request

from . import auth, bekci
from .api import api
from .database import BASE_DIR, Base, SessionLocal, engine
from .seed import mufredati_yukle, sema_guncelle

WEB_DIR = BASE_DIR / "web"
WEB_DIR.mkdir(parents=True, exist_ok=True)

TAZE_BASLIKLAR = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
}


class TazeStaticFiles(StaticFiles):
    """Statik dosyaları her zaman taze ver.

    Starlette varsayılan olarak ETag/Last-Modified üretip 304 döndürür; tarayıcı
    eski JavaScript/CSS'i önbellekten çalıştırmaya devam eder. Bu alt sınıf
    koşullu istekleri de tam içerikle yanıtlar ve önbelleği kapatır.
    """

    async def get_response(self, path: str, scope):
        istek = Request(scope)
        yanit = await super().get_response(path, scope)
        if yanit.status_code == 304:
            # Koşullu isteği (If-None-Match / If-Modified-Since) yok say
            temiz_scope = dict(scope)
            temiz_scope["headers"] = [
                (ad, deger)
                for ad, deger in scope.get("headers", [])
                if ad.lower() not in (b"if-none-match", b"if-modified-since", b"if-match")
            ]
            yanit = await super().get_response(path, temiz_scope)
        yanit.headers.update(TAZE_BASLIKLAR)
        for baslik in ("etag", "last-modified", "expires"):
            if baslik in yanit.headers:
                del yanit.headers[baslik]
        if istek.method == "HEAD":
            yanit.body = b""
        return yanit


@asynccontextmanager
async def yasam_dongusu(_app: FastAPI):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        sema_guncelle(db)
        mufredati_yukle(db)
    uyanik_tut = bekci.basla()  # bulutta: kendini uyanık tutan arka plan döngüsü
    yield
    if uyanik_tut is not None:
        uyanik_tut.cancel()


# Arayüz sürümü: web/ altındaki en yeni dosyanın zaman damgası.
# Statik dosyalar sürümlü yol altından yayınlanır; böylece dosya değişince URL
# değişir ve tarayıçı eski JavaScript/CSS'i önbellekten çalıştıramaz.
def _arayuz_damgasi() -> str:
    zamanlar = [p.stat().st_mtime for p in WEB_DIR.rglob("*") if p.is_file()]
    return time.strftime("%Y%m%d%H%M%S", time.localtime(max(zamanlar, default=0)))


ARAYUZ_SURUM = _arayuz_damgasi()


def taze_dosya(dosya: Path) -> FileResponse:
    """Önbelleğe alınmayan dosya yanıtı (ETag/Last-Modified kaldırılır)."""
    yanit = FileResponse(dosya)
    yanit.headers.update(TAZE_BASLIKLAR)
    for baslik in ("etag", "last-modified", "expires"):
        if baslik in yanit.headers:
            del yanit.headers[baslik]
    return yanit


def arayuz_yaniti() -> HTMLResponse:
    """index.html'i güncel sürümlü statik yoluyla sun."""
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    surum_yolu = f"/y/{_arayuz_damgasi()}/"
    return HTMLResponse(
        html.replace("/statik/", surum_yolu),
        headers={**TAZE_BASLIKLAR, "Content-Type": "text/html; charset=utf-8"},
    )


app = FastAPI(title="YKS Pusula", version="0.1.0", lifespan=yasam_dongusu)
app.include_router(api)
app.mount("/statik", TazeStaticFiles(directory=WEB_DIR), name="statik")

# Giriş kapısı: bu yollar kod sorulmadan açılır (sağlık kontrolü, statik, giriş)
SERBEST_ON_EKLER = ("/giris", "/cikis", "/api/saglik", "/statik/", "/y/", "/favicon")


@app.middleware("http")
async def giris_kapisi(request: Request, call_next):
    """``PUSULA_SIFRE`` doluysa sayfaları ve API'yi imzalı çereze bağlar.

    İnternete açık adreste linki bilen herkesin verileri görmesini engeller.
    Şifre boşsa (yerel kullanım) kapı kapalıdır ve istekler olduğu gibi geçer.
    """
    if not auth.kapi_acik():
        return await call_next(request)
    yol = request.url.path
    if yol.startswith(SERBEST_ON_EKLER):
        return await call_next(request)
    cerez = request.cookies.get(auth.COOKIE_AD)
    if auth.oturum_gecerli(cerez):
        yanit = await call_next(request)
        # Ömrünün son üçte birine giren oturum sessizce tazelenir
        if auth.kalan_sn(cerez) < auth.TAZELEME_ESIGI_SN:
            auth.oturum_kur(yanit, request)
        return yanit
    if yol.startswith("/api/"):
        return JSONResponse({"detail": "Oturum gerekli"}, status_code=401)
    if yol in ("", "/"):
        return RedirectResponse("/giris", status_code=303)
    return RedirectResponse(f"/giris?next={quote(yol)}", status_code=303)


@app.get("/", include_in_schema=False)
def kok():
    return arayuz_yaniti()


@app.get("/giris", include_in_schema=False)
def giris_formu(request: Request, next: str = "/"):
    """Giriş ekranı; oturum zaten açıksa doğrudan uygulamaya geçer."""
    if not auth.kapi_acik():
        return RedirectResponse("/", status_code=303)
    if auth.oturum_gecerli(request.cookies.get(auth.COOKIE_AD)):
        return RedirectResponse(auth.guvenli_hedef(next), status_code=303)
    return HTMLResponse(auth.giris_sayfasi(hedef=next))


@app.post("/giris", include_in_schema=False)
async def giris_yap(request: Request):
    """Giriş kodunu doğrular; doğruysa imzalı oturum çerezi kurar."""
    if not auth.kapi_acik():
        return RedirectResponse("/", status_code=303)
    if auth.cok_hata(request):
        return HTMLResponse(
            auth.giris_sayfasi(
                hata="Çok fazla hatalı deneme. Birkaç dakika sonra tekrar dene.",
            ),
            status_code=429,
        )
    # Gövde form kodlamasında gelir (ek bağımlılık gerekmesin diye elle çözülür)
    govde = (await request.body()).decode("utf-8", "replace")
    alanlar = parse_qs(govde)
    hedef = auth.guvenli_hedef((alanlar.get("next") or ["/"])[0])
    kod = (alanlar.get("kod") or [""])[0].strip()
    if kod and secrets.compare_digest(kod, auth.sifre()):
        auth.hata_temizle(request)
        return auth.oturum_kur(RedirectResponse(hedef, status_code=303), request)
    auth.hata_ekle(request)
    await asyncio.sleep(0.4)  # Kaba kuvvet denemelerini yavaşlatır
    return HTMLResponse(
        auth.giris_sayfasi(hata="Giriş kodu hatalı.", hedef=hedef), status_code=401
    )


@app.get("/cikis", include_in_schema=False)
def cikis():
    """Oturumu kapatır: çerezi siler, giriş ekranına döner."""
    yanit = RedirectResponse("/giris", status_code=303)
    yanit.delete_cookie(auth.COOKIE_AD, path="/")
    return yanit


@app.get("/y/{surum}/{yol:path}", include_in_schema=False)
def surumlu_statik(surum: str, yol: str):
    """Sürümlü statik yol: /y/<sürüm>/js/app.js → web/js/app.js.

    Sürüm parçası yolda olduğu için tarayıcı eski dosyayı önbellekten veremez.
    """
    aday = (WEB_DIR / yol).resolve()
    try:
        aday.relative_to(WEB_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=404, detail="Dosya bulunamadı")
    if not aday.is_file():
        raise HTTPException(status_code=404, detail="Dosya bulunamadı")
    return taze_dosya(aday)


@app.get("/{yol:path}", include_in_schema=False)
def spa(yol: str):
    if yol.startswith("api"):
        raise HTTPException(status_code=404, detail="Uç nokta bulunamadı")
    aday = WEB_DIR / yol
    if aday.is_file():
        return taze_dosya(aday)
    return arayuz_yaniti()
