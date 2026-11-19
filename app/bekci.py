"""Uygulamayı kendi kendine uyanık tutan hafif bekçi.

Render ücretsiz örnek (instance) 15 dakika trafik almazsa uyur; soğuk
uyanma yaklaşık 40 saniye sürer. Bu bekçi 02:00-22:59 UTC (05:00-01:55
İstanbul) arasında 10 dakikada bir kendi sağlık adresine istek atar, böylece
gündüz uyuma olmaz. Gece istek atılmaz: aylık 750 saat sınırı aşılmaz ve
gece gelen kullanıcı zaten uyanmayı kendisi başlatmış olur.

Yerelde (RENDER_EXTERNAL_URL / PUSULA_CANLI_URL yokken) bekçi hiç başlamaz.
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

import httpx

PENCERE_BAS_SAAT = 2  # UTC
PENCERE_SON_SAAT = 22  # UTC, dahil
DONGU_SN = 10 * 60
ISTEK_SN = 40


def pencere_acik(an: datetime | None = None) -> bool:
    """Uyanık kalınacak saat aralığında mıyız?"""
    saat = (an or datetime.now(timezone.utc)).hour
    return PENCERE_BAS_SAAT <= saat <= PENCERE_SON_SAAT


def hedef_adres() -> str:
    """Kendi genel adresimiz; bulutta değilsek boş döner."""
    return (os.getenv("PUSULA_CANLI_URL") or os.getenv("RENDER_EXTERNAL_URL") or "").rstrip("/")


async def _dongu(hedef: str) -> None:
    adres = f"{hedef}/api/saglik"
    async with httpx.AsyncClient(timeout=ISTEK_SN) as istemci:
        while True:
            await asyncio.sleep(DONGU_SN)
            if not pencere_acik():
                continue
            try:
                await istemci.get(adres)
            except Exception:  # ağ hatası bekçiyi durdurmamalı
                pass


def basla() -> asyncio.Task | None:
    """Bekçiyi arka planda başlatır; adres yoksa hiçbir şey yapmaz."""
    hedef = hedef_adres()
    if not hedef:
        return None
    return asyncio.create_task(_dongu(hedef), name="bekci")
