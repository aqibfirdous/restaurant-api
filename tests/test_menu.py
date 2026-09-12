"""Acceptance test A4: menu endpoints."""


def test_list_menu_returns_categorized_available_items(client):
    resp = client.get("/menu")
    assert resp.status_code == 200
    data = resp.get_json()

    assert isinstance(data, list)
    assert len(data) > 0

    all_items = []
    for category in data:
        # every category carries its own id/name/order
        assert "id" in category
        assert category["name"]
        assert isinstance(category["sort_order"], int)
        for item in category["items"]:
            assert item["available"] is True
            all_items.append(item)

    # Cheese Plate is seeded as unavailable and must not be listed
    assert not any(item["name"] == "Cheese Plate" for item in all_items)


def test_list_menu_only_returns_available_items(client):
    data = client.get("/menu").get_json()
    for category in data:
        for item in category["items"]:
            assert item["available"] is True


def test_get_menu_item(client):
    category = client.get("/menu").get_json()[0]
    item = category["items"][0]

    resp = client.get("/menu/%d" % item["id"])
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["id"] == item["id"]
    assert body["name"] == item["name"]
    assert isinstance(body["price_cents"], int)
    assert body["price_cents"] > 0


def test_get_menu_item_not_found(client):
    resp = client.get("/menu/999999")
    assert resp.status_code == 404
    assert "error" in resp.get_json()