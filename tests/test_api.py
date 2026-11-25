def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["engine"] == "mock"


def test_crud_flow(client):
    # create
    r = client.post("/api/transcriptions", json={"title": "Hello", "text": "नमस्ते world", "language": "hi,en"})
    assert r.status_code == 201
    obj = r.json()
    tid = obj["id"]
    assert obj["text"] == "नमस्ते world" and obj["source"] == "manual"

    # read
    assert client.get(f"/api/transcriptions/{tid}").json()["title"] == "Hello"

    # list + search
    lst = client.get("/api/transcriptions", params={"q": "नमस्ते"}).json()
    assert lst["total"] >= 1 and any(i["id"] == tid for i in lst["items"])
    assert client.get("/api/transcriptions", params={"q": "zzz-nope"}).json()["total"] == 0

    # update
    r = client.put(f"/api/transcriptions/{tid}", json={"text": "edited text"})
    assert r.status_code == 200 and r.json()["text"] == "edited text"
    assert r.json()["title"] == "Hello"  # untouched field preserved

    # delete
    assert client.delete(f"/api/transcriptions/{tid}").status_code == 204
    assert client.get(f"/api/transcriptions/{tid}").status_code == 404
    assert client.delete(f"/api/transcriptions/{tid}").status_code == 404


def test_default_title_when_missing(client):
    r = client.post("/api/transcriptions", json={"text": "x"})
    assert r.status_code == 201 and r.json()["title"].startswith("Note ")


def test_frontend_served(client):
    assert "Live Speech" in client.get("/").text
    assert client.get("/static/app.js").status_code == 200
