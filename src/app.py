from flask import Flask
from flask import send_from_directory

try:
    from . import handlers
except ImportError:  # running as a plain script (python src/app.py)
    import handlers  # type: ignore


def create_app():
    import os

    app = Flask(__name__)
    demo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    app.add_url_rule("/", "health", lambda: ("ok", 200))
    app.add_url_rule("/demo", "demo", lambda: send_from_directory(demo_dir, "demo.html"))
    app.add_url_rule("/menu", "listMenu", handlers.list_menu, methods=["GET"])
    app.add_url_rule("/menu/<int:item_id>", "getMenuItem", handlers.get_menu_item, methods=["GET"])
    app.add_url_rule("/customers", "createCustomer", handlers.create_customer, methods=["POST"])
    app.add_url_rule("/tables", "listDiningTables", handlers.list_dining_tables, methods=["GET"])
    app.add_url_rule("/reservations", "createReservation", handlers.create_reservation, methods=["POST"])
    app.add_url_rule("/reservations/<int:reservation_id>", "getReservation", handlers.get_reservation, methods=["GET"])
    app.add_url_rule("/orders", "createOrder", handlers.create_order, methods=["POST"])
    app.add_url_rule("/orders/<int:order_id>", "getOrder", handlers.get_order, methods=["GET"])
    app.add_url_rule("/orders/<int:order_id>/status", "updateOrderStatus", handlers.update_order_status, methods=["PATCH"])
    app.add_url_rule("/customers/<int:customer_id>/orders", "listCustomerOrders", handlers.list_customer_orders, methods=["GET"])

    return app


app = create_app()

if __name__ == "__main__":
    import os

    app.run(host=os.environ.get("HOST", "127.0.0.1"),
            port=int(os.environ.get("PORT", "5000")),
            debug=False)