# Copyright (c) 2026 kanshurichard
# Portions based on ha-sesame-ble (Copyright (c) 2026 ngoc-minh-do) and gomalock (Copyright (c) 2026 meronepy).
# Licensed under the MIT License. See LICENSE and NOTICE in the repository root for details.

"""Constants for the Sesame 5 BLE integration."""

from __future__ import annotations

from enum import Enum, IntFlag

DOMAIN = "sesame5_ble"

# Config entries
CONF_ADDRESS = "address"
CONF_DEVICE_ID = "device_id"
CONF_SECRET_KEY = "secret_key"
CONF_MODEL = "model"
CONF_MODEL_ID = "model_id"
CONF_REFRESH_INTERVAL = "refresh_interval"
CONF_HISTORY_TAG = "history_tag"
CONF_READ_ONLY = "read_only"
CONF_CONNECTION_MODE = "connection_mode"
CONF_LINKED_LOCK = "linked_lock"

DEFAULT_REFRESH_INTERVAL = 0  # 0 = on-demand only (saves battery)
DEFAULT_HISTORY_TAG = "HA"
DEFAULT_READ_ONLY = False
DEFAULT_LINKED_LOCK = "auto"

# Connection modes
CONNECTION_MODE_REALTIME = "realtime"
CONNECTION_MODE_POWER_SAVING = "power_saving"
DEFAULT_CONNECTION_MODE = CONNECTION_MODE_REALTIME
POWER_SAVING_IDLE_TIMEOUT = 10  # Seconds before disconnect in power-saving mode

# BLE GATT Service & Characteristics (Sesame standard)
SERVICE_UUID = "0000fd81-0000-1000-8000-00805f9b34fb"
TX_UUID = "16860002-a5ae-9856-b6d3-dbb4c676993e"  # Client writes to this
RX_UUID = "16860003-a5ae-9856-b6d3-dbb4c676993e"  # Lock notifies via this

COMPANY_ID = 0x055A  # CANDY HOUSE, Inc.


class ProductModel(Enum):
    """CANDY HOUSE product models (SesameOS 3 & compatible)."""

    SESAME_5 = 5
    SESAME_BIKE_2 = 6
    SESAME_5_PRO = 7
    SESAME_TOUCH_1_PRO = 9
    SESAME_TOUCH_1 = 10
    SESAME_5_US = 16
    SESAME_BOT_2 = 17
    SESAME_FACE_1_PRO = 18
    SESAME_FACE_1 = 19
    SESAME_6 = 20
    SESAME_6_PRO = 21
    SESAME_TOUCH_2 = 25
    SESAME_TOUCH_2_PRO = 26
    SESAME_BIKE_3 = 33
    SESAME_BOT_3 = 35


PRODUCT_NAMES: dict[int, str] = {
    ProductModel.SESAME_5.value: "Sesame 5",
    ProductModel.SESAME_BIKE_2.value: "Sesame Bike 2",
    ProductModel.SESAME_5_PRO.value: "Sesame 5 Pro",
    ProductModel.SESAME_TOUCH_1_PRO.value: "Sesame Touch 1 Pro",
    ProductModel.SESAME_TOUCH_1.value: "Sesame Touch 1",
    ProductModel.SESAME_5_US.value: "Sesame 5 US",
    ProductModel.SESAME_BOT_2.value: "Sesame Bot 2",
    ProductModel.SESAME_FACE_1_PRO.value: "Sesame Face 1 Pro",
    ProductModel.SESAME_FACE_1.value: "Sesame Face 1",
    ProductModel.SESAME_6.value: "Sesame 6",
    ProductModel.SESAME_6_PRO.value: "Sesame 6 Pro",
    ProductModel.SESAME_TOUCH_2.value: "Sesame Touch 2",
    ProductModel.SESAME_TOUCH_2_PRO.value: "Sesame Touch 2 Pro",
    ProductModel.SESAME_BIKE_3.value: "Sesame Bike 3",
    ProductModel.SESAME_BOT_3.value: "Sesame Bot 3",
}

