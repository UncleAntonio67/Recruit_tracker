FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Allow selecting which requirements file to install at build time.
# Example: docker build --build-arg REQUIREMENTS=requirements-postgres.txt ...
ARG REQUIREMENTS=requirements.txt

COPY requirements*.txt /app/
RUN pip install --no-cache-dir -r /app/${REQUIREMENTS}

COPY . /app

ENV PORT=8080
EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
