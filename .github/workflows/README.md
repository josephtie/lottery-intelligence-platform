# CI/CD Pipelines

This directory contains GitHub Actions workflows for continuous integration and deployment.

## Workflows

### CI Pipeline (`.github/workflows/ci.yml`)

Runs on every push and pull request to main/master/develop/feature branches.

**Jobs:**

1. **Test** - Runs all tests with PostgreSQL
   - Unit tests
   - Integration tests
   - Agent system tests (persistence + anti-lookahead)
   - Coverage reporting to Codecov

2. **Lint** - Code quality checks
   - Ruff linter
   - Ruff formatter check
   - MyPy type checking

3. **Frontend Build** - Frontend validation
   - Install dependencies
   - Run linter
   - Build production bundle
   - Upload build artifacts

4. **Migration Check** - Database schema validation
   - Apply all migrations
   - Verify agent system tables exist
   - Check triggers are in place

5. **Security Scan** - Vulnerability scanning
   - Trivy filesystem scan
   - Upload results to GitHub Security

### CD Pipeline (`.github/workflows/cd.yml`)

Runs on push to main/master branches after CI passes.

**Jobs:**

1. **Build and Push** - Docker image deployment
   - Build backend Docker image
   - Build frontend Docker image
   - Push to Docker Hub
   - Use GitHub Actions cache for faster builds

2. **Deploy** - Production deployment
   - Deploy via SSH to production server
   - Pull latest images
   - Restart services with docker-compose
   - Run database migrations
   - Health check
   - Slack notification

3. **Rollback** - Automatic rollback on failure
   - Triggered if deployment fails
   - Rollback to previous version via SSH
   - Slack notification

## Required Secrets

Configure these secrets in your GitHub repository settings:

### CI Secrets
- `CODECOV_TOKEN` - For coverage reporting (optional)

### CD Secrets
- `DOCKER_USERNAME` - Docker Hub username
- `DOCKER_PASSWORD` - Docker Hub password/token
- `DEPLOY_HOST` - Production server hostname
- `DEPLOY_USER` - SSH username for deployment
- `DEPLOY_SSH_KEY` - SSH private key for deployment
- `DEPLOY_PORT` - SSH port (default: 22)
- `DEPLOY_URL` - Production URL for health checks
- `SLACK_WEBHOOK` - Slack webhook for notifications (optional)

## Setting Up Secrets

1. Go to your GitHub repository
2. Navigate to Settings → Secrets and variables → Actions
3. Click "New repository secret"
4. Add each secret from the list above

## Local Testing

### Test CI workflow locally

```bash
# Install act (GitHub Actions runner for local testing)
brew install act  # macOS
# or visit https://github.com/nektos/act for other platforms

# Run the test job
act push -j test

# Run all jobs
act push
```

### Test PostgreSQL migrations locally

```bash
# Start PostgreSQL
docker-compose up -d postgres

# Apply migrations
python -c "
import psycopg
from lottery_intelligence_platform.migrations import apply_migrations

dsn = 'host=localhost port=5432 dbname=lottery_platform user=directus'
conn = psycopg.connect(dsn, autocommit=True)
migrations = apply_migrations(conn)
print(f'Applied {len(migrations)} migrations')
conn.close()
"
```

## Deployment Process

1. Developer pushes to `main` or `master` branch
2. CI pipeline runs automatically:
   - Tests validate code quality
   - Lint checks pass
   - Frontend builds successfully
   - Migrations apply cleanly
   - Security scan passes
3. CD pipeline triggers after CI:
   - Docker images built and pushed
   - Deployed to production server
   - Migrations applied
   - Health check validates deployment
   - Slack notification sent
4. If deployment fails:
   - Automatic rollback triggered
   - Previous version restored
   - Alert sent via Slack

## Monitoring

- Check GitHub Actions tab for pipeline status
- Monitor Slack notifications for deployment updates
- Review coverage reports on Codecov
- Check security alerts in GitHub Security tab

## Troubleshooting

### CI fails on tests
- Check test logs in GitHub Actions
- Run tests locally with `pytest tests/`
- Verify PostgreSQL connection in CI environment

### CD fails on deployment
- Check SSH key permissions
- Verify Docker Hub credentials
- Check production server connectivity
- Review docker-compose logs on server

### Migration check fails
- Verify migration files are in correct directory
- Check PostgreSQL version compatibility
- Review migration SQL syntax

### Security scan fails
- Review Trivy scan results
- Update vulnerable dependencies
- Check for exposed secrets in code

## Customization

### Adding new test suites
Add to the `test` job in `ci.yml`:

```yaml
- name: Run custom tests
  env:
    LOTTERY_TEST_DATABASE_URL: postgres://test_user:test_password@localhost:5432/test_lottery_platform
  run: |
    pytest tests/custom/ -v --tb=short
```

### Adding deployment environments
Add new environment in repository settings and update `cd.yml`:

```yaml
deploy-staging:
  name: Deploy to Staging
  environment: staging
  # ... steps
```

### Modifying Docker build process
Update build steps in `cd.yml` to customize:
- Build arguments
- Multi-stage builds
- Platform-specific builds
