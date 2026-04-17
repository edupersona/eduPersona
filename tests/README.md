# edupersona Testing Guide

This directory contains the test suite for edupersona using pytest with async support and NiceGUI testing fixtures.

## Test Structure

```
tests/
├── conftest.py           # Shared fixtures and test configuration
├── test_storage.py       # Storage layer and Tortoise ORM tests
├── test_api.py          # FastAPI REST API endpoint tests
├── test_ui_guest.py     # Guest workflow UI tests
├── test_ui_admin.py     # Admin interface UI tests
├── test_integration.py  # End-to-end integration tests
└── README.md           # This file
```

## Setup

Install test dependencies:

```bash
pip install -r requirements.txt
```

The following packages are required:
- `pytest` - Test framework
- `pytest-asyncio` - Async test support
- `pytest-cov` - Coverage reporting
- `nicegui` (includes testing plugin)
- `httpx` - Async HTTP client for API tests

## Running Tests

### Run all tests
```bash
pytest
```

### Run specific test file
```bash
pytest tests/test_storage.py
pytest tests/test_api.py
```

### Run tests by marker
```bash
# Run only API tests
pytest -m api

# Run only UI tests
pytest -m ui

# Run only integration tests
pytest -m integration

# Skip slow tests
pytest -m "not slow"
```

### Run with coverage
```bash
pytest --cov=. --cov-report=html
```

View coverage report in `htmlcov/index.html`

### Verbose output
```bash
pytest -v
pytest -vv  # Extra verbose
```

## Test Categories

### Storage Tests (`test_storage.py`)
Tests the Tortoise ORM models and storage layer functions:
- Creating guests, groups, and invitations
- Updating guest information from OIDC
- Group assignment and revocation
- Multitenancy isolation
- Foreign key relationships and join queries

**Key patterns tested:**
- FK field naming (`guest_id` in DB vs `guest` in model)
- Join fields with `__` syntax
- Datetime string formatting for ng_loba stores

### API Tests (`test_api.py`)
Tests FastAPI REST endpoints:
- `GET /api/groups`
- `GET /api/invitations`
- `POST /api/invitations`
- `POST /api/invite_roles` (SURF API emulation)

**Key patterns tested:**
- Request validation
- Error handling
- Response formats
- Tenant isolation via Host header

### UI Tests (`test_ui_guest.py`, `test_ui_admin.py`)
Tests NiceGUI user interface using the `user` fixture:
- Page loads and content verification
- Guest invitation acceptance workflow
- Admin authentication requirements

**Benefits of `user` fixture:**
- Fast execution (no real browser)
- Simulated user interactions
- Content assertions with `should_see()`

### Integration Tests (`test_integration.py`)
Tests multi-component workflows:
- Full invitation lifecycle (create → accept → verify)
- API to storage integration
- SURF API to regular API integration
- Complete tenant isolation across all layers

## Fixtures

### Database Fixtures
- `reset_database` - Auto-resets in-memory SQLite before each test
- `test_tenant` - Provides default test tenant ("hvh")

### Sample Data Fixtures
- `sample_guest` - Creates a test guest
- `sample_group` - Creates a test group
- `sample_invitation` - Creates a test invitation

### Client Fixtures
- `api_client` - Async HTTP client with tenant headers

### Mock Fixtures
- `mock_oidc_userinfo` - Mock OIDC user info response
- `mock_oidc_id_token` - Mock ID token claims
- `mock_oidc_token_data` - Mock token response
- `mock_scim_client` - Mock SCIM client (avoids external calls)
- `mock_smtp` - Mock email sending

## Test Markers

Tests are marked for easy filtering:

- `@pytest.mark.api` - API endpoint tests
- `@pytest.mark.ui` - UI tests
- `@pytest.mark.integration` - Integration tests
- `@pytest.mark.slow` - Slow-running tests

## Writing New Tests

### Basic async test
```python
async def test_my_feature(test_tenant):
    from services.storage.storage import get_guest_store
    
    guest_store = get_guest_store(test_tenant)
    guest = await guest_store.create_item({
        "tenant": test_tenant,
        "user_id": "test@example.com",
        "display_name": "Test User"
    })
    
    assert guest["user_id"] == "test@example.com"
```

### API test
```python
@pytest.mark.api
async def test_my_endpoint(api_client):
    response = await api_client.get("/api/my-endpoint")
    
    assert response.status_code == 200
    data = response.json()
    assert "expected_field" in data
```

### UI test
```python
@pytest.mark.ui
async def test_my_page(user: User):
    await user.open('/my-page')
    
    await user.should_see('Expected Content')
    user.find('Button Text').click()
    await user.should_see('Result')
```

## Current Limitations

### OIDC Mocking
Full OIDC authentication flows are not yet mocked. Tests that require authentication are placeholders. To add OIDC mocking:

1. Create fixture that patches OIDC protocol functions
2. Return mock userinfo, tokens, and claims
3. Set up mock session in `app.storage.user`

### SCIM Mocking
SCIM client mocking is defined but not fully integrated. To complete:

1. Patch SCIM client creation in storage layer
2. Verify observer pattern calls
3. Test provisioning and deprovisioning flows

### Browser-Based Tests
Currently using `user` fixture (simulated). For browser-specific features:

1. Switch to `screen` fixture in pytest.ini
2. Install Selenium and browser drivers
3. Tests will run slower but with real browser

## Best Practices

1. **Use in-memory database** - Fast, isolated tests
2. **Reset state between tests** - `reset_database` fixture ensures clean slate
3. **Test one thing** - Each test should verify one behavior
4. **Use descriptive names** - Test names explain what they verify
5. **Mark slow tests** - Use `@pytest.mark.slow` for long-running tests
6. **Mock external dependencies** - SCIM, SMTP, OIDC providers
7. **Test multitenancy** - Verify tenant isolation in relevant tests

## Continuous Integration

Add to your CI pipeline:

```yaml
# Example GitHub Actions workflow
- name: Run tests
  run: |
    pip install -r requirements.txt
    pytest --cov=. --cov-report=xml
    
- name: Upload coverage
  uses: codecov/codecov-action@v3
```

## Troubleshooting

### Database errors
If you see Tortoise ORM errors, ensure:
- `reset_database` fixture is running (it's autouse)
- Models are imported correctly in conftest.py

### Import errors
If tests can't find modules:
- Run tests from project root: `pytest`
- Check PYTHONPATH includes project directory

### Async errors
If you see "coroutine not awaited":
- Ensure test function is `async def`
- All async calls use `await`
- pytest.ini has `asyncio_mode = auto`

### NiceGUI user fixture errors
If UI tests fail:
- Verify pytest.ini specifies `main_file = main.py`
- Ensure main.py has proper ui.run() call
- Check that user plugin is loaded: `-p nicegui.testing.user_plugin`
