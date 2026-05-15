import time
import schedule
import yaml
from kis_api import KisApi
from telegram_bot import TelegramNotifier

kis_instance = None
telegram_instance = None

def load_config(filepath="config.yaml"):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"설정 파일(config.yaml)을 읽는 중 오류가 발생했습니다: {e}")
        return None

def trading_job():
    """정해진 시간(또는 주기)마다 실행될 매매 로직"""
    print("[진행중] 종목 검색 및 자동 매매 로직 실행...")
    
    # 1. 대상 종목 현재가 조회 (예: 삼성전자 '005930')
    target_stock = "005930"
    stock_name = "삼성전자"
    
    if kis_instance and telegram_instance:
        current_price = kis_instance.get_current_price(target_stock)
        
        if current_price:
            msg = f"[{stock_name}] 실시간 현재가: {current_price:,}원"
            print(msg)
            telegram_instance.send_message(msg)
        else:
            print("현재가 조회에 실패했습니다.")

def main():
    global kis_instance, telegram_instance
    
    print("="*50)
    print("라씨 매매비서 스타일 자동 주식 매매 봇 시작")
    print("="*50)
    
    config = load_config()
    if not config:
        return

    # API 연동 객체 생성
    kis_instance = KisApi(
        app_key=config['KIS'].get('APP_KEY', ''),
        app_secret=config['KIS'].get('APP_SECRET', ''),
        account_no=config['KIS'].get('ACCOUNT_NO', ''),
        is_mock=config['KIS'].get('IS_MOCK', True)
    )
    
    # KIS API 토큰 발급 테스트
    kis_instance.get_access_token()
    
    # 텔레그램 연동 객체 생성
    telegram_instance = TelegramNotifier(
        token=config['TELEGRAM'].get('BOT_TOKEN', ''),
        chat_id=config['TELEGRAM'].get('CHAT_ID', '')
    )
    
    telegram_instance.send_message("자동매매 봇이 정상적으로 시작되었습니다.")
    
    # 스케줄러 설정 (일단 10초마다 실행해서 테스트)
    schedule.every(10).seconds.do(trading_job)
    
    print("스케줄러가 시작되었습니다. 대기 중...")
    
    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n프로그램을 종료합니다.")
        telegram_instance.send_message("자동매매 봇이 종료되었습니다.")

if __name__ == "__main__":
    main()
