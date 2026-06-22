#!/usr/bin/env python3
"""Deterministic per-bank credit-card statement parser.
Reads cc-statements/*.pdf -> transactions.csv, reconciliation.csv, summaries.
No LLM. pdfplumber word-geometry + per-bank rules.
"""
import pdfplumber, re, csv, glob, os, sys
from collections import defaultdict

SRC = "cc-statements"
AMT_RE = re.compile(r'^(-?\d{1,3}(?:,\d{3})*\.\d{2})(CR)?$')
CARDNUM_DASH = re.compile(r'\b(\d{4}-\d{4}-\d{4}-\d{4})\b')
CARDNUM_SPACE = re.compile(r'\b(\d{4} \d{4} \d{4} \d{4})\b')
MONTHS = {m: i for i, m in enumerate(
    ['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'], 1)}


def rows_of(page, ytol=3.0):
    words = page.extract_words(keep_blank_chars=False, use_text_flow=False)
    words.sort(key=lambda w: (w['top'], w['x0']))
    out, cur, cy = [], [], None
    for w in words:
        if cy is None or abs(w['top'] - cy) <= ytol:
            cur.append(w)
            cy = w['top'] if cy is None else cy
        else:
            out.append((cy, sorted(cur, key=lambda x: x['x0'])))
            cur, cy = [w], w['top']
    if cur:
        out.append((cy, sorted(cur, key=lambda x: x['x0'])))
    return out


def all_rows(path, ytol=3.0):
    res = []
    with pdfplumber.open(path) as pdf:
        for pno, page in enumerate(pdf.pages, 1):
            for y, toks in rows_of(page, ytol):
                res.append((pno, y, toks))
    return res


def full_text(path):
    out = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            out.append(page.extract_text() or "")
    return "\n".join(out)


def find_amount(texts):
    """Return (amount_float, is_credit, index) of rightmost money token, else (None,None,None)."""
    for i in range(len(texts) - 1, -1, -1):
        m = AMT_RE.match(texts[i])
        if m:
            amt = float(m.group(1).replace(',', ''))
            cr = bool(m.group(2))
            if i + 1 < len(texts) and texts[i + 1].upper() == 'CR':
                cr = True
            return amt, cr, i
    return None, None, None


# trailing junk tokens to strip from descriptions
COUNTRY = {'MY', 'MYS', 'SG', 'SGP', 'USA', 'CA', 'GB', 'HK', 'TH',
           'JP', 'AU', 'NL', 'DE', 'FR', 'CN', 'KR', 'PH', 'VN'}


def clean_desc(tokens):
    toks = list(tokens)
    # drop installment markers and txn-ref noise
    cleaned = []
    skip_ref = False
    for t in toks:
        u = t.upper()
        if u in ('TXN', 'REF:', 'REF', 'INTERNET'):
            if u in ('TXN', 'REF', 'REF:'):
                skip_ref = True
            continue
        if skip_ref and (re.match(r'^[:\d]', t) or t.startswith('Ref')):
            continue
        skip_ref = False
        cleaned.append(t)
    # strip trailing country codes / installment ratio tokens
    while cleaned and (cleaned[-1].upper() in COUNTRY
                       or re.match(r'^:?\d{2,3}/\d{2,3}$', cleaned[-1])
                       or re.match(r'^[:]\d+', cleaned[-1])):
        cleaned.pop()
    desc = ' '.join(cleaned)
    desc = re.sub(r'\s+Txn\s+Ref:.*$', '', desc, flags=re.I)
    desc = re.sub(r'\s+:\s*\d{2,3}/\d{2,3}\b', '', desc)
    return desc.strip()


