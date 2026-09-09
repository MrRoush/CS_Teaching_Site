import os
import sqlite3
import json
from datetime import datetime
from functools import wraps

from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, 'cs_teaching.db')
GODOT_EDITOR_URL = 'https://editor.godotengine.org/releases/4.7.2.stable/godot.editor.html'

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY') or os.urandom(24).hex()


def get_db():
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys = ON')
    return db


def init_db():
    db = get_db()

    db.executescript(
        '''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            role TEXT NOT NULL CHECK(role IN ('teacher', 'student')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS course_offerings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            focus_area TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (teacher_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS module_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            summary TEXT NOT NULL,
            objectives TEXT NOT NULL DEFAULT '',
            lesson_type TEXT NOT NULL CHECK(lesson_type IN ('video', 'slides', 'project', 'mixed')),
            content_url TEXT,
            slide_url TEXT,
            godot_template_url TEXT,
            activity_video BOOLEAN DEFAULT 1,
            activity_slides BOOLEAN DEFAULT 1,
            activity_quiz BOOLEAN DEFAULT 1,
            activity_project BOOLEAN DEFAULT 1,
            quiz_prompt TEXT NOT NULL,
            quiz_questions_json TEXT NOT NULL DEFAULT '[]',
            quiz_max_attempts INTEGER NOT NULL DEFAULT 1,
            quiz_allow_reassessment BOOLEAN DEFAULT 0,
            project_brief TEXT NOT NULL,
            godot_enabled BOOLEAN DEFAULT 0,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (created_by) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS course_modules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL,
            module_template_id INTEGER NOT NULL,
            module_title TEXT NOT NULL,
            position INTEGER NOT NULL,
            required BOOLEAN DEFAULT 1,
            due_date TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (course_id) REFERENCES course_offerings(id) ON DELETE CASCADE,
            FOREIGN KEY (module_template_id) REFERENCES module_templates(id)
        );

        CREATE TABLE IF NOT EXISTS enrollments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (course_id) REFERENCES course_offerings(id) ON DELETE CASCADE,
            FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE(course_id, student_id)
        );

        CREATE TABLE IF NOT EXISTS project_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_module_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            submission_link TEXT NOT NULL,
            notes TEXT,
            status TEXT NOT NULL DEFAULT 'submitted' CHECK(status IN ('submitted', 'in_review', 'graded', 'revision_requested')),
            score INTEGER CHECK(score BETWEEN 0 AND 100),
            grading_mode TEXT NOT NULL DEFAULT 'points',
            rubric_notes TEXT,
            feedback TEXT,
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            graded_at TIMESTAMP,
            FOREIGN KEY (course_module_id) REFERENCES course_modules(id) ON DELETE CASCADE,
            FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE(course_module_id, student_id)
        );

        CREATE TABLE IF NOT EXISTS quiz_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_module_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            attempt_number INTEGER NOT NULL,
            responses_json TEXT NOT NULL,
            score INTEGER CHECK(score BETWEEN 0 AND 100),
            feedback TEXT,
            graded_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (course_module_id) REFERENCES course_modules(id) ON DELETE CASCADE,
            FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE(course_module_id, student_id, attempt_number)
        );
        '''
    )

    def ensure_column(table_name, column_name, definition):
        columns = {column['name'] for column in db.execute(f'PRAGMA table_info({table_name})').fetchall()}
        if column_name not in columns:
            db.execute(f'ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}')

    ensure_column('module_templates', 'objectives', "TEXT NOT NULL DEFAULT ''")
    ensure_column('module_templates', 'godot_template_url', 'TEXT')
    ensure_column('module_templates', 'activity_video', 'BOOLEAN DEFAULT 1')
    ensure_column('module_templates', 'activity_slides', 'BOOLEAN DEFAULT 1')
    ensure_column('module_templates', 'activity_quiz', 'BOOLEAN DEFAULT 1')
    ensure_column('module_templates', 'activity_project', 'BOOLEAN DEFAULT 1')
    ensure_column('module_templates', 'quiz_questions_json', "TEXT NOT NULL DEFAULT '[]'")
    ensure_column('module_templates', 'quiz_max_attempts', 'INTEGER NOT NULL DEFAULT 1')
    ensure_column('module_templates', 'quiz_allow_reassessment', 'BOOLEAN DEFAULT 0')
    ensure_column('course_modules', 'due_date', 'TEXT')
    ensure_column('project_submissions', 'grading_mode', "TEXT NOT NULL DEFAULT 'points'")
    ensure_column('project_submissions', 'rubric_notes', 'TEXT')

    user_count = db.execute('SELECT COUNT(*) AS count FROM users').fetchone()['count']
    if user_count == 0:
        db.executemany(
            'INSERT INTO users (name, email, role) VALUES (?, ?, ?)',
            [
                ('Avery Teacher', 'avery.teacher@school.demo', 'teacher'),
                ('Jordan Student', 'jordan.student@school.demo', 'student'),
                ('Casey Student', 'casey.student@school.demo', 'student'),
            ],
        )

        teacher_id = db.execute("SELECT id FROM users WHERE email = 'avery.teacher@school.demo'").fetchone()['id']

        module_templates = [
            (
                'Godot Onboarding Studio',
                'Introduce the Godot 4.7.2 interface, navigation, and a first playable scene.',
                'Understand core Godot editor panels and build confidence with scene setup basics.',
                'video',
                'https://www.youtube.com/embed/nAh_Kx5Zh5Q',
                'https://docs.google.com/presentation/d/e/2PACX-1vQ-demo-godot-intro/embed?start=false&loop=false&delayms=3000',
                'https://github.com/godotengine/godot-demo-projects',
                1,
                1,
                1,
                1,
                'What editor panels should students keep visible while building their first scene, and why?',
                json.dumps(
                    [
                        {
                            'type': 'mcq',
                            'question': 'Which panel is used to manage nodes in the active scene?',
                            'options': ['Inspector', 'Scene Tree', 'FileSystem', 'Debugger'],
                            'answer': 'B',
                        },
                        {
                            'type': 'short',
                            'question': 'Explain one habit that helps you keep a Godot scene organized.',
                        },
                    ]
                ),
                2,
                1,
                'Build a starter scene and share either a hosted build, repository link, or exported project archive.',
                1,
                teacher_id,
            ),
            (
                'Systems Thinking With Game Loops',
                'Connect event loops, state, and debugging habits to a classroom game design workflow.',
                'Describe the flow of input, simulation, and rendering inside a game loop.',
                'slides',
                'https://www.youtube.com/embed/QKgTZWbwD1U',
                'https://docs.google.com/presentation/d/e/2PACX-1vQ-demo-game-loops/embed?start=false&loop=false&delayms=3000',
                '',
                1,
                1,
                1,
                1,
                'Describe how a game loop updates input, simulation, and rendering during each frame.',
                json.dumps(
                    [
                        {
                            'type': 'mcq',
                            'question': 'Which step should happen after reading input in a typical frame?',
                            'options': ['Restart the game', 'Update simulation state', 'Export project files', 'Close debugger'],
                            'answer': 'B',
                        }
                    ]
                ),
                1,
                0,
                'Create a short reflection and pseudocode for the loop you will use in your project.',
                0,
                teacher_id,
            ),
            (
                'Arcade Prototype Sprint',
                'Guide students through building and submitting a small Godot arcade prototype for feedback.',
                'Plan, build, and iterate on a complete mini game with measurable gameplay goals.',
                'mixed',
                'https://www.youtube.com/embed/w8YH7eH8f_4',
                'https://docs.google.com/presentation/d/e/2PACX-1vQ-demo-arcade-sprint/embed?start=false&loop=false&delayms=3000',
                'https://github.com/godotengine/godot-demo-projects/tree/master/2d/platformer',
                1,
                1,
                1,
                1,
                'What gameplay metric will you use to show the project meets the module objective?',
                json.dumps(
                    [
                        {
                            'type': 'short',
                            'question': 'What is your target player goal and failure condition for this sprint?',
                        }
                    ]
                ),
                3,
                1,
                'Submit a playable prototype plus a short design note explaining controls, win state, and next iteration goals.',
                1,
                teacher_id,
            ),
        ]

        db.executemany(
            '''
            INSERT INTO module_templates (
                title, summary, objectives, lesson_type, content_url, slide_url, godot_template_url,
                activity_video, activity_slides, activity_quiz, activity_project,
                quiz_prompt, quiz_questions_json, quiz_max_attempts, quiz_allow_reassessment,
                project_brief, godot_enabled, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            module_templates,
        )

        course_id = db.execute(
            '''
            INSERT INTO course_offerings (teacher_id, title, description, focus_area)
            VALUES (?, ?, ?, ?)
            ''',
            (
                teacher_id,
                'Game Creation With Godot',
                'A starter course structure for hosting lessons, quick checks, and iterative game project submissions.',
                'Godot 4.7.2, gameplay systems, and project-based assessment',
            ),
        ).lastrowid

        template_rows = db.execute('SELECT id, title FROM module_templates ORDER BY id').fetchall()
        for position, template in enumerate(template_rows, start=1):
            db.execute(
                '''
                INSERT INTO course_modules (course_id, module_template_id, module_title, position, required)
                VALUES (?, ?, ?, ?, 1)
                ''',
                (course_id, template['id'], template['title'], position),
            )

        student_rows = db.execute("SELECT id FROM users WHERE role = 'student' ORDER BY id").fetchall()
        for student in student_rows:
            db.execute(
                'INSERT INTO enrollments (course_id, student_id) VALUES (?, ?)',
                (course_id, student['id']),
            )

        first_module_id = db.execute(
            'SELECT id FROM course_modules WHERE course_id = ? ORDER BY position LIMIT 1',
            (course_id,),
        ).fetchone()['id']
        first_student_id = student_rows[0]['id']

        db.execute(
            '''
            INSERT INTO project_submissions (
                course_module_id, student_id, submission_link, notes, status, score, feedback, graded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                first_module_id,
                first_student_id,
                'https://example.com/jordan-first-scene',
                'Prototype includes movement, camera follow, and a short design reflection.',
                'graded',
                92,
                'Strong start. Next step: tighten jump timing and add a clearer end goal.',
                datetime.utcnow().isoformat(timespec='seconds'),
            ),
        )

    db.commit()
    db.close()


