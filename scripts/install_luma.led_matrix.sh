#!/bin/bash

# instructions from https://luma-led-matrix.readthedocs.io/en/latest/install.html and the 
# instructions for raspi-config command line from https://github.com/glennklockwood/rpi-ansible/blob/master/roles/common/tasks/raspi-config.yml

sudo apt install -y python3 python3-pip build-essential python3-dev libfreetype6-dev libjpeg-dev libopenjp2-7 libtiff5
sudo raspi-config nonint do_spi 0 
sudo pip3 install --upgrade luma.led_matrix

