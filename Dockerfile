FROM python:3.13-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY config ./config
RUN python -m pip install --no-cache-dir .

RUN useradd --create-home --uid 10001 deliveryqc
USER deliveryqc

ENTRYPOINT ["delivery-qc", "--workspace", "/data", "--config", "/app/config/qc.toml"]
CMD ["--help"]
