"""Assert reminder-bills.json wiring + that the Code node filter logic is present."""
import json


def test_reminder_workflow_shape():
    with open("reminder-bills.json", encoding="utf-8") as fh:
        wf = json.load(fh)
    names = {n["name"] for n in wf["nodes"]}
    assert {"daily 9am", "get bills", "due in 3 days", "telegram reminder"} <= names
    schedule = next(n for n in wf["nodes"] if n["name"] == "daily 9am")
    assert schedule["type"] == "n8n-nodes-base.scheduleTrigger"
    getbills = next(n for n in wf["nodes"] if n["name"] == "get bills")
    assert getbills["parameters"]["url"].endswith("/bills")
    code = next(n for n in wf["nodes"] if n["name"] == "due in 3 days")
    assert "payment_due_date" in code["parameters"]["jsCode"]
    assert "Asia/Kuala_Lumpur" in code["parameters"]["jsCode"]
    conns = wf["connections"]
    assert conns["get bills"]["main"][0][0]["node"] == "due in 3 days"
    assert conns["due in 3 days"]["main"][0][0]["node"] == "telegram reminder"
