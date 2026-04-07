# syntax=docker/dockerfile:1.7

# Extends OpenClaw with Python 3.12 + Denario scientific research stack.
# No OpenClaw extensions needed — Denario connects via MCP server.

ARG OPENCLAW_VARIANT=default
ARG OPENCLAW_NODE_BOOKWORM_IMAGE="node:24-bookworm@sha256:3a09aa6354567619221ef6c45a5051b671f953f0a1924d1f819ffb236e520e6b"
ARG OPENCLAW_NODE_BOOKWORM_DIGEST="sha256:3a09aa6354567619221ef6c45a5051b671f953f0a1924d1f819ffb236e520e6b"
ARG OPENCLAW_NODE_BOOKWORM_SLIM_IMAGE="node:24-bookworm-slim@sha256:e8e2e91b1378f83c5b2dd15f0247f34110e2fe895f6ca7719dbb780f929368eb"
ARG OPENCLAW_NODE_BOOKWORM_SLIM_DIGEST="sha256:e8e2e91b1378f83c5b2dd15f0247f34110e2fe895f6ca7719dbb780f929368eb"

# ── Stage 1: ext-deps (no extensions needed for denario) ─────
FROM ${OPENCLAW_NODE_BOOKWORM_IMAGE} AS ext-deps
RUN mkdir -p /out

# ── Stage 2: Build OpenClaw ──────────────────────────────────
FROM ${OPENCLAW_NODE_BOOKWORM_IMAGE} AS build
RUN set -eux; \
    for attempt in 1 2 3 4 5; do \
      if curl --retry 5 --retry-all-errors --retry-delay 2 -fsSL https://bun.sh/install | bash; then \
        break; \
      fi; \
      if [ "$attempt" -eq 5 ]; then exit 1; fi; \
      sleep $((attempt * 2)); \
    done
ENV PATH="/root/.bun/bin:${PATH}"
RUN corepack enable
WORKDIR /app
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml .npmrc ./
COPY ui/package.json ./ui/package.json
COPY patches ./patches
COPY scripts ./scripts
COPY --from=ext-deps /out/ ./extensions/
RUN --mount=type=cache,id=openclaw-pnpm-store,target=/root/.local/share/pnpm/store,sharing=locked \
    NODE_OPTIONS=--max-old-space-size=2048 pnpm install --frozen-lockfile
COPY . .
RUN for dir in /app/extensions /app/.agent /app/.agents; do \
      if [ -d "$dir" ]; then \
        find "$dir" -type d -exec chmod 755 {} +; \
        find "$dir" -type f -exec chmod 644 {} +; \
      fi; \
    done
RUN pnpm canvas:a2ui:bundle || \
    (echo "A2UI bundle: creating stub (non-fatal)" && \
     mkdir -p src/canvas-host/a2ui && \
     echo "/* A2UI bundle unavailable */" > src/canvas-host/a2ui/a2ui.bundle.js && \
     echo "stub" > src/canvas-host/a2ui/.bundle.hash && \
     rm -rf vendor/a2ui apps/shared/OpenClawKit/Tools/CanvasA2UI)
RUN pnpm build:docker
ENV OPENCLAW_PREFER_PNPM=1
RUN pnpm ui:build

# ── Stage 3: Runtime assets ──────────────────────────────────
FROM build AS runtime-assets
RUN CI=true pnpm prune --prod && \
    find dist -type f \( -name '*.d.ts' -o -name '*.d.mts' -o -name '*.d.cts' -o -name '*.map' \) -delete

# ── Stage 4: Python 3.12 + Denario + cmbagent + ag2 ─────────
FROM python:3.12-bookworm AS python-env

# Copy local source repos (via docker-compose additional_contexts)
COPY --from=ag2-src . /tmp/ag2/
COPY --from=cmbagent-src . /tmp/cmbagent/
COPY --from=denario-src . /tmp/denario/

