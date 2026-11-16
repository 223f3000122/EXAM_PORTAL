from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_jwt_extended import get_jwt_identity
from models import db, Examination, ExaminationSlot, Booking, User, Evaluation
from auth import role_required

examiner_bp = Blueprint('examiner', __name__, url_prefix='/api/examiner')


# 1. Dashboard Summary & Available Examinations for Slot Creation
@examiner_bp.route('/dashboard', methods=['GET'])
@role_required('Examiner')
def get_examiner_dashboard():
    examiner_id = int(get_jwt_identity())

    # Fetch exams currently in 'Slot Creation' or exams where this examiner already hosts slots
    open_exams = Examination.query.filter_by(status='Slot Creation').all()
    my_slots = ExaminationSlot.query.filter_by(examiner_id=examiner_id).order_by(ExaminationSlot.slot_date.asc(), ExaminationSlot.start_time.asc()).all()

    total_booked = 0
    pending_evaluations = 0
    slot_list = []

    for slot in my_slots:
        booked_count = slot.maximum_capacity - slot.available_seats
        total_booked += booked_count

        # Count bookings in this slot that do not yet have an evaluation
        slot_pending = sum(1 for b in slot.bookings if b.status == 'Booked' and not b.evaluation)
        pending_evaluations += slot_pending

        slot_list.append({
            "id": slot.id,
            "examination_id": slot.examination_id,
            "examination_name": slot.examination.examination_name if slot.examination else "N/A",
            "course_code": slot.examination.course.course_code if (slot.examination and slot.examination.course) else "N/A",
            "exam_status": slot.examination.status if slot.examination else "N/A",
            "slot_date": slot.slot_date.strftime('%Y-%m-%d'),
            "start_time": slot.start_time.strftime('%H:%M'),
            "end_time": slot.end_time.strftime('%H:%M'),
            "maximum_capacity": slot.maximum_capacity,
            "available_seats": slot.available_seats,
            "booked_count": booked_count,
            "pending_evaluations": slot_pending
        })

    return jsonify({
        "stats": {
            "open_exams_count": len(open_exams),
            "created_slots_count": len(my_slots),
            "total_students_booked": total_booked,
            "pending_evaluations": pending_evaluations
        },
        "available_exams": [{
            "id": e.id,
            "course_code": e.course.course_code if e.course else "N/A",
            "examination_name": e.examination_name,
            "exam_type": e.exam_type,
            "duration": e.duration,
            "status": e.status
        } for e in open_exams],
        "slots": slot_list
    }), 200


# 2. Create Examination Slot (Allowed ONLY during 'Slot Creation' phase)
@examiner_bp.route('/slots', methods=['POST'])
@role_required('Examiner')
def create_slot():
    examiner_id = int(get_jwt_identity())
    data = request.get_json() or {}

    examination_id = data.get('examination_id')
    slot_date_str = data.get('slot_date', '').strip()     # Expected: YYYY-MM-DD
    start_time_str = data.get('start_time', '').strip()   # Expected: HH:MM
    end_time_str = data.get('end_time', '').strip()       # Expected: HH:MM
    max_capacity = data.get('maximum_capacity', 5)

    if not all([examination_id, slot_date_str, start_time_str, end_time_str]):
        return jsonify({"error": "Examination, date, start time, and end time are required"}), 400

    exam = Examination.query.get(examination_id)
    if not exam:
        return jsonify({"error": "Examination not found"}), 404

    # Enforce strict Milestone 4 & 6 phase rule
    if exam.status != 'Slot Creation':
        return jsonify({
            "error": f"Cannot create slots while examination status is '{exam.status}'. Must be 'Slot Creation'."
        }), 400

    try:
        slot_date = datetime.strptime(slot_date_str, '%Y-%m-%d').date()
        start_time = datetime.strptime(start_time_str, '%H:%M').time()
        end_time = datetime.strptime(end_time_str, '%H:%M').time()
        max_capacity = int(max_capacity)
    except ValueError:
        return jsonify({"error": "Invalid date/time format or capacity value"}), 400

    if start_time >= end_time:
        return jsonify({"error": "End time must be strictly after start time"}), 400

    if max_capacity < 1:
        return jsonify({"error": "Maximum capacity must be at least 1"}), 400

    # Prevent overlapping slots for the same examiner on the same date
    existing_slots = ExaminationSlot.query.filter_by(
        examiner_id=examiner_id,
        slot_date=slot_date
    ).all()

    for existing in existing_slots:
        if start_time < existing.end_time and end_time > existing.start_time:
            return jsonify({
                "error": f"Time conflict with your existing slot ({existing.start_time.strftime('%H:%M')} - {existing.end_time.strftime('%H:%M')})"
            }), 409

    new_slot = ExaminationSlot(
        examination_id=exam.id,
        examiner_id=examiner_id,
        slot_date=slot_date,
        start_time=start_time,
        end_time=end_time,
        maximum_capacity=max_capacity,
        available_seats=max_capacity
    )
    db.session.add(new_slot)
    db.session.commit()

    return jsonify({"message": "Examination slot created successfully", "slot_id": new_slot.id}), 201


