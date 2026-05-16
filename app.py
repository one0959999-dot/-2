from flask import Flask, render_template, jsonify, request, redirect, url_for, flash, session
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from bot_controller import manager
from database import get_db_connection, verify_user, add_user, init_db, update_user_keys
import os
import json
from datetime import datetime, timedelta
import threading

app = Flask(__name__)

# 보안 키 설정
_key_file = os.path.join(os.path.dirname(__file__), '.secret_key')
if os.path.exists(_key_file):
    with open(_key_file, 'rb') as f:
        app.secret_key = f.read()
else:
    app.secret_key = os.urandom(32)
    with open(_key_file, 'wb') as f:
        f.write(app.secret_key)

app.config['REMEMBER_COOKIE_DURATION'] = timedelta(days=7)
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, id, username, data):
        self.id = id
        self.username = username
        self.data = data

@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    user_data = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    if user_data:
        return User(user_data['id'], user_data['username'], dict(user_data))
    return None

def get_current_bot():
    return manager.get_bot(current_user.id, current_user.data)

@app.route('/')
@login_required
def index():
    user_data = current_user.data
    gemini_enabled = bool(user_data.get('gemini_api_key'))
    return render_template('index.html', user=current_user, gemini_enabled=gemini_enabled)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user_data = verify_user(username, password)
        if user_data:
            user = User(user_data['id'], user_data['username'], user_data)
            login_user(user, remember=True)
            session.permanent = True
            return redirect(url_for('index'))
        flash('아이디 또는 비밀번호가 올바르지 않습니다.')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if add_user(username, password):
            flash('회원가입이 완료되었습니다.')
            return redirect(url_for('login'))
        flash('이미 존재하는 아이디입니다.')
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- API Endpoints ---

@app.route('/api/status')
@login_required
def status():
    bot = get_current_bot()
    return jsonify(bot.get_status())

@app.route('/api/kis_balance')
@login_required
def kis_balance():
    """실시간 한국투자증권 계좌 잔고 조회 API"""
    bot = get_current_bot()
    if not bot or not bot.kis:
        return jsonify({"status": "error", "message": "API 설정이 필요합니다."})
    
    balance = bot.kis.get_account_balance()
    if balance:
        return jsonify({"status": "success", "data": balance})
    return jsonify({"status": "error", "message": "잔고 조회 실패"})

@app.route('/api/toggle', methods=['POST'])
@login_required
def toggle_bot():
    bot = get_current_bot()
    if bot.is_running:
        bot.stop()
        return jsonify({"status": "stopped"})
    else:
        # DB에 저장된 사용자의 실제 투자 원금(initial_cash)을 안전하게 읽어와 봇을 시작하도록 변경합니다.
        user_cash = current_user.data.get('initial_cash', 10000000)
        success = bot.start(total_cash=user_cash)
        if success:
            return jsonify({"status": "started"})
        return jsonify({"status": "error", "message": "봇 시작 실패"}), 400

@app.route('/api/pnl')
@login_required
def get_pnl():
    bot = get_current_bot()
    return jsonify(bot.get_pnl_data())

@app.route('/api/daily_report')
@login_required
def get_daily_report():
    bot = get_current_bot()
    if not bot or not bot.gemini:
        return jsonify({"status": "error", "message": "AI 설정이 필요합니다."})
        
    today_str = datetime.today().strftime('%Y-%m-%d')
    if bot.daily_report and bot.daily_report.get('date') == today_str:
        return jsonify({"status": "success", "data": bot.daily_report})
    
    threading.Thread(target=bot.generate_daily_report, daemon=True).start()
    return jsonify({"status": "waiting", "message": "리포트 생성 중..."})

@app.route('/api/ai_chat', methods=['POST'])
@login_required
def ai_chat():
    bot = get_current_bot()
    data = request.json
    user_message = data.get('message', '').strip()
    if not bot or not bot.gemini:
        return jsonify({"status": "error", "reply": "AI API 키를 등록해주세요."})

    reply = bot.gemini.chat(user_message, portfolio_context=bot.get_status())
    return jsonify({"status": "success", "reply": reply})

