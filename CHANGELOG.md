# Changelog

All notable changes to the Ordinaut project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial release of Ordinaut - AI agent coordination system
- Complete FastAPI REST API for task management
- APScheduler integration with PostgreSQL job store
- SKIP LOCKED worker system for distributed job processing
- RFC-5545 RRULE processing with timezone support
- Comprehensive monitoring with Prometheus and Grafana
- Docker containerization with multi-service architecture
- Production-ready security with JWT authentication
- Complete test coverage with unit, integration, and load tests
- Operational runbooks and disaster recovery procedures

### Changed
- N/A (Initial release)

### Deprecated
- N/A (Initial release)

### Removed
- N/A (Initial release)

### Fixed
- N/A (Initial release)

### Security
- JWT authentication with scope-based authorization
- Input validation at API boundaries
- Audit logging for all operations
- Rate limiting and DoS protection

---

## Release Notes

This changelog is automatically maintained by semantic-release based on conventional commits.

### Commit Message Format

This project follows the [Conventional Commits](https://conventionalcommits.org/) specification:

```
type(scope): description

[optional body]

[optional footer(s)]
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes
- `refactor`: Code refactoring
- `test`: Test changes
- `chore`: Build process or auxiliary tool changes
- `perf`: Performance improvements

**Examples:**
```
feat(api): add task snoozing functionality
fix(scheduler): resolve DST transition issues
docs(readme): update installation instructions
perf(worker): optimize SKIP LOCKED query performance
```

### Breaking Changes

Breaking changes should be indicated by placing `BREAKING CHANGE:` in the footer or by appending `!` after the type:

```
feat!: remove support for legacy API endpoints

BREAKING CHANGE: Legacy API endpoints have been removed. Migrate to v2 API.
```
