"""Tests for remind_bills.py — selection logic + the state file. Telegram is stubbed;
no test crosses the HTTP boundary."""
import os
import tempfile
from datetime import date

import remind_bills
from remind_bills import bill_key, due_soon, message

TODAY = date(2026, 8, 20)


def _bill(bank, due, bal=100.0, month="2026-08"):
    return {"bank": bank, "statement_month": month, "current_balance": bal,
            "payment_due_date": due, "minimum_payment": None}


def test_window():
    bills = [_bill("cimb", "2026-08-22"),    # 2d  -> in
             _bill("sc", "2026-08-23"),      # 3d  -> in (inclusive)
             _bill("rhb", "2026-08-24")]     # 4d  -> out
    got = [b["bank"] for b in due_soon(bills, TODAY, 3)]
    assert got == ["cimb", "sc"], got


def test_overdue_included_and_sorted_first():
    bills = [_bill("cimb", "2026-08-21"), _bill("hsbc", "2026-08-15")]
    assert [b["bank"] for b in due_soon(bills, TODAY, 3)] == ["hsbc", "cimb"]


def test_nulls_are_skipped_not_defaulted():
    assert due_soon([_bill("maybank", None)], TODAY, 3) == []
    assert due_soon([_bill("maybank", "2026-08-20", bal=None)], TODAY, 3) == []


def test_paid_and_already_sent_are_excluded():
    b = _bill("alliance", "2026-08-21")
    assert due_soon([b], TODAY, 3, paid={bill_key(b)}) == []
    assert due_soon([b], TODAY, 3, sent={bill_key(b)}) == []
    # same bank, different statement month -> different bill, still reminded
    assert due_soon([_bill("alliance", "2026-08-21", month="2026-09")], TODAY, 3,
                    paid={bill_key(b)}) != []


def test_default_template_renders_bank_amount_and_due():
    txt = message(_bill("cimb", "2026-08-22", 1234.5), TODAY)
    assert "<b>Automated Credit Card Payment Reminder</b>" in txt, txt
    assert "Pay CIMB statement amount of RM <code>1,234.50</code>" in txt, txt
    assert "By 2026-08-22 to avoid late charges" in txt, txt


def test_custom_template_gets_every_field():
    txt = message(_bill("sc", "2026-08-18", 20.0), TODAY,
                  "{bank} {amount} {due} {days} {when} {month}")
    assert txt == "SC 20.00 2026-08-18 -2 2d OVERDUE 2026-08", txt
    assert message(_bill("rhb", "2026-08-20", 5.0), TODAY, "{when}") == "today"


def test_unknown_placeholder_names_the_valid_ones():
    try:
        message(_bill("hsbc", "2026-08-21"), TODAY, "{nope}")
        raise AssertionError("expected a failure")
    except RuntimeError as e:
        assert "nope" in str(e) and "amount" in str(e), e


def test_send_keeps_the_telegram_description():
    """A 400 says only "Bad Request"; the reason ("chat not found") is in the body."""
    import io
    import urllib.error
    import urllib.request

    def boom(*a, **k):
        raise urllib.error.HTTPError(
            "u", 400, "Bad Request", {},
            io.BytesIO(b'{"ok":false,"description":"Bad Request: chat not found"}'))

    real_open = urllib.request.urlopen
    urllib.request.urlopen = boom
    os.environ.setdefault("TELEGRAM_BOT_TOKEN", "x")
    os.environ.setdefault("TELEGRAM_CHAT_ID", "y")
    try:
        remind_bills.send("hi")
        raise AssertionError("expected a failure")
    except RuntimeError as e:
        assert "chat not found" in str(e), e
    finally:
        urllib.request.urlopen = real_open


def test_run_sends_one_message_per_bill():
    sent = []
    real, remind_bills.send = remind_bills.send, sent.append
    try:
        with tempfile.TemporaryDirectory() as d:
            state = os.path.join(d, "reminded.json")
            bills = [_bill("hsbc", "2026-08-22"), _bill("cimb", "2026-08-21")]
            assert len(remind_bills.run(bills, set(), state, TODAY)) == 2
            assert len(sent) == 2 and sum("HSBC" in t for t in sent) == 1
            assert remind_bills.load_state(state) == {"hsbc|2026-08", "cimb|2026-08"}
    finally:
        remind_bills.send = real


def test_a_failed_send_does_not_lose_the_ones_already_sent():
    """Recording per bill: bill 1 stays recorded, bill 2 retries next run."""
    sent = []

    def flaky(text):
        if "CIMB" in text:
            raise RuntimeError("telegram 400: nope")
        sent.append(text)

    real, remind_bills.send = remind_bills.send, flaky
    try:
        with tempfile.TemporaryDirectory() as d:
            state = os.path.join(d, "reminded.json")
            bills = [_bill("hsbc", "2026-08-21"), _bill("cimb", "2026-08-22")]
            try:
                remind_bills.run(bills, set(), state, TODAY)
                raise AssertionError("expected a failure")
            except RuntimeError:
                pass
            assert remind_bills.load_state(state) == {"hsbc|2026-08"}, "sent one is recorded"
            assert len(sent) == 1
    finally:
        remind_bills.send = real


def test_run_sends_once_then_records_it():
    """The dedupe that makes an extra tick (or a server restart) a no-op."""
    sent = []
    real, remind_bills.send = remind_bills.send, sent.append
    try:
        with tempfile.TemporaryDirectory() as d:
            state = os.path.join(d, "reminded.json")
            bills, paid = [_bill("hsbc", "2026-08-22")], set()
            assert len(remind_bills.run(bills, paid, state, TODAY)) == 1
            assert len(sent) == 1 and "HSBC" in sent[0]
            # second run, same day or a restart later: nothing new to say
            assert remind_bills.run(bills, paid, state, TODAY) == []
            assert len(sent) == 1
            # dry run never sends and never records
            assert remind_bills.run([_bill("rhb", "2026-08-21")], paid, state, TODAY,
                                    dry=True) != []
            assert len(sent) == 1
            assert remind_bills.load_state(state) == {"hsbc|2026-08"}
    finally:
        remind_bills.send = real


if __name__ == "__main__":
    test_window()
    test_overdue_included_and_sorted_first()
    test_nulls_are_skipped_not_defaulted()
    test_paid_and_already_sent_are_excluded()
    test_default_template_renders_bank_amount_and_due()
    test_custom_template_gets_every_field()
    test_unknown_placeholder_names_the_valid_ones()
    test_run_sends_once_then_records_it()
    test_run_sends_one_message_per_bill()
    test_a_failed_send_does_not_lose_the_ones_already_sent()
    test_send_keeps_the_telegram_description()
    print("OK")
