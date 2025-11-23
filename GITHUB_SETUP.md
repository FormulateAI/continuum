# GitHub Setup Instructions

## Step 1: Create Repository on GitHub

1. Go to https://github.com/FormulateAI
2. Click "New repository"
3. Repository name: `continuum`
4. Description: "Universal context layer for AI agents across IDEs"
5. **Public** repository
6. **Do NOT** initialize with README, .gitignore, or license (we already have these)
7. Click "Create repository"

## Step 2: Push to GitHub

After creating the repository, run these commands:

```bash
cd /Users/krishna/Workspace/Antigravity/continuum

# Add the remote
git remote add origin https://github.com/FormulateAI/continuum.git

# Push to GitHub
git push -u origin master
```

## Step 3: Update PyPI Links

After pushing, update the GitHub URLs in `pyproject.toml`:
- Issues: https://github.com/FormulateAI/continuum/issues
- Source: https://github.com/FormulateAI/continuum

Then publish a new version (0.1.2) to PyPI with the updated links.

## Alternative: Use SSH

If you prefer SSH:
```bash
git remote add origin git@github.com:FormulateAI/continuum.git
git push -u origin master
```
