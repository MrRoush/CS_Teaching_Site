# CS Teaching Site

A web application for organizing computer science lessons and collecting student submissions. Features a playlist-based learning system with progress tracking and file upload capabilities.

## Features

- 📚 **Course Management**: Organize lessons into courses
- 🎬 **Video Playlist**: Watch tutorial videos in sequence
- ✅ **Progress Tracking**: Mark lessons as complete and track your progress
- 📤 **File Submissions**: Upload Blender files (.blend) for grading
- 👤 **Student Sessions**: Simple name-based session management
- 🎨 **Customizable**: Easy to customize for different courses

## Quick Start

### Prerequisites

- Python 3.8 or higher
- pip (Python package manager)

### Installation

1. Clone the repository:
```bash
git clone https://github.com/MrRoush/CS_Teaching_Site.git
cd CS_Teaching_Site
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run the application:
```bash
python app.py
```

4. Open your browser and navigate to:
```
http://localhost:5000
```

## Usage

### For Students

1. **Enter Your Name**: Click on the name field in the header and enter your name to start tracking progress
2. **Browse Courses**: View available courses on the home page
3. **Watch Lessons**: Click on a course to see the playlist of lessons
4. **Complete Lessons**: Watch the tutorial video and click "Mark as Complete" when done
5. **Submit Work**: Upload your Blender file (.blend) at the end of each lesson

### For Instructors

The application comes pre-configured with a Computer Animation course. To customize:

1. **Add New Courses**: Modify the `init_db()` function in `app.py` to add courses
2. **Add Lessons**: Insert lessons with YouTube video URLs in the database
3. **Change File Types**: Modify `ALLOWED_EXTENSIONS` in `app.py` for different file types

## Project Structure

```
CS_Teaching_Site/
├── app.py                 # Main Flask application
├── requirements.txt       # Python dependencies
├── templates/            # HTML templates
│   ├── base.html         # Base template
│   ├── index.html        # Home page
│   ├── course.html       # Course view
│   └── lesson.html       # Lesson view with video and upload
├── static/
│   └── css/
│       └── style.css     # Styling
├── uploads/              # Student file uploads (created on first run)
└── cs_teaching.db        # SQLite database (created on first run)
```

## Customization

### Adding a New Course

Edit the `init_db()` function in `app.py`:

```python
cursor = db.execute('''
    INSERT INTO courses (name, description) 
    VALUES (?, ?)
''', ('Your Course Name', 'Course description'))
```

### Adding Lessons

```python
lessons = [
    ('Lesson Title', 'Lesson Description', 'YouTube Embed URL', order_number),
    # Add more lessons...
]
```

### Changing Allowed File Types

Modify the `ALLOWED_EXTENSIONS` in `app.py`:

```python
app.config['ALLOWED_EXTENSIONS'] = {'blend', 'py', 'zip'}
```

## Database Schema

- **courses**: Course information
- **lessons**: Individual lessons with video URLs
- **student_progress**: Tracks lesson completion per student
- **submissions**: Stores uploaded file information

## Technologies Used

- **Backend**: Flask (Python web framework)
- **Database**: SQLite
- **Frontend**: HTML5, CSS3, JavaScript
- **Video**: YouTube embedded videos

## License

This project is open source and available for educational purposes.

## Support

For issues or questions, please open an issue on GitHub.