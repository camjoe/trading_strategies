FROM python:3.14-slim
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONDONTWRITEBYTECODE=1
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && apt-get clean \
    && find /var/lib/apt/lists -type f -delete
RUN git config --system --add safe.directory /work
COPY requirements-base.txt requirements-dev.txt /opt/req/
RUN pip install -r /opt/req/requirements-dev.txt
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin gate
USER gate
WORKDIR /work
