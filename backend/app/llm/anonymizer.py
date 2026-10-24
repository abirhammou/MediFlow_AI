import re

_EMAIL = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
_PHONE = re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)")
_NIR = re.compile(r"\b[12]\s?\d{2}\s?\d{2}\s?\d{2}\s?\d{3}\s?\d{3}\s?\d{2}\b")


def anonymize(text: str) -> str:
    text = _EMAIL.sub("[EMAIL]", text)
    text = _NIR.sub("[IDENTIFIANT]", text)
    return _PHONE.sub("[TÉLÉPHONE]", text)
