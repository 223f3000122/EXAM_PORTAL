import os
import csv
from datetime import datetime, timedelta
from celery import Celery
from celery.schedules import crontab

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
EXPORT_DIR = os.path.join(BASE_DIR, 'exports')

celery = Celery(
    'emp_tasks',
    broker='redis://localhost:6379/0',
    backend='redis://localhost:6379/0'
)

celery.conf.timezone = 'Asia/Kolkata'
celery.conf.beat_schedule = {
    'daily-exam-reminders': {
        'task': 'tasks.send_daily_exam_reminders',
        'schedule': crontab(hour=8, minute=0),
    },
    'monthly-admin-report': {
        'task': 'tasks.generate_monthly_admin_report',
        'schedule': crontab(day_of_month=1, hour=9, minute=0),
    },
}


@celery.task(name='tasks.send_daily_exam_reminders')
def send_daily_exam_reminders():
    from app import create_app
    from models import Booking, ExaminationSlot

    flask_app = create_app()
    with flask_app.app_context():
        tomorrow = (datetime.utcnow() + timedelta(days=1)).date()
        upcoming = Booking.query.join(ExaminationSlot).filter(
            Booking.status == 'Booked',
            ExaminationSlot.slot_date == tomorrow
        ).all()

        reminders = []
        for b in upcoming:
            examiner_name = b.slot.examiner.name if (b.slot and b.slot.examiner) else "Assigned Examiner"
            msg = (
                f"[REMINDER] Student: {b.student.email} | Exam: {b.slot.examination.examination_name} | "
                f"Date/Time: {b.slot.slot_date} {b.slot.start_time.strftime('%H:%M')} | "
                f"Examiner: {examiner_name}"
            )
            print(msg)
            reminders.append(msg)

        return {"date": str(tomorrow), "reminders_sent": len(reminders)}


@celery.task(name='tasks.generate_monthly_admin_report')
def generate_monthly_admin_report():
    from app import create_app
    from models import Examination, Booking, Evaluation, User

    flask_app = create_app()
    with flask_app.app_context():
        total_exams = Examination.query.count()
        completed_bookings = Booking.query.filter_by(status='Completed').count()
        evaluated_students = Evaluation.query.count()
        active_examiners = User.query.filter_by(role='Examiner', is_active=True).count()

        os.makedirs(EXPORT_DIR, exist_ok=True)
        report_path = os.path.join(EXPORT_DIR, f"monthly_admin_report_{datetime.utcnow().strftime('%Y_%m')}.html")
        html_content = f"""
        <html><body>
            <h2>EMP-V2 Monthly Examination Summary Report</h2>
            <ul>
                <li><strong>Examinations Conducted:</strong> {total_exams}</li>
                <li><strong>Evaluated Students:</strong> {evaluated_students}</li>
                <li><strong>Completed Bookings:</strong> {completed_bookings}</li>
                <li><strong>Active Examiners:</strong> {active_examiners}</li>
            </ul>
        </body></html>
        """
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        print(f"[MONTHLY REPORT] Generated at {report_path}")
        return {"report_path": report_path, "evaluated_students": evaluated_students}


@celery.task(name='tasks.export_student_history_csv')
def export_student_history_csv(student_id):
    from app import create_app
    from models import Booking, User

    flask_app = create_app()
    with flask_app.app_context():
        student = User.query.get(student_id)
        bookings = Booking.query.filter_by(student_id=student_id).all()

        os.makedirs(EXPORT_DIR, exist_ok=True)
        filename = f"student_{student_id}_history_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
        filepath = os.path.join(EXPORT_DIR, filename)

        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow([
                'Student ID', 'Examination Name', 'Course',
                'Examination Date', 'Examiner', 'Marks Obtained', 'Booking Status'
            ])
            for b in bookings:
                slot = b.slot
                exam = slot.examination if slot else None
                course = exam.course.course_code if (exam and exam.course) else 'N/A'
                examiner_name = slot.examiner.name if (slot and slot.examiner) else 'N/A'
                marks = b.evaluation.total_marks if b.evaluation else 'Pending'

                writer.writerow([
                    student.id if student else student_id,
                    exam.examination_name if exam else 'N/A',
                    course,
                    slot.slot_date.strftime('%Y-%m-%d') if slot else 'N/A',
                    examiner_name,
                    marks,
                    b.status
                ])

        print(f"[CSV EXPORT] Saved {filepath}")
        return {"file": filename, "rows": len(bookings)}