import time
import requests
import nfc
import sys
import threading

# --------------------------------------------------------------------------
# --- ★★★ かんたん設定 (ここを編集してください) ★★★ ---
# --------------------------------------------------------------------------
# このセクションでは、お使いの環境に合わせて子機の動作をカスタマイズできます。

# === サーバー接続設定 ===
# 親機（メインのPC）のIPアドレスとポート番号
# 例: "http://192.168.1.10:5000"
SERVER_URL = "http://192.168.11.4:5000"

# === 子機情報 ===
# この子機を識別するための名前とパスワード
# 親機の管理画面で設定したものと一致させる必要があります。
UNIT_NAME = "raspi-01"
UNIT_PASSWORD = "password123"

# === モーターの種類 ===
# 使用するモーターの種類を選びます。
# ・サーボモーターの場合: 'SERVO'
# ・ステッピングモーターの場合: 'STEPPER'
MOTOR_TYPE = 'STEPPER'

# === モーターの制御方法 ===
# モーターをどのように制御するかを選びます。
# ・ラズパイに直接PCA9685ドライバーを接続する場合: 'RASPI_DIRECT'
# ・Arduinoを介して制御する場合: 'ARDUINO_SERIAL'
CONTROL_METHOD = 'ARDUINO_SERIAL'

# === センサーの利用設定 ===
# 排出を検知するセンサーを使うかどうかを選びます。
# ・センサーを使う場合: True
# ・センサーを使わない場合: False
USE_SENSOR = True

# === GPIOピン設定 ===
# Raspberry Piに接続されている部品のピン番号を指定します。
# ※ピン番号は「BCM」モードのものです。
GREEN_LED_PIN = 17  # 成功を示す緑色LED
RED_LED_PIN = 27    # 失敗を示す赤色LED
SENSOR_PIN = 22     # 排出検知センサー

# === Arduino接続設定 (Arduino経由の場合のみ) ===
# Raspberry PiとArduinoを接続しているUSBポートの名前
# `ls /dev/tty*` コマンドで調べて、'ttyACM0'や'ttyUSB0'などを指定します。
ARDUINO_PORT = '/dev/ttyACM0'

# --------------------------------------------------------------------------
# --- ★★★ 設定はここまで ★★★ ---
# --------------------------------------------------------------------------

import time
import requests
import nfc
import sys
import threading

# --- ライブラリの初期化 ---
PLATFORM = "RASPI"
if PLATFORM == "RASPI":
    try:
        import RPi.GPIO as GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(GREEN_LED_PIN, GPIO.OUT)
        GPIO.setup(RED_LED_PIN, GPIO.OUT)
        
        if CONTROL_METHOD == 'RASPI_DIRECT':
            import Adafruit_PCA9685
            print("INFO: モード -> ラズパイ直結 (PCA9685)")
        elif CONTROL_METHOD == 'ARDUINO_SERIAL':
            import serial
            print("INFO: モード -> Arduino経由 (シリアル通信)")
        
        if USE_SENSOR:
            GPIO.setup(SENSOR_PIN, GPIO.IN)
            print(f"INFO: センサーを利用します (GPIO {SENSOR_PIN})")
        else:
            print("INFO: センサーは利用しません。")

    except (ImportError, RuntimeError) as e:
        print(f"警告: ライブラリ読込失敗: {e}。PCモードで続行します。")
        PLATFORM = "PC"

# --- 親機サーバー連携 ---

def send_heartbeat():
    """定期的に親機にハートビートを送信する"""
    while True:
        try:
            payload = {"name": UNIT_NAME, "password": UNIT_PASSWORD}
            requests.post(f"{SERVER_URL}/api/unit/heartbeat", json=payload, timeout=5)
        except requests.exceptions.RequestException as e:
            print(f"!! ハートビート送信失敗: {e}")
        time.sleep(30) # 30秒ごとに送信