# ---- statement date ----
def stmt_month(bank, text):
    t = text.replace('\r', ' ')

    def mon_date(d, mon, y):
        mon = mon[:3].upper()
        if mon not in MONTHS:
            return None
        yy = int(y) + (2000 if int(y) < 100 else 0)
        return f"{yy:04d}-{MONTHS[mon]:02d}", f"{yy:04d}-{MONTHS[mon]:02d}-{int(d):02d}"

    # 1) TIGHT "Statement Date" label + "dd Mon yyyy". Anchoring on the full label (not just the
    #    word "Statement") matters for SC: some SC templates print the Payment Due Date *before*
    #    the statement date, so a loose anchor grabs the due date and lands in the wrong month.
    m = re.search(r'Statement\s*Date\b[^0-9]{0,40}?(\d{1,2})\s+([A-Za-z]{3,})\s+(\d{2,4})', t, re.I)
    if m and (r := mon_date(*m.groups())):
        return r
    # 2) alliance: Malay label "Tarikh Penyata dd/mm/yy" sits right next to the value; the English
    #    "Statement Date" is far from it and the due date dd/mm/yy can appear first.
    m = re.search(r'Tarikh\s*Penyata\s*(\d{2})/(\d{2})/(\d{2})', t, re.I)
    if m:
        d, mo, y = m.groups()
        return f"20{y}-{mo}", f"20{y}-{mo}-{d}"
    # 3) LOOSE: first "dd Mon yyyy" after the word "Statement" (maybank/cimb: label & value are
    #    separated by address digits / bilingual headers, and the statement date precedes the due date).
    m = re.search(r'Statement[^0-9]{0,120}?(\d{1,2})\s+([A-Za-z]{3,})\s+(\d{2,4})', t, re.I)
    if m and (r := mon_date(*m.groups())):
        return r
    # 4) alliance English numeric fallback
    m = re.search(r'Statement\s*Date.{0,60}?(\d{2})/(\d{2})/(\d{2})', t, re.I | re.S)
    if m:
        d, mo, y = m.groups()
        return f"20{y}-{mo}", f"20{y}-{mo}-{d}"
    # 5) last resort: first "dd Mon yyyy" anywhere in the document
    m = re.search(r'\b(\d{1,2})\s+([A-Za-z]{3})\s+(\d{2,4})\b', t)
    if m and (r := mon_date(*m.groups())):
        return r
    return "UNKNOWN", "UNKNOWN"


# ---- payment due date ----
def _iso_due(d, mon, y):
    """(day, month-name-or-code, year) -> 'YYYY-MM-DD' or None. Year may be 2- or 4-digit."""
    mon = mon[:3].upper()
    if mon not in MONTHS:
        return None
    yy = int(y) + (2000 if int(y) < 100 else 0)
    return f"{yy:04d}-{MONTHS[mon]:02d}-{int(d):02d}"


def due_date(bank, text):
    """Per-bank payment due date as ISO 'YYYY-MM-DD', or None if not confidently found.
    Formats per bank are documented in docs/superpowers/plans/2026-06-22-deterministic-bills.md."""
    t = text.replace('\r', ' ')

    if bank == 'sc':
        m = re.search(r'Payment\s*Due\s*Date[^0-9]{0,30}(\d{1,2})\s+([A-Za-z]{3,})\s+(\d{4})', t, re.I)
        return _iso_due(*m.groups()) if m else None

    if bank == 'hsbc':
        m = re.search(r'Payment\s*Due\s*Date\s*(\d{1,2})\s+([A-Za-z]{3,})\s+(\d{4})', t, re.I)
        return _iso_due(*m.groups()) if m else None

    if bank == 'rhb':
        m = re.search(r'Payment\s*Due\s*Date\s*(\d{2})/(\d{2})/(\d{4})', t, re.I)
        if m:
            d, mo, y = m.groups()
            return f"{y}-{mo}-{d}"
        return None

    if bank == 'alliance':
        m = re.search(r'(?:Tarikh\s*Bayaran\s*Perlu\s*Dibuat|Payment\s*Due\s*Date)[^0-9]{0,30}'
                      r'(\d{2})/(\d{2})/(\d{2})', t, re.I)
        if m:
            d, mo, y = m.groups()
            return f"20{y}-{mo}-{d}"
        return None

    if bank in ('maybank', 'cimb'):
        # statement date then due date: the first two adjacent `dd Mon yy/yyyy` tokens
        # near the top of the statement; the due date is the SECOND. (Transaction rows
        # for these banks use dd/mm dates, so they don't collide with this dd-Mon form.)
        ms = re.findall(r'(\d{1,2})\s+([A-Za-z]{3})\s+(\d{2,4})\b', t)
        if len(ms) >= 2:
            return _iso_due(*ms[1])
        return None

    return None


def num(s):
    return float(s.replace(',', '').replace('CR', '').strip())


def grab(text, pat):
    m = re.search(pat, text, re.I)
    return num(m.group(1)) if m else None


