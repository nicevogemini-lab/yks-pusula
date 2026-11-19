# YKS Pusula - bulut (Neon) yayini icin imaj
#
# Yerel dosya veritabani yerine Neon PostgreSQL kullanilir:
#   PUSULA_DATABASE_URL  -> postgresql://...  (Space/panel gizli degiskeni)
#   PUSULA_SIFRE         -> giris kodu
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PUSULA_PORT=7860

WORKDIR /uygulama

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY web ./web
COPY baslat.py ./

# Render PORT degiskenini kendisi verir; baska yerlerde 7860'a duser
EXPOSE 7860
CMD ["sh", "-c", "python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
