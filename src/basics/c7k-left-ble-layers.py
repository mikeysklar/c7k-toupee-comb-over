import board
import busio
import time
import digitalio
from adafruit_mcp230xx.mcp23008 import MCP23008
import adafruit_ble
from adafruit_ble.advertising.standard import ProvideServicesAdvertisement
from adafruit_ble.services.standard.hid import HIDService
from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keycode import Keycode
from adafruit_hid.mouse import Mouse

# --- Turn on external VCC (P0.13 high) ---
vcc_enable = digitalio.DigitalInOut(board.VCC_OFF)
vcc_enable.direction = digitalio.Direction.OUTPUT
vcc_enable.value = True
time.sleep(0.5)

# Setup I2C and single MCP23008 expander
i2c = busio.I2C(scl=board.SCL, sda=board.SDA, frequency=400000)
mcp = MCP23008(i2c)

# Configure pins 0–6 as inputs with pull-ups
pins = [mcp.get_pin(i) for i in range(7)]
for pin in pins:
    pin.direction = digitalio.Direction.INPUT
    pin.pull = digitalio.Pull.UP

# BLE HID setup
ble = adafruit_ble.BLERadio()
hid = HIDService()
advertisement = ProvideServicesAdvertisement(hid)
keyboard = Keyboard(hid.devices)
mouse = Mouse(hid.devices)

# Map MCP pin → key index (0–6)
pin_to_key_index = {i: i for i in range(7)}

# State tracking
pressed_keys = [False] * 7
pending_combo = None
last_combo_time = 0
last_hold_time = 0
last_release_time = 0

# Timing params
minimum_hold_time   = 0.01
combo_time_window   = 0.01
cooldown_time       = 0.01
release_time_window = 0.01

# Modifier layer
modifier_layer_armed = False
held_modifier        = None
layer_trigger_chord  = (5, 6)
modifier_chords = {
    (0,): Keycode.LEFT_SHIFT,
    (1,): Keycode.LEFT_CONTROL,
    (2,): Keycode.LEFT_ALT,
    (3,): Keycode.LEFT_GUI
}

# Mouse layer
mouse_layer_armed  = False
mouse_trigger_chord = (4, 5)

# Chord → key mapping
chords = {
    (0,): Keycode.E,   (1,): Keycode.I,   (2,): Keycode.A,
    (3,): Keycode.S,   (4,): Keycode.SPACE, (0,1): Keycode.R,
    (0,2): Keycode.O,  (0,3): Keycode.C,   (1,2): Keycode.N,
    (1,3): Keycode.L,  (2,3): Keycode.T,   (0,5): Keycode.M,
    (1,5): Keycode.G,  (2,5): Keycode.H,   (3,5): Keycode.B,
    (0,4): Keycode.SPACE,
    (0,1,5): Keycode.Y,(0,2,5): Keycode.W,(0,3,5): Keycode.X,
    (1,2,5): Keycode.F,(1,3,5): Keycode.K,(2,3,5): Keycode.V,
    (0,1,2): Keycode.D,(1,2,3): Keycode.P,
    (0,1,2,5): Keycode.J,(1,2,3,5): Keycode.Z,
    (0,1,2,3): Keycode.U,(0,1,2,3,5): Keycode.Q,
    (0,6): Keycode.ONE,  (1,6): Keycode.TWO,   (2,6): Keycode.THREE,
    (3,6): Keycode.FOUR, (0,1,6): Keycode.FIVE, (1,2,6): Keycode.SIX,
    (2,3,6): Keycode.SEVEN,(0,2,6): Keycode.EIGHT,(1,3,6): Keycode.NINE,
    (0,3,6): Keycode.UP_ARROW,
    (0,1,2,6): Keycode.ZERO,
    (0,1,3,6): Keycode.RIGHT_ARROW,
    (0,2,3,6): Keycode.LEFT_ARROW,
    (1,2,3,6): Keycode.ESCAPE,
    (0,1,2,3,6): Keycode.DOWN_ARROW,
    (6,): Keycode.BACKSPACE,
    (1,4): Keycode.TAB, (2,4): Keycode.PERIOD,
    (3,4): Keycode.MINUS,
    (0,2,3): Keycode.SPACE,
    (0,1,3): Keycode.BACKSPACE,
    (2,3,4): Keycode.FORWARD_SLASH,
    (0,1,4): Keycode.ENTER,
    (0,2,4): Keycode.COMMA, (0,2,4): Keycode.EQUALS,
    (1,3,4): Keycode.LEFT_BRACKET,
    (0,3,4): Keycode.RIGHT_BRACKET,
    (2,3,4): Keycode.BACKSLASH,
    (1,2,4): Keycode.BACKSPACE,
    (0,1,3,4): Keycode.QUOTE,
    (0,2,3,4): Keycode.SEMICOLON,
    (0,1,2,3,4): Keycode.GRAVE_ACCENT
}

