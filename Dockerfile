FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN useradd --create-home --uid 10002 app && mkdir /data && chown app /data
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
RUN DJANGO_SECRET_KEY=build-only python manage.py collectstatic --noinput >/dev/null && chown -R app /app
USER app
ENV DJANGO_DB_PATH=/data/db.sqlite3
EXPOSE 8000
# Apply migrations, then serve. Put a proxy in front for TLS; the app lives under /todolist/.
CMD ["sh", "-c", "python manage.py migrate --noinput && exec gunicorn mysite.wsgi:application --bind 0.0.0.0:8000 --workers 2 --forwarded-allow-ips='*' --access-logfile -"]
