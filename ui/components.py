"""Reusable Streamlit widgets so app.py stays a thin layout file.

Every function here renders only — it takes domain objects in and draws them.
Any function that changes state returns the change instead of mutating.
"""

from datetime import date, time

import streamlit as st

from pawpal.models.contact import Contact, Groomer, VetClinic
from pawpal.models.enums import (
    BillCategory,
    ConditionStatus,
    EnergyLevel,
    GroomingService,
    PaymentStatus,
    Priority,
    Recurrence,
    Severity,
    Sex,
    Species,
    StrategyName,
    TaskCategory,
    TimeOfDay,
    VisitType,
)
from pawpal.models.owner import Owner
from pawpal.models.pet import Pet
from pawpal.models.plan import DailyPlan
from pawpal.models.preferences import OwnerPreferences
from pawpal.models.records import (
    Allergy,
    Bill,
    Condition,
    GroomingSession,
    Vaccination,
    VetVisit,
)
from pawpal.models.task import CareTask, make_task
from pawpal.services import expenses
from pawpal.utils.serialization import format_money
from pawpal.utils.timeutils import format_duration

WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _labels(enum_cls) -> list[str]:
    """Human-readable labels for every member of an enum, in declaration order.

    Priority is an IntEnum, so its .value is a number — it exposes .label
    instead. Everything else is a str enum where .value is the text.
    """
    return [
        str(getattr(m, "label", m.value)).replace("_", " ").title() for m in enum_cls
    ]


def _pick(enum_cls, label: str, current, key: str):
    """Selectbox over an enum that returns the member, not the display string."""
    members = list(enum_cls)
    index = members.index(current) if current in members else 0
    chosen = st.selectbox(label, _labels(enum_cls), index=index, key=key)
    return members[_labels(enum_cls).index(chosen)]


def init_session(owner: Owner) -> None:
    """Seed st.session_state with the loaded owner on first run only."""
    if "owner" not in st.session_state:
        st.session_state.owner = owner
    st.session_state.setdefault("plan", None)
    st.session_state.setdefault("editing_task", None)
    st.session_state.setdefault("active_pet_id", owner.pets[0].id if owner.pets else None)


def owner_form(owner: Owner) -> Owner:
    """Owner name, phone, email and address; returns the updated Owner on submit."""
    with st.form("owner_form"):
        st.subheader("Your details")
        col1, col2 = st.columns(2)
        name = col1.text_input("Name", value=owner.name)
        phone = col2.text_input("Contact number", value=owner.phone)
        col3, col4 = st.columns(2)
        email = col3.text_input("Email", value=owner.email)
        address = col4.text_input("Address", value=owner.address)
        if st.form_submit_button("Save details"):
            owner.name, owner.phone = name, phone
            owner.email, owner.address = email, address
            owner.validate()
            st.success("Saved.")
    return owner


def contact_form(contact: Contact | None, label: str) -> Contact | None:
    """Reusable name/phone/email form for emergency contact, vet and groomer."""
    kind = {"Emergency contact": Contact, "Vet clinic": VetClinic, "Groomer": Groomer}
    cls = kind.get(label, Contact)
    current = contact or cls()
    with st.form(f"contact_{label}"):
        st.markdown(f"**{label}**")
        col1, col2 = st.columns(2)
        name = col1.text_input("Name", value=current.name, key=f"{label}_name")
        phone = col2.text_input("Phone", value=current.phone, key=f"{label}_phone")
        email = st.text_input("Email", value=current.email, key=f"{label}_email")
        extra = {}
        if cls is VetClinic:
            col3, col4 = st.columns(2)
            extra["clinic_name"] = col3.text_input("Clinic name", value=current.clinic_name)
            extra["hours"] = col4.text_input("Hours (HH:MM-HH:MM)", value=current.hours)
            extra["is_emergency"] = st.checkbox("24h emergency clinic", value=current.is_emergency)
        if cls is Groomer:
            extra["salon_name"] = st.text_input("Salon", value=current.salon_name)
        if st.form_submit_button(f"Save {label.lower()}"):
            made = cls(name=name, phone=phone, email=email, **extra)
            made.validate()
            return made
    return None


