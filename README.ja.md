# Sesame 5 BLE for Home Assistant (日本語)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/default)
[![GitHub Release](https://img.shields.io/github/v/release/kanshurichard/ha-sesame5-ble?style=for-the-badge&color=blue)](https://github.com/kanshurichard/ha-sesame5-ble/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-blue.svg?style=for-the-badge&logo=home-assistant)](https://www.home-assistant.io)

[English](README.md) | [简体中文](README.zh-CN.md) | **日本語**

**CANDY HOUSE セサミ 5 (Sesame 5)**、**セサミ 5 Pro**、および **セサミタッチ / キーパッド** (**SesameOS 3** 搭載) を Home Assistant から Bluetooth Low Energy (BLE) 経由で完全ローカル直接制御するためのカスタムインテグレーションです。

---

## ✨ 主な機能

- **🔒 100% 完全ローカル BLE 接続**: クラウド、Wi-Fiモジュール、外部ゲートウェイは一切不要。インターネット回線が切断されても、ローカル完結でゼロ遅延操作が可能です。
- **⚡ SesameOS 3 暗号化プロトコル完全対応**: ECDH P-256 楕円曲線暗号による公開鍵共有および AES-CMAC メッセージ認証をネイティブ実装。
- **📱 幅広いハードウェアに対応**:
  - **Sesame 5 & Sesame 5 Pro**
  - **Sesame Touch 1 / Touch 1 Pro & Touch 2 / Touch 2 Pro** (暗証番号・指紋・ICカード、全シリーズ対応)
  - **Sesame Bike 2 & Sesame Bike 3** (自転車ロック)
  - **Sesame Bot 2 & Sesame Bot 3** (ボタンロボット)
  - **Sesame 5 US** (北米モデル)
  - **Sesame 6 & Sesame 6 Pro** (最新世代スマートロック)
  - **Sesame Face 1 & Sesame Face 1 Pro** (顔認証モデル)
- **🔄 柔軟なデュアル接続モード**:
  - **リアルタイム常時接続モード (推奨)**: BLE 常時接続とキープアライブを維持し、即時状態反映 (<1秒)、手動解錠検知、解錠オートメーション、ワンタイム暗証番号の自動削除をフルサポート。
  - **省電力モード**: 操作時のみオンデマンドで接続し、待機時は切断することでバッテリー寿命を最大化。
- **🔑 タッチ / キーパッドの暗証番号管理機能**:
  - Home Assistant から恒久暗証番号を直接追加。
  - 有効期間 (秒数) を指定した一時暗証番号の発行 (期限切れ後にキーパッドから自動削除)。
  - **ワンタイム暗証番号 (OTP)** の発行 (連携したスマートロックがその番号で解錠されると、即座にキーパッドから自動削除)。家事代行や配送業者向けに最適。
  - 登録済み暗証番号一覧の取得や削除サービス。
- **📊 充実したセンサー群**: ロック状態、バッテリー残量 (%)、電圧 (V)、サムターン角度 (°)、モーター稼働状態、最終操作履歴 (誰がどのように解錠したか)、登録認証情報数。
- **🛡️ 読み取り専用保護モード**: 誤操作防止のため、センサー状態監視のみを許可し、遠隔施錠・解錠操作を無効化するセーフティ設定。
- **📡 ESP32 Bluetooth Proxy 完全対応**: ESPHome の Bluetooth Proxy を利用して、広い家や鉄筋コンクリート壁越しでも安定した BLE 通信エリアを構築可能。

---

## 📦 対応機種一覧

| デバイス | プロトコル型番 | 施錠 / 解錠 | リアルタイム状態 | バッテリー & 角度 | 暗証番号管理 |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **Sesame 5** | 5 | ✅ | ✅ | ✅ | — |
| **Sesame 5 Pro** | 7 | ✅ | ✅ | ✅ | — |
| **Sesame 5 US** | 16 | ✅ | ✅ | ✅ | — |
| **Sesame 6 / 6 Pro** | 20, 21 | ✅ | ✅ | ✅ | — |
| **Sesame Bike 2 / 3** | 6, 33 | ✅ | ✅ | ✅ | — |
| **Sesame Touch 1 / 2 & Pro** | 9, 10, 25, 26 | — | ✅ | ✅ | ✅ (暗証番号) |
| **Sesame Bot 2 / 3** | 17, 35 | ✅ | ✅ | ✅ | — |
| **Sesame Face 1 / Pro** | 18, 19 | — | ✅ | ✅ | ✅ (暗証番号) |

---

## 🚀 インストール方法

### 方法 1: HACS によるインストール (推奨)

1. Home Assistant の **HACS** を開きます。
2. 右上のメニュー `⋮` から **カスタムリポジトリ (Custom repositories)** を選択します。
3. リポジトリ URL に以下を入力します：
   ```text
   https://github.com/kanshurichard/ha-sesame5-ble
   ```
4. カテゴリに **インテグレーション (Integration)** を選択し、**追加** をクリックします。
5. HACS ストアで **Sesame 5 BLE** を検索してダウンロードします。
6. Home Assistant を再起動します。

### 方法 2: 手動インストール

1. [Releases ページ](https://github.com/kanshurichard/ha-sesame5-ble/releases) から最新の `.zip` ファイルをダウンロードします。
2. 解凍後、`custom_components/sesame5_ble` フォルダを Home Assistant の `<config_dir>/custom_components/` に配置します：
   ```text
   <config_dir>/custom_components/sesame5_ble/
   ```
3. Home Assistant を再起動します。

---

## 🔑 シークレットキー (QRコード) の取得方法

ペアリングには公式 セサミアプリからエクスポートした **合鍵情報 (Secret Key)** が必要です：

1. スマートフォンの公式 **セサミアプリ** を開きます。
2. 対象の Sesame 5 またはセサミタッチを選択します。
3. 右上の **設定** アイコン → **鍵をシェア** → **オーナー鍵 (またはマネージャー鍵)** を選択します。
4. **QRコード** を表示させます。
5. スクリーンショットまたは QR コードリーダーでテキストを読み取ります：
   - フル URL (例: `ssm://UI?k=...` や Web リンク)
   - Base64 文字列、または 32 文字の 16進数キー
6. 本インテグレーションは主要なフォーマットを自動判別してデコードします。

---

## ⚙️ ペアリングと初期設定

1. Home Assistant の **設定** → **デバイスとサービス** → **統合を追加** を開きます。
2. **Sesame 5 BLE** を検索します。
3. スキャンされた Bluetooth 一覧からお使いの Sesame を選択します (または手動で MAC アドレスを入力)。
4. 取得した **シークレットキーまたは QR コード URL** を貼り付けます。
5. 接続オプションを設定します：
   - **接続モード**: 玄関ドアには **リアルタイム常時接続** を推奨します。
   - **履歴タグ (History Tag)**: アプリの解錠履歴に記録される名前 (デフォルト: `HA`)。
   - **読み取り専用モード**: 遠隔施錠・解錠を禁止し、状態監視のみを行う場合は有効化。
6. **セサミタッチ / キーパッドの場合**: **連携するスマートロック** を選択してください。対象のロックが暗証番号で解錠された際、ワンタイム暗証番号の自動削除が実行されます。

---

## 🛠️ サービス一覧 (暗証番号管理)

> [!WARNING]
> ### ⚠️ 一時暗証番号およびワンタイム暗証番号に関する重要事項と制約
> 1. **Home Assistant 側でのソフトウェア管理**: Sesame Touch 本体のファームウェアには、暗証番号の有効期限やワンタイム自動消去の概念はありません。一時暗証番号 (`duration`) およびワンタイム暗証番号 (`one_time`) の自動削除はすべて Home Assistant がタイマーおよび解錠イベントを検知して BLE 経由で削除命令を送信することで実現されています。
> 2. **BLE 接続の依存関係**: 有効期限の到来時または解錠時、HA はキーパッドと BLE 接続を確立して削除を実行します。**その瞬間にキーパッドが休眠中、電波圏外、または HA が停止していた場合、暗証番号は自動削除されず残存します**。接続復帰後に手動で削除サービスを実行してください。
> 3. **ワンタイム暗証番号の動作仕様**: SesameOS 3 の仕様上、ドアロック側は「キーパッドの暗証番号で解錠された」というイベントのみを報告し、**どの番号が入力されたかまでは通知されません**。そのため、連携したロックで**任意の暗証番号による解錠が行われた場合、登録されているワンタイム暗証番号が自動削除されます**（居住者が常駐暗証番号で解錠した場合も含みます）。確実に来訪者が解錠するタイミングに合わせて発行することを推奨します。

### 1. `sesame5_ble.add_passcode` (暗証番号の追加)
キーパッドに恒久暗証番号、一時暗証番号、ワンタイム暗証番号を登録します。

```yaml
service: sesame5_ble.add_passcode
target:
  device_id: <キーパッドのデバイスID>
data:
  passcode: "889900"
  name: "配達業者様"
  duration: 3600    # 有効期限 1時間 (3600秒)。無期限の場合は省略。
  one_time: true    # 1回解錠後に自動でキーパッドから削除。
```

### 2. `sesame5_ble.delete_passcode` (暗証番号の削除)
キーパッドから登録名（`get_passcodes` で取得）または暗証番号（数字）を指定して削除します。

```yaml
service: sesame5_ble.delete_passcode
target:
  device_id: <キーパッドのデバイスID>
data:
  name: "清掃スタッフ" # または `passcode: "889900"`
```

### 3. `sesame5_ble.get_passcodes` (暗証番号一覧の取得)
現在登録されている暗証番号の一覧をキーパッドから読み出します。

```yaml
service: sesame5_ble.get_passcodes
target:
  device_id: <キーパッドのデバイスID>
```

---

## 💡 オートメーション設定例

### 日没後に室外から解錠された際に玄関照明を自動点灯
```yaml
alias: "夜間の室外解錠で玄関照明を点灯"
description: "日没から日の出までの間、キーパッド・指紋・カードで解錠された場合に玄関ライトを点灯します。"
trigger:
  - platform: state
    entity_id: lock.front_door_sesame_5
    to: "unlocked"
condition:
  - condition: sun
    after: sunset
    before: sunrise
  # 室外からの解錠 (暗証番号/指紋/ICカード) のみを対象とし、室内手動解錠を除外
  - condition: template
    value_template: >-
      {{ state_attr('sensor.front_door_last_operation', 'method') in ['keypad', 'card', 'fingerprint'] }}
action:
  - service: light.turn_on
    target:
      entity_id: light.entrance_light
```

---

## ❓ よくある質問 (FAQ)

<details>
<summary><b>1. Bluetooth 接続が不安定、または切断される？</b></summary>
Sesame は省電力のため微弱な BLE 電波を使用しています。Home Assistant ホストとの距離が 5m を超える場合や、壁・ドアなどの遮蔽物がある場合は電波が減衰します。
玄関付近に安価な <b>ESP32 (ESPHome Bluetooth Proxy)</b> を設置することで、通信の安定性が大幅に向上します。
</details>

<details>
<summary><b>2. リアルタイム常時接続と省電力モードの違いは？</b></summary>
<ul>
  <li><b>リアルタイム常時接続 (推奨)</b>: BLE を常時接続し、ミリ秒単位で解錠・施錠を検知します。オートメーションやワンタイム暗証番号の自動削除に最適です。電池寿命は約 8〜12 ヶ月です。</li>
  <li><b>省電力モード</b>: 指示を出した時のみ接続します。電池寿命は最大化されます (1〜2年) が、手動解錠の即時検知は次回ポーリングまで行われません。</li>
</ul>
</details>

---

## 🤝 謝辞

- Sesame BLE プロトコルの基礎を築いた **[@ngoc-minh-do](https://github.com/ngoc-minh-do)** 氏の先駆的なプロジェクト [ha-sesame-ble](https://github.com/ngoc-minh-do/ha-sesame-ble)（MIT License）に心より感謝申し上げます。
- SesameOS 3 プロトコルの実装参考として **[@meronepy](https://github.com/meronepy)** 氏の [gomalock](https://github.com/meronepy/gomalock)（MIT License）に感謝申し上げます。
- 素晴らしいハードウェアと開発者フレンドリーな環境を提供してくださっている **[CANDY HOUSE 株式会社](https://candyhouse.co/)** に感謝いたします。

---

## 📄 ライセンス

本プロジェクトは [MIT ライセンス](LICENSE) の下で公開されています。サードパーティの著作権表示は [LICENSE](LICENSE) および [NOTICE](NOTICE) をご参照ください。
