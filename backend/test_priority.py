"""Test de l'analyse de priorité avec Gemini."""
import asyncio, sys, json
sys.path.insert(0, '.')

async def main():
    from app.core.config import settings
    from app.core.db import create_client, init_db
    from app.llm.providers.gemini import GeminiProvider
    from app.modules.follow_up.prompts import PRIORITY_SYSTEM_PROMPT, priority_prompt
    from app.modules.follow_up.schemas import PriorityResponse
    from datetime import date

    client = create_client(settings.mongodb_uri)
    db = client[settings.mongodb_db]
    await init_db(db)

    # Charger quelques taches
    from app.modules.follow_up.repository import TaskRepository
    repo = TaskRepository(db)
    docs = await repo.list_by_status('pending')
    print(f'{len(docs)} taches pending')

    if not docs:
        print('Aucune tache pending — test avec des données fictives')
        tasks_data = [
            {"task_id": "abc", "patient_name": "Test Patient", "appointment_date": "2026-11-05",
             "appointment_reason": "Controle", "due_date": "2026-11-01", "status": "pending"}
        ]
    else:
        tasks_data = [
            {"task_id": str(d["_id"]), "patient_name": d.get("patient_name",""),
             "appointment_date": d.get("appointment_date",""), "appointment_reason": d.get("appointment_reason",""),
             "due_date": d.get("due_date",""), "status": d.get("status","pending")}
            for d in docs
        ]

    _, _, model, api_key = settings.module_llm('follow_up')
    provider = GeminiProvider(api_key)
    today = date.today().isoformat()

    # Appel direct Gemini
    schema_json = json.dumps(PriorityResponse.model_json_schema(), ensure_ascii=False)
    system = (f"{PRIORITY_SYSTEM_PROMPT}\nRéponds uniquement avec un objet JSON conforme au schéma.\n"
              f"<output_schema>{schema_json}</output_schema>")
    user = priority_prompt(json.dumps(tasks_data, ensure_ascii=False), today)

    print('\nAppel Gemini...')
    raw = await provider.complete_json(system=system, user=user, model=model, timeout=30)
    print('Réponse brute:', raw[:400])

    try:
        data = json.loads(raw)
        result = PriorityResponse.model_validate(data)
        print(f'\nValidation OK : {len(result.tasks)} tache(s)')
    except Exception as e:
        print(f'\nEchec validation: {e}')
        print('Schema attendu:', json.dumps(PriorityResponse.model_json_schema(), indent=2)[:500])

    await client.close()

asyncio.run(main())