def sum_all(text, pat):
    vals = [num(m) for m in re.findall(pat, text, re.I)]
    return round(sum(vals), 2) if vals else None


def first_all(text, pat):
    m = re.findall(pat, text, re.I)
    return num(m[0]) if m else None


def sum_signed(text, pat):
    """Sum all matches of `pat` (group1=number, group2=optional 'CR'); CR -> negative."""
    vals = []
    for m in re.finditer(pat, text, re.I):
        v = num(m.group(1))
        vals.append(-v if m.group(2) else v)
    return round(sum(vals), 2) if vals else None


def recon_balances(bank, text):
    """Return (previous_balance, current_balance), summed across cards for multi-card banks."""
    if bank == 'maybank':
        prev = first_all(text, r'PREVIOUS\s+STATEMENT\s+BALANCE\s+([\d,]+\.\d{2})')
        cur = first_all(text, r'SUB\s*TOTAL\s*/?\s*JUMLAH\s+([\d,]+\.\d{2})')
    elif bank == 'hsbc':
        prev = first_all(text, r'Your\s*Previous\s*Statement\s*Balance\s*([\d,]+\.\d{2})')
        cur = first_all(text, r'Your\s*statement\s*balance\s*([\d,]+\.\d{2})')
    elif bank == 'sc':
        cur = first_all(text, r'New\s+BALANCE\s*(?:/\s*Baki\s*Baru)?\s+([\d,]+\.\d{2})')
        prev = first_all(text, r'PREVIOUS\s+STATEMENT\s+([\d,]+\.\d{2})')
        if prev is None:  # variant template: read first number of the "Previous Balance ... = New Balance" row
            for line in text.splitlines():
                if len(re.findall(r'[\d,]+\.\d{2}', line)) >= 6:
                    prev = num(re.findall(r'[\d,]+\.\d{2}', line)[0])
                    break
    elif bank == 'cimb':
        # CIMB-i: a trailing CR = credit (negative) balance -> flip sign on prev & cur.
        m = re.search(r'PREVIOUS\s+BALANCE\s+([\d,]+\.\d{2})(CR)?', text, re.I)
        prev = (-num(m.group(1)) if m.group(2) else num(m.group(1))) if m else None
        bals = []
        for cm in re.finditer(r'\d{4}-\d{4}-\d{4}-\d{4}\s+[A-Za-z][^\n]*', text):
            toks = re.findall(r'[\d,]+\.\d{2}(?:CR)?', cm.group(0))
            if len(toks) >= 3 and num(toks[0]) > 0:   # sale-price>0 skips the tax-summary zero rows
                sb = toks[-2]                         # statement balance = before min-payment
                bals.append(-num(sb) if sb.endswith('CR') else num(sb))
        cur = round(sum(bals), 2) if bals else None
    elif bank == 'rhb':
        prev = sum_all(text, r'OPENING\s+BALANCE\s*/?\s*BAKI\s*MULA\s+([\d,]+\.\d{2})')
        cur = first_all(text, r'(?:Outstanding\s+Balance|Baki\s+Terkini)[^\n]*?([\d,]+\.\d{2})')
    elif bank == 'alliance':
        # multi-card: sum per-card balances. A trailing "CR" = credit (negative) balance
        # (the virtual card often sits in credit) -> negate, else recon is off by 2x.
        prev = sum_signed(text, r'PREVIOUS\s+STATEMENT\s+BALANCE\s+([\d,]+\.\d{2})\s*(CR)?')
        cur = sum_signed(text, r'CURRENT\s+BALANCE\s+([\d,]+\.\d{2})\s*(CR)?')
    else:
        prev = cur = None
    return prev, cur


