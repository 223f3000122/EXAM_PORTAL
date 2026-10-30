from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='Student')  # Admin, Examiner, Student
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    slots = db.relationship('ExaminationSlot', backref='examiner', lazy=True)
    bookings = db.relationship('Booking', backref='student', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Course(db.Model):
    __tablename__ = 'courses'
    id = db.Column(db.Integer, primary_key=True)
    course_code = db.Column(db.String(20), unique=True, nullable=False)
    course_name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='Active')  # Active, Inactive

    examinations = db.relationship('Examination', backref='course', cascade="all, delete-orphan", lazy=True)


class Examination(db.Model):
    __tablename__ = 'examinations'
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    examination_name = db.Column(db.String(150), nullable=False)
    exam_type = db.Column(db.String(50), default='Viva')  # Viva, Practical, Project Demo
    duration = db.Column(db.Integer, nullable=False)      # In minutes
    maximum_marks = db.Column(db.Integer, nullable=False, default=100)
    slot_creation_start_date = db.Column(db.DateTime, nullable=True)
    slot_creation_end_date = db.Column(db.DateTime, nullable=True)
    slot_booking_start_date = db.Column(db.DateTime, nullable=True)
    slot_booking_end_date = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(30), default='Draft')    # Draft, Slot Creation, Booking Open, Closed, Completed

    rubrics = db.relationship('ExaminationRubric', backref='examination', cascade="all, delete-orphan", lazy=True)
    slots = db.relationship('ExaminationSlot', backref='examination', cascade="all, delete-orphan", lazy=True)


class ExaminationRubric(db.Model):
    __tablename__ = 'examination_rubrics'
    id = db.Column(db.Integer, primary_key=True)
    examination_id = db.Column(db.Integer, db.ForeignKey('examinations.id'), nullable=False)
    criterion_name = db.Column(db.String(100), nullable=False)
    maximum_marks = db.Column(db.Integer, nullable=False)
    weightage = db.Column(db.Float, default=1.0)
    description = db.Column(db.Text, nullable=True)


class ExaminationSlot(db.Model):
    __tablename__ = 'examination_slots'
    id = db.Column(db.Integer, primary_key=True)
    examination_id = db.Column(db.Integer, db.ForeignKey('examinations.id'), nullable=False)
    examiner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    slot_date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    maximum_capacity = db.Column(db.Integer, default=1)
    available_seats = db.Column(db.Integer, default=1)
    meeting_link = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(20), default='Available')  # Available, Full, Cancelled, Completed

    bookings = db.relationship('Booking', backref='slot', cascade="all, delete-orphan", lazy=True)


class Booking(db.Model):
    __tablename__ = 'bookings'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    slot_id = db.Column(db.Integer, db.ForeignKey('examination_slots.id'), nullable=False)
    booking_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='Booked')  # Booked, Cancelled, Completed

    evaluation = db.relationship('Evaluation', backref='booking', uselist=False, cascade="all, delete-orphan")


class Evaluation(db.Model):
    __tablename__ = 'evaluations'
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey('bookings.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    examiner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    total_marks = db.Column(db.Float, nullable=False)
    remarks = db.Column(db.Text, nullable=True)
    evaluation_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='Completed')