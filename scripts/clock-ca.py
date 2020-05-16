#!/usr/bin/env python3

# code modified, tweaked and tailored from code by bertwert 
# on RPi forum thread topic 91796

import RPi.GPIO as GPIO
import time

# GPIO ports for the 7seg pins
# 7seg_segment_pins (11, 7, 4, 2, 1, 10, 5, 3) +  resistor inline

segments = (11, 4, 23, 8, 7, 10, 18, 25)

# GPIO ports for the digit 0-3 pins 
# 7seg_digit_pins (12, 9, 8, 6) digits 0-3 respectively

digits = (22, 27, 17, 24)

# Confusingly,
#   HIGH = Segment OFF
#   LOW  = Segment ON

num = {
    ' ': (GPIO.HIGH, GPIO.HIGH, GPIO.HIGH, GPIO.HIGH, GPIO.HIGH, GPIO.HIGH, GPIO.HIGH),
    '0': (GPIO.LOW,  GPIO.LOW,  GPIO.LOW,  GPIO.LOW,  GPIO.LOW,  GPIO.LOW,  GPIO.HIGH),
    '1': (GPIO.HIGH, GPIO.LOW,  GPIO.LOW,  GPIO.HIGH, GPIO.HIGH, GPIO.HIGH, GPIO.HIGH),
    '2': (GPIO.LOW,  GPIO.LOW,  GPIO.HIGH, GPIO.LOW,  GPIO.LOW,  GPIO.HIGH, GPIO.LOW),
    '3': (GPIO.LOW,  GPIO.LOW,  GPIO.LOW,  GPIO.LOW,  GPIO.HIGH, GPIO.HIGH, GPIO.LOW),
    '4': (GPIO.HIGH, GPIO.LOW,  GPIO.LOW,  GPIO.HIGH, GPIO.HIGH, GPIO.LOW,  GPIO.LOW),
    '5': (GPIO.LOW,  GPIO.HIGH, GPIO.LOW,  GPIO.LOW,  GPIO.HIGH, GPIO.LOW,  GPIO.LOW),
    '6': (GPIO.LOW,  GPIO.HIGH, GPIO.LOW,  GPIO.LOW,  GPIO.LOW,  GPIO.LOW,  GPIO.LOW),
    '7': (GPIO.LOW,  GPIO.LOW,  GPIO.LOW,  GPIO.HIGH, GPIO.HIGH, GPIO.HIGH, GPIO.HIGH),
    '8': (GPIO.LOW,  GPIO.LOW,  GPIO.LOW,  GPIO.LOW,  GPIO.LOW,  GPIO.LOW,  GPIO.LOW),
    '9': (GPIO.LOW,  GPIO.LOW,  GPIO.LOW,  GPIO.LOW,  GPIO.HIGH, GPIO.LOW,  GPIO.LOW)
}
 
# Strobe a select pin high

def strobe_high(pin):
    GPIO.output(pin, GPIO.HIGH)
    time.sleep(0.001)
    GPIO.output(pin, GPIO.LOW)


# Initialise the GPIO ports

GPIO.setmode(GPIO.BCM)

for segment in segments:
    GPIO.setup(segment, GPIO.OUT, initial=GPIO.HIGH)

for digit in digits:
    GPIO.setup(digit, GPIO.OUT, initial=GPIO.LOW)
 
try:
    while True:
        _time = time.ctime()
        tmstr = _time[11:13] + _time[14:16]
        secs  = int(time.ctime()[18:19])

        for digit in range(4):
            colon = GPIO.LOW if (digit == 1 and secs % 2 == 0) else GPIO.HIGH
            GPIO.output(25, colon)

            for loop in range(7):
                GPIO.output(segments[loop], num[tmstr[digit]][loop])

            strobe_high(digits[digit])

finally:
    GPIO.cleanup()


