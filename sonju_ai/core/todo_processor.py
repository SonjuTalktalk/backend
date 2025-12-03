"""
손주톡톡 할일 추출 서비스
대화에서 자동으로 할일을 추출하는 AI 서비스 (대화형)
"""

import logging
import json
import re
from typing import Dict, Optional, Tuple

from sonju_ai.utils.openai_client import OpenAIClient

logger = logging.getLogger(__name__)


class TodoProcessor:
    """
    채팅 도중에 자연스럽게 "응", "아니" 등으로
    할일 등록을 이어갈 수 있도록 상태를 들고 있는 클래스.

    - pending_todos[(user_id, chat_list_num)] 에 현재 진행 중인 플로우를 저장한다.
    - step 값은 다음 중 하나다.
      - "none"        : 이번 턴에는 할일 관련 없음
      - "suggest"     : 새 할일 후보 감지 → 등록 여부만 물어본 상태
      - "ask_confirm" : (내부 state) 유저에게 yes/no를 물은 상태
      - "ask_date"    : 날짜/시간 추가 질문 상태
      - "saved"       : 이번 턴에서 할일이 확정됨
      - "cancelled"   : 유저가 거절해서 취소됨
    """

    def __init__(self) -> None:
        self.openai_client = OpenAIClient()
        # key: (user_id, chat_list_num)
        self.pending_todos: Dict[Tuple[str, int], Dict] = {}

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    def process_message(
        self,
        user_input: str,
        user_id: str,
        chat_list_num: int,
    ) -> Dict:
        """
        한 턴의 유저 발화를 받아서
        - 필요한 경우 할일 후보를 감지하고
        - 진행 중인 플로우(예/아니오, 날짜 물어보기 등)를 이어간다.

        반환 형식 예시:
        {
            "response": "~~~",   # 할일 관련 AI 멘트 (없을 수도 있음)
            "has_todo": False,   # 이번 턴에 실제로 할일이 확정/저장됐는지
            "task": "병원 가기",
            "date": "내일",
            "time": "오전 10시",
            "step": "suggest" | "ask_confirm" | "ask_date" | "saved" | "cancelled" | "none",
        }
        """
        key = (user_id, chat_list_num)

        try:
            # 1) 이미 진행 중인 플로우가 있으면 그걸 먼저 처리
            if key in self.pending_todos:
                return self._handle_pending_todo(key, user_input)

            # 2) 없으면 이번 발화에서 새 할일을 감지
            return self._detect_new_todo(key, user_input, user_id)

        except Exception as e:
            logger.error(
                f"[TodoProcessor] process_message 중 오류 - user_id={user_id}, err={e}"
            )
            return self._result_none()

    # ------------------------------------------------------------------
    # 내부 상태 처리
    # ------------------------------------------------------------------
    def _handle_pending_todo(self, key: Tuple[str, int], user_input: str) -> Dict:
        pending = self.pending_todos.get(key)
        if not pending:
            return self._result_none()

        state = pending.get("state")

        # 1) 예/아니오 대기 상태
        if state == "ask_confirm":
            yn = self._normalize_yn(user_input)

            # (1) YES → 날짜가 이미 있으면 바로 saved
            if yn == "yes":
                task = pending.get("task")
                date = pending.get("date")
                time = pending.get("time")

                if date:
                    # 이미 날짜가 있을 때는 이번 턴에서 확정
                    del self.pending_todos[key]
                    return {
                        "response": f"좋아요. '{task}' 할일을 등록해 둘게요.",
                        "has_todo": True,
                        "task": task,
                        "date": date,
                        "time": time,
                        "step": "saved",
                    }
                else:
                    # 날짜가 없으면 날짜를 물어보는 단계로 전환
                    pending["state"] = "ask_date"
                    self.pending_todos[key] = pending
                    return {
                        "response": "언제까지 해야 하는 일인지 날짜나 대략적인 시점을 알려줄래요? (예: 내일, 이번 주 토요일, 11월 25일)",
                        "has_todo": False,
                        "task": pending.get("task"),
                        "date": None,
                        "time": None,
                        "step": "ask_date",
                    }

            # (2) NO → 플로우 종료
            if yn == "no":
                del self.pending_todos[key]
                return {
                    "response": "알겠어요. 이번 건은 할일로 등록하지 않을게요.",
                    "has_todo": False,
                    "task": None,
                    "date": None,
                    "time": None,
                    "step": "cancelled",
                }

            # (3) 애매한 답 → 그냥 플로우 종료하고 일반 대화로 넘김
            del self.pending_todos[key]
            return self._result_none()

        # 2) 날짜/시간을 기다리는 상태
        if state == "ask_date":
            task = pending.get("task")
            # 여기서는 user_input 전체를 date 문자열로 받아두고,
            # 실제 date/time 파싱은 백엔드 라우터(_parse_korean_natural_datetime)에서 처리한다.
            date_text = user_input.strip()

            del self.pending_todos[key]
            return {
                "response": f"좋아요. '{task}'를 '{date_text}'까지 해야 할 일로 등록해 둘게요.",
                "has_todo": True,
                "task": task,
                "date": date_text,
                "time": None,
                "step": "saved",
            }

        # 그 외 알 수 없는 state → 방어적으로 초기화
        del self.pending_todos[key]
        return self._result_none()

    def _detect_new_todo(
        self,
        key: Tuple[str, int],
        user_input: str,
        user_id: str,
    ) -> Dict:
        """
        새 할일 후보를 LLM으로 감지하는 부분.
        """
        try:
            extracted = self._call_todo_extractor(user_input, user_id)
        except Exception:
            logger.exception("[TodoProcessor] 할일 추출 중 오류")
            return self._result_none()

        if not extracted or not extracted.get("has_todo"):
            return self._result_none()

        task = (extracted.get("task") or "").strip()
        date = (extracted.get("date") or "").strip() or None
        time = (extracted.get("time") or "").strip() or None

        # 안전장치: has_todo=True 인데 task가 비어 있으면 무시
        if not task:
            logger.warning(
                "[TodoProcessor] has_todo=True 이지만 task 가 비어 있어서 무시합니다. extracted=%s",
                extracted,
            )
            return self._result_none()

        # pending 으로 등록해서 다음 턴에서 "응/아니"로 이어갈 수 있도록 함
        self.pending_todos[key] = {
            "state": "ask_confirm",
            "task": task,
            "date": date,
            "time": time,
        }

        suggestion = f"지금 말씀하신 '{task}'를 할일 목록에 등록해 둘까요?"

        return {
            "response": suggestion,
            # 아직 사용자가 '응'을 안 했으므로 실제로 저장된 할일은 아님
            "has_todo": False,
            "task": task,
            "date": date,
            "time": time,
            "step": "suggest",
        }

    # ------------------------------------------------------------------
    # LLM 호출 및 유틸
    # ------------------------------------------------------------------
    def _call_todo_extractor(self, user_input: str, user_id: str) -> Dict:
        """
        실제 LLM 호출 부분.

        - OpenAIClient.chat_completion(...) 사용
        - response_format={"type": "json_object"} 로 JSON만 돌려받도록 요청
        """
        system_msg = (
            "너는 사용자의 한국어 대화에서 '할일(todo)'를 찾아내는 도우미야. "
            "사용자가 해야 할 일을 말하면, 그것을 JSON 형식으로 정리해줘.\n\n"
            "반드시 아래 스키마를 만족하는 JSON만 반환해야 해.\n"
            '예: {"has_todo": true, "task": "병원 가기", "date": "내일", "time": "오전 10시"}'
        )
        user_msg = (
            "다음 문장에서 사용자가 해야 할 일이 있는지 찾아줘.\n"
            f"문장: {user_input}\n\n"
            "반환 형식(JSON): "
            '{"has_todo": bool, "task": str | null, "date": str | null, "time": str | null}'
        )

        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ]

        # OpenAIClient.chat_completion 은 문자열을 돌려준다.
        response_text = self.openai_client.chat_completion(
            messages=messages,
            max_tokens=300,
            temperature=0.2,
            response_format={"type": "json_object"},
        )

        return self._parse_todo_json(response_text)

    def _parse_todo_json(self, response: str) -> Dict:
        """
        LLM 응답 문자열에서 JSON 덩어리만 뽑아서 dict 로 변환.
        (response_format 을 JSON 으로 요청했어도 방어적으로 한 번 더 처리)
        """
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        # 텍스트 안에 포함된 JSON 조각 찾기
        json_pattern = r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}"
        json_match = re.search(json_pattern, response, re.DOTALL)

        if json_match:
            json_str = json_match.group().strip()
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                logger.error(
                    f"[TodoProcessor] JSON 파싱 실패(부분 문자열): {json_str[:150]}"
                )

        logger.error(f"[TodoProcessor] JSON 파싱 실패: {response[:150]}")
        return {}

    def _normalize_yn(self, text: str) -> str:
        """
        사용자의 짧은 답변을 yes/no/other 로 정규화.
        """
        t = text.strip().lower()

        # 한국어/영어 긍정
        yes_keywords = [
            "응",
            "어",
            "어어",
            "그래",
            "좋아",
            "넵",
            "네",
            "예",
            "웅",
            "ㅇㅇ",
            "ok",
            "okay",
            "예스",
            "ㅇㅋ",
        ]
        no_keywords = [
            "아니",
            "아냐",
            "ㄴㄴ",
            "노",
            "no",
            "괜찮아",
            "됐어",
        ]

        for kw in yes_keywords:
            if kw in t:
                return "yes"
        for kw in no_keywords:
            if kw in t:
                return "no"

        return "other"

    def _result_none(self) -> Dict:
        """
        할일 관련 동작이 전혀 없을 때 공통으로 쓰는 기본 응답.
        """
        return {
            "response": "",
            "has_todo": False,
            "task": None,
            "date": None,
            "time": None,
            "step": "none",
        }
