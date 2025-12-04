# src/routers/background.py
from fastapi import HTTPException, APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import and_
from src.auth.dependencies import get_current_user
from src.db.database import get_db
from src.models.users import User
from src.models.background_buy_list import BackgroundBuyList
from src.models.background_list import BackgroundList

router = APIRouter(prefix="/background", tags=["배경"])

class AddPurchaseInfo(BaseModel):
    background_number: int 

class ResponseAddPurchase(BaseModel):
    background_number: int
    message: str

class EquipBackground(BaseModel):
    background_number: int 

class ResponseEquipStatus(BaseModel):
    background_number: int
    message: str

class ResponseUnequip(BaseModel):
    message: str

@router.post("/buy", response_model=ResponseAddPurchase)
def buy_background(
    body: AddPurchaseInfo,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    응답 메시지: "배경 구매 정보가 등록되었습니다."
    
    """
    isBought = db.query(BackgroundBuyList).filter(
        and_(
            BackgroundBuyList.cognito_id == current_user.cognito_id,
            BackgroundBuyList.background_number == body.background_number 
        )
    ).first()

    if isBought:
        raise HTTPException(
            status_code=409, 
            detail="이미 구매한 배경입니다."
        )
    #예외 처리#
        
    target_background = db.query(BackgroundList).filter(BackgroundList.background_number == body.background_number).first()
    if not target_background:
        raise HTTPException(
            status_code=404, 
            detail="존재하지 않는 배경입니다."
        )
    
    profile = db.query(User).filter(User.cognito_id == current_user.cognito_id).first()
    if profile.point < target_background.background_price:
        raise HTTPException(
            status_code=400, 
            detail="포인트가 모자랍니다."
        )


    new_purchase = BackgroundBuyList(
        cognito_id=current_user.cognito_id,
        background_number=body.background_number
    )

    db.add(new_purchase)
    db.commit()
    db.refresh(new_purchase)

    profile.point -= target_background.background_price
    db.commit()
    db.refresh(profile)
    return ResponseAddPurchase(
        background_number=new_purchase.background_number,
        message="배경 구매 정보가 등록되었습니다."
    )
   


@router.patch("/equip", response_model=ResponseEquipStatus)
def equip_background(
    body: EquipBackground,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    응답 메시지: "(배경 이름) 배경이 장착되었습니다."
    
    """
    isBought = db.query(BackgroundBuyList).filter(
        and_(
            BackgroundBuyList.cognito_id == current_user.cognito_id,
            BackgroundBuyList.background_number == body.background_number 
        )
    ).first()

    
    if not isBought:
        raise HTTPException(
            status_code=403, 
            detail="구매하지 않은 배경입니다."
        )
    #예외 처리#
    
    current_user.equipped_background = body.background_number
    db.commit()
    db.refresh(current_user)

    equipped = db.query(BackgroundList).filter(BackgroundList.background_number == current_user.equipped_background).first()
    return ResponseAddPurchase(
        background_number=current_user.equipped_background,
        message=f"{equipped.background_name} 배경이 장착되었습니다."
    )

@router.patch("/unequip", response_model=ResponseUnequip)
def unequip_background(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    응답 메시지: "배경이 장착 해제되었습니다."
    
    """
    
    current_user.equipped_background = None
    db.commit()
    db.refresh(current_user)

    return ResponseUnequip(
        message="배경이 장착 해제되었습니다."
    )