import requests

class TelegramNotifier:
    """텔레그램을 통해 매매 알림을 보내는 클래스입니다."""
    
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
            
    def send_message(self, text: str):
        """동기 방식으로 텔레그램 메시지 전송"""
        if not self.token or not self.chat_id:
            print(f"[텔레그램 알림] (설정안됨) {text}")
            return
            
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        data = {
            "chat_id": self.chat_id,
            "text": text
        }
        try:
            res = requests.post(url, data=data)
            if res.status_code != 200:
                print(f"[텔레그램 전송 실패] {res.text}")
        except Exception as e:
            print(f"[텔레그램 알림 에러] {e}")

if __name__ == '__main__':
    # 테스트 코드
    pass
