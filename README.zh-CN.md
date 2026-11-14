# Sesame 5 BLE for Home Assistant (中文版)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/default)
[![GitHub Release](https://img.shields.io/github/v/release/kan/ha-sesame5-ble?style=for-the-badge&color=blue)](https://github.com/kanshurichard/ha-sesame5-ble/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-blue.svg?style=for-the-badge&logo=home-assistant)](https://www.home-assistant.io)

[English](README.md) | **简体中文** | [日本語](README.ja.md)

专为 **CANDY HOUSE Sesame 5（五代）**、**Sesame 5 Pro** 及 **Sesame Touch / 密码键盘**（运行 **SesameOS 3** 协议）打造的现代化、高性能 Home Assistant 原生低功耗蓝牙（BLE）本地直连集成。

---

## ✨ 核心特性

- **🔒 100% 纯本地 BLE 直连**：通过蓝牙直接与门锁通信，无需 Wi-Fi 网关、无需云端账户、断网仍可正常控制，拥有真正的零延迟与极致隐私。
- **⚡ 完整支持 SesameOS 3 协议栈**：原生支持 ECDH P-256 椭圆曲线非对称密钥协商与 AES-CMAC 消息防篡改校验。
- **📱 广泛的硬件型号兼容**：
  - **Sesame 5 与 Sesame 5 Pro**
  - **Sesame Touch 1 / Touch 1 Pro**（密码与指纹刷卡面板）
  - **Sesame Bike 2**（自行车锁）
  - **Sesame Bot 2**（开关机器人）
  - **Sesame 5 US**（美标锁）
  - **Sesame Face 1 Pro**（人脸识别锁）
- **🔄 双连接模式自由切换**：
  - **实时长连接模式 (强烈推荐)**：保持蓝牙常连，心跳保活；支持毫秒级状态同步上报、开锁即时自动化联动，以及单次临时密码开门后秒级自毁。
  - **低功耗省电模式**：按需连接或定时轮询，闲置即断开，最大化延长门锁电池寿命。
- **🔑 Touch 密码键盘高级管理**：
  - 支持直接在 Home Assistant 中添加永久密码。
  - 支持设定有效时长（秒）的限时访客密码（过期自动从键盘注销）。
  - 支持**单次密码 (OTP)**：关联门锁检测到密码开门后，自动连线并立即销毁该临时密码，完美适配保洁、外卖与租客场景。
  - 提供密码列表查询与精准删除等服务。
- **📊 完备的实体传感器群**：锁舌开/关状态、电池百分比 (%)、电池电压 (V)、锁舌转角 (°)、电机运转状态、开锁方式与操作者记录、键盘各类凭据计数等。
- **🛡️ 只读保护模式**：在配对或选项中可随时开启，仅监控状态与电量，禁止下发开关锁指令，防止误触。
- **📡 完美兼容 ESP32 蓝牙代理**：支持 ESPHome 蓝牙代理（Bluetooth Proxy），轻松穿透大户型与承重墙。

---

## 📦 支持设备列表

| 设备名称 | 协议型号代号 | 开锁 / 关锁 | 实时状态 | 电池与角度 | 密码管理 |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **Sesame 5** | 5 | ✅ | ✅ | ✅ | — |
| **Sesame 5 Pro** | 7 | ✅ | ✅ | ✅ | — |
| **Sesame 5 US** | 16 | ✅ | ✅ | ✅ | — |
| **Sesame Bike 2** | 6 | ✅ | ✅ | ✅ | — |
| **Sesame Touch 1 / Pro** | 9, 10 | — | ✅ | ✅ | ✅ (密码增删) |
| **Sesame Bot 2** | 17 | ✅ | ✅ | ✅ | — |
| **Sesame Face 1 Pro** | 18 | — | ✅ | ✅ | ✅ (密码增删) |

---

## 🚀 安装步骤

### 方式一：通过 HACS 安装（推荐）

1. 打开 Home Assistant 的 **HACS** 页面。
2. 点击右上角菜单 `⋮`，选择 **自定义存储库（Custom repositories）**。
3. 填入存储库地址：
   ```text
   https://github.com/kanshurichard/ha-sesame5-ble
   ```
4. 类别选择 **集成 (Integration)**，点击 **添加**。
5. 在 HACS 列表中搜索 **Sesame 5 BLE**，点击下载并安装。
6. 重启 Home Assistant。

### 方式二：手动安装

1. 从 [Releases 页面](https://github.com/kanshurichard/ha-sesame5-ble/releases) 下载最新的 `.zip` 发布包。
2. 解压后将 `custom_components/sesame5_ble` 文件夹复制到 Home Assistant 配置目录的 `custom_components/` 下：
   ```text
   <config_dir>/custom_components/sesame5_ble/
   ```
3. 重启 Home Assistant。

---

## 🔑 获取密匙（Secret Key / 二维码）

配对前需从官方 Sesame App 中导出设备的 **密钥信息**：

1. 在手机上打开官方 **Sesame App**。
2. 点击进入您的 Sesame 5 锁或 Touch 键盘详情页。
3. 点击右上角 **设置** 图标 → **分享合键** → 选择 **主人 / 管理者**。
4. 点击生成 **二维码**。
5. 截图或使用扫码工具解析出二维码文本：
   - 支持完整的 URL（例如 `ssm://UI?k=...` 或网页链接）；
   - 也支持纯 Base64 编码字符串或 32 位十六进制密钥。
6. 本集成内置智能解析器，自动识别并解码各类标准格式！

---

## ⚙️ 配对与配置指南

1. 进入 Home Assistant 的 **设置** → **设备与服务** → **添加集成**。
2. 搜索 **Sesame 5 BLE**。
3. 从扫描到的蓝牙列表中选择您的 Sesame 设备（或选择 **手动输入** MAC 地址）。
4. 粘贴复制好的 **Secret Key 或二维码 URL**。
5. 根据需要选择配置项：
   - **连接模式**：入户大门建议选择 **实时长连接模式**；
   - **开门记录标记 (History Tag)**：门锁操作记录中显示的名称（默认 `HA`）；
   - **只读保护模式**：开启后仅监控状态，禁止远程操作。
6. 若添加的是 **Sesame Touch / 密码键盘**：请务必选择 **关联门锁**。当通过密码开启该门锁时，系统将触发单次密码的即时销毁机制。

---

## 🛠️ 服务说明（密码管理）

### 1. `sesame5_ble.add_passcode` (添加密码)
向密码键盘下发永久密码、临时限时密码或单次密码：

```yaml
service: sesame5_ble.add_passcode
target:
  device_id: <键盘设备ID>
data:
  passcode: "889900"
  name: "保洁阿姨"
  duration: 3600    # 有效期 1 小时 (3600 秒)，到期后自动删除；留空为永久
  one_time: true    # 开锁一次后自动从键盘中销毁删除
```

### 2. `sesame5_ble.delete_passcode` (删除密码)
从键盘中删除指定密码：

```yaml
service: sesame5_ble.delete_passcode
target:
  device_id: <键盘设备ID>
data:
  passcode: "889900" # 填入要删除的数字密码或16进制ID
```

### 3. `sesame5_ble.get_passcodes` (获取密码列表)
读取当前键盘内已注册的全部密码：

```yaml
service: sesame5_ble.get_passcodes
target:
  device_id: <键盘设备ID>
```

---

## 💡 自动化示例

### 夜间门外解锁自动开启玄关灯
```yaml
alias: "夜间门外解锁自动开灯"
description: "日落后至次日日出前，从门外（键盘、指纹或卡片）开门时自动打开走廊灯"
trigger:
  - platform: state
    entity_id: lock.front_door_sesame_5
    to: "unlocked"
condition:
  - condition: sun
    after: sunset
    before: sunrise
  # 确保是从门外通过密码/指纹/卡片解锁（排除门内旋钮手动开锁）
  - condition: template
    value_template: >-
      {{ state_attr('sensor.front_door_last_operation', 'method') in ['keypad', 'card', 'fingerprint'] }}
action:
  - service: light.turn_on
    target:
      entity_id: light.hallway_light
```

---

## ❓ 常见问题（FAQ）

<details>
<summary><b>1. 蓝牙连接断断续续或提示配对超时？</b></summary>
Sesame 为节约电量采用微功率蓝牙发射器。如果 Home Assistant 主机与门锁距离超过 5 米或隔有承重墙，信号会明显衰减。
强烈建议在玄关附近插一个十几元成本的 <b>ESP32（刷入 ESPHome 蓝牙代理）</b>，本集成能自动借由蓝牙代理无缝通信。
</details>

<details>
<summary><b>2. 实时长连接模式与省电模式有什么区别？</b></summary>
<ul>
  <li><b>实时长连接模式 (推荐)</b>：持续保持蓝牙连线，毫秒级响应，手动转动或门外开锁立刻感知并触发自动化。电池使用寿命约为 8~12 个月。</li>
  <li><b>省电模式</b>：仅在执行动作时连线，平时完全断开。电池寿命可达 1~2 年，但无法实时获知他人手动开锁状态，直到下一次轮询。</li>
</ul>
</details>

---

## 🤝 致谢与致敬

- 特别鸣谢 **[@ngoc-minh-do](https://github.com/ngoc-minh-do)** 打造的 [ha-sesame-ble](https://github.com/ngoc-minh-do/ha-sesame-ble) 开创性项目，为 Home Assistant 社区支持 Sesame 蓝牙协议奠定了基础。
- 感谢 **[CANDY HOUSE, Inc.](https://candyhouse.co/)** 制造的高品质智能锁硬件及对开源开发者的友好支持。

---

## 📄 开源许可证

本项目基于 [MIT 许可证](LICENSE) 开源。
