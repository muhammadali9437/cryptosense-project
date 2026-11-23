import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.routers import chat as chat_router
from app.services.agents import AGENT_ROLES


class ChatEndpointTests(unittest.TestCase):
    def test_chat_returns_all_six_specialist_reports(self):
        reports = [
            {"name": name, "status": "available", "summary": name, "data": {}}
            for name in AGENT_ROLES
        ]
        with (
            patch.object(chat_router, "fear_greed", new=AsyncMock(return_value=[])),
            patch.object(chat_router, "all_signals", new=AsyncMock(return_value=[])),
            patch.object(chat_router, "prices", new=AsyncMock(return_value={})),
            patch.object(chat_router, "run_specialists", new=AsyncMock(return_value=reports)),
            patch.object(chat_router.sage, "answer", new=AsyncMock(
                return_value=("Risk summary", "rules", [])
            )),
        ):
            response = TestClient(app).post("/api/chat", json={"question": "BTC risk"})

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["answer"], "Risk summary")
        self.assertEqual([report["name"] for report in body["agents"]], list(AGENT_ROLES))

    def test_agent_directory_describes_six_roles(self):
        response = TestClient(app).get("/api/chat/agents")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(response.json()), 6)
