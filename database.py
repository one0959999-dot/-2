import sqlite3
import os
from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = 'users.db'

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 사용자 테이블
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        kis_app_key TEXT,
        kis_app_secret TEXT,
        kis_account_no TEXT,
        telegram_token TEXT,
        telegram_chat_id TEXT,
        gemini_api_key TEXT,
        initial_cash REAL DEFAULT 10000000,
        is_running INTEGER DEFAULT 0,
        is_mock INTEGER DEFAULT 1,
        core_stocks TEXT
    )
    ''')

    # 기존 DB에 컬럼 추가 시도 (없을 경우)
    try:
        cursor.execute('ALTER TABLE users ADD COLUMN gemini_api_key TEXT')
    except sqlite3.OperationalError:
        pass

    # 기존 DB에 is_running 컬럼이 없는 경우 추가
    try:
        cursor.execute('ALTER TABLE users ADD COLUMN is_running INTEGER DEFAULT 0')
    except sqlite3.OperationalError:
        pass

    # 기존 DB에 core_stocks 컬럼이 없는 경우 추가
    try:
        cursor.execute('ALTER TABLE users ADD COLUMN core_stocks TEXT')
    except sqlite3.OperationalError:
        pass

    # 기존 DB에 is_mock 컬럼이 없는 경우 추가
    try:
        cursor.execute('ALTER TABLE users ADD COLUMN is_mock INTEGER DEFAULT 1')
    except sqlite3.OperationalError:
        pass
    
    # 봇 상태 테이블 (간이 저장용 - JSON 형태로 저장 예정)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS bot_states (
        user_id INTEGER PRIMARY KEY,
        state_json TEXT,
        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    ''')
    
    conn.commit()
    conn.close()

def add_user(username, password):
    conn = get_db_connection()
    cursor = conn.cursor()
    password_hash = generate_password_hash(password)
    try:
        cursor.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)', (username, password_hash))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def verify_user(username, password):
    conn = get_db_connection()
    cursor = conn.cursor()
    user = cursor.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    conn.close()
    
    if user and check_password_hash(user['password_hash'], password):
        return dict(user)
    return None

def update_user_keys(user_id, keys_dict):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE users 
        SET kis_app_key = ?, kis_app_secret = ?, kis_account_no = ?, 
            telegram_token = ?, telegram_chat_id = ?, gemini_api_key = ?, core_stocks = ?, is_mock = ?
        WHERE id = ?
    ''', (
        keys_dict.get('kis_app_key'),
        keys_dict.get('kis_app_secret'),
        keys_dict.get('kis_account_no'),
        keys_dict.get('telegram_token'),
        keys_dict.get('telegram_chat_id'),
        keys_dict.get('gemini_api_key'),
        keys_dict.get('core_stocks'),
        keys_dict.get('is_mock', 1),
        user_id
    ))
    conn.commit()
    conn.close()

def update_bot_status(user_id, is_running):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET is_running = ? WHERE id = ?', (1 if is_running else 0, user_id))
    conn.commit()
    conn.close()

def get_all_active_users():
    conn = get_db_connection()
    users = conn.execute('SELECT * FROM users WHERE is_running = 1').fetchall()
    conn.close()
    return [dict(u) for u in users]

def save_portfolio_state(user_id, state_dict):
    """포트폴리오 상태를 JSON으로 DB에 저장"""
    import json
    conn = get_db_connection()
    conn.execute('''
        INSERT OR REPLACE INTO bot_states (user_id, state_json, last_updated)
        VALUES (?, ?, CURRENT_TIMESTAMP)
    ''', (user_id, json.dumps(state_dict, ensure_ascii=False)))
    conn.commit()
    conn.close()

def load_portfolio_state(user_id):
    """DB에서 포트폴리오 상태를 불러옴"""
    import json
    conn = get_db_connection()
    row = conn.execute('SELECT state_json FROM bot_states WHERE user_id = ?', (user_id,)).fetchone()
    conn.close()
    if row and row['state_json']:
        return json.loads(row['state_json'])
    return None

if __name__ == '__main__':
    init_db()
    print("Database initialized.")
