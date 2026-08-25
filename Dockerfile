FROM python:3.11-slim

# libreoffice-calc (so o Calc, nao o pacote completo com Writer/Impress) e
# usado pra converter .xlsb -> .xlsx no upload, preservando cor de
# fundo/formatacao (que o motor usa pra detectar a versao em teste) —
# a biblioteca Python de leitura de .xlsb (pyxlsb) so extrai valores, sem
# formatacao nenhuma.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-calc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV MODELER_COOKIE_SECURE=true

CMD ["python", "backend/servidor.py"]
