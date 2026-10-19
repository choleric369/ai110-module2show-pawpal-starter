"""PawPal+ — Streamlit entry point.

Layout and wiring only. Every decision lives in the pawpal package so the
logic can be tested without a browser; this file just draws it.
"""

from datetime import date

import streamlit as st

from pawpal.models.preferences import DayConstraints
from pawpal.models.records import Bill
from pawpal.models.enums import BillCategory
from pawpal.scheduling.scheduler import Scheduler
from pawpal.scheduling.strategies import get_strategy
from pawpal.services import reminders, storage
from pawpal.utils.validation import PawPalError
from ui import components as ui

st.set_page_config(page_title="PawPal+", page_icon="\U0001f43e", layout="wide")

ui.init_session(storage.load_state())
owner = st.session_state.owner
today = date.today()

st.title("\U0001f43e PawPal+")
st.caption("Pet care planning, health records, grooming and costs — all in one place.")

owner.preferences = ui.constraints_sidebar(owner.preferences)
with st.sidebar:
    st.divider()
    if st.button("Save to disk", width="stretch"):
        try:
            path = storage.save_state(owner)
            st.success(f"Saved to {path}")
        except PawPalError as exc:
            st.error(str(exc))
    if st.button("Reload from disk", width="stretch"):
        st.session_state.owner = storage.load_state()
        st.rerun()

plan_tab, pets_tab, health_tab, groom_tab, money_tab, owner_tab = st.tabs(
    ["Today's plan", "Pets & tasks", "Health", "Grooming", "Costs", "Owner"]
)

# --------------------------------------------------------------- today's plan
with plan_tab:
    if not owner.pets:
        ui.empty_state("Add a pet on the 'Pets & tasks' tab to get started.")
    else:
        target = ui.pet_picker(owner)
        include = st.toggle(
            "Include reminders from records",
            value=True,
            help="Vet follow-ups, due boosters and overdue grooming become tasks.",
        )
        if st.button("Generate schedule", type="primary"):
            try:
                owner.preferences.validate()
                scheduler = Scheduler(
                    DayConstraints.from_preferences(owner.preferences),
                    get_strategy(owner.preferences.strategy, owner.preferences.priority_weights),
                )
                st.session_state.plan = scheduler.build_plan(owner, today, target, include)
            except PawPalError as exc:
                st.error(str(exc))

        plan = st.session_state.plan
        if plan is None:
            ui.empty_state("Press **Generate schedule** to build today's plan.")
        else:
            ui.metrics_row(plan, owner.preferences.available_minutes)
            ui.plan_table(plan)
            ui.plan_reasoning(plan)
            ui.skipped_panel(plan)
            for warning in plan.unmet_needs():
                st.warning(warning)
            st.divider()
            st.subheader("Mark off as you go")
            done = set(ui.progress_tracker(plan))
            for item in plan.scheduled:
                if item.task:
                    item.task.is_completed = item.task.id in done
            ui.export_buttons(plan)
            if st.button("Log this day to history"):
                storage.append_history(plan)
                st.success("Saved to history.")

# ---------------------------------------------------------------- pets & tasks
with pets_tab:
    st.subheader("Add or edit a pet")
    new_pet = ui.pet_form()
    if new_pet is not None:
        try:
            if not owner.get_pet(new_pet.id):
                owner.add_pet(new_pet)
            st.success(f"Saved {new_pet.name}.")
        except PawPalError as exc:
            st.error(str(exc))

    st.divider()
    for pet in owner.pets:
        with st.expander(f"{pet.name} — {len(pet.tasks)} tasks", expanded=False):
            ui.pet_profile_header(pet)
            st.markdown("#### Tasks")
            removed = ui.task_table(pet)
            if removed:
                pet.remove_task(removed)
                st.rerun()
            st.markdown("#### Add a task")
            made = ui.task_form(pet)
            if made is not None:
                pet.add_task(made)
                st.rerun()
            if st.button(f"Remove {pet.name}", key=f"rmpet_{pet.id}"):
                owner.remove_pet(pet.id)
                st.rerun()

