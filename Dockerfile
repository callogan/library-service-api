FROM python:3.11.2-slim-buster
LABEL maintainer="callogan217@gmail.com"

ENV PYTHONUNBUFFERED 1

WORKDIR app/

COPY requirements.txt requirements.txt
RUN pip install debugpy

RUN apt-get update \
    && apt-get -y install libpq-dev gcc

RUN pip install -r requirements.txt

COPY . .

RUN mkdir -p /vol/web/media

RUN adduser \
    --disabled-password \
    --no-create-home \
    django-user

RUN chown -R django-user:django-user /vol/
RUN chown -R 755 /vol/web/

USER django-user

CMD ["sh", "-c", "python -m debugpy --wait-for-client --listen 0.0.0.0:5678 -m celery -A tasks worker -l info -P eventlet"]
