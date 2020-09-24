"""Flask Application Factory. Initalize the Flask application that serves the
PIE web application.
"""

import logging
import os
import sys

from flask import Flask, jsonify, make_response
from logging.handlers import RotatingFileHandler

from app import config
import flowserv.error as err

root = logging.getLogger()
root.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(message)s')
handler.setFormatter(formatter)
root.addHandler(handler)


def create_app(test_config=None):
    """Initialize the Flask application."""
    # Create tha app. Follwoing the Twelve-Factor App methodology we configure
    # the Flask application from environment variables.
    app = Flask(__name__, instance_relative_config=True)
    if test_config is not None:
        app.config.update(test_config)
    app.config['MAX_CONTENT_LENGTH'] = config.MAX_CONTENT_LENGTH()
    # --------------------------------------------------------------------------
    # Initialize error logging
    # --------------------------------------------------------------------------
    # Use rotating file handler for server logs
    logdir = config.LOG_DIR()
    os.makedirs(config.LOG_DIR(), exist_ok=True)
    file_handler = RotatingFileHandler(
        os.path.join(logdir, 'pie.log'),
        maxBytes=1024 * 1024 * 100,
        backupCount=20
    )
    file_handler.setLevel(logging.ERROR)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    )
    app.logger.addHandler(file_handler)

    # --------------------------------------------------------------------------
    # Define error handlers
    # --------------------------------------------------------------------------
    @app.errorhandler(err.FlowservError)
    def flowserv_error(error):
        """JSON response handler for requests that raise an error in one of the
        flowserv components.

        Parameters
        ----------
        error : Exception
            Exception thrown by request Handler

        Returns
        -------
        Http response
        """
        app.logger.error(error)
        return make_response(jsonify({'message': str(error)}), 400)

    @app.errorhandler(413)
    def upload_error(error):
        """Exception handler for file uploads that exceed the file size
        limit.
        """
        app.logger.error(error)
        return make_response(jsonify({'error': str(error)}), 413)

    @app.errorhandler(500)
    def internal_error(error):
        """Exception handler that logs internal server errors."""
        app.logger.error(error)
        return make_response(jsonify({'error': str(error)}), 500)

    # --------------------------------------------------------------------------
    # Import blueprints for App components
    # --------------------------------------------------------------------------
    # Main welcome page.
    from app import welcome
    app.register_blueprint(welcome.bp)
    # File download.
    from app import files
    app.register_blueprint(files.bp)
    # Colony Recognition Application.
    from app import colony
    app.register_blueprint(colony.bp)
    # Return the app
    return app