# Start advertising and wait for connection
ble.start_advertising(advertisement)
while not ble.connected:
    pass
ble.stop_advertising()

def check_chords():
    global pending_combo, last_combo_time, last_hold_time, last_release_time
    global modifier_layer_armed, held_modifier, mouse_layer_armed

    current_time = time.monotonic()
    combo = tuple(i for i, down in enumerate(pressed_keys) if down)

    if combo:
        if last_hold_time == 0:
            last_hold_time = current_time

        if (current_time - last_hold_time) >= minimum_hold_time:
            # 1) Toggle mouse layer
            if combo == mouse_trigger_chord:
                mouse_layer_armed    = not mouse_layer_armed
                modifier_layer_armed = False
                held_modifier        = None
                pending_combo        = combo
                last_combo_time      = current_time
                return

            # 2) Arm modifier layer
            if combo == layer_trigger_chord:
                modifier_layer_armed = True
                mouse_layer_armed    = False
                held_modifier        = None
                pending_combo        = combo
                last_combo_time      = current_time
                return

            # 3) Mouse movement
            if mouse_layer_armed and combo != pending_combo:
                dx = dy = 0
                if   combo == (0,): dy = -10
                elif combo == (1,): dx =  10
                elif combo == (2,): dx = -10
                elif combo == (3,): dy =  10
                if dx or dy:
                    mouse.move(x=dx, y=dy)
                    pending_combo   = combo
                    last_combo_time = current_time
                    time.sleep(cooldown_time)
                    return

            # 4) Pick a modifier
            if modifier_layer_armed and held_modifier is None:
                if combo in modifier_chords and combo != pending_combo:
                    held_modifier    = modifier_chords[combo]
                    pending_combo    = combo
                    last_combo_time  = current_time
                    return

            # 5) Modifier + key
            if modifier_layer_armed and held_modifier:
                if combo in chords and combo != pending_combo:
                    keyboard.press(held_modifier, chords[combo])
                    keyboard.release_all()
                    modifier_layer_armed = False
                    held_modifier        = None
                    pending_combo        = combo
                    last_combo_time      = current_time
                    time.sleep(cooldown_time)
                    return

            # 6) Normal chord
            if (not modifier_layer_armed) and (not mouse_layer_armed) and combo in chords:
                if pending_combo is None or (current_time - last_combo_time) <= combo_time_window:
                    if combo != pending_combo:
                        keyboard.press(chords[combo])
                        keyboard.release_all()
                        pending_combo   = combo
                        last_combo_time = current_time
                        time.sleep(cooldown_time)
    else:
        # all keys released → reset
        if last_release_time == 0 or (current_time - last_release_time) >= release_time_window:
            pending_combo   = None
            last_hold_time  = 0
            last_release_time = current_time

# Main loop: sample pins and run chord logic
while ble.connected:
    for pin, idx in pin_to_key_index.items():
        if not mcp.get_pin(pin).value:
            if not pressed_keys[idx]:
                pressed_keys[idx] = True
        else:
            if pressed_keys[idx]:
                pressed_keys[idx] = False

    check_chords()
    time.sleep(0.05)
