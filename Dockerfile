FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY src src

ENV UVICORN_PORT=80
ENV UVICORN_HOST=0.0.0.0

ENTRYPOINT [ "uvicorn" ]
CMD [ "src.api:app" ]