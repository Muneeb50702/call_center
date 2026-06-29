import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200

def test_get_load():
    response = client.get("/loads/1001")
    assert response.status_code == 200
    assert response.json()["origin"] == "Chicago, IL"

def test_search_loads():
    response = client.get("/loads/search?equipment=Dry Van")
    assert response.status_code == 200
    assert len(response.json()) > 0

def test_get_rate():
    response = client.get("/rates/IL-TX")
    assert response.status_code == 200
    assert response.json()["per_mile"] == 2.45

def test_negotiate_rate_accept():
    response = client.post("/rates/negotiate", json={"lane_id": "IL-TX", "counter_offer": 2.30})
    assert response.status_code == 200
    assert response.json()["accepted"] == True

def test_negotiate_rate_reject():
    response = client.post("/rates/negotiate", json={"lane_id": "IL-TX", "counter_offer": 1.50})
    assert response.status_code == 200
    assert response.json()["accepted"] == False

def test_get_available_drivers():
    response = client.get("/drivers/available")
    assert response.status_code == 200
    assert len(response.json()) > 0