def contact_card(contact: Contact | None, label: str) -> None:
    """Read-only contact block with a tappable phone link; empty state if None."""
    if contact is None or not contact.name:
        empty_state(f"No {label.lower()} saved yet.")
        return
    line = f"**{label}** — {contact.name}"
    if contact.has_phone():
        line += f" · [{contact.formatted_phone()}]({contact.tel_link()})"
    if contact.email:
        line += f" · {contact.email}"
    st.markdown(line)


def pet_form(pet: Pet | None = None) -> Pet | None:
    """Add/edit pet: name, species, breed, sex, DOB, weight, microchip, insurance."""
    current = pet or Pet()
    with st.form("pet_form"):
        col1, col2, col3 = st.columns(3)
        name = col1.text_input("Pet name", value=current.name)
        species = _pick(Species, "Species", current.species, "pet_species")
        breed = col3.text_input("Breed", value=current.breed)

        col4, col5, col6 = st.columns(3)
        sex = _pick(Sex, "Sex", current.sex, "pet_sex")
        dob = col5.date_input(
            "Date of birth",
            value=current.date_of_birth or date.today(),
            max_value=date.today(),
        )
        weight = col6.number_input("Weight (kg)", 0.0, 120.0, float(current.weight_kg), 0.1)

        col7, col8 = st.columns(2)
        energy = _pick(EnergyLevel, "Energy level", current.energy_level, "pet_energy")
        microchip = col8.text_input("Microchip ID", value=current.microchip_id)

        col9, col10 = st.columns(2)
        insurer = col9.text_input("Insurance provider", value=current.insurance_provider)
        policy = col10.text_input("Policy number", value=current.insurance_policy_no)
        neutered = st.checkbox("Neutered / spayed", value=current.is_neutered)

        if st.form_submit_button("Save pet"):
            current.name, current.species, current.breed = name, species, breed
            current.sex, current.date_of_birth, current.weight_kg = sex, dob, weight
            current.energy_level, current.microchip_id = energy, microchip
            current.insurance_provider, current.insurance_policy_no = insurer, policy
            current.is_neutered = neutered
            current.validate()
            return current
    return None


def pet_profile_header(pet: Pet) -> None:
    """Name, age, breed and health badges at the top of the pet's page."""
    st.markdown(f"## {pet.name}")
    bits = [pet.species.value, pet.breed, pet.age_label()]
    if pet.weight_kg:
        bits.append(f"{pet.weight_kg} kg")
    st.caption(" · ".join(b for b in bits if b))
    col1, col2, col3 = st.columns(3)
    col1.metric("Daily activity target", f"{pet.daily_exercise_need()} min")
    col2.metric("Total spent", format_money(pet.total_spent()))
    col3.metric("Outstanding", format_money(pet.outstanding_total()))
    st.caption(pet.medical.summary_line())


def pet_picker(owner: Owner) -> Pet | None:
    """Selectbox over the owner's pets; None means 'whole household'."""
    if not owner.pets:
        return None
    options = ["Whole household"] + [p.name for p in owner.pets]
    choice = st.selectbox("Plan for", options, key="pet_picker")
    return None if choice == "Whole household" else owner.find_pet_by_name(choice)


def task_form(pet: Pet, task: CareTask | None = None) -> CareTask | None:
    """Add/edit task form; swaps extra fields based on the chosen category."""
    current = task or CareTask()
    with st.form(f"task_form_{pet.id}_{current.id}"):
        col1, col2, col3 = st.columns(3)
        title = col1.text_input("Task title", value=current.title or "Morning walk")
        category = _pick(TaskCategory, "Category", current.category, f"cat_{current.id}")
        duration = col3.number_input("Duration (min)", 1, 480, current.duration_minutes)

        col4, col5, col6 = st.columns(3)
        priority = _pick(Priority, "Priority", current.priority, f"pri_{current.id}")
        recurrence = _pick(Recurrence, "Repeats", current.recurrence, f"rec_{current.id}")
        preferred = _pick(TimeOfDay, "Preferred time", current.preferred_time, f"tod_{current.id}")

        weekdays: set[int] = set(current.weekdays)
        if recurrence is Recurrence.WEEKLY:
            picked = st.multiselect(
                "On which days",
                WEEKDAY_NAMES,
                default=[WEEKDAY_NAMES[d] for d in sorted(weekdays)] or ["Mon"],
            )
            weekdays = {WEEKDAY_NAMES.index(d) for d in picked}

        use_fixed = st.checkbox("Fixed time", value=current.is_anchored())
        fixed = st.time_input("At", value=current.fixed_time or time(8, 0)) if use_fixed else None
        notes = st.text_input("Notes", value=current.notes)

        if st.form_submit_button("Save task"):
            built = make_task(
                category,
                title=title,
                duration_minutes=int(duration),
                priority=priority,
                recurrence=recurrence,
                weekdays=weekdays,
                preferred_time=preferred,
                fixed_time=fixed,
                notes=notes,
            )
            built.validate()
            return built
    return None


