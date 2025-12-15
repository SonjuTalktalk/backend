"""
손주톡톡 할일 추출 서비스
대화에서 자동으로 할일을 추출하는 AI 서비스 (대화형)
"""

import logging
import json
import re
from typing import Dict, Optional, Tuple
from datetime import datetime
from zoneinfo import ZoneInfo

from sonju_ai.utils.openai_client import OpenAIClient

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")


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
            "date": "2025-12-10",   # 가능하면 YYYY-MM-DD
            "time": "15:00",        # 가능하면 HH:MM (24시간제)
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
                    msg = self._build_saved_message(task, date, time)
                    return {
                        "response": msg,
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
                        "response": (
                            "언제까지 해야 하는 일인지 날짜나 대략적인 시점을 알려줄래요? "
                            "(예: 내일, 이번 주 토요일, 11월 25일)"
                        ),
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

        task_raw = (extracted.get("task") or "").strip()
        date = (extracted.get("date") or "").strip() or None
        time_raw = (extracted.get("time") or "").strip()

        # time 후처리: 빈 문자열이나 "00:00" 같은 기본값은 None으로 처리
        if time_raw in ("", "00:00", "00:00:00", "0:00"):
            time = None
        else:
            time = time_raw

        task = task_raw

        # 안전장치: has_todo=True 인데 task가 비어 있으면 무시
        if not task:
            logger.warning(
                "[TodoProcessor] has_todo=True 이지만 task 가 비어 있어서 무시합니다. extracted=%s",
                extracted,
            )
            return self._result_none()

        # --------------------------------------------------------------
        # 1) "할일 등록해줘" 같이 '직접 등록 요청'인 경우 → 바로 saved/ask_date
        # --------------------------------------------------------------
        normalized = user_input.replace(" ", "")

        direct_register_keywords = [
            "할일등록",
            "할일로등록",
            "할일추가",
            "할일로추가",
        ]
        direct_register = (
            any(kw in normalized for kw in direct_register_keywords)
            or (
                any(
                    kw in normalized
                    for kw in ["등록해줘", "등록해주라", "등록해줄래", "등록해줘라"]
                )
                and ("할일" in normalized or "할일로" in normalized)
            )
        )

        if direct_register:
            # 날짜가 이미 있으면 → 바로 확정(saved)
            if date:
                self.pending_todos.pop(key, None)
                msg = self._build_saved_message(task, date, time)
                return {
                    "response": msg,
                    "has_todo": True,
                    "task": task,
                    "date": date,
                    "time": time,
                    "step": "saved",
                }
            else:
                # 날짜가 없으면 → 바로 날짜를 물어보는 단계로
                self.pending_todos[key] = {
                    "state": "ask_date",
                    "task": task,
                    "date": None,
                    "time": time,
                }
                return {
                    "response": (
                        "할일로 등록해 줄게요. 언제까지 해야 하는 일인지 "
                        "날짜나 대략적인 시점을 알려줄래요? "
                        "(예: 내일, 이번 주 토요일, 11월 25일)"
                    ),
                    "has_todo": False,
                    "task": task,
                    "date": None,
                    "time": None,
                    "step": "ask_date",
                }

        # --------------------------------------------------------------
        # 2) 일반적인 경우 → 제안 모드(suggest)로 플로우 시작
        # --------------------------------------------------------------
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
        - 여기서 날짜/시간을 최대한 절대값(YYYY-MM-DD, HH:MM)으로 정규화하도록 지시
        - task 는 '병원 가기', '약 먹기'처럼 짧은 할 일 제목으로 정리하도록 지시
        """
        now = datetime.now(KST)
        today_str = now.strftime("%Y-%m-%d")
        weekday_kr = ["월", "화", "수", "목", "금", "토", "일"][now.weekday()]

        system_msg = f"""
너는 사용자의 한국어 대화에서 '할일(todo)'을 찾아내는 도우미야.

[날짜/시간 처리 규칙]
- 오늘은 {today_str} {weekday_kr}요일 (KST 기준)이다.
- 사용자가 "오늘", "내일", "모레", "이번 주 토요일", "다음주 3시에"처럼
  상대적인 날짜/시간을 말하면, **반드시 절대 날짜/시간으로 계산해서** JSON에 넣어야 한다.
- date 필드는 가능하면 "YYYY-MM-DD" 형식으로 채운다.
- time 필드는 가능하면 24시간제 "HH:MM" 형식으로 채운다.
- 시각에 오전/오후가 명시되지 않은 경우에는 해당 숫자 그대로 시(hour)로 사용하고,
  분은 "00"으로 맞춘다. (예: "3시" → "03:00")
- "다음주" 단독 또는 "다음주 3시에" 같은 표현이 나오면:
  * 기준은 항상 "오늘({today_str})과 같은 요일의 다음 주"로 삼는다.
  * 예: 오늘이 수요일이면 "다음주 3시에"는
    → 오늘과 같은 요일(수요일)의 다음 주 날짜를 date에 넣어야 한다.

- **사용자가 시각(몇 시, 오전/오후, 몇 시 반 등)을 전혀 말하지 않은 경우에는**
  time 필드는 반드시 null 로 두어야 한다.
  "00:00" 처럼 임의의 기본값을 넣지 마라.

[task 작성 규칙 (중요)]
- task 는 사용자가 해야 할 일을 나타내는 **짧은 '할 일 제목'** 으로 써야 한다.
- 문장 전체를 그대로 쓰지 말고, 핵심 동작만 뽑아서 **동사 명사형(~하기, ~가기, ~사기 등)** 으로 작성해라.
- 어색한 표현(예: "병원에 가봐야할거", "청소를 좀 해야할 것 같음")은 자연스러운 제목으로 정리해라.

  예시:
  - "배가 아파서 내일 병원에 가봐야 할 것 같아"
    → task: "병원 가기"
  - "엄마 생신 선물도 사야지"
    → task: "엄마 생신 선물 사기"
  - "서류를 제출해야 되는데 자꾸 까먹네"
    → task: "서류 제출하기"
  - "약 먹는 거 잊지 말아야지"
    → task: "약 먹기"

- 다음은 **안 되는** task 예시:
  - "병원에 가봐야할거"  (문장 일부, 어색한 표현)
  - "서류를 제출해야 될 것 같음" (전체 문장)
  → 이런 경우는 각각 "병원 가기", "서류 제출하기"처럼 정리해서 넣어라.

[출력 규칙]
- 한 번에 하나의 사용자의 발화만 보고 아래 스키마를 만족하는 JSON **한 개만** 반환해.
- has_todo 가 false 이면 task, date, time 은 모두 null 로 채운다.
- JSON 이외의 텍스트는 절대 섞지 말고, 키 이름을 정확히 지켜라.
        """

        user_msg = (
            "다음 문장에서 사용자가 해야 할 일이 있는지 찾아줘.\n"
            f"문장: {user_input}\n\n"
            "반환 형식(JSON): "
            '{'
            '"has_todo": true 또는 false, '
            '"task": 문자열 또는 null, '
            '"date": "YYYY-MM-DD" 또는 null, '
            '"time": "HH:MM" 또는 null'
            '}\n\n'
            "- 날짜나 시간이 아예 언급되지 않으면 date/time 은 null 로 둬.\n"
            "- 상대적인 날짜/시간 표현이 있으면 위에서 설명한 규칙대로 절대 날짜/시간으로 바꿔서 넣어.\n"
            "- 시간을 말하지 않은 경우에는 time 에 절대로 \"00:00\" 같은 기본값을 넣지 말고 null 로 둬.\n"
            "- task 는 반드시 위의 'task 작성 규칙'을 지켜서 자연스러운 할 일 제목으로만 작성해."
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

        1차: 키워드 매칭 (빠르고 공짜)
        2차: 키워드로 못 잡으면 LLM에 분류 요청
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
            "엉",
            "해줘",
            "해주세요",
            "좋아요",
            "등록",
            "등록해줘",
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

        # 1차: 키워드 매칭
        for kw in yes_keywords:
            if kw in t:
                return "yes"
        for kw in no_keywords:
            if kw in t:
                return "no"

        # 2차: 키워드로 애매한 경우에만 LLM 분류
        try:
            return self._classify_yn_llm(text)
        except Exception as e:
            logger.error(f"[TodoProcessor] _classify_yn_llm 오류: {e}")
            return "other"

    def _classify_yn_llm(self, text: str) -> str:
        """
        LLM에게 이 발화가 yes/no/other 중 무엇인지 분류하도록 요청.

        - "yes": 할일 등록 제안에 대한 명확한 긍정
        - "no" : 할일 등록 제안에 대한 명확한 부정
        - "other": 질문에 대한 답이 아니거나 애매한 경우
        """
        system_msg = (
            "너는 한국어 대화에서 '이 대답이 어떤 제안(질문)에 대한 긍정/부정/기타인지'만 분류하는 도우미야.\n"
            "지금 상황은 보통 이런 흐름이야:\n"
            '- AI: \"지금 말씀하신 내용을 할일로 등록해 둘까요?\"\n'
            "- 사용자: 여러 가지 방식으로 대답함\n\n"
            "너는 사용자의 발화를 보고 다음 셋 중 하나로만 분류해야 해:\n"
            '- \"yes\": 제안(할일 등록)에 대한 분명한 긍정 '
            "(예: 응, 그래, 해야지, 등록해줘, 좋아요, 그렇게 해, 당연하지 등)\n"
            '- \"no\": 제안에 대한 분명한 부정 '
            "(예: 아니, 필요 없어, 됐어, 그냥 둘게, 그건 하지 말자 등)\n"
            '- \"other\": 질문에 대한 답이 아니거나, 맥락상 애매해서 확실히 yes/no라고 보기 어려운 경우\n\n'
            "반드시 JSON 형식으로만 짧게 답해야 해.\n"
            '예: {\"answer\": \"yes\"}'
        )

        user_msg = (
            "다음 사용자의 발화가 yes / no / other 중 무엇인지 분류해줘.\n"
            "사용자 발화:\n"
            f"{text}\n\n"
            '반환 형식(JSON): {"answer": "yes" | "no" | "other"}'
        )

        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ]

        resp = self.openai_client.chat_completion(
            messages=messages,
            max_tokens=30,
            temperature=0.0,
            response_format={"type": "json_object"},
        )

        try:
            data = json.loads(resp)
            ans = (data.get("answer") or "").strip().lower()
            if ans in ("yes", "no", "other"):
                return ans
        except json.JSONDecodeError:
            logger.error(
                f"[TodoProcessor] _classify_yn_llm JSON 파싱 실패: {resp[:100]}"
            )

        return "other"

    def _build_saved_message(
        self,
        task: str,
        date: Optional[str],
        time: Optional[str],
    ) -> str:
        """
        step == 'saved' 일 때 사용자에게 보여줄 안내 멘트 구성.

        - 시간 정보가 없거나 "00:00"처럼 기본값으로 보이는 경우에는
          시간 부분은 생략하고 날짜까지만 보여준다.
        """
        # "00:00" 류는 없는 시간 취급
        if not time or time.startswith("00:00"):
            time = None

        if date and time:
            return f"알겠어요. '{task}'를 {date} {time}까지 해야 할 일로 등록해 둘게요."
        if date:
            return f"알겠어요. '{task}'를 {date}까지 해야 할 일로 등록해 둘게요."
        return f"알겠어요. '{task}'를 할일로 등록해 둘게요."

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
