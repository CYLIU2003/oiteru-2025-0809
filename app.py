import os
import sqlite3
import hashlib
import random
import io
import pandas as pd
import traceback
import re  # 利用履歴抽出用
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta  # timedelta を追加
from flask import (
    Flask, request, jsonify, render_template,
    redirect, url_for, session, flash, g, send_file
)
try:
    import nfc
except ImportError:
    nfc = None

 # --- Flaskアプリケーションの初期化 ---
# templates と static フォルダをデフォルトに変更
app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = 'oiteru_secret_key_2025_final'
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'oiteru.sqlite3')


# --- DB Helpers ---

# --- データベース接続ヘルパー ---
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

# --- データベース初期化 ---
def init_db():
    """データベースのテーブルを初期化する"""
    if os.path.exists(DB_PATH):
        print("データベースは既に存在します。")
        return

    print("新しいデータベースを作成・初期化します...")
    with app.app_context():
        db = get_db()
        with db:
            # usersテーブル
            db.execute('''
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    card_id TEXT UNIQUE NOT NULL,
                    allow INTEGER DEFAULT 1,
                    entry TEXT,
                    stock INTEGER DEFAULT 2,
                    today INTEGER DEFAULT 0,
                    total INTEGER DEFAULT 0,
                    last1 TEXT,
                    last2 TEXT,
                    last3 TEXT,
                    last4 TEXT,
                    last5 TEXT,
                    last6 TEXT,
                    last7 TEXT,
                    last8 TEXT,
                    last9 TEXT,
                    last10 TEXT
                )
            ''')
            # unitsテーブル
            db.execute('''
                CREATE TABLE units (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    stock INTEGER DEFAULT 0,
                    connect INTEGER DEFAULT 0,
                    available INTEGER DEFAULT 1,
                    last_seen TEXT
                )
            ''')
# --- DBマイグレーション ---
def migrate_db():
    """
    データベーススキーマをチェックし、不足しているカラムがあれば追加する。
    """
    print("データベースの構造をチェック・更新します...")
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        # unitsテーブルに 'last_seen' カラムが存在するか確認
        cursor.execute("PRAGMA table_info(units)")
        columns = [row['name'] for row in cursor.fetchall()]
        if 'last_seen' not in columns:
            print("  -> 更新: unitsテーブルに 'last_seen' カラムを追加します。")
            try:
                cursor.execute("ALTER TABLE units ADD COLUMN last_seen TEXT")
                db.commit()
                print("  -> 更新完了。")
            except Exception as e:
                print(f"  -> エラー: カラムの追加に失敗しました: {e}")
        else:
            print("  -> データベースは最新です。")

# --- ユーティリティ関数 ---
def add_history(text):
    db = get_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    db.execute("INSERT INTO history (txt) VALUES (?)", (f"{now}: {text}",))
    db.commit()

def check_password(password):
    db = get_db()
    info = db.execute("SELECT pass FROM info WHERE id = 1").fetchone()
    return info and info['pass'] == hashlib.sha256(password.encode()).hexdigest()


# ICカードリーダーからカードIDを同期的に読み取る
def read_card_id():
    """
    ICカードリーダーからカードIDを同期的に読み取る。
    タイムアウト付きでカードを待ち受け、成功すればカードID(str)、失敗すればNoneを返す。
    """
    try:
        # nfcpyがインストールされていない場合はエラー
        if nfc is None:
            flash("サーバー側でNFCライブラリ(nfcpy)が不足しています。", "error")
            return None

        # USB接続のリーダーに接続
        with nfc.ContactlessFrontend('usb') as clf:
            # 1.5秒間、3回の試行でカードを待つ (ブロッキング処理)
            target = clf.sense(nfc.clf.RemoteTarget('106A'), nfc.clf.RemoteTarget('106B'), nfc.clf.RemoteTarget('212F'), iterations=3, interval=0.5)

            if target is None:
                flash("ICカードを読み取れませんでした。リーダーにカードを置いてから、もう一度お試しください。", "error")
                return None

            # ターゲットを有効化してタグ情報を取得
            tag = nfc.tag.activate(clf, target)
            if hasattr(tag, 'idm'):
                return tag.idm.hex()
            else:
                flash("カード情報を正しく取得できませんでした。", "error")
                return None

    except IOError:
        flash("ICカードリーダーが見つかりません。USB接続を確認してください。", "error")
        return None
    except Exception as e:
        # その他の予期せぬエラー
        error_message = f"NFCリーダーで予期せぬエラーが発生しました: {e}"
        print(error_message)
        traceback.print_exc()
        flash(error_message, "error")
        return None