def task_table(pet: Pet) -> str | None:
    """List a pet's tasks with edit/delete buttons; returns an id to act on."""
    if not pet.tasks:
        empty_state("No tasks yet. Add one above.")
        return None
    to_delete = None
    for task in pet.tasks:
        col1, col2, col3, col4 = st.columns([5, 2, 2, 1])
        col1.markdown(f"{task.icon()} **{task.title}**")
        col2.caption(format_duration(task.duration_minutes))
        col3.caption(f"{task.priority.label} · {task.recurrence.value}")
        if col4.button("Delete", key=f"del_{task.id}"):
            to_delete = task.id
    return to_delete


def constraints_sidebar(prefs: OwnerPreferences) -> OwnerPreferences:
    """Sidebar controls for wake/sleep, budget, breaks and strategy choice."""
    with st.sidebar:
        st.header("Your day")
        prefs.wake_time = st.time_input("Wake time", value=prefs.wake_time)
        prefs.sleep_time = st.time_input("Sleep time", value=prefs.sleep_time)
        prefs.available_minutes = st.slider(
            "Minutes you can spend on pet care", 15, 600, prefs.available_minutes, 15
        )
        prefs.break_minutes = st.slider("Break between tasks", 0, 30, prefs.break_minutes, 5)
        prefs.strategy = _pick(StrategyName, "Scheduling strategy", prefs.strategy, "strategy")
        prefs.currency = st.selectbox(
            "Currency",
            ["USD", "EUR", "GBP", "INR", "CAD", "AUD"],
            index=["USD", "EUR", "GBP", "INR", "CAD", "AUD"].index(prefs.currency)
            if prefs.currency in ["USD", "EUR", "GBP", "INR", "CAD", "AUD"]
            else 0,
        )
    return prefs


def plan_table(plan: DailyPlan) -> None:
    """Render the generated schedule as a time-ordered table with icons."""
    if plan.is_empty():
        empty_state("Nothing could be scheduled. Try raising your available minutes.")
        return
    rows = [
        {
            "Time": item.time_label(),
            "Pet": item.pet.name if item.pet else "",
            "Task": f"{item.task.icon()} {item.task.title}",
            "Duration": format_duration(item.duration()),
            "Priority": item.task.priority.label,
        }
        for item in plan.scheduled
        if item.task
    ]
    st.dataframe(rows, width="stretch", hide_index=True)


def plan_reasoning(plan: DailyPlan) -> None:
    """Show the explanation text and the per-task 'why' in an expander."""
    from pawpal.scheduling.explain import explain_plan

    with st.expander("Why this plan?", expanded=True):
        st.markdown(explain_plan(plan).replace("\n", "  \n"))
    with st.expander("Reason for each task"):
        for item in plan.scheduled:
            if item.task:
                st.markdown(f"**{item.time_label()} {item.task.title}** — {item.reason}")


def skipped_panel(plan: DailyPlan) -> None:
    """List dropped tasks with reasons, warning loudly on meds and feeding."""
    from pawpal.scheduling.explain import warnings_for

    if not plan.skipped:
        return
    loud = {id(w) for w in warnings_for(plan)}
    st.subheader("Not scheduled")
    for drop in plan.skipped:
        text = f"**{drop.task.title}** — {drop.reason}" if drop.task else drop.reason
        st.error(text) if id(drop) in loud else st.caption(text)


def metrics_row(plan: DailyPlan, budget_minutes: int) -> None:
    """Top-line st.metric row: tasks placed, minutes used, utilization."""
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Tasks scheduled", len(plan.scheduled))
    col2.metric("Time booked", format_duration(plan.total_minutes()))
    col3.metric("Budget used", f"{plan.utilization(budget_minutes) * 100:.0f}%")
    col4.metric("Skipped", len(plan.skipped))


