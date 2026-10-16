from sqlalchemy import inspect, text

from app.db.database import engine


COLUMN_DDL = {
    "compensation_structure_id":
        "ALTER TABLE payroll ADD COLUMN compensation_structure_id INTEGER NULL",
    "compensation_deductions":
        "ALTER TABLE payroll ADD COLUMN compensation_deductions "
        "DECIMAL(12,2) NOT NULL DEFAULT 0.00",
    "compensation_breakdown":
        "ALTER TABLE payroll ADD COLUMN compensation_breakdown JSON NULL",
}


def main():
    inspector = inspect(engine)

    if not inspector.has_table("payroll"):
        raise RuntimeError("The payroll table does not exist.")

    existing = {
        column["name"]
        for column in inspector.get_columns("payroll")
    }

    with engine.begin() as connection:
        for column_name, ddl in COLUMN_DDL.items():
            if column_name not in existing:
                connection.execute(text(ddl))
                print(f"ADDED: {column_name}")
            else:
                print(f"EXISTS: {column_name}")

    updated = {
        column["name"]
        for column in inspect(engine).get_columns("payroll")
    }

    missing = set(COLUMN_DDL) - updated
    if missing:
        raise RuntimeError(
            f"Migration verification failed: {sorted(missing)}"
        )

    print("PASS: All compensation snapshot columns verified.")


if __name__ == "__main__":
    main()