# --- UIルート ---

# ↓↓↓↓ ここから貼り付け ↓↓↓↓

@app.route("/admin/backup/download")
def admin_backup_download():
    """管理者向けにユーザーデータをExcel形式でダウンロードさせる"""
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))
    db = get_db()
    try:
        # データベースから全ユーザー情報を取得
        users_cursor = db.execute("SELECT * FROM users ORDER BY id")
        users = users_cursor.fetchall()
        users_list = [dict(row) for row in users]
        if not users_list:
            flash("バックアップ対象のユーザーデータがありません。", "warning")
            return redirect(url_for('admin_dashboard'))
        df = pd.DataFrame(users_list)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='users')
        output.seek(0)
        filename = f"backup_users_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        add_history("データバックアップ作成")
        return send_file(
            output,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        flash(f"バックアップファイルの作成中にエラーが発生しました: {e}", "error")
        add_history(f"バックアップ作成失敗: {e}")
        return redirect(url_for('admin_dashboard'))

@app.route('/admin/restore', methods=['GET', 'POST'])
def admin_restore():
    """バックアップファイルからユーザーデータを復元する"""
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    if request.method == 'POST':
        if 'backup_file' not in request.files:
            flash('ファイルが選択されていません。', 'error')
            return redirect(request.url)
        file = request.files['backup_file']
        if file.filename == '':
            flash('ファイルが選択されていません。', 'error')
            return redirect(request.url)
        if file and file.filename.endswith('.xlsx'):
            try:
                df = pd.read_excel(file)
                required_columns = ['card_id', 'allow', 'entry', 'stock', 'today', 'total']
                if not all(col in df.columns for col in required_columns):
                    flash('Excelファイルの形式が正しくありません。必須カラムが不足しています。', 'error')
                    return redirect(request.url)
                db = get_db()
                with db:
                    db.execute("DELETE FROM users")
                    df.to_sql('users', db, if_exists='append', index=False)
                add_history("データ復元完了")
                flash('データベースの復元が正常に完了しました。', 'success')
                return redirect(url_for('admin_users'))
            except Exception as e:
                add_history(f"データ復元エラー: {e}")
                flash(f'ファイルの処理中にエラーが発生しました: {e}', 'error')
                return redirect(request.url)
        else:
            flash('許可されていないファイル形式です。.xlsxファイルをアップロードしてください。', 'warning')
            return redirect(request.url)

    # GETリクエストの場合はアップロードフォームを表示
    return render_template('admin_restore.html')

@app.route('/admin/visuals')
def admin_visuals():
    """利用状況を可視化するページ (履歴ベース)"""
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    db = get_db()
    # 履歴から「利用を記録しました」というログのみを抽出
    logs = db.execute("SELECT txt FROM history WHERE txt LIKE '%利用を記録しました%'").fetchall()

    timestamps = []
    for log in logs:
        timestamp_str = log['txt'][:16]
        try:
            dt = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M")
            timestamps.append(dt)
        except (ValueError, TypeError):
            continue

    hourly_counts = [0] * 24
    daily_counts = {}
    weekly_counts = [0] * 7
    for ts in timestamps:
        hourly_counts[ts.hour] += 1
        day_str = ts.strftime("%Y-%m-%d")
        daily_counts[day_str] = daily_counts.get(day_str, 0) + 1
        weekly_counts[ts.weekday()] += 1
    sorted_daily = sorted(daily_counts.items())
    daily_labels = [item[0] for item in sorted_daily]
    daily_values = [item[1] for item in sorted_daily]
    chart_data = {
        'hourly_labels': [f"{h:02d}:00" for h in range(24)],
        'hourly_data': hourly_counts,
        'daily_labels': daily_labels,
        'daily_data': daily_values,
        'weekly_labels': ['月', '火', '水', '木', '金', '土', '日'],
        'weekly_data': weekly_counts
    }
    return render_template('admin_visuals.html', chart_data=chart_data)

@app.route('/admin/csv_export')
def admin_csv_export():
    """利用履歴をCSV形式でダウンロードする"""
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    db = get_db()
    logs = db.execute(
        "SELECT txt FROM history WHERE txt LIKE '%利用を記録しました%' ORDER BY id ASC"
    ).fetchall()
    if not logs:
        flash("ダウンロード対象の利用履歴がありません。", "warning")
        return redirect(url_for('admin_dashboard'))
    usage_data = []
    for log in logs:
        log_text = log['txt']
        timestamp_str = log_text[:16]
        match = re.search(r'\((\w+)\)', log_text)
        card_id = match.group(1) if match else '不明'
        usage_data.append({'timestamp': timestamp_str, 'card_id': card_id})
    df = pd.DataFrame(usage_data)
    output = io.StringIO()
    df.to_csv(output, index=False)
    output.seek(0)
    return send_file(
        io.BytesIO(output.read().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name='usage_history.csv'
    )

@app.route('/admin/log_export')
def admin_log_export():
    """全ての履歴ログをCSV形式でダウンロードする"""
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    db = get_db()
    # 履歴テーブルから全てのログをIDの昇順（古い順）で取得
    logs = db.execute("SELECT txt FROM history ORDER BY id ASC").fetchall()

    if not logs:
        flash("ダウンロード対象のログがありません。", "warning")
        return redirect(url_for('admin_dashboard'))

    # DataFrameに変換しやすいようにリストに格納
    log_data = [{'log_entry': log['txt']} for log in logs]
    df = pd.DataFrame(log_data)

    # CSVをメモリ上で作成
    output = io.StringIO()
    df.to_csv(output, index=False, header=['log']) # ヘッダーを'log'に指定
    output.seek(0)

    # ファイルとして送信
    return send_file(
        io.BytesIO(output.read().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name='all_history_logs.csv'
    )

# ↑↑↑↑ ここまで貼り付け ↑↑↑↑
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    # POSTリクエスト（登録ボタンが押された時）
    if request.method == "POST":
        # 課題1で作成した関数で、実際のカードIDを読み取る
        card_id = read_card_id()

        # カードIDが正常に読み取れた場合のみ処理を続行
        if card_id:
            db = get_db()
            try:
                # DBに新しいユーザーを登録
                now = datetime.now().strftime("%Y-%m-%d %H:%M")
                db.execute("INSERT INTO users (card_id, entry) VALUES (?, ?)", (card_id, now))
                db.commit()
                add_history(f"新規登録({card_id})")
                flash(f"登録が完了しました。(カードID: {card_id})", "success")
            except sqlite3.IntegrityError:
                # "UNIQUE"制約違反エラーを捕捉し、登録済みであることをユーザーに通知
                flash("この学生証は既に登録済みです。", "warning")
            except Exception as e:
                flash(f"データベース登録中にエラーが発生しました: {e}", "error")

        # read_card_id関数がNoneを返した場合、エラーメッセージは既に出ているのでここでは何もしない
        return redirect(url_for("register"))

    # GETリクエスト（ページ表示時）
    # ページ表示時にリーダーの接続状態を確認し、結果をテンプレートに渡す
    reader_connected = False
    try:
        if nfc:
            with nfc.ContactlessFrontend('usb'):
                reader_connected = True
    except Exception:
        reader_connected = False
        
    return render_template("register.html", reader_connected=reader_connected)



@app.route("/usage", methods=["GET", "POST"])
def usage():
    # POSTリクエスト（確認ボタンが押された時）
    if request.method == "POST":
        if 'retry' in request.form:
            return redirect(url_for('usage'))

        # 課題1で作成した関数で、実際のカードIDを読み取る
        card_id = read_card_id()
        if card_id:
            db = get_db()
            user = db.execute("SELECT * FROM users WHERE card_id = ?", (card_id,)).fetchone()
            if user:
                # ユーザーが見つかった場合、結果ページを表示
                return render_template("usage_result.html", **dict(user))
            else:
                flash("この学生証は登録されていません。", "warning")
                return redirect(url_for("usage"))
        else:
            # カードが読み取れなかった場合（エラーはread_card_id内でflash済み）
            return redirect(url_for("usage"))

    # GETリクエスト（ページ表示時）
    reader_connected = False
    try:
        if nfc is not None:
            with nfc.ContactlessFrontend('usb'):
                reader_connected = True
    except Exception:
        reader_connected = False
    
    return render_template("usage.html", reader_connected=reader_connected)

@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if 'logout' in request.args:
        session.pop('admin_logged_in', None)
        flash("ログアウトしました。", "success")
        return redirect(url_for('admin_login'))
    if request.method == "POST":
        entered_pass = request.form.get("password", "")
        if check_password(entered_pass):
            session["admin_logged_in"] = True
            return redirect(url_for("admin_dashboard"))
        else:
            flash("パスワードが違います。", "error")
    return render_template("admin_login.html")

@app.route("/admin/dashboard")
def admin_dashboard():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))
    db = get_db()
    users = db.execute("SELECT * FROM users").fetchall()
    units = db.execute("SELECT * FROM units").fetchall()
    history = db.execute("SELECT * FROM history ORDER BY id DESC").fetchall()
    return render_template("admin_dashboard.html", users=users, units=units, history=history)

@app.route("/admin/users")
def admin_users():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))
    db = get_db()
    users = db.execute("SELECT * FROM users").fetchall()
    return render_template("admin_users.html", users=users)

