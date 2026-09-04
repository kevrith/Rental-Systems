FROM python:3.12-slim

WORKDIR /app

# deb.debian.org resolves to IPv6 first on many networks; where IPv6 has no real
# route the fetch stalls until it times out, per package. Forcing IPv4 turns a
# ~40 minute build into a couple of minutes.
RUN printf 'Acquire::ForceIPv4 "true";\n' > /etc/apt/apt.conf.d/99force-ipv4

# WeasyPrint renders the lease, invoice and receipt PDFs and needs the pango /
# cairo stack at runtime; fonts-dejavu-core is the typeface the templates ask
# for. No compiler is installed: psycopg2-binary and asyncpg both ship manylinux
# wheels, so gcc and libpq-dev would only add ~60 packages of build tooling that
# never gets used.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libharfbuzz0b \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libffi8 \
    shared-mime-info \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=5 \
    CMD curl -fsS http://localhost:8000/api/v1/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
