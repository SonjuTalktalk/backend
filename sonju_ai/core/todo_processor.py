"""
손주톡톡 할일 추출 서비스
대화에서 자동으로 할일을 추출하는 AI 서비스 (대화형)
"""

import logging
import json
import re
from typing import Dict, Optional

from sonju_ai.utils.openai_client import OpenAIClient

logger = logging.getLogger(__name__)


class TodoProcessor:
    """
    할일 추출 전용 서비스 (대화형 상태 머신)

    - 한 턴에서 새 할일 후보를 발견하면: "지금 말씀하신 '~'를 할일로 등록해 둘까요?" 제안(suggest)
    - 이후 사용자의 "응/추가해줘/아니야/내일 오후 3시" 등의 응답에 따라:
      - 최종 확정되면 has_todo=True, step="saved"
      - 취소되면 step="cancelled"
      - 무시하고 다른 얘기하면 → 이 pending은 버리고 step="none" 으로 종료

    🔒 불변식(invariant):
      - 할일 플로우( step in {"suggest","ask_date","saved","cancelled"} )에 들어가는 순간,
        task는 반드시 존재한다 (None 불가).
      - has_todo=True 인 결과에서는 항상 task가 존재하고 date는 필수, time은 옵션.
    """

    def __init__(self) -> None:
        self.openai_client = OpenAIClient()
        # {user_id: {"state": "ask_confirm"|"ask_date",
        #            "task": str, "date": Optional[str], "time": Optional[str]}}
        self.pending_todos: Dict[str, Dict] = {}
        logger.info("할일 추출 서비스 초기화 완료 (대화형)")

    # ------------------------------------------------------------------
    # 외부에서 호출하는 메인 진입점
    # ------------------------------------------------------------------
    def process_message(self, user_input: str, user_id: str) -> Dict:
        """
        사용자 메시지를 처리하여 할일 추출 진행

        Returns:
            {
                "has_todo": bool,        # 최종 확정(saved)된 경우에만 True
                "response": Optional[str],  # 이번 턴에 '할일 관련'으로 AI가 말해야 할 문장
                "task": Optional[str],
                "date": Optional[str],      # 자연어 (예: "내일")
                "time": Optional[str],      # 자연어 (예: "오전 10시")
                "step": str,                # "none" | "suggest" | "ask_date" | "saved" | "cancelled"
            }
        """
        try:
            # 1. 이미 진행 중인 할일 플로우가 있으면, 그거 먼저 처리
            if user_id in self.pending_todos:
                return self._handle_pending_todo(user_input, user_id)

            # 2. 새로운 할일 감지 (GPT 호출)
            detection_result = self._detect_new_todo(user_input)

            has_todo = bool(detection_result.get("has_todo"))
            task = detection_result.get("task")
            date = detection_result.get("date")
            time = detection_result.get("time")

            # 🔒 불변식: "할일로 감지됐다"고 들어오려면 task는 반드시 있어야 한다.
            # → has_todo=True인데 task가 없으면, 이번 턴은 그냥 일반 대화로 처리(step="none")
            if not (has_todo and task):
                if has_todo and not task:
                    logger.warning(
                        "[TodoProcessor] has_todo=True인데 task가 없음. "
                        f"입력: {user_input!r}, detection_result={detection_result}"
                    )
                return {
                    "has_todo": False,
                    "response": None,
                    "task": None,
                    "date": None,
                    "time": None,
                    "step": "none",
                }

            # 여기 도달했다 = has_todo=True AND task not None ✅
            # 날짜가 있든 없든, 첫 단계는 항상 "등록해 둘까요?" (suggest)
            self.pending_todos[user_id] = {
                "state": "ask_confirm",
                "task": task,
                "date": date,  # None 가능
                "time": time,  # None 가능
            }

            return {
                "has_todo": False,  # 아직 유저가 예/아니요 안 했으니까 확정 X
                "response": f"지금 말씀하신 '{task}'를 할일로 등록해 둘까요?",
                "task": task,
                "date": date,
                "time": time,
                "step": "suggest",
            }

        except Exception as e:
            logger.error(f"[TodoProcessor] process_message 중 오류 - user_id={user_id}, err={e}")
            return {
                "has_todo": False,
                "response": None,
                "task": None,
                "date": None,
                "time": None,
                "step": "none",
            }

    # ------------------------------------------------------------------
    # 내부 상태 처리 로직
    # ------------------------------------------------------------------
    def _handle_pending_todo(self, user_input: str, user_id: str) -> Dict:
        """
        이미 pending_todos 에 저장된 할일 흐름에 대해
        사용자의 후속 입력(예/아니요/날짜)을 처리한다.
        """
        pending = self.pending_todos[user_id]
        state = pending["state"]

        # 1) "등록해 둘까요?"에 대한 예/아니요 응답 단계
        if state == "ask_confirm":
            confirmation = self._parse_confirmation(user_input)

            if confirmation == "yes":
                task = pending["task"]
                date = pending["date"]
                time = pending["time"]

                # 날짜가 이미 있는 경우 → 바로 확정 (saved)
                if date:
                    del self.pending_todos[user_id]

                    msg = (
                        f"네, {date}"
                        + (f" {time}" if time else "")
                        + f"에 '{task}' 일정으로 등록해 둘게요."
                    )
                    return {
                        "has_todo": True,
                        "response": msg,
                        "task": task,
                        "date": date,
                        "time": time,
                        "step": "saved",
                    }

                # 날짜가 없는 경우 → 날짜를 물어보는 단계로 전환
                self.pending_todos[user_id]["state"] = "ask_date"
                return {
                    "has_todo": False,
                    "response": (
                        "할일을 등록하려면 날짜가 필요해요.\n"
                        "날짜를 알려주시면 추가해 드릴게요.\n"
                        "예: 내일, 내일 오전 10시, 11월 25일"
                    ),
                    "task": task,
                    "date": None,
                    "time": None,
                    "step": "ask_date",
                }

            if confirmation == "no":
                # 사용자가 거절 → 이 pending은 버리고 종료
                del self.pending_todos[user_id]
                return {
                    "has_todo": False,
                    "response": "알겠어요, 일정으로는 따로 남기지 않을게요.",
                    "task": None,
                    "date": None,
                    "time": None,
                    "step": "cancelled",
                }

            # 🔥 그 외(응답이 애매하거나, 다른 얘기) → 이 pending을 버리고 일반 대화로 전환
            del self.pending_todos[user_id]
            return {
                "has_todo": False,
                "response": None,   # 별도 할일 멘트 없이 일반 챗으로 넘어가게 함
                "task": None,
                "date": None,
                "time": None,
                "step": "none",
            }

        # 2) 날짜/시간을 물어보는 단계
        if state == "ask_date":
            datetime_result = self._parse_datetime(user_input)
            date = datetime_result.get("date")
            time = datetime_result.get("time")

            if date:
                task = pending["task"]
                del self.pending_todos[user_id]

                msg = (
                    f"네, {date}"
                    + (f" {time}" if time else "")
                    + f"에 '{task}' 일정으로 등록해 둘게요."
                )
                return {
                    "has_todo": True,
                    "response": msg,
                    "task": task,
                    "date": date,
                    "time": time,
                    "step": "saved",
                }

            # 🔥 날짜가 전혀 안 잡힌 경우 = 사용자가 다른 얘기를 한 걸로 보고 이 pending을 버림
            del self.pending_todos[user_id]
            return {
                "has_todo": False,
                "response": None,   # 일반 챗으로 전환
                "task": None,
                "date": None,
                "time": None,
                "step": "none",
            }

        # 알 수 없는 상태 → 초기화
        del self.pending_todos[user_id]
        return {
            "has_todo": False,
            "response": None,
            "task": None,
            "date": None,
            "time": None,
            "step": "none",
        }

    # ------------------------------------------------------------------
    # GPT를 사용한 "새 할일 감지" / "날짜/시간 파싱"
    # ------------------------------------------------------------------
    def _detect_new_todo(self, user_input: str) -> Dict:
        """새로운 할일 감지 (GPT 호출)"""
        try:
            detection_prompt = """사용자 메시지에서 구체적인 일정이나 할일을 찾아주세요.

[추출 기준]
- 구체적인 "행동 + 대상"이 분명한 경우만 추출
  - 예: "내일 오전 10시에 병원 가야 해요" → task: "병원 가기"
  - 예: "도서관에 가야 해" → task: "도서관 가기"
  - 예: "손주한테 전화해야겠다" → task: "손주에게 전화하기"
- 단순한 시간 언급(예: "내일 9시에 가야 해")처럼
  '어디에/무엇을'이 없는 경우에는 할일로 보지 마세요.

[중요 규칙]
- task는 짧은 한국어 표현으로만 써야 합니다. (예: "병원 가기", "손주에게 전화하기")
- task를 분명하게 정할 수 없다면, 반드시 has_todo를 false로 설정하세요.

[응답 형식]
반드시 아래 JSON 형식 '하나만' 반환하세요. 설명 문장 없이 JSON만 출력하세요.

{
  "has_todo": true,
  "task": "병원 가기",
  "date": "내일",
  "time": "오전 10시"
}

- 할일이 없거나 task를 정하기 어렵다면:
  {"has_todo": false, "task": null, "date": null, "time": null}
- 날짜/시간이 없으면 해당 필드는 null
"""

            user_message = f'사용자 메시지: "{user_input}"\n\n위 메시지에서 할일을 찾아 JSON으로만 답변하세요.'
            response = self.openai_client.simple_chat(user_message, detection_prompt)
            result = self._parse_json_response(response)

            has_todo = bool(result.get("has_todo"))
            task = result.get("task") if has_todo else None
            date = result.get("date") if has_todo else None
            time = result.get("time") if has_todo else None

            return {
                "has_todo": has_todo,
                "task": task,
                "date": date,
                "time": time,
            }

        except Exception as e:
            logger.error(f"[TodoProcessor] 할일 감지 중 오류: {e}")
            return {"has_todo": False, "task": None, "date": None, "time": None}

    def _parse_confirmation(self, user_input: str) -> str:
        """
        확인 응답 파싱 (예/아니요)

        - "응", "예", "네", "추가해줘", "등록해줘", "넣어줘", "기억해줘" 등 → yes
        - "아니", "싫어", "필요 없어", "괜찮아" 등 → no
        - 그 밖에 다른 얘기 → unknown
        """
        text = user_input.strip().lower()

        yes_keywords = [
            "응", "예", "네", "좋아", "그래", "맞아",
            "ok", "okay", "ㅇㅋ", "ㅇㅇ",
            "추가", "등록", "넣어", "넣어줘", "해줘", "해 주세요", "해줘요",
            "해놓", "기억해", "기억해줘",
        ]
        no_keywords = [
            "아니", "아냐", "안", "싫어", "그만", "그냥 놔둬",
            "no", "ㄴㄴ", "거절", "말아", "필요없", "필요 없어", "괜찮아",
        ]

        if any(word in text for word in yes_keywords):
            return "yes"

        if any(word in text for word in no_keywords):
            return "no"

        return "unknown"

    def _parse_datetime(self, user_input: str) -> Dict:
        """날짜/시간 파싱 (GPT 호출)"""
        try:
            parse_prompt = """사용자가 입력한 날짜/시간을 추출해주세요.

[응답 형식]
반드시 아래 JSON 형식 '하나만' 반환하세요. 설명 문장 없이 JSON만 출력하세요.

{
  "date": "내일",
  "time": "오전 10시"
}

- 시간이 없으면 time은 null
- 날짜를 찾을 수 없으면 date와 time 모두 null
"""

            user_message = f'사용자 입력: "{user_input}"\n\n날짜와 시간을 추출해서 JSON으로만 답변하세요.'
            response = self.openai_client.simple_chat(user_message, parse_prompt)
            result = self._parse_json_response(response)

            date = result.get("date")
            time = result.get("time")
            return {"date": date, "time": time}

        except Exception as e:
            logger.error(f"[TodoProcessor] 날짜/시간 파싱 중 오류: {e}")
            return {"date": None, "time": None}

    def _parse_json_response(self, response: str) -> Dict:
        """GPT 응답에서 JSON 추출 및 파싱"""
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            # {...} 패턴만 추출해서 다시 시도
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
