from app import create_app


def test_api_cors_allows_only_local_frontend_origins():
    client = create_app().test_client()

    for origin in ("http://localhost:3000", "http://127.0.0.1:3000"):
        response = client.options(
            "/api/v1/health",
            headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
        )
        assert response.headers.get("Access-Control-Allow-Origin") == origin
        assert "Access-Control-Allow-Credentials" not in response.headers

    response = client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "Access-Control-Allow-Origin" not in response.headers
