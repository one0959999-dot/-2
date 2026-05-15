import google.generativeai as genai
import os
from datetime import datetime

# 재무제표 조회를 위한 DART API (선택적)
try:
    import requests as _requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

class GeminiApi:
    SYSTEM_PROMPT = """당신은 '라씨 AI'라는 이름의 전문 주식 투자 어시스턴트입니다.
당신은 다음 세 가지 분야에서 깊은 전문 지식을 가지고 있습니다:
1. 📈 시장 분석: KOSPI/KOSDAQ 지수 동향, 섹터 강세, 수급 분석, 거시경제 흐름
2. 📊 차트 분석: RSI, MACD, 볼린저밴드, 이동평균선, 추세 패턴 인식
3. 💰 재무제표 분석: PER, PBR, ROE, 부채비율, 영업이익률, 성장성 지표

[답변 규칙]
- 마크다운 형식을 사용하세요 (볼드, 표, 목록 등)
- 이모지를 적절히 사용해 가독성을 높이세요
- 구체적인 수치와 근거를 제시하세요
- 투자 판단은 참고용임을 항상 명시하세요
- 한국어로 답변하세요
- 답변은 간결하고 실용적이어야 합니다"""

    def __init__(self, api_key):
        self.api_key = api_key
        self.model = None
        self.chat_session = None
        self._conversation_history = []

        if api_key:
            try:
                genai.configure(api_key=api_key)
                self.model = genai.GenerativeModel(
                    model_name='gemini-2.5-flash',
                    system_instruction=self.SYSTEM_PROMPT
                )
            except Exception as e:
                print(f"Gemini 초기화 오류: {e}")

    def generate_content(self, prompt):
        if not self.model:
            return "Gemini API 키가 설정되지 않았거나 초기화에 실패했습니다."
        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            return f"Gemini 응답 생성 중 오류 발생: {str(e)}"

    def chat(self, user_message, portfolio_context=None):
        """
        사용자 메시지에 대한 AI 채팅 응답 생성.
        portfolio_context: 현재 포트폴리오 상태 딕셔너리 (선택적)
        """
        if not self.model:
            return "❌ Gemini API 키가 설정되지 않았습니다. [계좌 설정]에서 키를 등록해 주세요."

        # 포트폴리오 컨텍스트를 메시지에 주입
        context_prefix = ""
        if portfolio_context:
            cores = portfolio_context.get('cores', [])
            satellites = portfolio_context.get('satellites', [])
            is_mock = portfolio_context.get('is_mock', True)
            mode_str = "모의투자" if is_mock else "실전투자"

            core_str = ", ".join([f"{c['name']}({c['shares']}주)" for c in cores]) or "없음"
            sat_str = ", ".join([f"{s['name']}[{s['strategy']}]" for s in satellites]) or "없음"

            context_prefix = f"""[현재 포트폴리오 현황 - {mode_str} 모드]
- 코어 종목: {core_str}
- 위성 종목: {sat_str}

위 포트폴리오 정보를 참고하여 답변해 주세요.

사용자 질문: """

        full_message = context_prefix + user_message

        try:
            # 대화 히스토리 유지 (최근 10턴)
            self._conversation_history.append({
                "role": "user",
                "parts": [full_message]
            })
            if len(self._conversation_history) > 20:
                self._conversation_history = self._conversation_history[-20:]

            response = self.model.generate_content(self._conversation_history)
            ai_reply = response.text

            self._conversation_history.append({
                "role": "model",
                "parts": [ai_reply]
            })
            return ai_reply

        except Exception as e:
            return f"⚠️ AI 응답 생성 오류: {str(e)}"

    def reset_chat(self):
        """대화 히스토리 초기화"""
        self._conversation_history = []

    def analyze_market(self, market_data_text):
        """시장 데이터를 기반으로 분석 리포트 생성"""
        prompt = f"""당신은 전문 주식 투자 전략가 'Lassi AI'입니다.
제공된 시장 데이터를 바탕으로 투자자들이 참고할 수 있는 전문적이고 통찰력 있는 '데일리 시장 분석 리포트'를 작성해주세요.

[분석 지침]
1. 마크다운 형식을 사용하세요.
2. 현재 시장의 핵심 테마와 수급 동향을 명확히 짚어주세요.
3. 지수 동향(KOSPI, KOSDAQ)에 따른 단기/중기 전략을 제시하세요.
4. 주도 섹터에 대한 분석과 향후 전망을 포함하세요.
5. 말투는 신뢰감 있고 전문적인 어조(~입니다, ~권장합니다)를 유지하세요.
6. 이모지를 적절히 사용하여 가독성을 높여주세요.

[시장 데이터]
{market_data_text}

분석 리포트를 시작해주세요:
"""
        return self.generate_content(prompt)

    def analyze_stock(self, stock_name, stock_ticker, strategy_info):
        """특정 종목에 대한 AI 투자 의견 생성"""
        prompt = f"""종목명: {stock_name} ({stock_ticker})
적용 전략: {strategy_info}

위 종목에 대한 AI 투자 코멘트를 짧고 강렬하게 3줄 이내로 작성해주세요.
해당 종목이 현재 시장에서 갖는 의미와 전략적 유효성을 언급해주세요.
"""
        return self.generate_content(prompt)

    # ──────────────────────────────────────────────────────────────
    # 🤖 자율 매매 결정 메서드
    # ──────────────────────────────────────────────────────────────

    def ai_select_satellites(self, candidates: list, hot_sectors: list, n: int) -> list | None:
        """
        백테스트 결과(candidates)와 시장 섹터 정보를 AI에게 전달하여
        최종 위성 종목 N개와 각 종목의 최적 전략을 AI가 선정.

        Returns:
            list of {ticker, name, strategy_name, return_pct, ...}  — AI 선정 결과
            None — 파싱 실패 시 (호출자가 폴백 처리)
        """
        if not self.model:
            return None

        import json

        # 후보 데이터 요약 (AI에게 전달할 텍스트)
        candidates_text = "\n".join([
            f"{i+1}. {c['name']}({c['ticker']}) | 전략: {c['strategy_name']} | "
            f"백테스트수익: {c['return_pct']:+.1f}% | 20일모멘텀: {c['momentum_20d']:+.1f}% | "
            f"거래량급등: {c['volume_surge']:.1f}x | 소속섹터: {c['sector']} | 종합점수: {c['score']:.1f}"
            for i, c in enumerate(candidates[:30])  # 상위 30개만 전달
        ])

        prompt = f"""당신은 한국 주식 시장 전문 퀀트 투자 AI입니다.
아래 데이터를 분석하여 단기(1~4주) 위성 종목 포트폴리오를 구성해주세요.

[현재 강세 섹터]
{', '.join(hot_sectors) if hot_sectors else '분석 중'}

[후보 종목 데이터 (백테스트 + 수급 분석)]
{candidates_text}

[선정 기준]
1. 강세 섹터 종목 우선 (시장 테마 탑승)
2. 거래량 급등 + 백테스트 수익률 모두 양호한 종목
3. 20일 모멘텀이 양수이며 과열되지 않은 종목 (-5%~+20% 적정)
4. 종합점수가 높더라도 특정 섹터 쏠림 방지 (섹터 다변화)
5. 해당 종목에 가장 적합한 전략 재배정 가능 (백테스트 결과 참고)

[출력 형식 - 반드시 아래 JSON 배열만 출력하세요. 설명 없이 JSON만]
[
  {{"ticker": "종목코드", "name": "종목명", "strategy_name": "전략명", "reason": "선정 이유 한 줄"}},
  ...
]

선정할 종목 수: {n}개
사용 가능한 전략: RSI(9) 30/70, RSI(14) 30/70, EMA 5/20 크로스, EMA 3/10 크로스, SMA 3/20 크로스, MACD 크로스, 볼린저밴드 반전, Stochastic 크로스, CCI ±100, Williams %R
"""
        try:
            raw = self.generate_content(prompt)
            # JSON 블록 추출
            raw = raw.strip()
            if '```' in raw:
                raw = raw.split('```')[1]
                if raw.startswith('json'):
                    raw = raw[4:]
            # [ ... ] 추출
            start = raw.find('[')
            end   = raw.rfind(']') + 1
            if start == -1 or end == 0:
                return None
            parsed = json.loads(raw[start:end])
            # 원본 candidates에서 ticker 매핑으로 데이터 보강
            ticker_map = {c['ticker']: c for c in candidates}
            result = []
            for item in parsed:
                ticker = item.get('ticker', '')
                base = ticker_map.get(ticker, {})
                result.append({
                    'ticker':        ticker,
                    'name':          item.get('name', base.get('name', '')),
                    'strategy_name': item.get('strategy_name', base.get('strategy_name', 'RSI(14) 30/70')),
                    'return_pct':    base.get('return_pct', 0),
                    'volume_surge':  base.get('volume_surge', 1.0),
                    'sector':        base.get('sector', '-'),
                    'momentum_20d':  base.get('momentum_20d', 0),
                    'score':         base.get('score', 0),
                    'ai_reason':     item.get('reason', ''),  # AI 선정 이유
                    'ai_selected':   True,
                })
            return result[:n] if result else None
        except Exception as e:
            print(f"[GeminiApi] ai_select_satellites 파싱 오류: {e}")
            return None

    def ai_approve_trade(
        self,
        signal: str,          # 'BUY' or 'SELL'
        stock_name: str,
        ticker: str,
        price: float,
        strategy: str,
        indicator_val: float,
        avg_price: float = 0,
        shares: int = 0,
        hot_sectors: list = None,
    ) -> tuple[bool, str]:
        """
        매수/매도 신호 발생 시 AI가 시장 컨텍스트를 고려하여 최종 승인/거부.

        Returns:
            (True, 이유)  — 승인 (CONFIRM)
            (False, 이유) — 거부 (REJECT)
            (True, '')    — 파싱 실패 시 폴백 승인
        """
        if not self.model:
            return (True, '[폴백] Gemini 미설정 → 자동 승인')

        action_kr = "매수" if signal == 'BUY' else "매도"
        profit_str = ""
        if signal == 'SELL' and avg_price > 0 and shares > 0:
            profit_rt = (price / avg_price - 1) * 100
            profit_str = f"\n- 평균 매입가: {avg_price:,.0f}원 | 현재 수익률: {profit_rt:+.1f}%"

        prompt = f"""당신은 한국 주식 시장의 전문 트레이딩 AI입니다.
아래 매매 신호를 검토하고, 실행 여부를 최종 결정해주세요.

[신호 정보]
- 종목: {stock_name} ({ticker})
- 신호: {action_kr}
- 현재가: {price:,.0f}원
- 적용 전략: {strategy}
- 지표값: {indicator_val:.2f}{profit_str}
- 현재 강세 섹터: {', '.join(hot_sectors) if hot_sectors else '정보 없음'}

[판단 기준]
{'매수 판단 기준: 강세 섹터 여부, 과매수 구간 아닌지, 거래량 지지 여부, 시장 전반적 상승세' if signal == 'BUY' else '매도 판단 기준: 수익 실현 타이밍 적절성, 하락 추세 확인, 손절 필요성, 더 좋은 기회 대기'}

[출력 형식 - 아래 형식 그대로만 출력]
DECISION: CONFIRM
REASON: (한 줄 이유)

또는

DECISION: REJECT  
REASON: (한 줄 이유)
"""
        try:
            raw = self.generate_content(prompt).strip()
            lines = raw.split('\n')
            decision = ''
            reason = ''
            for line in lines:
                if line.startswith('DECISION:'):
                    decision = line.replace('DECISION:', '').strip()
                elif line.startswith('REASON:'):
                    reason = line.replace('REASON:', '').strip()

            if 'CONFIRM' in decision.upper():
                return (True, reason)
            elif 'REJECT' in decision.upper():
                return (False, reason)
            else:
                # 파싱 실패 → 안전하게 승인
                return (True, '[파싱 실패] 자동 승인')
        except Exception as e:
            return (True, f'[오류 폴백] {str(e)}')
