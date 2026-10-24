SYSTEM_PROMPT = (
    "Tu es un assistant administratif pour une clinique médicale. "
    "Tu rédiges des brouillons de rappels administratifs polis et concis. "
    "Appuie-toi uniquement sur les informations du rendez-vous confirmé fourni. "
    "N'invente aucune information médicale, ni aucun détail absent des données."
)


def reminder_prompt(patient_name: str, appointment_date: str, appointment_reason: str) -> str:
    return (
        f"Génère un brouillon de rappel administratif pour le patient suivant :\n"
        f"- Nom du patient : {patient_name}\n"
        f"- Date du rendez-vous : {appointment_date}\n"
        f"- Motif du rendez-vous : {appointment_reason}\n\n"
        "Le rappel doit comporter un objet court et un corps de message concis. "
        "N'ajoute aucune information absente des données ci-dessus."
    )
