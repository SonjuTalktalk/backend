# sonju_ai/core/health_service.py
"""
건강 관련 AI 서비스
- 건강 메모 분석 (4단계 상태 판정)
- 처방전/약봉투 OCR 처리
- STT (음성 메모)
"""

import json
import re
import logging
from typing import Dict, Optional, List
from datetime import datetime

from sonju_ai.utils.openai_client import OpenAIClient
from sonju_ai.config.prompts import get_prompt

logger = logging.getLogger(__name__)


class HealthService:
    """건강 관련 AI 서비스"""
    
    def __init__(self):
        """건강 서비스 초기화"""
        self.client = OpenAIClient()
        logger.info("건강 서비스 초기화 완료")
    
    def analyze_health_memo(
        self, 
        memo_text: str, 
        previous_memos: Optional[str] = None
    ) -> Dict:
        """
        건강 메모를 분석하여 상태 레벨 판정
        
        Args:
            memo_text: 분석할 메모 내용
            previous_memos: 같은 날짜의 이전 메모 (선택사항)
        
        Returns:
            {
                "status": "healthy" | "normal" | "warning" | "danger",
                "timestamp": "2025-11-03T12:00:00"
            }
        """
        try:
            # 입력 검증
            if not memo_text or not memo_text.strip():
                logger.warning("빈 메모 텍스트")
                return {
                    "status": "normal",
                    "timestamp": datetime.now().isoformat(),
                    "error": "빈 메모"
                }
            
            # 이전 메모가 있으면 함께 분석
            full_text = memo_text
            if previous_memos:
                full_text = f"[이전 메모]\n{previous_memos}\n\n[새 메모]\n{memo_text}"
            
            # 프롬프트 가져오기
            system_prompt = get_prompt("health_analysis")
            
            # GPT 호출
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": full_text}
            ]
            
            response = self.client.chat_completion(
                messages=messages,
                response_format={"type": "json_object"}
            )
            
            # JSON 파싱 (강화된 에러 핸들링)
            result = self._parse_json_response(response)
            
            # status 검증
            valid_statuses = ["healthy", "normal", "warning", "danger"]
            if result.get("status") not in valid_statuses:
                logger.warning(f"잘못된 status 값: {result.get('status')}, 기본값 사용")
                result["status"] = "normal"
            
            # 타임스탬프 추가
            result["timestamp"] = datetime.now().isoformat()
            
            logger.info(f"건강 메모 분석 완료: {result['status']}")
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON 파싱 실패: {e}")
            return {
                "status": "normal",
                "timestamp": datetime.now().isoformat(),
                "error": "JSON 파싱 실패"
            }
        except TimeoutError as e:
            logger.error(f"GPT API 타임아웃: {e}")
            return {
                "status": "normal",
                "timestamp": datetime.now().isoformat(),
                "error": "분석 시간 초과"
            }
        except Exception as e:
            logger.error(f"건강 메모 분석 실패: {e}")
            return {
                "status": "normal",
                "timestamp": datetime.now().isoformat(),
                "error": f"분석 실패: {str(e)}"
            }
    
    def extract_prescription_info(self, image_bytes: bytes) -> Dict:
        """
        처방전/약봉투 이미지에서 정보 추출
        
        Args:
            image_path: 이미지 파일 경로 또는 URL
        
        Returns:
            {
                "medicines": [
                    {
                        "name": "타이레놀",
                        "prescription_date": "2025-11-03",
                        "duration_days": 7,
                        "frequency": "1일 3회",
                        "times": ["아침", "점심", "저녁"]
                    }
                ],
                "raw_text": "OCR 원본 텍스트" (선택사항)
            }
        """
        try:
            """
            # 입력 검증
            if not image_path or not image_path.strip():
                logger.warning("빈 이미지 경로")
                return {
                    "medicines": [],
                    "error": "이미지 경로가 없습니다"
                }
            """
            # 프롬프트 가져오기
            system_prompt = get_prompt("prescription_ocr")
            
            # Vision API 호출
            response = self.client.vision_completion(
                prompt=system_prompt,
                image_bytes=image_bytes,
                response_format={"type": "json_object"}
            )
            
            # JSON 파싱
            result = self._parse_json_response(response)
            
            # medicines 필드 검증
            if "medicines" not in result:
                logger.warning("medicines 필드 없음, 빈 배열 추가")
                result["medicines"] = []
            
            # 각 약품 정보 검증
            validated_medicines = []
            for med in result.get("medicines", []):
                if isinstance(med, dict) and "name" in med:
                    validated_medicines.append(med)
            
            result["medicines"] = validated_medicines
            
            logger.info(f"처방전 인식 완료: {len(result['medicines'])}개 약품")
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON 파싱 실패: {e}")
            return {
                "medicines": [],
                "raw_text": "",
                "error": "JSON 파싱 실패"
            }
        except Exception as e:
            logger.error(f"처방전 인식 실패: {e}")
            return {
                "medicines": [],
                "raw_text": "",
                "error": f"인식 실패: {str(e)}"
            }
    
    def transcribe_audio(self, audio_path: str) -> str:
        """
        음성을 텍스트로 변환 (STT)
        
        Args:
            audio_path: 음성 파일 경로
        
        Returns:
            변환된 텍스트
        """
        try:
            # 입력 검증
            if not audio_path or not audio_path.strip():
                logger.warning("빈 오디오 경로")
                return ""
            
            text = self.client.transcribe_audio(audio_path)
            logger.info(f"음성 변환 완료: {len(text)}자")
            return text
            
        except Exception as e:
            logger.error(f"음성 변환 실패: {e}")
            return ""
    
    def analyze_voice_memo(self, audio_path: str) -> Dict:
        """
        음성 메모를 텍스트로 변환 후 건강 상태 분석
        
        Args:
            audio_path: 음성 파일 경로
        
        Returns:
            {
                "text": "변환된 텍스트",
                "status": "healthy" | "normal" | "warning" | "danger",
                "timestamp": "2025-11-03T12:00:00"
            }
        """
        try:
            # STT
            text = self.transcribe_audio(audio_path)
            
            if not text:
                return {
                    "text": "",
                    "status": "normal",
                    "timestamp": datetime.now().isoformat(),
                    "error": "음성 변환 실패"
                }
            
            # 건강 분석
            analysis = self.analyze_health_memo(text)
            analysis["text"] = text
            
            return analysis
            
        except Exception as e:
            logger.error(f"음성 메모 분석 실패: {e}")
            return {
                "text": "",
                "status": "normal",
                "timestamp": datetime.now().isoformat(),
                "error": str(e)
            }
    
    def get_status_color(self, status: str) -> str:
        """
        상태 코드를 색상 코드로 변환
        
        Args:
            status: "healthy" | "normal" | "warning" | "danger"
        
        Returns:
            색상 코드: "green" | "blue" | "yellow" | "red"
        """
        color_map = {
            "healthy": "green",
            "normal": "blue",
            "warning": "yellow",
            "danger": "red"
        }
        return color_map.get(status, "blue")
    
    def format_health_analysis(self, analysis: Dict) -> str:
        """
        분석 결과를 사용자 친화적인 텍스트로 변환
        
        Args:
            analysis: analyze_health_memo() 결과
        
        Returns:
            포맷된 문자열
        """
        status_text = {
            "healthy": "건강한 상태",
            "normal": "보통 상태",
            "warning": "주의 필요",
            "danger": "위험 상태"
        }
        
        status = analysis.get("status", "normal")
        text = status_text.get(status, "알 수 없음")
        
        return f"오늘의 건강 상태: {text}"
    
    def _parse_json_response(self, response: str) -> Dict:
        """
        GPT 응답에서 JSON 추출 및 파싱
        
        Args:
            response: GPT 응답 문자열
        
        Returns:
            파싱된 딕셔너리
        """
        try:
            # 직접 파싱 시도
            return json.loads(response)
        except json.JSONDecodeError:
            # JSON 추출 시도
            json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
            json_match = re.search(json_pattern, response, re.DOTALL)
            
            if json_match:
                json_str = json_match.group().strip()
                return json.loads(json_str)
            
            # 파싱 실패
            logger.error(f"JSON 파싱 실패: {response[:100]}")
            raise json.JSONDecodeError("JSON 형식 아님", response, 0)


# 간단한 테스트 실행
if __name__ == "__main__":
    try:
        print("=" * 50)
        print("손주톡톡 건강 서비스 테스트")
        print("=" * 50)
        
        health = HealthService()
        
        # 1. 건강 메모 분석
        print("\n[1] 건강 메모 분석")
        result1 = health.analyze_health_memo("오늘 머리가 좀 아파요")
        print(f"결과: {result1}")
        print(f"색상: {health.get_status_color(result1['status'])}")
        
        # 2. 건강한 메모
        print("\n[2] 건강한 메모")
        result2 = health.analyze_health_memo("오늘 산책하고 기분이 좋아요")
        print(f"결과: {result2}")
        
        # 3. 포맷팅
        print("\n[3] 포맷팅")
        formatted = health.format_health_analysis(result2)
        print(f"포맷: {formatted}")
        
        print("\n" + "=" * 50)
        print("테스트 완료!")
        print("=" * 50)
        
    except Exception as e:
        print(f"테스트 중 오류: {e}")