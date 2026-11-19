# -*- coding: utf-8 -*-
"""Puan/net hesapları ve deneme analizi.

Katsayılar YKS'nin yaygın olarak kullanılan yaklaşık ders katsayılarıdır.
Amaç resmî puan üretmek değil, öğrenciye **göreli** bir gelişim ölçüsü
vermektir; ekranda "tahmini" olarak sunulur.
"""
from __future__ import annotations

KATSAYI: dict[str, float] = {
    # TYT
    "TYT-TUR": 3.3,
    "TYT-MAT": 3.3,
    "TYT-GEO": 3.3,
    "TYT-FIZ": 3.4,
    "TYT-KIM": 3.4,
    "TYT-BIO": 3.4,
    "TYT-TAR": 3.4,
    "TYT-COG": 3.4,
    "TYT-FEL": 3.4,
    "TYT-DIN": 3.4,
    # AYT
    "AYT-MAT": 3.0,
    "AYT-GEO": 3.0,
    "AYT-FIZ": 2.85,
    "AYT-KIM": 3.07,
    "AYT-BIO": 3.07,
    "AYT-EDB": 3.0,
    "AYT-TAR1": 2.8,
    "AYT-COG1": 3.0,
    "AYT-TAR2": 2.9,
    "AYT-COG2": 2.9,
    "AYT-FEL": 3.0,
    "AYT-DIN": 3.3,
}


def net_hesapla(dogru: int, yanlis: int) -> float:
    """YKS net kuralı: doğru - (yanlış / 4)."""
    return round(dogru - yanlis / 4, 2)


def puan_tahmini(netler: dict[str, float]) -> dict[str, float]:
    """TYT, AYT ve yerleştirme puanı tahmini (100-500 aralığına sıkıştırılır)."""
    tyt_ham = 100 + sum(
        net * KATSAYI.get(kod, 3.0) for kod, net in netler.items() if kod.startswith("TYT-")
    )
    ayt_ham = 100 + sum(
        net * KATSAYI.get(kod, 3.0) for kod, net in netler.items() if kod.startswith("AYT-")
    )
    tyt = max(100.0, min(500.0, round(tyt_ham, 1)))
    ayt = max(100.0, min(500.0, round(ayt_ham, 1)))
    yerlestirme = round(0.4 * tyt + 0.6 * ayt, 1)
    return {"tyt": tyt, "ayt": ayt, "yerlestirme": yerlestirme}


def deneme_ozeti(sonuclar: list[dict], alan: str) -> dict:
    """Ders satırlarından toplam net, tahmini puan ve zayıf ders listesi üretir.

    ``sonuclar``: [{"ders_kod", "dogru", "yanlis", "bos", "net"}, ...]
    """
    netler = {s["ders_kod"]: float(s["net"]) for s in sonuclar}
    tyt_net = round(sum(n for k, n in netler.items() if k.startswith("TYT-")), 2)
    ayt_net = round(sum(n for k, n in netler.items() if k.startswith("AYT-")), 2)

    # Zayıf ders: net / soru oranı en düşük olanlar (en az 1 yanlış veya boş)
    oranlar = []
    for s in sonuclar:
        toplam = s.get("dogru", 0) + s.get("yanlis", 0) + s.get("bos", 0)
        if toplam <= 0:
            continue
        oranlar.append((s["net"] / toplam, s["ders_kod"]))
    oranlar.sort()
    zayif = [kod for oran, kod in oranlar if oran < 0.6][:4]

    return {
        "netler": netler,
        "toplam_tyt_net": tyt_net,
        "toplam_ayt_net": ayt_net,
        "puan": puan_tahmini(netler),
        "zayif_dersler": zayif,
        "alan": alan,
    }
