FROM python:3.14-slim AS gate
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

FROM node:24-slim AS node

FROM gate AS agent
ARG CLAUDE_CODE_VERSION
USER root
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && npm install -g "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}" \
    && claude --version \
    && printf '%s\n' '#!/bin/sh' 'set -e' 'python -m venv --copies --system-site-packages /work/.venv' 'rm -f /work/.venv/lib64' 'exec claude "$@"' \
        > /usr/local/bin/agent-entry \
    && chmod 755 /usr/local/bin/agent-entry
USER gate
ENTRYPOINT ["/usr/local/bin/agent-entry"]
