# Sesame 5 BLE for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/default)
[![GitHub Release](https://img.shields.io/github/v/release/kanshurichard/ha-sesame5-ble?style=for-the-badge&color=blue)](https://github.com/kanshurichard/ha-sesame5-ble/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-blue.svg?style=for-the-badge&logo=home-assistant)](https://www.home-assistant.io)

**English** | [简体中文](README.zh-CN.md) | [日本語](README.ja.md)

A modern, high-performance Home Assistant custom integration for direct, local Bluetooth Low Energy (BLE) control of **CANDY HOUSE Sesame 5**, **Sesame 5 Pro**, and **Sesame Touch / Keypad** devices running **SesameOS 3**.

---

## ✨ Key Features

- **🔒 100% Local BLE Control**: Direct communication with your Sesame locks via Bluetooth Low Energy. No Wi-Fi hub, cloud account, or external gateway required. Works even if your internet is down.
- **⚡ SesameOS 3 Protocol**: Full native implementation of the SesameOS 3 cryptographic stack (ECDH P-256 key exchange & AES-CMAC message authentication).
- **📱 Broad Hardware Support**:
  - **Sesame 5 & Sesame 5 Pro**
  - **Sesame Touch 1 / Touch 1 Pro & Touch 2 / Touch 2 Pro** (Keypad & Fingerprint reader, full series support)
  - **Sesame Bike 2 & Sesame Bike 3**
  - **Sesame Bot 2 & Sesame Bot 3**
  - **Sesame 5 US**
  - **Sesame 6 & Sesame 6 Pro**
  - **Sesame Face 1 & Sesame Face 1 Pro**
- **🔄 Dual Connection Modes**:
  - **Real-Time Persistent Mode (Recommended)**: Keeps a continuous BLE connection with keep-alive signals for instant status reports (<1s), real-time automation triggers, and immediate one-time passcode invalidation.
  - **Power-Saving Mode**: Connects only on-demand or at configurable intervals to maximize battery life.
- **🔑 Touch / Keypad Passcode Management**:
  - Add permanent passcodes directly from Home Assistant.
  - Add time-limited temporary passcodes (automatically purged from the keypad upon expiration).
  - Add **One-Time Passcodes (OTP)** (automatically deleted from the keypad immediately upon first successful door unlock).
  - Query and delete passcodes via native Home Assistant services.
- **📊 Comprehensive Sensor Suite**: Lock state, battery level (%), battery voltage (V), angle (°), motor status, last operation history (who/how unlocked), and registered credential counters.
- **🛡️ Read-Only Safety Mode**: An optional toggle during setup to prevent accidental remote unlocking while retaining full sensor monitoring.
- **📡 ESP32 Bluetooth Proxy Compatible**: Seamlessly works with ESPHome Bluetooth Proxies to extend BLE coverage across large multi-story houses.

---

## 📦 Compatibility Table

| Device | Model | Lock / Unlock | Real-Time State | Battery & Angle | Passcode Management |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **Sesame 5** | 5 | ✅ | ✅ | ✅ | — |
| **Sesame 5 Pro** | 7 | ✅ | ✅ | ✅ | — |
| **Sesame 5 US** | 16 | ✅ | ✅ | ✅ | — |
| **Sesame 6 / 6 Pro** | 20, 21 | ✅ | ✅ | ✅ | — |
| **Sesame Bike 2 / 3** | 6, 33 | ✅ | ✅ | ✅ | — |
| **Sesame Touch 1 / 2 & Pro** | 9, 10, 25, 26 | — | ✅ | ✅ | ✅ (Passcodes) |
| **Sesame Bot 2 / 3** | 17, 35 | ✅ | ✅ | ✅ | — |
| **Sesame Face 1 / Pro** | 18, 19 | — | ✅ | ✅ | ✅ (Passcodes) |

---

## 🚀 Installation

### Method 1: Via HACS (Recommended)

1. Open **HACS** in your Home Assistant.
2. Click the top-right three dots menu `⋮` and select **Custom repositories**.
3. Add repository URL:
   ```text
   https://github.com/kanshurichard/ha-sesame5-ble
   ```
4. Select category: **Integration**, and click **Add**.
5. Search for **Sesame 5 BLE** and click **Download**.
6. Restart Home Assistant.

### Method 2: Manual Installation

1. Download the latest release `.zip` from [Releases](https://github.com/kanshurichard/ha-sesame5-ble/releases).
2. Extract and copy the `custom_components/sesame5_ble` folder into your Home Assistant `<config_dir>/custom_components/` directory:
   ```bash
   # Destination structure:
   # <config_dir>/custom_components/sesame5_ble/__init__.py
   # <config_dir>/custom_components/sesame5_ble/manifest.json
   # ...
   ```
3. Restart Home Assistant.

---

## 🔑 Obtaining Your Secret Key (QR Code)

To pair your lock, Home Assistant needs the device's **Secret Key** exported from the official Sesame App:

1. Open the official **Sesame App** on your smartphone.
2. Select your Sesame 5 lock or Touch keypad.
3. Tap the **Settings** icon (top right) → **Share Key** → **Owner / Manager Key**.
4. Generate the **QR Code**.
5. Either take a screenshot or scan the QR code to obtain:
   - The full QR Code URL (e.g. `ssm://UI?k=...` or `https://sesame.candyhouse.co/...`), or
   - The raw base64 string, or the 32-character hexadecimal secret key.
6. The integration automatically parses and validates all standard formats!

---

## ⚙️ Configuration & Pairing

1. In Home Assistant, navigate to **Settings** → **Devices & Services** → **Add Integration**.
2. Search for **Sesame 5 BLE**.
3. Select your discovered Sesame device from the list (or choose **Manual Input** to enter the Bluetooth MAC address).
4. Paste the **Secret Key** or **QR Code URL**.
5. Configure your preferences:
   - **Connection Mode**: Choose *Real-time Persistent* (recommended for main doors) or *Power-Saving*.
   - **History Tag**: The name shown in the Sesame App's history log when Home Assistant operates the lock (default: `HA`).
   - **Read-Only Mode**: Check this if you only want to monitor status without remote control capability.
6. For **Sesame Touch / Keypads**: Select the **Linked Sesame Lock**. When the keypad unlocks that lock, the keypad will automatically connect and delete one-time passcodes immediately.

---

## 🛠️ Services (Passcode Management)

> [!WARNING]
> ### ⚠️ Important Notice & Limitations for Temporary and One-Time Passcodes
> 1. **Managed by Home Assistant**: Sesame Touch keypads do not natively store expiration timestamps or one-time flags in their firmware. Temporary passcodes (`duration`) and one-time passcodes (`one_time`) are tracked in memory and deleted by Home Assistant over BLE.
> 2. **Bluetooth Connection Requirement**: When the timer expires or the door is unlocked, Home Assistant initiates a BLE connection to the keypad to delete the passcode. **If the keypad is asleep, out of Bluetooth range, or if Home Assistant is offline at that moment, the passcode cannot be automatically removed** and must be deleted manually once connection is restored.
> 3. **One-Time Passcode Trigger Behavior**: Due to SesameOS 3 lock protocol design, the door lock only reports that an unlock occurred via "Keypad Password"; **it does NOT report which passcode PIN or label was entered**. Consequently, **ANY keypad password unlock** on the linked lock will trigger the auto-deletion of active one-time passcodes. If a homeowner unlocks using their regular permanent passcode while a one-time passcode is pending, the one-time passcode will also be cleared. Use OTPs only during active guest arrival windows.

### 1. `sesame5_ble.add_passcode`
Add a permanent, temporary, or one-time passcode to a Sesame Touch / Keypad.

```yaml
service: sesame5_ble.add_passcode
target:
  device_id: <KEYPAD_DEVICE_ID>
data:
  passcode: "889900"
  name: "Delivery Guy"
  duration: 3600    # Valid for 1 hour (optional; empty = permanent)
  one_time: true    # Automatically deleted after first unlock (optional)
```

### 2. `sesame5_ble.delete_passcode`
Remove a passcode from the keypad by name (from `sesame5_ble.get_passcodes`) or PIN digits.

```yaml
service: sesame5_ble.delete_passcode
target:
  device_id: <KEYPAD_DEVICE_ID>
data:
  name: "Cleaner" # Or pass `passcode: "889900"`
```

### 3. `sesame5_ble.get_passcodes`
Retrieve all registered passcodes from the keypad.

```yaml
service: sesame5_ble.get_passcodes
target:
  device_id: <KEYPAD_DEVICE_ID>
```

---

## 💡 Automation Examples

### Turn on lights when door is unlocked from outside after sunset
```yaml
alias: "Night Outdoor Unlock - Turn on Lights"
description: "Turn on hallway light when unlocked via keypad, fingerprint, or card after sunset."
trigger:
  - platform: state
    entity_id: lock.front_door_sesame_5
    to: "unlocked"
condition:
  - condition: sun
    after: sunset
    before: sunrise
  # Ensure the unlock was initiated from outside (keypad/card/fingerprint)
  - condition: template
    value_template: >-
      {{ state_attr('sensor.front_door_last_operation', 'method') in ['keypad', 'card', 'fingerprint'] }}
action:
  - service: light.turn_on
    target:
      entity_id: light.hallway_light
```

---

## ❓ Troubleshooting & FAQ

<details>
<summary><b>1. Bluetooth connection drops or fails to connect?</b></summary>
Sesame locks use low-power BLE transmitters. If the distance between your Home Assistant host and the lock exceeds 5-8 meters or passes through thick concrete walls, signal attenuation will cause disconnects. 
We strongly recommend placing an inexpensive <b>ESP32 Bluetooth Proxy</b> (running ESPHome) near the entrance door.
</details>

<details>
<summary><b>2. Difference between Real-time mode and Power-saving mode?</b></summary>
<ul>
  <li><b>Real-time mode</b>: Keeps BLE connection active. Status changes and manual unlocks are reported in sub-second latency. Ideal for automation and one-time passcodes. Battery consumption is slightly higher (~10-15% increase, batteries typically last 8-12 months).</li>
  <li><b>Power-saving mode</b>: Disconnects immediately after operations. Battery lasts maximum time (up to 1-2 years), but manual lock/unlock status changes cannot be received until the next poll.</li>
</ul>
</details>

---

## 🤝 Attribution & Acknowledgments

- Special thanks to **[@ngoc-minh-do](https://github.com/ngoc-minh-do)** for the pioneering work on [ha-sesame-ble](https://github.com/ngoc-minh-do/ha-sesame-ble) (MIT License), which established the foundation for Sesame BLE integration in Home Assistant.
- Thanks to **[@meronepy](https://github.com/meronepy)** for [gomalock](https://github.com/meronepy/gomalock) (MIT License) for SesameOS 3 protocol insights and reference.
- Thanks to **[CANDY HOUSE, Inc.](https://candyhouse.co/)** for building high-quality smart locks and providing developer-friendly documentation.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE). See [LICENSE](LICENSE) and [NOTICE](NOTICE) for third-party copyright notices.
