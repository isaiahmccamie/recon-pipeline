import csv
import re

# STEP 1: CLEANING
# The bank writes dates, amounts and loan numbers in messy ways.
# These three functions make everything look the same as our books.

def clean_date(us_date):
    # "11/12/2026" -> "2026-11-12"
    month, day, year = us_date.split("/")
    return year + "-" + month + "-" + day

def clean_amount(text):
    # "$2,409.77" or "2,409.77" -> 2409.77
    text = text.replace("$", "").replace(",", "")
    return float(text)

def clean_loan_id(description):
    # "ACH CREDIT MTG PMT LN 1004500" -> "SV-1004500"
    numbers = re.findall(r"\d{7,}", description)
    if not numbers:
        return None
    loan_number = str(int(numbers[0]))
    return "SV-" + loan_number

# Read the loan master (what each borrower SHOULD pay)
loans = {}
with open("data/loans.csv") as f:
    for row in csv.DictReader(f):
        loans[row["loan_id"]] = row

# STEP 1: clean every bank line and keep it in a list
bank = []
with open("data/bank.csv") as f:
    for row in csv.DictReader(f):
        line = {
            "date": clean_date(row["value_date"]),
            "loan": clean_loan_id(row["description"]),
            "amount": clean_amount(row["amount"]),
            "description": row["description"],
        }
        bank.append(line)

# STEP 2: CROSSWALK
# If the bank gave no loan number, play detective:
# last name in the description AND amount = scheduled payment
for line in bank:
    if line["loan"] is None:
        for loan_id, loan in loans.items():
            last_name = loan["borrower"].split()[-1].upper()
            if last_name in line["description"] and float(loan["scheduled"]) == line["amount"]:
                line["loan"] = loan_id
                line["note"] = "Suggested match: " + loan["borrower"] + " (confirm before posting)"

# Read our books (what we posted)
books = []
with open("data/books.csv") as f:
    for row in csv.DictReader(f):
        row["total"] = float(row["total"])
        books.append(row)

# STEP 3: MATCHING
# Pair a book posting with a bank line: same loan AND same amount.
# Anything left without a partner is a break.
matched = []
leftover_bank = list(bank)
leftover_books = []

for post in books:
    partner = None
    for line in leftover_bank:
        if line["loan"] == post["loan_id"] and line["amount"] == post["total"]:
            partner = line
            break
    if partner:
        matched.append((post, partner))
        leftover_bank.remove(partner)
    else:
        leftover_books.append(post)

# STEP 4: CLASSIFY - figure out WHY each break happened
AS_OF = "2026-11-16"   # today's business date

def same(a, b):
    # two amounts are equal if they're within half a cent
    return abs(a - b) < 0.005

def digits_swapped(a, b):
    # 2049.77 vs 2409.77 -> same digits, different order = keying error
    x = str(round(a * 100))
    y = str(round(b * 100))
    return x != y and sorted(x) == sorted(y)

def find_post(loan_id):
    for post in leftover_books:
        if post["loan_id"] == loan_id:
            return post
    return None

def find_bank_line(loan_id):
    for line in leftover_bank:
        if line["loan"] == loan_id:
            return line
    return None

def already_matched(loan_id, amount):
    for post, line in matched:
        if line["loan"] == loan_id and same(line["amount"], amount):
            return True
    return False

# make a list of every loan that has a break
loan_ids = []
for post in leftover_books:
    if post["loan_id"] not in loan_ids:
        loan_ids.append(post["loan_id"])
for line in leftover_bank:
    if line["loan"] not in loan_ids:
        loan_ids.append(line["loan"])
        breaks = []
for loan_id in loan_ids:
    loan = loans[loan_id]
    expected = float(loan["scheduled"])
    our_post = find_post(loan_id)
    bank_line = find_bank_line(loan_id)

    if our_post and bank_line:
        # both sides have it, but the amounts differ
        ours = our_post["total"]
        theirs = bank_line["amount"]
        diff = round(theirs - ours, 2)
        if same(ours, expected):
            # OUR books match the schedule, so the difference is on the bank side
            if digits_swapped(theirs, expected):
                reason = "Bank keyed the wrong amount (digits swapped)"
            elif diff > 0 and round(diff * 100) % 5000 == 0:
                reason = "Extra principal (curtailment) not applied"
            else:
                reason = "Bank amount is wrong"
        elif same(theirs, expected):
            # the BANK matches the schedule, so OUR books are off
            if same(diff, float(loan["interest"])):
                reason = "Interest not applied"
            elif same(diff, float(loan["escrow"])):
                reason = "Escrow not applied"
            elif digits_swapped(ours, expected):
                reason = "We keyed the wrong amount (digits swapped)"
            else:
                reason = "Our posting is wrong"
        else:
            reason = "Neither side matches the schedule: research"
    elif our_post:
        # only on OUR books
        diff = -our_post["total"]
        if our_post["settle_date"] > AS_OF:
            reason = "Pending settlement (timing, will clear)"
        else:
            reason = "On our books, never reached the bank"
    else:
        # only at the BANK
        diff = bank_line["amount"]
        if already_matched(loan_id, bank_line["amount"]):
            reason = "Duplicate credit at the bank"
        elif "note" in bank_line:
            reason = "Cash with no loan number. " + bank_line["note"]
        else:
            reason = "Cash received, not posted to the loan"

    breaks.append({"loan": loan_id, "borrower": loan["borrower"], "diff": diff, "reason": reason})

# STEP 5: ROUTE - send each break to the right person
def route(reason):
    if "Pending" in reason:
        return "WAIT", "Nobody - recheck on tomorrow's statement", 2
    if "Bank keyed" in reason or "never reached" in reason or "Duplicate" in reason:
        return "BANK", "Custodial bank ops - email with backup", 120
    if "We keyed" in reason or "Our posting" in reason:
        return "INTERNAL", "Cash Operations team - correct the posting", 45
    return "FIX", "Recon team posts the entry (client sign-off first)", 15

total_minutes = 0
for b in breaks:
    b["route"], b["owner"], b["minutes"] = route(b["reason"])
    total_minutes += b["minutes"]

print("BREAKS FOUND:", len(breaks))
for b in breaks:
    print(b["loan"], str(b["diff"]).rjust(9), " ", b["route"].ljust(8), b["reason"])
    print("                      ->", b["owner"])

print()
print("Time if worked by hand:", total_minutes, "minutes")

# save the report so the ops team can open it in Excel
with open("breaks_report.csv", "w", newline="") as f:
    columns = ["loan", "borrower", "diff", "reason", "route", "owner", "minutes"]
    writer = csv.DictWriter(f, fieldnames=columns)
    writer.writeheader()
    writer.writerows(breaks)
print("Saved breaks_report.csv")