"""Clinical history of the demo patients, used by scripts.seed_modules.

One entry per patient of scripts.seed / scripts.seed_dev_patients (key: CIN, or
"First Last" when the patient has none), consistent with their administrative notes:
three visits with their medical report, documents, follow-up tasks and the state of
the AI summary. All data is fictitious.

Report sections follow reports.service.SECTIONS (reason, history, examination,
assessment, plan). Every number in a section also appears in the visit notes, so the
reports pass the guardrail (reports.guardrails.check_content) without warnings.
"""

from dataclasses import dataclass

from app.modules.appointments.models import AppointmentStatus
from app.modules.followup.models import TaskStatus
from app.modules.reports.models import ReportStatus

BENALI = "B"
TRABELSI = "T"

FINAL = ReportStatus.FINAL
ARCHIVED = ReportStatus.ARCHIVED
DRAFT = ReportStatus.DRAFT


@dataclass(frozen=True)
class Visit:
    days_ago: int
    doctor: str
    title: str  # report title and appointment reason
    notes: str
    # (reason, history, examination, assessment, plan); None: raw notes only, to try "Générer"
    sections: tuple[str, str, str, str, str] | None = None
    status: ReportStatus = FINAL


@dataclass(frozen=True)
class Doc:
    category: str  # document_categories.code
    title: str
    text: str
    fields: tuple[tuple[str, str], ...] = ()
    validated: bool = True  # False: AI suggestion and extracted fields still to review


@dataclass(frozen=True)
class History:
    visits: tuple[Visit, Visit, Visit]
    documents: tuple[Doc, ...]
    tasks: tuple[tuple[str, int, TaskStatus], ...]  # (description, due in days, status)
    points: tuple[str, ...]  # "Points administratifs" of the AI summary
    # VALIDATED, SUPERSEDED (an older validated one + the current one), DRAFT, REJECTED or None
    summary: str | None = None
    # (days ahead, doctor, reason, status); patients of scripts.seed already have one
    next_visit: tuple[int, str, str, AppointmentStatus] | None = None


TODO, IN_PROGRESS, DONE, CANCELLED = (
    TaskStatus.TODO,
    TaskStatus.IN_PROGRESS,
    TaskStatus.DONE,
    TaskStatus.CANCELLED,
)
CONFIRMED, PENDING = AppointmentStatus.CONFIRMED, AppointmentStatus.PENDING

