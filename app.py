import os
import sqlite3
import json
from datetime import datetime
from functools import wraps

from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, 'cs_teaching.db')
GODOT_EDITOR_URL = 'https://editor.godotengine.org/releases/4.7.2.stable/godot.editor.html'
ACTIVITY_TYPE_LABELS = {
    'video': 'Video Activity',
    'slides': 'Slides Activity',
    'text': 'Text Activity',
    'quiz': 'Quiz Activity',
    'project': 'Project Activity',
}
QUIZ_ANSWER_LETTERS = ('A', 'B', 'C', 'D')

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
            quiz_unlimited_attempts BOOLEAN DEFAULT 0,
            quiz_allow_reassessment BOOLEAN DEFAULT 0,
            project_brief TEXT NOT NULL,
            godot_enabled BOOLEAN DEFAULT 0,
            is_reusable BOOLEAN DEFAULT 1,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (created_by) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS module_lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            module_template_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            overview TEXT NOT NULL DEFAULT '',
            position INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (module_template_id) REFERENCES module_templates(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS module_lesson_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lesson_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            item_type TEXT NOT NULL CHECK(item_type IN ('video', 'resource', 'slides', 'quiz', 'project')),
            description TEXT NOT NULL DEFAULT '',
            content_text TEXT NOT NULL DEFAULT '',
            resource_url TEXT,
            points_possible INTEGER,
            quiz_prompt TEXT NOT NULL DEFAULT '',
            quiz_questions_json TEXT NOT NULL DEFAULT '[]',
            quiz_max_attempts INTEGER NOT NULL DEFAULT 1,
            quiz_unlimited_attempts BOOLEAN DEFAULT 0,
            quiz_allow_reassessment BOOLEAN DEFAULT 0,
            project_brief TEXT NOT NULL DEFAULT '',
            godot_enabled BOOLEAN DEFAULT 0,
            godot_template_url TEXT,
            position INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (lesson_id) REFERENCES module_lessons(id) ON DELETE CASCADE
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
    ensure_column('module_templates', 'quiz_unlimited_attempts', 'BOOLEAN DEFAULT 0')
    ensure_column('module_templates', 'quiz_allow_reassessment', 'BOOLEAN DEFAULT 0')
    ensure_column('module_templates', 'is_reusable', 'BOOLEAN DEFAULT 1')
    ensure_column('module_lesson_items', 'content_text', "TEXT NOT NULL DEFAULT ''")
    ensure_column('module_lesson_items', 'quiz_unlimited_attempts', 'BOOLEAN DEFAULT 0')
    ensure_column('course_modules', 'due_date', 'TEXT')
    ensure_column('project_submissions', 'grading_mode', "TEXT NOT NULL DEFAULT 'points'")
    ensure_column('project_submissions', 'rubric_notes', 'TEXT')

    def backfill_module_outline():
        templates_without_outline = db.execute(
            '''
            SELECT mt.*
            FROM module_templates mt
            LEFT JOIN module_lessons ml ON ml.module_template_id = mt.id
            GROUP BY mt.id
            HAVING COUNT(ml.id) = 0
            '''
        ).fetchall()

        for template in templates_without_outline:
            lesson_id = db.execute(
                '''
                INSERT INTO module_lessons (module_template_id, title, overview, position)
                VALUES (?, ?, ?, 1)
                ''',
                (template['id'], 'Lesson 1', template['summary']),
            ).lastrowid

            lesson_items = []
            if template['activity_video']:
                if template['content_url']:
                    lesson_items.append(
                        (
                            lesson_id,
                            'Video lesson',
                            'video',
                            template['summary'],
                            '',
                            template['content_url'],
                            None,
                            '',
                            '[]',
                            1,
                            0,
                            0,
                            '',
                            0,
                            '',
                            len(lesson_items) + 1,
                        )
                    )
                else:
                    lesson_items.append(
                        (
                            lesson_id,
                            'Written resource',
                            'resource',
                            template['summary'],
                            '',
                            '',
                            None,
                            '',
                            '[]',
                            1,
                            0,
                            0,
                            '',
                            0,
                            '',
                            len(lesson_items) + 1,
                        )
                    )
            if template['activity_slides']:
                lesson_items.append(
                    (
                        lesson_id,
                        'Slides / presentation',
                        'slides',
                        'Use this slide deck or presentation while teaching the lesson.',
                        '',
                        template['slide_url'],
                        None,
                        '',
                        '[]',
                        1,
                        0,
                        0,
                        '',
                        0,
                        '',
                        len(lesson_items) + 1,
                    )
                )
            if template['activity_quiz']:
                lesson_items.append(
                    (
                        lesson_id,
                        'Quiz: Check for Understanding',
                        'quiz',
                        template['quiz_prompt'],
                        '',
                        '',
                        100,
                        template['quiz_prompt'],
                        template['quiz_questions_json'] or '[]',
                        template['quiz_max_attempts'],
                        template['quiz_unlimited_attempts'],
                        template['quiz_allow_reassessment'],
                        '',
                        0,
                        '',
                        len(lesson_items) + 1,
                    )
                )
            if template['activity_project']:
                lesson_items.append(
                    (
                        lesson_id,
                        'Godot project' if template['godot_enabled'] else 'Project assignment',
                        'project',
                        template['project_brief'],
                        '',
                        template['godot_template_url'],
                        100,
                        '',
                        '[]',
                        1,
                        0,
                        0,
                        template['project_brief'],
                        template['godot_enabled'],
                        template['godot_template_url'],
                        len(lesson_items) + 1,
                    )
                )

            if lesson_items:
                db.executemany(
                    '''
                    INSERT INTO module_lesson_items (
                        lesson_id, title, item_type, description, content_text, resource_url, points_possible,
                        quiz_prompt, quiz_questions_json, quiz_max_attempts, quiz_unlimited_attempts, quiz_allow_reassessment,
                        project_brief, godot_enabled, godot_template_url, position
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''',
                    lesson_items,
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
                0,
                1,
                'Build a starter scene and share either a hosted build, repository link, or exported project archive.',
                1,
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
                0,
                'Create a short reflection and pseudocode for the loop you will use in your project.',
                0,
                1,
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
                0,
                1,
                'Submit a playable prototype plus a short design note explaining controls, win state, and next iteration goals.',
                1,
                1,
                teacher_id,
            ),
        ]

        db.executemany(
            '''
            INSERT INTO module_templates (
                title, summary, objectives, lesson_type, content_url, slide_url, godot_template_url,
                activity_video, activity_slides, activity_quiz, activity_project,
                quiz_prompt, quiz_questions_json, quiz_max_attempts, quiz_unlimited_attempts, quiz_allow_reassessment,
                project_brief, godot_enabled, is_reusable, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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

    backfill_module_outline()
    ensure_private_course_module_templates(db)
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


def to_storage_activity_type(activity_type):
    return 'resource' if activity_type == 'text' else activity_type


def to_presented_activity_type(item_type):
    return 'text' if item_type == 'resource' else item_type


def get_activity_type_label(item_type):
    return ACTIVITY_TYPE_LABELS.get(to_presented_activity_type(item_type), item_type.replace('_', ' ').title())


def collect_quiz_questions(form_data):
    if hasattr(form_data, 'get'):
        raw_question_count = form_data.get('question_count', type=int) if 'question_count' in form_data else None
    else:
        raw_question_count = form_data.get('question_count', 1)
    question_count = max(1, min(raw_question_count or 1, 10))
    questions = []
    errors = {}
    for index in range(question_count):
        prompt = form_data.get(f'question_{index}_prompt', '').strip()
        options = [form_data.get(f'question_{index}_option_{letter}', '').strip() for letter in QUIZ_ANSWER_LETTERS]
        answer = form_data.get(f'question_{index}_answer', '').strip().upper()
        if not prompt:
            errors[f'question_{index}_prompt'] = 'Question prompt is required.'
        if any(not option for option in options):
            errors[f'question_{index}_options'] = 'All answer choices are required.'
        if answer not in QUIZ_ANSWER_LETTERS:
            errors[f'question_{index}_answer'] = 'Choose the correct answer.'
        questions.append(
            {
                'type': 'mcq',
                'question': prompt,
                'options': options,
                'answer': answer,
            }
        )
    return questions, errors, question_count


def get_default_activity_form(activity_type='video'):
    return {
        'activity_type': activity_type,
        'title': '',
        'description': '',
        'resource_url': '',
        'content_text': '',
        'quiz_prompt': '',
        'question_count': 1,
        'quiz_max_attempts': 1,
        'quiz_unlimited_attempts': False,
        'quiz_allow_reassessment': False,
        'questions': [
            {
                'prompt': '',
                'options': {letter: '' for letter in QUIZ_ANSWER_LETTERS},
                'answer': 'A',
            }
        ],
        'project_brief': '',
        'godot_enabled': False,
        'godot_template_url': '',
    }


def get_activity_form_from_item(item):
    activity_type = to_presented_activity_type(item['item_type'])
    questions = load_quiz_questions(item['quiz_questions_json']) if activity_type == 'quiz' else []
    form = {
        'activity_type': activity_type,
        'title': item['title'],
        'description': item['description'],
        'resource_url': item['resource_url'] or '',
        'content_text': item['content_text'] or '',
        'quiz_prompt': item['quiz_prompt'] or '',
        'question_count': len(questions) or 1,
        'quiz_max_attempts': item['quiz_max_attempts'] or 1,
        'quiz_unlimited_attempts': bool(item['quiz_unlimited_attempts']),
        'quiz_allow_reassessment': bool(item['quiz_allow_reassessment']),
        'questions': [],
        'project_brief': item['project_brief'] or '',
        'godot_enabled': bool(item['godot_enabled']),
        'godot_template_url': item['godot_template_url'] or '',
    }
    if questions:
        for question in questions:
            options = question.get('options') or ['', '', '', '']
            while len(options) < 4:
                options.append('')
            form['questions'].append(
                {
                    'prompt': question.get('question', ''),
                    'options': {letter: options[idx] for idx, letter in enumerate(QUIZ_ANSWER_LETTERS)},
                    'answer': (question.get('answer') or 'A').upper(),
                }
            )
    else:
        form['questions'].append(
            {
                'prompt': '',
                'options': {letter: '' for letter in QUIZ_ANSWER_LETTERS},
                'answer': 'A',
            }
        )
    return form


def resize_activity_questions(form_data, question_count):
    question_count = max(1, min(question_count, 10))
    questions = list(form_data.get('questions') or [])
    while len(questions) < question_count:
        questions.append(
            {
                'prompt': '',
                'options': {letter: '' for letter in QUIZ_ANSWER_LETTERS},
                'answer': 'A',
            }
        )
    form_data['questions'] = questions[:question_count]
    form_data['question_count'] = question_count
    return form_data


def validate_activity_form(form):
    activity_type = form.get('activity_type', '').strip().lower()
    title = form.get('title', '').strip()
    description = form.get('description', '').strip()
    resource_url = form.get('resource_url', '').strip()
    content_text = form.get('content_text', '').strip()
    quiz_prompt = form.get('quiz_prompt', '').strip()
    project_brief = form.get('project_brief', '').strip()
    godot_template_url = form.get('godot_template_url', '').strip()
    question_count = form.get('question_count', type=int) or 1
    quiz_max_attempts = form.get('quiz_max_attempts', type=int) or 1
    quiz_unlimited_attempts = form.get('quiz_unlimited_attempts') == 'on'
    quiz_allow_reassessment = form.get('quiz_allow_reassessment') == 'on'
    godot_enabled = form.get('godot_enabled') == 'on'

    form_data = get_default_activity_form(activity_type if activity_type in ACTIVITY_TYPE_LABELS else 'video')
    form_data.update(
        {
            'title': title,
            'description': description,
            'resource_url': resource_url,
            'content_text': content_text,
            'quiz_prompt': quiz_prompt,
            'question_count': max(1, min(question_count, 10)),
            'quiz_max_attempts': quiz_max_attempts,
            'quiz_unlimited_attempts': quiz_unlimited_attempts,
            'quiz_allow_reassessment': quiz_allow_reassessment,
            'project_brief': project_brief,
            'godot_enabled': godot_enabled,
            'godot_template_url': godot_template_url,
        }
    )

    errors = {}
    if activity_type not in ACTIVITY_TYPE_LABELS:
        errors['activity_type'] = 'Choose an activity type.'
    if not title:
        errors['title'] = 'Activity title is required.'
    if activity_type in {'video', 'slides'} and not resource_url:
        errors['resource_url'] = 'An embed URL is required for this activity.'
    if activity_type == 'text' and not content_text and not resource_url:
        errors['content_text'] = 'Add rich text content or an embedded document URL.'
    if activity_type == 'quiz':
        if not quiz_prompt:
            errors['quiz_prompt'] = 'Quiz instructions are required.'
        if not quiz_unlimited_attempts and not 1 <= quiz_max_attempts <= 20:
            errors['quiz_max_attempts'] = 'Limited attempts must be between 1 and 20.'
        questions, question_errors, question_count = collect_quiz_questions(form)
        form_data['question_count'] = question_count
        form_data['questions'] = [
            {
                'prompt': question['question'],
                'options': {letter: question['options'][idx] for idx, letter in enumerate(QUIZ_ANSWER_LETTERS)},
                'answer': question['answer'] or 'A',
            }
            for question in questions
        ]
        errors.update(question_errors)
    elif activity_type == 'project':
        if not description and not project_brief:
            errors['project_brief'] = 'Add teacher directions or a project brief.'
    else:
        form_data['questions'] = form_data['questions'][:1]

    cleaned = {
        'item_type': to_storage_activity_type(activity_type),
        'title': title,
        'description': description,
        'content_text': content_text,
        'resource_url': resource_url,
        'points_possible': 100 if activity_type in {'quiz', 'project'} else None,
        'quiz_prompt': quiz_prompt if activity_type == 'quiz' else '',
        'quiz_questions_json': json.dumps(
            [
                {
                    'type': 'mcq',
                    'question': question['prompt'],
                    'options': [question['options'][letter] for letter in QUIZ_ANSWER_LETTERS],
                    'answer': question['answer'],
                }
                for question in form_data['questions']
            ]
        )
        if activity_type == 'quiz'
        else '[]',
        'quiz_max_attempts': quiz_max_attempts if activity_type == 'quiz' else 1,
        'quiz_unlimited_attempts': 1 if activity_type == 'quiz' and quiz_unlimited_attempts else 0,
        'quiz_allow_reassessment': 1 if activity_type == 'quiz' and quiz_allow_reassessment else 0,
        'project_brief': project_brief if activity_type == 'project' else '',
        'godot_enabled': 1 if activity_type == 'project' and godot_enabled else 0,
        'godot_template_url': godot_template_url if activity_type == 'project' else '',
    }
    return cleaned, form_data, errors


def determine_module_lesson_type(item_types):
    item_types = set(item_types)
    if not item_types:
        return 'mixed'
    if item_types == {'slides'}:
        return 'slides'
    if item_types == {'project'}:
        return 'project'
    if item_types.issubset({'video', 'resource'}):
        return 'video'
    return 'mixed'


def resequence_rows(db, table_name, parent_column, parent_id):
    rows = db.execute(
        f'SELECT id FROM {table_name} WHERE {parent_column} = ? ORDER BY position, id',
        (parent_id,),
    ).fetchall()
    for position, row in enumerate(rows, start=1):
        db.execute(f'UPDATE {table_name} SET position = ? WHERE id = ?', (position, row['id']))


def sync_module_template_from_outline(db, module_template_id):
    items = [
        dict(row)
        for row in db.execute(
            '''
            SELECT mli.*
            FROM module_lesson_items mli
            JOIN module_lessons ml ON ml.id = mli.lesson_id
            WHERE ml.module_template_id = ?
            ORDER BY ml.position, mli.position, mli.id
            ''',
            (module_template_id,),
        ).fetchall()
    ]

    item_types = {item['item_type'] for item in items}
    first_video = next((item for item in items if item['item_type'] == 'video' and item['resource_url']), None)
    first_slide = next((item for item in items if item['item_type'] == 'slides'), None)
    first_quiz = next((item for item in items if item['item_type'] == 'quiz'), None)
    first_project = next((item for item in items if item['item_type'] == 'project'), None)

    db.execute(
        '''
        UPDATE module_templates
        SET lesson_type = ?,
            content_url = ?,
            slide_url = ?,
            godot_template_url = ?,
            activity_video = ?,
            activity_slides = ?,
            activity_quiz = ?,
            activity_project = ?,
            quiz_prompt = ?,
            quiz_questions_json = ?,
            quiz_max_attempts = ?,
            quiz_unlimited_attempts = ?,
            quiz_allow_reassessment = ?,
            project_brief = ?,
            godot_enabled = ?
        WHERE id = ?
        ''',
        (
            determine_module_lesson_type(item_types),
            first_video['resource_url'] if first_video else '',
            first_slide['resource_url'] if first_slide else '',
            first_project['godot_template_url'] if first_project else '',
            1 if {'video', 'resource'} & item_types else 0,
            1 if 'slides' in item_types else 0,
            1 if 'quiz' in item_types else 0,
            1 if 'project' in item_types else 0,
            first_quiz['quiz_prompt'] if first_quiz else '',
            first_quiz['quiz_questions_json'] if first_quiz else '[]',
            first_quiz['quiz_max_attempts'] if first_quiz else 1,
            first_quiz['quiz_unlimited_attempts'] if first_quiz else 0,
            first_quiz['quiz_allow_reassessment'] if first_quiz else 0,
            first_project['project_brief'] if first_project else '',
            first_project['godot_enabled'] if first_project else 0,
            module_template_id,
        ),
    )


def get_module_lessons(db, module_template_id):
    lessons = [
        {**dict(row), 'items': []}
        for row in db.execute(
            '''
            SELECT *
            FROM module_lessons
            WHERE module_template_id = ?
            ORDER BY position, id
            ''',
            (module_template_id,),
        ).fetchall()
    ]
    if not lessons:
        return []

    lesson_lookup = {lesson['id']: lesson for lesson in lessons}
    items = db.execute(
        '''
        SELECT mli.*
        FROM module_lesson_items mli
        JOIN module_lessons ml ON ml.id = mli.lesson_id
        WHERE ml.module_template_id = ?
        ORDER BY ml.position, mli.position, mli.id
        ''',
        (module_template_id,),
    ).fetchall()
    for item in items:
        item_dict = dict(item)
        item_dict['presented_type'] = to_presented_activity_type(item_dict['item_type'])
        item_dict['type_label'] = get_activity_type_label(item_dict['item_type'])
        item_dict['quiz_question_count'] = len(load_quiz_questions(item_dict['quiz_questions_json'])) if item_dict['item_type'] == 'quiz' else 0
        lesson_lookup[item['lesson_id']]['items'].append(item_dict)
    return lessons


def summarize_module_outline(lessons):
    lesson_count = len(lessons)
    item_count = sum(len(lesson['items']) for lesson in lessons)
    points_possible = sum(
        item['points_possible'] or 0
        for lesson in lessons
        for item in lesson['items']
    )
    return lesson_count, item_count, points_possible


def clone_module_template(db, source_template_id, created_by, is_reusable=0):
    source_template = db.execute(
        'SELECT * FROM module_templates WHERE id = ?',
        (source_template_id,),
    ).fetchone()
    if not source_template:
        return None

    new_template_id = db.execute(
        '''
        INSERT INTO module_templates (
            title, summary, objectives, lesson_type, content_url, slide_url, godot_template_url,
            activity_video, activity_slides, activity_quiz, activity_project,
            quiz_prompt, quiz_questions_json, quiz_max_attempts, quiz_unlimited_attempts, quiz_allow_reassessment,
            project_brief, godot_enabled, is_reusable, created_by
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            source_template['title'],
            source_template['summary'],
            source_template['objectives'],
            source_template['lesson_type'],
            source_template['content_url'],
            source_template['slide_url'],
            source_template['godot_template_url'],
            source_template['activity_video'],
            source_template['activity_slides'],
            source_template['activity_quiz'],
            source_template['activity_project'],
            source_template['quiz_prompt'],
            source_template['quiz_questions_json'],
            source_template['quiz_max_attempts'],
            source_template['quiz_unlimited_attempts'],
            source_template['quiz_allow_reassessment'],
            source_template['project_brief'],
            source_template['godot_enabled'],
            is_reusable,
            created_by,
        ),
    ).lastrowid

    lesson_rows = db.execute(
        '''
        SELECT *
        FROM module_lessons
        WHERE module_template_id = ?
        ORDER BY position, id
        ''',
        (source_template_id,),
    ).fetchall()
    lesson_id_map = {}
    for lesson in lesson_rows:
        new_lesson_id = db.execute(
            '''
            INSERT INTO module_lessons (module_template_id, title, overview, position)
            VALUES (?, ?, ?, ?)
            ''',
            (new_template_id, lesson['title'], lesson['overview'], lesson['position']),
        ).lastrowid
        lesson_id_map[lesson['id']] = new_lesson_id

    item_rows = db.execute(
        '''
        SELECT *
        FROM module_lesson_items
        WHERE lesson_id IN (
            SELECT id FROM module_lessons WHERE module_template_id = ?
        )
        ORDER BY lesson_id, position, id
        ''',
        (source_template_id,),
    ).fetchall()
    for item in item_rows:
        db.execute(
            '''
            INSERT INTO module_lesson_items (
                lesson_id, title, item_type, description, content_text, resource_url, points_possible,
                quiz_prompt, quiz_questions_json, quiz_max_attempts, quiz_unlimited_attempts, quiz_allow_reassessment,
                project_brief, godot_enabled, godot_template_url, position
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                lesson_id_map[item['lesson_id']],
                item['title'],
                item['item_type'],
                item['description'],
                item['content_text'],
                item['resource_url'],
                item['points_possible'],
                item['quiz_prompt'],
                item['quiz_questions_json'],
                item['quiz_max_attempts'],
                item['quiz_unlimited_attempts'],
                item['quiz_allow_reassessment'],
                item['project_brief'],
                item['godot_enabled'],
                item['godot_template_url'],
                item['position'],
            ),
        )
    return new_template_id


def create_course_module(db, course_id, template_id, module_title, due_date=None, required=1):
    next_position = db.execute(
        'SELECT COALESCE(MAX(position), 0) + 1 AS next_position FROM course_modules WHERE course_id = ?',
        (course_id,),
    ).fetchone()['next_position']
    return db.execute(
        '''
        INSERT INTO course_modules (course_id, module_template_id, module_title, position, required, due_date)
        VALUES (?, ?, ?, ?, ?, ?)
        ''',
        (course_id, template_id, module_title, next_position, required, due_date),
    ).lastrowid


def ensure_private_course_module_templates(db):
    course_modules = db.execute(
        '''
        SELECT cm.id, cm.module_template_id, c.teacher_id, mt.is_reusable
        FROM course_modules cm
        JOIN course_offerings c ON c.id = cm.course_id
        JOIN module_templates mt ON mt.id = cm.module_template_id
        WHERE COALESCE(mt.is_reusable, 1) = 1
        ORDER BY cm.id
        '''
    ).fetchall()
    for course_module in course_modules:
        cloned_template_id = clone_module_template(
            db,
            course_module['module_template_id'],
            course_module['teacher_id'],
            is_reusable=0,
        )
        db.execute(
            'UPDATE course_modules SET module_template_id = ? WHERE id = ?',
            (cloned_template_id, course_module['id']),
        )


def get_teacher_course_builder_context(db, course_id, teacher_id):
    course = db.execute(
        'SELECT * FROM course_offerings WHERE id = ? AND teacher_id = ?',
        (course_id, teacher_id),
    ).fetchone()
    if not course:
        return None

    modules = []
    module_rows = db.execute(
        '''
        SELECT cm.*, mt.summary, mt.objectives, mt.lesson_type, mt.created_by, mt.is_reusable
        FROM course_modules cm
        JOIN module_templates mt ON mt.id = cm.module_template_id
        WHERE cm.course_id = ?
        ORDER BY cm.position, cm.id
        ''',
        (course_id,),
    ).fetchall()
    for row in module_rows:
        module = dict(row)
        module['lessons'] = get_module_lessons(db, module['module_template_id'])
        module['lesson_count'], module['item_count'], module['points_possible'] = summarize_module_outline(module['lessons'])
        modules.append(module)

    importable_modules = db.execute(
        '''
        SELECT cm.id, cm.module_title, c.title AS course_title
        FROM course_modules cm
        JOIN course_offerings c ON c.id = cm.course_id
        WHERE c.teacher_id = ? AND c.id != ?
        ORDER BY c.title, cm.position, cm.id
        ''',
        (teacher_id, course_id),
    ).fetchall()
    reusable_templates = db.execute(
        '''
        SELECT mt.id, mt.title,
               COUNT(DISTINCT ml.id) AS lesson_count,
               COUNT(mli.id) AS item_count
        FROM module_templates mt
        LEFT JOIN module_lessons ml ON ml.module_template_id = mt.id
        LEFT JOIN module_lesson_items mli ON mli.lesson_id = ml.id
        WHERE mt.created_by = ? AND COALESCE(mt.is_reusable, 1) = 1
        GROUP BY mt.id
        ORDER BY mt.created_at DESC
        ''',
        (teacher_id,),
    ).fetchall()

    return {
        'course': course,
        'modules': modules,
        'importable_modules': importable_modules,
        'reusable_templates': reusable_templates,
    }


def render_teacher_course_builder(course_id, builder_state=None, form_errors=None, form_values=None, status_code=200):
    db = get_db()
    context = get_teacher_course_builder_context(db, course_id, g.user['id'])
    if not context:
        db.close()
        abort(404)
    db.close()
    return (
        render_template(
            'teacher_course_builder.html',
            builder_state=builder_state or {},
            form_errors=form_errors or {},
            form_values=form_values or {},
            **context,
        ),
        status_code,
    )


def get_course_module_for_teacher(db, course_id, course_module_id, teacher_id):
    return db.execute(
        '''
        SELECT cm.*, mt.summary, mt.objectives
        FROM course_modules cm
        JOIN course_offerings c ON c.id = cm.course_id
        JOIN module_templates mt ON mt.id = cm.module_template_id
        WHERE cm.id = ? AND cm.course_id = ? AND c.teacher_id = ?
        ''',
        (course_module_id, course_id, teacher_id),
    ).fetchone()


def get_module_lesson_for_teacher(db, course_id, course_module_id, lesson_id, teacher_id):
    return db.execute(
        '''
        SELECT ml.*, cm.module_title, cm.module_template_id
        FROM module_lessons ml
        JOIN course_modules cm ON cm.module_template_id = ml.module_template_id
        JOIN course_offerings c ON c.id = cm.course_id
        WHERE ml.id = ? AND cm.id = ? AND cm.course_id = ? AND c.teacher_id = ?
        ''',
        (lesson_id, course_module_id, course_id, teacher_id),
    ).fetchone()


def get_module_lesson_item_for_teacher(db, course_id, course_module_id, lesson_id, item_id, teacher_id):
    return db.execute(
        '''
        SELECT mli.*, ml.module_template_id
        FROM module_lesson_items mli
        JOIN module_lessons ml ON ml.id = mli.lesson_id
        JOIN course_modules cm ON cm.module_template_id = ml.module_template_id
        JOIN course_offerings c ON c.id = cm.course_id
        WHERE mli.id = ? AND ml.id = ? AND cm.id = ? AND cm.course_id = ? AND c.teacher_id = ?
        ''',
        (item_id, lesson_id, course_module_id, course_id, teacher_id),
    ).fetchone()


@app.before_request
def load_user():
    g.user = get_current_user()


@app.context_processor
def inject_globals():
    teacher_sidebar_courses = []
    active_course_id = None
    if g.user and g.user['role'] == 'teacher':
        db = get_db()
        teacher_sidebar_courses = db.execute(
            '''
            SELECT id, title
            FROM course_offerings
            WHERE teacher_id = ?
            ORDER BY created_at DESC
            ''',
            (g.user['id'],),
        ).fetchall()
        db.close()
        active_course_id = (request.view_args or {}).get('course_id')
    return {
        'current_user': g.user,
        'godot_editor_url': GODOT_EDITOR_URL,
        'current_year': datetime.utcnow().year,
        'teacher_sidebar_courses': teacher_sidebar_courses,
        'active_course_id': active_course_id,
        'activity_type_label': get_activity_type_label,
    }


@app.route('/')
def index():
    db = get_db()
    metrics = db.execute(
        '''
        SELECT
            (SELECT COUNT(*) FROM course_offerings) AS course_count,
            (SELECT COUNT(*) FROM module_templates WHERE COALESCE(is_reusable, 1) = 1) AS module_count,
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
        SELECT mt.*, u.name AS author_name,
               COUNT(DISTINCT ml.id) AS lesson_count,
               COUNT(mli.id) AS item_count,
               COALESCE(SUM(CASE WHEN mli.points_possible IS NOT NULL THEN mli.points_possible ELSE 0 END), 0) AS points_possible
        FROM module_templates mt
        LEFT JOIN users u ON u.id = mt.created_by
        LEFT JOIN module_lessons ml ON ml.module_template_id = mt.id
        LEFT JOIN module_lesson_items mli ON mli.lesson_id = ml.id
        WHERE COALESCE(mt.is_reusable, 1) = 1
        GROUP BY mt.id
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
            cloned_template_id = clone_module_template(db, template['id'], g.user['id'], is_reusable=0)
            db.execute(
                '''
                INSERT INTO course_modules (course_id, module_template_id, module_title, position, required)
                VALUES (?, ?, ?, ?, 1)
                ''',
                (course_id, cloned_template_id, template['title'], position),
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

    if not title or not summary or not objectives:
        flash('Module title, summary, and objectives are required.', 'warning')
        return redirect(url_for('teacher_dashboard'))

    db = get_db()
    template_id = db.execute(
        '''
        INSERT INTO module_templates (
            title, summary, objectives, lesson_type, content_url, slide_url, godot_template_url,
            activity_video, activity_slides, activity_quiz, activity_project,
            quiz_prompt, quiz_questions_json, quiz_max_attempts, quiz_unlimited_attempts, quiz_allow_reassessment,
            project_brief, godot_enabled, is_reusable, created_by
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            title,
            summary,
            objectives,
            'mixed',
            '',
            '',
            '',
            0,
            0,
            0,
            0,
            '',
            '[]',
            1,
            0,
            0,
            '',
            0,
            1,
            g.user['id'],
        ),
    ).lastrowid
    db.commit()
    db.close()
    flash('Unit template created. Add lessons and activities one piece at a time.', 'success')
    return redirect(url_for('module_template_builder', template_id=template_id))


@app.route('/teacher/modules/<int:template_id>/builder')
@role_required('teacher')
def module_template_builder(template_id):
    db = get_db()
    template = db.execute(
        'SELECT * FROM module_templates WHERE id = ? AND created_by = ?',
        (template_id, g.user['id']),
    ).fetchone()
    if not template:
        db.close()
        abort(404)

    lessons = get_module_lessons(db, template_id)
    lesson_count, item_count, points_possible = summarize_module_outline(lessons)
    db.close()
    return render_template(
        'module_template_builder.html',
        template=template,
        lessons=lessons,
        lesson_count=lesson_count,
        item_count=item_count,
        points_possible=points_possible,
    )


@app.route('/teacher/modules/<int:template_id>/lessons', methods=['POST'])
@role_required('teacher')
def add_module_lesson(template_id):
    title = request.form.get('title', '').strip()
    overview = request.form.get('overview', '').strip()
    if not title:
        flash('Lesson title is required.', 'warning')
        return redirect(url_for('module_template_builder', template_id=template_id))

    db = get_db()
    template = db.execute(
        'SELECT id FROM module_templates WHERE id = ? AND created_by = ?',
        (template_id, g.user['id']),
    ).fetchone()
    if not template:
        db.close()
        abort(404)

    next_position = db.execute(
        'SELECT COALESCE(MAX(position), 0) + 1 AS next_position FROM module_lessons WHERE module_template_id = ?',
        (template_id,),
    ).fetchone()['next_position']
    db.execute(
        '''
        INSERT INTO module_lessons (module_template_id, title, overview, position)
        VALUES (?, ?, ?, ?)
        ''',
        (template_id, title, overview, next_position),
    )
    db.commit()
    db.close()
    flash('Lesson added to the unit.', 'success')
    return redirect(url_for('module_template_builder', template_id=template_id))


@app.route('/teacher/modules/<int:template_id>/lessons/<int:lesson_id>/items', methods=['POST'])
@role_required('teacher')
def add_module_lesson_item(template_id, lesson_id):
    item_type = request.form.get('item_type', '').strip().lower()
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    resource_url = request.form.get('resource_url', '').strip()
    points_possible = request.form.get('points_possible', type=int)
    quiz_prompt = request.form.get('quiz_prompt', '').strip()
    quiz_questions = parse_quiz_questions(request.form.get('quiz_questions', ''))
    quiz_max_attempts = request.form.get('quiz_max_attempts', type=int) or 1
    quiz_allow_reassessment = 1 if request.form.get('quiz_allow_reassessment') == 'on' else 0
    project_brief = request.form.get('project_brief', '').strip()
    godot_enabled = 1 if request.form.get('godot_enabled') == 'on' else 0
    godot_template_url = request.form.get('godot_template_url', '').strip()

    if item_type not in {'video', 'resource', 'slides', 'quiz', 'project'}:
        abort(400)
    if not title:
        flash('Activity title is required.', 'warning')
        return redirect(url_for('module_template_builder', template_id=template_id))
    if points_possible is not None and points_possible < 0:
        flash('Points possible cannot be negative.', 'warning')
        return redirect(url_for('module_template_builder', template_id=template_id))
    if item_type == 'quiz' and not quiz_prompt:
        flash('Quiz prompt is required for quiz activities.', 'warning')
        return redirect(url_for('module_template_builder', template_id=template_id))
    if item_type == 'quiz' and (quiz_max_attempts < 1 or quiz_max_attempts > 10):
        flash('Quiz attempts must be between 1 and 10.', 'warning')
        return redirect(url_for('module_template_builder', template_id=template_id))
    if item_type == 'project' and not project_brief and not description:
        flash('Add a short project brief or description for project activities.', 'warning')
        return redirect(url_for('module_template_builder', template_id=template_id))

    db = get_db()
    lesson = db.execute(
        '''
        SELECT ml.id
        FROM module_lessons ml
        JOIN module_templates mt ON mt.id = ml.module_template_id
        WHERE ml.id = ? AND ml.module_template_id = ? AND mt.created_by = ?
        ''',
        (lesson_id, template_id, g.user['id']),
    ).fetchone()
    if not lesson:
        db.close()
        abort(404)

    next_position = db.execute(
        'SELECT COALESCE(MAX(position), 0) + 1 AS next_position FROM module_lesson_items WHERE lesson_id = ?',
        (lesson_id,),
    ).fetchone()['next_position']
    db.execute(
        '''
        INSERT INTO module_lesson_items (
            lesson_id, title, item_type, description, content_text, resource_url, points_possible,
            quiz_prompt, quiz_questions_json, quiz_max_attempts, quiz_unlimited_attempts, quiz_allow_reassessment,
            project_brief, godot_enabled, godot_template_url, position
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            lesson_id,
            title,
            item_type,
            description,
            '',
            resource_url,
            points_possible,
            quiz_prompt if item_type == 'quiz' else '',
            json.dumps(quiz_questions) if item_type == 'quiz' else '[]',
            quiz_max_attempts if item_type == 'quiz' else 1,
            0,
            quiz_allow_reassessment if item_type == 'quiz' else 0,
            project_brief if item_type == 'project' else '',
            godot_enabled if item_type == 'project' else 0,
            godot_template_url if item_type == 'project' else '',
            next_position,
        ),
    )
    sync_module_template_from_outline(db, template_id)
    db.commit()
    db.close()
    flash('Activity added to the lesson.', 'success')
    return redirect(url_for('module_template_builder', template_id=template_id))


@app.route('/teacher/modules/<int:template_id>/lessons/<int:lesson_id>/remove', methods=['POST'])
@role_required('teacher')
def remove_module_lesson(template_id, lesson_id):
    db = get_db()
    lesson = db.execute(
        '''
        SELECT ml.id
        FROM module_lessons ml
        JOIN module_templates mt ON mt.id = ml.module_template_id
        WHERE ml.id = ? AND ml.module_template_id = ? AND mt.created_by = ?
        ''',
        (lesson_id, template_id, g.user['id']),
    ).fetchone()
    if not lesson:
        db.close()
        abort(404)

    db.execute('DELETE FROM module_lessons WHERE id = ?', (lesson_id,))
    resequence_rows(db, 'module_lessons', 'module_template_id', template_id)
    sync_module_template_from_outline(db, template_id)
    db.commit()
    db.close()
    flash('Lesson removed from the unit.', 'success')
    return redirect(url_for('module_template_builder', template_id=template_id))


@app.route('/teacher/modules/<int:template_id>/lessons/<int:lesson_id>/items/<int:item_id>/remove', methods=['POST'])
@role_required('teacher')
def remove_module_lesson_item(template_id, lesson_id, item_id):
    db = get_db()
    item = db.execute(
        '''
        SELECT mli.id
        FROM module_lesson_items mli
        JOIN module_lessons ml ON ml.id = mli.lesson_id
        JOIN module_templates mt ON mt.id = ml.module_template_id
        WHERE mli.id = ? AND ml.id = ? AND ml.module_template_id = ? AND mt.created_by = ?
        ''',
        (item_id, lesson_id, template_id, g.user['id']),
    ).fetchone()
    if not item:
        db.close()
        abort(404)

    db.execute('DELETE FROM module_lesson_items WHERE id = ?', (item_id,))
    resequence_rows(db, 'module_lesson_items', 'lesson_id', lesson_id)
    sync_module_template_from_outline(db, template_id)
    db.commit()
    db.close()
    flash('Activity removed from the lesson.', 'success')
    return redirect(url_for('module_template_builder', template_id=template_id))


@app.route('/teacher/course/<int:course_id>')
@role_required('teacher')
def teacher_course(course_id):
    panel = request.args.get('panel', '').strip()
    module_id = request.args.get('module_id', type=int)
    lesson_id = request.args.get('lesson_id', type=int)
    activity_id = request.args.get('activity_id', type=int)
    activity_type = request.args.get('activity_type', '').strip().lower()
    question_count = max(1, min(request.args.get('question_count', type=int) or 1, 10))

    form_values = {}
    if panel in {'new-module', 'import-module'}:
        form_values = {
            'title': '',
            'summary': '',
            'objectives': '',
            'due_date': '',
            'source_course_module_id': '',
            'template_id': '',
        }

    db = get_db()
    course_builder_context = get_teacher_course_builder_context(db, course_id, g.user['id'])
    if not course_builder_context:
        db.close()
        abort(404)

    if panel == 'edit-module' and module_id:
        module = get_course_module_for_teacher(db, course_id, module_id, g.user['id'])
        if module:
            form_values = {
                'title': module['module_title'],
                'summary': module['summary'],
                'objectives': module['objectives'],
                'due_date': module['due_date'] or '',
            }
    elif panel in {'add-lesson', 'edit-lesson'} and module_id:
        form_values = {'title': '', 'overview': ''}
        if panel == 'edit-lesson' and lesson_id:
            lesson = get_module_lesson_for_teacher(db, course_id, module_id, lesson_id, g.user['id'])
            if lesson:
                form_values = {'title': lesson['title'], 'overview': lesson['overview']}
    elif panel in {'choose-activity', 'add-activity'}:
        form_values = resize_activity_questions(
            get_default_activity_form(activity_type if activity_type in ACTIVITY_TYPE_LABELS else 'video'),
            question_count,
        )
    elif panel == 'edit-activity' and module_id and lesson_id and activity_id:
        item = get_module_lesson_item_for_teacher(db, course_id, module_id, lesson_id, activity_id, g.user['id'])
        if item:
            form_values = resize_activity_questions(get_activity_form_from_item(item), question_count)
            activity_type = form_values['activity_type']

    db.close()
    return render_template(
        'teacher_course_builder.html',
        course=course_builder_context['course'],
        modules=course_builder_context['modules'],
        importable_modules=course_builder_context['importable_modules'],
        reusable_templates=course_builder_context['reusable_templates'],
        builder_state={
            'panel': panel,
            'module_id': module_id,
            'lesson_id': lesson_id,
            'activity_id': activity_id,
            'activity_type': activity_type,
            'question_count': question_count,
        },
        form_errors={},
        form_values=form_values,
    )


@app.route('/teacher/course/<int:course_id>/modules/create', methods=['POST'])
@role_required('teacher')
def create_course_module_builder(course_id):
    title = request.form.get('title', '').strip()
    summary = request.form.get('summary', '').strip()
    objectives = request.form.get('objectives', '').strip()
    due_date = request.form.get('due_date', '').strip()
    form_values = {
        'title': title,
        'summary': summary,
        'objectives': objectives,
        'due_date': due_date,
    }
    errors = {}
    if not title:
        errors['title'] = 'Module title is required.'
    if not summary:
        errors['summary'] = 'Module description is required.'
    if not objectives:
        errors['objectives'] = 'Module objectives are required.'
    if errors:
        return render_teacher_course_builder(
            course_id,
            builder_state={'panel': 'new-module'},
            form_errors=errors,
            form_values=form_values,
            status_code=400,
        )
    db = get_db()
    course = get_course_for_teacher(course_id, g.user['id'])
    if not course:
        db.close()
        abort(404)
    template_id = db.execute(
        '''
        INSERT INTO module_templates (
            title, summary, objectives, lesson_type, content_url, slide_url, godot_template_url,
            activity_video, activity_slides, activity_quiz, activity_project,
            quiz_prompt, quiz_questions_json, quiz_max_attempts, quiz_unlimited_attempts, quiz_allow_reassessment,
            project_brief, godot_enabled, is_reusable, created_by
        ) VALUES (?, ?, ?, 'mixed', '', '', '', 0, 0, 0, 0, '', '[]', 1, 0, 0, '', 0, 0, ?)
        ''',
        (title, summary, objectives, g.user['id']),
    ).lastrowid
    create_course_module(db, course_id, template_id, title, due_date or None, required=1)
    db.commit()
    db.close()
    flash('Module created for this course.', 'success')
    return redirect(url_for('teacher_course', course_id=course_id))


@app.route('/teacher/course/<int:course_id>/modules/import', methods=['POST'])
@role_required('teacher')
def import_module_to_course(course_id):
    source_course_module_id = request.form.get('source_course_module_id', type=int)
    template_id = request.form.get('template_id', type=int)
    due_date = request.form.get('due_date', '').strip()
    form_values = {
        'source_course_module_id': source_course_module_id or '',
        'template_id': template_id or '',
        'due_date': due_date,
    }
    if not source_course_module_id and not template_id:
        return render_teacher_course_builder(
            course_id,
            builder_state={'panel': 'import-module'},
            form_errors={'source_course_module_id': 'Choose a course module or reusable unit to copy.'},
            form_values=form_values,
            status_code=400,
        )
    db = get_db()
    course = get_course_for_teacher(course_id, g.user['id'])
    if not course:
        db.close()
        abort(404)
    template = None
    module_title = None
    if source_course_module_id:
        source = db.execute(
            '''
            SELECT cm.module_title, cm.module_template_id
            FROM course_modules cm
            JOIN course_offerings c ON c.id = cm.course_id
            WHERE cm.id = ? AND c.teacher_id = ?
            ''',
            (source_course_module_id, g.user['id']),
        ).fetchone()
        if source:
            template = db.execute(
                'SELECT id, title FROM module_templates WHERE id = ?',
                (source['module_template_id'],),
            ).fetchone()
            module_title = source['module_title']
    elif template_id:
        template = db.execute(
            'SELECT id, title FROM module_templates WHERE id = ? AND created_by = ? AND COALESCE(is_reusable, 1) = 1',
            (template_id, g.user['id']),
        ).fetchone()
        module_title = template['title'] if template else None
    if not template:
        db.close()
        return render_teacher_course_builder(
            course_id,
            builder_state={'panel': 'import-module'},
            form_errors={'source_course_module_id': 'The selected module could not be copied.'},
            form_values=form_values,
            status_code=404,
        )
    cloned_template_id = clone_module_template(db, template['id'], g.user['id'], is_reusable=0)
    create_course_module(db, course_id, cloned_template_id, module_title or template['title'], due_date or None, required=1)
    db.commit()
    db.close()
    flash('Module copied into this course.', 'success')
    return redirect(url_for('teacher_course', course_id=course_id))


@app.route('/teacher/course/<int:course_id>/modules/<int:course_module_id>/edit', methods=['POST'])
@role_required('teacher')
def update_course_module_builder(course_id, course_module_id):
    title = request.form.get('title', '').strip()
    summary = request.form.get('summary', '').strip()
    objectives = request.form.get('objectives', '').strip()
    due_date = request.form.get('due_date', '').strip() or None
    errors = {}
    if not title:
        errors['title'] = 'Module title is required.'
    if not summary:
        errors['summary'] = 'Module description is required.'
    if not objectives:
        errors['objectives'] = 'Module objectives are required.'
    if errors:
        return render_teacher_course_builder(
            course_id,
            builder_state={'panel': 'edit-module', 'module_id': course_module_id},
            form_errors=errors,
            form_values={
                'title': title,
                'summary': summary,
                'objectives': objectives,
                'due_date': due_date or '',
            },
            status_code=400,
        )
    db = get_db()
    module = get_course_module_for_teacher(db, course_id, course_module_id, g.user['id'])
    if not module:
        db.close()
        abort(404)
    db.execute(
        'UPDATE course_modules SET module_title = ?, due_date = ? WHERE id = ?',
        (title, due_date, course_module_id),
    )
    db.execute(
        'UPDATE module_templates SET title = ?, summary = ?, objectives = ? WHERE id = ?',
        (title, summary, objectives, module['module_template_id']),
    )
    db.commit()
    db.close()
    flash('Module details updated.', 'success')
    return redirect(url_for('teacher_course', course_id=course_id))


@app.route('/teacher/course/<int:course_id>/modules/<int:course_module_id>/remove', methods=['POST'])
@role_required('teacher')
def remove_module_from_course(course_id, course_module_id):
    db = get_db()
    module = get_course_module_for_teacher(db, course_id, course_module_id, g.user['id'])
    if not module:
        db.close()
        abort(404)
    db.execute('DELETE FROM course_modules WHERE id = ? AND course_id = ?', (course_module_id, course_id))
    resequence_rows(db, 'course_modules', 'course_id', course_id)
    remaining_links = db.execute(
        'SELECT COUNT(*) AS count FROM course_modules WHERE module_template_id = ?',
        (module['module_template_id'],),
    ).fetchone()['count']
    if remaining_links == 0:
        db.execute(
            'DELETE FROM module_templates WHERE id = ? AND COALESCE(is_reusable, 1) = 0',
            (module['module_template_id'],),
        )
    db.commit()
    db.close()
    flash('Module deleted from the course.', 'success')
    return redirect(url_for('teacher_course', course_id=course_id))


@app.route('/teacher/course/<int:course_id>/modules/<int:course_module_id>/lessons/create', methods=['POST'])
@role_required('teacher')
def add_course_module_lesson(course_id, course_module_id):
    title = request.form.get('title', '').strip()
    overview = request.form.get('overview', '').strip()
    if not title:
        return render_teacher_course_builder(
            course_id,
            builder_state={'panel': 'add-lesson', 'module_id': course_module_id},
            form_errors={'title': 'Lesson title is required.'},
            form_values={'title': title, 'overview': overview},
            status_code=400,
        )
    db = get_db()
    module = get_course_module_for_teacher(db, course_id, course_module_id, g.user['id'])
    if not module:
        db.close()
        abort(404)
    next_position = db.execute(
        'SELECT COALESCE(MAX(position), 0) + 1 AS next_position FROM module_lessons WHERE module_template_id = ?',
        (module['module_template_id'],),
    ).fetchone()['next_position']
    db.execute(
        'INSERT INTO module_lessons (module_template_id, title, overview, position) VALUES (?, ?, ?, ?)',
        (module['module_template_id'], title, overview, next_position),
    )
    db.commit()
    db.close()
    flash('Lesson added.', 'success')
    return redirect(url_for('teacher_course', course_id=course_id))


@app.route('/teacher/course/<int:course_id>/modules/<int:course_module_id>/lessons/<int:lesson_id>/edit', methods=['POST'])
@role_required('teacher')
def update_course_module_lesson(course_id, course_module_id, lesson_id):
    title = request.form.get('title', '').strip()
    overview = request.form.get('overview', '').strip()
    if not title:
        return render_teacher_course_builder(
            course_id,
            builder_state={'panel': 'edit-lesson', 'module_id': course_module_id, 'lesson_id': lesson_id},
            form_errors={'title': 'Lesson title is required.'},
            form_values={'title': title, 'overview': overview},
            status_code=400,
        )
    db = get_db()
    lesson = get_module_lesson_for_teacher(db, course_id, course_module_id, lesson_id, g.user['id'])
    if not lesson:
        db.close()
        abort(404)
    db.execute('UPDATE module_lessons SET title = ?, overview = ? WHERE id = ?', (title, overview, lesson_id))
    db.commit()
    db.close()
    flash('Lesson updated.', 'success')
    return redirect(url_for('teacher_course', course_id=course_id))


@app.route('/teacher/course/<int:course_id>/modules/<int:course_module_id>/lessons/<int:lesson_id>/remove', methods=['POST'])
@role_required('teacher')
def remove_course_module_lesson(course_id, course_module_id, lesson_id):
    db = get_db()
    lesson = get_module_lesson_for_teacher(db, course_id, course_module_id, lesson_id, g.user['id'])
    if not lesson:
        db.close()
        abort(404)
    db.execute('DELETE FROM module_lessons WHERE id = ?', (lesson_id,))
    resequence_rows(db, 'module_lessons', 'module_template_id', lesson['module_template_id'])
    sync_module_template_from_outline(db, lesson['module_template_id'])
    db.commit()
    db.close()
    flash('Lesson deleted.', 'success')
    return redirect(url_for('teacher_course', course_id=course_id))


@app.route('/teacher/course/<int:course_id>/modules/<int:course_module_id>/lessons/<int:lesson_id>/activities/create', methods=['POST'])
@role_required('teacher')
def add_course_module_activity(course_id, course_module_id, lesson_id):
    cleaned, form_values, errors = validate_activity_form(request.form)
    if errors:
        return render_teacher_course_builder(
            course_id,
            builder_state={
                'panel': 'add-activity',
                'module_id': course_module_id,
                'lesson_id': lesson_id,
                'activity_type': form_values['activity_type'],
                'question_count': form_values['question_count'],
            },
            form_errors=errors,
            form_values=form_values,
            status_code=400,
        )
    db = get_db()
    lesson = get_module_lesson_for_teacher(db, course_id, course_module_id, lesson_id, g.user['id'])
    if not lesson:
        db.close()
        abort(404)
    next_position = db.execute(
        'SELECT COALESCE(MAX(position), 0) + 1 AS next_position FROM module_lesson_items WHERE lesson_id = ?',
        (lesson_id,),
    ).fetchone()['next_position']
    db.execute(
        '''
        INSERT INTO module_lesson_items (
            lesson_id, title, item_type, description, content_text, resource_url, points_possible,
            quiz_prompt, quiz_questions_json, quiz_max_attempts, quiz_unlimited_attempts, quiz_allow_reassessment,
            project_brief, godot_enabled, godot_template_url, position
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            lesson_id,
            cleaned['title'],
            cleaned['item_type'],
            cleaned['description'],
            cleaned['content_text'],
            cleaned['resource_url'],
            cleaned['points_possible'],
            cleaned['quiz_prompt'],
            cleaned['quiz_questions_json'],
            cleaned['quiz_max_attempts'],
            cleaned['quiz_unlimited_attempts'],
            cleaned['quiz_allow_reassessment'],
            cleaned['project_brief'],
            cleaned['godot_enabled'],
            cleaned['godot_template_url'],
            next_position,
        ),
    )
    sync_module_template_from_outline(db, lesson['module_template_id'])
    db.commit()
    db.close()
    flash('Activity added.', 'success')
    return redirect(url_for('teacher_course', course_id=course_id))


@app.route('/teacher/course/<int:course_id>/modules/<int:course_module_id>/lessons/<int:lesson_id>/activities/<int:item_id>/edit', methods=['POST'])
@role_required('teacher')
def update_course_module_activity(course_id, course_module_id, lesson_id, item_id):
    cleaned, form_values, errors = validate_activity_form(request.form)
    if errors:
        return render_teacher_course_builder(
            course_id,
            builder_state={
                'panel': 'edit-activity',
                'module_id': course_module_id,
                'lesson_id': lesson_id,
                'activity_id': item_id,
                'activity_type': form_values['activity_type'],
                'question_count': form_values['question_count'],
            },
            form_errors=errors,
            form_values=form_values,
            status_code=400,
        )
    db = get_db()
    item = get_module_lesson_item_for_teacher(db, course_id, course_module_id, lesson_id, item_id, g.user['id'])
    if not item:
        db.close()
        abort(404)
    db.execute(
        '''
        UPDATE module_lesson_items
        SET title = ?, item_type = ?, description = ?, content_text = ?, resource_url = ?, points_possible = ?,
            quiz_prompt = ?, quiz_questions_json = ?, quiz_max_attempts = ?, quiz_unlimited_attempts = ?,
            quiz_allow_reassessment = ?, project_brief = ?, godot_enabled = ?, godot_template_url = ?
        WHERE id = ?
        ''',
        (
            cleaned['title'],
            cleaned['item_type'],
            cleaned['description'],
            cleaned['content_text'],
            cleaned['resource_url'],
            cleaned['points_possible'],
            cleaned['quiz_prompt'],
            cleaned['quiz_questions_json'],
            cleaned['quiz_max_attempts'],
            cleaned['quiz_unlimited_attempts'],
            cleaned['quiz_allow_reassessment'],
            cleaned['project_brief'],
            cleaned['godot_enabled'],
            cleaned['godot_template_url'],
            item_id,
        ),
    )
    sync_module_template_from_outline(db, item['module_template_id'])
    db.commit()
    db.close()
    flash('Activity updated.', 'success')
    return redirect(url_for('teacher_course', course_id=course_id))


@app.route('/teacher/course/<int:course_id>/modules/<int:course_module_id>/lessons/<int:lesson_id>/activities/<int:item_id>/remove', methods=['POST'])
@role_required('teacher')
def remove_course_module_activity(course_id, course_module_id, lesson_id, item_id):
    db = get_db()
    item = get_module_lesson_item_for_teacher(db, course_id, course_module_id, lesson_id, item_id, g.user['id'])
    if not item:
        db.close()
        abort(404)
    db.execute('DELETE FROM module_lesson_items WHERE id = ?', (item_id,))
    resequence_rows(db, 'module_lesson_items', 'lesson_id', lesson_id)
    sync_module_template_from_outline(db, item['module_template_id'])
    db.commit()
    db.close()
    flash('Activity deleted.', 'success')
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
               , mt.quiz_unlimited_attempts
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
    if not module['quiz_unlimited_attempts'] and attempt_count >= max_attempts:
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
        SELECT cm.*, mt.created_by, mt.summary, mt.objectives, mt.lesson_type, mt.content_url, mt.slide_url,
               mt.godot_template_url, mt.activity_video, mt.activity_slides, mt.activity_quiz, mt.activity_project,
               mt.quiz_prompt, mt.quiz_questions_json, mt.quiz_max_attempts, mt.quiz_unlimited_attempts, mt.quiz_allow_reassessment,
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
    lessons = get_module_lessons(db, module['module_template_id'])
    lesson_count, item_count, points_possible = summarize_module_outline(lessons)
    quiz_questions = load_quiz_questions(module['quiz_questions_json'])
    student_quiz_attempts = []
    teacher_quiz_attempts = []
    quiz_attempts_remaining = None if module['quiz_unlimited_attempts'] else module['quiz_max_attempts'] + (1 if module['quiz_allow_reassessment'] else 0)
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
        if quiz_attempts_remaining is not None:
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
        lessons=lessons,
        lesson_count=lesson_count,
        item_count=item_count,
        points_possible=points_possible,
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
