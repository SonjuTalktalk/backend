# src/services/cognito_admin.py
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from src.config.settings import settings

_cognito = boto3.client("cognito-idp", region_name=settings.cognito_region)

def admin_delete_user_by_sub(sub: str) -> None:
    """
    Cognito UserPool에서 유저 삭제.
    - AWS 문서상 Username에는 일반적으로 username(또는 alias)이지만,
      로컬 유저면 sub 값을 넣어도 동작 가능.
    """
    _cognito.admin_delete_user(
        UserPoolId=settings.cognito_user_pool_id,
        Username=sub,
    )
