# managers/session_vouchers.py
#
# Vouchers the customer has checked in the balance popup, remembered for their session
# (docs/remaining-work.md 2.2). The payment screen lists them with their balance and a
# tap-to-apply button, so they needn't scan or type a code again; they are never applied
# automatically. Cleared with the session's files: on any timeout that clears them, and
# whenever the kiosk goes back to idle.
#
# Only the canonical code and what the check showed are kept (the code is already in the
# customer's hands; nothing here is persisted). The balance is what the check saw: applying
# it still looks the Voucher up again at payment.

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional


@dataclass(frozen=True)
class CheckedVoucher:
    code: str                       # canonical code, as VoucherManager takes it
    remaining: int                  # pesos left when it was checked
    expires_at: Optional[datetime] = None

    @property
    def label(self) -> str:
        # Only the last 4 characters, like AppliedVoucher: the full code isn't left on screen.
        return f"Voucher \u2022\u2022\u2022\u2022-{self.code[-4:]}"


class SessionVouchers:
    def __init__(self):
        self._by_code: Dict[str, CheckedVoucher] = {}

    def add(self, code: Optional[str], remaining: int, expires_at: Optional[datetime] = None):
        """Remember a checked Voucher. Checking one again refreshes its balance."""
        if not code or remaining <= 0:
            return
        self._by_code[code] = CheckedVoucher(code, int(remaining), expires_at)

    def items(self) -> List[CheckedVoucher]:
        """In the order first checked."""
        return list(self._by_code.values())

    def remove(self, code: str):
        self._by_code.pop(code, None)

    def clear(self):
        self._by_code.clear()

    def __len__(self):
        return len(self._by_code)