# 3. Delete Slot (Allowed ONLY if owned by Examiner AND zero students have booked)
@examiner_bp.route('/slots/<int:slot_id>', methods=['DELETE'])
@role_required('Examiner')
def delete_slot(slot_id):
    examiner_id = int(get_jwt_identity())
    slot = ExaminationSlot.query.get(slot_id)

    if not slot:
        return jsonify({"error": "Slot not found"}), 404

    if slot.examiner_id != examiner_id:
        return jsonify({"error": "Forbidden: You can only manage your own slots"}), 403

    if slot.available_seats < slot.maximum_capacity or len(slot.bookings) > 0:
        return jsonify({"error": "Cannot delete slot after students have booked seats"}), 400

    db.session.delete(slot)
    db.session.commit()
    return jsonify({"message": "Examination slot removed successfully"}), 200


# 4. View Booked Students for a Specific Slot (Strict Ownership Check)
@examiner_bp.route('/slots/<int:slot_id>/bookings', methods=['GET'])
@role_required('Examiner')
def get_slot_bookings(slot_id):
    examiner_id = int(get_jwt_identity())
    slot = ExaminationSlot.query.get(slot_id)

    if not slot:
        return jsonify({"error": "Slot not found"}), 404

    if slot.examiner_id != examiner_id:
        return jsonify({"error": "Forbidden: Access restricted to assigned examiner"}), 403

    bookings_data = []
    for b in slot.bookings:
        bookings_data.append({
            "booking_id": b.id,
            "student_id": b.student.id,
            "student_name": b.student.name,
            "student_email": b.student.email,
            "status": b.status,
            "booked_at": b.booking_date.strftime('%Y-%m-%d %H:%M') if b.booking_date else "N/A",
            "evaluated": bool(b.evaluation),
            "marks_obtained": b.evaluation.total_marks if b.evaluation else None,
            "remarks": b.evaluation.remarks if b.evaluation else ""
        })

    return jsonify({
        "slot_id": slot.id,
        "examination_name": slot.examination.examination_name,
        "maximum_marks": slot.examination.maximum_marks,
        "rubrics": [{
            "id": r.id,
            "criterion_name": r.criterion_name,
            "maximum_marks": r.maximum_marks
        } for r in slot.examination.rubrics],
        "bookings": bookings_data
    }), 200


# 5. Evaluate a Booked Student (create or update Evaluation; strict ownership check)
@examiner_bp.route('/bookings/<int:booking_id>/evaluate', methods=['POST'])
@role_required('Examiner')
def evaluate_booking(booking_id):
    examiner_id = int(get_jwt_identity())
    booking = Booking.query.get(booking_id)

    if not booking:
        return jsonify({"error": "Booking not found"}), 404

    slot = booking.slot
    if not slot or slot.examiner_id != examiner_id:
        return jsonify({"error": "Forbidden: You can only evaluate students in your own slots"}), 403

    if booking.status == 'Cancelled':
        return jsonify({"error": "Cannot evaluate a cancelled booking"}), 400

    exam = slot.examination
    data = request.get_json() or {}

    raw_marks = data.get('total_marks')
    if raw_marks is None or str(raw_marks).strip() == '':
        return jsonify({"error": "Total marks are required"}), 400
    try:
        total_marks = float(raw_marks)
    except (TypeError, ValueError):
        return jsonify({"error": "Total marks must be a number"}), 400

    if total_marks < 0 or total_marks > exam.maximum_marks:
        return jsonify({"error": f"Marks must be between 0 and {exam.maximum_marks}"}), 400

    remarks = data.get('remarks') or ''
    if not isinstance(remarks, str):
        return jsonify({"error": "Remarks must be text"}), 400
    remarks = remarks.strip()
    if len(remarks) > 2000:
        return jsonify({"error": "Remarks must not exceed 2000 characters"}), 400

    evaluation = booking.evaluation
    if evaluation:
        evaluation.total_marks = total_marks
        evaluation.remarks = remarks
        evaluation.examiner_id = examiner_id
        evaluation.evaluation_date = datetime.utcnow()
        evaluation.status = 'Completed'
        message = "Evaluation updated successfully"
    else:
        evaluation = Evaluation(
            booking_id=booking.id,
            student_id=booking.student_id,
            examiner_id=examiner_id,
            total_marks=total_marks,
            remarks=remarks,
            status='Completed'
        )
        db.session.add(evaluation)
        message = "Evaluation recorded successfully"

    booking.status = 'Completed'
    db.session.commit()

    return jsonify({
        "message": message,
        "booking_id": booking.id,
        "total_marks": evaluation.total_marks,
        "remarks": evaluation.remarks
    }), 200