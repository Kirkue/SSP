"""
SessionVouchers (docs/remaining-work.md 2.2): the Vouchers a customer checked in the balance
popup, remembered for their session and offered at payment with a tap. Never applied
automatically, and gone when the session ends.
"""
import os
from datetime import datetime

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from managers.session_vouchers import CheckedVoucher, SessionVouchers  # noqa: E402


class TestSessionVouchers:
    def test_starts_empty(self):
        v = SessionVouchers()
        assert v.items() == [] and len(v) == 0

    def test_remembers_what_the_check_showed(self):
        v = SessionVouchers()
        expires = datetime(2026, 10, 31)
        v.add("ABCD1234", 7, expires)
        assert v.items() == [CheckedVoucher("ABCD1234", 7, expires)]

    def test_keeps_the_order_first_checked(self):
        v = SessionVouchers()
        v.add("AAAA1111", 5)
        v.add("BBBB2222", 9)
        assert [c.code for c in v.items()] == ["AAAA1111", "BBBB2222"]

    def test_checking_again_updates_in_place_without_moving_it(self):
        v = SessionVouchers()
        v.add("AAAA1111", 10)
        v.add("BBBB2222", 9)
        v.add("AAAA1111", 6)
        assert [(c.code, c.remaining) for c in v.items()] == [("AAAA1111", 6), ("BBBB2222", 9)]

    def test_ignores_what_cannot_be_used(self):
        v = SessionVouchers()
        v.add(None, 7)          # a code that didn't normalise
        v.add("", 7)
        v.add("ABCD1234", 0)    # nothing left on it
        assert v.items() == []

    def test_remove_and_clear(self):
        v = SessionVouchers()
        v.add("AAAA1111", 5)
        v.add("BBBB2222", 9)
        v.remove("AAAA1111")
        v.remove("NOPE0000")    # unknown: harmless
        assert [c.code for c in v.items()] == ["BBBB2222"]
        v.clear()
        assert len(v) == 0

    def test_items_is_a_copy(self):
        v = SessionVouchers()
        v.add("AAAA1111", 5)
        v.items().clear()
        assert len(v) == 1

    def test_the_label_shows_only_the_last_four_characters(self):
        label = CheckedVoucher("ABCD1234", 7).label
        assert label.endswith("1234") and "ABCD" not in label