CLINICAL_HISTORY: dict[str, History] = {
    "DEMO-0001": History(  # Leila Haddad, hypertension (linked to patient@mediflow.local)
        visits=(
            Visit(
                210, BENALI, "Bilan annuel de l'hypertension",
                "Bilan annuel HTA. TA 138/88 au cabinet, automesures 145/92 pendant la clôture "
                "comptable. Sous amlodipine 5 mg. Chevilles gonflées le soir. Poids 74 kg. "
                "Bilan : créatinine normale, LDL 1,65 g/l. Conseils : marche 30 min par jour, "
                "moins de sel. Revoir dans 3 mois.",
                (
                    "Bilan annuel de l'hypertension artérielle.",
                    "Hypertension traitée par amlodipine 5 mg. Automesures à 145/92 pendant les "
                    "périodes de clôture comptable.",
                    "Tension à 138/88 au cabinet. Poids 74 kg. Chevilles gonflées le soir.",
                    "Hypertension imparfaitement contrôlée en période de stress. Fonction rénale "
                    "normale, LDL à 1,65 g/l.",
                    "Marche 30 minutes par jour, réduction du sel. Contrôle dans 3 mois.",
                ),
            ),
            Visit(
                45, TRABELSI, "Consultation annuelle de cardiologie",
                "Avis cardio annuel. Asymptomatique. TA 132/84. ECG : rythme sinusal, pas "
                "d'hypertrophie. Écho cœur normale, FEVG 62 %. Œdèmes des chevilles "
                "probablement liés à l'amlodipine. Remplacer amlodipine 5 mg par périndopril "
                "4 mg. Holter tensionnel si automesures > 135/85.",
                (
                    "Consultation annuelle de cardiologie dans le cadre du suivi de "
                    "l'hypertension.",
                    "Hypertension traitée par amlodipine 5 mg, œdèmes des chevilles.",
                    "Tension à 132/84. ECG en rythme sinusal sans hypertrophie. Échographie "
                    "cardiaque normale, FEVG 62 %.",
                    "Cœur normal. Œdèmes probablement liés à l'amlodipine.",
                    "Remplacement de l'amlodipine par le périndopril 4 mg. Holter tensionnel si "
                    "les automesures dépassent 135/85.",
                ),
            ),
            Visit(
                3, BENALI, "Contrôle après changement de traitement",
                "Contrôle 6 semaines après passage au périndopril 4 mg. Œdèmes disparus. Toux "
                "sèche la nuit depuis 2 semaines. TA 128/82, automesures moyenne 131/83. "
                "Kaliémie et créatinine à contrôler. Si la toux persiste : discuter un sartan.",
                status=DRAFT,
            ),
        ),
        documents=(
            Doc("ORDONNANCE", "Ordonnance périndopril", "Périndopril 4 mg : 1 comprimé le matin. "
                "Traitement pour 3 mois.", (("Médicament", "Périndopril 4 mg"), ("Durée", "3 mois"))),
            Doc("ANALYSE", "Bilan lipidique et rénal", "Créatinine 7,8 mg/l. LDL cholestérol "
                "1,65 g/l. Potassium 4,2 mmol/l.", (("LDL", "1,65 g/l"), ("Créatinine", "7,8 mg/l"))),
            Doc("COMPTE_RENDU", "Échographie cardiaque", "Échographie transthoracique : "
                "cavités de taille normale, FEVG 62 %, pas de valvulopathie.",
                (("FEVG", "62 %"),), validated=False),
        ),
        tasks=(
            ("Prescrire la prise de sang de contrôle (kaliémie, créatinine)", 5, TODO),
            ("Envoyer le rappel SMS de la consultation de cardiologie", -2, DONE),
        ),
        points=(
            "Préfère les rendez-vous le matin avant 10h.",
            "Carnet de soins CNAM renouvelé en janvier 2026.",
            "Rappels par SMS plutôt que par appel.",
        ),
        summary="SUPERSEDED",
    ),
    "DEMO-0002": History(  # Youssef Ben Salah, type 2 diabetes
        visits=(
            Visit(
                280, BENALI, "Suivi du diabète",
                "Diabète type 2. HbA1c 8,4 %. Sous metformine 1000 mg x2 et gliclazide 60 mg. "
                "Fourmillements des pieds la nuit. Monofilament : sensibilité diminuée aux deux "
                "pieds. TA 142/88. Poids 92 kg. Consultation diététique. HbA1c dans 3 mois.",
                (
                    "Suivi du diabète de type 2.",
                    "Diabète traité par metformine 1000 mg deux fois par jour et gliclazide "
                    "60 mg. Fourmillements nocturnes des pieds.",
                    "Sensibilité diminuée aux deux pieds au monofilament. Tension 142/88. Poids "
                    "92 kg.",
                    "Diabète non équilibré, HbA1c à 8,4 %. Atteinte nerveuse débutante des pieds.",
                    "Consultation diététique. Nouvelle HbA1c dans 3 mois.",
                ),
                ARCHIVED,
            ),
            Visit(
                60, BENALI, "Renouvellement du traitement du diabète",
                "HbA1c 7,6 % (août). A perdu 6 kg en un an, poids 86 kg. Pieds : pas de plaie, "
                "sensibilité toujours diminuée. TA 140/88. Renouvellement metformine 1000 mg x2 "
                "et gliclazide 60 mg. Fond d'œil à refaire. Rappeler le patient la veille des RDV.",
                (
                    "Renouvellement du traitement du diabète de type 2.",
                    "Perte de 6 kg en un an. Deux rendez-vous manqués cette année.",
                    "Poids 86 kg. Pas de plaie des pieds, sensibilité toujours diminuée. Tension "
                    "140/88.",
                    "Diabète en amélioration, HbA1c à 7,6 %, objectif non atteint. Tension limite.",
                    "Renouvellement de la metformine 1000 mg deux fois par jour et du gliclazide "
                    "60 mg. Fond d'œil à refaire.",
                ),
            ),
            Visit(
                2, BENALI, "Examen des pieds et tension",
                "Examen des pieds : callosité talon droit, pas de plaie. TA 144/90 à deux "
                "reprises. Glycémies capillaires entre 1,30 et 1,80 g/l. Discuter un traitement "
                "de la tension. Ordonnance pédicure.",
                (
                    "Examen des pieds et contrôle de la tension.",
                    "Diabète suivi au cabinet, tension limite non traitée.",
                    "Callosité du talon droit sans plaie. Tension à 144/90 à deux reprises.",
                    "Glycémies capillaires entre 1,30 et 1,80 g/l. Tension au-dessus de "
                    "l'objectif.",
                    "Discuter un traitement de la tension. Ordonnance pour un pédicure.",
                ),
                DRAFT,
            ),
        ),
        documents=(
            Doc("ANALYSE", "Hémoglobine glyquée", "HbA1c 7,6 %. Glycémie à jeun 1,42 g/l.",
                (("HbA1c", "7,6 %"), ("Glycémie à jeun", "1,42 g/l"))),
            Doc("ADMINISTRATIF", "Accord APCI CNAM", "Prise en charge maladie chronique accordée "
                "jusqu'au 31/03/2027.", (("Validité", "31/03/2027"),)),
        ),
        tasks=(
            ("Lancer le renouvellement de l'APCI CNAM", 120, TODO),
            ("Programmer le fond d'œil", 14, IN_PROGRESS),
        ),
        points=(
            "Prise en charge CNAM APCI valable jusqu'au 31/03/2027.",
            "Deux rendez-vous manqués en 2026 : appeler la veille pour confirmer.",
        ),
        summary="VALIDATED",
    ),
    "DEMO-0003": History(  # Amira Gharbi, palpitations
        visits=(
            Visit(
                130, BENALI, "Palpitations",
                "Épisodes de cœur rapide le soir depuis fin 2025, de 5 à 30 minutes. 4 cafés par "
                "jour, nuits courtes. Examen normal, FC 78, TA 118/72. ECG de repos normal. TSH "
                "demandée. Adresser en cardiologie pour Holter.",
                (
                    "Palpitations.",
                    "Épisodes de cœur rapide le soir depuis fin 2025, durant de 5 à 30 minutes, "
                    "dans un contexte de 4 cafés par jour et de nuits courtes.",
                    "Examen normal. Fréquence cardiaque 78, tension 118/72. ECG de repos normal.",
                    "Palpitations sans signe de gravité à l'examen.",
                    "Dosage de la TSH. Avis cardiologique avec Holter.",
                ),
            ),
            Visit(
                40, TRABELSI, "Holter ECG",
                "Holter 24 h : rythme sinusal, FC moyenne 82, extrasystoles auriculaires rares, "
                "un passage de tachycardie sinusale à 130 pendant un épisode ressenti. TSH "
                "normale. Pas d'argument pour une arythmie grave. Échographie cardiaque à "
                "programmer.",
                (
                    "Analyse du Holter ECG pour palpitations.",
                    "Palpitations le soir, TSH normale.",
                    "Holter 24 h : rythme sinusal, fréquence moyenne 82, rares extrasystoles "
                    "auriculaires. Tachycardie sinusale à 130 pendant un épisode ressenti.",
                    "Pas d'argument pour une arythmie grave.",
                    "Échographie cardiaque à programmer.",
                ),
            ),
            Visit(
                5, BENALI, "Point sur les palpitations",
                "Moins d'épisodes depuis réduction du café à 1 par jour. Toujours anxieuse "
                "(soutenance dans 2 mois). TA 116/70. Échographie annulée, à reprogrammer. "
                "Discuter avec elle un suivi psychologique.",
                status=DRAFT,
            ),
        ),
        documents=(
            Doc("COMPTE_RENDU", "Compte rendu du Holter", "Holter ECG 24 h : rythme sinusal, "
                "FC moyenne 82/min, extrasystoles auriculaires rares.", (("FC moyenne", "82/min"),)),
            Doc("ANALYSE", "TSH", "TSH 1,9 mUI/l (normale).", (("TSH", "1,9 mUI/l"),), validated=False),
        ),
        tasks=(("Reprogrammer l'échographie cardiaque annulée", 3, TODO),),
        points=(
            "Pas d'assurance déclarée : règlement en espèces, reçu à chaque consultation.",
            "Disponible le samedi ou en fin de journée.",
        ),
        summary="DRAFT",
    ),
    "DEMO-0004": History(  # Karim Jaziri, low back pain
        visits=(
            Visit(
                330, BENALI, "Suivi après prothèse du genou",
                "10 mois après prothèse totale du genou droit. Flexion 110°, marche avec canne. "
                "Prise de poids 8 kg. TA 136/82 sous périndopril. Poursuite de la "
                "kinésithérapie. Conseils perte de poids.",
                (
                    "Suivi après prothèse totale du genou droit.",
                    "Prothèse du genou droit il y a 10 mois. Hypertension sous périndopril.",
                    "Flexion du genou à 110°. Marche avec une canne. Tension 136/82.",
                    "Bonne évolution de la prothèse. Prise de poids de 8 kg.",
                    "Poursuite de la kinésithérapie. Conseils pour la perte de poids.",
                ),
                ARCHIVED,
            ),
            Visit(
                50, BENALI, "Lombosciatique gauche",
                "Lombalgie depuis 2 mois irradiant à la jambe gauche, aggravée assis. EVA 6/10. "
                "Lasègue gauche à 60°. Pas de déficit, pas de trouble urinaire. Prend de "
                "l'ibuprofène de lui-même : arrêt (tension). Paracétamol 1 g x3. "
                "Kinésithérapie 10 séances.",
                (
                    "Douleurs lombaires irradiant dans la jambe gauche.",
                    "Douleurs depuis 2 mois, aggravées en position assise. Automédication par "
                    "ibuprofène.",
                    "Douleur à 6/10. Lasègue gauche à 60°. Pas de déficit, pas de trouble "
                    "urinaire.",
                    "Lombosciatique gauche sans signe de gravité.",
                    "Arrêt de l'ibuprofène à cause de la tension. Paracétamol 1 g trois fois par "
                    "jour. Kinésithérapie, 10 séances.",
                ),
            ),
            Visit(
                4, BENALI, "Réévaluation de la lombalgie",
                "Après 10 séances de kiné : EVA 4/10, sommeil meilleur. Lasègue négatif. "
                "Toujours gêné en voiture. IRM non nécessaire pour l'instant. Accord préalable "
                "assurance si IRM.",
                status=DRAFT,
            ),
        ),
        documents=(
            Doc("ORDONNANCE", "Ordonnance kinésithérapie", "Kinésithérapie lombaire : "
                "10 séances.", (("Séances", "10"),)),
            Doc("ADMINISTRATIF", "Relance facture de mars", "Relance envoyée le 12/04/2026 pour "
                "la facture de mars 2026.", (("Date de relance", "12/04/2026"),), validated=False),
        ),
        tasks=(
            ("Vérifier le règlement de la facture de mars 2026", -10, IN_PROGRESS),
            ("Demander l'accord préalable de l'assurance si une IRM est prescrite", 20, CANCELLED),
        ),
        points=(
            "Assurance privée : accord préalable obligatoire avant toute imagerie.",
            "Mobilité réduite : cabinet du rez-de-chaussée.",
            "Sa fille gère les rendez-vous.",
            "Facture de mars 2026 non réglée, relance envoyée.",
        ),
        summary="SUPERSEDED",
    ),
    "DEMO-0005": History(  # Nour Mansouri, vaccinations before moving abroad
        visits=(
            Visit(
                53, BENALI, "Mise à jour des vaccinations",
                "Départ en Allemagne avant l'été 2027. Carnet partiel (vaccins jusqu'à 6 ans). "
                "Allergie arachides (urticaire). Malaise à la prise de sang en 2021. Sérologies "
                "rougeole et hépatite B demandées. Rappel DTP dans le mois.",
                (
                    "Mise à jour des vaccinations avant un départ à l'étranger.",
                    "Carnet de vaccination partiel, vaccins notés jusqu'à 6 ans. Allergie aux "
                    "arachides. Malaise lors d'une prise de sang en 2021.",
                    "Non précisé dans les notes.",
                    "Statut vaccinal incomplet.",
                    "Sérologies rougeole et hépatite B. Rappel DTP dans le mois.",
                ),
            ),
            Visit(
                30, BENALI, "Rappel diphtérie-tétanos-polio",
                "Rappel DTP fait, patiente allongée, bonne tolérance, surveillance 15 min. "
                "Sérologie rougeole positive (immunisée). Hépatite B négative : schéma en 3 "
                "doses à débuter.",
                (
                    "Rappel diphtérie-tétanos-polio.",
                    "Mise à jour des vaccinations avant un départ en Allemagne.",
                    "Vaccin fait en position allongée, surveillance 15 minutes, bonne tolérance.",
                    "Immunisée contre la rougeole. Non immunisée contre l'hépatite B.",
                    "Vaccination contre l'hépatite B en 3 doses à débuter.",
                ),
            ),
            Visit(
                1, BENALI, "Hépatite B, première dose",
                "Hépatite B dose 1/3, allongée, pas de malaise. Dose 2 dans 1 mois. Certificat "
                "de vaccination en anglais demandé.",
                (
                    "Première dose du vaccin contre l'hépatite B.",
                    "Schéma vaccinal en cours avant un départ à l'étranger.",
                    "Vaccin fait en position allongée, pas de malaise.",
                    "Dose 1/3 réalisée.",
                    "Dose 2 dans 1 mois. Certificat de vaccination en anglais à préparer.",
                ),
                DRAFT,
            ),
        ),
        documents=(
            Doc("ANALYSE", "Sérologies rougeole et hépatite B", "IgG rougeole positives. "
                "Anticorps anti-HBs négatifs.", (("Rougeole", "Immunisée"), ("Hépatite B", "Non immunisée"))),
            Doc("CERTIFICAT", "Certificat de vaccination", "Certificat attestant le rappel DTP "
                "et la première dose d'hépatite B.", validated=False),
        ),
        tasks=(
            ("Remettre le formulaire d'affiliation CNAM", 7, TODO),
            ("Préparer le certificat de vaccination en anglais", 10, IN_PROGRESS),
        ),
        points=(
            "Pas d'assurance, souhaite s'affilier à la CNAM.",
            "Certificat de vaccination en anglais ou en allemand à fournir.",
            "Préfère être contactée par email.",
        ),
        summary=None,
    ),
    "09812345": History(  # Mohamed Ben Ammar, heart failure and atrial fibrillation
        visits=(
            Visit(
                240, TRABELSI, "Suivi de l'insuffisance cardiaque",
                "Suivi post-hospitalisation. Essoufflement aux escaliers. Poids 81 kg stable. "
                "FC 72 irrégulière. TA 124/76. Pas d'œdème. FEVG 40 % à l'écho. Traitement "
                "inchangé. Pesée quotidienne : appeler si +2 kg en 3 jours.",
                (
                    "Suivi de l'insuffisance cardiaque et de la fibrillation atriale.",
                    "Hospitalisation pour insuffisance cardiaque, infarctus ancien traité par "
                    "stent.",
                    "Poids 81 kg stable. Rythme irrégulier à 72. Tension 124/76. Pas d'œdème.",
                    "Insuffisance cardiaque stable, FEVG à 40 %.",
                    "Traitement inchangé. Pesée quotidienne : appeler en cas de prise de 2 kg en "
                    "3 jours.",
                ),
            ),
            Visit(
                35, TRABELSI, "Contrôle cardiologique trimestriel",
                "Stable depuis l'été. Poids 80 kg. FC 68. TA 118/72. Kaliémie 4,6, créatinine "
                "12 mg/l. Allergie pénicilline non documentée : à confirmer. Bilan dans 3 mois.",
                (
                    "Contrôle cardiologique trimestriel.",
                    "Insuffisance cardiaque et fibrillation atriale sous traitement.",
                    "Poids 80 kg. Fréquence 68. Tension 118/72.",
                    "État stable. Kaliémie à 4,6, créatinine à 12 mg/l.",
                    "Confirmer l'allergie à la pénicilline. Bilan sanguin dans 3 mois.",
                ),
            ),
            Visit(
                6, BENALI, "Bronchite",
                "Toux grasse depuis 5 jours, pas de fièvre (37,2). Poids 81 kg (+1 kg). Crépitants "
                "bases ? Pas d'œdème. Surveillance poids, revoir si +2 kg ou fièvre. Pas "
                "d'antibiotique pour l'instant (allergie pénicilline à vérifier).",
                status=DRAFT,
            ),
        ),
        documents=(
            Doc("ANALYSE", "Ionogramme et fonction rénale", "Potassium 4,6 mmol/l. Créatinine "
                "12 mg/l.", (("Potassium", "4,6 mmol/l"), ("Créatinine", "12 mg/l"))),
            Doc("ORDONNANCE", "Ordonnance du traitement cardiaque", "Anticoagulant, "
                "bêtabloquant, diurétique et traitement de l'insuffisance cardiaque, matin et "
                "soir. 3 mois."),
            Doc("COMPTE_RENDU", "Compte rendu d'hospitalisation", "Hospitalisation de janvier "
                "2025 : insuffisance cardiaque, fibrillation atriale, FEVG 40 %.",
                (("FEVG", "40 %"),), validated=False),
        ),
        tasks=(
            ("Regrouper bilan sanguin et cardiologie le même jour", 25, TODO),
            ("Demander le document attestant l'allergie à la pénicilline", 7, TODO),
        ),
        points=(
            "Vient accompagné de son épouse, qui garde les ordonnances.",
            "Souhaite regrouper ses rendez-vous le même jour.",
        ),
        summary="SUPERSEDED",
        next_visit=(30, TRABELSI, "Bilan cardiologique trimestriel", CONFIRMED),
    ),
    "09823456": History(  # Fatma Trabelsi, burnout and iron deficiency
        visits=(
            Visit(
                250, BENALI, "Fatigue et troubles du sommeil",
                "Épuisement, réveils à 4 h, pleurs après les cours. Bilan : ferritine 9, "
                "hémoglobine 11,2. TSH normale. Fer 1 cp/jour 3 mois. Arrêt de travail 14 jours. "
                "Psychologue proposée.",
                (
                    "Fatigue et troubles du sommeil.",
                    "Contexte de surcharge professionnelle et de séparation récente.",
                    "Non précisé dans les notes.",
                    "Épuisement professionnel avec carence en fer : ferritine 9, hémoglobine "
                    "11,2. TSH normale.",
                    "Fer 1 comprimé par jour pendant 3 mois. Arrêt de travail de 14 jours. "
                    "Suivi psychologique proposé.",
                ),
                ARCHIVED,
            ),
            Visit(
                55, BENALI, "Suivi mensuel",
                "Va mieux depuis les vacances. Psychologue 2 fois par mois. Refuse "
                "antidépresseur. Ferritine 28. Sommeil 6 h par nuit. Inquiète pour la rentrée. "
                "Consultation gynéco pas encore faite.",
                (
                    "Suivi mensuel de l'épuisement professionnel.",
                    "Suivi psychologique 2 fois par mois. Refus d'un antidépresseur.",
                    "Sommeil de 6 h par nuit.",
                    "Amélioration. Ferritine remontée à 28.",
                    "Poursuite du suivi. Consultation gynécologique à faire.",
                ),
            ),
            Visit(
                3, BENALI, "Certificat d'aptitude et suivi",
                "Rentrée difficile mais tient le coup. Demande certificat d'aptitude annuel. "
                "Humeur stable, sommeil 6 h. Poursuivre psychologue. Rappeler la consultation "
                "gynécologique.",
                status=DRAFT,
            ),
        ),
        documents=(
            Doc("ANALYSE", "Bilan martial", "Ferritine 28 µg/l. Hémoglobine 12,4 g/dl.",
                (("Ferritine", "28 µg/l"), ("Hémoglobine", "12,4 g/dl"))),
            Doc("CERTIFICAT", "Certificat d'aptitude 2026", "Certificat d'aptitude à "
                "l'enseignement pour l'année scolaire 2026-2027.", validated=False),
        ),
        tasks=(("Préparer le certificat d'aptitude pour l'employeur", 2, TODO),),
        points=(
            "Disponible le mercredi après-midi et pendant les vacances scolaires.",
            "Certificat d'aptitude à fournir chaque année en septembre.",
            "Accepte les rappels par SMS.",
        ),
        summary="REJECTED",
        next_visit=(21, BENALI, "Suivi mensuel de novembre", CONFIRMED),
    ),
    "09834567": History(  # Ahmed Chaabane, shoulder after a work accident
        visits=(
            Visit(
                160, BENALI, "Accident du travail, épaule droite",
                "Chute d'une échelle, réception sur le bras droit. Urgences : pas de fracture, "
                "entorse. Écharpe 10 jours. Douleur 7/10. Certificat d'accident du travail "
                "initial.",
                (
                    "Accident du travail : chute sur l'épaule droite.",
                    "Vu aux urgences le jour même, pas de fracture.",
                    "Douleur à 7/10.",
                    "Entorse de l'épaule droite.",
                    "Écharpe pendant 10 jours. Certificat initial d'accident du travail.",
                ),
            ),
            Visit(
                65, BENALI, "Épaule douloureuse persistante",
                "Douleur en levant le bras et la nuit couché à droite. Abduction limitée à 90°. "
                "Force diminuée. Échographie de l'épaule prescrite. Poste aménagé.",
                (
                    "Douleur persistante de l'épaule droite.",
                    "Accident du travail il y a plusieurs mois.",
                    "Abduction limitée à 90°. Force diminuée.",
                    "Suspicion de lésion des tendons.",
                    "Échographie de l'épaule. Poste de travail aménagé.",
                ),
            ),
            Visit(
                2, BENALI, "Contrôle de l'épaule",
                "Échographie toujours pas faite (coût). Douleur 5/10. Travail de nuit une "
                "semaine sur deux. Infiltration à discuter après écho. Voir échéancier.",
                (
                    "Contrôle de l'épaule droite.",
                    "Échographie non réalisée pour raison financière.",
                    "Douleur à 5/10.",
                    "Évolution lente, travail de nuit gênant la récupération.",
                    "Réaliser l'échographie. Infiltration à discuter ensuite.",
                ),
                DRAFT,
            ),
        ),
        documents=(
            Doc("CERTIFICAT", "Certificat d'accident du travail", "Certificat initial : entorse "
                "de l'épaule droite, arrêt de 10 jours.", (("Arrêt", "10 jours"),)),
            Doc("ORDONNANCE", "Prescription d'échographie", "Échographie de l'épaule droite.",
                validated=False),
        ),
        tasks=(
            ("Remettre la copie du certificat d'accident du travail", 4, TODO),
            ("Suivre l'échéancier du bilan sanguin (2 versements restants)", 15, IN_PROGRESS),
        ),
        points=(
            "Pas d'assurance déclarée.",
            "Échéancier accordé, deux versements restants.",
            "Adresse postale incomplète.",
        ),
        summary="DRAFT",
        next_visit=(12, BENALI, "Résultat de l'échographie de l'épaule", PENDING),
    ),
    "09845678": History(  # Sonia Dridi, rheumatoid arthritis
        visits=(
            Visit(
                190, BENALI, "Suivi de la polyarthrite",
                "PR peu active. Raideur matinale 30 min. Méthotrexate 15 mg/semaine + acide "
                "folique. Transaminases normales. Kiné main : 9 séances sur 15. Vaccin grippe à "
                "faire.",
                (
                    "Suivi de la polyarthrite rhumatoïde.",
                    "Polyarthrite sous méthotrexate 15 mg par semaine et acide folique.",
                    "Raideur matinale de 30 minutes.",
                    "Maladie peu active, bilan hépatique normal.",
                    "Terminer la kinésithérapie de la main (9 séances sur 15). Vaccin contre la "
                    "grippe.",
                ),
            ),
            Visit(
                70, BENALI, "Ostéoporose et polyarthrite",
                "Densitométrie : T-score -2,8 au rachis. Calcium + vitamine D. Discuter "
                "bisphosphonate. Méthotrexate inchangé. NFS normale.",
                (
                    "Suivi de l'ostéoporose et de la polyarthrite.",
                    "Fracture du poignet ancienne, cortisone lors des poussées.",
                    "Non précisé dans les notes.",
                    "Ostéoporose, T-score à -2,8 au rachis. Numération normale.",
                    "Calcium et vitamine D. Discussion d'un bisphosphonate. Méthotrexate "
                    "inchangé.",
                ),
            ),
            Visit(
                4, BENALI, "Bilan trimestriel",
                "Fatigue +. Raideur 45 min depuis 2 semaines. Synovite poignet droit ? Bilan "
                "sanguin (VS, CRP, transaminases). Vaccins grippe et pneumocoque à faire. Revoir "
                "dans 1 mois.",
                status=DRAFT,
            ),
        ),
        documents=(
            Doc("IMAGERIE", "Densitométrie osseuse", "T-score rachis lombaire -2,8. Col fémoral "
                "-2,1.", (("T-score rachis", "-2,8"), ("T-score col", "-2,1"))),
            Doc("ADMINISTRATIF", "Autorisation de récupération des résultats", "Autorisation "
                "signée le 10/01/2026 au nom de Hichem Dridi."),
        ),
        tasks=(
            ("Scanner la nouvelle attestation médecin de famille CNAM", 10, TODO),
            ("Relancer le cabinet de Monastir pour les anciens comptes rendus", -20, DONE),
        ),
        points=(
            "Filière médecin de famille CNAM en cours.",
            "Son frère peut récupérer les résultats (autorisation signée).",
            "Préfère le début d'après-midi.",
        ),
        summary="VALIDATED",
        next_visit=(28, BENALI, "Réévaluation de la polyarthrite", CONFIRMED),
    ),
    "09856789": History(  # Rania Bouazizi, childhood asthma
        visits=(
            Visit(
                200, BENALI, "Asthme, consultation de printemps",
                "Crises au printemps. Secours 1 fois par semaine. DEP 320 l/min. Technique "
                "d'inhalation correcte. Traitement de fond poursuivi. Certificat sport.",
                (
                    "Suivi de l'asthme au printemps.",
                    "Asthme depuis l'enfance, allergie aux acariens.",
                    "Débit expiratoire de pointe à 320 l/min. Bonne technique d'inhalation.",
                    "Asthme contrôlé, secours 1 fois par semaine.",
                    "Poursuite du traitement de fond. Certificat pour le sport.",
                ),
            ),
            Visit(
                38, BENALI, "Asthme mal contrôlé",
                "Rentrée : secours 2 à 3 fois par semaine, surtout au handball. Oublis du "
                "traitement de fond entre les deux maisons. DEP 280. Deuxième inhalateur "
                "prescrit. Plan d'action pour le collège.",
                (
                    "Asthme mal contrôlé depuis la rentrée.",
                    "Oublis du traitement de fond entre les deux domiciles.",
                    "Débit expiratoire de pointe à 280.",
                    "Asthme mal contrôlé, secours 2 à 3 fois par semaine.",
                    "Deuxième inhalateur pour chaque domicile. Plan d'action pour le collège.",
                ),
            ),
            Visit(
                5, BENALI, "Contrôle de l'asthme",
                "Avec le père. Secours 1 fois par semaine. DEP 310. Inhalateurs dans les deux "
                "maisons. Revoir technique : ok. Plan d'action remis à l'infirmière.",
                (
                    "Contrôle de l'asthme, avec son père.",
                    "Asthme mal contrôlé le mois dernier.",
                    "Débit expiratoire de pointe à 310. Technique d'inhalation correcte.",
                    "Amélioration, secours 1 fois par semaine.",
                    "Poursuite du traitement. Plan d'action remis à l'infirmière du collège.",
                ),
                DRAFT,
            ),
        ),
        documents=(
            Doc("CERTIFICAT", "Certificat de non-contre-indication au sport", "Handball en "
                "club, saison 2026-2027."),
            Doc("ORDONNANCE", "Ordonnance inhalateurs", "Inhalateur de fond matin et soir, "
                "inhalateur de secours, 2 exemplaires.", (("Exemplaires", "2"),), validated=False),
        ),
        tasks=(("Envoyer le plan d'action asthme à l'infirmière du collège", -3, DONE),),
        points=(
            "Patiente mineure : rendez-vous avec un parent.",
            "Le père signe les autorisations.",
            "Certificat sport à chaque rentrée.",
        ),
        summary="VALIDATED",
        next_visit=(45, BENALI, "Asthme, contrôle d'hiver", PENDING),
    ),
    "09867890": History(  # Hamza Khemiri, pneumothorax
        visits=(
            Visit(
                170, BENALI, "Certificat sportif",
                "Certificat basket universitaire. Fumeur 10 cig/jour. Auscultation normale. "
                "TA 122/70. Conseil arrêt tabac.",
                (
                    "Certificat de non-contre-indication au basket.",
                    "Fumeur de 10 cigarettes par jour.",
                    "Auscultation normale. Tension 122/70.",
                    "Pas de contre-indication.",
                    "Conseil d'arrêt du tabac.",
                ),
                ARCHIVED,
            ),
            Visit(
                50, BENALI, "Contrôle après pneumothorax",
                "Pneumothorax gauche drainé, 4 jours d'hospitalisation. Radio à 1 mois "
                "normale. Essoufflé à l'effort intense. Arrêt tabac : prêt, substituts "
                "nicotiniques. Pas d'avion ni de plongée.",
                (
                    "Contrôle après un pneumothorax gauche.",
                    "Pneumothorax spontané drainé, 4 jours d'hospitalisation.",
                    "Radiographie à 1 mois normale.",
                    "Bonne évolution, essoufflement seulement à l'effort intense.",
                    "Substituts nicotiniques pour l'arrêt du tabac. Pas d'avion ni de plongée.",
                ),
            ),
            Visit(
                2, BENALI, "Sevrage tabagique",
                "3 cigarettes/jour avec patch 21 mg. Pas de douleur thoracique. Envie de reprendre "
                "le sport. Certificat d'absence fac remis.",
                status=DRAFT,
            ),
        ),
        documents=(
            Doc("IMAGERIE", "Radiographie thoracique de contrôle", "Poumon gauche à la paroi, "
                "pas de décollement résiduel."),
            Doc("CERTIFICAT", "Certificat d'absence", "Absence aux examens du 18 au "
                "22 août 2026 pour hospitalisation.", validated=False),
        ),
        tasks=(("Vérifier la couverture CNAM (ayant droit expiré ?)", 5, TODO),),
        points=(
            "Couverture CNAM probablement expirée, à vérifier.",
            "Préfère être contacté par email.",
        ),
        summary="VALIDATED",
        next_visit=(16, BENALI, "Suivi du sevrage tabagique", CONFIRMED),
    ),
    "09878901": History(  # Claire Martin, thyroid nodule
        visits=(
            Visit(
                120, BENALI, "Nodule thyroïdien",
                "Boule à la base du cou depuis juin. Pas de dysphagie. Nodule droit palpable "
                "mobile. Lévothyroxine 75 µg. TSH 1,8. Échographie thyroïde demandée.",
                (
                    "Nodule de la thyroïde.",
                    "Hypothyroïdie traitée par lévothyroxine 75 µg.",
                    "Nodule droit palpable et mobile. Pas de difficulté pour avaler.",
                    "Nodule thyroïdien à explorer, TSH à 1,8.",
                    "Échographie de la thyroïde.",
                ),
            ),
            Visit(
                90, BENALI, "Résultat de l'échographie thyroïdienne",
                "Écho : nodule droit 18 mm, TI-RADS 4. Ponction à l'aiguille fine conseillée. "
                "Patiente inquiète (mère cancer du sein). Mammographie à prévoir.",
                (
                    "Résultat de l'échographie de la thyroïde.",
                    "Antécédent de cancer du sein chez la mère.",
                    "Nodule droit de 18 mm, classé TI-RADS 4.",
                    "Nodule nécessitant une ponction.",
                    "Ponction à l'aiguille fine. Mammographie à prévoir.",
                ),
            ),
            Visit(
                6, BENALI, "Décision sur la ponction",
                "Accepte de faire la cytoponction à Tunis. Prescription remise. Mammographie "
                "aussi. Copie des CR pour son médecin en France. Facture détaillée en français.",
                (
                    "Décision sur la ponction du nodule thyroïdien.",
                    "Nodule thyroïdien droit, antécédent familial de cancer du sein.",
                    "Non précisé dans les notes.",
                    "La patiente accepte la ponction à Tunis.",
                    "Prescription de la cytoponction et de la mammographie. Copie des comptes "
                    "rendus pour son médecin en France.",
                ),
                DRAFT,
            ),
        ),
        documents=(
            Doc("IMAGERIE", "Échographie thyroïdienne", "Nodule lobe droit 18 mm, TI-RADS 4.",
                (("Taille", "18 mm"), ("Classification", "TI-RADS 4"))),
            Doc("ADMINISTRATIF", "Facture détaillée pour l'assureur", "Facture en français "
                "avec numéro de dossier de l'assureur.", validated=False),
        ),
        tasks=(
            ("Envoyer la copie des comptes rendus au médecin traitant en France", 3, TODO),
            ("Préparer la facture détaillée en français", 1, DONE),
        ),
        points=(
            "Assurance privée internationale : factures détaillées en français.",
            "Consultations en français.",
            "Copie de tous les comptes rendus pour son médecin en France.",
        ),
        summary="DRAFT",
        next_visit=(9, BENALI, "Résultat de la cytoponction", CONFIRMED),
    ),
    "09889012": History(  # Walid Hammami, Parkinson's disease and falls
        visits=(
            Visit(
                300, BENALI, "Suivi de la maladie de Parkinson",
                "Tremblement main droite, marche à petits pas. Lévodopa 3 prises/jour. "
                "Constipation. Poids 64 kg. Audition : appareil une oreille. Kiné marche.",
                (
                    "Suivi de la maladie de Parkinson.",
                    "Maladie de Parkinson diagnostiquée par un neurologue. Surdité appareillée "
                    "d'une oreille.",
                    "Tremblement de la main droite, marche à petits pas. Poids 64 kg.",
                    "Maladie stable sous traitement. Constipation.",
                    "Lévodopa en 3 prises par jour. Kinésithérapie de la marche.",
                ),
                ARCHIVED,
            ),
            Visit(
                75, BENALI, "Chute nocturne",
                "Chute la nuit en allant aux toilettes. Plaie cuir chevelu suturée aux urgences "
                "(5 points). Pas de perte de connaissance. TA couché 132/78, debout 118/70. "
                "Veilleuse, barre d'appui. Kiné équilibre.",
                (
                    "Chute nocturne.",
                    "Maladie de Parkinson, levers nocturnes fréquents.",
                    "Plaie du cuir chevelu suturée (5 points). Tension couché 132/78, debout "
                    "118/70.",
                    "Chute sans perte de connaissance, légère baisse de tension en position "
                    "debout.",
                    "Veilleuse et barre d'appui. Kinésithérapie de l'équilibre.",
                ),
            ),
            Visit(
                4, BENALI, "Contrôle après les chutes",
                "Avec sa fille. Pas de nouvelle chute depuis 2 mois. Poids 62 kg (-2 kg). "
                "Blocages si prise retardée. Rendez-vous neuro à avancer ? Constipation : "
                "macrogol.",
                status=DRAFT,
            ),
        ),
        documents=(
            Doc("COMPTE_RENDU", "Compte rendu des urgences", "Plaie du cuir chevelu de 3 cm "
                "suturée. Scanner cérébral normal.", (("Scanner", "Normal"),)),
            Doc("ORDONNANCE", "Ordonnance antiparkinsonienne", "Lévodopa : 3 prises par jour "
                "à heures fixes. 3 mois.", validated=False),
        ),
        tasks=(
            ("Appeler la fille du patient pour confirmer le rendez-vous", 6, TODO),
            ("Transmettre le compte rendu de chute au neurologue", -15, DONE),
        ),
        points=(
            "Malentendant : contacter sa fille, ne pas appeler le patient.",
            "Pas de rendez-vous avant 9h30.",
        ),
        summary="VALIDATED",
        next_visit=(7, BENALI, "Suivi neurologique et chutes", CONFIRMED),
    ),
    "09890123": History(  # Ines Saidi, recurring abdominal pain
        visits=(
            Visit(
                100, BENALI, "Douleurs abdominales",
                "Crampes, ballonnements, alternance diarrhée/constipation depuis 1 an. Perte "
                "de 3 kg en 6 mois. Ventre souple, sensible. Bilan : NFS, CRP, anticorps "
                "maladie cœliaque, selles.",
                (
                    "Douleurs abdominales répétées.",
                    "Troubles digestifs depuis 1 an, après une gastro-entérite en voyage.",
                    "Ventre souple, légèrement sensible. Perte de 3 kg en 6 mois.",
                    "Troubles digestifs à explorer.",
                    "Numération, CRP, anticorps de la maladie cœliaque et analyse des selles.",
                ),
            ),
            Visit(
                42, BENALI, "Résultats du bilan digestif",
                "NFS normale, CRP 2. Anticorps anti-transglutaminase négatifs. Selles normales. "
                "Probable intestin irritable. Conseils repas réguliers malgré les gardes. "
                "Antispasmodique si besoin.",
                (
                    "Résultats du bilan digestif.",
                    "Douleurs abdominales, travail de nuit.",
                    "Non précisé dans les notes.",
                    "Bilan normal, CRP à 2, anticorps négatifs. Probable syndrome de l'intestin "
                    "irritable.",
                    "Repas à horaires réguliers. Antispasmodique si besoin.",
                ),
            ),
            Visit(
                1, BENALI, "Suivi des troubles digestifs",
                "Mieux depuis repas réguliers. Poids stable. Toujours gênée pendant les gardes. "
                "Avis gastro si nouvelle perte de poids.",
                status=DRAFT,
            ),
        ),
        documents=(
            Doc("ANALYSE", "Bilan digestif", "NFS normale. CRP 2 mg/l. Anticorps "
                "anti-transglutaminase négatifs.", (("CRP", "2 mg/l"),)),
            Doc("ADMINISTRATIF", "Formulaire d'inscription en ligne", "Formulaire du "
                "14/07/2026, champ remarques à revoir avec la patiente.", validated=False),
        ),
        tasks=(("Demander la carte d'assurance à la prochaine visite", 30, TODO),),
        points=(
            "Assurance non renseignée.",
            "Formulaire d'inscription en ligne à revoir avec elle.",
            "Disponible après ses gardes, l'après-midi.",
        ),
        summary="REJECTED",
        next_visit=(33, BENALI, "Contrôle digestif", PENDING),
    ),
    "09901234": History(  # Sami Ferchichi, suspected occupational asthma
        visits=(
            Visit(
                220, BENALI, "Rhinite allergique",
                "Rhinite au printemps, éternuements, nez bouché. Toux matinale. Antihistaminique "
                "1 cp/jour 1 mois. Spray nasal.",
                (
                    "Rhinite allergique.",
                    "Rhinite depuis l'adolescence, toux matinale.",
                    "Non précisé dans les notes.",
                    "Rhinite allergique saisonnière.",
                    "Antihistaminique 1 comprimé par jour pendant 1 mois. Spray nasal.",
                ),
            ),
            Visit(
                33, BENALI, "Crise d'essoufflement au travail",
                "Crise de sifflements au poste de travail. Sibilants bilatéraux. Amélioration "
                "sous salbutamol. Arrêt de travail 5 jours. Spirométrie à faire après 1 semaine "
                "de travail puis 1 semaine de congé.",
                (
                    "Crise d'essoufflement sur le lieu de travail.",
                    "Exposition professionnelle à des poussières et des vapeurs.",
                    "Sifflements dans les deux poumons.",
                    "Suspicion d'asthme lié au travail, amélioration sous salbutamol.",
                    "Arrêt de travail de 5 jours. Spirométrie après 1 semaine de travail puis "
                    "après 1 semaine de congé.",
                ),
            ),
            Visit(
                6, BENALI, "Résultats de la spirométrie",
                "VEMS 78 % après une semaine de travail, 91 % après une semaine de congé. "
                "Évocateur asthme professionnel. Avis médecin du travail. Certificat pour "
                "déclaration MP à discuter. Patient inquiet pour son poste.",
                (
                    "Résultats de la spirométrie.",
                    "Suspicion d'asthme lié au travail.",
                    "VEMS à 78 % après une semaine de travail et à 91 % après une semaine de "
                    "congé.",
                    "Résultats évocateurs d'un asthme professionnel.",
                    "Avis du médecin du travail. Certificat de maladie professionnelle à "
                    "discuter.",
                ),
                DRAFT,
            ),
        ),
        documents=(
            Doc("ANALYSE", "Spirométries comparées", "VEMS 78 % de la théorique après une "
                "semaine de travail, 91 % après une semaine de congé.",
                (("VEMS travail", "78 %"), ("VEMS congé", "91 %"))),
            Doc("CERTIFICAT", "Arrêt de travail", "Arrêt de travail de 5 jours délivré le "
                "22/09/2026.", (("Durée", "5 jours"),)),
            Doc("ADMINISTRATIF", "Attestation CNAM provisoire", "Attestation provisoire valable "
                "jusqu'au 30/11/2026.", validated=False),
        ),
        tasks=(
            ("Relancer le transfert du dossier CNAM depuis Gabès", 20, IN_PROGRESS),
            ("Écrire au médecin du travail de l'usine", 4, TODO),
        ),
        points=(
            "Attestation CNAM provisoire valable jusqu'au 30/11/2026.",
            "Vient de Gabès : regrouper consultation et examens.",
        ),
        summary="VALIDATED",
        next_visit=(18, BENALI, "Avis sur la maladie professionnelle", CONFIRMED),
    ),
    "09912345": History(  # Marwa Ben Youssef, gestational diabetes
        visits=(
            Visit(
                45, BENALI, "Diabète gestationnel",
                "Adressée par la sage-femme. HGPO 24 SA : 0,98 / 1,85 / 1,62 g/l. Diabète "
                "gestationnel confirmé. Régime avec diététicienne. Glycémies 4 fois par jour. "
                "TA 112/68.",
                (
                    "Diabète gestationnel.",
                    "Deux fausses couches précoces, grossesse obtenue après traitement.",
                    "Tension 112/68.",
                    "Diabète gestationnel confirmé : 0,98, 1,85 puis 1,62 g/l au test.",
                    "Régime avec une diététicienne. Glycémies capillaires 4 fois par jour.",
                ),
            ),
            Visit(
                24, BENALI, "Suivi du diabète gestationnel",
                "Glycémies journée correctes, à jeun 0,98 à 1,02. Poids +1 kg. Brûlures "
                "d'estomac. Très anxieuse. Si à jeun > 0,95 persiste : insuline.",
                (
                    "Suivi du diabète gestationnel.",
                    "Régime suivi avec une diététicienne.",
                    "Prise de poids de 1 kg. Brûlures d'estomac.",
                    "Glycémies de la journée correctes, à jeun entre 0,98 et 1,02.",
                    "Insuline si la glycémie à jeun reste au-dessus de 0,95.",
                ),
            ),
            Visit(
                3, BENALI, "Mise sous insuline",
                "À jeun toujours 1,00 à 1,05. Insuline lente le soir, 6 UI. Apprentissage "
                "injections. Courrier sage-femme. Revoir dans 1 semaine.",
                status=DRAFT,
            ),
        ),
        documents=(
            Doc("ANALYSE", "Hyperglycémie provoquée orale", "HGPO 75 g : T0 0,98 g/l, "
                "T1h 1,85 g/l, T2h 1,62 g/l.", (("T0", "0,98 g/l"), ("T1h", "1,85 g/l"), ("T2h", "1,62 g/l"))),
            Doc("COMPTE_RENDU", "Courrier de la sage-femme", "Grossesse de 24 semaines, "
                "dépistage du diabète positif.", validated=False),
            Doc("IMAGERIE", "Échographie du deuxième trimestre", "Croissance fœtale normale.",
                validated=False),
        ),
        tasks=(
            ("Classer les courriers de la sage-femme et les échographies", 2, TODO),
            ("Programmer le contrôle de glycémie après l'accouchement", 140, TODO),
        ),
        points=(
            "Pas d'assurance déclarée, ajout comme ayant droit CNAM en cours.",
            "Préfère la fin de journée.",
        ),
        summary=None,
        next_visit=(4, BENALI, "Contrôle des glycémies sous insuline", CONFIRMED),
    ),
    "09923456": History(  # Alex Mzoughi, panic attacks
        visits=(
            Visit(
                190, BENALI, "Crises de panique",
                "Crises dans les transports : palpitations, étouffement, tremblements. Bilan "
                "cardiaque urgences normal. Plusieurs crises/semaine. Psychologue proposée. "
                "Pas d'idées suicidaires. Respiration.",
                (
                    "Crises de panique.",
                    "Passage aux urgences avec bilan cardiaque normal.",
                    "Non précisé dans les notes.",
                    "Trouble panique, plusieurs crises par semaine. Pas d'idées suicidaires.",
                    "Suivi psychologique. Exercices de respiration.",
                ),
                ARCHIVED,
            ),
            Visit(
                60, BENALI, "Suivi de l'anxiété",
                "Environ 1 crise par mois. Psychologue chaque semaine. Évite le bus, vélo. "
                "Traitement de fond proposé, préfère attendre. Pas d'idées suicidaires. "
                "Certificat d'absence pour 2 examens.",
                (
                    "Suivi de l'anxiété.",
                    "Suivi psychologique hebdomadaire.",
                    "Non précisé dans les notes.",
                    "Nette amélioration, environ 1 crise par mois. Pas d'idées suicidaires.",
                    "Pas de traitement de fond pour l'instant, à la demande de la personne. "
                    "Certificat d'absence pour 2 examens.",
                ),
            ),
            Visit(
                5, BENALI, "Point mensuel",
                "Pas de crise depuis 5 semaines. Reprise du bus sur un trajet court. Sommeil "
                "toujours tardif. Pas d'idées suicidaires. Continuer psychologue.",
                (
                    "Point mensuel sur l'anxiété.",
                    "Trouble panique suivi par une psychologue.",
                    "Non précisé dans les notes.",
                    "Pas de crise depuis 5 semaines. Pas d'idées suicidaires. Sommeil tardif.",
                    "Poursuite du suivi psychologique.",
                ),
                DRAFT,
            ),
        ),
        documents=(
            Doc("CERTIFICAT", "Certificats d'absence", "Absence justifiée pour 2 examens de "
                "design.", (("Examens", "2"),)),
            Doc("ADMINISTRATIF", "Préférences de contact", "Prénom d'usage, sans civilité. "
                "Appels après 17h."),
        ),
        tasks=(("Mettre à jour le prénom d'usage dans les courriers", -5, DONE),),
        points=(
            "Prénom d'usage, sans civilité, à l'accueil et dans les courriers.",
            "Pas d'assurance déclarée.",
            "Appels uniquement après 17h.",
        ),
        summary="VALIDATED",
        next_visit=(26, BENALI, "Suivi de l'anxiété", PENDING),
    ),
    "09934567": History(  # Habib Zouari, coronary artery disease
        visits=(
            Visit(
                200, TRABELSI, "Douleur thoracique d'effort",
                "Oppression thoracique en portant des charges, cède au repos. 3 épisodes. "
                "Tabac 20 cig/jour. TA 158/96. Test d'effort positif. Coronarographie à "
                "programmer.",
                (
                    "Douleur thoracique à l'effort.",
                    "Fumeur de 20 cigarettes par jour, hypertension mal suivie.",
                    "Tension 158/96. Test d'effort positif.",
                    "Angor d'effort probable après 3 épisodes.",
                    "Coronarographie à programmer.",
                ),
            ),
            Visit(
                80, TRABELSI, "Suivi après pose de stent",
                "Stent IVA en juillet. Plus de douleur. Double antiagrégation, statine, "
                "bêtabloquant. 5 cig/jour. TA 134/84. LDL 0,92. Réadaptation refusée. Ne pas "
                "interrompre les antiagrégants.",
                (
                    "Suivi après la pose d'un stent coronaire.",
                    "Stent posé en juillet. Fumeur de 5 cigarettes par jour.",
                    "Tension 134/84.",
                    "Pas de récidive de douleur. LDL à 0,92.",
                    "Double antiagrégation à ne pas interrompre, statine, bêtabloquant. "
                    "Réadaptation cardiaque refusée.",
                ),
            ),
            Visit(
                2, TRABELSI, "Contrôle cardiologique",
                "Asymptomatique. Oubli du bêtabloquant 2 jours par semaine. TA 146/90. Tabac 5/jour. "
                "Rappel : antiagrégants à ne jamais arrêter. Pilulier proposé.",
                status=DRAFT,
            ),
        ),
        documents=(
            Doc("COMPTE_RENDU", "Compte rendu de coronarographie", "Sténose serrée de l'IVA "
                "proximale traitée par un stent actif.", (("Artère", "IVA proximale"),)),
            Doc("ANALYSE", "Bilan lipidique", "LDL 0,92 g/l. HDL 0,38 g/l.",
                (("LDL", "0,92 g/l"),), validated=False),
        ),
        tasks=(
            ("Rappeler la règle d'annulation de 24 h", -100, DONE),
            ("Proposer une nouvelle date de réadaptation cardiaque", 30, CANCELLED),
        ),
        points=(
            "CNAM à jour.",
            "Trois rendez-vous annulés tardivement en 2026, règle rappelée.",
            "Né un 29 février : vérifier l'âge dans les logiciels tiers.",
        ),
        summary="SUPERSEDED",
        next_visit=(23, TRABELSI, "Contrôle de la tension et du tabac", CONFIRMED),
    ),
    "Yasmine Gharsalli": History(  # infant, reflux
        visits=(
            Visit(
                240, BENALI, "Régurgitations du nourrisson",
                "2 mois. Régurgitations après chaque biberon, pleurs aux repas. Poids 4,6 kg. "
                "Lait épaissi. Revoir dans 1 mois.",
                (
                    "Régurgitations du nourrisson.",
                    "Jaunisse néonatale traitée par photothérapie.",
                    "Poids 4,6 kg.",
                    "Reflux du nourrisson probable.",
                    "Lait épaissi. Contrôle dans 1 mois.",
                ),
            ),
            Visit(
                60, BENALI, "Vaccins de 9 mois",
                "Visite des 9 mois. Vaccins du calendrier faits. Poids 8,1 kg, taille 70 cm. Tient assise. "
                "Régurgitations presque disparues.",
                (
                    "Vaccins de 9 mois.",
                    "Reflux dans les premiers mois.",
                    "Poids 8,1 kg, taille 70 cm. Tient assise.",
                    "Bonne croissance, régurgitations presque disparues.",
                    "Vaccins du calendrier réalisés.",
                ),
            ),
            Visit(
                4, BENALI, "Rhume et certificat de crèche",
                "Rhinite depuis 3 jours, 37,8 la veille. Tympans normaux. Lavages de nez. "
                "Certificat crèche renouvelé. Contrôle 12 mois en décembre.",
                status=DRAFT,
            ),
        ),
        documents=(
            Doc("CERTIFICAT", "Certificat pour la crèche", "Enfant apte à la vie en "
                "collectivité.", validated=False),
            Doc("ADMINISTRATIF", "Extrait de naissance", "Déposé le 10/12/2025 pour "
                "l'inscription CNAM.", (("Dépôt", "10/12/2025"),)),
        ),
        tasks=(("Récupérer le groupe sanguin auprès de la maternité", 14, TODO),),
        points=(
            "CIN non applicable.",
            "Inscription comme ayant droit CNAM de la mère en cours.",
        ),
        summary="DRAFT",
        next_visit=(38, BENALI, "Visite des 12 mois et vaccins", CONFIRMED),
    ),
    "Julien Lefèvre": History(  # tourist, erysipelas
        visits=(
            Visit(
                18, BENALI, "Infection de la jambe gauche",
                "Écorchure mollet gauche il y a 3 jours. Jambe rouge, chaude, gonflée. T 38,8. "
                "Glycémie 2,40 g/l. Érysipèle. Antibiotique 10 jours. Jambe surélevée. Contour "
                "dessiné.",
                (
                    "Infection de la jambe gauche.",
                    "Diabète traité par comprimés. Écorchure du mollet il y a 3 jours.",
                    "Jambe rouge, chaude et gonflée. Température 38,8. Glycémie 2,40 g/l.",
                    "Érysipèle de la jambe gauche.",
                    "Antibiotique pendant 10 jours. Jambe surélevée. Contour de la rougeur "
                    "dessiné.",
                ),
            ),
            Visit(
                16, BENALI, "Contrôle à 48 heures",
                "Contrôle à 48 h : rougeur en retrait du contour, apyrétique (37,1). Glycémie "
                "1,85. Poursuite antibiotique.",
                (
                    "Contrôle à 48 heures de l'érysipèle.",
                    "Érysipèle sous antibiotique.",
                    "Rougeur en retrait du contour. Température 37,1. Glycémie 1,85.",
                    "Nette amélioration.",
                    "Poursuite de l'antibiotique.",
                ),
            ),
            Visit(
                3, BENALI, "Fin de traitement",
                "Fin des 10 jours d'antibiotique. Plus de rougeur. Glycémie 1,45. Courrier "
                "pour le médecin traitant en France. Facture pour l'assurance voyage.",
                status=DRAFT,
            ),
        ),
        documents=(
            Doc("ORDONNANCE", "Ordonnance d'antibiotique", "Antibiotique pendant 10 jours.",
                (("Durée", "10 jours"),)),
            Doc("COMPTE_RENDU", "Courrier au médecin traitant", "Érysipèle de la jambe "
                "gauche traité, glycémie à surveiller.", validated=False),
        ),
        tasks=(("Envoyer la facture pour l'assurance voyage", 2, TODO),),
        points=(
            "Touriste de passage, pas de CIN.",
            "Séjourne à Sousse jusqu'à fin novembre 2026.",
            "Facture pour l'assurance voyage.",
        ),
        summary=None,
    ),
}  # fmt: skip

