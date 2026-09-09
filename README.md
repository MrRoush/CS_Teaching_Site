# CS Teaching Site

A reset prototype for a computer science teaching platform focused on privacy-aware sign-in, reusable course modules, Godot-based game creation, project submission, and teacher grading workflows.

## What this version delivers

This scaffold replaces the original lesson playlist starter with a more relevant structure for the new site direction:

- Demo sign-in flow that separates teacher and student experiences while documenting the path to Google Workspace authentication
- Teacher dashboard for creating courses, assembling modules, and reviewing project submissions
- Reusable module library with support for lesson links, slide decks, quiz prompts, project briefs, and optional Godot editor access
- Student dashboard for opening assigned modules, launching the Godot 4.7.2 web editor, and submitting project links for review
- Seeded SQLite demo data so the app can be deployed and explored immediately

## Feasibility analysis

### 1. Authentication and student privacy

A school-safe sign-in system is feasible and should use Google Workspace OAuth 2.0 / OpenID Connect in production. That approach can limit sign-in to the school domain, reduce password handling in this app, and align better with FERPA-style privacy expectations than building a custom credential store.

**Current scaffold status:** this repository ships with a demo-only session sign-in so work can begin before Google OAuth credentials and district approvals are available.

**Production follow-up:** integrate a Google auth library, enforce domain restrictions, store only the minimum profile fields needed for authorization, and define retention/deletion policies for student data.

### 2. Teacher course creation and modular curriculum

This is feasible with a reusable module-template data model. Teachers can assemble a course from saved module templates, remove unneeded units, and create custom modules without changing application code.

**Current scaffold status:** implemented with `course_offerings`, `module_templates`, and `course_modules` tables plus teacher-facing forms.

### 3. Modules with lesson content, quizzes, and projects

This is feasible with a module record that stores:

- a lesson resource URL
- an optional slide deck URL
- a quiz prompt or quick-check entry
- a project brief and submission expectation

**Current scaffold status:** implemented as teacher-authored module templates and student-facing module detail pages.

### 4. Godot integration

Launching the Godot 4.7.2 online editor is feasible today by linking directly to the official web editor. Full embedded workflows are possible, but browser restrictions, storage persistence, and submission/export expectations must be defined before relying on iframe-only use.

**Current scaffold status:** modules can opt into a Godot editor launch link and an embedded preview panel.

### 5. Teacher grading and classroom dashboards

This is feasible with per-module project submission tracking and teacher review states.

**Current scaffold status:** implemented with submission status, score, and feedback fields that appear on teacher and student dashboards.

## Clarifying questions

These questions should guide the next iteration:

1. What Google Workspace domain and admin approvals will be available for OAuth setup?
2. Should student enrollment come from manual invites, roster import, Google Classroom sync, or another LMS?
3. Do projects need file uploads, or are repository/build/Drive links sufficient for the first release?
4. Should quizzes be auto-graded multiple choice, teacher-reviewed short answer, or both?
5. Where should Godot project files live long term: site storage, GitHub, Google Drive, or cloud object storage?
6. Do teachers need rubrics, standards alignment, or CSV grade export in phase one?

## User implementation steps

### Local setup

1. Clone the repository.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the Flask app:
   ```bash
   python app.py
   ```
4. Open `http://localhost:5000`.
5. Use the **Demo Sign-In** page to choose a teacher or student account.

### Demo accounts

- **Teacher:** `avery.teacher@school.demo`
- **Student:** `jordan.student@school.demo`
- **Student:** `casey.student@school.demo`

### Teacher walkthrough

1. Sign in as the teacher account.
2. Create a new course shell from the dashboard.
3. Add existing module templates or create a new reusable module.
4. Open a course to remove modules or review student submissions.
5. Score work and leave feedback from the submission review forms.

### Student walkthrough

1. Sign in as a student account.
2. Open the student dashboard.
3. Enter a module and review the lesson content, quick-check prompt, and project brief.
4. Launch the Godot editor if the module enables it.
5. Submit a repository, hosted build, or shared project link for review.

## Suggested hosting options

### Best fit for early deployment

- **Render**: simple Flask deployment, easy environment variable setup, good for prototypes
- **Railway**: quick app deployment with managed service workflows
- **Fly.io**: good if you want more control and are comfortable with CLI deployment

### Production-oriented considerations

- Move from SQLite to PostgreSQL for multi-user reliability
- Use managed session storage if scaling beyond a simple prototype
- Store submissions in cloud storage instead of the application filesystem if file uploads are added
- Add HTTPS, secure cookies, backup policies, and audit logging before real classroom use

## Project structure

```text
CS_Teaching_Site/
├── app.py
├── requirements.txt
├── static/
│   └── css/
│       └── style.css
├── templates/
│   ├── base.html
│   ├── index.html
│   ├── module_detail.html
│   ├── sign_in.html
│   ├── student_dashboard.html
│   ├── teacher_course.html
│   └── teacher_dashboard.html
└── cs_teaching.db   # created on first run
```

## Additional considerations for future development

- Replace demo sign-in with Google Workspace OAuth and role-based access control
- Add roster management, invite flows, or LMS sync
- Support rubric-based grading and grade export
- Add quiz authoring, auto-grading, and analytics
- Decide whether Godot projects should be uploaded, version-controlled, or saved through an external storage provider
- Add automated tests, migration tooling, and environment-based configuration for production
- Add privacy policy language, consent notices, and district-specific data governance requirements