# ---------------------------------------------------------------------- health
with health_tab:
    if not owner.pets:
        ui.empty_state("Add a pet first.")
    else:
        names = [p.name for p in owner.pets]
        pet = owner.find_pet_by_name(st.selectbox("Pet", names, key="health_pet"))
        ui.health_banner(pet)
        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("#### Timeline")
            ui.medical_timeline(pet)
            st.markdown("#### Weight")
            ui.weight_chart(pet)
        with col2:
            st.markdown("#### Log a vet visit")
            visit = ui.vet_visit_form()
            if visit is not None:
                cost = st.session_state.pop("pending_visit_cost", 0.0)
                if cost:
                    bill = Bill(
                        description=f"Vet visit: {visit.reason or visit.visit_type.value}",
                        category=BillCategory.VET,
                        amount=cost,
                        billed_on=visit.visit_date,
                        provider=visit.clinic,
                        linked_record_id=visit.id,
                    )
                    pet.add_bill(bill)
                    visit.bill_id = bill.id
                pet.medical.add_visit(visit)
                st.rerun()
            st.markdown("#### Log a vaccination")
            vaccine = ui.vaccination_form()
            if vaccine is not None:
                pet.medical.add_vaccination(vaccine)
                st.rerun()
            st.markdown("#### Record a condition")
            condition = ui.condition_form()
            if condition is not None:
                pet.medical.add_condition(condition)
                st.rerun()
            st.markdown("#### Record an allergy")
            allergy = ui.allergy_form()
            if allergy is not None:
                pet.medical.add_allergy(allergy)
                st.rerun()

# -------------------------------------------------------------------- grooming
with groom_tab:
    if not owner.pets:
        ui.empty_state("Add a pet first.")
    else:
        names = [p.name for p in owner.pets]
        pet = owner.find_pet_by_name(st.selectbox("Pet", names, key="groom_pet"))
        ui.grooming_due_card(pet)
        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("#### Session log")
            removed = ui.grooming_log(pet)
            if removed:
                pet.remove_grooming_session(removed)
                st.rerun()
        with col2:
            st.markdown("#### Log a session")
            session = ui.grooming_form()
            if session is not None:
                cost = st.session_state.pop("pending_grooming_cost", 0.0)
                if cost:
                    bill = Bill(
                        description=f"Grooming: {', '.join(session.service_labels())}",
                        category=BillCategory.GROOMING,
                        amount=cost,
                        billed_on=session.session_date,
                        provider=session.provider,
                        linked_record_id=session.id,
                    )
                    pet.add_bill(bill)
                    session.bill_id = bill.id
                pet.add_grooming_session(session)
                st.rerun()

# ----------------------------------------------------------------------- costs
with money_tab:
    ui.spend_summary(owner)
    st.divider()
    ui.spend_charts(owner)
    st.divider()
    st.subheader("Outstanding")
    ui.outstanding_panel(owner)
    st.divider()
    if owner.pets:
        names = [p.name for p in owner.pets]
        pet = owner.find_pet_by_name(st.selectbox("Pet", names, key="money_pet"))
        st.markdown("#### Bills")
        removed = ui.bills_table(pet)
        if removed:
            pet.remove_bill(removed)
            st.rerun()
        st.markdown("#### Add a bill")
        bill = ui.bill_form()
        if bill is not None:
            pet.add_bill(bill)
            st.rerun()
        for nudge in reminders.bill_reminders(pet, today):
            st.warning(nudge)

# ----------------------------------------------------------------------- owner
with owner_tab:
    owner = ui.owner_form(owner)
    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        ui.contact_card(owner.emergency_contact, "Emergency contact")
        made = ui.contact_form(owner.emergency_contact, "Emergency contact")
        if made is not None:
            owner.emergency_contact = made
            st.rerun()
    with col2:
        ui.contact_card(owner.preferred_vet, "Vet clinic")
        made = ui.contact_form(owner.preferred_vet, "Vet clinic")
        if made is not None:
            owner.preferred_vet = made
            st.rerun()

st.session_state.owner = owner