def progress_tracker(plan: DailyPlan) -> list[str]:
    """Checkboxes to mark tasks done; returns the ids checked this run."""
    if plan.is_empty():
        return []
    st.progress(plan.completion_rate(), text=f"{plan.completion_rate() * 100:.0f}% complete")
    done = []
    for item in plan.scheduled:
        if item.task is None:
            continue
        label = f"{item.time_label()} — {item.task.title}"
        if st.checkbox(label, value=item.task.is_completed, key=f"done_{item.task.id}"):
            done.append(item.task.id)
    return done


def export_buttons(plan: DailyPlan) -> None:
    """Download .txt / copy-markdown buttons for the finished plan."""
    col1, col2 = st.columns(2)
    col1.download_button("Download plan (.txt)", plan.to_text(), file_name="pawpal_plan.txt")
    col2.download_button("Download plan (.md)", plan.to_markdown(), file_name="pawpal_plan.md")


def empty_state(message: str) -> None:
    """Consistent st.info placeholder used wherever a list is empty."""
    st.info(message)


# --------------------------------------------------------------------- health
def health_banner(pet: Pet) -> None:
    """Red/amber alerts: severe allergies, overdue boosters, pending follow-ups."""
    alerts = pet.health_alerts(date.today())
    if not alerts:
        st.success("No outstanding health items.")
        return
    for alert in alerts:
        st.warning(alert) if "Severe" not in alert else st.error(alert)


def condition_form(condition: Condition | None = None) -> Condition | None:
    """Add/edit a diagnosed condition with status and severity."""
    current = condition or Condition()
    with st.form("condition_form"):
        name = st.text_input("Condition", value=current.name)
        col1, col2, col3 = st.columns(3)
        diagnosed = col1.date_input("Diagnosed on", value=current.diagnosed_on or date.today())
        status = _pick(ConditionStatus, "Status", current.status, "cond_status")
        severity = _pick(Severity, "Severity", current.severity, "cond_sev")
        treatment = st.text_input("Treatment", value=current.treatment)
        if st.form_submit_button("Save condition"):
            made = Condition(
                name=name,
                diagnosed_on=diagnosed,
                status=status,
                severity=severity,
                treatment=treatment,
            )
            made.validate()
            return made
    return None


def allergy_form(allergy: Allergy | None = None) -> Allergy | None:
    """Add/edit an allergy: substance, reaction, severity."""
    current = allergy or Allergy()
    with st.form("allergy_form"):
        col1, col2 = st.columns(2)
        substance = col1.text_input("Substance", value=current.substance)
        reaction = col2.text_input("Reaction", value=current.reaction)
        severity = _pick(Severity, "Severity", current.severity, "allergy_sev")
        if st.form_submit_button("Save allergy"):
            made = Allergy(substance=substance, reaction=reaction, severity=severity)
            made.validate()
            return made
    return None


def vaccination_form(vaccination: Vaccination | None = None) -> Vaccination | None:
    """Log a shot with its given and next-due dates."""
    current = vaccination or Vaccination()
    with st.form("vaccination_form"):
        col1, col2, col3 = st.columns(3)
        name = col1.text_input("Vaccine", value=current.name)
        given = col2.date_input("Given on", value=current.given_on or date.today())
        due = col3.date_input("Next due", value=current.next_due_on or date.today())
        clinic = st.text_input("Clinic", value=current.clinic)
        if st.form_submit_button("Save vaccination"):
            made = Vaccination(name=name, given_on=given, next_due_on=due, clinic=clinic)
            made.validate()
            return made
    return None


def vet_visit_form(visit: VetVisit | None = None) -> VetVisit | None:
    """Log a hospital visit: date, type, clinic, diagnosis, cost, follow-up."""
    current = visit or VetVisit()
    with st.form("visit_form"):
        col1, col2, col3 = st.columns(3)
        when = col1.date_input("Visit date", value=current.visit_date or date.today())
        visit_type = _pick(VisitType, "Type", current.visit_type, "visit_type")
        clinic = col3.text_input("Clinic", value=current.clinic)

        col4, col5 = st.columns(2)
        vet_name = col4.text_input("Vet", value=current.vet_name)
        weight = col5.number_input("Weight at visit (kg)", 0.0, 120.0, float(current.weight_kg), 0.1)

        reason = st.text_input("Reason", value=current.reason)
        diagnosis = st.text_input("Diagnosis", value=current.diagnosis)
        treatment = st.text_input("Treatment", value=current.treatment)

        col6, col7 = st.columns(2)
        wants_follow_up = col6.checkbox("Follow-up needed", value=current.has_follow_up())
        follow_up = col7.date_input("Follow-up on", value=current.follow_up_on or when)
        cost = st.number_input("Cost (0 to skip billing)", 0.0, 100_000.0, 0.0, 10.0)

        if st.form_submit_button("Save visit"):
            made = VetVisit(
                visit_date=when,
                visit_type=visit_type,
                clinic=clinic,
                vet_name=vet_name,
                reason=reason,
                diagnosis=diagnosis,
                treatment=treatment,
                weight_kg=weight,
                follow_up_on=follow_up if wants_follow_up else None,
            )
            made.validate()
            st.session_state["pending_visit_cost"] = cost
            return made
    return None


