import datetime as dt
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from src.models.notification import Notification

KST = ZoneInfo("Asia/Seoul")


def create_notification(db: Session, owner_cognito_id: str, title: str, text: str) -> Notification:
    now = dt.datetime.now(KST).replace(microsecond=0)

    row = Notification(
        owner_cognito_id=owner_cognito_id,
        title=title,
        text=text,
        noti_date=now.date(),
        noti_time=now.time(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def delete_notifications_older_than_3_days(db: Session) -> int:
    cutoff = (dt.datetime.now(KST) - dt.timedelta(days=3)).replace(microsecond=0)
    cutoff_date = cutoff.date()
    cutoff_time = cutoff.time()

    deleted = (
        db.query(Notification)
        .filter(
            or_(
                Notification.noti_date < cutoff_date,
                and_(Notification.noti_date == cutoff_date, Notification.noti_time < cutoff_time),
            )
        )
        .delete(synchronize_session=False)
    )
    db.commit()
    return deleted
