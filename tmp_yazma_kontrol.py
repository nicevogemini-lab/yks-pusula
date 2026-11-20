# -*- coding: utf-8 -*-
"""Yeni token'in yazma yetkisini dogrular (gecici)."""
from __future__ import annotations

import base64
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

KOK = Path(__file__).resolve().parent
load_dotenv(KOK / ".env.yayin")
TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
DEPO = "nicevogemini-lab/yks-pusula"

with httpx.Client(
    timeout=60,
    headers={
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    },
) as gh:
    kullanici = gh.get("https://api.github.com/user")
    print("GET /user:", kullanici.status_code, kullanici.json().get("login") if kullanici.status_code == 200 else "")
    blob = gh.post(
        f"https://api.github.com/repos/{DEPO}/git/blobs",
        json={"content": base64.b64encode(b"probe").decode("ascii"), "encoding": "base64"},
    )
    print("POST git/blobs:", blob.status_code, "| istenen izin:", blob.headers.get("x-accepted-github-permissions"))
    if blob.status_code >= 300:
        print("  govde:", blob.text[:140].replace(TOKEN, "***"))
    else:
        print("  blob:", blob.json().get("sha", "")[:10])