def medical_timeline(pet: Pet) -> None:
    """Chronological health feed: visits, vaccinations and diagnoses combined."""
    events: list[tuple[date, str]] = []
    for visit in pet.medical.visits:
        if visit.visit_date:
            icon = "\U0001f6a8" if visit.is_emergency() else "\U0001f3e5"
            events.append((visit.visit_date, f"{icon} {visit}"))
    for vaccine in pet.medical.vaccinations:
        if vaccine.given_on:
            events.append((vaccine.given_on, f"\U0001f489 {vaccine.name} given"))
    for condition in pet.medical.conditions:
        if condition.diagnosed_on:
            events.append(
                (condition.diagnosed_on, f"\U0001fa7a Diagnosed: {condition.name}")
            )
    if not events:
        empty_state("No medical history recorded yet.")
        return
    for when, text in sorted(events, reverse=True):
        st.markdown(f"`{when.isoformat()}`  {text}")


def weight_chart(pet: Pet) -> None:
    """Line chart of weights recorded at vet visits over time."""
    history = pet.medical.weight_history()
    if len(history) < 2:
        empty_state("Need at least two weighed visits to chart a trend.")
        return
    st.line_chart({"kg": [w for _, w in history]}, x_label="visit", y_label="kg")


# ------------------------------------------------------------------- grooming
def grooming_form(session: GroomingSession | None = None) -> GroomingSession | None:
    """Log a grooming session: date, provider, services, cost, next due."""
    current = session or GroomingSession()
    with st.form("grooming_form"):
        col1, col2 = st.columns(2)
        when = col1.date_input("Session date", value=current.session_date or date.today())
        provider = col2.text_input("Provider", value=current.provider)
        labels = _labels(GroomingService)
        picked = st.multiselect(
            "Services", labels, default=[s.value.replace("_", " ").title() for s in current.services]
        )
        col3, col4 = st.columns(2)
        duration = col3.number_input("Duration (min)", 1, 480, current.duration_minutes)
        next_due = col4.date_input("Next due", value=current.next_due_on or when)
        cost = st.number_input("Cost (0 to skip billing)", 0.0, 10_000.0, 0.0, 5.0)
        if st.form_submit_button("Save session"):
            made = GroomingSession(
                session_date=when,
                provider=provider,
                services=[list(GroomingService)[labels.index(p)] for p in picked],
                duration_minutes=int(duration),
                next_due_on=next_due,
            )
            made.validate()
            st.session_state["pending_grooming_cost"] = cost
            return made
    return None


def grooming_log(pet: Pet) -> str | None:
    """Table of past sessions with edit/delete; returns an id to act on."""
    if not pet.grooming_sessions:
        empty_state("No grooming sessions logged yet.")
        return None
    to_delete = None
    for session in pet.grooming_sessions:
        col1, col2, col3 = st.columns([6, 2, 1])
        col1.markdown(f"**{session}**")
        col2.caption(format_duration(session.duration_minutes))
        if col3.button("Delete", key=f"delgroom_{session.id}"):
            to_delete = session.id
    return to_delete


def grooming_due_card(pet: Pet) -> None:
    """'Last groomed 47 days ago — due in 3 days' prompt with a Book button."""
    last = pet.last_grooming()
    if last is None:
        empty_state("No grooming history — log a session to start tracking.")
        return
    today = date.today()
    text = f"Last groomed {last.days_since(today)} days ago"
    if last.next_due_on:
        days = (last.next_due_on - today).days
        text += f" · {'overdue by ' + str(abs(days)) if days < 0 else 'due in ' + str(days)} days"
    interval = pet.grooming_interval_days()
    if interval:
        text += f" · usual interval {interval} days"
    st.warning(text) if pet.grooming_due(today) else st.info(text)


