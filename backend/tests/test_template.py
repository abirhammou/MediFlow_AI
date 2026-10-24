import pytest


@pytest.mark.asyncio
async def test_notes_crud_and_summary(client, mock_database):
    created = await client.post(
        "/api/notes/",
        json={"title": "Compte rendu", "content": "Note médicale de test."},
    )
    assert created.status_code == 201
    note = created.json()

    listed = await client.get("/api/notes/")
    assert listed.status_code == 200
    assert listed.json() == [note]

    fetched = await client.get(f"/api/notes/{note['id']}")
    assert fetched.json() == note

    updated = await client.put(
        f"/api/notes/{note['id']}",
        json={"title": "Compte rendu modifié"},
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "Compte rendu modifié"

    summary = await client.post(
        "/api/notes/summarize",
        json={"content": "Note médicale de test."},
    )
    assert summary.status_code == 200
    assert summary.json()["summary"]

    deleted = await client.delete(f"/api/notes/{note['id']}")
    assert deleted.status_code == 204
    missing = await client.get(f"/api/notes/{note['id']}")
    assert missing.status_code == 404
    assert missing.json()["code"] == "note_not_found"
