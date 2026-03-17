# Stage 1: Build frontend
FROM node:20-alpine AS frontend
WORKDIR /app/web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN STATIC_EXPORT=1 npm run build

# Stage 2: Python API server
FROM python:3.11-slim
WORKDIR /app

RUN pip install uv
COPY pyproject.toml ./
COPY cortex/ cortex/
RUN uv pip install --system .

COPY --from=frontend /app/web/out web/out/

EXPOSE 9400
CMD ["uvicorn", "cortex.api:app", "--host", "0.0.0.0", "--port", "9400"]
