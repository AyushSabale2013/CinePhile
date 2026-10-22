# Build the React UI first, then ship its static assets with the Flask API.
FROM node:22-alpine AS frontend-build
WORKDIR /srv/frontend
COPY frontend/package.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
COPY --from=frontend-build /srv/app/static/react /srv/app/static/react
RUN sed -i 's/\r$//' entrypoint.sh && chmod +x entrypoint.sh && useradd --create-home cinephile && chown -R cinephile /srv
USER cinephile
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')"
ENTRYPOINT ["./entrypoint.sh"]
