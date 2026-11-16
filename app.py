import os
from datetime import timedelta
from flask import Flask, render_template, jsonify, request
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from models import db
from auth import auth_bp, role_required
from admin import admin_bp
from examiner import examiner_bp
from student import student_bp
from celery import Celery
from celery.schedules import crontab
from cache import invalidate_portal_cache

REDIS_URL = 'redis://localhost:6379/0'


def make_celery(flask_app):
    """Create a Celery instance whose tasks always run inside the Flask app context."""
    celery_app = Celery(flask_app.import_name, broker=REDIS_URL, backend=REDIS_URL, include=['tasks'])
    celery_app.conf.update(
        timezone='Asia/Kolkata',
        enable_utc=False,
        task_serializer='json',
        result_serializer='json',
        accept_content=['json'],
        result_expires=3600,
        broker_connection_retry_on_startup=True,
        broker_connection_timeout=2,
        task_publish_retry=False,
        redis_socket_connect_timeout=2,
        beat_schedule={
            'daily-exam-reminders': {
                'task': 'tasks.send_daily_reminders',
                'schedule': crontab(hour=18, minute=0),               # every day, 6 PM IST
            },
            'monthly-admin-report': {
                'task': 'tasks.generate_monthly_admin_report',
                'schedule': crontab(day_of_month=1, hour=7, minute=0),  # 1st of month, 7 AM IST
            },
        },
    )

    class ContextTask(celery_app.Task):
        def __call__(self, *args, **kwargs):
            with flask_app.app_context():
                return self.run(*args, **kwargs)

    celery_app.Task = ContextTask
    celery_app.set_default()
    return celery_app

def create_app():
    app = Flask(__name__, template_folder='templates', static_folder='static')
    
    # Database and JWT configuration
    base_dir = os.path.abspath(os.path.dirname(__file__))
    app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(base_dir, 'exam_portal.db')}"
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['JWT_SECRET_KEY'] = 'emp-v2-mad2-secret-key-2026'
    app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=6)

    # Initialize extensions
    db.init_app(app)
    CORS(app)
    JWTManager(app)

    # Register application blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(examiner_bp)
    app.register_blueprint(student_bp)

    # Invalidate cached course lists / student dashboards after any successful write
    @app.after_request
    def invalidate_cache_on_write(response):
        if (request.method in ('POST', 'PUT', 'PATCH', 'DELETE')
                and response.status_code < 400
                and request.path.startswith(('/api/admin/', '/api/examiner/', '/api/student/'))
                and '/export-csv' not in request.path):
            invalidate_portal_cache()
        return response

    # Server health check
    @app.route('/api/ping', methods=['GET'])
    def ping():
        return jsonify({"status": "running", "portal": "EMP-V2"}), 200

    # Role-protected test endpoint
    @app.route('/api/admin/test', methods=['GET'])
    @role_required('Admin')
    def admin_only():
        return jsonify({"message": "Authorized: Welcome to the Admin restricted zone"}), 200

    # Single entry point for Vue SPA
    @app.route('/', defaults={'path': ''})
    @app.route('/<path:path>')
    def catch_all(path):
        return render_template('index.html')

    return app

app = create_app()
celery = make_celery(app)

if __name__ == '__main__':
    app.run(debug=True, port=5000)