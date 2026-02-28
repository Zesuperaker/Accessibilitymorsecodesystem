"""FlaskMeridian Application with Flask-Security-Too Authentication"""
import os
from flask import Flask
from flask_security import Security, SQLAlchemyUserDatastore
from db.database import init_db, db
from db.models import User, Role
from routes import register_blueprints


def create_app(config=None):
    """Application factory"""
    app = Flask(__name__)

    # Configuration
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Flask-Security configuration - load from environment variables
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-key-change-in-production')
    app.config['SECURITY_PASSWORD_SALT'] = os.getenv('SECURITY_PASSWORD_SALT', 'dev-salt-change-in-production')

    # Password hashing configuration - use argon2
    app.config['SECURITY_PASSWORD_SCHEMES'] = ['argon2']
    app.config['SECURITY_DEPRECATED_PASSWORD_SCHEMES'] = []

    # Enable registration
    app.config['SECURITY_REGISTERABLE'] = True
    app.config['SECURITY_CONFIRMABLE'] = False
    app.config['SECURITY_RECOVERABLE'] = False

    # Disable email sending for development (no Flask-Mail needed!)
    # Set to True in production if you have Flask-Mail configured
    app.config['SECURITY_SEND_REGISTER_EMAIL'] = False
    app.config['SECURITY_SEND_PASSWORD_CHANGE_EMAIL'] = False
    app.config['SECURITY_SEND_PASSWORD_RESET_EMAIL'] = False
    app.config['SECURITY_SEND_PASSWORD_RESET_NOTICE_EMAIL'] = False

    if config:
        app.config.update(config)

    # Initialize database
    init_db(app)

    # Setup Flask-Security (automatically registers all auth routes)
    # Routes provided by Flask-Security:
    # - GET/POST /login
    # - GET/POST /register
    # - GET /logout
    # - GET/POST /forgot-password (if RECOVERABLE=True)
    # - GET/POST /reset-password/<token> (if RECOVERABLE=True)
    user_datastore = SQLAlchemyUserDatastore(db, User, Role)
    security = Security(app, user_datastore)

    # Initialize default roles
    with app.app_context():
        _initialize_default_roles()

    # Register blueprints
    register_blueprints(app)

    return app


def _initialize_default_roles():
    """Create default roles if they don't exist"""
    default_roles = [
        ('admin', 'Administrator - full system access'),
        ('user', 'Regular user'),
        ('moderator', 'Content moderator'),
    ]

    for name, description in default_roles:
        if not Role.query.filter_by(name=name).first():
            role = Role(name=name, description=description)
            db.session.add(role)
            db.session.commit()


# Create app instance for Flask CLI
app = create_app()


@app.shell_context_processor
def make_shell_context():
    """Make database models available in flask shell"""
    from flask_security import hash_password
    return {
        'db': db,
        'User': User,
        'Role': Role,
        'hash_password': hash_password,
    }


if __name__ == '__main__':
    app.run(debug=True, port=5000)