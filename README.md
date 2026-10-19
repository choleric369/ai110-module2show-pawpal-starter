# PawPal+ (Module 2 Project)

**PawPal+** is a Streamlit app that helps a pet owner plan care tasks for their pets —
and keeps the health records, grooming log and costs that those plans depend on.

## Scenario

A busy pet owner needs help staying consistent with pet care. They want an assistant that can:

- Track pet care tasks (walks, feeding, meds, enrichment, grooming, etc.)
- Consider constraints (time available, priority, owner preferences)
- Produce a daily plan and explain why it chose that plan

## What this app does

- Owner profile with contact number, emergency contact and preferred vet clinic
- Multiple pets, each with name, breed, sex, date of birth, weight, microchip and insurance
- Tasks with duration, priority, recurrence, preferred time of day and fixed-time anchors
- **Medical history**: conditions, allergies, vaccinations and hospital visits
- **Grooming log** with services performed and when the next session is due
- **Bills** per pet, with payment status, insurance reimbursement and spending charts
- A daily schedule built from all of the above, with a written explanation of every choice
- Records feed the plan: a due booster, a vet follow-up or overdue grooming becomes a task
- JSON save/load — no database

## Getting started

### Setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

The app loads `data/pawpal_data.json` if present, and otherwise starts from built-in
demo data (a dog and a senior cat with full records), so it is never empty on first run.

### Project layout

```
pawpal/            core logic — pure Python, never imports Streamlit
  models/          Owner, Pet, CareTask (+6 subclasses), records, plan, preferences
  scheduling/      Scheduler, 4 ranking strategies, conflict handling, explanations
  services/        JSON storage, record-driven reminders, expense and plan stats
  utils/           time maths, validation, serialization
ui/components.py   Streamlit widgets
app.py             layout and wiring only
tests/             208 tests
diagrams/uml.mmd   class diagram, kept in sync with the code
```

## 🖥️ Sample Output

Real output from `DailyPlan.to_text()` on the built-in demo household:

```
Daily plan for the household — 2026-10-16
=========================================
  07:00 — Arthritis medication (5 min) [priority: high]
  07:10 — Training session (15 min) [priority: medium]
  07:30 — Morning meal (10 min) [priority: high]
  08:00 — Breakfast (10 min) [priority: high]
  08:15 — Morning walk (30 min) [priority: high]
  08:50 — Book FVRCP booster (30 min) [priority: high]
  17:00 — Wand play (10 min) [priority: medium]
  17:15 — Evening walk (40 min) [priority: high]
  18:30 — Dinner (10 min) [priority: high]
  19:00 — Evening meal (10 min) [priority: high]

Total: 170 min across 10 tasks

Skipped:
  - Brush coat: is not scheduled for this day
  - Brush + check for mats: is not scheduled for this day
  - Book Rabies booster: needs 30 min but only 10 min of your budget is left
  - Grooming: bath, de shedding, nail trim: needs 1h 15m but only 10 min of your budget is left
```

And the reasoning the app shows underneath it:

```
Strategy: Ranks by value per minute, so quick high-priority tasks come first. A good
middle ground, but it can defer a long task indefinitely.
Scheduled 10 task(s) totalling 2h 50m, running from 07:00 to 19:10.
4 task(s) did not fit:
  - Book Rabies booster needs 30 min but only 10 min of your budget is left
  - Grooming: bath, de shedding, nail trim needs 1h 15m but only 10 min of your budget is left
Tradeoff: kept 10 task(s) that fit the budget and deferred 'Book Rabies booster'.
```

Note `Book FVRCP booster` and the grooming task: neither was typed in by the owner.
Both were generated from records — an overdue vaccination and a lapsed grooming interval.

## 🧪 Testing PawPal+

```bash
# Run the full test suite:
pytest

# Run with coverage:
pytest --cov
```

Sample test output:

```
........................................................................ [ 34%]
........................................................................ [ 69%]
................................................................         [100%]
208 passed in 1.01s
```

| Test file | Tests | Covers |
|-----------|-------|--------|
| `test_task.py` | 22 | validation, scoring, recurrence, subclass round-trips |
| `test_pet.py` | 14 | task CRUD, age from DOB, species/age exercise needs |
| `test_scheduler_core.py` | 16 | ordering, budget, no-overlap, breaks, strategy swap |
| `test_scheduler_edge.py` | 11 | empty pool, zero budget, oversized task, determinism |
| `test_conflicts.py` | 14 | anchors, clashes, blocked windows, medication spacing |
| `test_recurrence.py` | 7 | daily / weekly / weekdays / once |
| `test_explain.py` | 14 | every task has a reason; warnings; text and markdown output |
| `test_records.py` | 35 | conditions, allergies, vaccinations, visits, grooming |
| `test_expenses.py` | 24 | bills, payments, reimbursement, rollups |
| `test_reminders.py` | 20 | records becoming tasks, and not duplicating manual ones |
| `test_storage.py` | 15 | JSON round-trip, corrupt-file fallback, atomic writes |
| `test_contact.py` | 16 | phone/email validation and formatting |