@app.route("/admin/user_detail/<int:uid>", methods=["GET", "POST"])
def admin_user_detail(uid):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))
    db = get_db()
    if request.method == "POST":
        card_id = request.form.get("cardid")
        allow = request.form.get("allow")
        stock = request.form.get("stock")
        if not card_id:
            db.execute("DELETE FROM users WHERE id = ?", (uid,))
            add_history(f"利用者削除(ID:{uid})")
            flash(f"利用者(ID:{uid})を削除しました。", "success")
            db.commit()
            return redirect(url_for("admin_users"))
        else:
            db.execute(
                "UPDATE users SET card_id = ?, allow = ?, stock = ? WHERE id = ?",
                (card_id, allow, stock, uid)
            )
            add_history(f"利用者更新(ID:{uid})")
            flash(f"利用者(ID:{uid})の情報を更新しました。", "success")
            db.commit()
            return redirect(url_for("admin_user_detail", uid=uid))
    user = db.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    if not user:
        flash("指定された利用者は見つかりません。", "error")
        return redirect(url_for("admin_users"))
    return render_template("admin_user_detail.html", user=user)


@app.route("/admin/units")
def admin_units():
    """子機一覧を表示する。ハートビートのタイムアウト処理も行う。"""
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    db = get_db()

    # --- ハートビートのタイムアウト処理 ---
    # 子機クライアント(unit_client.py)は30秒ごとにハートビートを送信するため、
    # 65秒以上信号がなければオフラインと判断する。
    HEARTBEAT_TIMEOUT = timedelta(seconds=65) 
    now = datetime.now()
    
    # 現在オンライン(connect=1)になっている子機を取得
    active_units = db.execute("SELECT * FROM units WHERE connect = 1").fetchall()
    
    for unit in active_units:
        if unit['last_seen']:
            try:
                last_seen_dt = datetime.strptime(unit['last_seen'], "%Y-%m-%d %H:%M:%S")
                # 最終接続時刻からタイムアウト時間を経過しているか確認
                if now - last_seen_dt > HEARTBEAT_TIMEOUT:
                    # タイムアウトした場合、接続状態をオフライン(0)に更新
                    db.execute("UPDATE units SET connect = 0 WHERE id = ?", (unit['id'],))
                    add_history(f"子機がタイムアウトしました: {unit['name']}")
            except ValueError:
                # 日付の形式が不正な場合はスキップ
                continue
    
    db.commit() # 状態の更新を確定
    # --- タイムアウト処理ここまで ---

    # 最新の状態をDBから再度取得して表示
    all_units = db.execute("SELECT * FROM units ORDER BY id").fetchall()
    return render_template("admin_units.html", units=all_units)

