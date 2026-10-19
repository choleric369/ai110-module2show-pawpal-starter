"""Owner and clinic contact details."""

import pytest

from pawpal.models.contact import Contact, Groomer, VetClinic, contact_from_dict
from pawpal.utils.validation import ValidationError


def test_contact_requires_a_name():
    """A blank name fails validate()."""
    with pytest.raises(ValidationError):
        Contact(name="", phone="5551234567").validate()


def test_implausible_phone_is_rejected():
    """'abc' is not accepted as a phone number."""
    with pytest.raises(ValidationError):
        Contact(name="Riley", phone="abc").validate()


def test_blank_phone_is_allowed():
    """Not every contact has a number on file."""
    contact = Contact(name="Riley")
    contact.validate()
    assert contact.has_phone() is False


def test_bad_email_is_rejected():
    """An email without an @ and a dot is refused."""
    with pytest.raises(ValidationError):
        Contact(name="Riley", email="not-an-email").validate()


def test_phone_formats_consistently():
    """A 10-digit number renders in the grouped display form."""
    assert Contact(name="R", phone="5551234567").formatted_phone() == "(555) 123-4567"


def test_international_phone_keeps_its_prefix():
    """A leading + survives formatting."""
    assert Contact(name="R", phone="+1 555 0177").formatted_phone().startswith("+")


def test_tel_link_strips_formatting():
    """tel_link() keeps digits and the country code, drops spaces and dashes."""
    assert Contact(name="R", phone="+1 (555) 123-4567").tel_link() == "tel:+15551234567"


def test_tel_link_is_blank_without_a_number():
    """No phone means no link to render."""
    assert Contact(name="R").tel_link() == ""


def test_has_phone_false_when_blank():
    """An empty phone means has_phone() is False."""
    assert not Contact(name="R", phone="   ").has_phone()


def test_owner_contact_card_includes_phone_and_email(owner_with_contacts):
    """contact_card() carries the owner's primary details."""
    card = owner_with_contacts.contact_card()
    assert card.name == "Jordan"
    assert card.phone == "5551234567"
    assert card.relationship == "owner"


def test_vet_clinic_round_trips_as_vet_clinic():
    """A VetClinic loads back as VetClinic, keeping is_emergency."""
    clinic = VetClinic(
        name="Dr. Rao", clinic_name="Bayside", phone="5550177", is_emergency=True
    )
    restored = contact_from_dict(clinic.to_dict())
    assert isinstance(restored, VetClinic)
    assert restored.is_emergency is True
    assert restored.clinic_name == "Bayside"


def test_groomer_round_trips_with_its_fields():
    """Salon name and typical cost survive the round trip."""
    groomer = Groomer(name="Sam", salon_name="Happy Paws", typical_cost=95.0)
    restored = contact_from_dict(groomer.to_dict())
    assert isinstance(restored, Groomer)
    assert restored.typical_cost == 95.0


def test_contact_from_dict_of_none_is_none():
    """An absent contact loads as None, not an empty object."""
    assert contact_from_dict(None) is None


def test_emergency_clinic_is_always_open():
    """A 24h clinic reports open regardless of the hours string."""
    assert VetClinic(name="ER", is_emergency=True).is_open_now()


def test_clinic_with_unparseable_hours_is_not_open():
    """Garbage in the hours field is treated as 'unknown', not 'open'."""
    assert not VetClinic(name="Clinic", hours="whenever").is_open_now()


def test_str_includes_the_number():
    """One-line display pairs the name with the formatted phone."""
    assert "555" in str(Contact(name="Riley", phone="5551234567"))
