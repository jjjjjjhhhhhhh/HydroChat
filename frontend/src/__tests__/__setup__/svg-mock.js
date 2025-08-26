// SVG Mock for Jest testing
jest.mock('react-native-svg', () => {
  const React = require('react');
  return {
    Svg: ({ children, ...props }) => React.createElement('View', { testID: 'mock-svg', ...props }, children),
    Path: (props) => React.createElement('View', { testID: 'mock-path', ...props }),
  };
});
