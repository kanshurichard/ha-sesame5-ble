# Sesame 5 BLE Home Assistant 蓝牙本地集成

[![HACS Custom Repository](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1+-blue.svg)](https://www.home-assistant.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

基于 Python 与 Home Assistant 蓝牙协议栈开发的 **CANDY HOUSE Sesame 5 / 5 Pro 智能锁本地 BLE 控制集成**。

无需 Wi-Fi 模块、无需网关或第三方云端 API，100% 本地直连通信，开锁响应毫秒级。

本项目参考并结合了 [`gomalock`](https://github.com/meronepy/gomalock) 与 [`ha-sesame-ble`](https://github.com/ngoc-minh-do/ha-sesame-ble) 的技术实现与协议反向成果。

---

## 主要特性

- **100% 局域网本地控制**：通过蓝牙 BLE 直连 Sesame 5，无需网络或云端，安全且响应迅速。
- **省电架构**：默认采用按需连接模式（执行开锁/关锁时毫秒级建立连接，操作完成后自动断开释放连接，最大程度延长门锁电池寿命）。
- **零额外依赖库**：利用 Home Assistant 核心自带的 `cryptography`（C加速）与 `bleak` 实现 AES-CMAC 与 AES-CCM 认证加密，无需在宿主机额外安装编译 `pycryptodome`。
- **完整实体支持**：
  - **锁实体 (Lock)**：施锁、解锁、门开/弹锁（`open`）、旋转/切换（`toggle`）、动作中过渡状态（`locking` / `unlocking`）。
  - **传感器 (Sensors)**：电量百分比（`%`）、电池电压（`V`）、旋钮当前角度（`°`）。
  - **二进制传感器 (Binary Sensors)**：低电量告警、电机旋转运转状态。
- **极简配网流程**：自动发现附近蓝牙门锁，支持直接粘贴官方 App 分享的二维码链接（`ssm://UI?t=sk&sk=...`）、Base64 字符串或 32 位 Hex 密匙。
- **原生多语言**：简体中文、English、日本語。

---

## 支持设备列表

| 型号 ID | 设备名称 | 运行协议 |
| :--- | :--- | :--- |
| **5** | **SESAME 5** | SesameOS 3 |
| **7** | **SESAME 5 Pro** | SesameOS 3 |
| **16** | **SESAME 5 US** | SesameOS 3 |
| **6** | **SESAME Bike 2** | SesameOS 3 |
| **17** | **SESAME Bot 2** | SesameOS 3 |
| **20 / 21** | **SESAME 6 / 6 Pro** | SesameOS 3 |
| **9 / 10 / 25 / 26** | **SESAME Touch 1/2 系列** | SesameOS 3 |

---

## 安装方法

### 方式 1：通过 HACS 安装（推荐）

1. 进入 Home Assistant 的 **HACS** 界面。
2. 点击右上角菜单 **⋮** → **自定义存储库 (Custom repositories)**。
3. 添加存储库地址：`https://github.com/kanshurichard/ha-sesame5-ble`（或你 Fork 的仓库地址），类别选择 **Integration（集成）**。
4. 搜索 **Sesame 5 BLE**，点击下载安装后重启 Home Assistant。

### 方式 2：手动拷贝安装

1. 下载本仓库中的 `custom_components/sesame5_ble` 文件夹。
2. 将其复制到 Home Assistant 配置目录的 `custom_components/` 路径下：
   ```
   /config/custom_components/sesame5_ble/
   ```
3. 重启 Home Assistant。

---

## 配置与配对教程

1. 打开 Home Assistant，进入 **设置** → **设备与服务** → **添加集成**。
2. 搜索并选择 **Sesame 5 BLE**。
3. 在扫描到的蓝牙设备列表中选择您的智能锁（或手动输入蓝牙 MAC 地址）。
4. **获取 Secret Key**：
   - 打开手机官方 **Sesame** App。
   - 点击你的设备设置 → **合鍵共有 (Share Key)** → **QR Code**。
   - 扫描或复制二维码内容：
     - 可以直接粘贴以 `ssm://UI?t=sk&sk=...` 开头的**完整 URL**！
     - 也可以粘贴二维码内解析出的 **Base64 字符串**。
     - 或者直接输入 32 位的 Hex 密匙。
5. 点击提交，集成将自动完成 BLE 握手与初次状态同步。

---

## 集成选项设置

添加完成后，点击设备条目上的 **配置 (Configure)** 可以调整：

- **定期刷新间隔 (分钟)**：
  - `0` *(默认，强烈推荐)*：仅按需连接。仅在开锁/关锁或手动请求时建立连接，极大提升门锁续航。
  - `> 0`：每隔 N 分钟后台连接门锁同步一次电池电压和角度信息。
- **开门记录标记 (History Tag)**：在官方 Sesame App 开锁历史记录中显示的名称（默认：`HA`）。

---

## 开源协议

本项目采用 [MIT License](LICENSE)。