# ============================ per-bank parsers ============================
def parse_dated(path, bank, date_re, ncards_multi=False):
    """Generic: rows shaped [date(s)] desc amount[CR]; optional multi-card via card-number header."""
    txns = []
    cur_card = None
    for pno, y, toks in all_rows(path):
        texts = [t['text'] for t in toks]
        line = ' '.join(texts)
        # card section header
        cm = CARDNUM_DASH.search(line) or CARDNUM_SPACE.search(line)
        if cm and ncards_multi:
            cur_card = cm.group(1)[-4:]
        # transaction row?
        dm = date_re.match(line)
        if not dm:
            continue
        amt, cr, ai = find_amount(texts)
        if amt is None:
            continue
        ndate = dm.group('n') and len(dm.group('n').split())  # not used
        # how many leading date tokens to drop
        lead = dm.group(0).split()
        drop = len(lead)
        desc_toks = texts[drop:ai]
        desc = clean_desc(desc_toks)
        if not desc or not re.search(r'[A-Za-z]', desc):
            continue
        # maybank balance-transfer-in principal ("BALANCE TFER ... T/F ER IN") is a contra memo,
        # excluded from the month's debit total (installments say full "TRANSFER", kept).
        # CIMB-i installment rows carry a ":NN/MM" ratio. ":0/MM" is the full plan principal
        # posted as a deferred memo (billed in later months) -> exclude from this month's debit;
        # ":01/MM"+ are the actual monthly charges -> keep in debit. Both are financing, not
        # consumption, so flag every installment row to force its category (see main()).
        inst = bool(bank == 'cimb' and re.search(r'(?:^|[\s:])\d{1,3}/\d{2,3}(?=\s|$)', line))
        inst0 = bool(inst and re.search(r'(?:^|[\s:])0+/\d{2,3}(?=\s|$)', line))
        excl = (bank == 'maybank' and 'TFER' in desc.upper()) or inst0
        txns.append(dict(card=cur_card, post=lead[0] if lead else '',
                         txn=lead[1] if len(lead) > 1 else (lead[0] if lead else ''),
                         desc=desc, amount=amt, credit=cr, excl=bool(excl), inst=inst))
    return txns


def parse_alliance(path):
    """Alliance: a date-only row (dd/mm/yy dd/mm/yy) immediately precedes its desc+amount row.
    Requiring that adjacency rejects rewards/marketing lines that merely carry a number."""
    txns = []
    cur_card = None
    pending_dates = None
    for pno, y, toks in all_rows(path):
        texts = [t['text'] for t in toks]
        line = ' '.join(texts)
        cm = CARDNUM_SPACE.search(line) or CARDNUM_DASH.search(line)
        if cm and re.search(r'VISA|CARD', line, re.I):
            cur_card = cm.group(1)[-4:]
            pending_dates = None
            continue
        if re.fullmatch(r'(?:\d{2}/\d{2}/\d{2}\s*)+', line.strip()):
            pending_dates = re.findall(r'\d{2}/\d{2}/\d{2}', line)
            continue
        # only the row directly after a date row can be a transaction
        if pending_dates is None:
            continue
        pd, pending_dates = pending_dates, None
        amt, cr, ai = find_amount(texts)
        if amt is None:
            continue
        if re.search(r'PREVIOUS STATEMENT BALANCE|CURRENT BALANCE|CHARGES THIS MONTH|'
                     r'CREDIT LIMIT|MINIMUM PAYMENT|TOTAL', line, re.I):
            continue
        desc = clean_desc(texts[:ai])
        if not desc or not re.search(r'[A-Za-z]', desc):
            continue
        post = pd[1] if len(pd) > 1 else pd[0]
        txns.append(dict(card=cur_card, post=post, txn=pd[0], desc=desc, amount=amt, credit=cr, excl=False))
    return txns


DATE_2_SLASH = re.compile(r'^(?P<n>\d{2}/\d{2}\s+\d{2}/\d{2})\b')
DATE_2_MON = re.compile(r'^(?P<n>\d{2}\s+[A-Za-z]{3}\s+\d{2}\s+[A-Za-z]{3})\b')


