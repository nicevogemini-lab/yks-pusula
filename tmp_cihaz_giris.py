# -*- coding: utf-8 -*-
"""GitHub cihaz onay akisiyle yazma yetkili token alir (gecici).

Kullanici github.com/login/device adresinde tek kullanimlik kodu onaylar;
token .env.yayin icindeki GITHUB_TOKEN satirina yazilir.
"""
from __future__ import annotations

import re
import time
from pathlib import Path

import httpx

KOK = Path(__file__).resolve().parent
ENV = KOK / ".env.yayin"
# GitHub CLI'in herkese acik OAuth istemcisi: cihaz akisini destekler
ISTEMCI = "178c6fc778ccc68e1d6a"
KAPSAM = "repo workflow"

with httpx.Client(timeout=60, headers={"Accept": "application/json"}) as istek:
    baslangic = istek.post(
        "https://github.com/login/device/code",
        data={"client_id": ISTEMCI, "scope": KAPSAM},
    )
    baslangic.raise_for_status()
    veri = baslangic.json()
    cihaz = veri["device_code"]
    print("KOD:", veri["user_code"], flush=True)
    print("ADRES:", veri["verification_uri"], flush=True)
    print("GECERLILIK:", veri.get("expires_in"), "saniye", flush=True)
    bekle = int(veri.get("interval", 5))

    bitis = time.time() + int(veri.get("expires_in", 900))
    while time.time() < bitis:
        time.sleep(bekle)
        yanit = istek.post(
            "https://github.com/login/oauth/access_token",
            data={
                "client_id": ISTEMCI,
                "device_code": cihaz,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            },
        )
        govde = yanit.json()
        hata = govde.get("error")
        if hata == "authorization_pending":
            continue
        if hata == "slow_down":
            bekle += 5
            continue
        if hata:
            print("HATA:", hata, govde.get("error_description", ""), flush=True)
            raise SystemExit(1)

        token = (govde.get("access_token") or "").strip()
        if not token:
            print("HATA: token gelmedi", flush=True)
            raise SystemExit(1)

        # Token'i dosyaya yaz (sohbete basilmaz)
        icerik = ENV.read_text(encoding="utf-8")
        yeni = re.sub(r"(?m)^GITHUB_TOKEN=.*$", f"GITHUB_TOKEN={token}", icerik)
        ENV.write_text(yeni, encoding="utf-8")
        print("TOKEN ALINDI | kapsam:", govde.get("scope"), flush=True)
        break
