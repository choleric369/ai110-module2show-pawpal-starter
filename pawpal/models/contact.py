"""People and places PawPal+ needs a phone number for.

One Contact type reused for the owner, their emergency contact, the vet clinic
and the groomer — same fields, different roles.
"""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4

from pawpal.utils.validation import (
    digits_only,
    require_email,
    require_non_empty,
    require_phone,
)


@dataclass
class Contact:
    """A reachable human or business: who they are and how to call them."""

    name: str = ""
    phone: str = ""
    email: str = ""
    address: str = ""
    relationship: str = ""
    notes: str = ""
    id: str = field(default_factory=lambda: uuid4().hex[:8])

    def validate(self) -> None:
        """Raise ValidationError on a blank name or a phone that isn't plausible."""
        self.name = require_non_empty(self.name, "Contact name")
        self.phone = require_phone(self.phone, "Contact phone")
        self.email = require_email(self.email, "Contact email")

    def has_phone(self) -> bool:
        """True if a usable number is stored; gates the 'Call' button in the UI."""
        return bool(digits_only(self.phone))

    def formatted_phone(self) -> str:
        """Display form of the number, digits grouped and country code kept."""
        digits = digits_only(self.phone)
        if not digits:
            return ""
        prefix = "+" if self.phone.strip().startswith("+") else ""
        if not prefix and len(digits) == 10:
            return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
        if not prefix and len(digits) == 11 and digits.startswith("1"):
            return f"+1 ({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
        groups = [digits[max(0, i - 3) : i] for i in range(len(digits), 0, -3)][::-1]
        return (prefix + " ".join(groups)).strip()

    def tel_link(self) -> str:
        """'tel:+15551234567' URL so the contact is tappable on mobile."""
        digits = digits_only(self.phone)
        if not digits:
            return ""
        prefix = "+" if self.phone.strip().startswith("+") else ""
        return f"tel:{prefix}{digits}"

    def to_dict(self) -> dict:
        """Serialize to a JSON-safe dict."""
        return {
            "type": type(self).__name__,
            "id": self.id,
            "name": self.name,
            "phone": self.phone,
            "email": self.email,
            "address": self.address,
            "relationship": self.relationship,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Contact":
        """Rebuild this exact class from JSON; use contact_from_dict to dispatch."""
        payload = dict(data or {})
        payload.pop("type", None)
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in payload.items() if k in known})

    def __str__(self) -> str:
        """'Dr. Rao — +1 555 0134' for one-line display."""
        phone = self.formatted_phone()
        return f"{self.name} — {phone}" if phone else self.name


@dataclass
class VetClinic(Contact):
    """A clinic or hospital; emergency ones are pinned to the top of the UI."""

    clinic_name: str = ""
    is_emergency: bool = False
    hours: str = ""

    def is_open_now(self) -> bool:
        """Best-effort check of the stored 'HH:MM-HH:MM' hours; False when unknown."""
        if self.is_emergency:
            return True
        try:
            opens, closes = self.hours.replace(" ", "").split("-")
            now = datetime.now().time()
            open_t = datetime.strptime(opens, "%H:%M").time()
            close_t = datetime.strptime(closes, "%H:%M").time()
        except (ValueError, AttributeError):
            return False
        return open_t <= now <= close_t

    def to_dict(self) -> dict:
        """Serialize, adding the clinic-specific fields."""
        return {
            **super().to_dict(),
            "clinic_name": self.clinic_name,
            "is_emergency": self.is_emergency,
            "hours": self.hours,
        }


@dataclass
class Groomer(Contact):
    """A groomer or salon, linked from each GroomingSession for rebooking."""

    salon_name: str = ""
    typical_cost: float = 0.0

    def to_dict(self) -> dict:
        """Serialize, adding the salon-specific fields."""
        return {
            **super().to_dict(),
            "salon_name": self.salon_name,
            "typical_cost": self.typical_cost,
        }


# Maps the 'type' key written by to_dict() back to the class that wrote it.
CONTACT_TYPES: dict[str, type[Contact]] = {
    "Contact": Contact,
    "VetClinic": VetClinic,
    "Groomer": Groomer,
}


def contact_from_dict(data: dict | None) -> Contact | None:
    """Polymorphic loader: read data['type'] and build the right Contact subclass."""
    if not data:
        return None
    payload = dict(data)
    target = CONTACT_TYPES.get(payload.pop("type", "Contact"), Contact)
    known = set(target.__dataclass_fields__)
    return target(**{k: v for k, v in payload.items() if k in known})
