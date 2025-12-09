#!/bin/bash

# Ask for the repository URL
echo "Please paste your GitHub Repository URL (e.g., https://github.com/username/nq-momentum-scalper.git):"
read REPO_URL

# Check if URL is provided
if [ -z "$REPO_URL" ]; then
    echo "Error: No URL provided."
    exit 1
fi

echo "Initializing Git..."
git init

# Configure .gitignore
echo "venv/" > .gitignore
echo "__pycache__/" >> .gitignore
echo ".DS_Store" >> .gitignore

# Add all files
echo "Adding files..."
git add .

# Commit
echo "Committing files..."
git commit -m "Initial commit of NQ Momentum Scalper Strategy"

# Rename branch to main
git branch -M main

# Add remote
echo "Adding remote origin..."
git remote remove origin 2>/dev/null # Remove if exists
git remote add origin "$REPO_URL"

# Push
echo "Pushing to GitHub..."
git push -u origin main

echo "Done! If requested, enter your GitHub username and password/token."
