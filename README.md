# OITELUシステム | REST APIサーバー & 子機クライアント

このプロジェクトは、Flask+SQLiteによるREST APIサーバー（親機）と、NFC・モーター制御を行うPythonスクリプト（子機）で構成されています。

---

## ディレクトリ構成

```
oiteru_250809_restAPI/
├── app.py                  # Flask REST APIサーバー本体（親機）
├── unit_client.py          # 子機クライアント（NFC・モーター制御）
├── requirements.txt        # 必要なPythonパッケージ一覧
├── README.md               # このファイル
├── oiteru.sqlite3          # サーバー用データベース
├── userdb.sqlite3          # 旧ユーザーデータベース
├── static/
│   ├── css/
│   │   └── style20250506.css
│   └── img/
│       └── logo20250506.png
├── templates/              # Flask用HTMLテンプレート
│   ├── base.html
│   ├── index.html
│   ├── register.html
│   ├── usage.html
│   ├── usage_result.html
│   ├── usage_error.html
│   ├── usage_status.html
│   ├── admin_login.html
│   ├── admin_dashboard.html
│   ├── admin_users.html
│   ├── admin_user_detail.html
│   ├── admin_units.html
│   ├── admin_unit_detail.html
│   ├── admin_new_unit.html
│   ├── admin_history.html
│   └── admin_restore.html
└── ...（その他のファイルやサンプルスケッチ等）
```

---

## 主な機能

### 親機 (app.py)

- 利用者情報（カードIDなど）の管理
- 子機の接続状態や在庫数の管理
- Webブラウザを通じた管理ダッシュボード
- データのバックアップと復元

#### セットアップ方法

1. 必要なパッケージをインストール
    ```sh
    pip install -r requirements.txt
    ```
2. サーバーを起動
    ```sh
    python app.py
    ```

#### 主なAPIエンドポイント

- `GET /api/users` : 全ユーザーの一覧を取得
- `GET /api/users/<card_id>` : 指定カードIDのユーザー情報を取得
- `POST /api/record_usage` : 利用を記録
- `POST /api/unit/heartbeat` : 子機からの生存確認

---

### 子機 (unit_client.py)

Raspberry Pi上で動作し、NFCカードの読み取りとモーター制御を行うスクリプトです。

#### 特徴

スクリプト冒頭の「かんたん設定」セクションを編集するだけで、以下の動作を簡単に切り替えられます。

- モーターの種類: サーボモーター / ステッピングモーター
- 制御方法: ラズパイ直結 (PCA9685) / Arduino経由 (シリアル通信)
- センサーの有無: 排出検知センサーの利用 / 非利用
- GPIOピン番号やArduinoポート名も簡単に変更可能

#### ハードウェア構成例

##### 構成1：Arduino経由のステッピングモーター

1. Raspberry PiとArduinoをUSBケーブルで接続
2. Arduinoのピン(8,9,10,11)をULN2003ドライバーのIN1〜IN4に接続
3. Raspberry PiのGPIOピン(BCM 22)に排出検知センサーを接続
4. ULN2003ドライバーにステッピングモーターと外部電源(5V)を接続
5. 付属の.inoファイルをArduinoに書き込み

##### 構成2：ラズパイ直結のサーボモーター

1. Raspberry PiのI2CピンをPCA9685ドライバーに接続
2. PCA9685ドライバーの任意のチャンネル（例: 15）にサーボモーターを接続
3. Raspberry PiのGPIOピン(BCM 22)に排出検知センサーを接続

#### 注意事項

- `unit_client.py`を実行する前に、スクリプト上部の「かんたん設定」セクションで使用するハードウェア構成に合わせて設定を変更してください。
- NFCリーダーが未接続の場合、カード読み取り機能は動作しません。

---
