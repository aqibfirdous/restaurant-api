from flask import request, jsonify
try:
    from . import db
except ImportError:  # running as a plain script (python src/app.py)
    import db  # type: ignore


def _error(message, status_code):
    return jsonify({"error": message}), status_code


def _menu_item_out(row):
    d = dict(row)
    d["available"] = bool(d["available"])
    return d


def _table_out(row):
    d = dict(row)
    d["active"] = bool(d["active"])
    return d


def list_menu():
    con = db.connect()
    try:
        categories = db.fetch_all(con, "SELECT * FROM menu_categories ORDER BY sort_order")
        result = []
        for cat in categories:
            items = db.fetch_all(
                con,
                "SELECT * FROM menu_items WHERE category_id = ? AND available = 1",
                (cat["id"],),
            )
            result.append({
                "id": cat["id"],
                "name": cat["name"],
                "sort_order": cat["sort_order"],
                "items": [_menu_item_out(i) for i in items],
            })
        return jsonify(result), 200
    finally:
        con.close()


def get_menu_item(item_id):
    con = db.connect()
    try:
        row = db.fetch_one(con, "SELECT * FROM menu_items WHERE id = ?", (item_id,))
        if row is None:
            return _error("Menu item not found", 404)
        return jsonify(_menu_item_out(row)), 200
    finally:
        con.close()


def create_customer():
    data = request.get_json()
    if not data or not data.get("name") or not data.get("email"):
        return _error("name and email are required", 400)
    con = db.connect()
    try:
        existing = db.fetch_one(con, "SELECT id FROM customers WHERE email = ?", (data["email"],))
        if existing:
            return _error("Customer with this email already exists", 409)
        cur = con.execute(
            "INSERT INTO customers (name, email, phone) VALUES (?, ?, ?)",
            (data["name"], data["email"], data.get("phone")),
        )
        con.commit()
        row = db.fetch_one(con, "SELECT * FROM customers WHERE id = ?", (cur.lastrowid,))
        return jsonify(dict(row)), 201
    finally:
        con.close()


def list_dining_tables():
    con = db.connect()
    try:
        rows = db.fetch_all(con, "SELECT * FROM dining_tables WHERE active = 1")
        return jsonify([_table_out(r) for r in rows]), 200
    finally:
        con.close()


def create_reservation():
    data = request.get_json()
    if not data:
        return _error("Request body is required", 400)

    customer_id = data.get("customer_id")
    dining_table_id = data.get("dining_table_id")
    reservation_time = data.get("reservation_time")
    party_size = data.get("party_size")

    if not all([customer_id, dining_table_id, reservation_time, party_size]):
        return _error("customer_id, dining_table_id, reservation_time, and party_size are required", 400)

    if party_size <= 0:
        return _error("party_size must be greater than 0", 400)

    con = db.connect()
    try:
        customer = db.fetch_one(con, "SELECT id FROM customers WHERE id = ?", (customer_id,))
        if not customer:
            return _error("Customer not found", 404)

        table = db.fetch_one(con, "SELECT * FROM dining_tables WHERE id = ? AND active = 1", (dining_table_id,))
        if not table:
            return _error("Dining table not found or inactive", 404)

        if party_size > table["seats"]:
            return _error("Party size exceeds table capacity", 400)

        existing = db.fetch_one(
            con,
            "SELECT id FROM reservations WHERE dining_table_id = ? AND reservation_time = ? AND status != 'CANCELLED'",
            (dining_table_id, reservation_time),
        )
        if existing:
            return _error("Table is already reserved for this time", 409)

        cur = con.execute(
            "INSERT INTO reservations (customer_id, dining_table_id, reservation_time, party_size, status) VALUES (?, ?, ?, ?, 'CONFIRMED')",
            (customer_id, dining_table_id, reservation_time, party_size),
        )
        con.commit()
        row = db.fetch_one(con, "SELECT * FROM reservations WHERE id = ?", (cur.lastrowid,))
        return jsonify(dict(row)), 201
    finally:
        con.close()


def get_reservation(reservation_id):
    con = db.connect()
    try:
        row = db.fetch_one(con, "SELECT * FROM reservations WHERE id = ?", (reservation_id,))
        if row is None:
            return _error("Reservation not found", 404)
        return jsonify(dict(row)), 200
    finally:
        con.close()


