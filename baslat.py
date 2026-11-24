# -*- coding: utf-8 -*-
"""A-KEY sunucusunu başlatır (çift tıkla çalıştırılabilir)."""
from __future__ import annotations

import os
import socket
import sys
import webbrowser
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

KOK = Path(__file__).resolve().parent
load_dotenv(KOK / ".env")

HOST = os.getenv("PUSULA_HOST", "0.0.0.0")
PORT = int(os.getenv("PUSULA_PORT", "8317"))


def _yerel_ip() -> str:
    """Aynı ağdaki telefon/tablet için bilgisayarın yerel IP'si."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


if __name__ == "__main__":
    adres = f"http://127.0.0.1:{PORT}"
    print("=" * 58)
    print("  A-KEY - Üniversiteye Giriş Anahtarı")
    print("=" * 58)
    print(f"  Bu bilgisayar : {adres}")
    print(f"  Aynı ağdaki cihazlar: http://{_yerel_ip()}:{PORT}")
    print("  Kapatmak için: Ctrl + C")
    print("=" * 58)

    if "--tarayici-acma" not in sys.argv:
        webbrowser.open(adres)

    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=False, log_level="info")
