FROM python:3.13.1

ENV PYTHONUNBUFFERED 1

RUN apt update

RUN mkdir /app
WORKDIR /app
COPY requirements.txt /app/

RUN pip install -r requirements.txt

COPY . /app/