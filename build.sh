#!/usr/bin/env bash
# Render runs this on every deploy (Build Command: bash build.sh). See "Deployment" in README.md.
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate --no-input
# Table for the failed-login counter (SCRUM-22); does nothing if it already exists.
python manage.py createcachetable
