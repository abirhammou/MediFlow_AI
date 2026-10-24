"""API schemas of the patients module.

JSON is camelCase (`firstName`). Input models only accept the fields a client
may write: `recordNumber`, `createdBy`, timestamps, `deletedAt` and
`currentSummaryId` are set by the server, and sending them is a 422.
Validation messages are in French, including Pydantic's built-in ones.
"""

import re
from collections.abc import Callable
from datetime import date, datetime
from typing import Annotated, Any, Generic, Self, TypeVar

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    ModelWrapValidatorHandler,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic.alias_generators import to_camel
from pydantic_core import InitErrorDetails, PydanticCustomError

from app.modules.auth.models import EMAIL_PATTERN
from app.modules.patients.dates import age_on, clinic_today, from_mongo_date, years_before
from app.modules.patients.models import (
    Address,
    BloodType,
    EmergencyContact,
    Gender,
    Insurance,
    Patient,
)

T = TypeVar("T")

MAX_AGE_YEARS = 130
NATIONAL_ID_PATTERN = r"^[0-9]{8}$"
PHONE_PATTERN = r"^[0-9 +]{8,20}$"

REQUIRED_MESSAGE = "Ce champ est obligatoire."
# French messages for Pydantic's built-in error types (custom errors already are).
BUILTIN_MESSAGES = {
    "missing": REQUIRED_MESSAGE,
    "extra_forbidden": "Champ non autorisé.",
    "enum": "Valeur non autorisée.",
    "string_type": "Texte attendu.",
    "model_type": "Objet attendu.",
    "model_attributes_type": "Objet attendu.",
    "date_type": "Date invalide (format AAAA-MM-JJ).",
    "date_parsing": "Date invalide (format AAAA-MM-JJ).",
    "date_from_datetime_parsing": "Date invalide (format AAAA-MM-JJ).",
    "date_from_datetime_inexact": "Date invalide (format AAAA-MM-JJ).",
}


def _french_error(error: Any) -> InitErrorDetails:
    error_type = error["type"]
    if error["input"] is None and error_type.endswith("_type"):
        message = REQUIRED_MESSAGE
    else:
        message = BUILTIN_MESSAGES.get(error_type, error["msg"])
    return {
        "type": PydanticCustomError(error_type, message),
        "loc": error["loc"],
        "input": error["input"],
    }


# ---------------------------------------------------------------------
# Field types
# ---------------------------------------------------------------------


def _clean_text(value: Any) -> Any:
    """Trim strings; an empty string means "no value"."""
    if isinstance(value, str):
        return value.strip() or None
    return value


def _clean_email(value: Any) -> Any:
    value = _clean_text(value)
    return value.lower() if isinstance(value, str) else value


def _check(predicate: Callable[[str], bool], code: str, message: str) -> AfterValidator:
    def validate(value: str | None) -> str | None:
        if value is not None and not predicate(value):
            raise PydanticCustomError(code, message)
        return value

    return AfterValidator(validate)


def _max_length(limit: int) -> AfterValidator:
    return _check(lambda value: len(value) <= limit, "too_long", f"{limit} caractères maximum.")


def _matches(pattern: str, message: str) -> AfterValidator:
    compiled = re.compile(pattern)
    return _check(lambda value: compiled.fullmatch(value) is not None, "invalid_format", message)


def _empty_to_none(value: BaseModel | None) -> BaseModel | None:
    """A nested object without any value is stored as null."""
    if value is not None and not value.model_dump(exclude_none=True):
        return None
    return value


Clean = BeforeValidator(_clean_text)
Name = Annotated[str | None, Clean, _max_length(80)]
Phone = Annotated[
    str | None,
    Clean,
    _matches(PHONE_PATTERN, "Téléphone invalide : 8 à 20 caractères (chiffres, espaces, +)."),
]
NationalId = Annotated[
    str | None, Clean, _matches(NATIONAL_ID_PATTERN, "Le CIN doit contenir exactement 8 chiffres.")
]
Email = Annotated[
    str | None,
    BeforeValidator(_clean_email),
    _max_length(254),
    _matches(EMAIL_PATTERN, "Adresse email invalide."),
]
Notes = Annotated[str | None, Clean, _max_length(5000)]
BirthDate = Annotated[date | None, Clean]
GenderValue = Annotated[Gender | None, Clean]
BloodTypeValue = Annotated[BloodType | None, Clean]
Text20 = Annotated[str | None, Clean, _max_length(20)]
Text50 = Annotated[str | None, Clean, _max_length(50)]
Text100 = Annotated[str | None, Clean, _max_length(100)]
Text200 = Annotated[str | None, Clean, _max_length(200)]


