import json
import os
from datetime import datetime
from functools import wraps

from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from werkzeug.security import check_password_hash, generate_password_hash


app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "change-me-in-production")
database_url = os.getenv("DATABASE_URL", "sqlite:///hometasks.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql+psycopg2://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


def ensure_sqlite_schema_updates():
    """Add newly introduced columns for existing SQLite DBs (lightweight migration)."""
    if not app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
        return

    def column_names(table_name):
        result = db.session.execute(text(f"PRAGMA table_info({table_name})"))
        return {row[1] for row in result}

    task_columns = column_names("task")
    if "task_type" not in task_columns:
        db.session.execute(text("ALTER TABLE task ADD COLUMN task_type VARCHAR(20) NOT NULL DEFAULT 'text'"))
    if "options_json" not in task_columns:
        db.session.execute(text("ALTER TABLE task ADD COLUMN options_json TEXT"))
    if "max_score" not in task_columns:
        db.session.execute(text("ALTER TABLE task ADD COLUMN max_score INTEGER NOT NULL DEFAULT 100"))

    submission_columns = column_names("submission")
    if "grade" not in submission_columns:
        db.session.execute(text("ALTER TABLE submission ADD COLUMN grade INTEGER"))
    if "teacher_comment" not in submission_columns:
        db.session.execute(text("ALTER TABLE submission ADD COLUMN teacher_comment TEXT"))

    db.session.commit()


@app.before_request
def run_schema_updates_once():
    if app.config.get("_schema_updates_done"):
        return
    db.create_all()
    ensure_sqlite_schema_updates()
    app.config["_schema_updates_done"] = True


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # teacher | student


class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    subject = db.Column(db.String(100), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    deadline = db.Column(db.DateTime, nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    task_type = db.Column(db.String(20), nullable=False, default="text")  # text | multiple_choice
    options_json = db.Column(db.Text, nullable=True)
    max_score = db.Column(db.Integer, nullable=False, default=100)

    @property
    def options(self):
        if not self.options_json:
            return []
        try:
            return json.loads(self.options_json)
        except (json.JSONDecodeError, TypeError):
            return []


class Submission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey("task.id"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    answer_text = db.Column(db.Text, nullable=True)
    answer_link = db.Column(db.String(500), nullable=True)
    answer_image_url = db.Column(db.String(500), nullable=True)
    selected_option = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="submitted")  # submitted | completed
    grade = db.Column(db.Integer, nullable=True)
    teacher_comment = db.Column(db.Text, nullable=True)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (db.UniqueConstraint("task_id", "student_id", name="unique_submission"),)


class Completion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey("task.id"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    completed_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint("task_id", "student_id", name="unique_completion"),)


def login_required(role=None):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            user_id = session.get("user_id")
            if not user_id:
                flash("Сначала войдите в систему.", "warning")
                return redirect(url_for("login"))

            user = db.session.get(User, user_id)
            if not user:
                session.clear()
                flash("Пользователь не найден.", "error")
                return redirect(url_for("login"))

            if role and user.role != role:
                flash("У вас нет доступа к этой странице.", "error")
                return redirect(url_for("tasks"))

            return view_func(*args, **kwargs)

        return wrapped

    return decorator


def get_user_name(user_id):
    user = db.session.get(User, user_id)
    return user.name if user else "Неизвестный"


@app.route("/")
def index():
    if session.get("user_id"):
        return redirect(url_for("tasks"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "")

        if role not in {"teacher", "student"}:
            flash("Выберите корректную роль: учитель или ученик.", "error")
            return render_template("register.html")

        if not name or not email or not password:
            flash("Заполните все поля.", "error")
            return render_template("register.html")

        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash("Пользователь с такой почтой уже существует.", "error")
            return render_template("register.html")

        user = User(
            name=name,
            email=email,
            password_hash=generate_password_hash(password),
            role=role,
        )
        db.session.add(user)
        db.session.commit()
        flash("Регистрация успешна. Теперь войдите.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email).first()
        if not user or not check_password_hash(user.password_hash, password):
            flash("Неверная почта или пароль.", "error")
            return render_template("login.html")

        session["user_id"] = user.id
        flash("Добро пожаловать!", "success")
        return redirect(url_for("tasks"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Вы вышли из аккаунта.", "success")
    return redirect(url_for("login"))


@app.route("/tasks")
@login_required()
def tasks():
    user = db.session.get(User, session["user_id"])
    subject_filter = request.args.get("subject", "").strip()

    query = Task.query
    if subject_filter:
        query = query.filter(Task.subject.ilike(f"%{subject_filter}%"))

    all_tasks = query.order_by(Task.deadline.asc()).all()
    subjects = sorted({task.subject for task in Task.query.all()})

    student_submissions = {}
    completed_task_ids = set()
    if user.role == "student":
        submissions = Submission.query.filter_by(student_id=user.id).all()
        student_submissions = {item.task_id: item for item in submissions}
        completed_task_ids = {item.task_id for item in submissions if item.status == "completed"}

    task_submissions = {}
    if user.role == "teacher":
        task_ids = [task.id for task in all_tasks]
        if task_ids:
            submissions = Submission.query.filter(Submission.task_id.in_(task_ids)).order_by(Submission.submitted_at.desc()).all()
            for submission in submissions:
                task_submissions.setdefault(submission.task_id, []).append(submission)

    return render_template(
        "tasks.html",
        user=user,
        tasks=all_tasks,
        completed_task_ids=completed_task_ids,
        student_submissions=student_submissions,
        task_submissions=task_submissions,
        get_user_name=get_user_name,
        subject_filter=subject_filter,
        subjects=subjects,
        now=datetime.utcnow(),
    )


@app.route("/tasks/add", methods=["GET", "POST"])
@login_required(role="teacher")
def add_task():
    user = db.session.get(User, session["user_id"])

    if request.method == "POST":
        subject = request.form.get("subject", "").strip()
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        deadline_raw = request.form.get("deadline", "").strip()
        task_type = request.form.get("task_type", "text").strip()
        options_raw = request.form.get("options", "").strip()
        max_score_raw = request.form.get("max_score", "100").strip()

        if not all([subject, title, description, deadline_raw]):
            flash("Заполните все поля задания.", "error")
            return render_template("add_task.html", user=user)

        if task_type not in {"text", "multiple_choice"}:
            flash("Выберите корректный тип задания.", "error")
            return render_template("add_task.html", user=user)

        try:
            max_score = int(max_score_raw)
            if max_score < 1:
                raise ValueError
        except ValueError:
            flash("Максимальный балл должен быть целым числом больше 0.", "error")
            return render_template("add_task.html", user=user)

        try:
            deadline = datetime.strptime(deadline_raw, "%Y-%m-%dT%H:%M")
        except ValueError:
            flash("Некорректный формат даты дедлайна.", "error")
            return render_template("add_task.html", user=user)

        options = []
        if task_type == "multiple_choice":
            options = [line.strip() for line in options_raw.splitlines() if line.strip()]
            if len(options) < 2:
                flash("Для multiple choice укажите минимум 2 варианта (каждый с новой строки).", "error")
                return render_template("add_task.html", user=user)

        task = Task(
            subject=subject,
            title=title,
            description=description,
            deadline=deadline,
            teacher_id=user.id,
            task_type=task_type,
            options_json=json.dumps(options, ensure_ascii=False) if options else None,
            max_score=max_score,
        )
        db.session.add(task)
        db.session.commit()
        flash("Задание добавлено.", "success")
        return redirect(url_for("tasks"))

    return render_template("add_task.html", user=user)


@app.route("/tasks/<int:task_id>/submit", methods=["POST"])
@login_required(role="student")
def submit_task(task_id):
    user = db.session.get(User, session["user_id"])
    task = db.session.get(Task, task_id)
    if not task:
        flash("Задание не найдено.", "error")
        return redirect(url_for("tasks"))

    answer_text = request.form.get("answer_text", "").strip()
    answer_link = request.form.get("answer_link", "").strip()
    answer_image_url = request.form.get("answer_image_url", "").strip()
    selected_option = request.form.get("selected_option", "").strip()

    if task.task_type == "multiple_choice":
        if selected_option not in task.options:
            flash("Выберите вариант ответа для теста.", "error")
            return redirect(url_for("tasks"))
    else:
        if not any([answer_text, answer_link, answer_image_url]):
            flash("Добавьте ответ: текст, ссылку или ссылку на фото.", "error")
            return redirect(url_for("tasks"))

    existing_submission = Submission.query.filter_by(task_id=task_id, student_id=user.id).first()
    if existing_submission:
        existing_submission.answer_text = answer_text
        existing_submission.answer_link = answer_link
        existing_submission.answer_image_url = answer_image_url
        existing_submission.selected_option = selected_option
        existing_submission.status = "submitted"
        existing_submission.grade = None
        existing_submission.teacher_comment = None
        existing_submission.submitted_at = datetime.utcnow()
    else:
        submission = Submission(
            task_id=task_id,
            student_id=user.id,
            answer_text=answer_text,
            answer_link=answer_link,
            answer_image_url=answer_image_url,
            selected_option=selected_option,
            status="submitted",
        )
        db.session.add(submission)

    completion = Completion.query.filter_by(task_id=task_id, student_id=user.id).first()
    if completion:
        db.session.delete(completion)

    db.session.commit()
    flash("Решение отправлено учителю на проверку.", "success")
    return redirect(url_for("tasks"))


@app.route("/tasks/<int:task_id>/complete", methods=["POST"])
@login_required(role="student")
def complete_task(task_id):
    user = db.session.get(User, session["user_id"])

    task = db.session.get(Task, task_id)
    if not task:
        flash("Задание не найдено.", "error")
        return redirect(url_for("tasks"))

    existing_completion = Completion.query.filter_by(task_id=task_id, student_id=user.id).first()
    if existing_completion:
        flash("Задание уже отмечено как выполненное.", "warning")
        return redirect(url_for("tasks"))

    completion = Completion(task_id=task_id, student_id=user.id)
    db.session.add(completion)

    submission = Submission.query.filter_by(task_id=task_id, student_id=user.id).first()
    if submission:
        submission.status = "completed"
        submission.reviewed_at = datetime.utcnow()

    db.session.commit()
    flash("Отлично! Задание отмечено как выполненное.", "success")
    return redirect(url_for("tasks"))


@app.route("/submissions/<int:submission_id>/review", methods=["POST"])
@login_required(role="teacher")
def review_submission(submission_id):
    submission = db.session.get(Submission, submission_id)
    if not submission:
        flash("Отправка не найдена.", "error")
        return redirect(url_for("tasks"))

    decision = request.form.get("decision", "")
    grade_raw = request.form.get("grade", "").strip()
    teacher_comment = request.form.get("teacher_comment", "").strip()
    if decision not in {"completed", "submitted"}:
        flash("Некорректное решение проверки.", "error")
        return redirect(url_for("tasks"))

    task = db.session.get(Task, submission.task_id)
    if not task:
        flash("Связанное задание не найдено.", "error")
        return redirect(url_for("tasks"))

    grade = None
    if grade_raw:
        try:
            grade = int(grade_raw)
        except ValueError:
            flash("Оценка должна быть целым числом.", "error")
            return redirect(url_for("tasks"))
        if grade < 0 or grade > task.max_score:
            flash(f"Оценка должна быть в диапазоне 0..{task.max_score}.", "error")
            return redirect(url_for("tasks"))

    submission.status = decision
    submission.grade = grade
    submission.teacher_comment = teacher_comment or None
    submission.reviewed_at = datetime.utcnow()

    completion = Completion.query.filter_by(task_id=submission.task_id, student_id=submission.student_id).first()
    if decision == "completed":
        if not completion:
            db.session.add(Completion(task_id=submission.task_id, student_id=submission.student_id))
    elif completion:
        db.session.delete(completion)

    db.session.commit()
    flash("Статус отправки обновлён.", "success")
    return redirect(url_for("tasks"))


@app.cli.command("init-db")
def init_db_command():
    db.create_all()
    ensure_sqlite_schema_updates()
    print("Database initialized")


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        ensure_sqlite_schema_updates()
    app.run(host="0.0.0.0", port=5000, debug=True)