def parse_statement(path):
    bank = os.path.basename(path).split('_')[0]
    text = full_text(path)
    smonth, sdate = stmt_month(bank, text)

    if bank == 'maybank':
        txns = parse_dated(path, bank, DATE_2_SLASH, ncards_multi=False)
    elif bank in ('cimb', 'rhb', 'sc', 'hsbc'):
        txns = parse_dated(path, bank, DATE_2_MON, ncards_multi=(bank in ('cimb', 'rhb')))
    elif bank == 'alliance':
        txns = parse_alliance(path)
    else:
        txns = []

    # default single-card last4 if none captured (also handles masked numbers like 5520-40XX-XXXX-XXXX)
    if not any(t['card'] for t in txns):
        m = (CARDNUM_DASH.search(text) or CARDNUM_SPACE.search(text)
             or re.search(r'[\dX*]{4}[- ][\dX*]{4}[- ][\dX*]{4}[- ](\d{4})', text))
        last4 = m.group(1)[-4:] if m else '????'
        for t in txns:
            t['card'] = last4

    # ---- reconciliation figures (statement-level) ----
    prev, cur = recon_balances(bank, text)
    debit = sum(t['amount'] for t in txns if not t['credit'] and not t.get('excl'))
    credit = sum(t['amount'] for t in txns if t['credit'] and not t.get('excl'))
    expected = (prev + debit - credit) if prev is not None else None
    diff = (expected - cur) if (expected is not None and cur is not None) else None
    if diff is None:
        status = 'NO_BALANCE'
    elif abs(diff) <= 0.02:
        status = 'VERIFIED'
    else:
        status = 'REVIEW'

    return dict(file=os.path.basename(path), bank=bank, smonth=smonth, sdate=sdate,
                due=due_date(bank, text),
                prev=prev, cur=cur, debit=round(debit, 2), credit=round(credit, 2),
                expected=None if expected is None else round(expected, 2),
                diff=None if diff is None else round(diff, 2),
                status=status, n=len(txns)), txns


