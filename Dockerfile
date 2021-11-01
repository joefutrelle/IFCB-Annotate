FROM python

COPY python/env/requirements.txt .

RUN pip install -r requirements.txt

WORKDIR /code