SYSTEM_PROMPT = (
    "Tu résumes des notes de démonstration. N'ajoute aucune information absente du texte."
)


def summary_prompt(content: str) -> str:
    return f"Résume cette note de façon concise :\n{content}"
