# Deployment Guide for CS Teaching Site

## Important Note about GitHub Pages

**GitHub Pages does not support Flask applications** because it only serves static HTML, CSS, and JavaScript files. Since this is a Python Flask application with a database backend, you'll need to use one of the alternative hosting solutions below.

## Free Hosting Options for Flask Applications

### Option 1: Render.com (Recommended - Easiest)

[Render](https://render.com) offers free hosting for web applications with automatic deployments from GitHub.

**Steps:**

1. Create a free account at [render.com](https://render.com)
2. Click "New +" and select "Web Service"
3. Connect your GitHub repository
4. Configure the service:
   - **Name**: cs-teaching-site (or your preferred name)
   - **Environment**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`
   - **Plan**: Free
5. Add environment variable:
   - `SECRET_KEY`: Generate a random string (use: `python -c "import os; print(os.urandom(24).hex())"`)
6. Click "Create Web Service"

**Note**: You'll need to add `gunicorn` to your requirements.txt (see below).

Your site will be available at: `https://cs-teaching-site.onrender.com`

### Option 2: PythonAnywhere

[PythonAnywhere](https://www.pythonanywhere.com) offers free hosting with limited resources.

**Steps:**

1. Create a free account at [pythonanywhere.com](https://www.pythonanywhere.com)
2. Go to "Web" tab and click "Add a new web app"
3. Choose "Flask" and Python 3.x
4. Follow the setup wizard
5. Upload your files or clone from GitHub
6. Configure the WSGI file to point to your app
7. Reload the web app

Your site will be available at: `https://yourusername.pythonanywhere.com`

### Option 3: Railway.app

[Railway](https://railway.app) offers easy deployment with GitHub integration.

**Steps:**

1. Create account at [railway.app](https://railway.app)
2. Create new project from GitHub repo
3. Railway will auto-detect Flask and deploy
4. Set environment variables in the Railway dashboard

### Option 4: Fly.io

[Fly.io](https://fly.io) offers free tier for small applications.

**Steps:**

1. Install Fly CLI: `curl -L https://fly.io/install.sh | sh`
2. Login: `fly auth login`
3. Launch app: `fly launch` (follow the prompts)
4. Deploy: `fly deploy`

## Local Development

To run the application locally for testing:

```bash
# Clone the repository
git clone https://github.com/MrRoush/CS_Teaching_Site.git
cd CS_Teaching_Site

# Install dependencies
pip install -r requirements.txt

# Run the application
python app.py
```

Visit `http://localhost:5000` in your browser.

## Docker Deployment

If you prefer Docker, use the included Dockerfile:

```bash
# Build the image
docker build -t cs-teaching-site .

# Run the container
docker run -p 5000:5000 cs-teaching-site
```

Visit `http://localhost:5000` in your browser.

## Production Considerations

Before deploying to production:

1. **Set SECRET_KEY**: Use a strong, random secret key
   ```bash
   export SECRET_KEY=$(python -c "import os; print(os.urandom(24).hex())")
   ```

2. **Database**: Consider upgrading from SQLite to PostgreSQL for production
   - SQLite works fine for small deployments
   - For multiple concurrent users, use PostgreSQL or MySQL

3. **File Storage**: For production, consider using cloud storage (AWS S3, etc.) instead of local file uploads

4. **HTTPS**: Most hosting platforms provide free SSL certificates

5. **Environment Variables**: Never commit sensitive data to Git
   - Use environment variables for secrets
   - Add `.env` to `.gitignore`

## Troubleshooting

### Port Issues
If port 5000 is in use, change it in `app.py`:
```python
app.run(debug=debug_mode, host='0.0.0.0', port=8080)  # Changed from 5000
```

### Database Not Created
The database is created automatically on first run. If issues occur:
```bash
python -c "from app import init_db; init_db()"
```

### Permission Errors
Make sure the `uploads` directory is writable:
```bash
chmod 755 uploads
```

## Getting Help

- Check the [main README](README.md) for basic setup
- Open an issue on GitHub for bugs
- Review Flask documentation at [flask.palletsprojects.com](https://flask.palletsprojects.com)
