# Ordinaut Documentation

This directory contains the complete documentation for Ordinaut, built with MkDocs and Material theme.

## Features

### 🔍 Interactive Mermaid Diagrams
All Mermaid diagrams in the documentation include **zoom and pan controls** for better user experience:

- **Zoom In/Out**: Use mouse wheel or pinch gestures
- **Pan**: Click and drag to move around large diagrams
- **Reset**: Double-click to reset to original view

This is particularly useful for complex architecture diagrams like the task execution triggers in the Core Concepts guide.

### 🌐 Multi-language Support
Documentation is available in three languages:
- **English** (default)
- **Romanian** (Română) 
- **Russian** (Русский)

## Building Documentation

### Prerequisites
Install documentation dependencies:
```bash
pip install -r requirements-docs.txt
```

### Local Development
```bash
# Serve documentation locally with live reload
mkdocs serve

# Build static documentation
mkdocs build

# Deploy to GitHub Pages
mkdocs gh-deploy
```

### Dependencies
- `mkdocs-material`: Material Design theme
- `mkdocs-static-i18n`: Multi-language support
- `mkdocs-panzoom-plugin`: Interactive zoom/pan for diagrams
- `pymdown-extensions`: Enhanced Markdown features

## Technical Implementation

The zoom/pan functionality is implemented using the `mkdocs-panzoom-plugin`, which:
- Automatically detects Mermaid diagrams (`.mermaid` selector)
- Adds interactive controls without modifying source content
- Works seamlessly with Material theme's shadow DOM implementation
- Provides smooth zoom/pan experience on both desktop and mobile

## Documentation Structure

```
docs/
├── getting-started/     # Installation and quick start
├── guides/             # Core concepts and tutorials
├── api/               # API reference documentation
├── operations/        # Deployment and monitoring
├── project/          # Project status and reports
└── assets/           # Images, logos, and static files
```

For more information about Ordinaut, visit: https://github.com/yoda-digital/ordinaut