@app.route("/admin/unit_detail/<int:uid>", methods=["GET", "POST"])
def admin_unit_detail(uid):
    """子機の詳細情報とログを一緒に表示する"""
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    db = get_db()
    
    if request.method == "POST":
        name = request.form.get("name")
        stock = request.form.get("stock")
        available = request.form.get("available")
        db.execute(
            "UPDATE units SET name = ?, stock = ?, available = ? WHERE id = ?",
            (name, stock, available, uid)
        )
        db.commit()
        add_history(f"子機情報を更新しました (ID:{uid}, 名前:{name})")
        flash(f"子機(ID:{uid})の情報を更新しました。", "success")
        return redirect(url_for("admin_unit_detail", uid=uid))

    # 子機の詳細情報を取得
    unit = db.execute("SELECT * FROM units WHERE id = ?", (uid,)).fetchone()
    if not unit:
        flash("指定された子機が見つかりません。", "error")
        return redirect(url_for('admin_units'))

    # --- ログ取得ロジックを追加 ---
    unit_name = unit['name']
    search_pattern = f"%[{unit_name}]%"
    logs = db.execute(
        "SELECT txt FROM history WHERE txt LIKE ? ORDER BY id DESC", 
        (search_pattern,)
    ).fetchall()
    # --- ここまで追加 ---

    # 取得した子機情報とログをテンプレートに渡す
    return render_template("admin_unit_detail.html", unit=unit, logs=logs)

@app.route("/admin/history")
def admin_history():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    db = get_db()
    history = db.execute("SELECT * FROM history ORDER BY id DESC").fetchall()
    return render_template("admin_history.html", history=history)

