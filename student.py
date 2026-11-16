from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_jwt_extended import get_jwt_identity
from models import db, Examination, ExaminationSlot, Booking, User
from auth import role_required

student_bp = Blueprint('student', __name__, url_prefix='/api/student')


def _serialize_booking(b):
    slot = b.slot
    exam = slot.examination if slot else None
    ev = b.evaluation
    slot_dt = datetime.combine(slot.slot_date, slot.start_time) if slot else None
    return {
        "booking_id": b.id,
        "status": b.status,
        "booking_date": b.booking_date.strftime('%Y-%m-%d %H:%M') if b.booking_date else None,
        "slot_id": slot.id if slot else None,
        "slot_date": slot.slot_date.strftime('%Y-%m-%d') if slot else None,
        "start_time": slot.start_time.strftime('%H:%M') if slot else None,
        "end_time": slot.end_time.strftime('%H:%M') if slot else None,
        "is_upcoming": bool(slot_dt and slot_dt >= datetime.now() and b.status == 'Booked'),
        "examiner_name": slot.examiner.name if (slot and slot.examiner) else "N/A",
        "meeting_link": slot.meeting_link if slot else None,
        "examination_id": exam.id if exam else None,
        "examination_name": exam.examination_name if exam else "N/A",
        "course_code": exam.course.course_code if (exam and exam.course) else "N/A",
        "exam_type": exam.exam_type if exam else None,
        "maximum_marks": exam.maximum_marks if exam else None,
        "evaluation": {
            "total_marks": ev.total_marks,
            "remarks": ev.remarks or "",
            "evaluation_date": ev.evaluation_date.strftime('%Y-%m-%d %H:%M') if ev.evaluation_date else None
        } if ev else None
    }


# 1. Student Dashboard: open exams with available slots + own bookings/history
@student_bp.route('/dashboard', methods=['GET'])
@role_required('Student')
def get_student_dashboard():
    student_id = int(get_jwt_identity())
    student = User.query.get(student_id)

    my_bookings = Booking.query.filter_by(student_id=student_id) \
        .order_by(Booking.booking_date.desc()).all()

    # Exams for which the student already holds an active (Booked/Completed) booking
    active_exam_ids = {
        b.slot.examination_id for b in my_bookings
        if b.slot and b.status in ('Booked', 'Completed')
    }

    open_exams = Examination.query.filter_by(status='Booking Open').all()
    exams_data = []
    for e in open_exams:
        slots = ExaminationSlot.query.filter(
            ExaminationSlot.examination_id == e.id,
            ExaminationSlot.available_seats > 0
        ).order_by(ExaminationSlot.slot_date.asc(), ExaminationSlot.start_time.asc()).all()

        exams_data.append({
            "id": e.id,
            "examination_name": e.examination_name,
            "course_code": e.course.course_code if e.course else "N/A",
            "course_name": e.course.course_name if e.course else "N/A",
            "exam_type": e.exam_type,
            "duration": e.duration,
            "maximum_marks": e.maximum_marks,
            "already_booked": e.id in active_exam_ids,
            "slots": [{
                "id": s.id,
                "slot_date": s.slot_date.strftime('%Y-%m-%d'),
                "start_time": s.start_time.strftime('%H:%M'),
                "end_time": s.end_time.strftime('%H:%M'),
                "available_seats": s.available_seats,
                "maximum_capacity": s.maximum_capacity,
                "examiner_name": s.examiner.name if s.examiner else "N/A"
            } for s in slots]
        })

    bookings_data = [_serialize_booking(b) for b in my_bookings]

    return jsonify({
        "profile": {"id": student.id, "name": student.name, "email": student.email},
        "stats": {
            "open_exams": len(open_exams),
            "upcoming": sum(1 for b in my_bookings if b.status == 'Booked'),
            "completed": sum(1 for b in my_bookings if b.status == 'Completed'),
            "cancelled": sum(1 for b in my_bookings if b.status == 'Cancelled')
        },
        "open_exams": exams_data,
        "bookings": bookings_data
    }), 200


# 2. Book a Slot (atomic seat decrement)
@student_bp.route('/book', methods=['POST'])
@role_required('Student')
def book_slot():
    student_id = int(get_jwt_identity())
    data = request.get_json() or {}

    try:
        slot_id = int(data.get('slot_id'))
    except (TypeError, ValueError):
        return jsonify({"error": "A valid slot_id is required"}), 400

    slot = ExaminationSlot.query.get(slot_id)
    if not slot:
        return jsonify({"error": "Slot not found"}), 404

    exam = slot.examination
    if not exam or exam.status != 'Booking Open':
        return jsonify({"error": "Booking is not open for this examination"}), 400

    # Prevent duplicate active booking for the same examination
    duplicate = Booking.query.join(ExaminationSlot, Booking.slot_id == ExaminationSlot.id).filter(
        Booking.student_id == student_id,
        ExaminationSlot.examination_id == exam.id,
        Booking.status.in_(['Booked', 'Completed'])
    ).first()
    if duplicate:
        return jsonify({"error": "You already have an active booking for this examination"}), 409

    if slot.available_seats <= 0:
        return jsonify({"error": "This slot is fully booked"}), 409

    try:
        # Atomic conditional decrement: only succeeds if a seat is still free at write time
        updated = ExaminationSlot.query.filter(
            ExaminationSlot.id == slot.id,
            ExaminationSlot.available_seats > 0
        ).update(
            {ExaminationSlot.available_seats: ExaminationSlot.available_seats - 1},
            synchronize_session=False
        )
        if updated == 0:
            db.session.rollback()
            return jsonify({"error": "This slot was just filled. Please choose another."}), 409

        booking = Booking(student_id=student_id, slot_id=slot.id, status='Booked')
        db.session.add(booking)
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Booking failed due to a server error"}), 500

    return jsonify({"message": "Slot booked successfully", "booking_id": booking.id}), 201


# 3. Cancel a Booking (restores the seat)
@student_bp.route('/bookings/<int:booking_id>/cancel', methods=['PATCH'])
@role_required('Student')
def cancel_booking(booking_id):
    student_id = int(get_jwt_identity())
    booking = Booking.query.get(booking_id)

    if not booking:
        return jsonify({"error": "Booking not found"}), 404
    if booking.student_id != student_id:
        return jsonify({"error": "Forbidden: You can only cancel your own bookings"}), 403
    if booking.status != 'Booked':
        return jsonify({"error": f"Cannot cancel a booking with status '{booking.status}'"}), 400

    try:
        booking.status = 'Cancelled'
        ExaminationSlot.query.filter(ExaminationSlot.id == booking.slot_id).update(
            {ExaminationSlot.available_seats: ExaminationSlot.available_seats + 1},
            synchronize_session=False
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Cancellation failed due to a server error"}), 500

    return jsonify({"message": "Booking cancelled successfully"}), 200


# 4. Update Student Profile (name only)
@student_bp.route('/profile', methods=['PATCH'])
@role_required('Student')
def update_profile():
    student_id = int(get_jwt_identity())
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()

    if not name:
        return jsonify({"error": "Name is required"}), 400
    if len(name) > 100:
        return jsonify({"error": "Name must not exceed 100 characters"}), 400

    student = User.query.get(student_id)
    student.name = name
    db.session.commit()
    return jsonify({"message": "Profile updated successfully", "name": student.name}), 200
