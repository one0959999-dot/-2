from flask import Flask, render_template, jsonify, request, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from bot_controller import manager
from database import get_db_connection, verify_user, add_user, init_db, update_user_keys, get_all_active_users
import os
import json
from datetime import timedelta

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
        # core_stocks JSON을 텍스트로 변환 (UI 표시용)
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
    return render_template('index.html', user=current_user)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user_data = verify_user(username, password)
        if user_data:
            user = User(user_data['id'], user_data['username'], user_data)
            login_user(user, remember=True)
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

# --- API 경로 (로그인 필요) ---

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
    
    # 주요 KOSPI/KOSDAQ 종목 내장 DB (KIS API 의존 없이 항상 동작)
    MAJOR_STOCKS = [
        # KOSPI 시총 상위
        ("005930", "삼성전자"), ("000660", "SK하이닉스"), ("207940", "삼성바이오로직스"),
        ("005380", "현대차"), ("006400", "삼성SDI"), ("035420", "NAVER"),
        ("000270", "기아"), ("051910", "LG화학"), ("105560", "KB금융"),
        ("035720", "카카오"), ("003550", "LG"), ("086790", "하나금융지주"),
        ("028260", "삼성물산"), ("009150", "삼성전기"), ("316140", "우리금융지주"),
        ("032830", "삼성생명"), ("011200", "HMM"), ("017670", "SK텔레콤"),
        ("066570", "LG전자"), ("003490", "대한항공"), ("012330", "현대모비스"),
        ("055550", "신한지주"), ("096770", "SK이노베이션"), ("003850", "보령"),
        ("047040", "대우건설"), ("042700", "한미반도체"), ("950130", "엑세스바이오"),
        ("011070", "LG이노텍"), ("018880", "한온시스템"), ("034730", "SK"),
        ("015760", "한국전력"), ("009540", "HD한국조선해양"), ("010950", "S-Oil"),
        ("030200", "KT"), ("002790", "아모레퍼시픽"), ("018260", "삼성에스디에스"),
        ("010130", "고려아연"), ("139480", "이마트"), ("033780", "KT&G"),
        ("003670", "포스코퓨처엠"), ("005490", "POSCO홀딩스"), ("090430", "아모레G"),
        ("006800", "미래에셋증권"), ("023530", "롯데쇼핑"), ("000810", "삼성화재"),
        ("011780", "금호석유"), ("035250", "강원랜드"), ("028050", "삼성엔지니어링"),
        ("267250", "HD현대"), ("078930", "GS"), ("000100", "유한양행"),
        ("024110", "기업은행"), ("138040", "메리츠금융지주"), ("011790", "SKC"),
        ("004370", "농심"), ("021240", "코웨이"), ("051900", "LG생활건강"),
        ("010140", "삼성중공업"), ("009830", "한화솔루션"), ("180640", "한진칼"),
        ("034020", "두산에너빌리티"), ("047050", "포스코인터내셔널"),
        ("072750", "카카오뱅크"), ("293490", "카카오게임즈"),
        ("035900", "JYP Ent."), ("041510", "에스엠"), ("122870", "와이지엔터테인먼트"),
        ("005940", "NH투자증권"), ("016360", "삼성증권"), ("071050", "한국금융지주"),
        ("030000", "제일기획"), ("097950", "CJ제일제당"), ("001040", "CJ"),
        ("006260", "LS"), ("042660", "한화오션"), ("064350", "현대로템"),
        ("007310", "오뚜기"), ("271560", "오리온"), ("000080", "하이트진로"),
        ("082740", "HSD엔진"), ("161390", "한국타이어앤테크놀로지"), ("002380", "KCC"),
        ("008770", "호텔신라"), ("120110", "코오롱인더"), ("058470", "리노공업"),
        ("000120", "CJ대한통운"), ("069960", "현대백화점"), ("001450", "현대해상"),
        # KOSDAQ 주요
        ("091990", "셀트리온헬스케어"), ("196170", "알테오젠"), ("086900", "메디톡스"),
        ("068270", "셀트리온"), ("247540", "에코프로비엠"), ("086520", "에코프로"),
        ("323410", "카카오페이"), ("035900", "JYP Ent."), ("263750", "펄어비스"),
        ("036570", "엔씨소프트"), ("112040", "위메이드"), ("251270", "넷마블"),
        ("078340", "컴투스"), ("095660", "네오위즈"), ("214150", "클래시스"),
        ("041830", "인바디"), ("145020", "휴젤"), ("200130", "콜마비앤에이치"),
        ("005300", "롯데칠성"), ("000720", "현대건설"), ("047810", "한국항공우주"),
        ("012450", "한화에어로스페이스"), ("004020", "현대제철"), ("005010", "현대상선"),
        ("005930", "삼성전자우"), ("000887", "삼성전자우선주"),
        ("072990", "에이치엘비"), ("027360", "아주IB투자"), ("263750", "펄어비스"),
        ("348210", "넥스틴"), ("357780", "솔브레인"), ("408900", "한화리츠"),
        ("005850", "에스엘"), ("005930", "삼성전자"), ("009540", "HD한국조선해양"),
        ("010620", "현대미포조선"), ("000157", "두산2우B"), ("036460", "한국가스공사"),
        ("071320", "지역난방공사"), ("088350", "한화생명"), ("016580", "환인제약"),
        ("068760", "셀트리온제약"), ("196300", "셀리버리"), ("298020", "효성티앤씨"),
    ]
    
    # 중복 제거
    seen = set()
    unique_stocks = []
    for ticker, name in MAJOR_STOCKS:
        if ticker not in seen:
            seen.add(ticker)
            unique_stocks.append((ticker, name))
    
    q_lower = q.lower()
    results = []
    for ticker, name in unique_stocks:
        if q_lower in name.lower() or q in ticker:
            results.append({"ticker": ticker, "name": name})
        if len(results) >= 15:
            break
    
    return jsonify({"results": results})