def check_server_connection():
    """親機サーバーとの接続を確認する"""
    try:
        response = requests.get(f"{SERVER_URL}/api/health", timeout=3)
        if response.status_code == 200 and response.json().get('status') == 'ok':
            print(f"◎ 親機サーバーとの接続に成功しました。 ({SERVER_URL})")
            return True
        else:
            print(f"!! 親機サーバーとの接続に失敗しました。ステータス: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"!! 親機サーバーに接続できません: {e}")
        return False

def send_log_to_server(message):
    """親機にログを送信する (子機名を添えて)"""
    log_message = f"[{UNIT_NAME}] {message}"
    print(f"[ログ送信] {log_message}")
    try:
        # 子機名とメッセージをセットで送信
        payload = {"unit_name": UNIT_NAME, "message": message}
        requests.post(f"{SERVER_URL}/api/log", json=payload, timeout=3)
    except requests.exceptions.RequestException as e:
        print(f"!! 親機へのログ送信に失敗しました: {e}")

# --- LED・モーター制御（Raspberry Piの場合のみ） ---

def indicate(status):
    """成功/失敗をLEDで示す"""
    if PLATFORM != "RASPI":
        return # PCモードでは何もしない

    if status == "success":
        pin = GREEN_LED_PIN
    else: # "failure"
        pin = RED_LED_PIN

    GPIO.output(pin, GPIO.HIGH)
    time.sleep(2)  # 2秒間点灯
    GPIO.output(pin, GPIO.LOW)

def dispense_with_raspi_direct():
    """【ラズパイ直結】PCA9685でサーボモーターとセンサーを制御"""
    print("INFO: ラズパイ直結でサーボモーターを制御します。")
    try:
        pwm = Adafruit_PCA9685.PCA9685()
        pwm.set_pwm_freq(60)
        gpio_sensor = 22
        GPIO.setup(gpio_sensor, GPIO.IN)
        time_start = time.time()
        attempts = 0
        while True:
            elapsed = time.time() - time_start
            sensor_val = GPIO.input(gpio_sensor)
            print(f'Time: {elapsed:.1f}s, Sensor: {sensor_val}')

            if sensor_val == 0:  # 反応あり: まだ排出されていない / 物が詰まり? -> 小刻み動作
                pwm.set_pwm(15, 0, 5)
                time.sleep(0.4)
                pwm.set_pwm(15, 0, 0)
                time.sleep(1)
                attempts += 1
                if attempts >= 5:
                    print("排出リミットに達しました。")
                    send_log_to_server("排出リミット到達 (5回)")
                    break
            else:  # 反応なし: 排出成功
                pwm.set_pwm(15, 0, 100)
                time.sleep(0.2)
                pwm.set_pwm(15, 0, 0)
                time.sleep(0.1)
                print("排出が完了しました。")
                send_log_to_server("排出完了")
                break
    except Exception as e:
        msg = f"モーター/センサー制御エラー: {e}"
        print(f"!! {msg}")
        send_log_to_server(msg)
        indicate("failure")
    finally:
        # センサーのみクリーンアップ (LED等は継続利用) ※存在しない場合の例外は無視
        try:
            GPIO.cleanup(gpio_sensor)
        except Exception:
            pass

def dispense_with_arduino_serial():
    """【Arduino経由】設定に応じてステッピングモーターを制御"""
    print(f"INFO: Arduino経由で制御開始 (センサー利用: {USE_SENSOR})")
    try:
        # 「かんたん設定」で指定されたポートに接続
        ser = serial.Serial(ARDUINO_PORT, 9600, timeout=1)
        time.sleep(2) # Arduinoの起動を待つ

        # === センサーを利用する場合のロジック ===
        if USE_SENSOR:
            print("センサーと連携したモーター制御を開始します。")
            # 無限ループを避けるため、最大15回（約3秒）でタイムアウト
            max_attempts = 15
            for attempt in range(max_attempts):
                time.sleep(0.2)
                input_sensor = GPIO.input(SENSOR_PIN)
                print(f"  -> 試行 {attempt + 1}: センサー値 = {input_sensor}")
                if input_sensor == 1:
                    print("     -> 前進命令 'F' を送信")
                    ser.write(b'F')
                else:
                    print("     -> 排出完了。微調整命令 'S' を送信")
                    ser.write(b'S')
                    break
            else:
                print("警告: タイムアウトしました。停止命令を送信します。")
                ser.write(b'S')
        else:
            print("センサーを使わず、固定動作命令 '1' を送信します。")
            ser.write(b'1')
        ser.close()
        print("✅ モーター制御完了。")
    except Exception as e:
        error_message = f"Arduino制御中にエラー発生: {e}"
        print(f"!! {error_message}")
        send_log_to_server(error_message)

def dispense_item():
    """設定に応じて適切なモーター制御関数を呼び出す"""
    if PLATFORM != "RASPI":
        print("モーター制御はRaspberry Piモードでのみ有効です。")
        return

    # 設定の組み合わせに応じて処理を分岐
    if MOTOR_TYPE == 'SERVO' and CONTROL_METHOD == 'RASPI_DIRECT':
        dispense_with_raspi_direct()
    elif MOTOR_TYPE == 'STEPPER' and CONTROL_METHOD == 'ARDUINO_SERIAL':
        dispense_with_arduino_serial()
    else:
        # サポートされていない組み合わせの場合
        error_message = f"未サポートのモーター設定です: MOTOR_TYPE='{MOTOR_TYPE}', CONTROL_METHOD='{CONTROL_METHOD}'"
        print(f"!! {error_message}")
        send_log_to_server(error_message)
        indicate("failure")

# --- NFCカード処理 ---
def handle_card_touch(tag):
    """NFCカードがタッチされた時のメイン処理"""
    if not isinstance(tag, nfc.tag.tt3.Type3Tag):
        return False

    card_id = tag.idm.hex()
    print(f"カードを検出: {card_id}")

    # 1. 親機にカード情報を問い合わせ
    try:
        response = requests.get(f"{SERVER_URL}/api/users/{card_id}", timeout=5)

        if response.status_code == 200:
            try:
                user = response.json()
            except Exception:
                send_log_to_server(f"サーバーから不正なレスポンス (JSONデコード失敗) ({card_id})")
                indicate("failure")
                return False

            # 2. 利用可能かチェック
            if int(user.get('allow', 0)) != 1:
                send_log_to_server(f"利用不許可のカード ({card_id})")
                indicate("failure")
                return False
            if int(user.get('stock', 0)) <= 0:
                send_log_to_server(f"在庫不足のため利用不可 ({card_id})")
                indicate("failure")
                return False

            # 3. 利用記録を親機に送信
            usage_response = requests.post(f"{SERVER_URL}/api/record_usage", json={"card_id": card_id}, timeout=5)
            if usage_response.status_code == 200:
                print("◎ 利用成功")
                send_log_to_server(f"利用を記録しました ({card_id})")
                indicate("success")
                dispense_item()  # 認証成功後に排出
                return True
            else:
                try:
                    error_msg = usage_response.json().get('error', '不明なエラー')
                except Exception:
                    error_msg = '不明なエラー (JSONデコード失敗)'
                send_log_to_server(f"利用記録に失敗: {error_msg} ({card_id})")
                indicate("failure")
                return False

        elif response.status_code == 404:
            send_log_to_server(f"未登録カードのため利用不可 ({card_id})")
            indicate("failure")
            return False
        else:
            send_log_to_server(f"サーバー問い合わせエラー: HTTP {response.status_code} ({card_id})")
            indicate("failure")
            return False

    except requests.exceptions.RequestException as e:
        print(f"!! 親機サーバーとの通信に失敗しました: {e}")
        indicate("failure")
        return False

# --- メイン処理 ---
if __name__ == "__main__":
    print(f"--- 子機クライアントを開始します (モード: {PLATFORM}) ---")
    print(f"接続先サーバー: {SERVER_URL}")
    print("Ctrl+Cで終了します。")

    # サーバー接続チェックを追加
    if not check_server_connection():
        print("!! 処理を中断します。サーバーの設定や起動状態を確認してください。")
        sys.exit(1) # 接続失敗時はスクリプトを終了する

    # ハートビート送信をバックグラウンドで開始
    heartbeat_thread = threading.Thread(target=send_heartbeat, daemon=True)
    heartbeat_thread.start()
    print("◎ ハートビート送信を開始しました。")

    clf = None
    try:
        # USB接続のNFCリーダーを初期化
        clf = nfc.ContactlessFrontend('usb')
        print("NFCリーダーの準備ができました。カードを待っています...")

        while True:
            # 接続待ち受け。rdwrにコールバック関数を指定。
            clf.connect(rdwr={'on-connect': handle_card_touch})
            # カード処理が終わったら、次の読み取りのために少し待つ
            time.sleep(1)

    except IOError:
        print("エラー: NFCリーダーが見つかりません。接続を確認してください。")
    except Exception as e:
        print(f"予期せぬエラーが発生しました: {type(e).__name__}: {e}", file=sys.stderr)
    finally:
        if clf:
            clf.close()
        if PLATFORM == "RASPI":
            GPIO.cleanup()
        print("\n--- スクリプトを終了します ---")