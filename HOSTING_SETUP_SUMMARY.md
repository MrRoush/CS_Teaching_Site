# GitHub Hosting Setup - Summary

## Important Information

Your CS Teaching Site is a **Flask web application** (Python backend with database), which means it **cannot be hosted on GitHub Pages**. GitHub Pages only supports static HTML, CSS, and JavaScript files.

## What I've Added

I've set up multiple deployment options for you to host this application on free platforms:

### 1. Files Created

- **DEPLOYMENT.md** - Comprehensive guide for all deployment options
- **DEPLOY_TO_RENDER.md** - Quick start guide for Render.com (easiest option)
- **Dockerfile** - For Docker-based deployment
- **.dockerignore** - Docker build optimization
- **render.yaml** - One-click deployment configuration for Render
- **.github/workflows/test.yml** - Automated testing workflow
- **requirements.txt** - Updated with gunicorn for production

### 2. Files Updated

- **README.md** - Added prominent deployment instructions at the top

## How to Deploy (Recommended Method)

### Option A: One-Click Deploy to Render.com (Easiest)

1. Open the repository on GitHub
2. Click the "Deploy to Render" button in the README
3. Sign up for a free Render account (if needed)
4. Click "Create Web Service"
5. Your site will be live at: `https://your-service-name.onrender.com`

**Time**: 5 minutes  
**Cost**: Free  
**Features**: Automatic HTTPS, auto-deploy on git push

### Option B: Manual Deployment to Render

1. Go to [render.com](https://render.com) and create a free account
2. Click "New +" → "Web Service"
3. Connect your GitHub repository: `MrRoush/CS_Teaching_Site`
4. Configure:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`
   - **Environment Variable**: Add `SECRET_KEY` with a random value
5. Click "Create Web Service"

### Option C: Other Free Platforms

See [DEPLOYMENT.md](DEPLOYMENT.md) for detailed instructions on:
- **PythonAnywhere** - Traditional Python hosting
- **Railway.app** - Modern, GitHub-integrated hosting
- **Fly.io** - CLI-based deployment

### Option D: Docker (Local or Any Server)

```bash
# Build the Docker image
docker build -t cs-teaching-site .

# Run the container
docker run -p 5000:5000 cs-teaching-site

# Access at http://localhost:5000
```

## What Won't Work

❌ **GitHub Pages** - Cannot run Python/Flask applications  
❌ **Static Site Hosting** - Requires a backend server and database  

## Why Not GitHub Pages?

GitHub Pages is designed for static websites (HTML/CSS/JS only). Your application:
- Uses Python Flask backend
- Has SQLite database
- Handles file uploads
- Manages sessions
- Requires a web server to run

All of these features require a server environment that GitHub Pages doesn't provide.

## Next Steps

1. **For Quick Testing**: Use Render.com (free tier, very easy)
2. **For Production**: Consider Render.com, Railway, or a VPS
3. **For Local Development**: Run `python app.py` (already works)

## Testing the Application

The GitHub Actions workflow (`.github/workflows/test.yml`) will automatically:
- Install dependencies
- Initialize the database
- Verify the application starts correctly
- Run on every push to main/master branch

## Need Help?

- Check [DEPLOYMENT.md](DEPLOYMENT.md) for detailed guides
- Check [DEPLOY_TO_RENDER.md](DEPLOY_TO_RENDER.md) for Render-specific help
- The application is ready to deploy - no code changes needed!

## Free Tier Limitations

Most free hosting platforms have some limitations:
- **Render**: Server sleeps after 15 minutes of inactivity (wakes up in ~30 seconds)
- **PythonAnywhere**: Limited CPU seconds per day
- **Railway**: 500 hours per month, $5 credit

For a testing/debugging environment, these free tiers are perfect!