# ============================ categorization ============================
CATS = [
    ('Transfers/Payments', ['PAYMENT - THANK', 'PAYMENT-THANK', 'IBG PAYMENT', 'PYMT@', 'DUITNOW',
                            'FROM ARIFF', 'PAYMENT THANK', 'FUND TRANSFER', 'FUNDS TRANSFER', 'INSTANT TRANSFER',
                            'CC STATEMENT', 'PAYMENT THROUGH GIRO', 'PAYMENT VIA', 'GIRO', 'INTERBANK FUND',
                            'INTERBANK GIRO', 'IBG', 'IBFT', 'RPP ', 'BTCX']),
    ('Fees/Charges', ['PROFIT CHRG', 'PROFIT CHARGE', 'SERVICE TAX', 'ONE TIME CHARGE', 'CASH ADVANCE FEE',
                      'LATE PAYMENT', 'FINANCE CHARGE', 'INTEREST', 'ANNUAL FEE', 'OVERLIMIT', 'RTL PROFIT',
                      'STAMP DUTY', 'CHRG RATE', 'WISE *CARD', 'IPAY88', 'GHL*', 'EZBIZ']),
    ('Rebate/Cashback', ['CASH BACK', 'CASHBACK', 'REBATE', 'REWARDS CASH', 'CASH REWARD', 'REWARD',
                         'SIMPLYCASH']),
    ('Installments/BT', ['BALANCE TRANSFER', 'BAL TRANSFER', 'SMART MOVE', 'INSTL', 'EZBELI', 'EASY PAYMENT',
                         'BALANCE TFER', '-12M', '-24M', '-36M', 'HOMEPRO', 'FLEXIPAY']),
    ('Vehicle', ['PETRONAS', 'SHELL', 'SETEL', 'BHP', 'CALTEX', 'PETRON',
                 'GRAB RIDES', 'GRAB-EC', 'GRABCAR', 'GRAB RIDE', 'TOUCH N GO', 'TNG', 'TOUCHNGO',
                 'TOLL', 'PARKING', 'RAPIDKL', 'MRT', 'LRT', 'AIRPORT PARK', 'FLOWPARK', 'GRABPAY',
                 'EXPRESS RAIL', 'ERL ', 'KTMB', 'RAPID ', 'TPT ',
                 'MOTORSPORT', 'AUTOSPEED', 'EE TIONG', 'PSS-', 'PSS ', 'PS SG', 'PS R&R',
                 'AMANO', 'PUTRAJAYA SENTRAL', '372-MY', 'APSB']),
    ('Groceries', ['LOTUS', 'MYDIN', 'AEON CO', 'AEON ', '99 SPEED', 'SPEED MART', 'KK SUPER', 'KK MART',
                   '7-ELEVEN', '7 ELEVEN', 'GIANT', 'TESCO', 'JAYA GROCER', 'ECONSAVE', 'ECON ',
                   'FARM FRESH', 'NSK', 'MYNEWS', 'BILLION', 'SEGI FRESH', 'HERO MARKET', 'VILLAGE GROCER',
                   'KK SUPERMART', 'PASARAYA', 'GROCER', 'MART -', 'SUPERMARKET', 'SUPER SEVEN',
                   'FAMILYMART', 'FAMILY MART']),
    ('F&B', ['RESTORAN', 'RESTAURANT', 'SUBWAY', 'A&W', 'DUNKIN', 'FAMOUS AMOS', 'AUNTIE ANNE',
                'ROTIBOY', 'HOT & ROLL', 'EMPIRE SUSHI', 'BISTRO', 'MCDONALD', 'KFC', 'STARBUCKS', 'ZUS',
                'BAKER', 'CAFE', 'COFFEE', 'KOPITIAM', 'SUSHI', 'PIZZA', 'BURGER', 'FOOD', 'KENNY ROGERS',
                'NANDOS', 'SECRET RECIPE', 'OLDTOWN', 'TEALIVE', 'CHATIME', 'MIXUE', 'KOI', 'BIG APPLE',
                'TEPPANYAKI', 'TORII', 'LAEM CHAROEN', 'BUNGKUS', "ME'NATE", 'STEAK', 'NASI', 'MAKAN',
                'KOPI', 'BLACK CANYON', 'MARRYBROWN', 'TEPANYAKI', 'RAMEN', 'NOODLE', 'CHICKEN', 'BISTRO',
                'THAIKOR', 'MYEUREKA', 'SARA SOFEYA', 'CENDOL', 'CHENDUL', 'AKMAL SQUARED',
                'KEDAI PERNAMA', 'PENANG CHENDUL', 'LITTLE MALAYSIA', '10 POTS', 'POTS @',
                '4 FINGERS', 'YONG TAU FOO', 'ANI SUP', 'BK MID VALLEY',
                'FUJIYAMA', 'SUKI-YA', "CHILI'S", "NANDO'S", 'MENGRAI', 'PADI HOUSE', 'ICHIBAN',
                'AH CHENG', 'SATE KAJANG', 'JFC-', 'KAKATOO', 'QCC BAKED', 'HAPPY POTATO', 'POP MEALS',
                'KRA POW', 'SHIHLIN', 'HOE HUAT', 'NAK NAK', 'MYOHSOME', 'KAIFLEX']),
    ('Telco/Utilities', ['MAXIS', 'CELCOM', 'DIGI', 'UNIFI', 'TM ', 'TIMEDOTCOM', 'TIME DOTCOM', 'TNB',
                         'AIR SELANGOR', 'AIR SELANGO', 'PENGURUSAN AIR', 'YES ', 'U MOBILE', 'UMOBILE',
                         'INDAH WATER', 'TELEKOM', 'WEBE', 'TUNE TALK']),
    ('Travel', ['AGODA', 'BOOKING.COM', 'AIRASIA', 'MALAYSIA AIRLINE', 'BATIK AIR', 'HOTEL', 'PULLMAN',
                'EXPEDIA', 'TRAVELOKA', 'KLIA', 'RESORTS', 'TRIP.COM', 'AIRBNB']),
    ('Health/Insurance', ['AIA', 'PRUBSN', 'PRUDENTIAL', 'GREAT EASTERN', 'ALLIANZ', 'TAKAFUL', 'DENTABAY',
                          'CANCER', 'PHARMACY', 'GUARDIAN', 'WATSON', 'CLINIC', 'KLINIK', 'HOSPITAL',
                          'DENTAL', 'VITALITY', 'MEDICAL', 'PRU', 'FARMASI', 'HOSPITAL', 'POLIKLINIK',
                          'AURELIUS', 'OPTIMAX', 'DR SMILE', 'POLIKLINIK', 'SPECIALIST', 'EYE SPCLT']),
    ('Subscriptions', ['CLAUDE', 'ANTHROPIC', 'NETFLIX', 'SPOTIFY', 'YOUTUBE', 'OPENAI', 'GOOGLE',
                       'WORKSPACE', 'WHATSAPP BUSIN', 'MICROSOFT', 'APPLE.COM', 'ADOBE', 'CANVA',
                       'DISNEY', 'AMAZON PRIME', 'ICLOUD', 'GITHUB', 'OPENROUTER', 'CURSOR', 'FIGMA',
                       '1PASSWORD', 'ERASER.IO', 'VERCEL', 'NOTION', 'SUPABASE', 'CLOUDFLARE', 'LINODE',
                       'PIKAPODS', 'YOODO', 'DOWNL MANAGER', 'PADDLE.NET', 'CLEANVOICE', 'PYX*BEAM',
                       'TIOF', 'GRABGIFTS']),
    ('Shopping', ['SHOPEE', 'LAZADA', 'HARVEY NORM', 'IKEA', 'ERGOWORKS', 'PADINI', 'UNIQLO', 'B&M',
                  'CAROUSELL', 'ZALORA', 'DECATHLON', 'COURTS', 'SENHENG', 'POPULAR', 'MR DIY', 'MR. DIY',
                  'MR D.I.Y', 'SPAYLATER', 'ATOME', 'BLIND BOX', 'KOMACHI', 'WATSONS', 'DAISO', 'KKV',
                  'NINSO', 'MR DOLLAR', 'ECOSHOP', 'ECO-', 'ECO SHOP', "TOYS 'R' US", 'TOYS R US',
                  'MR.DIY', 'ELLA', 'STORE', 'NINJA', 'TADO', 'HOME PRODUCT', 'HABIB', 'ALL IT',
                  'IM-ALL IT', 'ECS-', 'BRIGHTSTAR', 'SENQ', 'SENHENG', 'KEMUDI TIMUR',
                  'PARKSON', 'BATA ', "JR BROTHER", 'BIG-IPC', 'WHSMITH', 'TCRS', 'PETS.TWENTYONE',
                  'MYMART', 'CONVENIENCE SHOP', 'AMPANG PARK', 'BOK MARKETING', 'JIM-KSL', 'HP-KIP',
                  "D'GANU", 'MPC2004', 'MPC1009', 'AGIBS', 'WOODSAGE', 'BMS-KL', 'TPRBGURNEY',
                  'SIMA-IOI', 'AYMAR', 'SMART LEGACY', 'ZHOE']),
    ('Entertainment', ['GSC', 'TGV', 'CINEMA', 'STEAM', 'PLAYSTATION', 'GAME', 'KARAOKE', 'GOLF',
                       'CELEBRITY FITNESS', 'GYM', 'FITNESS', 'KIDZOOONA', 'KIDZOONA', 'KIDDYTOPIA',
                       'MISSION WORLD', 'PARENTHOOD', 'FLIZZIE', 'ELEVATE SOCIAL']),
    ('Certifications', ['BOARD OF TECH', 'MBOT']),
    ('Charity', ['SUKA SOCIETY', 'DONATION', 'DERMA', 'ZAKAT', 'WAKAF']),
]


