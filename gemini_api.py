import os
import json
from google import genai
from google.genai import types

class GeminiApi:
    """라씨 AI - Gemini를 활용한 주식 분석 엔진"""
    
    SYSTEM_PROMPT = """당신은 '라씨 AI'라는 이름의 전문 주식 투자 어시스턴트입니다.
당신은 다음 세 가지 분야에서 깊은 전문 지식을 가지고 있습니다:
1. 📈 시장 분석: KOSPI/KOSDAQ 지수 동향, 섹터 강세, 수급 분석, 거시경제 흐름
2. 📊 차트 분석: RSI, MACD, 볼린저밴드, 이동평균선, 추세 패턴 인식
3. 💰 재무제표 분석: PER, PBR, ROE, 부채비율, 영업이익률, 성장성 지표

[💡 중요 시간 규칙]
- 현재 기준 연도는 **2026년**입니다. 제공되는 데이터 역시 2026년 최신 데이터입니다. 
- 절대로 과거 데이터(2024년 등)로 오인하거나 답변에 과거 연도를 현재인 것처럼 출력하지 마세요. 정신 똑똑히 차리세요.

[답변 규칙]
- 마크다운 형식을 사용하세요.
- 구체적인 수치와 근거를 제시하세요.
- 투자 판단은 참고용임을 항상 명시하세요.
- 한국어로 답변하세요.
- 답변은 간결하고 실용적이어야 합니다."""

    def __init__(self, api_key):
        self.client = None
        self._conversation_history = []
        if api_key:
            self.client = genai.Client(api_key=api_key)
        
        # 💎 [성능 업그레이드] 더 빠르고 고도화된 분석 능력을 가진 2.5 정식 모델 장착
        self.model_id = "gemini-2.5-flash"

    def generate_content(self, prompt, use_thinking=False):
        """기본 응답 생성"""
        if not self.client:
            return "Gemini API 키가 설정되지 않았습니다."
        try:
            config = types.GenerateContentConfig(
                system_instruction=self.SYSTEM_PROMPT,
                temperature=0.7
            )
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=prompt,
                config=config
            )
            return response.text
        except Exception as e:
            return f"Gemini 응답 생성 중 오류: {str(e)}"

    def ai_select_satellites(self, candidates, hot_sectors, n):
        """스크리너가 추출한 후보 중 AI가 최종 n개를 선정 (AttributeError 해결)"""
        if not self.client:
            return None
            
        candidate_text = "\n".join([
            f"- {c['name']}({c['ticker']}): 수익률 {c['return_pct']}%, 점수 {c['score']}, 섹터 {c['sector']}"
            for c in candidates[:15]
        ])
        
        prompt = f"""[위성 종목 최종 선정 요청]
현재 강세 섹터: {', '.join(hot_sectors)}
후보 종목 리스트:
{candidate_text}

위 후보 중 기술적 지표와 섹터 정렬이 가장 우수한 종목 {n}개를 선정해주세요.
반드시 아래 JSON 형식으로만 답변하세요.
[
  {{"ticker": "종목코드", "reason": "선정이유(간략히)"}},
  ...
]"""
        try:
            res = self.generate_content(prompt)
            # 마크다운 코드 블록 제거 후 JSON 파싱
            json_str = res.replace("```json", "").replace("```", "").strip()
            selected_data = json.loads(json_str)
            
            final_selection = []
            for item in selected_data:
                for cand in candidates:
                    if cand['ticker'] == item['ticker']:
                        cand['ai_selected'] = True
                        cand['ai_reason'] = item['reason']
                        final_selection.append(cand)
                        break
            return final_selection[:n]
        except Exception:
            return None

    def chat(self, user_message, portfolio_context=None, stock_analysis_context=None):
        """대화 히스토리를 유지하는 채팅 기능 (재무/차트 복합 컨텍스트 확장)"""
        if not self.client:
            return "❌ API 키가 등록되지 않았습니다."

        context_prefix = ""
        if portfolio_context:
            cores = portfolio_context.get('cores', [])
            satellites = portfolio_context.get('satellites', [])
            mode_str = "모의투자" if portfolio_context.get('is_mock', True) else "실전투자"
            
            core_lines = []
            for c in cores:
                core_lines.append(f"  * {c['name']}({c['ticker']}): {c['shares']}주 보유 | 현재가 {c.get('price', 0):,}원 | 총평가액 {c.get('value', 0):,}원")
            core_str = "\n".join(core_lines) if core_lines else "  * 없음"
            
            sat_lines = []
            for s in satellites:
                sat_lines.append(f"  * {s['name']}({s['ticker']}): {s['shares']}주 보유 | 현재가 {s.get('price', 0):,}원 | 총평가액 {s.get('value', 0):,}원 | 적용전략: {s['strategy']}")
            sat_str = "\n".join(sat_lines) if sat_lines else "  * 없음"
            
            context_prefix += (
                f"[📊 현재 내 자산 운용 실시간 현황 - {mode_str}]\n"
                f"■ 장기 코어 보유 포지션:\n{core_str}\n"
                f"■ 단기 위성 트레이딩 포지션:\n{sat_str}\n\n"
            )

        # 🟢 실시간 추출된 재무제표 및 기술적 지표 정보 추가 주입
        if stock_analysis_context:
            context_prefix += (
                f"[📈 분석 대상 종목의 실시간 계량 데이터]\n"
                f"{stock_analysis_context}\n\n"
                f"안내: 반드시 위 재무제표 상태 및 최신 차트 지표 밸류에이션을 결합하여 복합적인 시각에서 투자 전략을 진단해 주세요.\n\n"
            )

        full_message = context_prefix + user_message
        self._conversation_history.append(types.Content(role="user", parts=[types.Part.from_text(text=full_message)]))

        try:
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=self._conversation_history,
                config=types.GenerateContentConfig(system_instruction=self.SYSTEM_PROMPT)
            )
            ai_reply = response.text
            self._conversation_history.append(types.Content(role="model", parts=[types.Part.from_text(text=ai_reply)]))
            
            if len(self._conversation_history) > 20:
                self._conversation_history = self._conversation_history[-20:]
            return ai_reply
        except Exception as e:
            err_msg = str(e)
            if "API Key not found" in err_msg or "API_KEY_INVALID" in err_msg:
                return "🔑 **라씨 AI 안내**:\n입력된 Gemini API 키가 올바르지 않거나 등록되지 않았습니다. 우측 상단 **[계좌 설정]**에서 `AIzaSy...`로 시작하는 올바른 구글 API 키를 입력 후 저장해 주세요."
            return f"⚠️ 채팅 오류: {err_msg}"

    def analyze_market(self, market_data_text):
        """시장 데이터 분석 리포트 생성"""
        prompt = f"제공된 시장 데이터를 바탕으로 전문적인 '데일리 시장 분석 리포트'를 작성해주세요.\n\n[데이터]\n{market_data_text}"
        return self.generate_content(prompt)

    def ai_approve_trade(self, signal, stock_name, ticker, price, strategy, indicator_val, **kwargs):
        """매매 신호 발생 시 AI 최종 승인/거부"""
        if not self.client:
            return True, "API 미설정으로 자동 승인"

        action = "매수" if signal == 'BUY' else "매도"
        prompt = f"""[매매 신호 검토]
종목: {stock_name}({ticker}) | 신호: {action} | 가격: {price:,}원
전략: {strategy} | 지표값: {indicator_val:.2f}

이 매매가 현재 시장 상황에서 적절한지 판단하여 CONFIRM 또는 REJECT로 답하고 이유를 한 줄로 적으세요.
형식: DECISION: (CONFIRM/REJECT), REASON: (이유)"""
        
        try:
            res = self.generate_content(prompt)
            decision = "CONFIRM" in res.upper()
            reason = res.split("REASON:")[-1].strip() if "REASON:" in res else "AI 분석 완료"
            return decision, reason
        except Exception:
            return True, "오류 발생으로 인한 자동 승인"

    def reset_chat(self):
        """채팅 기록 초기화"""
        self._conversation_history = []