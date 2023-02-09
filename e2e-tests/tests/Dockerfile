FROM ubuntu:22.04
#FROM python:3.10-bullseye

RUN apt-get update -y && apt-get upgrade -y 
RUN apt-get install -y python3 python3-pip wget
# RUN apt-get install -y wget
RUN bash -c 'wget -qO- https://get.docker.com | bash'
RUN cd /tmp && wget https://github.com/Yelp/dumb-init/releases/download/v1.2.5/dumb-init_1.2.5_amd64.deb
RUN dpkg -i /tmp/dumb-init_1.2.5_amd64.deb

COPY .temp /tmp
RUN ls -lha /tmp
ARG WHEEL_FN=
RUN pip install /tmp/${WHEEL_FN}

WORKDIR /test
COPY src /test
RUN pip install -r requirements.txt
