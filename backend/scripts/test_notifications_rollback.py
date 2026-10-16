from uuid import uuid4

from sqlalchemy.orm import Session

from app.db.database import engine
from app.models.user import User
from app.models.employee import Employee
from app.models.notification import Notification, NotificationPreference
from app.routers import notifications as notification_router
from app.schemas.notification import (
    NotificationBroadcastRequest,
    NotificationPreferenceUpdate,
)
from app.services.notification_service import create_in_app_notification


connection = engine.connect()
outer_transaction = connection.begin()
db = Session(bind=connection, join_transaction_mode="create_savepoint")

try:
    admin = (
        db.query(User)
        .filter(User.role == "Admin", User.is_active.is_(True))
        .first()
    )
    if admin is None:
        raise RuntimeError("An active Admin user is required for this test.")

    employee_user_pair = (
        db.query(Employee, User)
        .join(User, User.id == Employee.user_id)
        .filter(
            Employee.is_active.is_(True),
            User.is_active.is_(True),
        )
        .first()
    )
    if employee_user_pair is None:
        raise RuntimeError("No active employee linked to an active user was found.")

    employee, recipient = employee_user_pair
    if not employee.department or not employee.department.strip():
        raise RuntimeError("The selected employee has no department.")

    tag = f"ROLLBACK_TEST_{uuid4().hex[:10]}"
    print("===== NOTIFICATION ROLLBACK TEST =====")
    print(f"Test recipient: user ID {recipient.id}")
    print(f"Test department: {employee.department}")

    # Temporarily disable the selected employee's announcement preference.
    # This change is made inside the outer transaction and will be rolled back.
    preference = (
        db.query(NotificationPreference)
        .filter(
            NotificationPreference.user_id == recipient.id,
            NotificationPreference.category == "announcement",
        )
        .first()
    )

    if preference is None:
        preference = NotificationPreference(
            user_id=recipient.id,
            category="announcement",
            enabled=False,
        )
        db.add(preference)
    else:
        preference.enabled = False

    db.flush()

    # Test the preference update/read functions for the Admin account.
    updated = notification_router.update_notification_preference(
        payload=NotificationPreferenceUpdate(
            category="announcement",
            enabled=False,
        ),
        db=db,
        current_user=admin,
    )
    assert updated["enabled"] is False

    preferences = notification_router.get_notification_preferences(
        db=db,
        current_user=admin,
    )
    admin_announcement_preference = next(
        item for item in preferences if item["category"] == "announcement"
    )
    assert admin_announcement_preference["enabled"] is False

    suppressed = create_in_app_notification(
        db=db,
        recipient_user_id=admin.id,
        title=f"{tag}_suppressed",
        message="Temporary preference test",
        category="announcement",
    )
    assert suppressed is None
    print("PASS: Disabled preference suppresses notification creation.")

    notification_router.update_notification_preference(
        payload=NotificationPreferenceUpdate(
            category="announcement",
            enabled=True,
        ),
        db=db,
        current_user=admin,
    )

    delivered = create_in_app_notification(
        db=db,
        recipient_user_id=admin.id,
        title=f"{tag}_enabled",
        message="Temporary enabled-preference test",
        category="announcement",
    )
    assert delivered is not None
    db.flush()
    print("PASS: Enabled preference permits notification creation.")

    # Test a department-specific broadcast using a real active department.
    department_title = f"{tag}_department"
    department_result = notification_router.broadcast_notification(
        payload=NotificationBroadcastRequest(
            title=department_title,
            message="Temporary rollback-only department broadcast test",
            category="announcement",
            department=employee.department,
        ),
        db=db,
        current_user=admin,
    )

    assert department_result["eligible_users"] >= 1
    assert department_result["suppressed_by_preferences"] >= 1

    recipient_department_count = (
        db.query(Notification)
        .filter(
            Notification.recipient_user_id == recipient.id,
            Notification.title == department_title,
        )
        .count()
    )
    assert recipient_department_count == 0
    print("PASS: Department broadcast respects disabled preference.")

    # Test a company-wide broadcast; all effects remain in this transaction.
    company_title = f"{tag}_company"
    company_result = notification_router.broadcast_notification(
        payload=NotificationBroadcastRequest(
            title=company_title,
            message="Temporary rollback-only company broadcast test",
            category="announcement",
            department=None,
        ),
        db=db,
        current_user=admin,
    )

    assert company_result["eligible_users"] >= 1
    assert company_result["suppressed_by_preferences"] >= 1

    recipient_company_count = (
        db.query(Notification)
        .filter(
            Notification.recipient_user_id == recipient.id,
            Notification.title == company_title,
        )
        .count()
    )
    assert recipient_company_count == 0
    print("PASS: Company-wide broadcast respects disabled preference.")

    print("\nDepartment result:", department_result)
    print("Company result:", company_result)
    print("\nPASS: Preference and broadcast checks completed.")

finally:
    db.rollback()
    outer_transaction.rollback()
    db.close()
    connection.close()
    print("ROLLBACK: Temporary notification, preference, and audit changes rolled back.")