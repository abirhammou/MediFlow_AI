import re

_EMAIL = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
# Numéros de téléphone : avec préfixe + ou avec séparateurs (espaces/tirets/points)
# Exclut les dates ISO comme 2026-10-30 (pattern YYYY-MM-DD)
_DATE_ISO = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_PHONE = re.compile(
    r"(?<!\w)"
    r"(?:"
    r"\+\d{6,15}"                                                      # +21651964422
    r"|\+\d{1,3}[\s.\-()\d]{7,20}"                                    # +216 51 964 422
    r"|0\d(?:[\s.\-]\d{2}){4}"                                        # 06 12 34 56 78
    r")"
    r"(?!\w)"
)
_NIR = re.compile(r"\b[12]\s?\d{2}\s?\d{2}\s?\d{2}\s?\d{3}\s?\d{3}\s?\d{2}\b")


def anonymize(text: str) -> str:
    # Protéger les dates ISO avant l'anonymisation
    placeholders: list[tuple[str, str]] = []
    for i, m in enumerate(_DATE_ISO.finditer(text)):
        placeholder = f"__DATE_{i}__"
        placeholders.append((placeholder, m.group()))

    protected = text
    for placeholder, original in placeholders:
        protected = protected.replace(original, placeholder, 1)

    # Anonymiser
    protected = _EMAIL.sub("[EMAIL]", protected)
    protected = _NIR.sub("[IDENTIFIANT]", protected)
    protected = _PHONE.sub("[TÉLÉPHONE]", protected)

    # Restaurer les dates
    for placeholder, original in placeholders:
        protected = protected.replace(placeholder, original)

    return protected