@app.route('/api/pnl')
@login_required
def get_pnl():
    bot = get_current_bot()
    if bot:
        return jsonify(bot.get_pnl_data())
    return jsonify({"labels": [], "values": []})

@app.route('/api/daily_report')
@login_required
def get_daily_report():
    from datetime import datetime
    import threading
    bot = get_current_bot()
    today_str = datetime.today().strftime('%Y-%m-%d')
    if bot and bot.daily_report:
        # 날짜가 오늘이 아닌 리포트는 백그라운드에서 재생성 후 대기 상태 반환
        if bot.daily_report.get('date') != today_str:
            bot.daily_report = None
            threading.Thread(target=bot.generate_daily_report, daemon=True).start()
            return jsonify({"status": "waiting", "message": "📡 어제 리포트 감지! 오늘 날짜 AI 분석 리포트를 생성 중입니다. 30초 후 다시 확인해 주세요."})
        return jsonify({"status": "success", "data": bot.daily_report})
    return jsonify({"status": "waiting", "message": "오늘의 리포트가 아직 생성되지 않았습니다."})

@app.route('/api/ai_chat', methods=['POST'])
@login_required
def ai_chat():
    bot = get_current_bot()
    data = request.json
    user_message = data.get('message', '').strip()
    if not user_message:
        return jsonify({"status": "error", "message": "메시지를 입력해주세요."}), 400

    if not bot or not bot.gemini:
        return jsonify({
            "status": "error",
            "reply": "❌ Gemini API 키가 설정되지 않았습니다.\n\n[계좌 설정] → Google Gemini API Key를 입력하고 저장해주세요."
        })

    # 현재 포트폴리오 상태를 컨텍스트로 전달
    portfolio_ctx = bot.get_status()
    reply = bot.gemini.chat(user_message, portfolio_context=portfolio_ctx)
    return jsonify({"status": "success", "reply": reply})

@app.route('/api/ai_reset', methods=['POST'])
@login_required
def ai_reset():
    bot = get_current_bot()
    if bot and bot.gemini:
        bot.gemini.reset_chat()
    return jsonify({"status": "success", "message": "대화 기록이 초기화되었습니다."})

@app.route('/api/settings/satellites', methods=['POST'])
@login_required
def set_satellites():
    bot = get_current_bot()
    data = request.json
    count = data.get('count', 5)
    if 1 <= count <= 15:
        bot.num_satellites = count
        return jsonify({"status": "success", "num_satellites": bot.num_satellites})
    return jsonify({"status": "error", "message": "Invalid count"}), 400

@app.route('/api/settings/keys', methods=['POST'])
@login_required
def set_keys():
    data = request.json
    
    # 코어 종목 텍스트를 JSON으로 변환
    core_text = data.get('core_stocks', '')
    core_list = []
    for line in core_text.split('\n'):
        if ':' in line:
            ticker, name = line.split(':', 1)
            core_list.append({"ticker": ticker.strip(), "name": name.strip()})
    
    data['core_stocks'] = json.dumps(core_list)
    
    # is_mock 파라미터 처리 (없으면 기본값 1)
    if 'is_mock' in data:
        data['is_mock'] = 1 if data['is_mock'] else 0
    else:
        data['is_mock'] = 1
        
    data['kis_app_key'] = data.get('kis_app_key', '').strip()
    data['kis_app_secret'] = data.get('kis_app_secret', '').strip()
    data['kis_account_no'] = data.get('kis_account_no', '').strip()
    data['telegram_token'] = data.get('telegram_token', '').strip()
    data['telegram_chat_id'] = data.get('telegram_chat_id', '').strip()
    data['gemini_api_key'] = data.get('gemini_api_key', '').strip()
    
    update_user_keys(current_user.id, data)
    # 봇 인스턴스 정보 갱신 (다음 get_bot 호출 시 반영되게 하거나 현재 인스턴스 업데이트)
    if current_user.id in manager.bots:
        del manager.bots[current_user.id] # 재설정을 위해 인스턴스 삭제
    return jsonify({"status": "success"})

@app.route('/api/settings/mode', methods=['POST'])
@login_required
def set_mode():
    data = request.json
    is_mock = 1 if data.get('is_mock') else 0
    from database import get_db_connection
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET is_mock = ? WHERE id = ?', (is_mock, current_user.id))
    conn.commit()
    conn.close()
    
    # 설정 변경 시 봇 재초기화를 위해 삭제
    if current_user.id in manager.bots:
        del manager.bots[current_user.id]
    return jsonify({"status": "success", "is_mock": is_mock})
@app.route('/api/kis_balance')
@login_required
def get_kis_balance():
    bot = get_current_bot()
    if not bot or not bot.kis:
        return jsonify({"status": "error", "message": "한국투자증권 API가 설정되지 않았습니다."}), 400
    
    balance = bot.kis.get_account_balance()
    if balance:
        return jsonify({"status": "success", "data": balance})
    else:
        return jsonify({"status": "error", "message": "잔고 조회에 실패했습니다. (API 오류 또는 토큰 만료)"}), 500

# --- 서버 시작 시 봇 자동 복구 ---
def resume_bots():
    with app.app_context():
        active_users = get_all_active_users()
        print(f"🔄 서버 시작: {len(active_users)}명의 봇을 복구하는 중...")
        for user_data in active_users:
            bot = manager.get_bot(user_data['id'], user_data)
            bot.start()

if __name__ == '__main__':
    init_db()
    # 서버 실행 전 봇 복구 실행
    resume_bots()
    app.run(host='0.0.0.0', port=5000, debug=False)
