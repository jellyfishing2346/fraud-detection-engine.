"""
Week 5: Alert escalation job.
Finds open alerts past SLA deadline and marks them escalated.

Usage:
    cd backend
    python3.12 scripts/escalate_alerts.py
"""

import os
import sys
from datetime import UTC, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.models import FraudAlert, get_engine
from dotenv import load_dotenv
from sqlalchemy.orm import Session

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))


def escalate_overdue_alerts():
    engine = get_engine()
    now = datetime.now(UTC)

    with Session(engine) as db:
        overdue = (
            db.query(FraudAlert)
            .filter(
                FraudAlert.state == "open",
                FraudAlert.escalated == False,  # noqa: E712
                FraudAlert.sla_deadline < now,
            )
            .all()
        )

        if not overdue:
            print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] No overdue alerts.")
            return 0

        for alert in overdue:
            alert.escalated = True
            print(f"  Escalating alert {alert.id}")

        db.commit()
        print(f"Escalated {len(overdue)} alert(s).")
        return len(overdue)


if __name__ == "__main__":
    escalate_overdue_alerts()
