"""Assert process-cc-statement.json is rewired to the runner, Gemini/Tasks gone."""
import json


def load():
    with open("process-cc-statement.json", encoding="utf-8") as fh:
        return json.load(fh)


def test_gemini_and_tasks_nodes_removed():
    wf = load()
    names = {n["name"] for n in wf["nodes"]}
    types = {n["type"] for n in wf["nodes"]}
    for gone in ("extract info with AI (cc statement)", "AI Agent", "Google Tasks",
                 "split pages", "decompress", "extract text", "gemini-flash-latest"):
        assert gone not in names, f"{gone} should be deleted"
    assert "n8n-nodes-base.googleTasksTool" not in types
    assert "@n8n/n8n-nodes-langchain.informationExtractor" not in types


def test_ingest_node_present_and_multipart():
    wf = load()
    node = next((n for n in wf["nodes"] if n["name"] == "post to statement-app"), None)
    assert node is not None, "post to statement-app node missing"
    p = node["parameters"]
    assert p["method"] == "POST"
    assert "/ingest" in p["url"]
    assert p["contentType"] == "multipart-form-data"
    pnames = {bp.get("name") for bp in p["bodyParameters"]["parameters"]}
    assert {"file", "bank"} <= pnames


def test_unlock_still_present_and_keeps_credentials():
    wf = load()
    unlock = next((n for n in wf["nodes"] if n["name"] == "unlock pdf"), None)
    assert unlock is not None
    assert unlock["credentials"]["httpHeaderAuth"]["id"] == "wWP2trG8rMNF7wt7"


def test_connections_route_unlock_to_ingest_to_markread():
    wf = load()
    conns = wf["connections"]
    assert "unlock pdf" in conns
    nxt = conns["unlock pdf"]["main"][0][0]["node"]
    assert nxt == "post to statement-app"
    assert conns["post to statement-app"]["main"][0][0]["node"] == "mark email read"
