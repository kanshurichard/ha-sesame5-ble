# Sesame 5 BLE for Home Assistant

[![HACS Custom Repository](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1+-blue.svg)](https://www.home-assistant.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A clean, modern Home Assistant custom integration providing **100% local Bluetooth Low Energy (BLE)** control for **CANDY HOUSE Sesame 5**, **Sesame 5 Pro**, and other SesameOS 3 smart devices.

Inspired by and built upon the findings of [`gomalock`](https://github.com/meronepy/gomalock) and [`ha-sesame-ble`](https://github.com/ngoc-minh-do/ha-sesame-ble).

---

## Features

- **100% Local Control**: Communicates directly with the lock over Bluetooth Low Energy — no Wi-Fi module, bridge, or Candy House Cloud API needed.
- **Ultra-Fast & Battery-Friendly**: Uses on-demand BLE connection by default (connects, executes lock/unlock, and disconnects immediately to maximize lock battery life).
- **Zero Third-Party Pip Dependencies**: Uses Home Assistant's built-in `cryptography` and `bleak` libraries natively.
- **Rich Entities Provided**:
  - **Lock**: `Lock` (`is_locked`, `locking`, `unlocking`, `open` / unlatch).
  - **Sensors**: Battery Percentage (`%`), Battery Voltage (`V`), Thumb-turn Position (`°`).
  - **Binary Sensors**: Battery Low Warning, Motor Active.
- **Effortless Setup**: Accepts the raw QR Code URL (`ssm://UI?t=sk&sk=...`), the scanned Base64 string, or a 32-character Hex secret key.
- **Multi-language**: English, Simplified Chinese (简体中文), and Japanese (日本語).

---

## Supported Devices

| Model | Device Name | Protocol |
| :--- | :--- | :--- |
| **5** | **SESAME 5** | SesameOS 3 |
| **7** | **SESAME 5 Pro** | SesameOS 3 |
| **16** | **SESAME 5 US** | SesameOS 3 |
| **6** | **SESAME Bike 2** | SesameOS 3 |
| **17** | **SESAME Bot 2** | SesameOS 3 |
| **20 / 21** | **SESAME 6 / 6 Pro** | SesameOS 3 |
| **9 / 10 / 25 / 26** | **SESAME Touch 1/2 Series** | SesameOS 3 |

---

## Installation

### Method 1: HACS (Recommended)

1. Open **HACS** in your Home Assistant dashboard.
2. Click **Integrations** → **⋮ (top right menu)** → **Custom repositories**.
3. Add repository URL: `https://github.com/kan/ha-sesame5-ble` (or your local repo fork) with category **Integration**.
4. Search for **Sesame 5 BLE**, click **Download**, and restart Home Assistant.

### Method 2: Manual Installation

1. Download the `custom_components/sesame5_ble` folder from this repository.
2. Copy it into your Home Assistant configuration directory under:
   ```
   <config_dir>/custom_components/sesame5_ble
   ```
3. Restart Home Assistant.

---

## Configuration

1. In Home Assistant, navigate to **Settings** → **Devices & Services** → **Add Integration**.
2. Search for **Sesame 5 BLE**.
3. Select your nearby lock from the discovered devices list (or enter its Bluetooth MAC address manually).
4. **Obtain your Secret Key**:
   - Open the official **Sesame App** on your smartphone.
   - Go to your device's settings → **Share Key (合鍵共有)** → **QR Code**.
   - Share/Scan the QR code and copy the content:
     - You can paste the **entire QR Code URL** (`ssm://UI?t=sk&sk=...`) directly!
     - Or paste the **Base64 string** from the QR code.
     - Or paste a **32-character hex secret key**.
5. Click **Submit**. Home Assistant will authenticate directly with the lock over BLE.

---

## Integration Options

After adding the integration, click **Configure** on the device entry to adjust:

- **Periodic refresh interval** (minutes):
  - `0` *(Default & Recommended)*: **On-demand only**. Connects only when executing lock/unlock actions or when manually requesting update, saving maximum lock battery.
  - `> 0`: Periodically connects every N minutes to update battery and lock status in the background.
- **History Tag**: The name displayed in the Sesame mobile app's unlock history (Default: `HA`).

---

## License

This project is licensed under the [MIT License](LICENSE).
