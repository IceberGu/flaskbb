# -*- coding: utf-8 -*-
"""
    flaskbb.app
    ~~~~~~~~~~~~~~~~~~~~

    manages the app creation and configuration process

    :copyright: (c) 2013 by the FlaskBB Team.
    :license: BSD, see LICENSE for more details.
"""
import os
import logging

from flask import Flask, render_template
from flask.ext.login import current_user
from flask_debugtoolbar import DebugToolbarExtension

# Import the user blueprint
from flaskbb.user.views import user
from flaskbb.user.models import User, Guest
# Import the auth blueprint
from flaskbb.auth.views import auth
# Import the admin blueprint
from flaskbb.admin.views import admin
# Import the PM blueprint
from flaskbb.pms.views import pms
# Import the forum blueprint
from flaskbb.forum.views import forum
from flaskbb.forum.models import *

from flaskbb.extensions import db, login_manager, mail, cache #toolbar
from flaskbb.helpers import time_delta_format, last_seen, can_moderate


DEFAULT_BLUEPRINTS = (
    (forum, ""),
    (auth, ""),
    (user, "/u"),
    (pms, "/pm"),
    (admin, "/admin")
)


def create_app(config=None, blueprints=None):
    """
    Creates the app.
    """

    if blueprints is None:
        blueprints = DEFAULT_BLUEPRINTS

    # Initialize the app
    app = Flask("flaskbb")

    configure_app(app, config)
    configure_extensions(app)
    configure_blueprints(app, blueprints)
    configure_template_filters(app)
    configure_before_handlers(app)
    configure_errorhandlers(app)
    configure_logging(app)

    return app


def configure_app(app, config):
    """
    Configures the app. If no configuration file is choosen,
    the app will use the example configuration.
    """

    # Get the configuration file
    if config is None:
        from flaskbb.configs.development import DevelopmentConfig
        app.config.from_object(DevelopmentConfig)
        app.logger.info("No configuration specified. Using Development config")
    else:
        app.config.from_object(config)


def configure_extensions(app):
    """
    Configures the extensions
    """

    # Flask-SQLAlchemy
    db.init_app(app)

    # Flask-Mail
    mail.init_app(app)

    # Flask-Cache
    cache.init_app(app)

    # Flask-Debugtoolbar
    toolbar = DebugToolbarExtension(app)

    # Flask-Login
    login_manager.login_view = app.config["LOGIN_VIEW"]
    login_manager.refresh_view = app.config["REAUTH_VIEW"]
    login_manager.anonymous_user = Guest

    @login_manager.user_loader
    def load_user(id):
        """
        Loads the user. Required by the `login` extension
        """
        return User.query.get(id)

    login_manager.init_app(app)


def configure_blueprints(app, blueprints):
    """
    Configures the blueprints
    """

    for blueprint, url_prefix in blueprints:
        app.register_blueprint(blueprint, url_prefix=url_prefix)


def configure_template_filters(app):
    """
    Configures the template filters
    """

    @app.template_filter()
    def format_date(value, format='%Y-%m-%d'):
        """
        Returns a formatted time string
        """
        return value.strftime(format)

    @app.template_filter()
    def time_since(value):
        return time_delta_format(value)

    @app.template_filter()
    def is_online(user):
        if user.lastseen >= last_seen():
            return True
        return False

    @app.template_filter()
    def is_current_user(user, post):
        """
        Check if the post is written by the user
        """
        return post.user_id == user.id

    @app.template_filter()
    def edit_post(user, post, forum):
        """
        Check if the post can be edited by the user
        """
        if can_moderate(user, forum):
            return True
        if post.user_id == user.id and user.permissions['editpost']:
            return True
        return False

    @app.template_filter()
    def delete_post(user, post, forum):
        """
        Check if the post can be edited by the user
        """
        if can_moderate(user, forum):
            return True
        if post.user_id == user.id and user.permissions['deletepost']:
            return True
        return False

    @app.template_filter()
    def delete_topic(user, post, forum):
        if can_moderate(user, forum):
            return True
        if post.user_id == user.id and user.permissions['deletetopic']:
            return True
        return False


    @app.template_filter()
    def post_reply(user, forum):
        if can_moderate(user, forum):
            return True
        if user.permissions['postreply']:
            return True
        return False


def configure_before_handlers(app):
    """
    Configures the before request handlers
    """

    @app.before_request
    def update_lastseen():
        """
        Updates `lastseen` before every reguest if the user is authenticated
        """
        if current_user.is_authenticated():
            current_user.lastseen = datetime.utcnow()
            db.session.add(current_user)
            db.session.commit()

    @app.before_request
    def get_user_permissions():
        current_user.permissions = current_user.get_permissions()


def configure_errorhandlers(app):
    """
    Configures the error handlers
    """

    @app.errorhandler(403)
    def forbidden_page(error):
        return render_template("errors/forbidden_page.html"), 403

    @app.errorhandler(404)
    def page_not_found(error):
        return render_template("errors/page_not_found.html"), 404

    @app.errorhandler(500)
    def server_error_page(error):
        return render_template("errors/server_error.html"), 500


def configure_logging(app):
    """
    Configures logging.
    """

    logs_folder = os.path.join(app.root_path, os.pardir, "logs")
    from logging.handlers import SMTPHandler
    formatter = logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s '
        '[in %(pathname)s:%(lineno)d]')

    info_log = os.path.join(logs_folder, app.config['INFO_LOG'])

    info_file_handler = logging.handlers.RotatingFileHandler(
        info_log,
        maxBytes=100000,
        backupCount=10
    )

    info_file_handler.setLevel(logging.INFO)
    info_file_handler.setFormatter(formatter)
    app.logger.addHandler(info_file_handler)

    error_log = os.path.join(logs_folder, app.config['ERROR_LOG'])

    error_file_handler = logging.handlers.RotatingFileHandler(
        error_log,
        maxBytes=100000,
        backupCount=10
    )

    error_file_handler.setLevel(logging.ERROR)
    error_file_handler.setFormatter(formatter)
    app.logger.addHandler(error_file_handler)

    if app.config["SEND_LOGS"]:
        mail_handler = \
            SMTPHandler(app.config['MAIL_SERVER'],
                        app.config['DEFAULT_MAIL_SENDER'],
                        app.config['ADMINS'],
                        'application error, no admins specified',
                        (
                            app.config['MAIL_USERNAME'],
                            app.config['MAIL_PASSWORD'],
                        ))

        mail_handler.setLevel(logging.ERROR)
        mail_handler.setFormatter(formatter)
        app.logger.addHandler(mail_handler)