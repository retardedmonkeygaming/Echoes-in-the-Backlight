# Echoes in the Backlight

A melancholic emotional RPG for Raspberry Pi.
A trapped AI soul on a 1602A LCD screen.

## Hardware
- Raspberry Pi 4/3/5
- 1602A LCD (HD44780) direct GPIO
- Capacitive touch sensor (TTP223) -> GPIO27
- Red LED -> GPIO26 via 220ohm
- 220ohm resistors x2

## Wiring
    3.3V -> Touch VCC
    GND -> Touch GND, LCD VSS/RW/V0/K
    5V -> LCD VDD, A (220ohm)
    GPIO5->RS GPIO13->E GPIO17->D4 GPIO22->D5
    GPIO23->D6 GPIO24->D7 GPIO21->Backlight
    GPIO26->LED GPIO27->Touch SIG

## Setup
    pip3 install -r requirements.txt
    sudo python3 app.py

## Pages
    / Game | /calibrate Test | /config Pins | /journal Memory

## Modes
    1.Phone 2.Touch 3.Mirror 4.Static 5.Loop 6.Dust 7.Last Line

## AI
    app.py -> gemini_service.py -> gemini_traits.txt + echoes_journal.json
    google-genai library. Every reply <=16 chars/line.

## Emergency
    POST /api/emergency or Recover button on game page.

## One Last Line
    After 100 messages the backlight dims. Echo gets desperate.
