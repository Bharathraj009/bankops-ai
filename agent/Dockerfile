FROM python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159 AS build

WORKDIR /build
RUN python -m venv /opt/venv
COPY requirements.lock pyproject.toml ./
COPY src ./src
RUN /opt/venv/bin/python -m pip install --no-cache-dir pip==26.2.2 \
    && /opt/venv/bin/python -m pip install --no-cache-dir -r requirements.lock \
    && /opt/venv/bin/python -m pip install --no-cache-dir --no-deps . \
    && /opt/venv/bin/python -m pip check \
    && /opt/venv/bin/python -m pip uninstall -y pip setuptools wheel

FROM python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BANKOPS_AGENT_HOST=0.0.0.0 \
    PATH=/opt/venv/bin:$PATH

WORKDIR /app
RUN apt-get update && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip uninstall -y pip setuptools wheel \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/state && chown agent:agent /home/agent/state
COPY --from=build /opt/venv /opt/venv

USER agent
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('BANKOPS_AGENT_PORT','8000')+'/health',timeout=3)"
CMD ["bankops-agent"]
