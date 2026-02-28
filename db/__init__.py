"""Database module for FlaskMeridian app"""
from .database import db
from .models import BaseModel

__all__ = ['db', 'BaseModel']
