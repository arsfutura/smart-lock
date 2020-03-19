FROM python:3.7-slim-buster

RUN mkdir -p /app && \
    apt-get update -y && \
    apt-get install -y build-essential python3-dev libsm6 libxext6 libxrender-dev libglib2.0-0 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR app

COPY data-collector /app/data-collector
COPY util /app/util

RUN pip3 install -r data-collector/requirements.txt --no-cache-dir

ENTRYPOINT ["python3", "-m", "data-collector.collector"]
