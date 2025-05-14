import board
import busio
import time
import digitalio
import displayio
import microcontroller

from i2cdisplaybus import I2CDisplayBus
import adafruit_displayio_ssd1306
from adafruit_display_text import label
import terminalio

import adafruit_ble
from adafruit_ble.advertising.standard import ProvideServicesAdvertisement
from adafruit_ble.services.standard.hid import HIDService
from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keycode import Keycode
from adafruit_hid.mouse import Mouse

from adafruit_mcp230xx.mcp23008 import MCP23008

# —— OLED Power & Reset ——
vcc = digitalio.DigitalInOut(board.VCC_OFF)       # drives P0_20
vcc.direction = digitalio.Direction.OUTPUT
vcc.value = True
time.sleep(0.2)  # let rail settle

displayio.release_displays()
for p in (microcontroller.pin.P0_20, microcontroller.pin.P0_17):
    try:
        digitalio.DigitalInOut(p).deinit()
    except Exception:
        pass

# —— I²C Bus @400 kHz ——
i2c = busio.I2C(scl=board.SCL, sda=board.SDA, frequency=400000)

# —— SSD1306 OLED Init ——
bus = I2CDisplayBus(i2c, device_address=0x3C)
display = adafruit_displayio_ssd1306.SSD1306(bus, width=128, height=64)
splash = displayio.Group()
display.root_group = splash
# Large font scale=4, y=32 center
txt = label.Label(terminalio.FONT, text="", x=0, y=32, scale=4)
splash.append(txt)

# Rolling text buffer
text_buffer = ""

def update_display(msg: str):
    global text_buffer
    text_buffer += msg
    if len(text_buffer) > 5:
        text_buffer = text_buffer[-5:]
    txt.text = text_buffer

# —— Keycode → ASCII Map ——
KEYCODE_CHAR = {}
for i in range(26):
    c = chr(ord('A') + i)
    KEYCODE_CHAR[getattr(Keycode, c)] = c
nums = ['ZERO','ONE','TWO','THREE','FOUR','FIVE','SIX','SEVEN','EIGHT','NINE']
for digit, name in zip('0123456789', nums):
    KEYCODE_CHAR[getattr(Keycode, name)] = digit
KEYCODE_CHAR[Keycode.SPACE] = ' '
KEYCODE_CHAR[Keycode.ENTER] = '\n'

def key_to_char(kc):
    return KEYCODE_CHAR.get(kc, '?')

# —— Shift + Number → Symbol Map ——
SHIFT_NUM_SYMBOLS = {
    Keycode.ONE:   '!',
    Keycode.TWO:   '@',
    Keycode.THREE: '#',
    Keycode.FOUR:  '$',
    Keycode.FIVE:  '%',
    Keycode.SIX:   '^',
    Keycode.SEVEN: '&',
    Keycode.EIGHT: '*',
    Keycode.NINE:  '(',
    Keycode.ZERO:  ')'
}

# —— MCP23008 Expander Setup ——
mcp = MCP23008(i2c)
for i in range(7):
    p = mcp.get_pin(i)
    p.direction = digitalio.Direction.INPUT
    p.pull = digitalio.Pull.UP

# —— BLE HID Setup ——
ble = adafruit_ble.BLERadio()
hid = HIDService()
advertisement = ProvideServicesAdvertisement(hid)
keyboard = Keyboard(hid.devices)
mouse    = Mouse(hid.devices)

# —— Chording Configuration ——
pin_to_key_index  = {i: i for i in range(7)}
pressed_keys      = [False] * 7
pending_combo     = None
last_hold_time    = 0
last_release_time = 0
last_combo_time   = 0

MIN_HOLD     = 0.01
COMBO_WINDOW = 0.01
COOLDOWN     = 0.01
RELEASE_WIN  = 0.01

modifier_armed   = False
held_modifier    = None
mod_trigger      = (5, 6)
modifier_chords  = {
    (0,): Keycode.LEFT_SHIFT,
    (1,): Keycode.LEFT_CONTROL,
    (2,): Keycode.LEFT_ALT,
    (3,): Keycode.LEFT_GUI
}

mouse_armed    = False
mouse_trigger  = (4, 5)

