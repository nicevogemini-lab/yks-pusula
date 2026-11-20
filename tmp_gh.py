# -*- coding: utf-8 -*-
"""GitHub token kimligini ve repo yetkilerini dogrular (gecici arac)."""
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

KOK = Path(__file__).resolve().parent
load_dotenv(KOK / ".env.yayin")
belirteç = os.getenv("GITHUB_TOKEN", "").strip()
if not belirteç:
    raise SystemExit("GITHUB_TOKEN yok")

B = {"Authorization": f"Bearer {belirteç}", "Accept": "application/vnd.github+json",
     "X-GitHub-Api-Version": "2022-11-28"}

with httpx.Client(timeout=60, headers=B) as gh:
    u = gh.get("https://api.github.com/user")
    print("kullanici http:", u.status_code)
    if u.status_code != 200:
        raise SystemExit(u.text[:300])
    print("login:", u.json().get("login"))

    r = gh.get("https://api.github.com/repos/nicevogemini-lab/yks-pusula")
    print("repo http:", r.status_code)
    if r.status_code == 200:
        veri = r.json()
        print("repo:", veri["full_name"], "| private:", veri["private"], "| dal:", veri["default_branch"])
        print("permissions:", veri.get("permissions"))
