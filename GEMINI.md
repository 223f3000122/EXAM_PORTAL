# EMP-V2 Project Context & Strict MAD-2 Rules
- **Project:** Examination Management Portal – V2 (EMP-V2) for IITM MAD-2.
- **Tech Stack (Strict):** Flask RESTful APIs, SQLite via SQLAlchemy ORM (programmatic only, NO manual DB tools), Vue 3 (CDN) + Bootstrap 5 ONLY (NO Tailwind/Vuetify/Bulma), Flask-JWT-Extended RBAC, Redis, Celery + Celery Beat.
- **Completed & Pushed Milestones (M0–M6):**
  * M0: Private repo, .gitignore, requirements.txt, MADII-cs2006 collaborator.
  * M1: models.py (User, Course, Examination, ExaminationRubric, ExaminationSlot, Booking, Evaluation) + init_db.py (programmatic schema + admin@examportal.com / Admin@1234).
  * M2: auth.py (/api/auth/register for Student only, /api/auth/login, /api/auth/me, @role_required).
  * M3: admin.py (Course CRUD, Examination phase management, Examiner provisioning) + Admin UI in templates/index.html.
  * M4: examiner.py (slot creation in 'Slot Creation' phase, roster view, rubric evaluation) + Examiner UI.
  * M5 & M6: student.py (atomic seat booking, duplicate prevention, cancellation, history & results) + Student UI.
- **Remaining Milestones to Verify & Finish:**
  * M7: Celery Worker + Celery Beat (daily upcoming exam reminder, monthly HTML Admin report, async user-triggered CSV export of student booking history).
  * M8: Redis caching with TTL (`setex`) and cache invalidation (`delete`) on frequently accessed GET endpoints.
  * Final Submission: Git commit "Milestone-EMP-V2 Final-Submission", 3-5 page PDF report, 5-10 min demo video, clean ZIP validation.
- **Rules:** Do NOT rewrite working M0–M6 logic unless fixing a concrete bug. Keep Jinja2 `{% raw %}...{% endraw %}` intact in templates/index.html.