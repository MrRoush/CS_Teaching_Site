import os
import sqlite3
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
            lesson_type TEXT NOT NULL CHECK(lesson_type IN ('video', 'slides', 'project', 'mixed')),
            content_url TEXT,
            slide_url TEXT,
            quiz_prompt TEXT NOT NULL,
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
            feedback TEXT,
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            graded_at TIMESTAMP,
            FOREIGN KEY (course_module_id) REFERENCES course_modules(id) ON DELETE CASCADE,
            FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE(course_module_id, student_id)
        );
        '''
    )

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
                'video',
                'https://www.youtube.com/embed/nAh_Kx5Zh5Q',
                'https://docs.google.com/presentation/d/e/2PACX-1vQ-demo-godot-intro/embed?start=false&loop=false&delayms=3000',
                'What editor panels should students keep visible while building their first scene, and why?',
                'Build a starter scene and share either a hosted build, repository link, or exported project archive.',
                1,
                teacher_id,
            ),
            (
                'Systems Thinking With Game Loops',
                'Connect event loops, state, and debugging habits to a classroom game design workflow.',
                'slides',
                'https://www.youtube.com/embed/QKgTZWbwD1U',
                'https://docs.google.com/presentation/d/e/2PACX-1vQ-demo-game-loops/embed?start=false&loop=false&delayms=3000',
                'Describe how a game loop updates input, simulation, and rendering during each frame.',
                'Create a short reflection and pseudocode for the loop you will use in your project.',
                0,
                teacher_id,
            ),
            (
                'Arcade Prototype Sprint',
                'Guide students through building and submitting a small Godot arcade prototype for feedback.',
                'mixed',
                'https://www.youtube.com/embed/w8YH7eH8f_4',
                'https://docs.google.com/presentation/d/e/2PACX-1vQ-demo-arcade-sprint/embed?start=false&loop=false&delayms=3000',
                'What gameplay metric will you use to show the project meets the module objective?',
                'Submit a playable prototype plus a short design note explaining controls, win state, and next iteration goals.',
                1,
                teacher_id,
            ),
        ]

        db.executemany(
            '''
            INSERT INTO module_templates (
                title, summary, lesson_type, content_url, slide_url, quiz_prompt, project_brief, godot_enabled, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
    lesson_type = request.form.get('lesson_type', '').strip() or 'mixed'
    content_url = request.form.get('content_url', '').strip()
    slide_url = request.form.get('slide_url', '').strip()
    quiz_prompt = request.form.get('quiz_prompt', '').strip()
    project_brief = request.form.get('project_brief', '').strip()
    godot_enabled = 1 if request.form.get('godot_enabled') == 'on' else 0

    if lesson_type not in {'video', 'slides', 'project', 'mixed'}:
        abort(400)

    if not title or not summary or not quiz_prompt or not project_brief:
        flash('Module title, summary, quiz prompt, and project brief are required.', 'warning')
        return redirect(url_for('teacher_dashboard'))

    db = get_db()
    db.execute(
        '''
        INSERT INTO module_templates (
            title, summary, lesson_type, content_url, slide_url, quiz_prompt, project_brief, godot_enabled, created_by
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (title, summary, lesson_type, content_url, slide_url, quiz_prompt, project_brief, godot_enabled, g.user['id']),
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
        SELECT cm.*, mt.summary, mt.lesson_type, mt.godot_enabled, mt.content_url, mt.slide_url
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
        INSERT INTO course_modules (course_id, module_template_id, module_title, position, required)
        VALUES (?, ?, ?, ?, ?)
        ''',
        (course_id, template['id'], template['title'], next_position, 1 if request.form.get('required') == 'on' else 0),
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
    raw_score = request.form.get('score', '').strip()
    if status not in {'submitted', 'in_review', 'graded', 'revision_requested'}:
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
        SET status = ?, score = ?, feedback = ?, graded_at = ?
        WHERE id = ?
        ''',
        (
            status,
            score_value,
            feedback,
            datetime.utcnow().isoformat(timespec='seconds') if status in {'graded', 'revision_requested'} else None,
            submission_id,
        ),
    )
    db.commit()
    db.close()
    flash('Submission updated.', 'success')
    return redirect(url_for('teacher_course', course_id=submission['course_id']))


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
               mt.summary, mt.godot_enabled, ps.status, ps.score
        FROM enrollments e
        JOIN course_offerings c ON c.id = e.course_id
        JOIN course_modules cm ON cm.course_id = c.id
        JOIN module_templates mt ON mt.id = cm.module_template_id
        LEFT JOIN project_submissions ps ON ps.course_module_id = cm.id AND ps.student_id = e.student_id
        WHERE e.student_id = ?
        ORDER BY c.title, cm.position
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
        SELECT cm.*, mt.summary, mt.lesson_type, mt.content_url, mt.slide_url,
               mt.quiz_prompt, mt.project_brief, mt.godot_enabled
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
    if g.user['role'] == 'student':
        student_submission = db.execute(
            '''
            SELECT * FROM project_submissions
            WHERE course_module_id = ? AND student_id = ?
            ''',
            (course_module_id, g.user['id']),
        ).fetchone()
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

    db.close()
    return render_template(
        'module_detail.html',
        course=course,
        module=module,
        student_submission=student_submission,
        submissions=submissions,
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
