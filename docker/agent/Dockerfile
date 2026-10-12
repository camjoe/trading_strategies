ARG BASE
FROM node:24-slim AS node
FROM ${BASE}
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
