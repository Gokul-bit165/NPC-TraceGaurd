FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt backend/
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ backend/
COPY --from=web /web/dist frontend/dist
WORKDIR /app/backend
ENV TRACEGUARD_DB=sqlite:////data/traceguard.db
EXPOSE 8000
CMD ["sh", "-c", "python -m app.seed --reset && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
