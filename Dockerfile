FROM python

WORKDIR /code

COPY python/env/manualclassify .
COPY python/env/requirements.txt .

RUN pip install -r requirements.txt
