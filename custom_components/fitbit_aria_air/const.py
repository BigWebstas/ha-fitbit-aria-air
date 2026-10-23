"""Constants for the Fitbit Aria Air integration."""

DOMAIN = "fitbit_aria_air"

CONF_KEY = "key"
CONF_UNIT = "unit"
CONF_ALWAYS_CONNECT = "always_connect"

UNIT_KG = "kg"
UNIT_LB = "lb"

# The scale advertises this local name and puts a 2-byte status plus its own
# address in manufacturer data (company code 0x018E). The second byte is 1 while
# the scale is awake because someone is standing on it.
LOCAL_NAME = "Aria Air"
MANUFACTURER_ID = 0x018E

# Vendor characteristic that indicates encrypted weigh-ins. It declares the
# indicate property, but the scale only streams data once its client
# characteristic configuration is 0x0001 (the value the Fitbit app writes).
WEIGHT_CHAR_UUID = "67b0ab2c-8323-427a-b1c9-70324bb5e228"
CCCD_UUID = "00002902-0000-1000-8000-00805f9b34fb"
CCCD_NOTIFY = b"\x01\x00"

# Session timing, in seconds.
CONNECT_MAX = 60  # give up connecting; the scale sleeps soon after waking
DISCONNECT_MAX = 10  # a dropped disconnect reply must not hold the session open
SESSION_MAX = 120  # hard cap for one connection
NO_DATA_TIMEOUT = 45  # give up if nothing arrives after subscribing
IDLE_AFTER_READING = 20  # disconnect this long after the last reading
RETRY_COOLDOWN = 3  # pause between sessions
ALWAYS_CONNECT_COOLDOWN = 15  # spacing when "always connect" is enabled
