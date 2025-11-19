"""
손주톡톡 할일 추출 서비스
대화에서 자동으로 일정/스케줄을 추출하는 AI 서비스
"""

import logging
import json
import re
from typing import Dict, List
from datetime import datetime

from sonju_ai.utils.openai_client import OpenAIClient
from sonju_ai.config.prompts import get_prompt

logger = logging.getLogger(__name__)

class TodoProcessor:
    """할일 추출 전용 서비스"""
    
    def __init__(self):
        """할일 추출 서비스 초기화"""
        self.openai_client = OpenAIClient()
        logger.info("할일 추출 서비스 초기화 완료")
    
    def extract_todos_from_conversation(self, user_input: str, user_id: str) -> Dict:
        """
        대화에서 일정/스케줄만 추출
        
        Args:
            user_input: 사용자 입력 텍스트
            user_id: 사용자 ID
            
        Returns:
            dict: {
                "tasks": [
                    {"task": "병원 가기", "time": "내일 오전 10시"},
                    {"task": "약 먹기", "time": "오늘 저녁"}
                ]
            }
        """
        try:
            # 할일 추출 프롬프트
            extraction_prompt = get_prompt("todo")
            
            # AI에게 할일 추출 요청
            user_message = f"""
다음 대화에서 일정/스케줄만 추출해주세요:

"{user_input}"

추출 기준:
- 추출: 구체적인 행동 + 시간 (병원, 약속, 전화, 장보기, 약 먹기 등)
- 제외: 학습 희망사항, 과거 이야기, 단순 대화

task 작성: 최대한 짧고 간결하게 (2~5 단어)
time 작성: 날짜/시간 명확하면 기록, 없으면 null

응답 형식:
{{
    "tasks": [
        {{
            "task": "간결한 할일",
            "time": "날짜/시간 또는 null"
        }}
    ]
}}

할일이 없으면: {{"tasks": []}}
"""
            
            response = self.openai_client.simple_chat(user_message, extraction_prompt)
            
            # 응답 파싱
            extraction_result = self._parse_extraction_response(response)
            
            # 로깅
            task_count = len(extraction_result.get("tasks", []))
            logger.info(f"할일 추출 완료 - 사용자: {user_id}, 추출된 할일: {task_count}개")
            
            return extraction_result
            
        except Exception as e:
            logger.error(f"할일 추출 중 오류 - 사용자: {user_id}, 오류: {e}")
            return {"tasks": []}
    
    def _parse_extraction_response(self, response: str) -> Dict:
        """AI 응답을 파싱하여 구조화된 할일 목록 생성"""
        try:
            # JSON 추출을 위한 정규식 패턴
            json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
            json_match = re.search(json_pattern, response, re.DOTALL)
            
            if not json_match:
                logger.warning("응답에서 JSON을 찾을 수 없습니다")
                return {"tasks": []}
            
            # JSON 안정성 강화: 앞뒤 불필요한 텍스트 제거
            json_str = json_match.group().strip()
            json_str = re.sub(r'^[^{]*', '', json_str)
            json_str = re.sub(r'[^}]*$', '', json_str)
            
            result = json.loads(json_str)
            
            # tasks 키가 있고 리스트인지 확인
            if "tasks" not in result or not isinstance(result["tasks"], list):
                logger.warning("잘못된 응답 형식: tasks 키가 없거나 리스트가 아님")
                return {"tasks": []}
            
            # 각 태스크 검증 및 정제
            valid_tasks = []
            for task in result["tasks"]:
                if isinstance(task, dict) and "task" in task:
                    # 필수 필드 보정
                    cleaned_task = {
                        "task": str(task.get("task", "")).strip(),
                        "time": task.get("time")
                    }
                    
                    # 빈 할일은 제외
                    if cleaned_task["task"]:
                        valid_tasks.append(cleaned_task)
            
            # 중복 할일 필터링
            seen = set()
            unique_tasks = []
            for task in valid_tasks:
                task_key = task["task"].lower().strip()
                if task_key not in seen:
                    seen.add(task_key)
                    unique_tasks.append(task)
            
            return {"tasks": unique_tasks}
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON 파싱 오류: {e}")
            return {"tasks": []}
        except Exception as e:
            logger.error(f"응답 파싱 중 예상치 못한 오류: {e}")
            return {"tasks": []}
    
    def format_extracted_todos(self, extraction_result: Dict) -> str:
        """
        추출된 할일을 사용자용 텍스트로 포맷
        
        Args:
            extraction_result: extract_todos_from_conversation의 결과
            
        Returns:
            str: 포맷된 할일 목록 텍스트
        """
        tasks = extraction_result.get("tasks", [])
        
        if not tasks:
            return "추출된 할일이 없습니다."
        
        lines = [f"추출된 할일 {len(tasks)}개:"]
        
        for i, task in enumerate(tasks, 1):
            task_text = f"{i}. {task['task']}"
            
            # 시간 정보 추가
            if task.get("time"):
                task_text += f" ({task['time']})"
            
            lines.append(task_text)
        
        return "\n".join(lines)
    
    def get_tasks_list(self, extraction_result: Dict) -> List[Dict]:
        """
        API 응답용 태스크 리스트 반환
        
        Args:
            extraction_result: extract_todos_from_conversation의 결과
            
        Returns:
            list: 태스크 딕셔너리 리스트
        """
        return extraction_result.get("tasks", [])


# 간단한 테스트 실행
if __name__ == "__main__":
    try:
        processor = TodoProcessor()
        
        # 테스트 케이스들
        test_cases = [
            "내일 오전 10시에 병원 가야 해요",
            "카카오톡으로 사진 보내는 법 배우고 싶어요",
            "내일 마트 가서 장보고, 저녁에는 드라마 봐야지"
        ]
        
        print("=== 손주톡톡 할일 추출 테스트 ===\n")
        
        for user_input in test_cases:
            print(f"📝 입력: {user_input}")
            
            result = processor.extract_todos_from_conversation(user_input, "test_user")
            formatted = processor.format_extracted_todos(result)
            
            print(f"✅ {formatted}\n")
        
    except Exception as e:
        print(f"테스트 중 오류: {e}")