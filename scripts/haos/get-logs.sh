#!/bin/bash
# Get HA logs
source "$(dirname "$0")/../lib-sh/ha-api.sh"

TARGET="${1:-core}"
case "$TARGET" in
    host) ha_api_get "hassio/host/logs" ;;
    core) ha_api_get "hassio/core/logs" ;;
    *) ha_api_get "hassio/addons/$TARGET/logs" ;;
esac
