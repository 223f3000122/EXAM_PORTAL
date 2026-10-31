import os
from datetime import timedelta
from flask import Flask, render_template, jsonify
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from models import db
from auth import auth_bp, role_required
from admin import admin_bp

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

if __name__ == '__main__':
    app.run(debug=True, port=5000)