@app.route('/api/ai_reset', methods=['POST'])
@login_required
def ai_reset():
    """AI 채팅 기록 초기화 (누락된 API 추가)"""
    bot = get_current_bot()
    if bot and bot.gemini:
        bot.gemini.reset_chat()
        return jsonify({"status": "success"})
    return jsonify({"status": "error"})

@app.route('/api/search/stock')
@login_required
def search_stock():
    """프론트엔드 종목 검색창 요청 처리 API (KIS API 연동)"""
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({"results": []})
        
    bot = get_current_bot()
    if not bot or not bot.kis:
        return jsonify({"results": [], "message": "API 설정이 비어있습니다."})
        
    # kis_api.py에 정의된 search_stock_name 메서드를 사용하여 한국거래소 종목을 검색합니다.
    results = bot.kis.search_stock_name(query)
    return jsonify({"results": results})

@app.route('/api/settings/mode', methods=['POST'])
@login_required
def set_mode():
    """실전/모의 투자 모드 전환 API"""
    data = request.json
    is_mock = int(data.get('is_mock', 1))
    
    # 1. DB 업데이트
    from database import get_db_connection
    conn = get_db_connection()
    conn.execute('UPDATE users SET is_mock = ? WHERE id = ?', (is_mock, current_user.id))
    conn.commit()
    conn.close()
    
    # 2. 실행 중인 봇의 모드 즉시 변경
    bot = get_current_bot()
    if bot:
        # 사용자의 가설정 자산 원금(initial_cash)을 함께 인자로 전달하여 장부 초기화에 대응합니다.
        user_cash = current_user.data.get('initial_cash', 10000000)
        bot.update_mode(bool(is_mock), total_cash=user_cash)
        
    return jsonify({"status": "success", "is_mock": is_mock})

@app.route('/api/settings/keys', methods=['POST'])
@login_required
def set_keys():
    data = request.json
    update_data = {
        'real_app_key': data.get('real_app_key'),
        'real_app_secret': data.get('real_app_secret'),
        'real_account_no': data.get('real_account_no'),
        'mock_app_key': data.get('mock_app_key'),
        'mock_app_secret': data.get('mock_app_secret'),
        'mock_account_no': data.get('mock_account_no'),
        'telegram_token': data.get('telegram_token'),
        'telegram_chat_id': data.get('telegram_chat_id'),
        'gemini_api_key': data.get('gemini_api_key'),
        'core_stocks': data.get('core_stocks'),
        'is_mock': data.get('is_mock')
    }

   # 1. 데이터 저장
    update_user_keys(current_user.id, update_data)

    # [핵심 추가] 변경된 설정을 메모리에 구동 중인 봇 컨트롤러 인스턴스에도 즉시 동기화해 줍니다.
    is_mock = int(data.get('is_mock', 1))
    prefix = 'mock_' if is_mock else 'real_'
    
    bot = get_current_bot()
    if bot:
        bot.reload_api_keys(
            kis_config={
                "app_key": data.get(f'{prefix}app_key'),
                "app_secret": data.get(f'{prefix}app_secret'),
                "account_no": data.get(f'{prefix}account_no'),
                "is_mock": bool(is_mock)
            },
            telegram_config={
                "token": data.get('telegram_token'),
                "chat_id": data.get('telegram_chat_id')
            },
            gemini_config={
                "api_key": data.get('gemini_api_key')
            },
            core_stocks=data.get('core_stocks')
        )

    # 2. 브라우저에게 "성공했다"고 대답해줌
    return jsonify({"status": "success"})

if __name__ == '__main__':
    init_db()
    # debug=False 및 use_reloader=False로 설정하여 프로세스 이중 실행과 의도치 않은 자동 시작을 원천 차단합니다.
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)