#!/bin/bash

echo "🧪 Running HydroChat Phase 12 Frontend Tests..."
echo "================================================"

# Change to frontend directory
cd "$(dirname "$0")/.."

# Install test dependencies if they don't exist
if [ ! -d "node_modules/@testing-library/react-native" ]; then
    echo "📦 Installing test dependencies..."
    npm install
fi

echo ""
echo "🔧 Running Jest tests directly..."
echo "=================================="

# Run specific tests for Phase 12 using npx jest directly
npx jest --testMatch="<rootDir>/src/__tests__/**/*.test.{js,jsx,ts,tsx}" --verbose

echo ""
echo "📊 Test Coverage Report:"
echo "========================"

npx jest --coverage --testMatch="<rootDir>/src/__tests__/**/*.test.{js,jsx,ts,tsx}" --silent

echo ""
echo "✅ Phase 12 test execution completed!"
