"""Main routes for the application"""
from flask import Blueprint, render_template

main_bp = Blueprint('main', __name__, url_prefix='/')


@main_bp.route('/')
def index():
    """Homepage route - serves the new home page"""
    return render_template('home.html')


@main_bp.route('/health')
def health():
    """Health check endpoint"""
    return {'status': 'healthy'}, 200