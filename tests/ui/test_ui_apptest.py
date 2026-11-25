"""Streamlit AppTest smoke tests for all pages and interaction scenarios."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
APP_FILE = str(REPO_ROOT / "ui" / "app.py")
DOCS_PAGE = str(REPO_ROOT / "ui" / "pages" / "documents.py")
HOW_IT_WORKS_PAGE = str(REPO_ROOT / "ui" / "pages" / "how_it_works.py")


def test_apptest_chat_page_landing_empty_state():
    """Verify clean landing page with empty state and suggestion chips."""
    at = AppTest.from_file(APP_FILE)
    at.run()
    assert not at.exception, f"App threw unexpected exception: {at.exception}"

    # Verify sample data disclaimer is present in sidebar or page
    banner_found = any("sample data" in str(c.value).lower() for c in at.caption) or any(
        "sample data" in str(m.value).lower() for m in at.markdown
    )
    assert banner_found, "Sample-data disclaimer banner not found"

    # Verify main screen brand header
    brand_header_found = any("MediCare — " in str(m.value) for m in at.markdown)
    assert brand_header_found, "Main-screen brand header not found"


def test_apptest_backend_down_banner(monkeypatch):
    """Verify backend-down banner is displayed gracefully when service is unreachable."""
    monkeypatch.setenv("BACKEND_SERVICE_URL", "http://127.0.0.1:59999")
    at = AppTest.from_file(APP_FILE)
    at.run()
    assert not at.exception

    # Error banner for offline connection should appear gracefully
    assert len(at.error) >= 1
    offline_msg_found = any("Cannot connect to MediCare" in str(err.value) for err in at.error)
    assert offline_msg_found, "Backend offline notification banner not displayed"

    # Chat input is present and disabled
    assert len(at.chat_input) >= 1
    assert at.chat_input[0].disabled is True


def test_apptest_chat_page_with_assistant_message_table_citations():
    """Verify assistant message renders markdown, citations, table, and trace without crashing."""
    at = AppTest.from_file(APP_FILE)

    fake_msg = {
        "type": "ai",
        "content": "Here is the comparative cost breakdown [C1] across accredited hospitals.",
        "response_metadata": {
            "medicare": {
                "route": "data_only",
                "citations": [
                    {
                        "cite_id": "C1",
                        "source": "star_health_policy.pdf",
                        "section": "Coverage Limits",
                        "text": "Inpatient room rent capped at ₹5,000 per day.",
                        "score": 0.92,
                        "scope": "curated",
                    }
                ],
                "table": {
                    "columns": ["hospital_name", "avg_cost_inr", "cashless_accepted"],
                    "rows": [
                        ["City Hospital", 45000, 1],
                        ["Metro Hospital", 62000, 0],
                    ],
                },
                "chart": {
                    "chart_type": "grouped_bar",
                    "title": "Cost Comparison",
                    "x_axis": "hospital_name",
                    "y_axis": "avg_cost_inr",
                    "data": [
                        {"hospital_name": "City Hospital", "avg_cost_inr": 45000},
                        {"hospital_name": "Metro Hospital", "avg_cost_inr": 62000},
                    ],
                },
                "grounding": {
                    "passed": True,
                    "issues": [],
                    "fallback_used": False,
                },
                "timings_ms": {
                    "supervisor": 120,
                    "sql_agent": 340,
                    "writer": 280,
                },
            }
        },
    }

    at.session_state["messages"] = [
        {"type": "human", "content": "Compare surgical procedure costs across hospitals"},
        fake_msg,
    ]
    at.run()
    assert not at.exception

    # Check that assistant message text is rendered
    rendered_text = any("comparative cost breakdown" in str(m.value) for m in at.markdown)
    assert rendered_text, "Assistant response text not rendered"

    # Check that DataFrame is rendered
    assert len(at.dataframe) >= 1


def test_apptest_blocked_safety_response():
    """Verify safety guardrail blocked replies render in a distinct card without table or chart."""
    at = AppTest.from_file(APP_FILE)

    blocked_msg = {
        "type": "ai",
        "content": "If you are experiencing a medical emergency, please call 112 immediately.",
        "response_metadata": {
            "medicare": {
                "guardrail": {
                    "blocked": True,
                    "category": "emergency",
                },
                "table": None,
                "chart": None,
            }
        },
    }

    at.session_state["messages"] = [
        {"type": "human", "content": "I need emergency assistance"},
        blocked_msg,
    ]
    at.run()
    assert not at.exception

    # Check that helpline notice is rendered
    emergency_text = any("112 immediately" in str(m.value) for m in at.markdown)
    assert emergency_text, "Emergency helpline notice text was not rendered"

    # Ensure no table or chart rendered for emergency response
    assert len(at.dataframe) == 0


def test_apptest_documents_page():
    """Verify My Documents page renders file uploader, inputs, and curated list."""
    at = AppTest.from_file(DOCS_PAGE)
    at.run()
    assert not at.exception

    # File uploader should exist
    assert len(at.file_uploader) >= 1
    # Type selectbox should exist
    assert len(at.selectbox) >= 1


def test_apptest_how_it_works_page():
    """Verify How It Works page renders title and agent cards."""
    at = AppTest.from_file(HOW_IT_WORKS_PAGE)
    at.run()
    assert not at.exception

    # Verify How It Works title
    title_found = any(
        "How It Works" in str(t.value) or "Multi-Agent Architecture" in str(t.value)
        for t in at.title
    )
    assert title_found, "How It Works title not found"

    # Plain language agent titles should exist
    agent_title_found = any("Supervisor Agent" in str(m.value) for m in at.markdown)
    assert agent_title_found, "Supervisor Agent card not found on Multi-Agent Architecture page"
