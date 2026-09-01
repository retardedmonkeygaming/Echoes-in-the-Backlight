# The Last Apartment

A haunting RPG where ERIN waits.

## Wiring

GPIO 5 -> RS, GPIO 13 -> E
GPIO 17,22,23,24 -> D4,D5,D6,D7
GPIO 21 -> Backlight (active-low)
GPIO 27 -> Touch sensor
GPIO 26 -> Feedback LED
GND -> VSS, RW, K
5V -> VDD, A

## Setup

pip3 install -r requirements.txt
echo GEMINI_API_KEY=your_key > .env
sudo python3 app.py

## Rules

Max 16 chars/line, 2 lines. ERIN starts with ...