chords = {
    (0,): Keycode.E,   (1,): Keycode.I,    (2,): Keycode.A,
    (3,): Keycode.S,   (4,): Keycode.SPACE,(0,1): Keycode.R,
    (0,2): Keycode.O,  (0,3): Keycode.C,    (1,2): Keycode.N,
    (1,3): Keycode.L,  (2,3): Keycode.T,    (0,5): Keycode.M,
    (1,5): Keycode.G,  (2,5): Keycode.H,    (3,5): Keycode.B,
    (0,6): Keycode.SPACE,
    (0,1,5): Keycode.Y,(0,2,5): Keycode.W,  (0,3,5): Keycode.X,
    (1,2,5): Keycode.F,(1,3,5): Keycode.K,  (2,3,5): Keycode.V,
    (0,1,2): Keycode.D,(1,2,3): Keycode.P,
    (0,1,2,5): Keycode.J,(1,2,3,5): Keycode.Z,
    (0,1,2,3): Keycode.U,(0,1,2,3,5): Keycode.Q,
    (0,1,3,5): Keycode.DELETE,
    (0,4): Keycode.ONE,(1,4): Keycode.TWO,  (2,4): Keycode.THREE,
    (3,4): Keycode.FOUR,(0,1,4): Keycode.FIVE,(1,2,4): Keycode.SIX,
    (2,3,4): Keycode.SEVEN,(0,2,4): Keycode.EIGHT,(1,3,4): Keycode.NINE,
    (0,1,3): Keycode.BACKSPACE,
    (0,2,3): Keycode.SPACE,
    (0,3,4): Keycode.UP_ARROW,
    (0,1,2,4): Keycode.ZERO,
    (0,1,3,4): Keycode.RIGHT_ARROW,
    (0,2,3,4): Keycode.LEFT_ARROW,
    (1,2,3,4): Keycode.ESCAPE,
    (0,1,2,3,4): Keycode.DOWN_ARROW,
    (6,): Keycode.BACKSPACE,
    (1,6): Keycode.TAB,   (2,6): Keycode.PERIOD, (3,6): Keycode.MINUS,
    (2,3,6): Keycode.FORWARD_SLASH,
    (0,1,6): Keycode.ENTER,(0,2,6): Keycode.COMMA,
    (1,3,6): Keycode.LEFT_BRACKET,(0,3,6): Keycode.RIGHT_BRACKET,
    (1,2,3,6): Keycode.BACKSLASH,(1,2,6): Keycode.BACKSPACE,
    (0,1,3,6): Keycode.QUOTE,(0,2,3,6): Keycode.SEMICOLON,
    (0,1,2,3,6): Keycode.GRAVE_ACCENT
}

# —— BLE Advertise & Connect ——
update_display("")
update_display("ADV")
ble.start_advertising(advertisement)
while not ble.connected:
    time.sleep(0.05)
ble.stop_advertising()
update_display("CONN")

# —— Chord Processing Function ——
def check_chords():
    global pending_combo, last_hold_time, last_release_time, last_combo_time
    global modifier_armed, held_modifier, mouse_armed

    now = time.monotonic()
    combo = tuple(i for i, d in enumerate(pressed_keys) if d)

    if combo:
        if last_hold_time == 0:
            last_hold_time = now
        if now - last_hold_time >= MIN_HOLD:
            # Modifier layer arm
            if combo == mod_trigger:
                modifier_armed = True; mouse_armed = False; held_modifier = None
                pending_combo = combo; last_combo_time = now
                return
            # Mouse layer toggle
            if combo == mouse_trigger:
                mouse_armed = not mouse_armed; modifier_armed = False; held_modifier = None
                pending_combo = combo; last_combo_time = now
                return
            # Mouse movement
            if mouse_armed and combo != pending_combo:
                dx = dy = 0
                if combo == (0,): dy = -10
                elif combo == (1,): dx =  10
                elif combo == (2,): dx = -10
                elif combo == (3,): dy =  10
                if dx or dy:
                    mouse.move(dx, dy)
                    pending_combo = combo; last_combo_time = now
                    update_display('?')  # placeholder or show move indicator
                    time.sleep(COOLDOWN)
                    return
            # Pick modifier
            if modifier_armed and held_modifier is None and combo in modifier_chords:
                held_modifier = modifier_chords[combo]
                pending_combo = combo
                last_combo_time = now
                # Display modifier initial: S=Shift, C=Ctrl, A=Alt, G=GUI
                mod_char = {
                    Keycode.LEFT_SHIFT: 'S',
                    Keycode.LEFT_CONTROL: 'C',
                    Keycode.LEFT_ALT: 'A',
                    Keycode.LEFT_GUI: 'G'
                }.get(held_modifier, '?')
                update_display(mod_char)
                return

            # Modifier + key
            if modifier_armed and held_modifier and combo in chords:
                key = chords[combo]
                keyboard.press(held_modifier, key)
                keyboard.release_all()
                # if shift+number, show the shifted symbol
                if held_modifier == Keycode.LEFT_SHIFT and key in SHIFT_NUM_SYMBOLS:
                    ch = SHIFT_NUM_SYMBOLS[key]
                else:
                    ch = key_to_char(key)
                modifier_armed = False; held_modifier = None
                pending_combo = combo; last_combo_time = now
                update_display(ch); time.sleep(COOLDOWN); return

            # Normal chord
            if not modifier_armed and not mouse_armed and combo in chords:
                if pending_combo is None or (now - last_combo_time) <= COMBO_WINDOW:
                    if combo != pending_combo:
                        key = chords[combo]
                        keyboard.press(key); keyboard.release_all()
                        ch = key_to_char(key)
                        pending_combo = combo; last_combo_time = now
                        update_display(ch); time.sleep(COOLDOWN)
    else:
        if last_release_time == 0 or (now - last_release_time) >= RELEASE_WIN:
            pending_combo = None; last_hold_time = 0; last_release_time = now

# —— Main Loop ——
while ble.connected:
    for pin, idx in pin_to_key_index.items():
        pressed_keys[idx] = not mcp.get_pin(pin).value
    check_chords()
    time.sleep(0.05)
