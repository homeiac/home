#!/usr/bin/env bash
# Verify the pinned deployment image actually provides the POSIX tools it uses.
set -euo pipefail
endpoint=$(docker context inspect --format '{{.Endpoints.docker.Host}}')
config=$(mktemp -d)
trap 'rm -rf "$config"' EXIT
# This public image needs no registry login; isolate a broken desktop helper.
DOCKER_CONFIG="$config" docker -H "$endpoint" run --rm --network none --entrypoint /bin/sh \
  alpine/git:v2.49.1@sha256:c0280cf9572316299b08544065d3bf35db65043d5e3963982ec50647d2746e26 \
  -ec 'command -v sh; command -v ssh; command -v tar; ssh -V'
