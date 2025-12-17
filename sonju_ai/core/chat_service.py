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

# ✅ 모든 ChatService 인스턴스가 공유할 TodoProcessor (유저+방 단위 상태 유지)
_SHARED_TODO_PROCESSOR = TodoProcessor()

# 🆕 성격(model_type)별 TTS 음성 매핑
# - AiProfile.personality 값(friendly/active/pleasant/reliable)과 키를 맞춤
VOICE_MAPPING = {
    "friendly": "sage",
    "active": "coral",
    "pleasant": "nova",
    "reliable": "verse",
}


def resolve_tts_voice(model_type: str) -> str:
    """model_type에 맞는 TTS voice 반환"""
    return VOICE_MAPPING.get(model_type, "nova")


class ChatService:
    """손주톡톡 메인 채팅 서비스 (4개 AI 모델 + 대화형 할일 추출 + TTS)"""

    def __init__(
        self,
        ai_name: str = "손주",
        model_type: str = "friendly",
        todo_processor: Optional[TodoProcessor] = None,
    ) -> None:
        # 모델 타입 유효성 검사
        self.model_type = validate_model_type(model_type)
        self.ai_name = ai_name

        self.openai_client = OpenAIClient()
        # 주입받지 않으면 전역 공유 인스턴스 사용
        self.todo_processor = todo_processor or _SHARED_TODO_PROCESSOR

        logger.info(
            "채팅 서비스 초기화 완료 (AI 이름: %s, 모델: %s)",
            self.ai_name,
            self.model_type,
        )

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    def chat(
        self,
        user_id: str,
        message: str,
        history: List[Dict],
        enable_tts: bool = False,
        chat_list_num: Optional[int] = None,
    ) -> Dict:
        """
        한 턴의 사용자 메시지에 대한 AI 응답 + 할일 추출 결과를 함께 반환한다.

        반환 형식 예시:
        {
            "response": "...",          # AI 텍스트
            "timestamp": "...",         # ISO 문자열
            "ai_name": "손주",
            "model_type": "friendly",
            "tts_path": "outputs/tts/..." | None,
            "has_todo": True/False,
            "task": "...",
            "date": "...",
            "time": "...",
            "step": "none|suggest|ask_confirm|ask_date|saved|cancelled",
        }
        """
        if chat_list_num is None:
            chat_list_num = 0

        try:
            # 1) 우선 TodoProcessor로 이번 메시지를 전달해서
            #    할일 플로우 상태를 먼저 확인한다.
            todo_result = self.todo_processor.process_message(
                user_input=message,
                user_id=user_id,
                chat_list_num=chat_list_num,
            )

            step = todo_result.get("step", "none")
            has_todo = todo_result.get("has_todo", False)
            todo_resp = (todo_result.get("response") or "").strip()

            # 2) step 에 따라 메인 챗봇 호출 여부 결정
            #
            #   - ask_confirm / ask_date / saved / cancelled:
            #       → Todo 관련 멘트만 주고, 메인 챗봇은 부르지 않는다.
            #   - suggest:
            #       → 메인 챗봇 답변 + "할일로 등록해 줄까?" 멘트를 합쳐서 전달
            #   - none:
            #       → 순수 메인 챗봇만 호출
            if step in {"ask_confirm", "ask_date", "saved", "cancelled"} and todo_resp:
                # 할일 플로우용 멘트만 사용
                ai_text = todo_resp
            else:
                # 메인 챗봇 호출
                main_answer = self._call_main_chat(
                    message=message,
                    history=history,
                )

                if step == "suggest" and todo_resp:
                    # 새 할일 후보가 감지된 경우 → 메인 답변 뒤에 제안 문장 붙이기
                    ai_text = f"{main_answer}\n\n{todo_resp}"
                else:
                    ai_text = main_answer

            # 3) 필요 시 TTS 생성
            tts_path: Optional[str] = None
            if enable_tts and ai_text:
                try:
                    tts_path = self._generate_tts(ai_text)
                except Exception as e:
                    # TTS 실패는 치명적이지 않으니 로깅만 하고 넘어간다.
                    logger.exception(f"[ChatService] TTS 생성 실패: {e}")

            # 4) 최종 결과 묶어서 반환
            return {
                "response": ai_text,
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

        except Exception as e:
            logger.error(f"[ChatService] chat 처리 중 예외 발생 - user_id={user_id}, err={e}")
            error_response = (
                "죄송해요, 잠시 문제가 생겨서 답변을 완전히 처리하지 못했어요. "
                "다시 한 번 말씀해 주실 수 있을까요?"
            )

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

    # ------------------------------------------------------------------
    # 내부 LLM 호출 및 TTS
    # ------------------------------------------------------------------
    def _call_main_chat(
        self,
        message: str,
        history: List[Dict],
    ) -> str:
        """
        실제 메인 챗봇(일상대화/격려 등) LLM을 호출하는 부분.

        - get_prompt("chat", model_type=..., ai_name=...) 형태로
          기존 prompts.py 의 타입에 맞춰 호출한다.
        """
        system_prompt = get_prompt(
            "chat",  # ✅ 여기 첫 번째 인자가 prompt_type
            model_type=self.model_type,
            ai_name=self.ai_name,
        )

        messages: List[Dict[str, str]] = [
            {"role": "system", "content": system_prompt},
        ]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": message})

        answer = self.openai_client.chat_completion(messages)
        return answer

    def _generate_tts(self, text: str) -> Optional[str]:
        """
        텍스트를 음성으로 변환하고, 저장된 경로를 반환한다.
        OpenAIClient.text_to_speech(...) 사용.
        """
        voice = resolve_tts_voice(self.model_type)
        return self.openai_client.text_to_speech(text, voice=voice)