def fetch_one(query, params=()):
    db = get_db()
    row = db.execute(query, params).fetchone()
    db.close()
    return row


def get_current_user():
    user_id = session.get('user_id')
    if not user_id:
        return None
    return fetch_one('SELECT * FROM users WHERE id = ?', (user_id,))


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not g.user:
            flash('Please sign in to continue.', 'warning')
            return redirect(url_for('sign_in'))
        return view(*args, **kwargs)

    return wrapped_view


def role_required(role):
    def decorator(view):
        @wraps(view)
        def wrapped_view(*args, **kwargs):
            if not g.user:
                flash('Please sign in to continue.', 'warning')
                return redirect(url_for('sign_in'))
            if g.user['role'] != role:
                abort(403)
            return view(*args, **kwargs)

        return wrapped_view

    return decorator


def get_course_for_teacher(course_id, teacher_id):
    return fetch_one(
        'SELECT * FROM course_offerings WHERE id = ? AND teacher_id = ?',
        (course_id, teacher_id),
    )


def get_course_for_student(course_id, student_id):
    return fetch_one(
        '''
        SELECT c.*
        FROM course_offerings c
        JOIN enrollments e ON e.course_id = c.id
        WHERE c.id = ? AND e.student_id = ?
        ''',
        (course_id, student_id),
    )


def parse_quiz_questions(raw_text):
    questions = []
    for line in raw_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parts = [part.strip() for part in stripped.split('|')]
        if not parts:
            continue
        question_type = parts[0].lower()
        if question_type == 'mcq' and len(parts) >= 7:
            answer = parts[6].upper()
            if answer in {'A', 'B', 'C', 'D'}:
                questions.append(
                    {
                        'type': 'mcq',
                        'question': parts[1],
                        'options': parts[2:6],
                        'answer': answer,
                    }
                )
        elif question_type in {'short', 'short_answer'} and len(parts) >= 2:
            questions.append({'type': 'short', 'question': parts[1]})
    return questions


def load_quiz_questions(quiz_questions_json):
    try:
        parsed = json.loads(quiz_questions_json or '[]')
        if isinstance(parsed, list):
            return parsed
    except json.JSONDecodeError:
        pass
    return []


@app.before_request
def load_user():
    g.user = get_current_user()


@app.context_processor
def inject_globals():
    return {
        'current_user': g.user,
        'godot_editor_url': GODOT_EDITOR_URL,
        'current_year': datetime.utcnow().year,
    }


@app.route('/')
def index():
    db = get_db()
    metrics = db.execute(
        '''
        SELECT
            (SELECT COUNT(*) FROM course_offerings) AS course_count,
            (SELECT COUNT(*) FROM module_templates) AS module_count,
            (SELECT COUNT(*) FROM users WHERE role = 'student') AS student_count,
            (SELECT COUNT(*) FROM project_submissions) AS submission_count
        '''
    ).fetchone()
    demo_courses = db.execute(
        '''
        SELECT c.id, c.title, c.description, c.focus_area, u.name AS teacher_name,
               COUNT(cm.id) AS module_count
        FROM course_offerings c
        JOIN users u ON u.id = c.teacher_id
        LEFT JOIN course_modules cm ON cm.course_id = c.id
        GROUP BY c.id
        ORDER BY c.created_at DESC
        '''
    ).fetchall()
    db.close()
    return render_template('index.html', metrics=metrics, demo_courses=demo_courses)


@app.route('/sign-in', methods=['GET', 'POST'])
def sign_in():
    db = get_db()
    users = db.execute('SELECT * FROM users ORDER BY role DESC, name').fetchall()
    db.close()

    if request.method == 'POST':
        user_id = request.form.get('user_id', type=int)
        user = fetch_one('SELECT * FROM users WHERE id = ?', (user_id,)) if user_id else None
        if not user:
            flash('Choose a demo account to continue.', 'warning')
            return render_template('sign_in.html', users=users)

        session.clear()
        session['user_id'] = user['id']
        flash(f"Signed in as {user['name']}.", 'success')
        return redirect(url_for('dashboard'))

    return render_template('sign_in.html', users=users)


@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    flash('You have been signed out.', 'success')
    return redirect(url_for('index'))


@app.route('/dashboard')
@login_required
def dashboard():
    if g.user['role'] == 'teacher':
        return redirect(url_for('teacher_dashboard'))
    return redirect(url_for('student_dashboard'))