def create_order():
    data = request.get_json()
    if not data or not data.get("items"):
        return _error("items are required", 400)

    customer_id = data.get("customer_id")
    dining_table_id = data.get("dining_table_id")
    reservation_id = data.get("reservation_id")

    con = db.connect()
    try:
        if customer_id:
            customer = db.fetch_one(con, "SELECT id FROM customers WHERE id = ?", (customer_id,))
            if not customer:
                return _error("Customer not found", 404)

        if dining_table_id:
            table = db.fetch_one(con, "SELECT id FROM dining_tables WHERE id = ?", (dining_table_id,))
            if not table:
                return _error("Dining table not found", 404)

        if reservation_id:
            res = db.fetch_one(con, "SELECT id FROM reservations WHERE id = ?", (reservation_id,))
            if not res:
                return _error("Reservation not found", 404)

        order_items = []
        total_cents = 0

        for item_req in data["items"]:
            menu_item_id = item_req.get("menu_item_id")
            quantity = item_req.get("quantity")
            if not menu_item_id or not quantity or quantity < 1:
                return _error("Each item must have menu_item_id and quantity >= 1", 400)

            menu_item = db.fetch_one(con, "SELECT * FROM menu_items WHERE id = ?", (menu_item_id,))
            if not menu_item:
                return _error(f"Menu item {menu_item_id} not found", 400)
            if not menu_item["available"]:
                return _error(f"Menu item '{menu_item['name']}' is not available", 400)

            unit_price = menu_item["price_cents"]
            line_total = unit_price * quantity
            total_cents += line_total
            order_items.append({
                "menu_item_id": menu_item_id,
                "quantity": quantity,
                "unit_price_cents": unit_price,
                "line_total_cents": line_total,
            })

        cur = con.execute(
            "INSERT INTO orders (customer_id, dining_table_id, reservation_id, status, total_cents, created_at) VALUES (?, ?, ?, 'NEW', ?, datetime('now'))",
            (customer_id, dining_table_id, reservation_id, total_cents),
        )
        order_id = cur.lastrowid

        for oi in order_items:
            con.execute(
                "INSERT INTO order_items (order_id, menu_item_id, quantity, unit_price_cents, line_total_cents) VALUES (?, ?, ?, ?, ?)",
                (order_id, oi["menu_item_id"], oi["quantity"], oi["unit_price_cents"], oi["line_total_cents"]),
            )

        con.commit()

        order_row = db.fetch_one(con, "SELECT * FROM orders WHERE id = ?", (order_id,))
        items_rows = db.fetch_all(con, "SELECT * FROM order_items WHERE order_id = ?", (order_id,))
        order_dict = dict(order_row)
        order_dict["items"] = [dict(i) for i in items_rows]
        return jsonify(order_dict), 201
    finally:
        con.close()


def get_order(order_id):
    con = db.connect()
    try:
        order_row = db.fetch_one(con, "SELECT * FROM orders WHERE id = ?", (order_id,))
        if order_row is None:
            return _error("Order not found", 404)
        items_rows = db.fetch_all(con, "SELECT * FROM order_items WHERE order_id = ?", (order_id,))
        order_dict = dict(order_row)
        order_dict["items"] = [dict(i) for i in items_rows]
        return jsonify(order_dict), 200
    finally:
        con.close()


VALID_TRANSITIONS = {
    "NEW": ["PREPARING", "CANCELLED"],
    "PREPARING": ["READY"],
    "READY": ["COMPLETED"],
    "COMPLETED": [],
    "CANCELLED": [],
}


def update_order_status(order_id):
    data = request.get_json()
    if not data or "status" not in data:
        return _error("status is required", 400)

    new_status = data["status"]
    con = db.connect()
    try:
        order_row = db.fetch_one(con, "SELECT * FROM orders WHERE id = ?", (order_id,))
        if order_row is None:
            return _error("Order not found", 404)

        current_status = order_row["status"]
        allowed = VALID_TRANSITIONS.get(current_status, [])
        if new_status not in allowed:
            return _error(f"Cannot transition from {current_status} to {new_status}", 400)

        con.execute("UPDATE orders SET status = ? WHERE id = ?", (new_status, order_id))
        con.commit()

        order_row = db.fetch_one(con, "SELECT * FROM orders WHERE id = ?", (order_id,))
        items_rows = db.fetch_all(con, "SELECT * FROM order_items WHERE order_id = ?", (order_id,))
        order_dict = dict(order_row)
        order_dict["items"] = [dict(i) for i in items_rows]
        return jsonify(order_dict), 200
    finally:
        con.close()


def list_customer_orders(customer_id):
    con = db.connect()
    try:
        customer = db.fetch_one(con, "SELECT id FROM customers WHERE id = ?", (customer_id,))
        if not customer:
            return _error("Customer not found", 404)
        rows = db.fetch_all(
            con,
            "SELECT * FROM orders WHERE customer_id = ? ORDER BY created_at DESC",
            (customer_id,),
        )
        return jsonify([dict(r) for r in rows]), 200
    finally:
        con.close()