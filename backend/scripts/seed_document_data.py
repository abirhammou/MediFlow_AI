"""Medical documents of the demo patients, used by scripts.seed_modules and scripts.seed_files.

One entry per patient of scripts.seed_clinical_data (same keys), consistent with their
visits: lab results, imaging reports (MRI, CT, X-ray, ultrasound, ECG), prescriptions,
certificates, letters and administrative papers. Each document is stored as a MedDoc
document (its full text) and as a file of the patient record (PDF, or PNG for the
scanned papers, plus a JPEG of the exam for imaging). All data is fictitious.

`{date}` in a text or a field value is replaced by the date of the document. Every
extracted field value appears word for word in the text, as required by
documents.guardrails.validate_extracted_fields.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Lab:
    lab: str
    rows: tuple[tuple[str, str, str], ...]  # (analysis, result, reference values)
    comment: str


@dataclass(frozen=True)
class Imaging:
    centre: str
    indication: str
    technique: str
    findings: tuple[str, ...]
    conclusion: str
    signed_by: str
    # IRM, SCANNER, RADIO, ECHO, ECG or ANGIO: an image of the exam is stored too
    modality: str | None = None
    requested_by: str | None = None  # None: the patient's doctor at that date


@dataclass(frozen=True)
class Prescription:
    items: tuple[tuple[str, str], ...]  # (medicine, exam or care, instructions)
    note: str = ""


@dataclass(frozen=True)
class Letter:
    issuer: str | None  # None: the doctor's practice
    paragraphs: tuple[str, ...]
    signed_by: str | None = None  # None: the patient's doctor at that date


@dataclass(frozen=True)
class Doc:
    category: str  # documents.schemas.DocumentCategoryCode
    title: str
    days_ago: int
    body: Lab | Imaging | Prescription | Letter
    fields: tuple[tuple[str, str], ...] = ()
    validated: bool = True  # False: AI suggestion and extracted fields still to review


LAB_ENNOUR = "Laboratoire d'analyses médicales Ennour, 14 rue de Marseille, Tunis"
LAB_ELAMEL = "Laboratoire de biologie médicale El Amel, avenue Habib Bourguiba, Ariana"
IMG_MANAR = "Centre d'imagerie médicale El Manar, Tunis"
IMG_LAC = "Centre de radiologie Les Berges du Lac, Tunis"
CARDIO = "Clinique MediFlow, unité de cardiologie, Tunis"
CLINIC = "Clinique MediFlow, Tunis"
BILLING = "Clinique MediFlow, service de facturation, Tunis"
CNAM = "Caisse nationale d'assurance maladie, centre régional de Tunis"
ER = "Service des urgences, clinique Ennasr, Tunis"

AYARI = "Dr Salma Ayari, médecin radiologue"
KALLEL = "Dr Nizar Kallel, médecin radiologue"
TRABELSI_SIGN = "Dr Mehdi Trabelsi, cardiologue"
SAADAOUI = "Dr Rym Saadaoui, biologiste"
FERJANI = "Dr Anis Ferjani, biologiste"

MEDICAL, ORDONNANCE, CERTIFICAT = "MEDICAL", "ORDONNANCE", "CERTIFICAT"
FINANCIER, CNAM_CODE, ADMINISTRATIF = "FINANCIER", "CNAM", "ADMINISTRATIF"


DOCUMENTS: dict[str, tuple[Doc, ...]] = {
    "DEMO-0001": (  # Leila Haddad, hypertension
        Doc(
            MEDICAL,
            "Bilan lipidique et rénal",
            214,
            Lab(
                LAB_ENNOUR,
                (
                    ("Créatinine", "7,8 mg/l", "6,0 à 12,0 mg/l"),
                    ("DFG estimé (CKD-EPI)", "98 ml/min/1,73 m²", "supérieur à 90"),
                    ("Potassium", "4,2 mmol/l", "3,5 à 5,0 mmol/l"),
                    ("Cholestérol total", "2,45 g/l", "inférieur à 2,00 g/l"),
                    ("LDL cholestérol", "1,65 g/l", "objectif inférieur à 1,60 g/l"),
                    ("HDL cholestérol", "0,52 g/l", "supérieur à 0,40 g/l"),
                    ("Triglycérides", "1,40 g/l", "inférieur à 1,50 g/l"),
                    ("Glycémie à jeun", "0,94 g/l", "0,70 à 1,10 g/l"),
                ),
                "Fonction rénale normale. LDL cholestérol légèrement au-dessus de l'objectif.",
            ),
            (("LDL", "1,65 g/l"), ("Créatinine", "7,8 mg/l")),
        ),
        Doc(
            MEDICAL,
            "Échographie cardiaque",
            45,
            Imaging(
                CARDIO,
                "Hypertension artérielle, œdèmes des chevilles. Bilan annuel.",
                "Échographie transthoracique, coupes parasternales, apicales et sous-costales.",
                (
                    "Ventricule gauche non dilaté (diamètre télédiastolique 48 mm).",
                    "Pas d'hypertrophie : septum interventriculaire 10 mm.",
                    "Fonction systolique conservée, FEVG 62 % (Simpson biplan).",
                    "Valves fines, pas de valvulopathie.",
                    "Oreillette gauche non dilatée. Ventricule droit normal.",
                    "Pressions pulmonaires normales (PAPS 25 mmHg). Péricarde sec.",
                ),
                "Échographie cardiaque normale, sans cardiopathie hypertensive.",
                TRABELSI_SIGN,
                modality="ECHO",
            ),
            (("FEVG", "62 %"),),
            validated=False,
        ),
        Doc(
            ORDONNANCE,
            "Ordonnance périndopril",
            45,
            Prescription(
                (("Périndopril 4 mg", "1 comprimé le matin. Traitement pour 3 mois."),),
                "Arrêter l'amlodipine 5 mg. Kaliémie et créatinine dans 6 semaines.",
            ),
            (("Médicament", "Périndopril 4 mg"), ("Durée", "3 mois")),
        ),
    ),
    "DEMO-0002": (  # Youssef Ben Salah, type 2 diabetes
        Doc(
            MEDICAL,
            "Hémoglobine glyquée",
            66,
            Lab(
                LAB_ELAMEL,
                (
                    ("Hémoglobine glyquée (HbA1c)", "7,6 %", "objectif inférieur à 7,0 %"),
                    ("Glycémie à jeun", "1,42 g/l", "0,70 à 1,10 g/l"),
                    ("Créatinine", "9,1 mg/l", "7,0 à 13,0 mg/l"),
                    ("Microalbuminurie", "22 mg/24 h", "inférieure à 30 mg/24 h"),
                    ("LDL cholestérol", "0,98 g/l", "objectif inférieur à 1,00 g/l"),
                ),
                "Amélioration par rapport au dosage précédent (HbA1c 8,4 %). Pas d'atteinte "
                "rénale.",
            ),
            (("HbA1c", "7,6 %"), ("Glycémie à jeun", "1,42 g/l")),
        ),
        Doc(
            CNAM_CODE,
            "Accord APCI CNAM",
            250,
            Letter(
                CNAM,
                (
                    "Objet : décision de prise en charge au titre des affections prolongées "
                    "et chroniques (APCI).",
                    "Affection reconnue : diabète de type 2.",
                    "Les soins en rapport avec cette affection sont pris en charge "
                    "intégralement jusqu'au 31/03/2027.",
                    "Médecin de famille déclaré : Dr Hela Benali.",
                    "Le renouvellement doit être demandé deux mois avant l'échéance.",
                ),
                "Le médecin conseil",
            ),
            (("Validité", "31/03/2027"),),
        ),
        Doc(
            ORDONNANCE,
            "Ordonnance de renouvellement du traitement du diabète",
            60,
            Prescription(
                (
                    ("Metformine 1000 mg", "1 comprimé matin et soir, au milieu du repas."),
                    ("Gliclazide 60 mg", "1 comprimé le matin."),
                    ("Bandelettes et lancettes", "1 boîte de 50 par mois."),
                ),
                "Traitement pour 3 mois. Fond d'œil à programmer chez l'ophtalmologiste.",
            ),
            (("Durée", "3 mois"),),
        ),
        Doc(
            ORDONNANCE,
            "Ordonnance de pédicurie",
            2,
            Prescription(
                (
                    (
                        "Soins de pédicurie-podologie",
                        "4 séances. Callosité du talon droit chez un patient diabétique.",
                    ),
                ),
                "Ne pas marcher pieds nus. Examen des pieds chaque soir.",
            ),
            (("Séances", "4 séances"),),
            validated=False,
        ),
    ),
    "DEMO-0003": (  # Amira Gharbi, palpitations
        Doc(
            MEDICAL,
            "Lettre d'adressage en cardiologie",
            130,
            Letter(
                None,
                (
                    "Cher confrère,",
                    "Je vous adresse cette patiente pour des épisodes de palpitations le soir, "
                    "depuis fin 2025, durant 5 à 30 minutes.",
                    "Elle boit 4 cafés par jour et dort peu. Examen clinique normal, FC 78/min, "
                    "TA 118/72 mmHg. ECG de repos normal.",
                    "Je vous remercie de bien vouloir réaliser un Holter ECG de 24 heures. Le "
                    "dosage de la TSH est en cours.",
                    "Bien confraternellement.",
                ),
            ),
            (("Examen demandé", "Holter ECG de 24 heures"),),
        ),
        Doc(
            MEDICAL,
            "TSH",
            125,
            Lab(
                LAB_ENNOUR,
                (
                    ("TSH ultrasensible", "1,9 mUI/l", "0,4 à 4,0 mUI/l"),
                    ("T4 libre", "14,2 pmol/l", "10,0 à 22,0 pmol/l"),
                    ("Hémoglobine", "13,1 g/dl", "12,0 à 16,0 g/dl"),
                    ("Ferritine", "45 µg/l", "15 à 150 µg/l"),
                ),
                "Bilan thyroïdien normal. Pas d'anémie.",
            ),
            (("TSH", "1,9 mUI/l"),),
            validated=False,
        ),
        Doc(
            MEDICAL,
            "Compte rendu du Holter",
            40,
            Imaging(
                CARDIO,
                "Palpitations du soir, ECG de repos normal.",
                "Enregistrement Holter ECG de 24 heures, 3 voies, avec journal des symptômes.",
                (
                    "Rythme sinusal permanent.",
                    "FC moyenne 82/min, minimale 54/min pendant le sommeil, maximale 130/min.",
                    "Extrasystoles auriculaires rares (38 sur 24 heures), isolées.",
                    "Pas d'extrasystole ventriculaire significative, pas de pause.",
                    "Épisode ressenti à 21 h 40 : tachycardie sinusale à 130/min.",
                ),
                "Pas d'arythmie grave. Les palpitations correspondent à une tachycardie sinusale.",
                TRABELSI_SIGN,
                modality="ECG",
            ),
            (("FC moyenne", "82/min"),),
        ),
    ),
    "DEMO-0004": (  # Karim Jaziri, knee replacement then low back pain
        Doc(
            MEDICAL,
            "IRM du genou droit",
            520,
            Imaging(
                IMG_LAC,
                "Gonalgie droite mécanique invalidante. Bilan avant chirurgie.",
                "IRM 1,5 T, séquences sagittales DP avec saturation de la graisse, coronales "
                "T1 et axiales T2.",
                (
                    "Pincement fémoro-tibial interne complet avec ostéophytose marginale.",
                    "Œdème osseux sous-chondral du plateau tibial interne.",
                    "Lésion dégénérative complexe de la corne postérieure du ménisque interne.",
                    "Épanchement articulaire modéré, kyste poplité de 25 mm.",
                    "Ligaments croisés et collatéraux continus.",
                ),
                "Gonarthrose fémoro-tibiale interne évoluée. Indication chirurgicale à discuter.",
                AYARI,
                modality="IRM",
                requested_by="Dr Lotfi Mabrouk, chirurgien orthopédiste",
            ),
            (("Conclusion", "Gonarthrose fémoro-tibiale interne évoluée"),),
        ),
        Doc(
            MEDICAL,
            "Radiographie du genou droit",
            335,
            Imaging(
                IMG_MANAR,
                "Contrôle à 10 mois d'une prothèse totale du genou droit.",
                "Genou droit de face et de profil en charge, défilé fémoro-patellaire.",
                (
                    "Prothèse totale du genou en place, bien axée.",
                    "Pas de liseré péri-prothétique, pas de signe de descellement.",
                    "Pas de fracture péri-prothétique.",
                    "Rotule centrée.",
                ),
                "Prothèse totale du genou droit en bonne position, sans complication.",
                KALLEL,
                modality="RADIO",
            ),
            validated=False,
        ),
        Doc(
            ORDONNANCE,
            "Ordonnance kinésithérapie",
            50,
            Prescription(
                (
                    (
                        "Kinésithérapie lombaire",
                        "10 séances, 2 à 3 par semaine : renforcement du tronc, étirements, "
                        "école du dos.",
                    ),
                    ("Paracétamol 1 g", "1 comprimé 3 fois par jour si douleur, 15 jours."),
                ),
                "Pas d'anti-inflammatoire (hypertension).",
            ),
            (("Séances", "10 séances"),),
        ),
        Doc(
            FINANCIER,
            "Relance facture de mars",
            197,
            Letter(
                BILLING,
                (
                    "Objet : relance pour la facture de mars 2026.",
                    "Sauf erreur de notre part, la facture de votre consultation de mars 2026 "
                    "reste impayée à ce jour.",
                    "Votre assurance privée attend la feuille de soins signée. Merci de nous la "
                    "retourner ou de régler le reste à charge au secrétariat.",
                    "Relance envoyée le {date}.",
                ),
                "Le service de facturation",
            ),
            (("Date de relance", "{date}"),),
            validated=False,
        ),
    ),
    "DEMO-0005": (  # Nour Mansouri, vaccinations before moving abroad
        Doc(
            MEDICAL,
            "Sérologies rougeole et hépatite B",
            45,
            Lab(
                LAB_ELAMEL,
                (
                    ("IgG anti-rougeole", "210 UI/l, positives", "positif au-dessus de 150 UI/l"),
                    ("Anticorps anti-HBs", "inférieurs à 2 UI/l", "protection à partir de 10 UI/l"),
                    ("Antigène HBs", "négatif", "négatif"),
                    ("Anticorps anti-HBc", "négatifs", "négatifs"),
                ),
                "Rougeole : immunisée. Hépatite B : non immunisée, vaccination recommandée.",
            ),
            (("Rougeole", "Immunisée"), ("Hépatite B", "Non immunisée")),
        ),
        Doc(
            ORDONNANCE,
            "Ordonnance de vaccination hépatite B",
            30,
            Prescription(
                (
                    (
                        "Vaccin contre l'hépatite B, dosage adulte",
                        "3 doses : J0, 1 mois, 6 mois.",
                    ),
                ),
                "Injection en position allongée (malaise lors d'une prise de sang en 2021). "
                "Surveillance de 15 minutes.",
            ),
            (("Schéma", "J0, 1 mois, 6 mois"),),
        ),
        Doc(
            CERTIFICAT,
            "Certificat de vaccination",
            1,
            Letter(
                None,
                (
                    "Je soussignée, Dr Hela Benali, certifie que la patiente a reçu :",
                    "- un rappel diphtérie-tétanos-poliomyélite le mois dernier, bien toléré ;",
                    "- ce jour, la première dose du vaccin contre l'hépatite B (deuxième dose "
                    "dans 1 mois, troisième dans 6 mois).",
                    "Sérologie rougeole positive : patiente immunisée.",
                    "Certificat établi à la demande de l'intéressée pour son départ en "
                    "Allemagne. Une version en anglais est demandée.",
                ),
            ),
            validated=False,
        ),
    ),
    "09812345": (  # Mohamed Ben Ammar, heart failure
        Doc(
            MEDICAL,
            "Compte rendu d'hospitalisation",
            636,
            Letter(
                "Service de cardiologie, clinique Les Oliviers, Tunis",
                (
                    "Hospitalisation de janvier 2025 pour insuffisance cardiaque aiguë inaugurale.",
                    "À l'entrée : fibrillation atriale à 130/min, œdèmes des membres "
                    "inférieurs. FEVG 40 % à l'échographie.",
                    "Évolution favorable sous diurétiques intraveineux. Poids de sortie 81 kg.",
                    "Traitement de sortie : anticoagulant, bêtabloquant, diurétique et "
                    "traitement de l'insuffisance cardiaque.",
                    "Allergie à la pénicilline signalée par la famille, non documentée.",
                    "Suivi : consultation de cardiologie à 1 mois, pesée quotidienne.",
                ),
                "Le chef de service",
            ),
            (("FEVG", "40 %"),),
            validated=False,
        ),
        Doc(
            MEDICAL,
            "IRM cardiaque",
            628,
            Imaging(
                IMG_LAC,
                "Insuffisance cardiaque inaugurale avec fibrillation atriale. Recherche de "
                "la cause.",
                "IRM cardiaque 1,5 T, ciné SSFP, séquences de rehaussement tardif après "
                "gadolinium.",
                (
                    "Ventricule gauche dilaté (volume télédiastolique 112 ml/m²).",
                    "Hypokinésie globale, FEVG 38 %.",
                    "Pas de rehaussement tardif d'allure ischémique.",
                    "Oreillette gauche dilatée. Ventricule droit normal.",
                    "Pas d'épanchement péricardique.",
                ),
                "Cardiomyopathie dilatée non ischémique avec altération modérée de la "
                "fonction systolique.",
                AYARI,
                modality="IRM",
                requested_by="Service de cardiologie, clinique Les Oliviers",
            ),
            (("FEVG", "38 %"),),
        ),
        Doc(
            MEDICAL,
            "Ionogramme et fonction rénale",
            37,
            Lab(
                LAB_ENNOUR,
                (
                    ("Sodium", "139 mmol/l", "135 à 145 mmol/l"),
                    ("Potassium", "4,6 mmol/l", "3,5 à 5,0 mmol/l"),
                    ("Créatinine", "12 mg/l", "7,0 à 13,0 mg/l"),
                    ("DFG estimé (CKD-EPI)", "62 ml/min/1,73 m²", "supérieur à 60"),
                    ("NT-proBNP", "680 pg/ml", "inférieur à 450 pg/ml"),
                ),
                "Kaliémie et fonction rénale stables sous traitement. NT-proBNP modérément élevé.",
            ),
            (("Potassium", "4,6 mmol/l"), ("Créatinine", "12 mg/l")),
        ),
        Doc(
            ORDONNANCE,
            "Ordonnance du traitement cardiaque",
            35,
            Prescription(
                (
                    ("Apixaban 5 mg", "1 comprimé matin et soir."),
                    ("Bisoprolol 5 mg", "1 comprimé le matin."),
                    ("Furosémide 40 mg", "1 comprimé le matin."),
                    ("Sacubitril/valsartan 49/51 mg", "1 comprimé matin et soir."),
                ),
                "Traitement pour 3 mois. Pesée quotidienne : appeler si +2 kg en 3 jours.",
            ),
            (("Durée", "3 mois"),),
        ),
    ),
    "09823456": (  # Fatma Trabelsi, exhaustion, iron deficiency
        Doc(
            CERTIFICAT,
            "Arrêt de travail initial",
            250,
            Letter(
                None,
                (
                    "Avis d'arrêt de travail.",
                    "Je soussignée, Dr Hela Benali, certifie avoir examiné ce jour la patiente.",
                    "Son état de santé nécessite un arrêt de travail de 14 jours à compter de "
                    "ce jour.",
                    "Sorties autorisées.",
                ),
            ),
            (("Durée", "14 jours"),),
        ),
        Doc(
            MEDICAL,
            "Bilan martial",
            60,
            Lab(
                LAB_ENNOUR,
                (
                    ("Ferritine", "28 µg/l", "15 à 150 µg/l"),
                    ("Hémoglobine", "12,4 g/dl", "12,0 à 16,0 g/dl"),
                    ("VGM", "84 fl", "80 à 100 fl"),
                    ("Fer sérique", "11 µmol/l", "9 à 30 µmol/l"),
                    ("CRP", "1 mg/l", "inférieure à 5 mg/l"),
                ),
                "Nette amélioration depuis le bilan précédent (ferritine 9 µg/l, hémoglobine "
                "11,2 g/dl).",
            ),
            (("Ferritine", "28 µg/l"), ("Hémoglobine", "12,4 g/dl")),
        ),
        Doc(
            CERTIFICAT,
            "Certificat d'aptitude 2026",
            3,
            Letter(
                None,
                (
                    "Je soussignée, Dr Hela Benali, certifie que l'état de santé de la "
                    "patiente ne présente pas de contre-indication à l'enseignement pour "
                    "l'année scolaire 2026-2027.",
                    "Certificat remis en main propre pour servir et valoir ce que de droit.",
                ),
            ),
            (("Année scolaire", "2026-2027"),),
            validated=False,
        ),
    ),
    "09834567": (  # Ahmed Chaabane, work accident, right shoulder
        Doc(
            CERTIFICAT,
            "Certificat d'accident du travail",
            160,
            Letter(
                None,
                (
                    "Certificat médical initial d'accident du travail.",
                    "Accident survenu ce jour : chute d'une échelle sur le lieu de travail, "
                    "réception sur le bras droit.",
                    "Lésions constatées : entorse de l'épaule droite, sans fracture à la "
                    "radiographie. Douleur cotée à 7/10, immobilisation par écharpe.",
                    "Arrêt de travail de 10 jours, sauf complication.",
                ),
            ),
            (("Arrêt", "10 jours"),),
        ),
        Doc(
            MEDICAL,
            "Radiographie de l'épaule droite",
            161,
            Imaging(
                ER,
                "Chute d'une échelle, réception sur le bras droit. Recherche de fracture.",
                "Épaule droite de face en rotations neutre, interne et externe, profil de coiffe.",
                (
                    "Pas de fracture visible.",
                    "Pas de luxation gléno-humérale ni acromio-claviculaire.",
                    "Espace sous-acromial conservé.",
                    "Pas de calcification tendineuse.",
                ),
                "Radiographie de l'épaule droite normale.",
                KALLEL,
                modality="RADIO",
                requested_by="Service des urgences",
            ),
            (("Conclusion", "Radiographie de l'épaule droite normale"),),
        ),
        Doc(
            ORDONNANCE,
            "Prescription d'échographie",
            65,
            Prescription(
                (
                    (
                        "Échographie de l'épaule droite",
                        "Recherche d'une tendinopathie ou d'une rupture de la coiffe des "
                        "rotateurs. Abduction limitée à 90°.",
                    ),
                    ("Paracétamol 1 g", "1 comprimé jusqu'à 3 fois par jour si douleur."),
                ),
            ),
            (("Examen", "Échographie de l'épaule droite"),),
            validated=False,
        ),
        Doc(
            MEDICAL,
            "Demande d'aménagement de poste",
            64,
            Letter(
                None,
                (
                    "À l'attention du médecin du travail.",
                    "Le patient garde une épaule droite douloureuse depuis son accident du "
                    "travail, avec une abduction limitée à 90°.",
                    "Je préconise d'éviter le port de charges lourdes et les gestes bras "
                    "au-dessus de l'épaule pendant 2 mois.",
                    "Merci de bien vouloir étudier un aménagement de son poste.",
                ),
            ),
            (("Durée", "2 mois"),),
        ),
    ),
    "09845678": (  # Sonia Dridi, rheumatoid arthritis and osteoporosis
        Doc(
            MEDICAL,
            "Radiographie des mains et des poignets",
            190,
            Imaging(
                IMG_MANAR,
                "Polyarthrite rhumatoïde sous méthotrexate. Bilan structural annuel.",
                "Mains et poignets de face, pieds de face et de trois quarts.",
                (
                    "Déminéralisation en bande épiphysaire.",
                    "Pincement des articulations métacarpo-phalangiennes 2 et 3 droites.",
                    "Pas d'érosion nouvelle par rapport aux clichés de 2024.",
                    "Pincement radio-carpien droit débutant. Pieds sans érosion.",
                ),
                "Polyarthrite rhumatoïde sans progression structurale nette.",
                KALLEL,
                modality="RADIO",
            ),
            (("Conclusion", "Polyarthrite rhumatoïde sans progression structurale nette"),),
        ),
        Doc(
            ADMINISTRATIF,
            "Autorisation de récupération des résultats",
            289,
            Letter(
                "Document remis par la patiente",
                (
                    "Je soussignée, Sonia Dridi, autorise mon frère, Hichem Dridi, à "
                    "récupérer mes résultats d'analyses et mes comptes rendus auprès de la "
                    "clinique MediFlow.",
                    "Fait à Tunis, le {date}.",
                ),
                "Signature de la patiente",
            ),
            (("Personne autorisée", "Hichem Dridi"),),
        ),
        Doc(
            MEDICAL,
            "Densitométrie osseuse",
            75,
            Imaging(
                IMG_MANAR,
                "Polyarthrite rhumatoïde, ménopause. Dépistage de l'ostéoporose.",
                "Absorptiométrie biphotonique (DXA) du rachis lombaire et de la hanche gauche.",
                (
                    "Rachis lombaire L1-L4 : densité 0,742 g/cm², T-score -2,8, Z-score -1,9.",
                    "Col fémoral gauche : densité 0,701 g/cm², T-score -2,1.",
                    "Hanche totale gauche : T-score -1,8.",
                ),
                "Ostéoporose densitométrique au rachis lombaire, ostéopénie fémorale.",
                AYARI,
            ),
            (("T-score rachis", "-2,8"), ("T-score col", "-2,1")),
        ),
        Doc(
            MEDICAL,
            "Bilan de surveillance du méthotrexate",
            73,
            Lab(
                LAB_ELAMEL,
                (
                    ("Hémoglobine", "12,9 g/dl", "12,0 à 16,0 g/dl"),
                    ("Leucocytes", "6 200/mm³", "4 000 à 10 000/mm³"),
                    ("Plaquettes", "254 000/mm³", "150 000 à 400 000/mm³"),
                    ("ASAT", "24 UI/l", "inférieur à 35 UI/l"),
                    ("ALAT", "29 UI/l", "inférieur à 35 UI/l"),
                    ("Créatinine", "7,2 mg/l", "6,0 à 12,0 mg/l"),
                    ("Vitamine D (25-OH)", "18 ng/ml", "30 à 100 ng/ml"),
                ),
                "NFS et transaminases normales. Carence en vitamine D.",
            ),
            (("ALAT", "29 UI/l"), ("Vitamine D", "18 ng/ml")),
            validated=False,
        ),
    ),
    "09856789": (  # Rania Bouazizi, asthma (child)
        Doc(
            CERTIFICAT,
            "Certificat de non-contre-indication au sport",
            200,
            Letter(
                None,
                (
                    "Je soussignée, Dr Hela Benali, certifie avoir examiné ce jour l'enfant et "
                    "n'avoir constaté aucune contre-indication à la pratique du handball en "
                    "club, y compris en compétition, pour la saison 2026-2027.",
                    "Asthme connu et suivi : l'inhalateur de secours doit être emporté à chaque "
                    "entraînement.",
                ),
            ),
            (("Saison", "2026-2027"),),
        ),
        Doc(
            ORDONNANCE,
            "Ordonnance inhalateurs",
            38,
            Prescription(
                (
                    (
                        "Budésonide/formotérol 200/6 µg, inhalateur",
                        "1 inhalation matin et soir, traitement de fond. 2 exemplaires.",
                    ),
                    (
                        "Salbutamol 100 µg, aérosol doseur",
                        "2 bouffées en cas de gêne, à renouveler si besoin. 2 exemplaires.",
                    ),
                    ("Chambre d'inhalation", "1 exemplaire."),
                ),
                "Un inhalateur de chaque sorte dans chacune des deux maisons.",
            ),
            (("Exemplaires", "2 exemplaires"),),
            validated=False,
        ),
        Doc(
            MEDICAL,
            "Plan d'action asthme pour le collège",
            37,
            Letter(
                None,
                (
                    "Plan d'action destiné à l'infirmière scolaire.",
                    "Zone verte (pas de gêne) : traitement de fond matin et soir à la maison. "
                    "Avant le sport : 2 bouffées de salbutamol 15 minutes avant l'effort.",
                    "Zone orange (toux, sifflements, essoufflement) : 2 bouffées de salbutamol "
                    "avec la chambre, à renouveler après 20 minutes si besoin.",
                    "Zone rouge (difficulté à parler, pas d'amélioration après 2 prises) : "
                    "appeler le 190 puis les parents.",
                ),
            ),
            (("Numéro d'urgence", "190"),),
        ),
    ),
    "09867890": (  # Hamza Khemiri, pneumothorax, smoking
        Doc(
            MEDICAL,
            "Scanner thoracique",
            88,
            Imaging(
                IMG_LAC,
                "Douleur thoracique gauche brutale avec essoufflement.",
                "Scanner thoracique sans injection, coupes fines millimétriques.",
                (
                    "Pneumothorax gauche complet avec rétraction du poumon.",
                    "Pas de déviation du médiastin.",
                    "Petites bulles apicales gauches infracentimétriques.",
                    "Poumon droit normal, pas d'épanchement pleural.",
                ),
                "Pneumothorax spontané gauche complet. Drainage indiqué.",
                AYARI,
                modality="SCANNER",
                requested_by="Service des urgences",
            ),
            (("Conclusion", "Pneumothorax spontané gauche complet"),),
        ),
        Doc(
            MEDICAL,
            "Radiographie thoracique de contrôle",
            56,
            Imaging(
                IMG_MANAR,
                "Contrôle à 1 mois d'un pneumothorax gauche drainé.",
                "Thorax de face en inspiration.",
                (
                    "Poumon gauche à la paroi.",
                    "Pas de décollement résiduel.",
                    "Pas d'épanchement pleural.",
                    "Silhouette cardiaque normale.",
                ),
                "Radiographie thoracique normale à 1 mois du drainage.",
                KALLEL,
                modality="RADIO",
            ),
            (("Conclusion", "Radiographie thoracique normale à 1 mois du drainage"),),
        ),
        Doc(
            CERTIFICAT,
            "Certificat d'absence",
            2,
            Letter(
                None,
                (
                    "Je soussignée, Dr Hela Benali, certifie que le patient a été hospitalisé "
                    "pendant 4 jours pour un pneumothorax et n'a pas pu se présenter à ses "
                    "examens universitaires.",
                    "Certificat remis à l'intéressé pour être présenté à sa faculté.",
                ),
            ),
            (("Hospitalisation", "4 jours"),),
            validated=False,
        ),
    ),
    "09878901": (  # Claire Martin, thyroid nodule
        Doc(
            MEDICAL,
            "Bilan thyroïdien",
            122,
            Lab(
                LAB_ENNOUR,
                (
                    ("TSH ultrasensible", "1,8 mUI/l", "0,4 à 4,0 mUI/l"),
                    ("T4 libre", "15,1 pmol/l", "10,0 à 22,0 pmol/l"),
                    ("Anticorps anti-TPO", "12 UI/ml", "inférieurs à 35 UI/ml"),
                    ("Calcitonine", "inférieure à 2 pg/ml", "inférieure à 10 pg/ml"),
                ),
                "Équilibre thyroïdien satisfaisant sous lévothyroxine 75 µg.",
            ),
            (("TSH", "1,8 mUI/l"),),
        ),
        Doc(
            MEDICAL,
            "Échographie thyroïdienne",
            95,
            Imaging(
                IMG_LAC,
                "Nodule palpable de la base du cou à droite.",
                "Échographie cervicale avec sonde linéaire haute fréquence et doppler.",
                (
                    "Thyroïde de taille normale, échostructure homogène.",
                    "Nodule du lobe droit de 18 mm, solide, hypoéchogène, à contours "
                    "réguliers, sans microcalcification.",
                    "Lobe gauche sans nodule.",
                    "Pas d'adénopathie cervicale suspecte.",
                ),
                "Nodule thyroïdien droit de 18 mm, TI-RADS 4. Cytoponction à l'aiguille fine "
                "recommandée.",
                AYARI,
                modality="ECHO",
            ),
            (("Taille", "18 mm"), ("Classification", "TI-RADS 4")),
        ),
        Doc(
            ORDONNANCE,
            "Prescription de cytoponction et de mammographie",
            6,
            Prescription(
                (
                    (
                        "Cytoponction échoguidée du nodule thyroïdien droit",
                        "Nodule de 18 mm classé TI-RADS 4. Cytologie selon Bethesda.",
                    ),
                    (
                        "Mammographie bilatérale et échographie mammaire",
                        "Dépistage, antécédent familial de cancer du sein (mère).",
                    ),
                ),
                "Copie des comptes rendus à adresser à son médecin en France.",
            ),
            validated=False,
        ),
        Doc(
            FINANCIER,
            "Facture détaillée pour l'assureur",
            6,
            Letter(
                BILLING,
                (
                    "Facture détaillée établie en français pour l'assurance privée de la patiente.",
                    "- Consultation de médecine générale (nodule thyroïdien) : 45,000 TND",
                    "- Consultation de médecine générale (résultat de l'échographie) : 45,000 TND",
                    "- Consultation de médecine générale (décision sur la ponction) : 45,000 TND",
                    "Montant total : 135,000 TND.",
                    "Numéro de dossier de l'assureur : à compléter par la patiente.",
                ),
                "Le service de facturation",
            ),
            (("Montant total", "135,000 TND"),),
            validated=False,
        ),
    ),
    "09889012": (  # Walid Hammami, Parkinson's disease, falls
        Doc(
            MEDICAL,
            "IRM cérébrale",
            790,
            Imaging(
                IMG_LAC,
                "Syndrome parkinsonien akinéto-rigide prédominant à droite. Bilan initial.",
                "IRM encéphalique 1,5 T : séquences T1, T2, FLAIR, diffusion et T2*.",
                (
                    "Atrophie cortico-sous-corticale modérée, en rapport avec l'âge.",
                    "Quelques hypersignaux FLAIR punctiformes de la substance blanche (Fazekas 1).",
                    "Noyaux gris centraux et mésencéphale sans anomalie.",
                    "Pas de saignement ancien, pas de lésion ischémique récente.",
                ),
                "Pas d'argument pour un syndrome parkinsonien atypique ou vasculaire.",
                AYARI,
                modality="IRM",
                requested_by="Dr Nabil Jebali, neurologue",
            ),
            (
                (
                    "Conclusion",
                    "Pas d'argument pour un syndrome parkinsonien atypique ou vasculaire",
                ),
            ),
        ),
        Doc(
            MEDICAL,
            "Compte rendu des urgences",
            75,
            Letter(
                ER,
                (
                    "Motif : chute nocturne à domicile en allant aux toilettes, sans perte de "
                    "connaissance.",
                    "Examen : plaie du cuir chevelu de 3 cm, suturée par 5 points. Examen "
                    "neurologique inchangé par rapport à l'état antérieur.",
                    "Scanner cérébral sans injection : normal, pas d'hématome.",
                    "Sortie avec sa fille. Ablation des fils dans 7 jours.",
                ),
                "Le médecin urgentiste",
            ),
            (("Scanner", "Normal"),),
        ),
        Doc(
            MEDICAL,
            "Scanner cérébral",
            75,
            Imaging(
                ER,
                "Chute avec plaie du cuir chevelu chez un patient parkinsonien.",
                "Scanner cérébral sans injection, fenêtres parenchymateuse et osseuse.",
                (
                    "Pas d'hématome intra- ou extra-axial.",
                    "Pas de fracture de la voûte crânienne.",
                    "Hématome sous-cutané pariétal droit.",
                    "Atrophie cortico-sous-corticale stable.",
                ),
                "Pas de lésion traumatique intracrânienne.",
                KALLEL,
                modality="SCANNER",
                requested_by="Service des urgences",
            ),
            validated=False,
        ),
        Doc(
            ORDONNANCE,
            "Ordonnance antiparkinsonienne",
            4,
            Prescription(
                (
                    (
                        "Lévodopa/bensérazide 100/25 mg",
                        "1 gélule à 8 h, 13 h et 19 h, à heures fixes.",
                    ),
                    ("Macrogol 4000", "1 sachet le matin en cas de constipation."),
                    ("Kinésithérapie", "Rééducation de l'équilibre et de la marche, 15 séances."),
                ),
                "Traitement pour 3 mois.",
            ),
            (("Prises", "8 h, 13 h et 19 h"),),
            validated=False,
        ),
    ),
    "09890123": (  # Ines Saidi, irritable bowel
        Doc(
            ADMINISTRATIF,
            "Formulaire d'inscription en ligne",
            104,
            Letter(
                "Formulaire du site de la clinique MediFlow",
                (
                    "Formulaire d'inscription rempli en ligne le {date}.",
                    "Profession : infirmière, gardes de 24 heures.",
                    "Médecin souhaité : Dr Hela Benali.",
                    "Champ remarques : texte incomplet, à revoir avec la patiente.",
                ),
                "Secrétariat",
            ),
            validated=False,
        ),
        Doc(
            MEDICAL,
            "Bilan digestif",
            95,
            Lab(
                LAB_ELAMEL,
                (
                    ("Hémoglobine", "13,4 g/dl", "12,0 à 16,0 g/dl"),
                    ("Leucocytes", "7 100/mm³", "4 000 à 10 000/mm³"),
                    ("CRP", "2 mg/l", "inférieure à 5 mg/l"),
                    (
                        "Anticorps anti-transglutaminase IgA",
                        "inférieurs à 1 U/ml",
                        "négatif en dessous de 10 U/ml",
                    ),
                    ("IgA totales", "2,1 g/l", "0,7 à 4,0 g/l"),
                    ("Ferritine", "34 µg/l", "15 à 150 µg/l"),
                ),
                "NFS normale, pas de syndrome inflammatoire. Sérologie de la maladie cœliaque "
                "négative.",
            ),
            (("CRP", "2 mg/l"),),
        ),
        Doc(
            MEDICAL,
            "Examen des selles",
            93,
            Lab(
                LAB_ELAMEL,
                (
                    ("Examen parasitologique", "absence de parasites", "absence"),
                    ("Coproculture", "flore banale, pas de germe pathogène", "absence"),
                    ("Calprotectine fécale", "32 µg/g", "inférieure à 50 µg/g"),
                ),
                "Pas d'argument pour une maladie inflammatoire de l'intestin.",
            ),
            (("Calprotectine", "32 µg/g"),),
            validated=False,
        ),
    ),
    "09901234": (  # Sami Ferchichi, occupational asthma
        Doc(
            CERTIFICAT,
            "Arrêt de travail",
            33,
            Letter(
                None,
                (
                    "Avis d'arrêt de travail.",
                    "Crise de sifflements survenue sur le lieu de travail, améliorée par le "
                    "salbutamol.",
                    "Arrêt de travail de 5 jours à compter de ce jour.",
                ),
            ),
            (("Durée", "5 jours"),),
        ),
        Doc(
            CNAM_CODE,
            "Attestation CNAM provisoire",
            30,
            Letter(
                CNAM,
                (
                    "Attestation provisoire de droits à l'assurance maladie.",
                    "Valable jusqu'au 30/11/2026, dans l'attente de la carte définitive.",
                    "Filière choisie : médecin de famille.",
                ),
                "Le chef de centre",
            ),
            (("Validité", "30/11/2026"),),
            validated=False,
        ),
        Doc(
            MEDICAL,
            "Spirométries comparées",
            8,
            Lab(
                "Clinique MediFlow, explorations fonctionnelles respiratoires, Tunis",
                (
                    (
                        "VEMS après une semaine de travail",
                        "78 %",
                        "supérieur à 80 % de la théorique",
                    ),
                    ("VEMS après une semaine de congé", "91 %", "supérieur à 80 % de la théorique"),
                    (
                        "CVF après une semaine de travail",
                        "94 %",
                        "supérieure à 80 % de la théorique",
                    ),
                    ("VEMS/CVF après une semaine de travail", "0,68", "supérieur à 0,70"),
                    ("VEMS/CVF après une semaine de congé", "0,79", "supérieur à 0,70"),
                ),
                "Trouble ventilatoire obstructif au travail, qui disparaît pendant le congé.",
            ),
            (("VEMS travail", "78 %"), ("VEMS congé", "91 %")),
        ),
        Doc(
            MEDICAL,
            "Courrier au médecin du travail",
            5,
            Letter(
                None,
                (
                    "Cher confrère,",
                    "Je vois ce patient pour des crises de sifflements survenant au poste de "
                    "travail.",
                    "Le VEMS est à 78 % de la théorique après une semaine de travail et à 91 % "
                    "après une semaine de congé, ce qui évoque un asthme professionnel.",
                    "Je vous remercie de votre avis sur son poste et sur une éventuelle "
                    "déclaration de maladie professionnelle.",
                    "Bien confraternellement.",
                ),
            ),
            (("VEMS travail", "78 %"),),
        ),
    ),
    "09912345": (  # Marwa Ben Youssef, gestational diabetes
        Doc(
            MEDICAL,
            "Courrier de la sage-femme",
            48,
            Letter(
                "Cabinet de sage-femme Hajer Toumi, La Marsa",
                (
                    "Chère consœur,",
                    "Je vous adresse cette patiente, enceinte de 24 semaines, pour un dépistage "
                    "du diabète gestationnel positif.",
                    "Grossesse jusque-là sans particularité. Tension 112/68 mmHg.",
                    "Merci de prendre en charge le suivi glycémique.",
                ),
                "Hajer Toumi, sage-femme",
            ),
            validated=False,
        ),
        Doc(
            MEDICAL,
            "Hyperglycémie provoquée orale",
            47,
            Lab(
                LAB_ENNOUR,
                (
                    ("Glycémie à jeun (T0)", "0,98 g/l", "inférieure à 0,92 g/l"),
                    ("Glycémie à 1 heure (T1h)", "1,85 g/l", "inférieure à 1,80 g/l"),
                    ("Glycémie à 2 heures (T2h)", "1,62 g/l", "inférieure à 1,53 g/l"),
                ),
                "Charge orale de 75 g de glucose à 24 semaines d'aménorrhée. Trois valeurs "
                "au-dessus des seuils : diabète gestationnel.",
            ),
            (("T0", "0,98 g/l"), ("T1h", "1,85 g/l"), ("T2h", "1,62 g/l")),
        ),
        Doc(
            MEDICAL,
            "Échographie du deuxième trimestre",
            50,
            Imaging(
                "Cabinet d'échographie obstétricale, La Marsa",
                "Échographie morphologique du deuxième trimestre.",
                "Échographie obstétricale par voie abdominale.",
                (
                    "Grossesse monofœtale évolutive.",
                    "Biométries au 50e percentile : périmètre crânien, périmètre abdominal et "
                    "longueur fémorale conformes au terme.",
                    "Morphologie fœtale sans anomalie visible.",
                    "Placenta antérieur, liquide amniotique en quantité normale.",
                ),
                "Croissance fœtale normale à 23 semaines d'aménorrhée.",
                "Dr Imen Baccar, échographiste",
                modality="ECHO",
                requested_by="Hajer Toumi, sage-femme",
            ),
            validated=False,
        ),
        Doc(
            ORDONNANCE,
            "Ordonnance d'insuline",
            3,
            Prescription(
                (
                    (
                        "Insuline glargine 100 UI/ml, stylo",
                        "6 UI le soir au coucher, dose à adapter aux glycémies à jeun.",
                    ),
                    (
                        "Lecteur de glycémie, bandelettes et lancettes",
                        "Glycémies 4 fois par jour : à jeun et 2 heures après chaque repas.",
                    ),
                    ("Aiguilles pour stylo 4 mm", "1 boîte."),
                ),
            ),
            (("Dose", "6 UI"),),
        ),
    ),
    "09923456": (  # Alex Mzoughi, panic attacks
        Doc(
            ADMINISTRATIF,
            "Préférences de contact",
            190,
            Letter(
                "Fiche du secrétariat",
                (
                    "Prénom d'usage : Alex. Pas de civilité dans les courriers et les rappels.",
                    "Appels uniquement après 17 h (cours en journée).",
                    "Rappels par SMS acceptés.",
                ),
                "Secrétariat",
            ),
            (("Appels", "après 17 h"),),
        ),
        Doc(
            MEDICAL,
            "Courrier à la psychologue",
            189,
            Letter(
                None,
                (
                    "Chère consœur,",
                    "Je vous adresse Alex pour des crises de panique survenant dans "
                    "les transports : palpitations, sensation d'étouffement, tremblements.",
                    "Le bilan cardiaque réalisé aux urgences est normal. Plusieurs crises par "
                    "semaine. Pas d'idées suicidaires.",
                    "Je vous remercie de votre prise en charge.",
                    "Bien confraternellement.",
                ),
            ),
            (("Motif", "crises de panique"),),
        ),
        Doc(
            CERTIFICAT,
            "Certificats d'absence",
            60,
            Letter(
                None,
                (
                    "Je soussignée, Dr Hela Benali, certifie que l'état de santé de la personne "
                    "nommée ci-dessus a justifié son absence à 2 examens de design ce "
                    "semestre.",
                    "Certificat remis en main propre à l'intéressé·e.",
                ),
            ),
            (("Examens", "2 examens"),),
        ),
    ),
    "09934567": (  # Habib Zouari, coronary stent
        Doc(
            MEDICAL,
            "Épreuve d'effort",
            200,
            Imaging(
                CARDIO,
                "Oppression thoracique d'effort, tabagisme actif.",
                "Épreuve d'effort sur bicyclette ergométrique, paliers de 30 W toutes les "
                "3 minutes.",
                (
                    "Arrêt à 120 W pour oppression thoracique.",
                    "FC maximale 138/min (85 % de la théorique).",
                    "Sous-décalage du segment ST de 2 mm de V4 à V6 à 120 W.",
                    "TA d'effort 196/104 mmHg.",
                ),
                "Épreuve d'effort cliniquement et électriquement positive. Coronarographie "
                "indiquée.",
                TRABELSI_SIGN,
                modality="ECG",
            ),
            (("Conclusion", "positive"),),
        ),
        Doc(
            MEDICAL,
            "Compte rendu de coronarographie",
            100,
            Imaging(
                CARDIO,
                "Épreuve d'effort positive.",
                "Coronarographie par voie radiale droite, puis angioplastie.",
                (
                    "Sténose serrée de 90 % de l'IVA proximale.",
                    "Circonflexe et coronaire droite sans lésion significative.",
                    "Angioplastie de l'IVA proximale avec pose d'un stent actif 3,0 × 18 mm, "
                    "bon résultat.",
                ),
                "Atteinte d'une seule artère, l'IVA proximale, traitée par un stent actif. "
                "Double antiagrégation plaquettaire pendant 12 mois.",
                TRABELSI_SIGN,
                modality="ANGIO",
            ),
            (("Artère", "IVA proximale"),),
        ),
        Doc(
            ORDONNANCE,
            "Ordonnance après pose de stent",
            80,
            Prescription(
                (
                    ("Aspirine 75 mg", "1 sachet par jour, sans interruption."),
                    ("Ticagrélor 90 mg", "1 comprimé matin et soir pendant 12 mois."),
                    ("Atorvastatine 80 mg", "1 comprimé le soir."),
                    ("Bisoprolol 2,5 mg", "1 comprimé le matin."),
                ),
                "Ne jamais interrompre les antiagrégants sans l'avis du cardiologue.",
            ),
            (("Durée", "12 mois"),),
        ),
        Doc(
            MEDICAL,
            "Bilan lipidique",
            82,
            Lab(
                LAB_ENNOUR,
                (
                    ("Cholestérol total", "1,62 g/l", "inférieur à 2,00 g/l"),
                    ("LDL cholestérol", "0,92 g/l", "objectif inférieur à 0,55 g/l"),
                    ("HDL cholestérol", "0,38 g/l", "supérieur à 0,40 g/l"),
                    ("Triglycérides", "1,58 g/l", "inférieur à 1,50 g/l"),
                    ("Hémoglobine glyquée (HbA1c)", "5,9 %", "inférieure à 6,0 %"),
                ),
                "LDL cholestérol au-dessus de l'objectif après la pose du stent.",
            ),
            (("LDL", "0,92 g/l"),),
            validated=False,
        ),
    ),
    "Yasmine Gharsalli": (  # infant
        Doc(
            ADMINISTRATIF,
            "Extrait de naissance",
            320,
            Letter(
                "Document remis par la mère",
                (
                    "Extrait d'acte de naissance déposé au secrétariat le {date} pour "
                    "l'inscription de l'enfant à la CNAM.",
                    "Date de naissance : 01/12/2025.",
                ),
                "Secrétariat",
            ),
            (("Dépôt", "{date}"),),
        ),
        Doc(
            MEDICAL,
            "Carnet de vaccination (copie)",
            60,
            Letter(
                None,
                (
                    "Copie des pages de vaccination du carnet de santé.",
                    "- Naissance : BCG et hépatite B.",
                    "- 2, 3 et 6 mois : vaccins du calendrier national faits.",
                    "- 9 mois : vaccins du calendrier faits ce jour, bien tolérés.",
                    "Poids 8,1 kg, taille 70 cm à la visite des 9 mois.",
                ),
            ),
            (("Poids", "8,1 kg"),),
        ),
        Doc(
            CERTIFICAT,
            "Certificat pour la crèche",
            4,
            Letter(
                None,
                (
                    "Je soussignée, Dr Hela Benali, certifie que l'enfant est à jour de ses "
                    "vaccinations et ne présente pas de contre-indication à la vie en "
                    "collectivité.",
                    "Rhinite banale en cours, sans fièvre ce jour.",
                ),
            ),
            validated=False,
        ),
    ),
    "Julien Lefèvre": (  # French tourist, erysipelas
        Doc(
            MEDICAL,
            "Glycémie et bilan inflammatoire",
            18,
            Lab(
                LAB_ENNOUR,
                (
                    ("Glycémie", "2,40 g/l", "0,70 à 1,10 g/l"),
                    ("Hémoglobine glyquée (HbA1c)", "8,9 %", "inférieure à 6,0 %"),
                    ("CRP", "148 mg/l", "inférieure à 5 mg/l"),
                    ("Leucocytes", "14 800/mm³", "4 000 à 10 000/mm³"),
                    ("Créatinine", "9 mg/l", "7,0 à 13,0 mg/l"),
                ),
                "Syndrome inflammatoire important. Hyperglycémie non connue : bilan de "
                "diabète à prévoir.",
            ),
            (("Glycémie", "2,40 g/l"), ("CRP", "148 mg/l")),
        ),
        Doc(
            ORDONNANCE,
            "Ordonnance d'antibiotique",
            18,
            Prescription(
                (
                    ("Amoxicilline 1 g", "1 comprimé 3 fois par jour pendant 10 jours."),
                    ("Paracétamol 1 g", "Si fièvre ou douleur, 3 comprimés par jour au maximum."),
                ),
                "Jambe surélevée. Contrôle à 48 heures.",
            ),
            (("Durée", "10 jours"),),
        ),
        Doc(
            MEDICAL,
            "Courrier au médecin traitant",
            3,
            Letter(
                None,
                (
                    "Cher confrère,",
                    "Votre patient a été pris en charge pendant son séjour en Tunisie pour un "
                    "érysipèle de la jambe gauche.",
                    "Traitement par amoxicilline pendant 10 jours, évolution favorable, "
                    "apyrexie à 48 heures.",
                    "Glycémie à 2,40 g/l au diagnostic, puis 1,45 g/l en fin de traitement : "
                    "un diabète est à rechercher à votre retour.",
                    "Bien confraternellement.",
                ),
            ),
            validated=False,
        ),
        Doc(
            FINANCIER,
            "Facture pour l'assurance voyage",
            3,
            Letter(
                BILLING,
                (
                    "Facture détaillée pour l'assurance voyage du patient.",
                    "- Consultation initiale (érysipèle) : 45,000 TND",
                    "- Contrôle à 48 heures : 45,000 TND",
                    "- Consultation de fin de traitement : 45,000 TND",
                    "Montant total : 135,000 TND.",
                ),
                "Le service de facturation",
            ),
            (("Montant total", "135,000 TND"),),
        ),
    ),
}
