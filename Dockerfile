FROM python:slim

RUN useradd annex

WORKDIR /home/annex

RUN apt-get update \
    && apt-get install -y build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements.txt
RUN python -m venv venv
RUN venv/bin/pip install -r requirements.txt
RUN venv/bin/pip install gunicorn pymysql cryptography

COPY app app
COPY migrations migrations
COPY annex.py config.py boot.sh ./
RUN chmod a+x boot.sh

ENV FLASK_APP annex.py

RUN chown -R annex:annex ./
USER annex

EXPOSE 5000
ENTRYPOINT ["./boot.sh"]