The Streamlit layer is verified separately with `streamlit.testing.v1.AppTest`,
which runs `app.py` end to end and clicks **Generate schedule**.

## 📐 Smarter Scheduling

| Feature | Method(s) | Notes |
|---------|-----------|-------|
| Task sorting | `SortStrategy.rank()` — `PriorityFirst`, `ShortestFirst`, `WeightedScore`, `Balanced` | Strategies decide order only; the scheduler owns placement, so no strategy can produce an invalid plan. Selectable in the sidebar. |
| Scoring | `CareTask.score()` + subclass overrides | Value density (priority ÷ minutes), with bands: medication `10_000+`, appointments `5_000+`, meals ×1.5, walks ×1.2. |
| Filtering | `Scheduler._filter_due()`, `CareTask.is_due()` | Daily / weekly / weekdays / once. Tasks not due today are reported as skipped *with a reason*, never dropped silently. |
| Time budget | `Scheduler._fits()` | Skippable tasks respect `available_minutes`; non-skippable ones (medication, appointments) bypass the budget but still cannot run past bedtime. |
| Placement | `conflicts.first_free_slot()` | Earliest-fit search across the whole day per task, so a lower-ranked task can still take an early gap. |
| Conflict handling | `conflicts.place_anchors()`, `find_overlaps()` | Fixed-time tasks are immovable and placed first; flexible tasks bend around them. Two anchors at one time → one placed, one reported. |
| Breaks | `break_minutes` padding in `first_free_slot()` | Each placed task reserves break minutes either side. |
| Blocked windows | `DayConstraints.is_blocked()` | Work hours etc. are never scheduled into. |
| Medication safety | `MedicationTask.conflicts_with()`, `respects_medication_gap()` | Doses of the same medication are kept `min_hours_between_doses` apart. |
| Recurring tasks | `Recurrence` enum + `weekdays` set | Weekly tasks carry the weekdays they fall on. |
| Record-driven tasks | `services/reminders.py` | Vet follow-ups, due boosters and overdue grooming become tasks automatically, tagged `[auto]`. |
| Explanation | `scheduling/explain.py` | Per-task reasons, concrete skip reasons ("needs 30 min, 10 left"), and a named tradeoff. |
| Unmet needs | `DailyPlan.unmet_needs()` | Warns when scheduled activity falls below a pet's species/age/energy target. |

## 📸 Demo Walkthrough

1. **Launch** with `streamlit run app.py`. The demo household loads: Biscuit (a 3-year-old
   Golden Retriever) and Mochi (a 12-year-old cat with arthritis).
2. **Set your day** in the sidebar — wake and sleep times, how many minutes you can spend
   on pet care, break length, and which scheduling strategy to use.
3. **Today's plan tab** → press *Generate schedule*. You get a time-ordered table, metrics
   across the top, and a "Why this plan?" panel explaining the strategy, each placement,
   and exactly why anything was dropped.
4. **Change the strategy** in the sidebar to *Shortest First* and regenerate — more tasks
   fit, but the long evening walk gets deferred. The explanation names that tradeoff.
5. **Pets & tasks tab** → open a pet to see its activity target and spend, add a task
   with a duration, priority, recurrence and optional fixed time.
6. **Health tab** → log a vet visit with a diagnosis, a cost and a follow-up date. Enter a
   vaccination with its next-due date. Severe allergies and overdue boosters appear as
   alerts at the top.
7. **Regenerate the plan** — the follow-up and the due booster are now scheduled tasks you
   never typed in.
8. **Grooming tab** → log a session and the services performed; the card tells you how long
   it has been and when the next one is due.
9. **Costs tab** → household spend, outstanding and overdue bills, a per-category breakdown
   and a monthly trend. Mark a bill paid inline.
10. **Save to disk** in the sidebar writes everything to `data/pawpal_data.json`.

**Screenshot or video** *(optional)*: <!-- Insert a screenshot or link to a demo video here -->

## Design notes

See **`reasoning.txt`** for the decisions behind the implementation, the bugs found while
building it, and the open questions I had to make assumptions about.
