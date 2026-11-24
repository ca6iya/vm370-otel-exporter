# Multi-arch image. Build for the host architecture where Dockhand deploys.
FROM python:3.12-slim-bookworm

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY examples/cp-sample.txt ./examples/cp-sample.txt
COPY docker/entrypoint.sh /entrypoint.sh

RUN pip install --no-cache-dir . \
    && chmod 755 /entrypoint.sh \
    && mkdir -p /data

ENV VM370_TEXT=/data/cp.txt
VOLUME ["/data"]
EXPOSE 9370

ENTRYPOINT ["/entrypoint.sh"]
