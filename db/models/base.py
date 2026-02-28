"""Base model with common attributes"""
from ..database import db


class BaseModel(db.Model):
    """Base model with common attributes"""
    __abstract__ = True

    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(
        db.DateTime, 
        default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp()
    )

    def __repr__(self):
        return f'<{self.__class__.__name__} {self.id}>'
