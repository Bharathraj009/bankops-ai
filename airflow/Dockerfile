FROM python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159 AS build
WORKDIR /build
COPY requirements.txt requirements-airflow.txt requirements-runtime.lock security-requirements.txt /tmp/bankops/
RUN python -m venv /opt/venv \
    && /opt/venv/bin/python -m pip install --no-cache-dir pip==26.2.2 \
    && /opt/venv/bin/python -m pip install --no-cache-dir \
       -r /tmp/bankops/requirements-airflow.txt apache-airflow-providers-standard==1.19.0 \
       -c /tmp/bankops/requirements-runtime.lock -c /tmp/bankops/security-requirements.txt \
    && /opt/venv/bin/python -m pip check

FROM python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH \
    AIRFLOW_HOME=/opt/airflow \
    AIRFLOW_USER_HOME_DIR=/home/airflow \
    AIRFLOW__CORE__LOAD_EXAMPLES=False \
    PYTHONPATH=/opt/bankops
RUN apt-get update && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends tini \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 50000 --gid 0 airflow \
    && mkdir -p /opt/airflow/local-auth /opt/airflow/logs /opt/airflow/dags \
    && chown -R airflow:0 /opt/airflow \
    && chmod 770 /opt/airflow/local-auth
COPY --from=build /opt/venv /opt/venv
COPY runtime/remove_build_tools.py /tmp/remove_build_tools.py
RUN python /tmp/remove_build_tools.py && rm /tmp/remove_build_tools.py
WORKDIR /opt/airflow
USER airflow
COPY reconciliation /opt/bankops/reconciliation
COPY dags /opt/airflow/dags
COPY runtime/start.py /opt/bankops/start.py
ENTRYPOINT ["/usr/bin/tini", "-g", "--"]
CMD ["python", "/opt/bankops/start.py"]
