FROM python:3.12.11-alpine3.22

ARG ODUPILOT_BRIDGE_VERSION=unknown

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ODUPILOT_BRIDGE_VERSION=${ODUPILOT_BRIDGE_VERSION}

RUN apk add --no-cache curl git \
    && addgroup -S -g 1000 bridge \
    && adduser -S -D -u 1000 -G bridge bridge
WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY bridge.py smoke.sh /app/
USER bridge:bridge

CMD ["python", "/app/bridge.py"]
