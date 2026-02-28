"""Main routes for the application"""
from flask import Blueprint, render_template

main_bp = Blueprint('main', __name__, url_prefix='/')


@main_bp.route('/')
def index():
    """Homepage route"""
    return render_template('index.html')


@main_bp.route('/health')
def health():
    """Health check endpoint"""
    return {'status': 'healthy'}, 200
