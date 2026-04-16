import json
import os
from datetime import datetime
from functools import wraps

from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from werkzeug.security import check_password_hash, generate_password_hash


CLASS_OPTIONS = [
    "5A","5B","6A","6B","7A","7B",
    "8A","8B","9A","9B","10A","10B","11A","11B",
]

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "change-me-in-production")

database_url = os.getenv("DATABASE_URL", "sqlite:///hometasks.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql+psycopg2://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


def ensure_sqlite_schema_updates():
    if not app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
        return

    def column_names(table):
        result = db.session.execute(text(f"PRAGMA table_info({table})"))
        return {row[1] for row in result}

    user_cols = column_names("user")
    if "class_name" not in user_cols:
        db.session.execute(text(
            "ALTER TABLE user ADD COLUMN class_name VARCHAR(50) NOT NULL DEFAULT 'Не указан'"
        ))

    task_cols = column_names("task")
    if "task_type" not in task_cols:
        db.session.execute(text("ALTER TABLE task ADD COLUMN task_type VARCHAR(20) DEFAULT 'text'"))
    if "options_json" not in task_cols:
        db.session.execute(text("ALTER TABLE task ADD COLUMN options_json TEXT"))
    if "max_score" not in task_cols:
        db.session.execute(text("ALTER TABLE task ADD COLUMN max_score INTEGER DEFAULT 100"))
    if "question_count" not in task_cols:
        db.session.execute(text("ALTER TABLE task ADD COLUMN question_count INTEGER DEFAULT 0"))

    sub_cols = column_names("submission")
    if "grade" not in sub_cols:
        db.session.execute(text("ALTER TABLE submission ADD COLUMN grade INTEGER"))
    if "teacher_comment" not in sub_cols:
        db.session.execute(text("ALTER TABLE submission ADD COLUMN teacher_comment TEXT"))
    if "selected_answers_json" not in sub_cols:
        db.session.execute(text("ALTER TABLE submission ADD COLUMN selected_answers_json TEXT"))

    db.session.commit()


@app.before_request
def run_schema_updates_once():
    if app.config.get("_schema_done"):
        return
    db.create_all()
    ensure_sqlite_schema_updates()
    app.config["_schema_done"] = True


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    class_name = db.Column(db.String(50), nullable=False, default="Не указан")


class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    subject = db.Column(db.String(100), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    deadline = db.Column(db.DateTime, nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    task_type = db.Column(db.String(20), default="text")
    options_json = db.Column(db.Text)
    question_count = db.Column(db.Integer, default=0)
    max_score = db.Column(db.Integer, default=100)

    @property
    def test_questions(self):
        if not self.options_json:
            return []
        try:
            data = json.loads(self.options_json)
            return data if isinstance(data, list) else []
        except:
            return []


class Submission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey("task.id"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    answer_text = db.Column(db.Text)
    answer_link = db.Column(db.String(500))
    answer_image_url = db.Column(db.String(500))
    selected_answers_json = db.Column(db.Text)

    status = db.Column(db.String(20), default="submitted")
    grade = db.Column(db.Integer)
    teacher_comment = db.Column(db.Text)

    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_at = db.Column(db.DateTime)

    __table_args__ = (db.UniqueConstraint("task_id", "student_id"),)


class Completion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer)
    student_id = db.Column(db.Integer)
    completed_at = db.Column(db.DateTime, default=datetime.utcnow)


def login_required(role=None):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            user_id = session.get("user_id")
            if not user_id:
                return redirect(url_for("login"))

            user = db.session.get(User, user_id)
            if not user:
                session.clear()
                return redirect(url_for("login"))

            if role and user.role != role:
                return redirect(url_for("tasks"))

            return func(*args, **kwargs)
        return wrapper
    return decorator


def get_user_name(user_id):
    user = db.session.get(User, user_id)
    return user.name if user else "Неизвестный"


def class_options():
    return CLASS_OPTIONS


@app.route("/")
def index():
    if session.get("user_id"):
        return redirect(url_for("tasks"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        user = User(
            name=request.form["name"],
            email=request.form["email"],
            password_hash=generate_password_hash(request.form["password"]),
            role=request.form["role"],
            class_name=request.form.get("class_name", "Не указан")
        )
        db.session.add(user)
        db.session.commit()
        return redirect(url_for("login"))

    return render_template("register.html", class_options=CLASS_OPTIONS)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(email=request.form["email"]).first()
        if user and check_password_hash(user.password_hash, request.form["password"]):
            session["user_id"] = user.id
            return redirect(url_for("tasks"))
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/tasks")
@login_required()
def tasks():
    tasks = Task.query.order_by(Task.deadline.asc()).all()
    return render_template("tasks.html", tasks=tasks)


@app.route("/tasks/add", methods=["GET", "POST"])
@login_required(role="teacher")
def add_task():
    if request.method == "POST":
        task = Task(
            subject=request.form["subject"],
            title=request.form["title"],
            description=request.form["description"],
            deadline=datetime.strptime(request.form["deadline"], "%Y-%m-%dT%H:%M"),
            teacher_id=session["user_id"]
        )
        db.session.add(task)
        db.session.commit()
        return redirect(url_for("tasks"))

    return render_template("add_task.html")


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        ensure_sqlite_schema_updates()

    app.run(host="0.0.0.0", port=5000, debug=True)