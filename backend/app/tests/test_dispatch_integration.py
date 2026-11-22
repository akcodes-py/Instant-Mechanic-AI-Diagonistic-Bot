"""H3 dispatch integration tests. No broker, MongoDB or model files required."""
import pytest

from app.services import event_bus, ranker
from app.services.spatial import lat_lng_to_cell

ORIGIN = lat_lng_to_cell(28.4595, 77.0266, 8)


def test_haversine_same_point_is_zero():
    assert ranker.haversine_km(28.4595, 77.0266, 28.4595, 77.0266) == pytest.approx(0.0)


def test_ranker_returns_honest_deterministic_result():
    result = ranker.rank(
        "booking-1",
        ORIGIN,
        [
            {"mechanic_id": "near", "h3_res8": ORIGIN, "lat": 28.4595, "lon": 77.0266},
            {"mechanic_id": "far", "h3_res8": ORIGIN, "lat": 28.5600, "lon": 77.1300},
        ],
    )
    assert result["model_used"] is False
    assert result["strategy"] == "nearest_distance"
    assert [item["mechanic_id"] for item in result["rankings"]] == ["near", "far"]
    assert result["rankings"][0]["eta_seconds"] <= result["rankings"][1]["eta_seconds"]


def test_ranker_skips_invalid_candidates_and_handles_bad_origin():
    result = ranker.rank(
        "booking-2",
        "not-a-cell",
        [{"mechanic_id": ""}, {"mechanic_id": "ok", "lat": "bad"}, {"mechanic_id": "good", "lat": 28.4, "lon": 77.0}],
    )
    assert [item["mechanic_id"] for item in result["rankings"]] == ["good"]


async def test_rank_eta_endpoint(client):
    response = await client.post(
        "/rank/eta",
        json={
            "booking_id": "booking-3",
            "origin_h3": ORIGIN,
            "candidates": [{"mechanic_id": "m1", "h3_res8": ORIGIN, "lat": 28.4595, "lon": 77.0266}],
        },
    )
    assert response.status_code == 200
    assert response.json()["rankings"][0]["mechanic_id"] == "m1"


async def test_context_endpoint_is_honest_when_mongo_disabled(client):
    response = await client.get("/api/context/some-session/")
    assert response.status_code == 503
    assert "unavailable" in response.json()["error"].lower()


def test_event_bus_returns_false_without_a_producer(monkeypatch):
    monkeypatch.setattr(event_bus, "_get_producer", lambda: None)
    assert event_bus.publish_diagnosis_completed(
        session_id="s1",
        diagnosis_id="d1",
        recommended_service="battery_jumpstart",
        urgency="high",
        summary="Battery suspected",
    ) is False


def test_event_bus_payload_matches_the_contract(monkeypatch):
    captured = {}

    class FakeProducer:
        def send(self, topic, key, value):
            captured.update(topic=topic, key=key, value=value)

    monkeypatch.setattr(event_bus, "_get_producer", lambda: FakeProducer())
    assert event_bus.publish_diagnosis_completed(
        session_id="s1",
        diagnosis_id="d1",
        recommended_service="engine_overheat",
        urgency="critical",
        summary="Overheating",
    ) is True
    assert captured["topic"] == "diagnosis.completed"
    assert captured["value"]["required_skill"] == "engine_overheat"
    assert captured["value"]["h3_res7_index"][1] == "7"
    assert captured["value"]["producer"] == "ai-service"
