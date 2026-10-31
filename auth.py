from functools import wraps
from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token,
    jwt_required,
    get_jwt_identity,
    get_jwt
)
from models import db, User

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')

# Custom Decorator for Role-Based Access Control (RBAC)
def role_required(*allowed_roles):
    def decorator(fn):
        @wraps(fn)
        @jwt_required()
        def wrapper(*args, **kwargs):
            claims = get_jwt()
            user_role = claims.get('role')
            if user_role not in allowed_roles:
                return jsonify({
                    "error": "Forbidden",
                    "message": f"Access denied. Requires one of roles: {list(allowed_roles)}"
                }), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator


# 1. Student Registration (Only Students are allowed to self-register)
@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    name = data.get('name', '').strip()

    if not email or not password or not name:
        return jsonify({"error": "Missing required fields: email, password, name"}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "Email is already registered"}), 409

    # Role is strictly hardcoded to 'Student' for security
    student = User(email=email, name=name, role='Student', is_active=True)
    student.set_password(password)
    db.session.add(student)
    db.session.commit()

    return jsonify({"message": "Student registered successfully", "user_id": student.id}), 201


# 2. Unified Login (Admin, Examiner, Student)
@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    user = User.query.filter_by(email=email).first()

    if not user or not user.check_password(password):
        return jsonify({"error": "Invalid email or password"}), 401

    if not user.is_active:
        return jsonify({"error": "Account is deactivated. Contact Administrator."}), 403

    # Embed identity and role inside the JWT token claims
    additional_claims = {
        "role": user.role,
        "name": user.name
    }
    access_token = create_access_token(identity=str(user.id), additional_claims=additional_claims)

    return jsonify({
        "message": "Login successful",
        "access_token": access_token,
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role
        }
    }), 200


# 3. Current User Profile Check
@auth_bp.route('/me', methods=['GET'])
@jwt_required()
def get_current_user():
    user_id = int(get_jwt_identity())
    claims = get_jwt()
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    return jsonify({
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "role": claims.get('role')
    }), 200