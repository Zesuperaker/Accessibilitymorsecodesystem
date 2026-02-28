"""Role model for RBAC (Role-Based Access Control)"""
from .base import BaseModel
from ..database import db


class Role(BaseModel):
    """User role for role-based access control"""
    __tablename__ = 'role'

    name = db.Column(db.String(80), unique=True, nullable=False, index=True)
    description = db.Column(db.String(255))

    def __repr__(self):
        return f'<Role {self.name}>'

    def __str__(self):
        return self.name
