FROM arm32v7/python:3.7-slim-buster

RUN mkdir -p /app && \
    apt-get update -y && \
    apt-get install -y build-essential && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY door-api /app

RUN pip3 install -r requirements.txt --no-cache-dir

ENTRYPOINT ["python3", "api.py"]
