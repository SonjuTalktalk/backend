# sonju_ai/utils/openai_client.py
"""
OpenAI API 클라이언트
손주톡톡 AI 모듈의 OpenAI API 통신 담당 (Chat + Vision + STT + TTS)
"""
import os
import base64
import logging
from typing import Optional, List, Dict
from datetime import datetime
from openai import OpenAI, APIConnectionError, AuthenticationError, RateLimitError
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

# 로깅 설정
# 개발 단계: logging.INFO
# 서비스 운영 시: logging.WARNING 권장
logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

class OpenAIClient:
    """손주톡톡용 OpenAI API 클라이언트 (Chat + Vision + STT + TTS)"""
    
    DEFAULT_MODEL = "gpt-4o-mini"
    
    def __init__(self, model: Optional[str] = None):
        """OpenAI 클라이언트 초기화"""
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")
        
        self.client = OpenAI(api_key=api_key)
        self.model = model or self.DEFAULT_MODEL
        logger.info(f"OpenAI 클라이언트 초기화 완료 (모델: {self.model})")
    
    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 300,
        temperature: float = 0.7,
        response_format: Optional[Dict] = None
    ) -> str:
        """
        채팅 완성 API 호출
        
        Args:
            messages: [{"role": "user", "content": "..."}]
            max_tokens: 최대 토큰 수
            temperature: 응답 창의성 (0.0~1.0)
            response_format: 응답 형식 (예: {"type": "json_object"})
        """
        try:
            kwargs = {
                "model": self.model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature
            }
            
            if response_format:
                kwargs["response_format"] = response_format
            
            response = self.client.chat.completions.create(**kwargs)
            
            result = response.choices[0].message.content.strip()
            logger.debug(f"API 호출 성공 (토큰: {response.usage.total_tokens})")
            return result
            
        except AuthenticationError:
            logger.error("OpenAI API 키 인증 오류")
            return "API 키가 올바르지 않습니다. 설정을 확인해주세요."
        except RateLimitError:
            logger.warning("API 요청 한도 초과")
            return "요청이 너무 많습니다. 잠시 후 다시 시도해주세요."
        except APIConnectionError:
            logger.error("OpenAI API 연결 오류")
            return "인터넷 연결을 확인해주세요."
        except Exception as e:
            logger.exception(f"OpenAI API 처리 중 예상치 못한 오류: {e}")
            return "죄송해요, 잠시 생각이 안 나네요. 다시 한 번 말씀해 주시겠어요?"
    
    def simple_chat(self, user_message: str, system_prompt: Optional[str] = None) -> str:
        """간단한 1회 채팅"""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_message})
        return self.chat_completion(messages)
    
    def test_connection(self) -> bool:
        """API 연결 테스트"""
        try:
            response = self.simple_chat("테스트", "OK라고 답해주세요.")
            success = bool(response) and "오류" not in response
            logger.info(f"연결 테스트: {'성공' if success else '실패'}")
            return success
        except Exception as e:
            logger.error(f"연결 테스트 중 오류: {e}")
            return False
    
    def vision_completion(
        self,
        prompt: str,
        image_bytes: bytes,
        image_type: str = "jpeg", # 기본값 jpeg, png도 가능
        max_tokens: int = 2000,
        temperature: float = 0.5,
        response_format: Optional[Dict] = None
    ) -> str:
        """
        Vision API 호출 (이미지 분석)
        
        Args:
            prompt: 분석 요청 프롬프트
            image_path: 이미지 URL 또는 로컬 파일 경로
            max_tokens: 최대 토큰 수
            temperature: 응답 창의성
            response_format: 응답 형식 (예: {"type": "json_object"})
        
        Returns:
            str: 분석 결과
        """
        try:
            # MIME 타입 결정
            mime_type = "image/jpeg" if image_type.lower() != "png" else "image/png"
            
            # base64 인코딩
            b64_string = base64.b64encode(image_bytes).decode("utf-8")
            image_content = {
                "type": "image_url",
                "image_url": {"url": f"data:{mime_type};base64,{b64_string}"}
            }


            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        image_content
                    ]
                }
            ]
            
            kwargs = {
                "model": self.model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature
            }
            
            if response_format:
                kwargs["response_format"] = response_format
            
            response = self.client.chat.completions.create(**kwargs)
            result = response.choices[0].message.content.strip()
            logger.debug(f"Vision API 호출 성공")
            return result
            
        except FileNotFoundError:
            logger.error(f"이미지 파일을 찾을 수 없습니다: {image_path}")
            return "이미지 파일을 찾을 수 없습니다."
        except AuthenticationError:
            logger.error("OpenAI API 키 인증 오류")
            return "API 키가 올바르지 않습니다. 설정을 확인해주세요."
        except RateLimitError:
            logger.warning("API 요청 한도 초과")
            return "요청이 너무 많습니다. 잠시 후 다시 시도해주세요."
        except APIConnectionError:
            logger.error("OpenAI API 연결 오류")
            return "인터넷 연결을 확인해주세요."
        except Exception as e:
            logger.exception(f"Vision API 처리 중 예상치 못한 오류: {e}")
            return "이미지 분석 중 문제가 발생했습니다."
    
    def transcribe_audio(self, audio_path: str) -> str:
        """
        STT: 음성을 텍스트로 변환
        
        Args:
            audio_path: 오디오 파일 경로
        
        Returns:
            str: 변환된 텍스트
        """
        try:
            with open(audio_path, "rb") as audio_file:
                response = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language="ko"
                )
            
            logger.info(f"STT 변환 성공: {len(response.text)}자")
            return response.text
            
        except FileNotFoundError:
            logger.error(f"오디오 파일을 찾을 수 없습니다: {audio_path}")
            return "오디오 파일을 찾을 수 없습니다."
        except Exception as e:
            logger.exception(f"STT 변환 중 오류: {e}")
            return "음성 변환 중 문제가 발생했습니다."

    
    def text_to_speech(
        self, 
        text: str, 
        voice: str = "alloy",
        output_path: Optional[str] = None
    ) -> Optional[str]:
        """
        TTS: 텍스트를 음성으로 변환
        
        Args:
            text: 변환할 텍스트
            voice: 음성 모델 (alloy, echo, fable, onyx, nova, shimmer)
            output_path: 저장할 파일 경로 (None이면 자동 생성)
        
        Returns:
            str: 저장된 파일 경로 (실패 시 None)
        """
        try:
            # 빈 텍스트 체크
            if not text or not text.strip():
                logger.warning("빈 텍스트로 TTS 요청됨")
                return None
            
            # 출력 경로 자동 생성
            if not output_path:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                os.makedirs("outputs/tts", exist_ok=True)
                output_path = f"outputs/tts/tts_output_{timestamp}.mp3"
            else:
                # 출력 경로의 디렉토리 생성
                os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            
            # TTS API 호출 (스트리밍 방식)
            with self.client.audio.speech.with_streaming_response.create(
                model="tts-1",
                voice=voice,
                input=text,
                response_format="mp3"
            ) as response:
                response.stream_to_file(output_path)
            
            logger.info(f"TTS 변환 성공: {output_path} (음성: {voice})")
            return output_path
            
        except Exception as e:
            logger.exception(f"TTS 변환 중 오류: {e}")
            return None

        
# 파일 실행 테스트
if __name__ == "__main__":
    client = OpenAIClient()
    print(client.simple_chat("안녕!"))