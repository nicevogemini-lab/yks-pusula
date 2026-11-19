# -*- coding: utf-8 -*-
"""Veritabani baglantisi ve oturum yonetimi.

Varsayilan olarak proje icindeki ``veri/pusula.db`` SQLite dosyasi kullanilir.
``PUSULA_DATABASE_URL`` doluysa (ornegin Neon PostgreSQL) bulut veritabani
kullanilir; bu durumda yerel dosya yedegi olmadigi icin ``DB_YOLU`` bostur.
``PUSULA_DB`` yalnizca SQLite dosyasinin yolunu degistirir.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

VERI_DIR = BASE_DIR / "veri"
VERI_DIR.mkdir(parents=True, exist_ok=True)


def surucu_url(ham: str) -> str:
    """libpq/Neon adresini SQLAlchemy + psycopg surucusune uyarlar.

    Neon panosu ``postgresql://...`` verir; SQLAlchemy'de surucu adi acikca
    yazilmalidir, aksi halde psycopg2 aranir.
    """
    if ham.startswith("postgres://"):
        return ham.replace("postgres://", "postgresql+psycopg://", 1)
    if ham.startswith("postgresql://"):
        return ham.replace("postgresql://", "postgresql+psycopg://", 1)
    return ham


_bulut_url = os.getenv("PUSULA_DATABASE_URL", "").strip()
if _bulut_url:
    DATABASE_URL = surucu_url(_bulut_url)
    DB_YOLU: Path | None = None  # bulutta indirilecek dosya yok
    engine = create_engine(
        DATABASE_URL,
        # Neon bos oturumlari kapatir: bayat baglanti kullanilmadan once yoklanir
        pool_pre_ping=True,
        pool_recycle=300,
        future=True,
    )
else:
    _db_yolu = Path(os.getenv("PUSULA_DB", "veri/pusula.db"))
    if not _db_yolu.is_absolute():
        _db_yolu = BASE_DIR / _db_yolu
    _db_yolu.parent.mkdir(parents=True, exist_ok=True)
    DATABASE_URL = f"sqlite:///{_db_yolu.as_posix()}"
    DB_YOLU = _db_yolu
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        future=True,
    )

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Tum tablolarin ortak tabani."""


def get_db():
    """FastAPI bagimliligi: istek basina oturum acar, is bitince kapatir."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
