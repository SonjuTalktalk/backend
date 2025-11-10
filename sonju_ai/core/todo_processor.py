"""
손주톡톡 할일 추출 서비스
대화에서 자동으로 할일과 루틴을 추출하는 AI 서비스
"""

import logging
import json
import re
from typing import Dict, List, Optional
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
        대화에서 할일과 루틴 추출
        
        Args:
            user_input: 사용자 입력 텍스트
            user_id: 사용자 ID
            
        Returns:
            dict: {
                "tasks": [
                    {"task": "병원 가기", "time": "내일 오전", "category": "건강"},
                    {"task": "전화하기", "time": None, "category": "가족"}
                ]
            }
        """
        try:
            # 할일 추출 프롬프트
            extraction_prompt = get_prompt("todo")
            
            # AI에게 할일 추출 요청
            user_message = f"""
다음 대화에서 할일이나 해야 할 것들을 추출해주세요:

"{user_input}"

위 텍스트에서 어르신이 해야 할 구체적인 행동이나 일정이 있다면 추출해주세요.
단순한 대화나 과거 이야기는 제외하고, 실제로 해야 할 일만 추출해주세요.

카테고리 분류 기준:
- 건강: 약, 병원, 운동, 건강검진 관련
- 가족: 가족, 친구, 지인과의 연락·만남
- 학습: 배우기, 공부, 익히기, 새로운 기능 습득
- 일상: 가사, 장보기, 청소, 일상 생활 업무
- 취미: 여가, 즐기기, 드라마, 음악, 영화, 오락

응답은 반드시 다음 JSON 형식으로만 해주세요:
{{
    "tasks": [
        {{
            "task": "할일 내용",
            "time": "시간 정보 (없으면 null)",
            "category": "건강|가족|학습|일상|취미"
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
            json_str = re.sub(r'^[^{]*', '', json_str)  # JSON 앞 텍스트 제거
            json_str = re.sub(r'[^}]*$', '', json_str)  # JSON 뒤 텍스트 제거
            
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
                        "time": task.get("time"),
                        "category": task.get("category", "일상")
                    }
                    
                    # 빈 할일은 제외
                    if cleaned_task["task"]:
                        valid_tasks.append(cleaned_task)
            
            # 중복 할일 필터링
            seen = set()
            unique_tasks = []
            for task in valid_tasks:
                task_key = task["task"].lower().strip()  # 대소문자 구분 없이 중복 체크
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
            
            # 카테고리 추가
            if task.get("category"):
                task_text += f" - {task['category']}"
            
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
            "손주한테 안부 전화 드려야 하는데 까먹을까봐 걱정이 에요",
            "카카오톡으로 사진 보내는 법 배우고 싶어요",
            "매일 오후 3시에 약 먹어야 해",
            "주말마다 공원에서 산책하려고 해요",
            "오늘 날씨가 정말 좋네요",
            "손주가 어제 왔었어요",
            "내일 마트 가서 장보고, 저녁에는 드라마 봐야지",
            "요즘 혈압약 깜빡깜빡 해서 알람 맞춰놔야겠어"
        ]
        
        print("=== 손주톡톡 할일 추출 테스트 ===")
        
        for user_input in test_cases:
            print(f"📝 입력: {user_input}")
            
            result = processor.extract_todos_from_conversation(user_input, "test_user")
            formatted = processor.format_extracted_todos(result)
            
            print(f"✅ {formatted}")
            
        
    except Exception as e:
        print(f"테스트 중 오류: {e}")