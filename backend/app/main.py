
from fastapi import FastAPI
from sqlalchemy import text

from app.db.database import Base, engine
from app.models.user import User
from app.routers.auth import router as auth_router
from app.models.employee import Employee
from app.routers.employees import router as employee_router
from app.models.attendance import Attendance
from app.routers.attendance import router as attendance_router
from app.models.leave import LeaveRequest
from app.models.leave_balance import LeaveBalance
from app.routers.leaves import router as leave_router
from app.models.payroll import Payroll
from app.routers.payroll import router as payroll_router
from app.routers.salary_slips import router as salary_slips_router

app = FastAPI(
    title="HRMS API",
    description="Human Resource Management System",
    version="1.0.0",
)

# Create database tables for initial development
Base.metadata.create_all(bind=engine)

# Register authentication routes
app.include_router(auth_router)
app.include_router(employee_router)
app.include_router(attendance_router)
app.include_router(leave_router)
app.include_router(payroll_router)
app.include_router(salary_slips_router)


@app.get("/")
def home():
    return {
        "message": "HRMS API is running",
        "status": "success",
    }


@app.get("/health")
def health():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        return {
            "status": "healthy",
            "database": "connected",
        }
    except Exception:
        return {
            "status": "unhealthy",
            "database": "disconnected",
        }
