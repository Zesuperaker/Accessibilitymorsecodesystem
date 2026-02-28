"""Routes module for FlaskMeridian app

Flask-Security-Too automatically registers authentication routes:
- GET/POST /login              - User login
- GET/POST /register           - User registration
- GET /logout                  - User logout
- GET/POST /forgot-password    - Password reset request
- GET/POST /reset-password/<token> - Password reset confirmation

This file registers application-specific blueprints only.
"""
from .main import main_bp


def register_blueprints(app):
    """Register application blueprints
    
    Flask-Security-Too handles authentication routes automatically via the
    Security() initialization in app.py. This function registers custom
    application blueprints only.
    """
    app.register_blueprint(main_bp)
