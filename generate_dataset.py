# pyrefly: ignore [missing-import]
import yfinance as yf
import pandas as pd
import json

def calc_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    return 100 - 100 / (1 + gain / (loss + 1e-10))

print("📊 2000~2024년 미장(나스닥 QQQ) 데이터를 불러옵니다...")
df = yf.download("QQQ", start="2000-01-01", end="2024-05-01")

# ✅ [추가된 에러 해결 코드] yfinance의 다중 인덱스(MultiIndex)를 단일 인덱스로 평탄화
if isinstance(df.columns, pd.MultiIndex):
    df.columns = df.columns.droplevel(1)

# 보조지표 계산
df['RSI'] = calc_rsi(df['Close'], 14)
df['SMA_20'] = df['Close'].rolling(window=20).mean()
df['SMA_120'] = df['Close'].rolling(window=120).mean() # 장기 추세 (하락장 판별용)
df = df.dropna()

dataset = []
print("🧠 AI 학습용 문제집(Q&A)을 생성 중입니다...")

for i in range(len(df) - 20):  # 미래 20일의 결과를 봐야 하므로 끝에 20일은 제외
    current_date = df.index[i].strftime('%Y-%m-%d')
    close_price = float(df['Close'].iloc[i])
    rsi = float(df['RSI'].iloc[i])
    sma20 = float(df['SMA_20'].iloc[i])
    sma120 = float(df['SMA_120'].iloc[i])
    
    # [조건] RSI가 35 이하로 떨어져서 봇이 '매수 신호'라고 착각할 만한 자리만 추출
    if rsi <= 35:
        # 미래 20일(약 1달) 동안의 최고가와 최저가 확인
        future_20_days = df['Close'].iloc[i+1 : i+21]
        max_future = float(future_20_days.max())
        min_future = float(future_20_days.min())
        
        profit_pct = (max_future - close_price) / close_price * 100
        loss_pct = (min_future - close_price) / close_price * 100
        
        # 장기 이평선(120일) 아래면 대세 하락장(베어마켓)으로 간주
        is_bear_market = bool(close_price < sma120)
        
        # 텍스트 인풋 (AI가 보게 될 문제)
        market_status = "대세 하락장(120일선 붕괴)" if is_bear_market else "상승/조정장"
        text_input = f"종목: QQQ, 시기: {current_date}, 상태: {market_status}, RSI: {rsi:.1f}, 현재가: {close_price:.2f}. 이 매매 신호를 승인하시겠습니까?"
        
        # 아웃풋 (AI가 맞춰야 할 정답)
        if is_bear_market and loss_pct < -10:
            output = "REJECT. 이유: 120일선 아래의 역배열 하락장이며, RSI가 낮더라도 전형적인 '떨어지는 칼날(가짜 반등)'입니다. 추가 폭락 위험이 높습니다."
        elif profit_pct >= 5 and loss_pct >= -5:
            output = "CONFIRM. 이유: 충분한 과매도 구간이며 반등 확률이 높은 안전한 자리입니다."
        else:
            output = "REJECT. 이유: 변동성이 너무 크고 확실한 반등 시그널이 부족합니다. 관망하세요."

        dataset.append({"text_input": text_input, "output": output})

# JSONL 파일로 저장 (구글 AI 스튜디오 규격)
with open("bear_market_training.jsonl", "w", encoding="utf-8") as f:
    for data in dataset:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")

print(f"✅ 총 {len(dataset)}개의 역사적 하락장/반등장 Q&A가 'bear_market_training.jsonl' 파일로 저장되었습니다!")