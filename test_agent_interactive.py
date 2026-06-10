import os
import json
from edu2sql.agent import NL2SQLAgent
from edu2sql.config import load_config
from dotenv import load_dotenv

def test_agent_flow():
    load_dotenv(override=True)
    
    config = load_config()
    agent = NL2SQLAgent(config)
    
    print("--- Phase 1: Initial Question ---")
    question = "요즘 참여율 높은 수업 보여줘"
    print(f"User: {question}")
    
    result = agent.answer_question(question)
    print(f"Agent Type: {result['type']}")
    if result['type'] == 'clarification':
        print(f"Agent Question: {result['question']}")
        print(f"Options: {result['options']}")
        state = result['state']
        print(f"DEBUG: Answers so far: {state['clarification_answers']}")
    else:
        print(f"Agent Answer: {result['answer']}")
        return

    print("\n--- Phase 2: Clarification Answer ---")
    answer = "이번 달"
    print(f"User: {answer}")
    
    result = agent.answer_question(answer, state=state)
    print(f"Agent Type: {result['type']}")
    if result['type'] == 'clarification':
        print(f"Agent Question: {result['question']}")
        print(f"Options: {result['options']}")
        state = result['state']
        print(f"DEBUG: Answers so far: {state['clarification_answers']}")
    else:
        print(f"Agent Answer: {result['answer']}")
        return

    print("\n--- Phase 3: Second Clarification ---")
    answer = "제출 완료 기준"
    print(f"User: {answer}")
    result = agent.answer_question(answer, state=state)
    print(f"Agent Type: {result['type']}")
    if result['type'] == 'clarification':
        print(f"Agent Question: {result['question']}")
        print(f"Options: {result['options']}")
        state = result['state']
        print(f"DEBUG: Answers so far: {state['clarification_answers']}")
    elif result['type'] == 'answer':
        print(f"Agent Answer: {result['answer']}")
        print(f"SQL: {result['sql']}")
    else:
        print(f"Result: {result}")

if __name__ == "__main__":
    load_dotenv(override=True)
    if not os.getenv("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY is not set in .env")
    else:
        try:
            test_agent_flow()
        except Exception as e:
            print(f"Error during test: {e}")
