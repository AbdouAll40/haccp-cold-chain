"""Demo data, inserted once when the database is empty.

Equipment and products come from Achref's FoodSafe sample data, with limits
aligned on the HACCP values in docs/mqtt.md. Expiry dates are relative to today
so the dashboard always shows OK, expiring-soon and expired batches.
"""
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Batch, Delivery, Equipment, Product, Truck


def seed(db: Session) -> None:
    if db.scalar(select(Equipment).limit(1)) is not None:
        return
    today = date.today()

    fridge = Equipment(code="fridge-1", name="Fridge 1", location="Cold room A",
                       equipment_type="fridge", min_temp=0.0, max_temp=4.0)
    freezer = Equipment(code="freezer-1", name="Freezer 1", location="Freezer bay",
                        equipment_type="freezer", min_temp=None, max_temp=-18.0)
    coldroom = Equipment(code="coldroom-1", name="Cold room A", location="Loading dock",
                         equipment_type="cold_room", min_temp=0.0, max_temp=4.0)
    truck = Truck(code="truck-1", name="Truck 1 (refrigerated)")
    db.add_all([fridge, freezer, coldroom, truck])
    db.flush()

    delivery = Delivery(code="DLV-0001", truck_id=truck.id, origin="Warehouse, Khenchela",
                        destination="Shop, Batna")
    db.add(delivery)

    products = {
        "Milk": Product(name="Milk", category="dairy", storage_type="fridge"),
        "Yogurt": Product(name="Yogurt", category="dairy", storage_type="fridge"),
        "Ice cream": Product(name="Ice cream", category="frozen", storage_type="freezer"),
        "Chicken": Product(name="Chicken", category="meat", storage_type="fridge"),
        "Smoked fish": Product(name="Smoked fish", category="seafood", storage_type="fridge"),
    }
    db.add_all(products.values())
    db.flush()

    def batch(lot, product, qty, produced_days_ago, expires_in, equipment=None, deliv=None):
        return Batch(lot_code=lot, product_id=products[product].id, quantity=qty,
                     equipment_id=equipment.id if equipment else None,
                     delivery_id=deliv.id if deliv else None,
                     production_date=today - timedelta(days=produced_days_ago),
                     expiry_date=today + timedelta(days=expires_in))

    db.add_all([
        batch("MLK-001", "Milk", 40, 4, 2, equipment=fridge),
        batch("YOG-014", "Yogurt", 28, 7, 10, equipment=fridge),
        batch("ICE-203", "Ice cream", 18, 20, 60, equipment=freezer),
        batch("CHK-087", "Chicken", 14, 3, -1, equipment=coldroom),
        batch("FSH-022", "Smoked fish", 9, 5, 1, equipment=coldroom),
        batch("YOG-015", "Yogurt", 60, 2, 15, deliv=delivery),
        batch("MLK-002", "Milk", 80, 1, 6, deliv=delivery),
    ])
    db.commit()