MODEL_NAME_TO_ID: dict[str, int] = {v: k for k, v in PRODUCT_NAMES.items()}

MANUAL_MODEL_OPTIONS: list[str] = [
    "Sesame 5",
    "Sesame 5 Pro",
    "Sesame 5 US",
    "Sesame 6",
    "Sesame 6 Pro",
    "Sesame Touch 2 Pro",
    "Sesame Touch 2",
    "Sesame Touch 1 Pro",
    "Sesame Touch 1",
    "Sesame Face 1 Pro",
    "Sesame Face 1",
    "Sesame Bike 2",
    "Sesame Bike 3",
    "Sesame Bot 2",
    "Sesame Bot 3",
]

LOCK_MODELS = {
    ProductModel.SESAME_5.value,
    ProductModel.SESAME_5_PRO.value,
    ProductModel.SESAME_5_US.value,
    ProductModel.SESAME_BIKE_2.value,
    ProductModel.SESAME_BIKE_3.value,
    ProductModel.SESAME_6.value,
    ProductModel.SESAME_6_PRO.value,
}

TOUCH_MODELS = {
    ProductModel.SESAME_TOUCH_1_PRO.value,
    ProductModel.SESAME_TOUCH_1.value,
    ProductModel.SESAME_TOUCH_2.value,
    ProductModel.SESAME_TOUCH_2_PRO.value,
    ProductModel.SESAME_FACE_1_PRO.value,
    ProductModel.SESAME_FACE_1.value,
}

BOT_MODELS = {
    ProductModel.SESAME_BOT_2.value,
    ProductModel.SESAME_BOT_3.value,
}


class PacketType(IntFlag):
    """1-byte packet header bits for BLE communication."""

    BEGINNING = 0b001
    PLAINTEXT_END = 0b010
    ENCRYPTED_END = 0b100


class ItemCode(Enum):
    """Item codes for commands, publishes, and responses in SesameOS 3."""

    NONE = 0
    REGISTRATION = 1
    LOGIN = 2
    USER = 3
    HISTORY = 4
    VERSION_TAG = 5
    DISCONNECT_REBOOT_NOW = 6
    ENABLE_DFU = 7
    TIME = 8
    AUTOLOCK = 11
    INITIAL = 14
    MECH_SETTING = 80
    MECH_STATUS = 81
    LOCK = 82
    UNLOCK = 83
    MOVE_TO = 84
    DRIVE_DIRECTION = 85
    STOP = 86
    TOGGLE = 88
    CLICK = 89

    # Biometric & Keypad item codes (Sesame Touch / Touch 2 / Keypad / Face)
    CARD_CHANGE = 107
    CARD_DELETE = 108
    CARD_GET = 109
    CARD_NOTIFY = 110
    CARD_LAST = 111
    CARD_FIRST = 112
    CARD_MODE_GET = 113
    CARD_MODE_SET = 114

    FINGERPRINT_CHANGE = 115
    FINGERPRINT_DELETE = 116
    FINGERPRINT_GET = 117
    FINGERPRINT_NOTIFY = 118
    FINGERPRINT_LAST = 119
    FINGERPRINT_FIRST = 120
    FINGERPRINT_MODE_GET = 121
    FINGERPRINT_MODE_SET = 122

    SSM_OS3_PASSCODE_CHANGE = 123
    SSM_OS3_PASSCODE_DELETE = 124
    SSM_OS3_PASSCODE_GET = 125
    SSM_OS3_PASSCODE_NOTIFY = 126
    SSM_OS3_PASSCODE_LAST = 127
    SSM_OS3_PASSCODE_FIRST = 128
    SSM_OS3_PASSCODE_MODE_GET = 129
    SSM_OS3_PASSCODE_MODE_SET = 130
    SSM_OS3_PASSCODE_ADD = 138
    SSM_OS3_PASSCODE_MOVE = 142
    CARD_ADD = 140
    CARD_MOVE = 141


class OpCode(Enum):
    """OpCodes in Sesame message framing."""

    CREATE = 0x01
    READ = 0x02
    UPDATE = 0x03
    DELETE = 0x04
    SYNC = 0x05
    ASYNC = 0x06
    RESPONSE = 0x07
    PUBLISH = 0x08


