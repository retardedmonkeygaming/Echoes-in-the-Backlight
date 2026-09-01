# The Last Apartment - Echoes in the Backlight

Haunting RPG for Raspberry Pi + 1602A LCD.
Player talks to ERIN (Elena Voss), murdered in 1993.

## Story
Elena Voss, 23, painter. Met Marcus Hale in bookstore.
He drugged her coffee. Held her hand for 3 days while she died.
Police believed him. He stayed a year. Then locked the door.
She is still here. In the screen. In the static.

## Run
pip3 install -r requirements.txt
sudo python3 app.py

## Wiring
GPIO5->RS, GPIO6->RW, GPIO13->E, GPIO17->D4
GPIO22->D5, GPIO23->D6, GPIO24->D7, GPIO21->Backlight
GPIO27->Touch, GPIO26->LED, GPIO18->Buzzer

## Features
5 personalities, Gemini API, 16x2 LCD, PWM tones
Truth Mode after 80+ messages
Two endings: close door or leave light on
Room Decay, Silent Mode, Memory Dust, Ghost Messages
Web Audio API sounds on phone
