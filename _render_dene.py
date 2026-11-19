# -*- coding: utf-8 -*-
"""Gecici teshis: Render servis olusturma neden 403 donuyor."""
import json
import os

import httpx

RD = "https://api.render.com/v1"
H = {"Authorization": f"Bearer {os.environ['RENDER_API_KEY']}", "Accept": "application/json"}

with httpx.Client(timeout=60, headers=H) as c:
    r = c.get(f"{RD}/services", params={"limit": 5})
    print("GET /services:", r.status_code, r.text[:300])

    o = c.get(f"{RD}/owners").json()[0]["owner"]
    print("owner:", o["id"], o["type"])

    govde = {
        "type": "web_service",
        "name": "yks-pusula",
        "ownerId": o["id"],
        "repo": "https://github.com/nicevogemini-lab/yks-pusula",
        "branch": "main",
        "autoDeploy": "yes",
        "serviceDetails": {
            "env": "docker",
            "plan": "free",
            "region": "ohio",
            "healthCheckPath": "/api/saglik",
            "envSpecificDetails": {"dockerfilePath": "./Dockerfile", "dockerContext": "."},
        },
    }
    r = c.post(f"{RD}/services", json=govde)
    print("POST /services:", r.status_code)
    print(r.text[:1500])
