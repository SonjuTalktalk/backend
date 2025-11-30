# src/routers/item.py
from fastapi import HTTPException, APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import and_
from src.auth.dependencies import get_current_user
from src.db.database import get_db
from src.models.users import User
from src.models.ai import AiProfile
from src.models.item_buy_list import ItemBuyList
from src.models.item_list import ItemList

router = APIRouter(prefix="/item", tags=["상점"])

class AddPurchaseInfo(BaseModel):
    item_number: int 

class ResponseAddPurchase(BaseModel):
    item_number: int
    message: str

class EquipItem(BaseModel):
    item_number: int 

class ResponseEquipStatus(BaseModel):
    item_number: int
    message: str

@router.post("/buy", response_model=ResponseAddPurchase)
def buy_item(
    body: AddPurchaseInfo,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    응답 메시지: "아이템 구매 정보가 등록되었습니다."
    
    """
    isBought = db.query(ItemBuyList).filter(
        and_(
            ItemBuyList.cognito_id == current_user.cognito_id,
            ItemBuyList.item_number == body.item_number 
        )
    ).first()

    
    # 1. 기존에 작성한 메모를 수정한거라면 원래 튜플에서 memo_text만 수정
    if isBought:
        raise HTTPException(
            status_code=409, 
            detail="이미 구매한 아이템입니다."
        )
    #예외 처리#
        
    target_item = db.query(ItemList).filter(ItemList.item_number == body.item_number).first()
    if not target_item:
        raise HTTPException(
            status_code=404, 
            detail="존재하지 않는 아이템입니다."
        )
    
    profile = db.query(User).filter(User.cognito_id == current_user.cognito_id).first()
    if profile.point < target_item.item_price:
        raise HTTPException(
            status_code=400, 
            detail="포인트가 모자랍니다."
        )


    new_purchase = ItemBuyList(
        cognito_id=current_user.cognito_id,
        item_number=body.item_number
    )

    db.add(new_purchase)
    db.commit()
    db.refresh(new_purchase)

    profile.point = profile.point - target_item.item_price
    db.commit()
    db.refresh(profile)
    return ResponseAddPurchase(
        item_number=new_purchase.item_number,
        message="아이템 구매 정보가 등록되었습니다."
    )
   


@router.post("/equip", response_model=ResponseEquipStatus)
def buy_item(
    body: EquipItem,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    응답 메시지: "(아이템 이름) 아이템이 장착되었습니다."
    
    """
    isBought = db.query(ItemBuyList).filter(
        and_(
            ItemBuyList.cognito_id == current_user.cognito_id,
            ItemBuyList.item_number == body.item_number 
        )
    ).first()

    
    # 1. 기존에 작성한 메모를 수정한거라면 원래 튜플에서 memo_text만 수정
    if not isBought:
        raise HTTPException(
            status_code=403, 
            detail="구매하지 않은 아이템입니다."
        )
    #예외 처리#
    
    ai_profile = db.query(AiProfile).filter(AiProfile.owner_cognito_id == current_user.cognito_id).first()
    ai_profile.equipped_item = body.item_number
    db.commit()
    db.refresh(ai_profile)

    equipped = db.query(ItemList).filter(ItemList.item_number == ai_profile.equipped_item).first()
    return ResponseAddPurchase(
        item_number=ai_profile.equipped_item,
        message=f"{equipped.item_name} 아이템이 장착되었습니다."
    )