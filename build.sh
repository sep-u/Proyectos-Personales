#!/usr/bin/env bash
# Lo ejecuta Render en cada despliegue. -e: si un paso falla, se detiene.
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate
