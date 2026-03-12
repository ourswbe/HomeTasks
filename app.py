from datetime import datetime
from functools import wraps

from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash


app = Flask(__name__)
app.config["SECRET_KEY"] = "change-me-in-production"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///hometasks.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


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

    completed_task_ids = set()
    if user.role == "student":
        completions = Completion.query.filter_by(student_id=user.id).all()
        completed_task_ids = {item.task_id for item in completions}

    return render_template(
        "tasks.html",
        user=user,
        tasks=all_tasks,
        completed_task_ids=completed_task_ids,
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

        if not all([subject, title, description, deadline_raw]):
            flash("Заполните все поля задания.", "error")
            return render_template("add_task.html", user=user)

        try:
            deadline = datetime.strptime(deadline_raw, "%Y-%m-%dT%H:%M")
        except ValueError:
            flash("Некорректный формат даты дедлайна.", "error")
            return render_template("add_task.html", user=user)

        task = Task(
            subject=subject,
            title=title,
            description=description,
            deadline=deadline,
            teacher_id=user.id,
        )
        db.session.add(task)
        db.session.commit()
        flash("Задание добавлено.", "success")
        return redirect(url_for("tasks"))

    return render_template("add_task.html", user=user)


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
    db.session.commit()
    flash("Отлично! Задание отмечено как выполненное.", "success")
    return redirect(url_for("tasks"))


@app.cli.command("init-db")
def init_db_command():
    db.create_all()
    print("Database initialized")


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=5000, debug=True)
