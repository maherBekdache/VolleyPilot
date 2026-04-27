#!/bin/sh
set -eu

cd /app

python manage.py migrate --noinput

if [ "${VOLLEYPILOT_AUTO_SEED:-true}" = "true" ]; then
  python manage.py shell -c "from django.contrib.auth import get_user_model; raise SystemExit(0 if get_user_model().objects.exists() else 1)" >/dev/null 2>&1 || python manage.py seed_data
fi

exec "$@"
