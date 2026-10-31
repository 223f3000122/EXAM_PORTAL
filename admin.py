from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from models import db, User, Course, Examination, ExaminationRubric, ExaminationSlot, Booking
from auth import role_required

admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')

# 1. Summary Statistics for Admin Dashboard Cards
@admin_bp.route('/stats', methods=['GET'])
@role_required('Admin')
def get_stats():
    return jsonify({
        "total_courses": Course.query.count(),
        "total_examinations": Examination.query.count(),
        "total_examiners": User.query.filter_by(role='Examiner').count(),
        "total_students": User.query.filter_by(role='Student').count(),
        "total_slots": ExaminationSlot.query.count(),
        "total_bookings": Booking.query.count()
    }), 200


# 2. Course CRUD Endpoints
@admin_bp.route('/courses', methods=['GET'])
@role_required('Admin')
def list_courses():
    courses = Course.query.order_by(Course.id.desc()).all()
    return jsonify([{
        "id": c.id,
        "course_code": c.course_code,
        "course_name": c.course_name,
        "description": c.description,
        "status": c.status,
        "exam_count": len(c.examinations)
    } for c in courses]), 200

@admin_bp.route('/courses', methods=['POST'])
@role_required('Admin')
def create_course():
    data = request.get_json() or {}
    code = data.get('course_code', '').strip().upper()
    name = data.get('course_name', '').strip()
    description = data.get('description', '').strip()

    if not code or not name:
        return jsonify({"error": "Course code and course name are required"}), 400

    if Course.query.filter_by(course_code=code).first():
        return jsonify({"error": f"Course code '{code}' already exists"}), 409

    course = Course(course_code=code, course_name=name, description=description, status='Active')
    db.session.add(course)
    db.session.commit()
    return jsonify({"message": "Course created successfully", "course_id": course.id}), 201

@admin_bp.route('/courses/<int:course_id>', methods=['PUT'])
@role_required('Admin')
def update_course(course_id):
    course = Course.query.get(course_id)
    if not course:
        return jsonify({"error": "Course not found"}), 404

    data = request.get_json() or {}
    course.course_name = data.get('course_name', course.course_name).strip()
    course.description = data.get('description', course.description).strip()
    course.status = data.get('status', course.status)

    db.session.commit()
    return jsonify({"message": "Course updated successfully"}), 200

@admin_bp.route('/courses/<int:course_id>', methods=['DELETE'])
@role_required('Admin')
def delete_course(course_id):
    course = Course.query.get(course_id)
    if not course:
        return jsonify({"error": "Course not found"}), 404

    db.session.delete(course)
    db.session.commit()
    return jsonify({"message": "Course and associated exams deleted successfully"}), 200


# 3. Examination Management Endpoints
@admin_bp.route('/examinations', methods=['GET'])
@role_required('Admin')
def list_examinations():
    exams = Examination.query.order_by(Examination.id.desc()).all()
    results = []
    for exam in exams:
        results.append({
            "id": exam.id,
            "course_id": exam.course_id,
            "course_code": exam.course.course_code if exam.course else "N/A",
            "examination_name": exam.examination_name,
            "exam_type": exam.exam_type,
            "duration": exam.duration,
            "maximum_marks": exam.maximum_marks,
            "status": exam.status,
            "rubrics": [{
                "id": r.id,
                "criterion_name": r.criterion_name,
                "maximum_marks": r.maximum_marks,
                "weightage": r.weightage
            } for r in exam.rubrics]
        })
    return jsonify(results), 200

@admin_bp.route('/examinations', methods=['POST'])
@role_required('Admin')
def create_examination():
    data = request.get_json() or {}
    course_id = data.get('course_id')
    name = data.get('examination_name', '').strip()
    exam_type = data.get('exam_type', 'Viva')
    duration = data.get('duration', 30)
    max_marks = data.get('maximum_marks', 100)
    rubrics_data = data.get('rubrics', [])

    if not course_id or not name:
        return jsonify({"error": "Course selection and examination name are required"}), 400

    course = Course.query.get(course_id)
    if not course:
        return jsonify({"error": "Invalid course ID"}), 404

    exam = Examination(
        course_id=course_id,
        examination_name=name,
        exam_type=exam_type,
        duration=int(duration),
        maximum_marks=int(max_marks),
        status='Draft'
    )
    db.session.add(exam)
    db.session.flush()

    for item in rubrics_data:
        c_name = item.get('criterion_name', '').strip()
        c_marks = item.get('maximum_marks', 0)
        c_weight = item.get('weightage', 1.0)
        if c_name and c_marks:
            rubric = ExaminationRubric(
                examination_id=exam.id,
                criterion_name=c_name,
                maximum_marks=int(c_marks),
                weightage=float(c_weight)
            )
            db.session.add(rubric)

    db.session.commit()
    return jsonify({"message": "Examination created successfully", "exam_id": exam.id}), 201

@admin_bp.route('/examinations/<int:exam_id>/status', methods=['PATCH'])
@role_required('Admin')
def update_exam_status(exam_id):
    exam = Examination.query.get(exam_id)
    if not exam:
        return jsonify({"error": "Examination not found"}), 404

    data = request.get_json() or {}
    new_status = data.get('status')
    valid_statuses = ['Draft', 'Slot Creation', 'Booking Open', 'Closed', 'Completed']

    if new_status not in valid_statuses:
        return jsonify({"error": f"Invalid status. Must be one of {valid_statuses}"}), 400

    exam.status = new_status
    db.session.commit()
    return jsonify({"message": f"Examination status updated to {new_status}"}), 200


# 4. Examiner Management (Admin Creates Staff Accounts)
@admin_bp.route('/examiners', methods=['GET'])
@role_required('Admin')
def list_examiners():
    examiners = User.query.filter_by(role='Examiner').all()
    return jsonify([{
        "id": u.id,
        "name": u.name,
        "email": u.email,
        "is_active": u.is_active,
        "created_at": u.created_at.strftime('%Y-%m-%d') if u.created_at else None
    } for u in examiners]), 200

@admin_bp.route('/examiners', methods=['POST'])
@role_required('Admin')
def create_examiner():
    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()
    name = data.get('name', '').strip()
    password = data.get('password', '')

    if not email or not name or not password:
        return jsonify({"error": "Full name, email, and temporary password are required"}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "Email is already registered in the system"}), 409

    examiner = User(email=email, name=name, role='Examiner', is_active=True)
    examiner.set_password(password)
    db.session.add(examiner)
    db.session.commit()

    return jsonify({"message": "Examiner account created successfully", "examiner_id": examiner.id}), 201

@admin_bp.route('/examiners/<int:examiner_id>/status', methods=['PATCH'])
@role_required('Admin')
def toggle_examiner_status(examiner_id):
    examiner = User.query.filter_by(id=examiner_id, role='Examiner').first()
    if not examiner:
        return jsonify({"error": "Examiner not found"}), 404

    examiner.is_active = not examiner.is_active
    db.session.commit()
    return jsonify({"message": "Examiner status updated", "is_active": examiner.is_active}), 200