@app.route('/teacher')
@role_required('teacher')
def teacher_dashboard():
    db = get_db()
    courses = db.execute(
        '''
        SELECT c.id, c.title, c.description, c.focus_area,
               COUNT(DISTINCT cm.id) AS module_count,
               COUNT(DISTINCT e.student_id) AS student_count,
               ROUND(AVG(ps.score), 1) AS average_score
        FROM course_offerings c
        LEFT JOIN course_modules cm ON cm.course_id = c.id
        LEFT JOIN enrollments e ON e.course_id = c.id
        LEFT JOIN project_submissions ps ON ps.course_module_id = cm.id
        WHERE c.teacher_id = ?
        GROUP BY c.id
        ORDER BY c.created_at DESC
        ''',
        (g.user['id'],),
    ).fetchall()
    templates = db.execute(
        '''
        SELECT mt.*, u.name AS author_name
        FROM module_templates mt
        LEFT JOIN users u ON u.id = mt.created_by
        ORDER BY mt.created_at DESC
        '''
    ).fetchall()
    submissions = db.execute(
        '''
        SELECT ps.*, s.name AS student_name, cm.module_title, c.title AS course_title
        FROM project_submissions ps
        JOIN users s ON s.id = ps.student_id
        JOIN course_modules cm ON cm.id = ps.course_module_id
        JOIN course_offerings c ON c.id = cm.course_id
        WHERE c.teacher_id = ?
        ORDER BY CASE ps.status WHEN 'submitted' THEN 0 WHEN 'in_review' THEN 1 WHEN 'revision_requested' THEN 2 ELSE 3 END,
                 ps.submitted_at DESC
        LIMIT 8
        ''',
        (g.user['id'],),
    ).fetchall()
    db.close()
    return render_template(
        'teacher_dashboard.html',
        courses=courses,
        templates=templates,
        submissions=submissions,
    )


@app.route('/teacher/courses/create', methods=['POST'])
@role_required('teacher')
def create_course():
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    focus_area = request.form.get('focus_area', '').strip()
    template_ids = [value for value in request.form.getlist('template_ids') if value.isdigit()]

    if not title or not description or not focus_area:
        flash('Course title, description, and focus area are required.', 'warning')
        return redirect(url_for('teacher_dashboard'))

    db = get_db()
    course_id = db.execute(
        '''
        INSERT INTO course_offerings (teacher_id, title, description, focus_area)
        VALUES (?, ?, ?, ?)
        ''',
        (g.user['id'], title, description, focus_area),
    ).lastrowid

    for position, template_id in enumerate(template_ids, start=1):
        template = db.execute(
            'SELECT id, title FROM module_templates WHERE id = ?',
            (int(template_id),),
        ).fetchone()
        if template:
            db.execute(
                '''
                INSERT INTO course_modules (course_id, module_template_id, module_title, position, required)
                VALUES (?, ?, ?, ?, 1)
                ''',
                (course_id, template['id'], template['title'], position),
            )

    db.commit()
    db.close()
    flash('Course created. Add or remove modules to tailor the sequence.', 'success')
    return redirect(url_for('teacher_course', course_id=course_id))


