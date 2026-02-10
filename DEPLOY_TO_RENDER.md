# Quick Deploy to Render.com

Click the button below to deploy this Flask application to Render.com with one click:

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy)

## What Happens When You Click Deploy

1. You'll be taken to Render.com (create a free account if needed)
2. Render will read the `render.yaml` configuration file
3. Your application will be automatically:
   - Built with the correct Python environment
   - Configured with a secure SECRET_KEY
   - Deployed with Gunicorn as the production server
4. You'll get a public URL like: `https://cs-teaching-site.onrender.com`

## After Deployment

Your site will be live! The first time it loads may take a few seconds as the server starts up.

### What You Get

- ✅ Free hosting on Render's free tier
- ✅ HTTPS automatically enabled
- ✅ Auto-deploy on git push (if you connect your GitHub repo)
- ✅ Fresh database initialized with sample content

### Limitations on Free Tier

- Server spins down after 15 minutes of inactivity
- 750 hours of runtime per month (plenty for testing)
- First request after inactivity may take 30-60 seconds to wake up

## Manual Deployment to Render

If the button doesn't work, follow these steps:

1. Go to [render.com](https://render.com) and create a free account
2. Click "New +" → "Web Service"
3. Connect your GitHub repository
4. Use these settings:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`
5. Add environment variable:
   - **SECRET_KEY**: Generate using: `python -c "import os; print(os.urandom(24).hex())"`
6. Click "Create Web Service"

Your site will be deployed in a few minutes!

## Alternative Hosting Options

See [DEPLOYMENT.md](DEPLOYMENT.md) for other free hosting options including:
- PythonAnywhere
- Railway.app  
- Fly.io
- Docker deployment
