FROM python:3.11

WORKDIR /code

COPY python/env/requirements.txt .

RUN pip install -r requirements.txt

COPY python/env/manualclassify .
