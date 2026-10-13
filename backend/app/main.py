
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

# Database
from app.db.database import Base, engine

# Models: import before create_all so their tables are registered
from app.models.user import User
from app.models.employee import Employee
from app.models.attendance import Attendance
from app.models.leave import LeaveRequest
from app.models.leave_balance import LeaveBalance
from app.models.payroll import Payroll

# API routers
from app.routers.auth import router as auth_router
from app.routers.employees import router as employee_router
from app.routers.attendance import router as attendance_router
from app.routers.leaves import router as leave_router
from app.routers.payroll import router as payroll_router
from app.routers.salary_slips import router as salary_slips_router


app = FastAPI(
    title="HRMS API",
    description="Human Resource Management System",
    version="1.0.0",
)


# Allow the local React frontend to call the FastAPI backend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Initial development setup.
# Use Alembic migrations for production schema management.
Base.metadata.create_all(bind=engine)


# Register API routers
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
