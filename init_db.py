import os
from flask import Flask
from models import db, User, Course

def create_app():
    app = Flask(__name__)
    # Configure SQLite database location
    db_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'exam_portal.db')
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)
    return app

def initialize_database():
    app = create_app()
    with app.app_context():
        # 1. Programmatic table creation (Mandatory for MAD-II)
        print("Creating all database tables programmatically...")
        db.create_all()

        # 2. Seed Pre-existing Admin (Mandatory requirement)
        admin_email = "admin@examportal.com"
        admin = User.query.filter_by(email=admin_email).first()

        if not admin:
            print("Creating pre-existing superuser Admin...")
            admin_user = User(
                email=admin_email,
                name="Portal Administrator",
                role="Admin",
                is_active=True
            )
            # Werkzeug secure hash
            admin_user.set_password("Admin@1234")
            db.session.add(admin_user)
        else:
            print("Admin user already exists.")

        # 3. Seed an initial sample course for testing
        sample_course = Course.query.filter_by(course_code="CS2006").first()
        if not sample_course:
            print("Seeding initial course: CS2006...")
            course = Course(
                course_code="CS2006",
                course_name="Modern Application Development II",
                description="Core MAD-II course portal for assessments.",
                status="Active"
            )
            db.session.add(course)

        # Commit all changes to SQLite
        db.session.commit()
        print("Database initialized successfully!")

if __name__ == '__main__':
    initialize_database()