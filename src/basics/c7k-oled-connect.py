import board
import busio
import digitalio
import displayio
import microcontroller
import time
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

# ——— OLED Power & Reset Setup ———
vcc = digitalio.DigitalInOut(board.VCC_OFF)
vcc.direction = digitalio.Direction.OUTPUT
vcc.value = True
# allow 3.3 V rail to settle
time.sleep(0.2)

# release any previous display bindings and free RESET/DC pins
displayio.release_displays()
for p in (microcontroller.pin.P0_20, microcontroller.pin.P0_17):
    try:
        digitalio.DigitalInOut(p).deinit()
    except Exception:
        pass

# ——— I²C Bus (400 kHz) ———
i2c = busio.I2C(board.SCL, board.SDA, frequency=400000)

# ——— SSD1306 OLED Initialization ———
OLED_ADDR = 0x3C  # confirmed working
bus = I2CDisplayBus(i2c, device_address=OLED_ADDR)
display = adafruit_displayio_ssd1306.SSD1306(bus, width=128, height=64)
splash = displayio.Group()
display.root_group = splash
status_lbl = label.Label(terminalio.FONT, text="Ready", x=0, y=16)
splash.append(status_lbl)

def update_display(msg: str):
    status_lbl.text = msg

# ——— MCP23008 Expander Setup ———
mcp = MCP23008(i2c)
for i in range(7):
    pin = mcp.get_pin(i)
    pin.direction = digitalio.Direction.INPUT
    pin.pull = digitalio.Pull.UP

# ——— BLE HID Setup ———
ble = adafruit_ble.BLERadio()
hid = HIDService()
advertisement = ProvideServicesAdvertisement(hid)
keyboard = Keyboard(hid.devices)
mouse = Mouse(hid.devices)

# ——— Chording Configuration ———
pin_to_key_index = {i: i for i in range(7)}
pressed_keys = [False] * 7
pending_combo = None
last_combo_time = 0
last_hold_time = 0
last_release_time = 0

# Timing parameters
MIN_HOLD   = 0.01
COMBO_WIN  = 0.01
COOLDOWN   = 0.01
RELEASE_WIN= 0.01

# Modifier layer
modifier_layer_armed = False
held_modifier = None
layer_trigger_chord = (5, 6)
modifier_chords = {
    (0,): Keycode.LEFT_SHIFT,
    (1,): Keycode.LEFT_CONTROL,
    (2,): Keycode.LEFT_ALT,
    (3,): Keycode.LEFT_GUI
}

# Mouse layer\mouse_layer_armed = False
mouse_trigger_chord = (4, 5)

# Chord → Key mapping
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
    (0,1,2,5):Keycode.J,(1,2,3,5):Keycode.Z,
    (0,1,2,3):Keycode.U,(0,1,2,3,5):Keycode.Q,
    (0,6): Keycode.ONE,(1,6): Keycode.TWO,  (2,6): Keycode.THREE,
    (3,6):Keycode.FOUR,(0,1,6):Keycode.FIVE,(1,2,6):Keycode.SIX,
    (2,3,6):Keycode.SEVEN,(0,2,6):Keycode.EIGHT,(1,3,6):Keycode.NINE,
    (0,3,6):Keycode.UP_ARROW,
    (0,1,2,6):Keycode.ZERO,
    (0,1,3,6):Keycode.RIGHT_ARROW,
    (0,2,3,6):Keycode.LEFT_ARROW,
    (1,2,3,6):Keycode.ESCAPE,
    (0,1,2,3,6):Keycode.DOWN_ARROW,
    (6,): Keycode.BACKSPACE,
    (1,4):Keycode.TAB, (2,4):Keycode.PERIOD, (3,4):Keycode.MINUS,
    (0,2,3):Keycode.SPACE,(0,1,3):Keycode.BACKSPACE,
    (2,3,4):Keycode.FORWARD_SLASH,(0,1,4):Keycode.ENTER,
    (0,2,4):Keycode.COMMA,(0,2,4):Keycode.EQUALS,
    (1,3,4):Keycode.LEFT_BRACKET,(0,3,4):Keycode.RIGHT_BRACKET,
    (2,3,4):Keycode.BACKSLASH,(1,2,4):Keycode.BACKSPACE,
    (0,1,3,4):Keycode.QUOTE,(0,2,3,4):Keycode.SEMICOLON,
    (0,1,2,3,4):Keycode.GRAVE_ACCENT
}

# ——— Main Loop ———
while True:
    # Advertise until connected
    update_display("Advertising")
    ble.start_advertising(advertisement)
    while not ble.connected:
        time.sleep(0.05)
    ble.stop_advertising()
    update_display("Connected")

    # Process chords while connected
    while ble.connected:
        for pin, idx in pin_to_key_index.items():
            pressed_keys[idx] = not mcp.get_pin(pin).value
        # chord handling logic...
        time.sleep(0.05)

    # Disconnected: show status and loop back
    update_display("Disconnected")
    time.sleep(0.5)

