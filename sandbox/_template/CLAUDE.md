# Experiment — [NAME HERE]

## STATUS
EXPERIMENT (sandbox). Not live. Not auto-started.

## GOAL
*(1-2 sentences: what question does this experiment answer?)*

## PORT
8000 — change to an unused port in 8000-8999 range if occupied.

## ISOLATION CHECKLIST
- [ ] No imports from `trading/`, `kalshi/`, `companies/`, `telegram-bridge/`
- [ ] No writes outside this folder
- [ ] `PAPER_MODE=True` hard-coded
- [ ] No real credentials (use test tokens in local `.env`)
- [ ] Runs manually (`python run.py`), no VBS

## HOW TO RUN
```bash
cd sandbox/<this-folder>
python run.py
```

## GRADUATION CRITERIA
*(what would this need to show before cherry-picking into production?)*

## NOTES
*(freeform — what you tried, what worked, what didn't)*