# ---------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------


class InputModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        validate_by_alias=True,
        validate_by_name=False,
        extra="forbid",
    )

    @model_validator(mode="wrap")
    @classmethod
    def _french_messages(cls, data: Any, handler: ModelWrapValidatorHandler[Self]) -> Self:
        try:
            return handler(data)
        except ValidationError as exc:
            errors = [_french_error(error) for error in exc.errors()]
            raise ValidationError.from_exception_data(exc.title, errors) from None


class AddressIn(InputModel):
    street: Text200 = None
    city: Text100 = None
    postal_code: Text20 = None


class InsuranceIn(InputModel):
    provider: Text100 = None
    number: Text50 = None


class EmergencyContactIn(InputModel):
    name: Text200 = None
    phone: Phone = None
    relation: Text50 = None


class PatientUpdate(InputModel):
    """PATCH body: only the fields sent are changed; `null` clears an optional field."""

    first_name: Name = None
    last_name: Name = None
    date_of_birth: BirthDate = None
    gender: GenderValue = None
    national_id: NationalId = None
    phone: Phone = None
    email: Email = None
    address: Annotated[AddressIn | None, AfterValidator(_empty_to_none)] = None
    blood_type: BloodTypeValue = None
    insurance: Annotated[InsuranceIn | None, AfterValidator(_empty_to_none)] = None
    emergency_contact: Annotated[EmergencyContactIn | None, AfterValidator(_empty_to_none)] = None
    administrative_notes: Notes = None

    # Field validators only run on values that were sent, never on defaults.
    @field_validator("first_name", "last_name", "date_of_birth", "gender")
    @classmethod
    def _not_null(cls, value: Any) -> Any:
        if value is None:
            raise PydanticCustomError("required", REQUIRED_MESSAGE)
        return value

    @field_validator("date_of_birth")
    @classmethod
    def _plausible_birth_date(cls, value: date | None) -> date | None:
        if value is None:
            return value
        today = clinic_today()
        if value > today:
            raise PydanticCustomError(
                "birth_date_in_future", "La date de naissance ne peut pas être dans le futur."
            )
        if value < years_before(today, MAX_AGE_YEARS):
            raise PydanticCustomError(
                "birth_date_too_old",
                f"La date de naissance ne peut pas remonter à plus de {MAX_AGE_YEARS} ans.",
            )
        return value


class PatientCreate(PatientUpdate):
    first_name: Name
    last_name: Name
    date_of_birth: BirthDate
    gender: GenderValue


# ---------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------


class OutputModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class Page(OutputModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    size: int


class PatientListItem(OutputModel):
    id: str
    record_number: str
    first_name: str
    last_name: str
    date_of_birth: date
    age: int
    gender: Gender
    phone: str | None = None
    city: str | None = None


class DeletedPatientItem(PatientListItem):
    deleted_at: datetime


class PatientOut(OutputModel):
    id: str
    record_number: str
    first_name: str
    last_name: str
    date_of_birth: date
    age: int
    gender: Gender
    national_id: str | None
    phone: str | None
    email: str | None
    address: Address | None
    blood_type: BloodType | None
    insurance: Insurance | None
    emergency_contact: EmergencyContact | None
    administrative_notes: str | None
    current_summary_id: str | None
    created_by: str | None
    updated_by: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_patient(cls, patient: Patient) -> "PatientOut":
        birth_date = from_mongo_date(patient.date_of_birth)
        return cls(
            id=str(patient.id),
            record_number=patient.record_number,
            first_name=patient.first_name,
            last_name=patient.last_name,
            date_of_birth=birth_date,
            age=age_on(birth_date, clinic_today()),
            gender=patient.gender,
            national_id=patient.national_id,
            phone=patient.phone,
            email=patient.email,
            address=patient.address,
            blood_type=patient.blood_type,
            insurance=patient.insurance,
            emergency_contact=patient.emergency_contact,
            administrative_notes=patient.administrative_notes,
            current_summary_id=_str_or_none(patient.current_summary_id),
            created_by=_str_or_none(patient.created_by),
            updated_by=_str_or_none(patient.updated_by),
            created_at=patient.created_at,
            updated_at=patient.updated_at,
        )


def _str_or_none(value: object | None) -> str | None:
    return None if value is None else str(value)
