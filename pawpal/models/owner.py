"""Owner: the root object. Saving the Owner saves the whole app state."""

from dataclasses import dataclass, field
from datetime import date

from pawpal.models.contact import Contact, VetClinic, contact_from_dict
from pawpal.models.pet import Pet
from pawpal.models.preferences import OwnerPreferences
from pawpal.models.records import Bill
from pawpal.models.task import CareTask
from pawpal.utils.validation import (
    ValidationError,
    require_email,
    require_non_empty,
    require_phone,
)


@dataclass
class Owner:
    """The human: contact details, their pets, and their scheduling preferences."""

    # --- primary details ---
    name: str = ""
    phone: str = ""
    email: str = ""
    address: str = ""

    # --- people to call ---
    emergency_contact: Contact | None = None
    preferred_vet: VetClinic | None = None

    # --- app state ---
    pets: list[Pet] = field(default_factory=list)
    preferences: OwnerPreferences = field(default_factory=OwnerPreferences)

    def validate(self) -> None:
        """Raise ValidationError on a blank name, bad phone/email, or bad prefs."""
        self.name = require_non_empty(self.name, "Owner name")
        self.phone = require_phone(self.phone, "Owner phone")
        self.email = require_email(self.email, "Owner email")
        self.preferences.validate()

    def contact_card(self) -> Contact:
        """Package the owner's own details as a Contact for display and export."""
        return Contact(
            name=self.name,
            phone=self.phone,
            email=self.email,
            address=self.address,
            relationship="owner",
        )

    # ------------------------------------------------------------------ pets
    def add_pet(self, pet: Pet) -> None:
        """Validate then add a pet, rejecting a duplicate name."""
        pet.validate()
        if self.find_pet_by_name(pet.name):
            raise ValidationError(f"You already have a pet named {pet.name}.")
        self.pets.append(pet)

    def remove_pet(self, pet_id: str) -> bool:
        """Delete a pet and all of its records; returns False if nothing matched."""
        remaining = [p for p in self.pets if p.id != pet_id]
        if len(remaining) == len(self.pets):
            return False
        self.pets = remaining
        return True

    def get_pet(self, pet_id: str) -> Pet | None:
        """Look up one pet by id, for the pet picker and edit form."""
        return next((p for p in self.pets if p.id == pet_id), None)

    def find_pet_by_name(self, name: str) -> Pet | None:
        """Case-insensitive name lookup, mainly for tests and seed data."""
        key = (name or "").strip().lower()
        return next((p for p in self.pets if p.name.strip().lower() == key), None)

    # ------------------------------------------------------------------ tasks
    def all_tasks(self) -> list[CareTask]:
        """Flatten every pet's tasks into one pool for a household-wide plan."""
        return [task for pet in self.pets for task in pet.tasks]

    def owner_of(self, task_id: str) -> Pet | None:
        """Which pet a task belongs to, so the plan can label each row."""
        return next((p for p in self.pets if p.get_task(task_id)), None)

    # ------------------------------------------------------------------ rollups
    def all_bills(self) -> list[Bill]:
        """Every bill across every pet, for the household spending view."""
        return [bill for pet in self.pets for bill in pet.bills]

    def household_spend(self, start: date | None = None, end: date | None = None) -> float:
        """Total net spend across all pets in a period."""
        return round(sum(pet.total_spent(start, end) for pet in self.pets), 2)

    def outstanding_total(self) -> float:
        """Everything still owed across the household."""
        return round(sum(pet.outstanding_total() for pet in self.pets), 2)

    def health_alerts(self, today: date) -> dict[str, list[str]]:
        """Per-pet health warnings, keyed by pet name, for the dashboard banner."""
        return {
            pet.name: alerts for pet in self.pets if (alerts := pet.health_alerts(today))
        }

    # ------------------------------------------------------------------ io
    def to_dict(self) -> dict:
        """Serialize owner + contacts + pets + preferences; the whole save file."""
        return {
            "name": self.name,
            "phone": self.phone,
            "email": self.email,
            "address": self.address,
            "emergency_contact": (
                self.emergency_contact.to_dict() if self.emergency_contact else None
            ),
            "preferred_vet": self.preferred_vet.to_dict() if self.preferred_vet else None,
            "pets": [pet.to_dict() for pet in self.pets],
            "preferences": self.preferences.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Owner":
        """Rebuild the full object graph from a loaded JSON dict."""
        data = data or {}
        vet = contact_from_dict(data.get("preferred_vet"))
        return cls(
            name=data.get("name", ""),
            phone=data.get("phone", ""),
            email=data.get("email", ""),
            address=data.get("address", ""),
            emergency_contact=contact_from_dict(data.get("emergency_contact")),
            preferred_vet=vet if isinstance(vet, VetClinic) else None,
            pets=[Pet.from_dict(p) for p in data.get("pets", [])],
            preferences=OwnerPreferences.from_dict(data.get("preferences", {})),
        )
