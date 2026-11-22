from __future__ import annotations

import unittest

from app.services.ratelimit import (
    MAX_FAILURES,
    LoginBlocked,
    check_login_allowed,
    clear_login_failures,
    record_login_failure,
)


class LoginRateLimitTest(unittest.TestCase):
    def setUp(self) -> None:
        self.ip = "127.0.0.1"
        self.email = "ratelimit@example.com"
        clear_login_failures(self.ip, self.email)

    def tearDown(self) -> None:
        clear_login_failures(self.ip, self.email)

    def test_blocks_after_max_failures(self) -> None:
        for _ in range(MAX_FAILURES):
            record_login_failure(self.ip, self.email)
        with self.assertRaises(LoginBlocked):
            check_login_allowed(self.ip, self.email)

    def test_clear_resets_failures(self) -> None:
        for _ in range(MAX_FAILURES):
            record_login_failure(self.ip, self.email)
        clear_login_failures(self.ip, self.email)
        check_login_allowed(self.ip, self.email)


if __name__ == "__main__":
    unittest.main()
