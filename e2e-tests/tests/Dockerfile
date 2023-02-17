FROM ubuntu:22.04
#FROM python:3.10-bullseye

RUN apt-get update -y
RUN apt-get install -y python3 python3-pip wget
RUN bash -c 'wget -qO- https://get.docker.com | bash'
RUN cd /tmp && wget https://github.com/Yelp/dumb-init/releases/download/v1.2.5/dumb-init_1.2.5_amd64.deb
RUN apt-get install /tmp/dumb-init_1.2.5_amd64.deb
RUN bash -c 'wget -qO- https://www.mongodb.org/static/pgp/server-6.0.asc | apt-key add -'
RUN echo "deb [ arch=amd64,arm64 ] https://repo.mongodb.org/apt/ubuntu focal/mongodb-org/6.0 multiverse" | tee /etc/apt/sources.list.d/mongodb-org-6.0.list
RUN apt-get update -y
RUN apt-get install -y mongodb-org-tools

COPY .temp /tmp
ARG WHEEL_FN=
RUN pip install /tmp/${WHEEL_FN}

WORKDIR /test
COPY src/requirements.txt /test/requirements.txt
RUN pip install -r requirements.txt
COPY src .key.json wait-for-it.sh /test
