import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, jsonify, session
from werkzeug.utils import secure_filename
from datetime import datetime

app = Flask(__name__)
# Generate a random secret key if not provided
app.secret_key = os.environ.get('SECRET_KEY') or os.urandom(24).hex()
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max file size
app.config['ALLOWED_EXTENSIONS'] = {'blend'}

DATABASE = 'cs_teaching.db'

def get_db():
    """Get database connection"""
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    return db

def init_db():
    """Initialize the database with tables and sample data"""
    db = get_db()
    
    # Create tables
    db.execute('''
        CREATE TABLE IF NOT EXISTS courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    db.execute('''
        CREATE TABLE IF NOT EXISTS lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            video_url TEXT NOT NULL,
            order_num INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (course_id) REFERENCES courses (id)
        )
    ''')
    
    db.execute('''
        CREATE TABLE IF NOT EXISTS student_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_name TEXT NOT NULL,
            lesson_id INTEGER NOT NULL,
            completed BOOLEAN DEFAULT 0,
            completed_at TIMESTAMP,
            FOREIGN KEY (lesson_id) REFERENCES lessons (id),
            UNIQUE(student_name, lesson_id)
        )
    ''')
    
    db.execute('''
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_name TEXT NOT NULL,
            lesson_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            filepath TEXT NOT NULL,
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (lesson_id) REFERENCES lessons (id)
        )
    ''')
    
    # Check if we need to add sample data
    cursor = db.execute('SELECT COUNT(*) as count FROM courses')
    if cursor.fetchone()['count'] == 0:
        # Add Computer Animation course
        cursor = db.execute('''
            INSERT INTO courses (name, description) 
            VALUES (?, ?)
        ''', ('Computer Animation', 'Learn the fundamentals of 3D animation using Blender'))
        course_id = cursor.lastrowid
        
        # Add sample lessons
        lessons = [
            ('Introduction to Blender', 'Learn the Blender interface and basic navigation', 
             'https://www.youtube.com/embed/jnj2BL4chaQ', 1),
            ('Basic Modeling', 'Create your first 3D models using basic shapes', 
             'https://www.youtube.com/embed/imdYIdv8F4w', 2),
            ('Materials and Textures', 'Add colors and textures to your 3D models', 
             'https://www.youtube.com/embed/OYsZmH1Fa3k', 3),
            ('Introduction to Animation', 'Learn keyframe animation basics', 
             'https://www.youtube.com/embed/1d8PjiPu4kM', 4),
        ]
        
        for title, desc, video, order in lessons:
            db.execute('''
                INSERT INTO lessons (course_id, title, description, video_url, order_num)
                VALUES (?, ?, ?, ?, ?)
            ''', (course_id, title, desc, video, order))
    
    db.commit()
    db.close()

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

@app.route('/')
def index():
    """Home page showing all courses"""
    db = get_db()
    courses = db.execute('SELECT * FROM courses ORDER BY created_at DESC').fetchall()
    db.close()
    return render_template('index.html', courses=courses)

@app.route('/course/<int:course_id>')
def course_view(course_id):
    """View a specific course and its lessons"""
    db = get_db()
    course = db.execute('SELECT * FROM courses WHERE id = ?', (course_id,)).fetchone()
    if not course:
        db.close()
        return "Course not found", 404
    
    lessons = db.execute('''
        SELECT * FROM lessons 
        WHERE course_id = ? 
        ORDER BY order_num
    ''', (course_id,)).fetchall()
    
    # Get progress if student is logged in
    student_name = session.get('student_name', '')
    progress = {}
    if student_name:
        progress_rows = db.execute('''
            SELECT lesson_id, completed 
            FROM student_progress 
            WHERE student_name = ?
        ''', (student_name,)).fetchall()
        progress = {row['lesson_id']: row['completed'] for row in progress_rows}
    
    db.close()
    return render_template('course.html', course=course, lessons=lessons, 
                          progress=progress, student_name=student_name)

@app.route('/lesson/<int:lesson_id>')
def lesson_view(lesson_id):
    """View a specific lesson"""
    db = get_db()
    lesson = db.execute('SELECT * FROM lessons WHERE id = ?', (lesson_id,)).fetchone()
    if not lesson:
        db.close()
        return "Lesson not found", 404
    
    course = db.execute('SELECT * FROM courses WHERE id = ?', (lesson['course_id'],)).fetchone()
    
    # Get student progress
    student_name = session.get('student_name', '')
    completed = False
    submission = None
    
    if student_name:
        progress = db.execute('''
            SELECT completed FROM student_progress 
            WHERE student_name = ? AND lesson_id = ?
        ''', (student_name, lesson_id)).fetchone()
        completed = progress['completed'] if progress else False
        
        # Check for submission
        submission = db.execute('''
            SELECT * FROM submissions 
            WHERE student_name = ? AND lesson_id = ?
            ORDER BY submitted_at DESC LIMIT 1
        ''', (student_name, lesson_id)).fetchone()
    
    db.close()
    return render_template('lesson.html', lesson=lesson, course=course, 
                          completed=completed, submission=submission, 
                          student_name=student_name)

@app.route('/set-student-name', methods=['POST'])
def set_student_name():
    """Set the student name in session"""
    student_name = request.form.get('student_name', '').strip()
    if student_name:
        session['student_name'] = student_name
    return redirect(request.referrer or url_for('index'))

@app.route('/mark-complete/<int:lesson_id>', methods=['POST'])
def mark_complete(lesson_id):
    """Mark a lesson as complete"""
    student_name = session.get('student_name')
    if not student_name:
        return jsonify({'error': 'Please enter your name first'}), 400
    
    db = get_db()
    try:
        db.execute('''
            INSERT INTO student_progress (student_name, lesson_id, completed, completed_at)
            VALUES (?, ?, 1, ?)
            ON CONFLICT(student_name, lesson_id) 
            DO UPDATE SET completed = 1, completed_at = ?
        ''', (student_name, lesson_id, datetime.now(), datetime.now()))
        db.commit()
        db.close()
        return jsonify({'success': True})
    except Exception as e:
        db.close()
        return jsonify({'error': str(e)}), 500

@app.route('/upload/<int:lesson_id>', methods=['POST'])
def upload_file(lesson_id):
    """Handle file upload for a lesson"""
    student_name = session.get('student_name')
    if not student_name:
        return "Please enter your name first", 400
    
    if 'file' not in request.files:
        return "No file provided", 400
    
    file = request.files['file']
    if file.filename == '':
        return "No file selected", 400
    
    if not allowed_file(file.filename):
        return "Only .blend files are allowed", 400
    
    # Create student directory using sanitized name
    # Note: For production, consider using student IDs instead of names to avoid collisions
    safe_student_name = secure_filename(student_name.replace(' ', '_'))
    student_dir = os.path.join(app.config['UPLOAD_FOLDER'], safe_student_name)
    os.makedirs(student_dir, exist_ok=True)
    
    # Save file with lesson ID in filename
    filename = secure_filename(file.filename)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    new_filename = f"lesson_{lesson_id}_{timestamp}_{filename}"
    filepath = os.path.join(student_dir, new_filename)
    file.save(filepath)
    
    # Save submission to database
    db = get_db()
    db.execute('''
        INSERT INTO submissions (student_name, lesson_id, filename, filepath)
        VALUES (?, ?, ?, ?)
    ''', (student_name, lesson_id, filename, filepath))
    db.commit()
    db.close()
    
    return redirect(url_for('lesson_view', lesson_id=lesson_id))

if __name__ == '__main__':
    # Initialize database on startup
    if not os.path.exists(DATABASE):
        init_db()
    # Debug mode controlled by environment variable for security
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(debug=debug_mode, host='0.0.0.0', port=5000)
