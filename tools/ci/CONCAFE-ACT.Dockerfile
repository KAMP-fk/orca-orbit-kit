FROM node:24-trixie

# CI's shell-based gate tests use jq. Node is in /usr/local/bin so JavaScript
# actions can still reach it after pnpm/action-setup updates act's PATH.
RUN apt-get update \
    && apt-get install -y --no-install-recommends jq \
    && rm -rf /var/lib/apt/lists/*
