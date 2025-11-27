"""
손주톡톡 채팅 서비스
메인 채팅 기능과 대화 관리 (4개 모델 지원 + 대화형 할일 추출 + TTS)
"""

import logging
from typing import List, Dict, Optional
from datetime import datetime

from sonju_ai.utils.openai_client import OpenAIClient
from sonju_ai.config.prompts import get_prompt, validate_model_type
from sonju_ai.core.todo_processor import TodoProcessor

logger = logging.getLogger(__name__)


class ChatService:
    """손주톡톡 메인 채팅 서비스 (4개 AI 모델 + 대화형 할일 추출 + TTS)"""

    def __init__(
        self,
        ai_name: str = "손주",
        model_type: str = "friendly",
    ):
        """
        Args:
            ai_name: AI 어시스턴트 이름
            model_type: AI 모델 타입
                - "friendly": 다정한
                - "active": 활발한
                - "pleasant": 유쾌한
                - "reliable": 듬직한
        """
        self.ai_name = ai_name
        self.model_type = validate_model_type(model_type)

        self.openai_client = OpenAIClient()
        self.todo_processor = TodoProcessor()  # 대화형 할일 추출 프로세서

        logger.info(
            f"채팅 서비스 초기화 완료 (AI 이름: {ai_name}, 모델: {self.model_type})"
        )

    def update_model_type(self, model_type: str):
        self.model_type = validate_model_type(model_type)
        logger.info(f"AI 모델 업데이트 완료: {self.model_type}")

    def update_ai_name(self, ai_name: str):
        self.ai_name = ai_name
        logger.info(f"AI 이름 업데이트 완료: {self.ai_name}")

    def chat(
        self,
        user_id: str,
        message: str,
        history: Optional[List[Dict]] = None,
        enable_tts: bool = False,
    ) -> Dict:
        """
        사용자와 채팅 (대화형 할일 추출 + TTS 지원)

        흐름:
          1) TodoProcessor로 '할일 관련 상태' 먼저 확인
          2) step에 따라:
             - none      → 순수 일반 채팅
             - suggest   → 일반 채팅 + "등록해 둘까요?" 문장 붙이기
             - ask_confirm / ask_date / saved / cancelled
                        → TodoProcessor가 준 문장만 사용 (일반 채팅 호출 X)

        Returns:
            dict:
            {
                "response": "AI 전체 응답 문자열(할일 관련 멘트 포함)",
                "timestamp": "ISO8601",
                "ai_name": str,
                "model_type": str,
                "tts_path": Optional[str],

                "has_todo": bool,   # 최종 확정된 경우에만 True
                "task": Optional[str],
                "date": Optional[str],   # 자연어: "내일"
                "time": Optional[str],   # 자연어: "오전 10시"
                "step": str,             # "none" | "suggest" | "ask_confirm" | "ask_date" | "saved" | "cancelled"
            }
        """
        try:
            # 1) 할일 상태/후보 먼저 확인
            todo_result = self.todo_processor.process_message(message, user_id)
            step = todo_result.get("step", "none")
            todo_resp = todo_result.get("response")
            has_todo = bool(todo_result.get("has_todo"))

            # 2) 후속 대화(예/아니요/날짜 입력 등)만 있는 경우:
            #    일반 ChatCompletion 호출하지 않고, TodoProcessor가 준 문장만 사용
            if step in ("ask_confirm", "ask_date", "saved", "cancelled"):
                ai_response = todo_resp or "알겠어요."
                tts_path = None
                if enable_tts:
                    tts_path = self.openai_client.text_to_speech(ai_response)

                return {
                    "response": ai_response,
                    "timestamp": datetime.now().isoformat(),
                    "ai_name": self.ai_name,
                    "model_type": self.model_type,
                    "tts_path": tts_path,
                    "has_todo": has_todo,
                    "task": todo_result.get("task"),
                    "date": todo_result.get("date"),
                    "time": todo_result.get("time"),
                    "step": step,
                }

            # 3) 새 할일 후보가 감지된 경우 → 일반 답변 + "등록해 둘까요?" 문장 붙이기
            if step == "suggest" and todo_resp:
                system_prompt = get_prompt(
                    "chat",
                    model_type=self.model_type,
                    ai_name=self.ai_name,
                )
                messages = [{"role": "system", "content": system_prompt}]
                if history:
                    messages.extend(history)
                messages.append({"role": "user", "content": message})

                main_answer = self.openai_client.chat_completion(messages)

                # 한 메시지 안에 메인 답변 + 제안 문장
                combined = f"{main_answer}\n\n{todo_resp}"

                tts_path = None
                if enable_tts:
                    tts_path = self.openai_client.text_to_speech(combined)

                return {
                    "response": combined,
                    "timestamp": datetime.now().isoformat(),
                    "ai_name": self.ai_name,
                    "model_type": self.model_type,
                    "tts_path": tts_path,
                    "has_todo": False,  # 아직 확정 전
                    "task": todo_result.get("task"),
                    "date": todo_result.get("date"),
                    "time": todo_result.get("time"),
                    "step": step,
                }

            # 4) 할일과 전혀 상관없는 일반 대화
            system_prompt = get_prompt(
                "chat",
                model_type=self.model_type,
                ai_name=self.ai_name,
            )

            messages = [{"role": "system", "content": system_prompt}]
            if history:
                messages.extend(history)
            messages.append({"role": "user", "content": message})

            ai_response = self.openai_client.chat_completion(messages)

            tts_path = None
            if enable_tts:
                tts_path = self.openai_client.text_to_speech(ai_response)

            return {
                "response": ai_response,
                "timestamp": datetime.now().isoformat(),
                "ai_name": self.ai_name,
                "model_type": self.model_type,
                "tts_path": tts_path,
                "has_todo": False,
                "task": None,
                "date": None,
                "time": None,
                "step": "none",
            }

        except Exception as e:
            logger.error(f"채팅 처리 중 오류 발생 - 사용자: {user_id}, 오류: {e}")
            error_response = "죄송해요, 잠시 문제가 생겼어요. 다시 한 번 말씀해 주시겠어요?"

            return {
                "response": error_response,
                "timestamp": datetime.now().isoformat(),
                "ai_name": self.ai_name,
                "model_type": self.model_type,
                "tts_path": None,
                "has_todo": False,
                "task": None,
                "date": None,
                "time": None,
                "step": "none",
            }

    # 아래 generate_encouragement / analyze_user_pattern 함수는 기존 코드 그대로 두면 됨
