"""User model with Flask-Security-Too and Flask-Login integration"""
import uuid
from .base import BaseModel
from ..database import db
from flask_security import verify_password


# Association table for User-Role many-to-many relationship
roles_users = db.Table(
    'roles_users',
    db.Column('user_id', db.Integer(), db.ForeignKey('user.id'), primary_key=True),
    db.Column('role_id', db.Integer(), db.ForeignKey('role.id'), primary_key=True)
)


class User(BaseModel):
    """User model with Flask-Security-Too and Flask-Login integration"""
    __tablename__ = 'user'

    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    username = db.Column(db.String(80), unique=True, nullable=True, index=True)
    password = db.Column(db.String(255), nullable=False)

    # Account status
    active = db.Column(db.Boolean(), default=True, index=True)
    
    # Flask-Security requirement: unique identifier per user
    fs_uniquifier = db.Column(
        db.String(255), 
        unique=True, 
        nullable=False,
        default=lambda: str(uuid.uuid4())
    )

    # User profile information
    first_name = db.Column(db.String(100))
    last_name = db.Column(db.String(100))

    # Login tracking
    last_login_at = db.Column(db.DateTime())
    current_login_at = db.Column(db.DateTime())
    last_login_ip = db.Column(db.String(100))
    current_login_ip = db.Column(db.String(100))
    login_count = db.Column(db.Integer, default=0)

    # Relationships
    roles = db.relationship(
        'Role',
        secondary=roles_users,
        backref=db.backref('users', lazy='dynamic')
    )

    def __repr__(self):
        return f'<User {self.email}>'

    def __str__(self):
        return self.email

    # ========================
    # Flask-Login Required Properties
    # ========================
    @property
    def is_active(self):
        """Flask-Login requirement: check if account is active"""
        return self.active

    @property
    def is_authenticated(self):
        """Flask-Login requirement: user is authenticated if loaded from database"""
        return True

    @property
    def is_anonymous(self):
        """Flask-Login requirement: this is not an anonymous user"""
        return False

    def get_id(self):
        """Flask-Login requirement: return user ID as string"""
        return str(self.id)

    # ========================
    # Flask-Security-Too Required Methods
    # ========================
    def verify_and_update_password(self, password):
        """
        Flask-Security-Too REQUIRED: Verify password and update hash if needed
        
        This method is called by Flask-Security's LoginForm during authentication.
        It verifies the provided password against the stored hash, and can update
        the hash if the password hashing algorithm has changed.
        
        Args:
            password: The plaintext password to verify
            
        Returns:
            bool: True if password is correct, False otherwise
        """
        # Verify password using Flask-Security's verify_password
        is_correct = verify_password(password, self.password)
        return is_correct

    # ========================
    # User Methods
    # ========================
    def has_role(self, role_name):
        """Check if user has a specific role"""
        return any(role.name == role_name for role in self.roles)

    def get_full_name(self):
        """Get user display name"""
        if self.first_name and self.last_name:
            return f'{self.first_name} {self.last_name}'
        elif self.first_name:
            return self.first_name
        return self.username

    def add_role(self, role):
        """Add a role to the user"""
        if role not in self.roles:
            self.roles.append(role)

    def remove_role(self, role):
        """Remove a role from the user"""
        if role in self.roles:
            self.roles.remove(role)