@app.route('/teacher/modules/create', methods=['POST'])
@role_required('teacher')
def create_module_template():
    title = request.form.get('title', '').strip()
    summary = request.form.get('summary', '').strip()
    objectives = request.form.get('objectives', '').strip()
    lesson_type = request.form.get('lesson_type', '').strip() or 'mixed'
    content_url = request.form.get('content_url', '').strip()
    slide_url = request.form.get('slide_url', '').strip()
    godot_template_url = request.form.get('godot_template_url', '').strip()
    activity_video = 1 if request.form.get('activity_video') == 'on' else 0
    activity_slides = 1 if request.form.get('activity_slides') == 'on' else 0
    activity_quiz = 1 if request.form.get('activity_quiz') == 'on' else 0
    activity_project = 1 if request.form.get('activity_project') == 'on' else 0
    quiz_prompt = request.form.get('quiz_prompt', '').strip()
    quiz_questions = parse_quiz_questions(request.form.get('quiz_questions', ''))
    quiz_max_attempts = request.form.get('quiz_max_attempts', type=int) or 1
    quiz_allow_reassessment = 1 if request.form.get('quiz_allow_reassessment') == 'on' else 0
    project_brief = request.form.get('project_brief', '').strip()
    godot_enabled = 1 if request.form.get('godot_enabled') == 'on' else 0

    if lesson_type not in {'video', 'slides', 'project', 'mixed'}:
        abort(400)

    if quiz_max_attempts < 1 or quiz_max_attempts > 10:
        flash('Quiz attempts must be between 1 and 10.', 'warning')
        return redirect(url_for('teacher_dashboard'))

    if not (activity_video or activity_slides or activity_quiz or activity_project):
        flash('Select at least one module activity.', 'warning')
        return redirect(url_for('teacher_dashboard'))

    if not title or not summary or not objectives:
        flash('Module title, summary, and objectives are required.', 'warning')
        return redirect(url_for('teacher_dashboard'))
    if activity_quiz and not quiz_prompt:
        flash('Quiz prompt is required when quiz activity is enabled.', 'warning')
        return redirect(url_for('teacher_dashboard'))
    if activity_project and not project_brief:
        flash('Project brief is required when project activity is enabled.', 'warning')
        return redirect(url_for('teacher_dashboard'))

    db = get_db()
    db.execute(
        '''
        INSERT INTO module_templates (
            title, summary, objectives, lesson_type, content_url, slide_url, godot_template_url,
            activity_video, activity_slides, activity_quiz, activity_project,
            quiz_prompt, quiz_questions_json, quiz_max_attempts, quiz_allow_reassessment,
            project_brief, godot_enabled, created_by
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            title,
            summary,
            objectives,
            lesson_type,
            content_url,
            slide_url,
            godot_template_url,
            activity_video,
            activity_slides,
            activity_quiz,
            activity_project,
            quiz_prompt,
            json.dumps(quiz_questions),
            quiz_max_attempts,
            quiz_allow_reassessment,
            project_brief,
            godot_enabled,
            g.user['id'],
        ),
    )
    db.commit()
    db.close()
    flash('Module template saved to the teaching library.', 'success')
    return redirect(url_for('teacher_dashboard'))


@app.route('/teacher/course/<int:course_id>')
@role_required('teacher')
def teacher_course(course_id):
    course = get_course_for_teacher(course_id, g.user['id'])
    if not course:
        abort(404)

    db = get_db()
    modules = db.execute(
        '''
        SELECT cm.*, mt.summary, mt.objectives, mt.lesson_type, mt.godot_enabled, mt.content_url, mt.slide_url,
               mt.activity_video, mt.activity_slides, mt.activity_quiz, mt.activity_project,
               mt.quiz_max_attempts, mt.quiz_allow_reassessment
        FROM course_modules cm
        JOIN module_templates mt ON mt.id = cm.module_template_id
        WHERE cm.course_id = ?
        ORDER BY cm.position, cm.id
        ''',
        (course_id,),
    ).fetchall()
    templates = db.execute(
        'SELECT * FROM module_templates ORDER BY created_at DESC'
    ).fetchall()
    submissions = db.execute(
        '''
        SELECT ps.*, u.name AS student_name, cm.module_title
        FROM project_submissions ps
        JOIN users u ON u.id = ps.student_id
        JOIN course_modules cm ON cm.id = ps.course_module_id
        WHERE cm.course_id = ?
        ORDER BY ps.submitted_at DESC
        ''',
        (course_id,),
    ).fetchall()
    db.close()
    return render_template(
        'teacher_course.html',
        course=course,
        modules=modules,
        templates=templates,
        submissions=submissions,
    )


@app.route('/teacher/course/<int:course_id>/modules/add', methods=['POST'])
@role_required('teacher')
def add_module_to_course(course_id):
    course = get_course_for_teacher(course_id, g.user['id'])
    if not course:
        abort(404)

    template_id = request.form.get('module_template_id', type=int)
    due_date = request.form.get('due_date', '').strip() or None
    if not template_id:
        flash('Choose a module template to add.', 'warning')
        return redirect(url_for('teacher_course', course_id=course_id))

    db = get_db()
    template = db.execute('SELECT id, title FROM module_templates WHERE id = ?', (template_id,)).fetchone()
    if not template:
        db.close()
        abort(404)

    next_position = db.execute(
        'SELECT COALESCE(MAX(position), 0) + 1 AS next_position FROM course_modules WHERE course_id = ?',
        (course_id,),
    ).fetchone()['next_position']

    db.execute(
        '''
        INSERT INTO course_modules (course_id, module_template_id, module_title, position, required, due_date)
        VALUES (?, ?, ?, ?, ?, ?)
        ''',
        (
            course_id,
            template['id'],
            template['title'],
            next_position,
            1 if request.form.get('required') == 'on' else 0,
            due_date,
        ),
    )
    db.commit()
    db.close()
    flash('Module added to the course.', 'success')
    return redirect(url_for('teacher_course', course_id=course_id))


@app.route('/teacher/course/<int:course_id>/modules/<int:course_module_id>/remove', methods=['POST'])
@role_required('teacher')
def remove_module_from_course(course_id, course_module_id):
    course = get_course_for_teacher(course_id, g.user['id'])
    if not course:
        abort(404)

    db = get_db()
    db.execute(
        'DELETE FROM course_modules WHERE id = ? AND course_id = ?',
        (course_module_id, course_id),
    )
    remaining_modules = db.execute(
        'SELECT id FROM course_modules WHERE course_id = ? ORDER BY position, id',
        (course_id,),
    ).fetchall()
    for position, module in enumerate(remaining_modules, start=1):
        db.execute('UPDATE course_modules SET position = ? WHERE id = ?', (position, module['id']))
    db.commit()
    db.close()
    flash('Module removed from the course.', 'success')
    return redirect(url_for('teacher_course', course_id=course_id))


@app.route('/teacher/submissions/<int:submission_id>/grade', methods=['POST'])
@role_required('teacher')
def grade_submission(submission_id):
    status = request.form.get('status', '').strip()
    feedback = request.form.get('feedback', '').strip()
    grading_mode = request.form.get('grading_mode', '').strip() or 'points'
    rubric_notes = request.form.get('rubric_notes', '').strip()
    raw_score = request.form.get('score', '').strip()
    if status not in {'submitted', 'in_review', 'graded', 'revision_requested'}:
        abort(400)
    if grading_mode not in {'points', 'rubric'}:
        abort(400)

    if raw_score and not raw_score.isdigit():
        abort(400)

    score_value = int(raw_score) if raw_score else None
    if score_value is not None and not 0 <= score_value <= 100:
        abort(400)

    db = get_db()
    submission = db.execute(
        '''
        SELECT ps.id, c.id AS course_id
        FROM project_submissions ps
        JOIN course_modules cm ON cm.id = ps.course_module_id
        JOIN course_offerings c ON c.id = cm.course_id
        WHERE ps.id = ? AND c.teacher_id = ?
        ''',
        (submission_id, g.user['id']),
    ).fetchone()
    if not submission:
        db.close()
        abort(404)

    db.execute(
        '''
        UPDATE project_submissions
        SET status = ?, score = ?, grading_mode = ?, rubric_notes = ?, feedback = ?, graded_at = ?
        WHERE id = ?
        ''',
        (
            status,
            score_value,
            grading_mode,
            rubric_notes,
            feedback,
            datetime.utcnow().isoformat(timespec='seconds') if status in {'graded', 'revision_requested'} else None,
            submission_id,
        ),
    )
    db.commit()
    db.close()
    flash('Submission updated.', 'success')
    return redirect(url_for('teacher_course', course_id=submission['course_id']))


@app.route('/teacher/course/<int:course_id>/modules/<int:course_module_id>/due-date', methods=['POST'])
@role_required('teacher')
def update_module_due_date(course_id, course_module_id):
    course = get_course_for_teacher(course_id, g.user['id'])
    if not course:
        abort(404)

    due_date = request.form.get('due_date', '').strip() or None
    db = get_db()
    db.execute(
        'UPDATE course_modules SET due_date = ? WHERE id = ? AND course_id = ?',
        (due_date, course_module_id, course_id),
    )
    db.commit()
    db.close()
    flash('Module due date updated.', 'success')
    return redirect(url_for('teacher_course', course_id=course_id))


@app.route('/teacher/course/<int:course_id>/gradebook')
@role_required('teacher')
def teacher_gradebook(course_id):
    course = get_course_for_teacher(course_id, g.user['id'])
    if not course:
        abort(404)

    db = get_db()
    modules = db.execute(
        '''
        SELECT cm.id, cm.module_title, cm.position, cm.due_date
        FROM course_modules cm
        WHERE cm.course_id = ?
        ORDER BY cm.position, cm.id
        ''',
        (course_id,),
    ).fetchall()
    students = db.execute(
        '''
        SELECT u.id, u.name, u.email
        FROM enrollments e
        JOIN users u ON u.id = e.student_id
        WHERE e.course_id = ?
        ORDER BY u.name
        ''',
        (course_id,),
    ).fetchall()
    project_rows = db.execute(
        '''
        SELECT ps.course_module_id, ps.student_id, ps.status, ps.score
        FROM project_submissions ps
        JOIN course_modules cm ON cm.id = ps.course_module_id
        WHERE cm.course_id = ?
        ''',
        (course_id,),
    ).fetchall()
    quiz_rows = db.execute(
        '''
        SELECT qa.course_module_id, qa.student_id, qa.score
        FROM quiz_attempts qa
        JOIN (
            SELECT course_module_id, student_id, MAX(attempt_number) AS latest_attempt
            FROM quiz_attempts
            GROUP BY course_module_id, student_id
        ) latest ON latest.course_module_id = qa.course_module_id
               AND latest.student_id = qa.student_id
               AND latest.latest_attempt = qa.attempt_number
        JOIN course_modules cm ON cm.id = qa.course_module_id
        WHERE cm.course_id = ?
        ''',
        (course_id,),
    ).fetchall()
    db.close()

    project_lookup = {(row['student_id'], row['course_module_id']): row for row in project_rows}
    quiz_lookup = {(row['student_id'], row['course_module_id']): row for row in quiz_rows}

    grade_rows = []
    for student in students:
        assignments = []
        for module in modules:
            project = project_lookup.get((student['id'], module['id']))
            quiz = quiz_lookup.get((student['id'], module['id']))
            assignments.append(
                {
                    'module_id': module['id'],
                    'project_score': project['score'] if project else None,
                    'project_status': project['status'] if project else None,
                    'quiz_score': quiz['score'] if quiz else None,
                }
            )
        grade_rows.append({'student': student, 'assignments': assignments})

    return render_template('teacher_gradebook.html', course=course, modules=modules, grade_rows=grade_rows)


@app.route('/course/<int:course_id>/module/<int:course_module_id>/quiz-submit', methods=['POST'])
@role_required('student')
def submit_quiz(course_id, course_module_id):
    course = get_course_for_student(course_id, g.user['id'])
    if not course:
        abort(404)

    db = get_db()
    module = db.execute(
        '''
        SELECT cm.id, mt.quiz_questions_json, mt.activity_quiz, mt.quiz_max_attempts, mt.quiz_allow_reassessment
        FROM course_modules cm
        JOIN module_templates mt ON mt.id = cm.module_template_id
        WHERE cm.id = ? AND cm.course_id = ?
        ''',
        (course_module_id, course_id),
    ).fetchone()
    if not module or not module['activity_quiz']:
        db.close()
        abort(404)

    questions = load_quiz_questions(module['quiz_questions_json'])
    if not questions:
        db.close()
        flash('Quiz questions are not configured for this module yet.', 'warning')
        return redirect(url_for('module_detail', course_id=course_id, course_module_id=course_module_id))

    attempt_count = db.execute(
        'SELECT COUNT(*) AS count FROM quiz_attempts WHERE course_module_id = ? AND student_id = ?',
        (course_module_id, g.user['id']),
    ).fetchone()['count']
    max_attempts = module['quiz_max_attempts'] + (1 if module['quiz_allow_reassessment'] else 0)
    if attempt_count >= max_attempts:
        db.close()
        flash('No quiz attempts remaining for this module.', 'warning')
        return redirect(url_for('module_detail', course_id=course_id, course_module_id=course_module_id))

    responses = {}
    mcq_total = 0
    mcq_correct = 0
    for index, question in enumerate(questions):
        answer = request.form.get(f'quiz_q_{index}', '').strip()
        responses[str(index)] = answer
        if question.get('type') == 'mcq':
            mcq_total += 1
            if answer.upper() == question.get('answer'):
                mcq_correct += 1
    score = round((mcq_correct / mcq_total) * 100) if mcq_total else None

    db.execute(
        '''
        INSERT INTO quiz_attempts (course_module_id, student_id, attempt_number, responses_json, score, feedback, graded_at)
        VALUES (?, ?, ?, ?, ?, NULL, NULL)
        ''',
        (
            course_module_id,
            g.user['id'],
            attempt_count + 1,
            json.dumps(responses),
            score,
        ),
    )
    db.commit()
    db.close()
    flash('Quiz attempt submitted.', 'success')
    return redirect(url_for('module_detail', course_id=course_id, course_module_id=course_module_id))


@app.route('/teacher/quiz-attempts/<int:attempt_id>/grade', methods=['POST'])
@role_required('teacher')
def grade_quiz_attempt(attempt_id):
    raw_score = request.form.get('score', '').strip()
    feedback = request.form.get('feedback', '').strip()
    if raw_score and not raw_score.isdigit():
        abort(400)
    score_value = int(raw_score) if raw_score else None
    if score_value is not None and not 0 <= score_value <= 100:
        abort(400)

    db = get_db()
    attempt = db.execute(
        '''
        SELECT qa.id, qa.course_module_id, cm.course_id
        FROM quiz_attempts qa
        JOIN course_modules cm ON cm.id = qa.course_module_id
        JOIN course_offerings c ON c.id = cm.course_id
        WHERE qa.id = ? AND c.teacher_id = ?
        ''',
        (attempt_id, g.user['id']),
    ).fetchone()
    if not attempt:
        db.close()
        abort(404)

    db.execute(
        'UPDATE quiz_attempts SET score = ?, feedback = ?, graded_at = ? WHERE id = ?',
        (score_value, feedback, datetime.utcnow().isoformat(timespec='seconds'), attempt_id),
    )
    db.commit()
    db.close()
    flash('Quiz attempt feedback saved.', 'success')
    return redirect(url_for('module_detail', course_id=attempt['course_id'], course_module_id=attempt['course_module_id']))


@app.route('/student')
@role_required('student')
def student_dashboard():
    db = get_db()
    course_cards = db.execute(
        '''
        SELECT c.id, c.title, c.description, c.focus_area, u.name AS teacher_name,
               COUNT(DISTINCT cm.id) AS module_count,
               COUNT(DISTINCT ps.id) AS submitted_count,
               COUNT(DISTINCT CASE WHEN ps.status = 'graded' THEN ps.id END) AS graded_count,
               ROUND(AVG(ps.score), 1) AS average_score
        FROM enrollments e
        JOIN course_offerings c ON c.id = e.course_id
        JOIN users u ON u.id = c.teacher_id
        LEFT JOIN course_modules cm ON cm.course_id = c.id
        LEFT JOIN project_submissions ps ON ps.course_module_id = cm.id AND ps.student_id = e.student_id
        WHERE e.student_id = ?
        GROUP BY c.id
        ORDER BY c.created_at DESC
        ''',
        (g.user['id'],),
    ).fetchall()
    upcoming_modules = db.execute(
        '''
        SELECT c.id AS course_id, c.title AS course_title, cm.id AS course_module_id, cm.module_title,
               mt.summary, mt.objectives, mt.godot_enabled, cm.due_date, ps.status, ps.score
        FROM enrollments e
        JOIN course_offerings c ON c.id = e.course_id
        JOIN course_modules cm ON cm.course_id = c.id
        JOIN module_templates mt ON mt.id = cm.module_template_id
        LEFT JOIN project_submissions ps ON ps.course_module_id = cm.id AND ps.student_id = e.student_id
        WHERE e.student_id = ?
        ORDER BY COALESCE(cm.due_date, '9999-12-31'), c.title, cm.position
        ''',
        (g.user['id'],),
    ).fetchall()
    db.close()
    return render_template(
        'student_dashboard.html',
        course_cards=course_cards,
        upcoming_modules=upcoming_modules,
    )


@app.route('/course/<int:course_id>/module/<int:course_module_id>')
@login_required
def module_detail(course_id, course_module_id):
    if g.user['role'] == 'teacher':
        course = get_course_for_teacher(course_id, g.user['id'])
    else:
        course = get_course_for_student(course_id, g.user['id'])
    if not course:
        abort(404)

    db = get_db()
    module = db.execute(
        '''
        SELECT cm.*, mt.summary, mt.objectives, mt.lesson_type, mt.content_url, mt.slide_url,
               mt.godot_template_url, mt.activity_video, mt.activity_slides, mt.activity_quiz, mt.activity_project,
               mt.quiz_prompt, mt.quiz_questions_json, mt.quiz_max_attempts, mt.quiz_allow_reassessment,
               mt.project_brief, mt.godot_enabled
        FROM course_modules cm
        JOIN module_templates mt ON mt.id = cm.module_template_id
        WHERE cm.id = ? AND cm.course_id = ?
        ''',
        (course_module_id, course_id),
    ).fetchone()
    if not module:
        db.close()
        abort(404)

    student_submission = None
    submissions = []
    quiz_questions = load_quiz_questions(module['quiz_questions_json'])
    student_quiz_attempts = []
    teacher_quiz_attempts = []
    quiz_attempts_remaining = module['quiz_max_attempts'] + (1 if module['quiz_allow_reassessment'] else 0)
    if g.user['role'] == 'student':
        student_submission = db.execute(
            '''
            SELECT * FROM project_submissions
            WHERE course_module_id = ? AND student_id = ?
            ''',
            (course_module_id, g.user['id']),
        ).fetchone()
        student_quiz_attempts = db.execute(
            '''
            SELECT *
            FROM quiz_attempts
            WHERE course_module_id = ? AND student_id = ?
            ORDER BY attempt_number DESC
            ''',
            (course_module_id, g.user['id']),
        ).fetchall()
        quiz_attempts_remaining = max(0, quiz_attempts_remaining - len(student_quiz_attempts))
    else:
        submissions = db.execute(
            '''
            SELECT ps.*, u.name AS student_name
            FROM project_submissions ps
            JOIN users u ON u.id = ps.student_id
            WHERE ps.course_module_id = ?
            ORDER BY ps.submitted_at DESC
            ''',
            (course_module_id,),
        ).fetchall()
        teacher_quiz_attempts = db.execute(
            '''
            SELECT qa.*, u.name AS student_name
            FROM quiz_attempts qa
            JOIN users u ON u.id = qa.student_id
            WHERE qa.course_module_id = ?
            ORDER BY qa.created_at DESC
            ''',
            (course_module_id,),
        ).fetchall()
        teacher_quiz_attempts = [
            {
                **dict(attempt),
                'responses': json.loads(attempt['responses_json'] or '{}'),
            }
            for attempt in teacher_quiz_attempts
        ]

    db.close()
    return render_template(
        'module_detail.html',
        course=course,
        module=module,
        quiz_questions=quiz_questions,
        student_submission=student_submission,
        student_quiz_attempts=student_quiz_attempts,
        quiz_attempts_remaining=quiz_attempts_remaining,
        submissions=submissions,
        teacher_quiz_attempts=teacher_quiz_attempts,
    )


@app.route('/course/<int:course_id>/module/<int:course_module_id>/submit', methods=['POST'])
@role_required('student')
def submit_project(course_id, course_module_id):
    course = get_course_for_student(course_id, g.user['id'])
    if not course:
        abort(404)

    submission_link = request.form.get('submission_link', '').strip()
    notes = request.form.get('notes', '').strip()
    if not submission_link:
        flash('Add a project link or repository URL before submitting.', 'warning')
        return redirect(url_for('module_detail', course_id=course_id, course_module_id=course_module_id))

    db = get_db()
    module = db.execute(
        'SELECT id FROM course_modules WHERE id = ? AND course_id = ?',
        (course_module_id, course_id),
    ).fetchone()
    if not module:
        db.close()
        abort(404)

    db.execute(
        '''
        INSERT INTO project_submissions (course_module_id, student_id, submission_link, notes, status, score, feedback, submitted_at, graded_at)
        VALUES (?, ?, ?, ?, 'submitted', NULL, NULL, ?, NULL)
        ON CONFLICT(course_module_id, student_id)
        DO UPDATE SET submission_link = excluded.submission_link,
                      notes = excluded.notes,
                      status = 'submitted',
                      score = NULL,
                      feedback = NULL,
                      submitted_at = excluded.submitted_at,
                      graded_at = NULL
        ''',
        (course_module_id, g.user['id'], submission_link, notes, datetime.utcnow().isoformat(timespec='seconds')),
    )
    db.commit()
    db.close()
    flash('Project submitted for teacher review.', 'success')
    return redirect(url_for('module_detail', course_id=course_id, course_module_id=course_module_id))


init_db()


if __name__ == '__main__':
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(debug=debug_mode, host='0.0.0.0', port=5000)
