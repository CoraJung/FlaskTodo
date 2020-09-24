"""Blueprint for rendering the application welcome page."""

from flask import Blueprint, jsonify, make_response, request, render_template

bp = Blueprint('welcome', __name__, url_prefix='/')


@bp.route('/', methods=['GET'])
def pie_colonies_input():
    """Render the main welcome page for the application."""
    return render_template('public/index.html')
