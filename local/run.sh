#!/bin/sh
# Start one service in the local stack: load what bootstrap generated,
# migrate its database if it has one, then serve.
set -eu
SERVICE="$1"
set -a
. /run/cappy/local.env
set +a
# Each consumer reads its own queue: CATALOG_QUEUE_URL for catalog, and so on.
EVENT_QUEUE_URL="$(printenv "$(echo "$SERVICE" | tr a-z A-Z)_QUEUE_URL" || true)"
export EVENT_QUEUE_URL
if python -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('$SERVICE.migrations') else 1)"; then
  python -m cappy_common.migrations "$SERVICE"
fi
exec uvicorn --factory "$SERVICE.main:create" --host 0.0.0.0 --port 8000 --no-server-header