# ---------------------------------------------------------------------- money
def bill_form(bill: Bill | None = None) -> Bill | None:
    """Add/edit a cost: description, category, amount, status, invoice ref."""
    current = bill or Bill()
    with st.form("bill_form"):
        col1, col2, col3 = st.columns(3)
        description = col1.text_input("Description", value=current.description)
        category = _pick(BillCategory, "Category", current.category, "bill_cat")
        amount = col3.number_input("Amount", 0.0, 100_000.0, float(current.amount), 5.0)

        col4, col5, col6 = st.columns(3)
        billed = col4.date_input("Billed on", value=current.billed_on or date.today())
        status = _pick(PaymentStatus, "Status", current.status, "bill_status")
        paid = col6.number_input("Amount paid", 0.0, 100_000.0, float(current.amount_paid), 5.0)

        col7, col8 = st.columns(2)
        provider = col7.text_input("Provider", value=current.provider)
        reimbursed = col8.number_input(
            "Insurance reimbursed", 0.0, 100_000.0, float(current.reimbursed_amount), 5.0
        )
        if st.form_submit_button("Save bill"):
            made = Bill(
                description=description,
                category=category,
                amount=amount,
                billed_on=billed,
                status=status,
                amount_paid=paid,
                provider=provider,
                reimbursed_amount=reimbursed,
                insurance_claimed=reimbursed > 0,
            )
            made.validate()
            return made
    return None


def bills_table(pet: Pet) -> str | None:
    """Bills with amount, status and paid-on; returns an id to edit or delete."""
    if not pet.bills:
        empty_state("No bills recorded for this pet.")
        return None
    to_delete = None
    for bill in pet.bills:
        col1, col2, col3, col4 = st.columns([5, 2, 2, 1])
        col1.markdown(f"**{bill.description}**")
        col2.caption(bill.category.value)
        col3.caption(f"{format_money(bill.amount)} · {bill.status.value}")
        if col4.button("Delete", key=f"delbill_{bill.id}"):
            to_delete = bill.id
    return to_delete


def spend_summary(owner: Owner) -> None:
    """Household totals: spend this month, outstanding, and per-pet split."""
    currency = owner.preferences.currency
    bills = owner.all_bills()
    today = date.today()
    col1, col2, col3 = st.columns(3)
    col1.metric("Total spent", format_money(expenses.total_spend(bills), currency))
    col2.metric("Outstanding", format_money(owner.outstanding_total(), currency))
    col3.metric(
        "Projected / year", format_money(expenses.projected_annual(bills, today), currency)
    )
    per_pet = expenses.spend_by_pet(owner)
    if per_pet:
        st.caption(" · ".join(f"{n}: {format_money(v, currency)}" for n, v in per_pet.items()))


def spend_charts(owner: Owner) -> None:
    """Category breakdown and monthly trend charts for the Expenses tab."""
    bills = owner.all_bills()
    if not bills:
        empty_state("No bills yet — add one on a pet's Costs tab.")
        return
    by_category = {k.value: v for k, v in expenses.spend_by_category(bills).items()}
    by_month = expenses.spend_by_month(bills)
    col1, col2 = st.columns(2)
    with col1:
        st.caption("By category")
        st.bar_chart(by_category)
    with col2:
        st.caption("By month")
        st.bar_chart(by_month)


def outstanding_panel(owner: Owner) -> None:
    """Unpaid and overdue bills with a 'Mark paid' action on each row."""
    currency = owner.preferences.currency
    unpaid = expenses.outstanding_bills(owner)
    if not unpaid:
        st.success("Everything is paid up.")
        return
    overdue_ids = {b.id for b in expenses.overdue_bills(owner, date.today())}
    for bill in unpaid:
        col1, col2, col3 = st.columns([5, 2, 2])
        label = f"**{bill.description}** — {format_money(bill.outstanding(), currency)} due"
        col1.error(label) if bill.id in overdue_ids else col1.markdown(label)
        col2.caption(bill.provider or bill.category.value)
        if col3.button("Mark paid", key=f"pay_{bill.id}"):
            bill.mark_paid(date.today())
            st.rerun()
