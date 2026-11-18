# Mortgage Servicing Cash Reconciliation Pipeline

A Python pipeline that reconciles a mortgage servicer's books against its custodial bank statement, finds the root cause of every break, and routes each one to the right owner.

Built by Isaiah McCamie to model the daily reconciliation work I did at SEI Investments, translated into mortgage servicing.

## How it works
1. **Clean:** standardize the bank's messy dates, amounts and loan references
2. **Crosswalk:** map bank references to internal loan IDs; suggest matches for cash with no loan number (borrower name + exact scheduled amount)
3. **Match:** pair book postings to bank lines by loan and amount
4. **Classify:** use the loan schedule as a tiebreaker to decide which side is wrong, then identify the cause (missing interest, missing escrow, curtailment, transposition, timing, duplicate, not received)
5. **Route:** send each break to one of four paths (wait, fix with client sign-off, internal team, bank) and export `breaks_report.csv`

## Run it
    python pipeline.py

## Data
All data in `/data` is synthetic.