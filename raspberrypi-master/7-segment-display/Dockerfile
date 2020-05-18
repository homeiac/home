FROM python:3.8.3

RUN pip3 install fauxmo luma.led_matrix netifaces

COPY . /usr/src/app/

WORKDIR /usr/src/app/

CMD ["fauxmo","-c","config.json"]

