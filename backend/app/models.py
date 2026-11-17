"""Database tables.

Equipment, products, alerts with severity/resolution and HACCP inspections follow
the data model proposed in Achref's FoodSafe design; batches, trucks and deliveries
cover expiry tracking and delivery follow-up.
"""
from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Equipment(Base):
    """A monitored storage zone (fridge, freezer, cold room)."""

    __tablename__ = "equipment"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True)  # MQTT zone_id, e.g. fridge-1
    name: Mapped[str] = mapped_column(String(100))
    location: Mapped[str] = mapped_column(String(100))
    equipment_type: Mapped[str] = mapped_column(String(20))  # fridge | freezer | cold_room
    min_temp: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_temp: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), default="unknown")  # ok | alert | offline | unknown
    last_temp: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Reading(Base):
    """Recent temperature readings (InfluxDB keeps the long history)."""

    __tablename__ = "readings"
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(50), index=True)  # equipment or truck code
    temperature: Mapped[float] = mapped_column(Float)
    ts: Mapped[datetime] = mapped_column(DateTime, index=True)


class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    category: Mapped[str] = mapped_column(String(50))
    storage_type: Mapped[str] = mapped_column(String(20))  # fridge | freezer


class Truck(Base):
    __tablename__ = "trucks"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True)  # MQTT truck_id
    name: Mapped[str] = mapped_column(String(100))
    min_temp: Mapped[float] = mapped_column(Float, default=0.0)
    max_temp: Mapped[float] = mapped_column(Float, default=4.0)
    status: Mapped[str] = mapped_column(String(20), default="unknown")
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    speed_kmh: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_temp: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Delivery(Base):
    __tablename__ = "deliveries"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True)  # MQTT delivery_id
    truck_id: Mapped[int] = mapped_column(ForeignKey("trucks.id"))
    origin: Mapped[str] = mapped_column(String(100))
    destination: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="in_transit")
    truck: Mapped[Truck] = relationship()


class Batch(Base):
    """A lot of one product, stored in one zone or carried by one delivery."""

    __tablename__ = "batches"
    id: Mapped[int] = mapped_column(primary_key=True)
    lot_code: Mapped[str] = mapped_column(String(50), unique=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    equipment_id: Mapped[int | None] = mapped_column(ForeignKey("equipment.id"), nullable=True)
    delivery_id: Mapped[int | None] = mapped_column(ForeignKey("deliveries.id"), nullable=True)
    production_date: Mapped[date] = mapped_column(Date)
    expiry_date: Mapped[date] = mapped_column(Date)
    # Set when the cold chain was broken while this batch was stored or transported.
    cold_chain_breach: Mapped[bool] = mapped_column(Boolean, default=False)
    product: Mapped[Product] = relationship()
    equipment: Mapped[Equipment | None] = relationship()
    delivery: Mapped[Delivery | None] = relationship()


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(30))  # temperature | sensor_silent | expiry | transit_breach
    severity: Mapped[str] = mapped_column(String(10))  # warning | critical
    source: Mapped[str] = mapped_column(String(50))  # equipment, truck or batch code
    message: Mapped[str] = mapped_column(String(300))
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Inspection(Base):
    """A manual HACCP check recorded by an inspector."""

    __tablename__ = "inspections"
    id: Mapped[int] = mapped_column(primary_key=True)
    equipment_id: Mapped[int] = mapped_column(ForeignKey("equipment.id"))
    inspection_date: Mapped[date] = mapped_column(Date)
    observed_temperature: Mapped[float] = mapped_column(Float)
    compliant: Mapped[bool] = mapped_column(Boolean)
    inspector: Mapped[str] = mapped_column(String(100))
    notes: Mapped[str] = mapped_column(String(500), default="")
    equipment: Mapped[Equipment] = relationship()