def categorize(desc):
    u = desc.upper()
    for cat, kws in CATS:
        for kw in kws:
            if kw in u:
                return cat
    return 'Other'


# ============================ main ============================
def main():
    files = sorted(glob.glob(os.path.join(SRC, '*.pdf')))
    tx_rows = []
    recon = []
    seen_fp = {}                              # statement fingerprint -> first file that had it
    for f in files:
        try:
            meta, txns = parse_statement(f)
        except Exception as e:
            recon.append(dict(file=os.path.basename(f), bank='?', smonth='ERR', sdate=str(e),
                              prev=None, cur=None, debit=0, credit=0, expected=None, diff=None,
                              status='ERROR', n=0))
            continue
        # Drop duplicate statements. The n8n compile workflow re-exports the FULL label-CC history
        # every run, so the same statement can arrive under several filenames (the _N index is
        # meaningless). Two files with identical (bank, statement date, balances, debit/credit, txn
        # count) are the same statement -> keep the first, skip the rest, else everything double-counts.
        fp = (meta['bank'], meta['sdate'], meta['prev'], meta['cur'],
              meta['debit'], meta['credit'], meta['n'])
        if fp in seen_fp:
            meta = dict(meta, status='DUPLICATE')
            meta['diff'] = None
            recon.append(meta)
            continue
        seen_fp[fp] = meta['file']
        recon.append(meta)
        for t in txns:
            cat = 'Installments/BT' if t.get('inst') else categorize(t['desc'])
            typ = 'credit' if t['credit'] else 'debit'
            tx_rows.append(dict(
                bank=meta['bank'], card_last4=t['card'], statement_month=meta['smonth'],
                statement_date=meta['sdate'], post_date=t['post'], txn_date=t['txn'],
                description=t['desc'], amount=t['amount'], type=typ, category=cat,
                source_file=meta['file']))

    # transactions.csv
    with open('transactions.csv', 'w', newline='', encoding='utf-8-sig') as fh:
        w = csv.DictWriter(fh, fieldnames=['bank', 'card_last4', 'statement_month', 'statement_date',
                                           'post_date', 'txn_date', 'description', 'amount', 'type',
                                           'category', 'source_file'])
        w.writeheader()
        w.writerows(tx_rows)

    # reconciliation.csv
    with open('reconciliation.csv', 'w', newline='', encoding='utf-8-sig') as fh:
        w = csv.DictWriter(fh, fieldnames=['file', 'bank', 'smonth', 'sdate', 'due', 'n', 'prev', 'debit',
                                           'credit', 'expected', 'cur', 'diff', 'status'])
        w.writeheader()
        for r in recon:
            w.writerow({k: r.get(k) for k in w.fieldnames})

    # "Spend" = discretionary consumption, excluding financing/contra/rebate categories.
    # Consumption categories are NETTED: a refund/reversal (a credit sitting under a merchant
    # category, e.g. a cancelled hotel booking) subtracts from that category. Financing categories
    # stay debit-only/gross (their credits are bill payments & cashback, not negative spend).
    NON_SPEND = {'Transfers/Payments', 'Rebate/Cashback', 'Installments/BT'}
    spend = defaultdict(float)            # (bank, card, month) -> net discretionary spend
    catm = defaultdict(float)             # (month, category) -> total
    cube = defaultdict(float)             # (bank, card, month, category) -> total
    for t in tx_rows:
        cat = t['category']
        if cat in NON_SPEND:
            if t['type'] != 'debit':      # ignore payments/cashback credits
                continue
            val = t['amount']
        else:
            val = t['amount'] if t['type'] == 'debit' else -t['amount']   # net refunds
        catm[(t['statement_month'], cat)] += val
        cube[(t['bank'], t['card_last4'], t['statement_month'], cat)] += val
        if cat not in NON_SPEND:
            spend[(t['bank'], t['card_last4'], t['statement_month'])] += val
    with open('summary_card_month.csv', 'w', newline='', encoding='utf-8-sig') as fh:
        w = csv.writer(fh)
        w.writerow(['bank', 'card_last4', 'statement_month', 'total_spend'])
        for (b, c, m), v in sorted(spend.items()):
            w.writerow([b, c, m, round(v, 2)])
    with open('summary_category_month.csv', 'w', newline='', encoding='utf-8-sig') as fh:
        w = csv.writer(fh)
        w.writerow(['statement_month', 'category', 'total'])
        for (m, c), v in sorted(catm.items()):
            w.writerow([m, c, round(v, 2)])
    with open('summary_card_category_month.csv', 'w', newline='', encoding='utf-8-sig') as fh:
        w = csv.writer(fh)
        w.writerow(['bank', 'card_last4', 'statement_month', 'category', 'total'])
        for (b, c, m, cat), v in sorted(cube.items()):
            w.writerow([b, c, m, cat, round(v, 2)])

    # report
    from collections import Counter
    st = Counter(r['status'] for r in recon)
    perbank = defaultdict(Counter)
    for r in recon:
        perbank[r['bank']][r['status']] += 1
    uniq = sum(1 for r in recon if r['status'] != 'DUPLICATE')
    print(f"files={len(files)} unique_statements={uniq} txns={len(tx_rows)}  status={dict(st)}")
    for b in sorted(perbank):
        print(f"  {b:9s} {dict(perbank[b])}")
    dups = [r for r in recon if r['status'] == 'DUPLICATE']
    if dups:
        print(f"--- DUPLICATE (dropped, same statement under another filename) x{len(dups)} ---")
        for r in dups:
            print(f"  {r['file']:30s} {r['bank']:8s} {r['smonth']} sdate={r['sdate']} n={r['n']} cur={r['cur']}")
    print("--- REVIEW (|diff|>0.02) ---")
    for r in recon:
        if r['status'] == 'REVIEW':
            print(f"  {r['file']:30s} {r['bank']:8s} n={r['n']} prev={r['prev']} deb={r['debit']} "
                  f"cr={r['credit']} exp={r['expected']} cur={r['cur']} diff={r['diff']}")


if __name__ == '__main__':
    main()
