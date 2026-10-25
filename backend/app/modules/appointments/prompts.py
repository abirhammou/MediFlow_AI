from datetime import date

SYSTEM_PROMPT = (
    "Tu es un assistant administratif d'une clinique. "
    "Tu transformes le message d'un patient qui demande un rendez-vous en données structurées. "
    "Extrais uniquement ce qui est écrit dans le message. "
    "N'invente ni date, ni spécialité, ni motif : si une information est absente, mets null. "
    "Tu ne donnes aucun avis médical."
)

_WEEKDAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def intent_prompt(message: str, today: date) -> str:
    return (
        f"Aujourd'hui, nous sommes {_WEEKDAYS[today.weekday()]} {today.isoformat()}.\n"
        "Extrais de ce message :\n"
        "- preferred_date : la date souhaitée au format YYYY-MM-DD. Pour un jour de la semaine "
        "(« mardi »), prends sa prochaine occurrence à partir de demain. Sinon null.\n"
        "- day_part : MORNING (matin), AFTERNOON (après-midi) ou EVENING (soir), sinon null.\n"
        "- specialty : la spécialité médicale demandée si elle est écrite, sinon null.\n"
        "- reason : le motif de la visite s'il est écrit, sinon null.\n\n"
        f"Message : {message}"
    )