# --- REST API ---


@app.route('/api/unit/heartbeat', methods=['POST'])
def unit_heartbeat():
    """子機からの生存確認を受け取り、接続状態を更新または新規登録する"""
    data = request.json
    unit_name = data.get('name')
    unit_pass = data.get('password')

    if not all([unit_name, unit_pass]):
        return jsonify({'error': 'Name and password are required'}), 400
    
    db = get_db()
    unit = db.execute("SELECT * FROM units WHERE name = ?", (unit_name,)).fetchone()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1. もし子機が未登録（None）だったら、自動で新規登録する
    if unit is None:
        # 新しい子機をDBに追加。在庫は0、接続・利用可は1で初期化
        db.execute(
            """
            INSERT INTO units (name, password, stock, connect, available, last_seen)
            VALUES (?, ?, 0, 1, 1, ?)
            """,
            (unit_name, unit_pass, now_str)
        )
        db.commit()
        add_history(f"子機を自動登録しました: {unit_name}")
        return jsonify({'success': True, 'message': 'Unit auto-registered and heartbeat received'}), 201

    # 2. 登録済みの子機の場合、パスワードを検証
    if unit['password'] != unit_pass:
        return jsonify({'error': 'Invalid credentials'}), 401

    # 3. 従来通り、接続状態と最終接続時刻を更新
    db.execute(
        "UPDATE units SET connect = 1, last_seen = ? WHERE id = ?",
        (now_str, unit['id'])
    )
    db.commit()
    
    return jsonify({'success': True, 'message': 'Heartbeat received'}), 200

@app.route("/api/health")
def health_check():
    """サーバーの生存確認用エンドポイント"""
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})
@app.route("/api/reader_status")
def reader_status():
    try:
        if nfc is None:
            raise ImportError("nfcpy not installed")
        clf = nfc.ContactlessFrontend('usb')
        if clf:
            clf.close()
            return jsonify({"connected": True, "error": None})
    except Exception as e:
        error_message = str(e)
        print(f"リーダー接続エラー: {error_message}")
        print(traceback.format_exc())
        return jsonify({
            "connected": False,
            "error": f"リーダー初期化失敗: {error_message}"
        }), 500

@app.route('/api/users', methods=['GET'])
def api_get_users():
    db = get_db()
    users = db.execute('SELECT * FROM users').fetchall()
    return jsonify([dict(row) for row in users])

@app.route('/api/users/<string:card_id>', methods=['GET'])
def api_get_user_by_card(card_id):
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE card_id = ?', (card_id,)).fetchone()
    if user:
        return jsonify(dict(user))
    return jsonify({'error': 'User not found'}), 404

@app.route('/api/log', methods=['POST'])
def api_add_log():
    """子機からのログを受け取り、子機名を付けて保存する"""
    data = request.json
    message = data.get('message')
    unit_name = data.get('unit_name', '不明な子機') # 子機名を取得、なければ'不明な子機'

    if message:
        # ログメッセージに子機名を付ける
        log_entry = f"[{unit_name}] {message}"
        add_history(log_entry)  # add_historyは自動でタイムスタンプを付ける
        return jsonify({'success': True, 'message': 'Log added.'}), 200
    return jsonify({'success': False, 'error': 'Message not provided'}), 400

@app.route('/api/record_usage', methods=['POST'])
def api_record_usage():
    data = request.json
    card_id = data.get('card_id')
    if not card_id:
        return jsonify({'error': 'Card ID is required'}), 400
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE card_id = ?", (card_id,)).fetchone()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    if user['stock'] <= 0:
        return jsonify({'error': 'No stock remaining'}), 400
    new_stock = user['stock'] - 1
    new_total = user['total'] + 1
    new_today = user['today'] + 1
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    history_updates = {f"last{i+1}": user[f"last{i}"] for i in range(1, 10)}
    history_updates["last1"] = now
    set_clauses = ["stock = ?", "total = ?", "today = ?"]
    update_values = [new_stock, new_total, new_today]
    for key, value in history_updates.items():
        set_clauses.append(f"{key} = ?")
        update_values.append(value)
    update_query = f"UPDATE users SET {', '.join(set_clauses)} WHERE card_id = ?"
    update_values.append(card_id)
    db.execute(update_query, tuple(update_values))
    db.commit()
    return jsonify({'success': True, 'message': 'Usage recorded successfully.'})

if __name__ == '__main__':
    migrate_db()
    app.run(host='0.0.0.0', port=5000, debug=True)

