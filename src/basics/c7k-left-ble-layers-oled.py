import board
import busio
import time
import digitalio
import displayio
import microcontroller
from i2cdisplaybus import I2CDisplayBus
from adafruit_display_text import label
import terminalio
import adafruit_displayio_ssd1306
from adafruit_mcp230xx.mcp23008 import MCP23008
import adafruit_ble
from adafruit_ble.advertising.standard import ProvideServicesAdvertisement
from adafruit_ble.services.standard.hid import HIDService
from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keycode import Keycode
from adafruit_hid.mouse import Mouse

# --- External VCC enable ---
vcc_enable = digitalio.DigitalInOut(board.VCC_OFF)
vcc_enable.direction = digitalio.Direction.OUTPUT
vcc_enable.value = True
# Allow power to stabilize
time.sleep(0.5)

# --- Clean up previous display bindings ---
displayio.release_displays()
for pin in (microcontroller.pin.P0_20, microcontroller.pin.P0_17):
    try:
        digitalio.DigitalInOut(pin).deinit()
    except Exception:
        pass

# --- I2C bus at 400 kHz ---
i2c = busio.I2C(board.SCL, board.SDA, frequency=400000)

# --- SSD1306 OLED initialization ---
OLED_ADDR = 0x3C  # fixed address
display_bus = I2CDisplayBus(i2c, device_address=OLED_ADDR)
display = adafruit_displayio_ssd1306.SSD1306(display_bus, width=128, height=64)

# Create text label for status
splash = displayio.Group()
display.root_group = splash
status_label = label.Label(terminalio.FONT, text="Starting BLE...", x=0, y=0)
splash.append(status_label)

def update_display(msg: str):
    status_label.text = msg

# --- MCP23008 expander setup ---
mcp = MCP23008(i2c)
pins = [mcp.get_pin(i) for i in range(7)]
for pin in pins:
    pin.direction = digitalio.Direction.INPUT
    pin.pull = digitalio.Pull.UP

# --- BLE HID setup ---
ble = adafruit_ble.BLERadio()
hid = HIDService()
advertisement = ProvideServicesAdvertisement(hid)
keyboard = Keyboard(hid.devices)
mouse = Mouse(hid.devices)

# --- Start advertising with a small pause in loop ---
ble.start_advertising(advertisement)
update_display("Advertising")
while not ble.connected:
    time.sleep(0.05)  # yield for BLE
ble.stop_advertising()
update_display("Connected")

# --- Pin mapping & state for chording ---
pin_to_key_index = {i: i for i in range(7)}
pressed_keys = [False] * 7
pending_combo = None
last_combo_time = 0
last_hold_time = 0
last_release_time = 0

# --- Timing parameters ---
minimum_hold_time   = 0.01
combo_time_window   = 0.01
cooldown_time       = 0.01
release_time_window = 0.01

# --- Modifier layer setup ---
modifier_layer_armed = False
held_modifier        = None
layer_trigger_chord  = (5, 6)
modifier_chords = {
    (0,): Keycode.LEFT_SHIFT,
    (1,): Keycode.LEFT_CONTROL,
    (2,): Keycode.LEFT_ALT,
    (3,): Keycode.LEFT_GUI
}

# --- Mouse layer setup ---
mouse_layer_armed   = False
mouse_trigger_chord = (4, 5)

