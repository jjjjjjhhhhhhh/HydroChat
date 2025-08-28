# Frontend Test Scripts

This folder contains test runners for HydroChat Phase 12 frontend tests.

## Test Runners

### PowerShell (Windows)
```powershell
.\run-phase12-tests.ps1
```

### Bash (Linux/macOS)
```bash
./run-phase12-tests.sh
```

## Manual Testing
You can also run tests manually from the frontend directory:

```bash
# Run all tests
npx jest

# Run specific test patterns
npx jest --testMatch="**/src/__tests__/**/*.test.{js,jsx,ts,tsx}"

# Run with coverage
npx jest --coverage

# Run in watch mode
npx jest --watch
```

## Test Structure
- **Service Tests:** `src/__tests__/services/`
- **Screen Tests:** `src/__tests__/screens/`
- **Setup:** `src/__tests__/setup.js`