class ResultCode(Enum):
    """Command result codes returned by Sesame lock."""

    SUCCESS = 0
    INVALID_FORMAT = 1
    NOT_SUPPORTED = 2
    STORAGE_FAIL = 3
    INVALID_SIG = 4
    NOT_FOUND = 5
    UNKNOWN = 6
    BUSY = 7
    INVALID_PARAM = 8
    INVALID_ACTION = 9


class HistoryType(Enum):
    """Operation history event type reported by Sesame lock."""

    NONE = 0
    BLE_LOCK = 1
    BLE_UNLOCK = 2
    TIME_CHANGED = 3
    AUTOLOCK_UPDATED = 4
    MECH_SETTING_UPDATED = 5
    AUTOLOCK = 6
    MANUAL_LOCKED = 7
    MANUAL_UNLOCKED = 8
    MANUAL_ELSE = 9
    DRIVE_LOCKED = 10
    DRIVE_UNLOCKED = 11
    DRIVE_FAILED = 12
    BLE_ADV_PARAM_UPDATED = 13
    WM2_LOCK = 14
    WM2_UNLOCK = 15
    WEB_LOCK = 16
    WEB_UNLOCK = 17
    BLE_CLICK = 18
    DRIVE_CLICKED = 21
    OPEN_SENSOR_OPEN = 90
    OPEN_SENSOR_CLOSE = 91


class HistoryTagType(Enum):
    """Access accessory/trigger type for Sesame Touch, Remote, or Face devices."""

    NFC_CARD = 0
    FINGERPRINT = 1
    PASSWORD = 2
    FACE = 3
    PALM_VEIN = 4
    TOUCH_PRO_LOCK = 5
    TOUCH_LOCK = 6
    OPEN_SENSOR = 7
    FACE_PRO_LOCK = 8
    FACE_LOCK = 9
    REMOTE = 10
    REMOTE_NANO = 11
    BIZ_USER = 12
    WEB_API = 13
    ANDROID_BLE = 14
    IOS_BLE = 15
    ANDROID_WIFI = 16
    IOS_WIFI = 17


class MechStatusBitFlag(IntFlag):
    """Mechanical status bit flags for Sesame 5."""

    IS_CLUTCH_FAILED = 0b00000001
    IS_IN_LOCK_RANGE = 0b00000010
    IS_IN_UNLOCK_RANGE = 0b00000100
    IS_CRITICAL = 0b00001000
    IS_STOP = 0b00010000
    IS_BATTERY_CRITICAL = 0b00100000
    IS_CLOCKWISE = 0b01000000


# CR123A x2 Voltage to Percentage lookup table (Sesame standard)
VOLTAGE_LEVELS = (
    5.85,
    5.82,
    5.79,
    5.76,
    5.73,
    5.70,
    5.65,
    5.60,
    5.55,
    5.50,
    5.40,
    5.20,
    5.10,
    5.00,
    4.80,
    4.60,
)

BATTERY_PERCENTAGES = (
    100.0,
    95.0,
    90.0,
    85.0,
    80.0,
    70.0,
    60.0,
    50.0,
    40.0,
    32.0,
    21.0,
    13.0,
    10.0,
    7.0,
    3.0,
    0.0,
)

# Timeouts in seconds
CONNECT_TIMEOUT = 10
INITIAL_TOKEN_TIMEOUT = 5
LOGIN_TIMEOUT = 8
COMMAND_TIMEOUT = 5

# Services
SERVICE_ADD_PASSCODE = "add_passcode"
SERVICE_DELETE_PASSCODE = "delete_passcode"
SERVICE_GET_PASSCODES = "get_passcodes"

# Service Attributes
ATTR_PASSCODE = "passcode"
ATTR_NAME = "name"
ATTR_DURATION = "duration"
ATTR_ONE_TIME = "one_time"

# Internal Dispatcher Signals
SIGNAL_SESAME_HISTORY_UPDATE = "sesame5_ble_history_update"
