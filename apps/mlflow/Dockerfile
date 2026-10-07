# syntax=docker/dockerfile:1
FROM python:3.13-slim AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
COPY requirements.txt .
RUN python -m venv /venv && /venv/bin/pip install -r requirements.txt

FROM python:3.13-slim
ARG RELEASE=dev
ENV PATH=/venv/bin:$PATH PYTHONUNBUFFERED=1 MLFLOW_DISABLE_AGENT_HINT=1
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin mlflow
COPY --from=build /venv /venv
RUN rm -rf /usr/local/lib/python3.13/site-packages/pip* /usr/local/bin/pip* \
           /venv/lib/python3.13/site-packages/pip* /venv/bin/pip*
USER 10001
EXPOSE 5000
ENTRYPOINT ["mlflow", "server"]
