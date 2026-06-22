"""Plain-assert tests for parse.py due-date extraction. Run: python test_parse.py"""
from parse import due_date


def check(bank, text, expected):
    got = due_date(bank, text)
    assert got == expected, f"{bank}: got {got!r} expected {expected!r}"


def test_due_date_per_bank():
    # maybank: two `dd MON yy` dates after the address; due = 2nd
    check("maybank", "NO 32 JALAN PS 5/6\n71450 SEREMBAN 28 APR 26 18 MAY 26", "2026-05-18")
    # cimb: two `dd MON yyyy` dates on the values line; due = 2nd
    check("cimb", "Statement / Invoice Date Payment Due Date\n19 APR 2026 11 MAY 2026", "2026-05-11")
    # sc: inline after the bilingual label
    check("sc", "Payment Due Date / Tarikh Akhir : 09 Jul 2026", "2026-07-09")
    # alliance: inline `dd/mm/yy` after the Malay label
    check("alliance", "Makluman Pembayaran Payment Due Date\nTarikh Bayaran Perlu Dibuat 06/05/26", "2026-05-06")
    # hsbc: inline, full month name, no spaces in label
    check("hsbc", "StatementDate 02 Apr 2026 PaymentDueDate 22 April 2026", "2026-04-22")
    # rhb: value on the next line after the label
    check("rhb", "Payment Due Date\n12/05/2026", "2026-05-12")


def test_due_date_null_when_absent():
    assert due_date("maybank", "no dates here at all") is None
    assert due_date("sc", "Payment Due Date / Tarikh Akhir :") is None
    assert due_date("unknownbank", "Payment Due Date 01 Jan 2026") is None


if __name__ == "__main__":
    test_due_date_per_bank()
    test_due_date_null_when_absent()
    print("OK")