RUN python3.12 -m venv /opt/denario-venv && \
    /opt/denario-venv/bin/pip install --upgrade pip

# Install ag2 (cmbagent_autogen) from local source first
RUN /opt/denario-venv/bin/pip install /tmp/ag2/

# Install cmbagent from local source (uses cmbagent_autogen already installed)
RUN /opt/denario-venv/bin/pip install /tmp/cmbagent/

# Install Denario from local source (uses cmbagent already installed)
RUN /opt/denario-venv/bin/pip install /tmp/denario/

# Install MCP server dependency + scientific packages
RUN /opt/denario-venv/bin/pip install \
      mcp \
      numpy \
      scipy \
      matplotlib \
      pandas \
      sympy \
      scikit-learn \
      slack_bolt \
      beautifulsoup4

# Clean up source copies
RUN rm -rf /tmp/ag2 /tmp/cmbagent /tmp/denario

# ── Stage 5: Runtime base ────────────────────────────────────
FROM ${OPENCLAW_NODE_BOOKWORM_IMAGE} AS base-default
FROM ${OPENCLAW_NODE_BOOKWORM_SLIM_IMAGE} AS base-slim

# ── Stage 6: Final image ─────────────────────────────────────
FROM base-${OPENCLAW_VARIANT}
ARG OPENCLAW_VARIANT

WORKDIR /app

RUN --mount=type=cache,id=denario-apt-cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,id=denario-apt-lists,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get upgrade -y --no-install-recommends && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      procps hostname curl git lsof openssl libopenblas0 liblapack3 \
      texlive-latex-recommended texlive-latex-extra texlive-fonts-recommended \
      texlive-xetex texlive-science latexmk cm-super && \
    curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
      | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
      > /etc/apt/sources.list.d/github-cli.list && \
    apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends gh

# Copy Python 3.12 install + pre-built venv from python stage
COPY --from=python-env /usr/local/bin/python3.12 /usr/local/bin/python3.12
COPY --from=python-env /usr/local/lib/python3.12 /usr/local/lib/python3.12
COPY --from=python-env /usr/local/lib/libpython3.12.so* /usr/local/lib/
COPY --from=python-env /opt/denario-venv /opt/denario-venv
RUN ldconfig && chown -R node:node /opt/denario-venv

RUN chown node:node /app

COPY --from=runtime-assets --chown=node:node /app/dist ./dist
COPY --from=runtime-assets --chown=node:node /app/node_modules ./node_modules
COPY --from=runtime-assets --chown=node:node /app/package.json .
COPY --from=runtime-assets --chown=node:node /app/openclaw.mjs .
COPY --from=runtime-assets --chown=node:node /app/extensions ./extensions
# Skip skills — not needed for research scientists
RUN mkdir -p /app/skills
COPY --from=runtime-assets --chown=node:node /app/docs ./docs

ENV OPENCLAW_BUNDLED_PLUGINS_DIR=/app/extensions
ENV COREPACK_HOME=/usr/local/share/corepack
RUN install -d -m 0755 "$COREPACK_HOME" && \
    corepack enable && \
    for attempt in 1 2 3 4 5; do \
      if corepack prepare "$(node -p "require('./package.json').packageManager")" --activate; then \
        break; \
      fi; \
      if [ "$attempt" -eq 5 ]; then exit 1; fi; \
      sleep $((attempt * 2)); \
    done && \
    chmod -R a+rX "$COREPACK_HOME"

RUN ln -sf /app/openclaw.mjs /usr/local/bin/openclaw \
 && chmod 755 /app/openclaw.mjs

ENV NODE_ENV=production
ENV DENARIO_PYTHON_PATH=/opt/denario-venv/bin/python
ENV PATH="/opt/denario-venv/bin:${PATH}"

USER node

HEALTHCHECK --interval=3m --timeout=10s --start-period=15s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:18789/healthz').then((r)=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node", "openclaw.mjs", "gateway", "--allow-unconfigured"]
