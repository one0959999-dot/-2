import os
import json
from google import genai
from google.genai import types

class GeminiApi:
    # 사용자님이 설정하신 주식 전문가 페르소나 유지 및 강화
    SYSTEM_PROMPT = """당신은 '라씨 AI'라는 이름의 전문 주식 투자 어시스턴트입니다.
당신은 다음 세 가지 분야에서 깊은 전문 지식을 가지고 있습니다:
1. 📈 시장 분석: KOSPI/KOSDAQ 지수 동향, 섹터 강세, 수급 분석, 거시경제 흐름
2. 📊 차트 분석: RSI, MACD, 볼린저밴드, 이동평균선, 추세 패턴 인식
3. 💰 재무제표 분석: PER, PBR, ROE, 부채비율, 영업이익률, 성장성 지표

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
        
        # 최신 Pro 모델명 적용
        self.model_id = "gemini-3.1-pro-preview" 

    def generate_content(self, prompt, use_thinking=False):
        """기본 응답 생성 (기존 코드의 generate_content 호환)"""
        if not self.client:
            return "Gemini API 키가 설정되지 않았습니다."
        try:
            config = types.GenerateContentConfig(
                system_instruction=self.SYSTEM_PROMPT,
                temperature=0.7
            )
            # 추론이 필요한 경우 Thinking 모드 활성화
            if use_thinking:
                config.thinking_config = types.ThinkingConfig(thinking_level="HIGH")

            response = self.client.models.generate_content(
                model=self.model_id,
                contents=prompt,
                config=config
            )
            return response.text
        except Exception as e:
            return f"Gemini 응답 생성 중 오류: {str(e)}"

    def chat(self, user_message, portfolio_context=None):
        """대화 히스토리를 유지하는 채팅 기능 (기존 chat 기능 복구)"""
        if not self.client:
            return "❌ API 키가 등록되지 않았습니다."

        context_prefix = ""
        if portfolio_context:
            cores = portfolio_context.get('cores', [])
            satellites = portfolio_context.get('satellites', [])
            mode_str = "모의투자" if portfolio_context.get('is_mock', True) else "실전투자"
            core_str = ", ".join([f"{c['name']}({c['shares']}주)" for c in cores]) or "없음"
            sat_str = ", ".join([f"{s['name']}[{s['strategy']}]" for s in satellites]) or "없음"
            context_prefix = f"[현황: {mode_str}]\n- 코어: {core_str}\n- 위성: {sat_str}\n\n"

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
            return f"⚠️ 채팅 오류: {str(e)}"

    def analyze_market(self, market_data_text):
        """시장 데이터 분석 리포트 생성 (기존 기능 유지)"""
        prompt = f"제공된 시장 데이터를 바탕으로 전문적인 '데일리 시장 분석 리포트'를 작성해주세요.\n\n[데이터]\n{market_data_text}"
        return self.generate_content(prompt, use_thinking=True)

    def ai_approve_trade(self, signal, stock_name, ticker, price, strategy, indicator_val, avg_price=0, shares=0, hot_sectors=None):
        """매매 신호 발생 시 최종 승인/거부 (Pro의 사고력 활용)"""
        if not self.client:
            return True, "API 미설정으로 자동 승인"

        action_kr = "매수" if signal == 'BUY' else "매도"
        profit_info = f"\n- 수익률: {(price/avg_price-1)*100:+.1f}%" if signal == 'SELL' and avg_price > 0 else ""
        
        prompt = f"""[매매 신호 검토]
- 종목: {stock_name} ({ticker}) | 신호: {action_kr}
- 현재가: {price:,.0f}원 | 전략: {strategy} | 지표값: {indicator_val:.2f}{profit_info}
- 강세 섹터: {', '.join(hot_sectors) if hot_sectors else '없음'}

위 정보를 바탕으로 승인 여부를 결정하세요.
출력 형식:
DECISION: (CONFIRM/REJECT)
REASON: (이유 한 줄)"""

        try:
            res = self.generate_content(prompt, use_thinking=True)
            decision = "CONFIRM" in res.upper()
            reason = res.split("REASON:")[-1].strip() if "REASON:" in res else "AI 분석 완료"
            return decision, reason
        except:
            return True, "오류 발생으로 인한 자동 승인"

    def reset_chat(self):
        self._conversation_history = []