# --- Chord to key mapping ---
chords = {
    (0,): Keycode.E,   (1,): Keycode.I,    (2,): Keycode.A,
    (3,): Keycode.S,   (4,): Keycode.SPACE,(0,1): Keycode.R,
    (0,2): Keycode.O,  (0,3): Keycode.C,    (1,2): Keycode.N,
    (1,3): Keycode.L,  (2,3): Keycode.T,    (0,5): Keycode.M,
    (1,5): Keycode.G,  (2,5): Keycode.H,    (3,5): Keycode.B,
    (0,4): Keycode.SPACE,
    (0,1,5): Keycode.Y,(0,2,5): Keycode.W,  (0,3,5): Keycode.X,
    (1,2,5): Keycode.F,(1,3,5): Keycode.K,  (2,3,5): Keycode.V,
    (0,1,2): Keycode.D,(1,2,3): Keycode.P,
    (0,1,2,5): Keycode.J,(1,2,3,5): Keycode.Z,
    (0,1,2,3): Keycode.U,(0,1,2,3,5): Keycode.Q,
    (0,6): Keycode.ONE,(1,6): Keycode.TWO,  (2,6): Keycode.THREE,
    (3,6): Keycode.FOUR,(0,1,6): Keycode.FIVE,(1,2,6):Keycode.SIX,
    (2,3,6):Keycode.SEVEN,(0,2,6):Keycode.EIGHT,(1,3,6):Keycode.NINE,
    (0,3,6):Keycode.UP_ARROW,
    (0,1,2,6):Keycode.ZERO,
    (0,1,3,6):Keycode.RIGHT_ARROW,
    (0,2,3,6):Keycode.LEFT_ARROW,
    (1,2,3,6):Keycode.ESCAPE,
    (0,1,2,3,6):Keycode.DOWN_ARROW,
    (6,):Keycode.BACKSPACE,
    (1,4):Keycode.TAB,(2,4):Keycode.PERIOD,(3,4):Keycode.MINUS,
    (0,2,3):Keycode.SPACE,(0,1,3):Keycode.BACKSPACE,
    (2,3,4):Keycode.FORWARD_SLASH,(0,1,4):Keycode.ENTER,
    (0,2,4):Keycode.COMMA,(0,2,4):Keycode.EQUALS,
    (1,3,4):Keycode.LEFT_BRACKET,(0,3,4):Keycode.RIGHT_BRACKET,
    (2,3,4):Keycode.BACKSLASH,(1,2,4):Keycode.BACKSPACE,
    (0,1,3,4):Keycode.QUOTE,(0,2,3,4):Keycode.SEMICOLON,
    (0,1,2,3,4):Keycode.GRAVE_ACCENT
}

# --- Chord processing function ---
def check_chords():
    global pending_combo, last_combo_time, last_hold_time, last_release_time
    global modifier_layer_armed, held_modifier, mouse_layer_armed

    now = time.monotonic()
    combo = tuple(i for i,d in enumerate(pressed_keys) if d)
    if combo:
        if last_hold_time == 0:
            last_hold_time = now
        if now - last_hold_time >= minimum_hold_time:
            # Mouse layer toggle
            if combo == mouse_trigger_chord:
                mouse_layer_armed = not mouse_layer_armed
                modifier_layer_armed = False
                held_modifier = None
                pending_combo = combo
                last_combo_time = now
                update_display(f"Mouse: {mouse_layer_armed}")
                return
            # Modifier layer arm
            if combo == layer_trigger_chord:
                modifier_layer_armed = True
                mouse_layer_armed = False
                held_modifier = None
                pending_combo = combo
                last_combo_time = now
                update_display("Mod Layer")
                return
            # Mouse movement
            if mouse_layer_armed and combo != pending_combo:
                dx = dy = 0
                if combo == (0,): dy = -10
                elif combo == (1,): dx = 10
                elif combo == (2,): dx = -10
                elif combo == (3,): dy = 10
                if dx or dy:
                    mouse.move(dx,dy)
                    pending_combo = combo
                    last_combo_time = now
                    update_display(f"Move: {dx},{dy}")
                    time.sleep(cooldown_time)
                    return
            # Pick a modifier
            if modifier_layer_armed and held_modifier is None:
                if combo in modifier_chords and combo != pending_combo:
                    held_modifier = modifier_chords[combo]
                    pending_combo = combo
                    last_combo_time = now
                    update_display(f"Mod: {held_modifier}")
                    return
            # Modifier + key
            if modifier_layer_armed and held_modifier:
                if combo in chords and combo != pending_combo:
                    key = chords[combo]
                    keyboard.press(held_modifier, key)
                    keyboard.release_all()
                    modifier_layer_armed = False
                    held_modifier = None
                    pending_combo = combo
                    last_combo_time = now
                    update_display(f"Key: {key}")
                    time.sleep(cooldown_time)
                    return
            # Normal chord
            if not modifier_layer_armed and not mouse_layer_armed and combo in chords:
                if pending_combo is None or (now - last_combo_time) <= combo_time_window:
                    if combo != pending_combo:
                        key = chords[combo]
                        keyboard.press(key)
                        keyboard.release_all()
                        pending_combo = combo
                        last_combo_time = now
                        update_display(f"Key: {key}")
                        time.sleep(cooldown_time)
    else:
        # Reset on release
        if last_release_time == 0 or (now - last_release_time) >= release_time_window:
            pending_combo = None
            last_hold_time = 0
            last_release_time = now

# --- Main loop ---
while ble.connected:
    for pin, idx in pin_to_key_index.items():
        pressed_keys[idx] = not mcp.get_pin(pin).value
    check_chords()
    time.sleep(0.05)

