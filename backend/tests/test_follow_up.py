from datetime import date

TASK = {
    "description": "Rappeler la patiente pour reprogrammer l'échographie",
    "due_date": "2026-11-03",
    "patient_name": "Amira Gharbi",
    "appointment_date": "2026-11-10",
    "appointment_reason": "Échographie cardiaque",
}


async def test_tasks_pass_the_schema_validator(api_client, db):
    created = await api_client.post("/api/follow-up/tasks", json=TASK)
    stored = await db["followup_tasks"].find_one()

    assert created.status_code == 201
    assert created.json()["status"] == "pending"
    assert stored["status"] == "TODO" and stored["patientName"] == "Amira Gharbi"
    assert stored["dueDate"].date() == date(2026, 11, 3)


async def test_task_round_trip(api_client):
    task = (await api_client.post("/api/follow-up/tasks", json=TASK)).json()
    await api_client.post("/api/follow-up/tasks", json={**TASK, "due_date": "2026-11-01"})

    done = await api_client.patch(f"/api/follow-up/tasks/{task['id']}", json={"status": "done"})
    listing = await api_client.get("/api/follow-up/tasks")
    pending = await api_client.get("/api/follow-up/tasks", params={"status": "pending"})
    stats = await api_client.get("/api/follow-up/tasks/stats")

    assert done.status_code == 200 and done.json()["status"] == "done"
    assert [item["due_date"] for item in listing.json()] == ["2026-11-01", "2026-11-03"]
    assert len(pending.json()) == 1
    assert stats.json() == {"total": 2, "pending": 1, "done": 1, "cancelled": 0}