# Free-text appointment requests (Appointment Manager AI).
# (message, days ago, patient key or None, parsed: (days ahead, day part, doctor, specialty, reason) or None)
APPOINTMENT_REQUESTS: list[tuple[str, int, str | None, tuple | None]] = [
    ("Bonjour, je voudrais un rendez-vous la semaine prochaine le matin pour le "
     "renouvellement de mon traitement. Youssef Ben Salah", 3, "DEMO-0002",
     (7, "MORNING", BENALI, "Médecine générale", "Renouvellement d'ordonnance")),
    ("Ma fille Rania a besoin d'un certificat pour le handball, possible un mercredi "
     "après-midi ?", 6, "09856789", (9, "AFTERNOON", BENALI, None, "Certificat sportif")),
    ("Je souhaite voir le cardiologue pour mon contrôle, plutôt jeudi après-midi.", 2,
     "09934567", (11, "AFTERNOON", TRABELSI, "Cardiologie", "Contrôle cardiologique")),
    ("Rendez-vous pour mon père Walid Hammami, pas avant 9h30 s'il vous plaît.", 9,
     "09889012", (7, "MORNING", BENALI, None, "Suivi neurologique et chutes")),
    ("Bonsoir, est-ce qu'il reste de la place demain soir ? J'ai de la fièvre.", 1, None,
     (1, "EVENING", None, None, "Fièvre")),
    ("Je voudrais prendre rendez-vous pour une échographie cardiaque.", 4, "DEMO-0003",
     (14, None, TRABELSI, "Cardiologie", "Échographie cardiaque")),
    ("bonjour svp rdv", 2, None, None),
    ("Je suis touriste à Sousse, besoin d'un médecin pour un contrôle de glycémie.", 12,
     "Julien Lefèvre", None),
]  # fmt: skip
