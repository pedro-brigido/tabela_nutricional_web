"""
NutritionTable and TableVersion models.
"""

from datetime import datetime, timezone

from app.extensions import db


def _utcnow():
    return datetime.now(timezone.utc)


class NutritionTable(db.Model):
    __tablename__ = "nutrition_tables"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    idempotency_key = db.Column(db.String(64), unique=True, nullable=True)
    title = db.Column(db.String(255), nullable=False)
    product_data = db.Column(db.JSON, nullable=False)
    ingredients_data = db.Column(db.JSON, nullable=False)
    result_data = db.Column(db.JSON, nullable=False)
    ingredient_count = db.Column(db.Integer, default=0)
    version = db.Column(db.Integer, default=1)
    is_finalized = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    user = db.relationship(
        "User", backref=db.backref("nutrition_tables", lazy="dynamic")
    )
    versions = db.relationship(
        "TableVersion", backref="table", lazy="dynamic",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<NutritionTable id={self.id} title={self.title!r}>"


class TableVersion(db.Model):
    __tablename__ = "table_versions"

    id = db.Column(db.Integer, primary_key=True)
    table_id = db.Column(
        db.Integer,
        db.ForeignKey("nutrition_tables.id"),
        nullable=False,
        index=True,
    )
    version_number = db.Column(db.Integer, nullable=False)
    product_data = db.Column(db.JSON, nullable=False)
    ingredients_data = db.Column(db.JSON, nullable=False)
    result_data = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow)

    def __repr__(self):
        return f"<TableVersion table={self.table_id} v={self.version_number}>"
