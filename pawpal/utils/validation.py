"""Input guards and the exception hierarchy.

Models raise these from validate(); the Streamlit layer catches PawPalError and
shows st.error() instead of a traceback.
"""

import re

PHONE_MIN_DIGITS = 7
PHONE_MAX_DIGITS = 15
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class PawPalError(Exception):
    """Base class so the UI can catch every PawPal failure with one except."""


class ValidationError(PawPalError):
    """Bad user input: empty name, zero duration, sleep before wake, etc."""


class SchedulingError(PawPalError):
    """The scheduler could not produce a plan at all (e.g. impossible constraints)."""


class StorageError(PawPalError):
    """A JSON save/load failed or the file was malformed."""


def require_non_empty(value: str, field_name: str) -> str:
    """Return the stripped string, or raise ValidationError if it is blank."""
    text = (value or "").strip()
    if not text:
        raise ValidationError(f"{field_name} cannot be empty.")
    return text


def require_positive_int(value: int, field_name: str, maximum: int | None = None) -> int:
    """Return value if it is a positive int within maximum, else raise ValidationError."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{field_name} must be a whole number.") from None
    if number < 1:
        raise ValidationError(f"{field_name} must be at least 1 (got {number}).")
    if maximum is not None and number > maximum:
        raise ValidationError(f"{field_name} cannot exceed {maximum} (got {number}).")
    return number


def require_in_range(value: float, field_name: str, low: float, high: float) -> float:
    """Return value if low <= value <= high, else raise ValidationError."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{field_name} must be a number.") from None
    if not low <= number <= high:
        raise ValidationError(f"{field_name} must be between {low} and {high} (got {number}).")
    return number


def require_non_negative(value: float, field_name: str) -> float:
    """Return value if it is zero or positive, else raise ValidationError."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{field_name} must be a number.") from None
    if number < 0:
        raise ValidationError(f"{field_name} cannot be negative (got {number}).")
    return number


def digits_only(value: str) -> str:
    """Strip a phone number down to its digits, keeping nothing else."""
    return re.sub(r"\D", "", value or "")


def is_plausible_phone(value: str) -> bool:
    """True if the string holds a believable number of digits for a phone."""
    return PHONE_MIN_DIGITS <= len(digits_only(value)) <= PHONE_MAX_DIGITS


def require_phone(value: str, field_name: str = "Phone") -> str:
    """Return the phone unchanged if plausible; blank is allowed, junk is not."""
    if not (value or "").strip():
        return ""
    if not is_plausible_phone(value):
        raise ValidationError(f"{field_name} does not look like a phone number: {value!r}")
    return value.strip()


def require_email(value: str, field_name: str = "Email") -> str:
    """Return the email if it has a basic user@host.tld shape; blank is allowed."""
    text = (value or "").strip()
    if not text:
        return ""
    if not EMAIL_RE.match(text):
        raise ValidationError(f"{field_name} does not look like an email: {value!r}")
    return text
