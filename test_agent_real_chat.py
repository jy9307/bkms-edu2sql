import os
import json
import sys
from edu2sql.agent import NL2SQLAgent
from edu2sql.config import load_config
from dotenv import load_dotenv

def chat():
    # .env 파일에서 환경 변수 로드
    load_dotenv(override=True)
    
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ 오류: .env 파일에 OPENAI_API_KEY가 설정되어 있지 않습니다.")
        return

    # 설정 로드 및 에이전트 초기화
    try:
        config = load_config()
        agent = NL2SQLAgent(config)
    except Exception as e:
        print(f"❌ 초기화 중 오류 발생: {e}")
        return

    print("================================================")
    print("🎓 Edu2SQL 대화형 에이전트 테스트")
    print("질문을 입력하세요. 종료하려면 'exit' 또는 'quit'을 입력하세요.")
    print("================================================")

    state = None
    
    while True:
        # 사용자 입력 받기
        if state and state.get("pending_clarification"):
            prompt = f"\n[명료화 답변 입력] > "
        else:
            prompt = f"\n[새 질문 입력] > "
            state = None # 새 질문일 경우 상태 초기화
            
        user_input = input(prompt).strip()

        if user_input.lower() in ['exit', 'quit', '종료', 'q']:
            print("테스트를 종료합니다. 감사합니다!")
            break

        if not user_input:
            continue

        try:
            # 에이전트 호출
            result = agent.answer_question(user_input, state=state)
            
            # 결과 처리
            if result['type'] == 'clarification':
                print(f"\n🤖 에이전트 질문: {result['question']}")
                if result.get('options'):
                    print(f"📍 선택지: {', '.join(result['options'])}")
                state = result['state']
                
            elif result['type'] == 'answer':
                print(f"\n✅ 에이전트 답변:\n{result['answer']}")
                state = None # 답변 완료 후 상태 초기화
                
            elif result['type'] == 'error':
                print(f"\n❌ 에러 발생: {result['message']}")
                if result.get('errors'):
                    for err in result['errors']:
                        print(f"   - {err}")
                state = None
                
        except Exception as e:
            print(f"⚠️ 실행 중 예상치 못한 오류 발생: {e}")
            state = None

if __name__ == "__main__":
    chat()
