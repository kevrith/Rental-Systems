FROM python:3.12-slim

WORKDIR /app

# deb.debian.org and pypi.org both resolve to IPv6 first on many networks;
# where IPv6 has no real route each fetch stalls until it times out, per
# package — sometimes a full package succeeds and the next one on the same
# host fails, which is what makes this look like a flaky package rather than
# a routing problem (seen directly: this exact build failed for one line of
# requirements.txt while every other line above it succeeded).
# `Acquire::ForceIPv4` only ever covered apt; `gai.conf`'s precedence rule
# covers every tool that resolves through glibc — apt, pip, and anything
# else — which is the fix this needed all along, apt was just the first
# symptom anyone hit.
RUN printf 'Acquire::ForceIPv4 "true";\n' > /etc/apt/apt.conf.d/99force-ipv4 \
    && printf 'precedence ::ffff:0:0/96 100\n' >> /etc/gai.conf

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
# A slow or flaky link to PyPI (common on a residential/CGNAT connection
# fetching ~30 packages including a couple of large binary wheels) makes pip
# report a version as nonexistent when it only failed to list it in time.
# Retries and a longer per-request timeout turn a transient stall into a
# retry instead of a hard failure.
RUN pip install --no-cache-dir --retries 10 --timeout 120 -r requirements.txt

COPY . .

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=5 \
    CMD curl -fsS "http://localhost:${PORT:-8000}/api/v1/health" || exit 1

# Shell form, and `${PORT:-8000}` rather than a literal, because a PaaS assigns
# the port at run time and expects the process to bind whatever it was given.
# Locally PORT is unset, so this is still 8000 and docker-compose is unchanged.
CMD exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
