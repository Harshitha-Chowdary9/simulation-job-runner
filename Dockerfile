# NOTE: configuration only - not built/run in the development environment
# (no Docker runtime available there). The verified run path is the README's
# local setup plus scripts/demo.py.
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src ./src
ENV PYTHONPATH=/app/src
CMD ["uvicorn", "simrunner.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
