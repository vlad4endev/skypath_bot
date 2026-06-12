# Admin React build
FROM node:20-slim AS admin-build
WORKDIR /build
ENV NODE_OPTIONS=--max-old-space-size=512
COPY admin/package.json admin/package-lock.json ./
RUN npm ci
COPY admin/index.html admin/vite.config.ts admin/tsconfig.json admin/tsconfig.node.json ./
COPY admin/src ./src
RUN npm run build

# Web cabinet React build
FROM node:20-slim AS cabinet-build
WORKDIR /build
ENV NODE_OPTIONS=--max-old-space-size=512
COPY cabinet/package.json cabinet/package-lock.json ./
RUN npm ci
COPY cabinet/index.html cabinet/vite.config.ts cabinet/tsconfig.json cabinet/tsconfig.node.json ./
COPY cabinet/public ./public
COPY cabinet/src ./src
RUN npm run build

FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot/ ./bot/
COPY database/ ./database/
COPY alembic/ ./alembic/
COPY scripts/ ./scripts/
COPY data/ ./data/
COPY webapp/ ./webapp/
COPY alembic.ini .

COPY --from=admin-build /build/dist ./admin/dist
COPY --from=cabinet-build /build/dist ./cabinet/dist

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

EXPOSE 8080

CMD ["python", "-m", "bot.main"]
