# Ordinaut - Assets Directory

## Purpose and Role

The `assets/` directory contains visual and static assets for the Ordinaut project, including logos, icons, diagrams, and other multimedia resources used in documentation, user interfaces, and branding.

## Directory Contents

### Visual Assets
- **`ordinaut_logo.png`** - Primary project logo and branding asset
- **Future assets may include:**
  - Architecture diagrams and flowcharts
  - API documentation illustrations
  - Dashboard mockups and screenshots
  - Icon sets for different tool categories
  - Video demonstrations and tutorials

### Asset Categories

#### 1. Branding Assets
```
assets/branding/
├── logos/
│   ├── ordinaut_logo.png          # Primary logo
│   ├── ordinaut_logo_dark.png     # Dark theme variant
│   └── ordinaut_logo_small.png    # Icon/favicon size
├── colors/
│   └── brand_palette.json         # Official color scheme
└── fonts/
    └── typography_guide.md        # Font specifications
```

#### 2. Documentation Assets
```
assets/docs/
├── architecture/
│   ├── system_overview.svg        # High-level architecture diagram
│   ├── data_flow.svg             # Pipeline execution flow
│   ├── scheduling_flow.svg       # APScheduler workflow
│   └── security_model.svg        # Authentication and authorization
├── api/
│   ├── endpoint_examples.png     # API documentation screenshots
│   └── postman_collection.json  # API testing collection
└── tutorials/
    ├── getting_started.gif       # Animated setup guide
    └── pipeline_creation.mp4     # Video tutorial
```

#### 3. Dashboard Assets
```
assets/ui/
├── icons/
│   ├── task_status/
│   │   ├── running.svg
│   │   ├── completed.svg
│   │   ├── failed.svg
│   │   └── pending.svg
│   └── tools/
│       ├── telegram.svg
│       ├── calendar.svg
│       ├── weather.svg
│       └── email.svg
└── screenshots/
    ├── dashboard_main.png
    ├── task_creation.png
    └── run_history.png
```

## Asset Management Standards

### File Naming Conventions
- Use lowercase with underscores: `system_diagram.svg`
- Include dimensions for raster images: `logo_256x256.png`
- Version control with semantic numbering: `api_flow_v2.svg`
- Use descriptive prefixes by category: `icon_`, `diagram_`, `screenshot_`

### Format Standards
- **Logos/Icons**: SVG preferred for scalability, PNG for raster needs
- **Screenshots**: PNG with consistent resolution (1920x1080 recommended)
- **Diagrams**: SVG for technical diagrams, PNG for complex illustrations
- **Videos**: MP4 with H.264 encoding, maximum 10MB file size

### Resolution Guidelines
| Asset Type | Recommended Size | Format | Use Case |
|------------|------------------|--------|----------|
| Primary Logo | 512x512px | PNG/SVG | Documentation headers |
| Favicon | 32x32px | PNG/ICO | Browser tabs |
| Screenshots | 1920x1080px | PNG | Documentation |
| Icons | 64x64px | SVG | UI elements |
| Diagrams | Scalable | SVG | Technical docs |

## Integration Patterns

### Documentation Integration
```markdown
# Example usage in documentation
![System Architecture](../assets/docs/architecture/system_overview.svg)

<img src="../assets/branding/logos/ordinaut_logo.png" alt="Ordinaut" width="200">
```

### API Documentation
```yaml
# OpenAPI specification with assets
info:
  title: Ordinaut API
  description: |
    ![API Architecture](./assets/docs/api/architecture.svg)
    
    The Ordinaut provides...
  x-logo:
    url: './assets/branding/logos/ordinaut_logo.png'
    altText: 'Ordinaut Logo'
```

### Web Dashboard
```html
<!-- Example HTML integration -->
<link rel="icon" type="image/png" href="/assets/branding/logos/favicon.png">
<img src="/assets/ui/icons/task_status/running.svg" alt="Task Running" class="status-icon">
```

## Asset Creation Guidelines

### Technical Diagrams
- Use consistent color scheme matching brand palette
- Include legend and labels for complex diagrams
- Export in both SVG and PNG formats
- Maintain source files (Figma, Sketch, etc.) for future edits

### Screenshots
- Use consistent browser/application theming
- Include realistic but anonymized data
- Highlight important UI elements with callouts
- Maintain consistent window sizing and resolution

### Icons
- Follow consistent design language across icon set
- Use scalable vector format (SVG) when possible
- Include accessibility attributes (alt text, ARIA labels)
- Test at multiple sizes (16px to 512px)

## Version Control and Updates

### Asset Versioning
```bash
# Track asset changes with descriptive commits
git add assets/docs/architecture/system_overview_v2.svg
git commit -m "Update system architecture diagram with MCP integration"

# Use Git LFS for large binary assets
git lfs track "*.mp4" "*.gif" "*.psd"
```

### Update Process
1. **Create/Update Asset** - Using appropriate design tools
2. **Optimize File Size** - Compress images, optimize SVGs
3. **Test Integration** - Verify display in all intended contexts  
4. **Update References** - Check all documentation and code references
5. **Commit Changes** - Use descriptive commit messages

### Asset Maintenance
- **Quarterly Review** - Check for broken links and outdated screenshots
- **Brand Consistency** - Ensure all assets follow current brand guidelines
- **Performance Monitoring** - Monitor load times for web-embedded assets
- **Accessibility Audit** - Verify alt text and contrast ratios

## Best Practices

### File Organization
- Group related assets in subdirectories by purpose
- Use consistent directory structure across asset types
- Maintain index files listing available assets
- Include README files for complex asset collections

### Performance Optimization
- Compress images without quality loss (TinyPNG, ImageOptim)
- Use appropriate formats (WebP for web, PNG for print)
- Implement responsive image loading for documentation
- Monitor total asset directory size

### Accessibility
- Provide alt text for all images used in documentation
- Ensure sufficient color contrast in diagrams
- Include text descriptions for complex visual information
- Test assets with screen readers

## Future Enhancements

### Planned Asset Categories
- **Interactive Diagrams** - Zoomable architecture overviews
- **Video Tutorials** - Step-by-step feature demonstrations  
- **3D Visualizations** - Pipeline execution flow animations
- **Localized Assets** - Multi-language versions of key diagrams

### Asset Pipeline Automation
```yaml
# Automated asset optimization workflow
name: Optimize Assets
on:
  push:
    paths: ['assets/**']
jobs:
  optimize:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Optimize Images
        run: |
          find assets/ -name "*.png" -exec optipng {} \;
          find assets/ -name "*.svg" -exec svgo {} \;
```

### Integration Goals
- **CDN Distribution** - Serve assets via content delivery network
- **Responsive Loading** - Adaptive asset delivery based on device
- **Asset Analytics** - Track usage and performance metrics
- **Dynamic Generation** - Programmatically create diagrams from code

---

*The assets directory serves as the visual foundation for the Ordinaut project, ensuring consistent branding and clear communication through carefully crafted visual elements.*