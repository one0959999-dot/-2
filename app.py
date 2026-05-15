from flask import Flask, render_template, jsonify, request, redirect, url_for, flash, session
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from bot_controller import manager
from database import get_db_connection, verify_user, add_user, init_db, update_user_keys, get_all_active_users
import os
import json
from datetime import datetime, timedelta
import threading

app = Flask(__name__)

# 서버 재시작에도 세션 유지를 위해 고정 secret_key 사용
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

# Flask-Login 설정
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
        data = dict(user_data)
        try:
            stocks = json.loads(data.get('core_stocks')) if data.get('core_stocks') else []
            data['core_stocks_text'] = "\n".join([f"{s['ticker']}:{s['name']}" for s in stocks])
        except:
            data['core_stocks_text'] = ""
        return User(data['id'], data['username'], data)
    return None

# --- 웹 페이지 경로 ---

@app.route('/')
@login_required
def index():
    user_data = current_user.data
    gemini_enabled = bool(user_data.get('gemini_api_key') and user_data.get('gemini_api_key').strip())
    return render_template('index.html', 
                           user=current_user, 
                           gemini_enabled=gemini_enabled,
                           settings=user_data)

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
            flash('회원가입이 완료되었습니다. 로그인해 주세요.')
            return redirect(url_for('login'))
        flash('이미 존재하는 아이디입니다.')
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- API 경로 ---

def get_current_bot():
    return manager.get_bot(current_user.id, current_user.data)

@app.route('/api/status')
@login_required
def status():
    bot = get_current_bot()
    return jsonify(bot.get_status())

@app.route('/api/toggle', methods=['POST'])
@login_required
def toggle_bot():
    bot = get_current_bot()
    if bot.is_running:
        bot.stop()
        return jsonify({"status": "stopped"})
    else:
        success = bot.start()
        if success:
            return jsonify({"status": "started"})
        else:
            return jsonify({"status": "error", "message": "API 키가 설정되지 않았습니다."}), 400

@app.route('/api/search/stock')
@login_required
def search_stock():
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify({"results": []})
    
    # 주요 종목 리스트 (필요 시 KIS API 검색 결과와 병합 가능)
    MAJOR_STOCKS = [
        ("005930", "삼성전자"), ("000660", "SK하이닉스"), ("003850", "보령"),
        ("005380", "현대차"), ("035420", "NAVER"), ("035720", "카카오"),
        ("068270", "셀트리온"), ("005490", "POSCO홀딩스"), ("207940", "삼성바이오로직스"),
        ("051910", "LG화학"), ("000270", "기아"), ("012330", "현대모비스")
    ]
    
    q_lower = q.lower()
    results = [{"ticker": t, "name": n} for t, n in MAJOR_STOCKS if q_lower in n.lower() or q in t]
    return jsonify({"results": results[:15]})

@app.route('/api/pnl')
@login_required
def get_pnl():
    bot = get_current_bot()
    return jsonify(bot.get_pnl_data() if bot else {"labels": [], "values": []})

@app.route('/api/daily_report')
@login_required
def get_daily_report():
    bot = get_current_bot()
    if not bot or not bot.gemini:
        return jsonify({"status": "error", "message": "AI 설정이 필요합니다."})
        
    today_str = datetime.today().strftime('%Y-%m-%d')
    if bot.daily_report and bot.daily_report.get('date') == today_str:
        return jsonify({"status": "success", "data": bot.daily_report})
    
    bot.daily_report = None
    threading.Thread(target=bot.generate_daily_report, daemon=True).start()
    return jsonify({"status": "waiting", "message": "📡 오늘 날짜 AI 분석 리포트를 생성 중입니다. 잠시만 기다려 주세요."})

@app.route('/api/ai_chat', methods=['POST'])
@login_required
def ai_chat():
    bot = get_current_bot()
    data = request.json
    user_message = data.get('message', '').strip()
    
    if not bot or not bot.gemini:
        return jsonify({"status": "error", "reply": "❌ AI API 키를 등록해주세요."})

    portfolio_ctx = bot.get_status()
    reply = bot.gemini.chat(user_message, portfolio_context=portfolio_ctx)
    return jsonify({"status": "success", "reply": reply})

@app.route('/api/settings/keys', methods=['POST'])
@login_required
def set_keys():
    """사용자 설정(API 키, 모드, 코어 종목) 업데이트"""
    data = request.json
    
    # 코어 종목 텍스트를 리스트로 변환
    core_text = data.get('core_stocks', '')
    core_list = []
    for line in core_text.split('\n'):
        if ':' in line:
            parts = line.split(':')
            core_list.append({"ticker": parts[0].strip(), "name": parts[1].strip()})
    
    data['core_stocks'] = json.dumps(core_list)
    
    # checkbox 값을 확실하게 1 또는 0으로 변환
    new_is_mock = bool(data.get('is_mock'))
    data['is_mock'] = 1 if new_is_mock else 0
    
    # DB 업데이트
    update_user_keys(current_user.id, data)
    
    # 실행 중인 봇의 실시간 모드 전환 처리
    if current_user.id in manager.bots:
        bot = manager.bots[current_user.id]
        
        # 모드(실전/모의)만 변경된 경우
        if bot._is_mock != new_is_mock:
            bot.update_mode(new_is_mock)
            return jsonify({"status": "success", "message": "모드가 실시간으로 전환되었습니다."})
        
        # API 키 등 중요 정보 변경 시에는 봇을 안전하게 중단시키고 인스턴스 제거 (다음 호출 시 재생성)
        bot.stop()
        del manager.bots[current_user.id]
        
    return jsonify({"status": "success"})

def resume_bots():
    """서버 시작 시 실행 중이었던 봇 복구"""
    print("🔄 서버 시작: 봇 상태를 복구하는 중...")
    from database import get_db_connection
    conn = get_db_connection()
    users = conn.execute("SELECT * FROM users WHERE is_running = 1").fetchall()
    conn.close()
    
    for user_row in users:
        user_data = dict(user_row)
        user_id = user_data['id']
        try:
            bot = manager.get_bot(user_id, user_data)
            bot.start()
            print(f"✅ User {user_id} 봇 복구 완료")
        except Exception as e:
            print(f"⚠️ User {user_id} 봇 복구 실패: {e}")

if __name__ == '__main__':
    init_db()
    resume_bots()
    # debug=True로 변경하면 에러 발생 시 상세한 내용을 콘솔에서 볼 수 있습니다.
    app.run(host='0.0.0.0', port=5000, debug=True)