FROM balenalib/raspberry-pi-python:3.7.5

RUN mkdir -p /app && \
    apt-get update -y && \
    apt-get install -y build-essential && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY camera /app

RUN READTHEDOCS=True pip3 install -r requirements.txt --no-cache-dir

CMD ["python3", "stream.py"]
