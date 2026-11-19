# -*- coding: utf-8 -*-
"""YKS Pusula veri modelleri.

Tablo ve alan adlari Turkce tutuldu: uygulama dili Turkce oldugu icin
bakim ve raporlama sirasinda okunabilirlik saglar.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base

# 0 = mezun, digerleri sinif duzeyi
SINIF_MEZUN = 0
ALAN_ETIKET = {
    "sayisal": "Sayısal",
    "ea": "Eşit Ağırlık",
    "sozel": "Sözel",
}
DURUM_ETIKET = {
    "yok": "Başlanmadı",
    "calisiliyor": "Çalışılıyor",
    "tamam": "Tamamlandı",
    "tekrar": "Tekrar Gerekli",
}


class Profil(Base):
    """Öğrenci profili: alan + sınıf seçimi burada tutulur."""

    __tablename__ = "profiller"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ad: Mapped[str] = mapped_column(String(80), default="Öğrenci")
    alan: Mapped[str] = mapped_column(String(16), default="sayisal")
    sinif: Mapped[int] = mapped_column(Integer, default=11)
    hedef_siralama: Mapped[int] = mapped_column(Integer, default=0)
    gunluk_hedef_dk: Mapped[int] = mapped_column(Integer, default=180)
    sinav_tarihi: Mapped[date] = mapped_column(Date, default=date(2028, 6, 17))
    # Gün akışı çerçevesi: okul, uyanış ve yatış saatleri programa yerleşir
    uyanma_saati: Mapped[str] = mapped_column(String(5), default="06:45")
    yatma_saati: Mapped[str] = mapped_column(String(5), default="22:45")
    okul_baslangic: Mapped[str] = mapped_column(String(5), default="08:20")
    okul_bitis: Mapped[str] = mapped_column(String(5), default="15:20")
    # Okuldan eve varış (boş = dönüş süresi otomatik 35 dk)
    okul_donus: Mapped[str] = mapped_column(String(5), default="")
    olusturma: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    @property
    def sinif_etiketi(self) -> str:
        return "Mezun" if self.sinif == SINIF_MEZUN else f"{self.sinif}. sınıf"

    @property
    def alan_etiketi(self) -> str:
        return ALAN_ETIKET.get(self.alan, self.alan)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "ad": self.ad,
            "alan": self.alan,
            "alan_etiketi": self.alan_etiketi,
            "sinif": self.sinif,
            "sinif_etiketi": self.sinif_etiketi,
            "hedef_siralama": self.hedef_siralama,
            "gunluk_hedef_dk": self.gunluk_hedef_dk,
            "sinav_tarihi": self.sinav_tarihi.isoformat() if self.sinav_tarihi else None,
            "uyanma_saati": self.uyanma_saati or "06:45",
            "yatma_saati": self.yatma_saati or "22:45",
            "okul_baslangic": self.okul_baslangic or "08:20",
            "okul_bitis": self.okul_bitis or "15:20",
            "okul_donus": self.okul_donus or "",
        }


class Ders(Base):
    """TYT/AYT dersi. ``alanlar`` virgüllü liste ya da ``ortak``."""

    __tablename__ = "dersler"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kod: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    ad: Mapped[str] = mapped_column(String(80))
    sinav: Mapped[str] = mapped_column(String(8), default="TYT")
    alanlar: Mapped[str] = mapped_column(String(32), default="ortak")
    soru_sayisi: Mapped[int] = mapped_column(Integer, default=0)
    renk: Mapped[str] = mapped_column(String(16), default="#ea580c")
    sira: Mapped[int] = mapped_column(Integer, default=0)

    def to_dict(self) -> dict:
        return {
            "kod": self.kod,
            "ad": self.ad,
            "sinav": self.sinav,
            "alanlar": self.alanlar,
            "soru_sayisi": self.soru_sayisi,
            "renk": self.renk,
            "sira": self.sira,
        }


class Konu(Base):
    """Ders içindeki konu/ünite. ``beceri`` Maarif Modeli beceri kodlarını taşır."""

    __tablename__ = "konular"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kod: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    ders_kod: Mapped[str] = mapped_column(ForeignKey("dersler.kod"), index=True)
    ad: Mapped[str] = mapped_column(String(160))
    sinif: Mapped[int] = mapped_column(Integer, default=11)
    agirlik: Mapped[int] = mapped_column(Integer, default=1)  # 1-3 tahmini soru yoğunluğu
    sure_dk: Mapped[int] = mapped_column(Integer, default=90)
    beceri: Mapped[str] = mapped_column(String(64), default="")  # KB, AB, SD, OK
    onkosul: Mapped[str] = mapped_column(String(64), default="")  # virgüllü konu kodları
    sira: Mapped[int] = mapped_column(Integer, default=0)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kod": self.kod,
            "ders_kod": self.ders_kod,
            "ad": self.ad,
            "sinif": self.sinif,
            "agirlik": self.agirlik,
            "sure_dk": self.sure_dk,
            "beceri": [b for b in self.beceri.split(",") if b],
            "onkosul": [o for o in self.onkosul.split(",") if o],
        }


class KonuDurum(Base):
    """Profilin bir konudaki ilerlemesi ve özgüven seviyesi."""

    __tablename__ = "konu_durumlari"
    __table_args__ = (UniqueConstraint("profil_id", "konu_id", name="uq_profil_konu"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profil_id: Mapped[int] = mapped_column(ForeignKey("profiller.id"), index=True)
    konu_id: Mapped[int] = mapped_column(ForeignKey("konular.id"), index=True)
    durum: Mapped[str] = mapped_column(String(16), default="yok")
    guven: Mapped[int] = mapped_column(Integer, default=0)  # 0-5
    tekrar_sayisi: Mapped[int] = mapped_column(Integer, default=0)
    son_calisma: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    tekrar_tarihi: Mapped[date | None] = mapped_column(Date, nullable=True)


class Deneme(Base):
    """Deneme sınavı başlığı (TYT, AYT veya branş)."""

    __tablename__ = "denemeler"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profil_id: Mapped[int] = mapped_column(ForeignKey("profiller.id"), index=True)
    tur: Mapped[str] = mapped_column(String(16), default="TYT")
    ad: Mapped[str] = mapped_column(String(120), default="")
    tarih: Mapped[date] = mapped_column(Date, default=date.today)
    sure_dk: Mapped[int] = mapped_column(Integer, default=0)
    notlar: Mapped[str] = mapped_column(Text, default="")
    olusturma: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class DenemeSonuc(Base):
    """Denemenin ders bazlı doğru/yanlış/boş satırı."""

    __tablename__ = "deneme_sonuclari"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    deneme_id: Mapped[int] = mapped_column(ForeignKey("denemeler.id"), index=True)
    ders_kod: Mapped[str] = mapped_column(String(16))
    dogru: Mapped[int] = mapped_column(Integer, default=0)
    yanlis: Mapped[int] = mapped_column(Integer, default=0)
    bos: Mapped[int] = mapped_column(Integer, default=0)
    net: Mapped[float] = mapped_column(default=0.0)


class DenemeKonu(Base):
    """Denemede yanlış yapılan konu (konu bazlı deneme analizi).

    Deneme sonuçları ders bazlı tutulur; hangi konudan yanlış geldiği burada
    işaretlenir. Konu başarısı çalışma günlüğüyle birleşince "açık konu"
    tablosu ders kırılımından bağımsız olarak çıkar.
    """

    __tablename__ = "deneme_konulari"
    __table_args__ = (UniqueConstraint("deneme_id", "konu_id", name="uq_deneme_konu"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    deneme_id: Mapped[int] = mapped_column(ForeignKey("denemeler.id"), index=True)
    konu_id: Mapped[int] = mapped_column(ForeignKey("konular.id"), index=True)
    ders_kod: Mapped[str] = mapped_column(String(16), default="")
    yanlis: Mapped[int] = mapped_column(Integer, default=1)


class Calisma(Base):
    """Çalışma günlüğü kaydı (konu/soru/tekrar/deneme)."""

    __tablename__ = "calismalar"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profil_id: Mapped[int] = mapped_column(ForeignKey("profiller.id"), index=True)
    konu_id: Mapped[int | None] = mapped_column(ForeignKey("konular.id"), nullable=True)
    tarih: Mapped[date] = mapped_column(Date, default=date.today, index=True)
    tur: Mapped[str] = mapped_column(String(16), default="konu")
    sure_dk: Mapped[int] = mapped_column(Integer, default=0)
    dogru: Mapped[int] = mapped_column(Integer, default=0)
    yanlis: Mapped[int] = mapped_column(Integer, default=0)
    notlar: Mapped[str] = mapped_column(Text, default="")


class PlanItem(Base):
    """Günlük çalışma planı maddesi."""

    __tablename__ = "plan_maddeleri"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profil_id: Mapped[int] = mapped_column(ForeignKey("profiller.id"), index=True)
    tarih: Mapped[date] = mapped_column(Date, default=date.today, index=True)
    ders_kod: Mapped[str] = mapped_column(String(16), default="")
    konu_id: Mapped[int | None] = mapped_column(ForeignKey("konular.id"), nullable=True)
    baslik: Mapped[str] = mapped_column(String(200), default="")
    tur: Mapped[str] = mapped_column(String(16), default="konu")  # konu|soru|tekrar|deneme
    sure_dk: Mapped[int] = mapped_column(Integer, default=45)
    durum: Mapped[str] = mapped_column(String(16), default="bekliyor")
    sira: Mapped[int] = mapped_column(Integer, default=0)
    # Gün akışındaki saat (HH:MM); planı üreten servis doldurur
    baslangic: Mapped[str] = mapped_column(String(5), default="")


class AiMesaj(Base):
    """Yapay zeka koç sohbet geçmişi."""

    __tablename__ = "ai_mesajlari"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profil_id: Mapped[int] = mapped_column(ForeignKey("profiller.id"), index=True)
    rol: Mapped[str] = mapped_column(String(16), default="kullanici")  # kullanici|koc
    icerik: Mapped[str] = mapped_column(Text)
    kaynak: Mapped[str] = mapped_column(String(16), default="yerel")  # yerel|gemini
    olusturma: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Ayar(Base):
    """Uygulama ayarları (ör. panelden girilen Gemini anahtarı)."""

    __tablename__ = "ayarlar"

    anahtar: Mapped[str] = mapped_column(String(64), primary_key=True)
    deger: Mapped[str] = mapped_column(Text, default="")
