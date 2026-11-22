from __future__ import annotations

import unittest

from sqlmodel import Session, SQLModel, create_engine, select

from app.models.models import CreditLog, User
from app.services.credits import InsufficientCredits, charge


class AtomicChargeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}
        )
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.user = User(email="charge@example.com", credits=100)
        self.session.add(self.user)
        self.session.commit()
        self.session.refresh(self.user)

    def tearDown(self) -> None:
        self.session.close()

    def test_charge_deducts_and_writes_log(self) -> None:
        charge(self.session, self.user, 30, "test")
        self.session.commit()
        self.session.refresh(self.user)
        self.assertEqual(self.user.credits, 70)
        log = self.session.exec(
            select(CreditLog).where(CreditLog.user_id == self.user.id)
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.delta, -30)
        self.assertEqual(log.balance_after, 70)

    def test_charge_rejects_when_insufficient(self) -> None:
        with self.assertRaises(InsufficientCredits):
            charge(self.session, self.user, 200, "test")
        self.session.rollback()
        self.session.refresh(self.user)
        self.assertEqual(self.user.credits, 100)


if __name__ == "__main__":
    unittest.main()
