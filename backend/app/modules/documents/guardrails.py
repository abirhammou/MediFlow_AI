import re

from app.modules.documents.schemas import ExtractedFieldProposal


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def validate_extracted_fields(
    raw_text: str, fields: list[ExtractedFieldProposal]
) -> tuple[list[ExtractedFieldProposal], list[str]]:
    source = _normalize(raw_text)
    validated: list[ExtractedFieldProposal] = []
    warnings: list[str] = []

    for field in fields:
        value = field.value
        if value is not None and _normalize(value) not in source:
            warnings.append(
                f"La valeur extraite pour « {field.name} » n'apparaît pas dans le document; elle a été remplacée par null."
            )
            value = None
        validated.append(ExtractedFieldProposal(name=field.name, value=value))

    return validated, warnings
