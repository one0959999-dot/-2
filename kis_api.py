import requests
import json
import pandas as pd
from datetime import datetime, timedelta
class KisApi:
    """한국투자증권 OpenAPI 연동을 위한 클래스입니다."""
    
    def __init__(self, app_key: str, app_secret: str, account_no: str, is_mock: bool = True):
        self.app_key = app_key
        self.app_secret = app_secret
        # 계좌번호 정규화: "44550923-01" → "4455092301" (하이픈 자동 제거)
        self.account_no = account_no.replace('-', '').strip() if account_no else ''
        self.is_mock = is_mock
        
        # 모의투자 및 실전투자 URL 구분
        self.base_url = "https://openapivts.koreainvestment.com:29443" if is_mock else "https://openapi.koreainvestment.com:9443"
        self.access_token = None
        self.token_expiry = None
    def get_access_token(self):
        """API 사용을 위한 토큰 발급"""
        print("[KIS] 접속 토큰(Access Token) 발급을 요청합니다...")
        url = f"{self.base_url}/oauth2/tokenP"
        headers = {"content-type": "application/json"}
        body = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret
        }
        res = requests.post(url, headers=headers, data=json.dumps(body))
        
        if res.status_code == 200:
            self.access_token = res.json().get('access_token')
            # 24시간 유효하지만 안전하게 23시간 뒤 만료로 설정
            self.token_expiry = datetime.now() + timedelta(hours=23)
            print("[KIS] 토큰 발급 완료! (유효기간 24시간)")
            return self.access_token
        else:
            print(f"[KIS] 토큰 발급 실패: {res.text}")
            return None

    def _ensure_token(self):
        """토큰이 없거나 만료되었으면 자동 발급"""
        if not self.access_token or not self.token_expiry or datetime.now() >= self.token_expiry:
            return self.get_access_token()
        return self.access_token

    def _order_headers(self, tr_id: str) -> dict:
        """주문 공통 헤더 생성"""
        return {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
        }
        
    def get_current_price(self, stock_code: str):
        """특정 종목의 현재가 조회"""
        if not self._ensure_token():
            print("[KIS] 접속 토큰이 없어 현재가를 조회할 수 없습니다. (APP_KEY 등을 확인해주세요)")
            return None
            
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-price"
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "FHKST01010100"
        }
        params = {
            "fid_cond_mrkt_div_code": "J",
            "fid_input_iscd": stock_code
        }
        res = requests.get(url, headers=headers, params=params)
        
        if res.status_code == 200:
            data = res.json()
            if data['rt_cd'] == '0':
                price = int(data['output']['stck_prpr'])
                return price
            else:
                print(f"[KIS] 현재가 조회 오류: {data['msg1']}")
                return None
        else:
            print(f"[KIS] 현재가 조회 통신 실패: {res.text}")
            return None

    def _place_order(self, stock_code: str, qty: int, side: str):
        """
        시장가 주문 공통 로직
        side: 'BUY' | 'SELL'
        """
        if not self._ensure_token():
            return None

        # 실전: TTTC0802U(매수) / TTTC0801U(매도)
        # 모의: VTTC0802U(매수) / VTTC0801U(매도)
        if side == 'BUY':
            tr_id = "VTTC0802U" if self.is_mock else "TTTC0802U"
        else:
            tr_id = "VTTC0801U" if self.is_mock else "TTTC0801U"

        # 계좌번호 분리 (앞 8자리 + 뒤 2자리)
        acnt_no   = self.account_no[:8]
        acnt_prdt = self.account_no[8:] if len(self.account_no) > 8 else "01"

        url  = f"{self.base_url}/uapi/domestic-stock/v1/trading/order-cash"
        body = {
            "CANO":           acnt_no,
            "ACNT_PRDT_CD":   acnt_prdt,
            "PDNO":           stock_code,
            "ORD_DVSN":       "01",   # 01 = 시장가
            "ORD_QTY":        str(qty),
            "ORD_UNPR":       "0",    # 시장가는 0
        }

        res = requests.post(
            url,
            headers=self._order_headers(tr_id),
            data=json.dumps(body)
        )

        if res.status_code == 200:
            data = res.json()
            if data.get('rt_cd') == '0':
                odno = data['output'].get('ODNO', '-')
                label = '매수' if side == 'BUY' else '매도'
                print(f"[KIS] {label} 주문 완료 | {stock_code} {qty}주 | 주문번호: {odno}")
                return data
            else:
                msg_cd = data.get('msg_cd', '')
                print(f"[KIS] 주문 실패: {data.get('msg1', res.text)}")
                # 토큰 만료(EGW00123/EGW00121) → 재발급 후 1회 재시도
                if msg_cd in ('EGW00123', 'EGW00121'):
                    print("[KIS] 토큰 만료 → 재발급 후 재시도")
                    self.access_token = None
                    self._ensure_token()
                    return self._place_order(stock_code, qty, side)
                return None
        else:
            print(f"[KIS] 주문 통신 오류: {res.status_code} {res.text}")
            return None
        
    def buy_market_order(self, stock_code: str, qty: int):
        """시장가 매수 주문"""
        if qty <= 0:
            return None
        return self._place_order(stock_code, qty, 'BUY')
        
    def sell_market_order(self, stock_code: str, qty: int):
        """시장가 매도 주문"""
        if qty <= 0:
            return None
        return self._place_order(stock_code, qty, 'SELL')

    def get_account_balance(self):
        """계좌 잔고 및 종목 보유 내역 조회 (실제 계좌)"""
        if not self._ensure_token():
            return None
            
        tr_id = "VTTC8434R" if self.is_mock else "TTTC8434R"
        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/inquire-balance"
        
        acnt_no = self.account_no[:8]
        acnt_prdt = self.account_no[8:] if len(self.account_no) > 8 else "01"
        
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
        }
        
        params = {
            "CANO": acnt_no,
            "ACNT_PRDT_CD": acnt_prdt,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "N",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "00",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": ""
        }
        
        res = requests.get(url, headers=headers, params=params)
        
        if res.status_code == 200:
            data = res.json()
            if data.get('rt_cd') == '0':
                stocks = data.get('output1', [])
                summary = data.get('output2', [{}])[0]
                
                parsed_stocks = []
                for s in stocks:
                    if int(s.get('hldg_qty', 0)) > 0:
                        parsed_stocks.append({
                            "name": s.get('prdt_name', ''),
                            "ticker": s.get('pdno', ''),
                            "shares": int(s.get('hldg_qty', 0)),
                            "purchase_price": float(s.get('pchs_avg_pric', 0)),
                            "current_price": float(s.get('prpr', 0)),
                            "value": float(s.get('evlu_amt', 0)),
                            "profit_rt": float(s.get('evlu_pfls_rt', 0))
                        })
                
                return {
                    "stocks": parsed_stocks,
                    "total_cash": float(summary.get('prvs_rcdl_excc_amt') or summary.get('dnca_tot_amt') or 0), # D+2 예수금
                    "total_value": float(summary.get('tot_evlu_amt') or summary.get('evlu_amt_smtl_amt') or 0), # 총 평가금액
                    "total_purchase": float(summary.get('pchs_amt_smtl_amt') or summary.get('tot_pchs_amt') or 0), # 매입금액 합계
                }
            else:
                msg1 = data.get('msg1', '')
                rt_cd = data.get('rt_cd', '')
                print(f"[KIS] 잔고 조회 실패: rt_cd={rt_cd}, msg={msg1}, data={data}")
                if msg1 in ('EGW00123', 'EGW00121'):
                    self.access_token = None
                    self._ensure_token()
                    return self.get_account_balance()
        else:
            print(f"[KIS] 잔고 조회 통신 오류: status={res.status_code}, text={res.text}")
        return None

    def search_stock_name(self, query: str):
        """종목명 또는 코드로 KOSPI/KOSDAQ 종목 검색 (KIS API 사용)"""
        if not self._ensure_token():
            return []
        
        # 실전 전용 URL (모의투자에서도 시세 조회는 실전 URL 사용 가능하나, 여기선 base_url 통일)
        url = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/search-stock-info"
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "CTPF1002R",
            "custtype": "P",
        }
        params = {
            "PRDT_TYPE_CD": "300",   # 300 = 주식
            "PDNO": query if query.isdigit() else "",
            "PRDT_NAME": "" if query.isdigit() else query,
            "COND_MRKT_DIV_CODE_1": "J",  # KOSPI
            "COND_MRKT_DIV_CODE_2": "Q",  # KOSDAQ
        }
        try:
            res = requests.get(url, headers=headers, params=params, timeout=5)
            if res.status_code == 200:
                data = res.json()
                if data.get('rt_cd') == '0':
                    results = []
                    for item in data.get('output', []):
                        ticker = item.get('pdno', '')
                        name = item.get('prdt_abrv_name', '') or item.get('prdt_name', '')
                        if ticker and name:
                            results.append({'ticker': ticker, 'name': name})
                    return results
        except Exception as e:
            print(f"[KIS] 종목 검색 오류: {e}")
        return []


    def get_volume_rank(self, market_div="J", limit=30):
        """
        거래량 상위 종목 검색 (KIS API 사용)
        market_div: 'J' (KOSPI) 또는 'Q' (KOSDAQ)
        """
        if not self._ensure_token():
            return []
            
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/volume-rank"
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "FHPST01710000",
            "custtype": "P",
        }
        params = {
            "FID_COND_MRKT_DIV_CODE": market_div,
            "FID_COND_SCR_DIV_CODE": "20171",
            "FID_INPUT_ISCD": "0000",
            "FID_DIV_CLS_CODE": "0",
            "FID_BLNG_CLS_CODE": "0",
            "FID_TRGT_CLS_CODE": "111111111",
            "FID_TRGT_EXLS_CLS_CODE": "111111",
            "FID_INPUT_PRICE_1": "1000",
            "FID_INPUT_PRICE_2": "1000000",
            "FID_VOL_CNT": "100000",
            "FID_INPUT_DATE_1": ""
        }
        
        try:
            res = requests.get(url, headers=headers, params=params, timeout=5)
            if res.status_code == 200:
                data = res.json()
                if data.get('rt_cd') == '0':
                    tickers = []
                    for idx, item in enumerate(data.get('output', [])):
                        if idx >= limit: break
                        ticker = item.get('mksc_shrn_iscd')
                        if ticker:
                            tickers.append(ticker)
                    return tickers
        except Exception as e:
            print(f"[KIS] 거래량 상위 검색 오류: {e}")
        return []

if __name__ == '__main__':
    # 테스트 코드
    pass
