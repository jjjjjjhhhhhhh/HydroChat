import '@testing-library/jest-native/extend-expect';

// Mock React Native modules
jest.mock('react-native/Libraries/EventEmitter/NativeEventEmitter');

// Mock AsyncStorage
jest.mock('@react-native-async-storage/async-storage', () =>
  require('@react-native-async-storage/async-storage/jest/async-storage-mock')
);

// Mock react-navigation
jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({
    navigate: jest.fn(),
    goBack: jest.fn(),
    setParams: jest.fn(),
  }),
  useRoute: () => ({
    params: {},
  }),
  useFocusEffect: jest.fn(),
}));

// Mock react-native-svg
jest.mock('react-native-svg', () => {
  const React = require('react');
  const { View } = require('react-native');
  return {
    __esModule: true,
    default: ({ children, ...props }) => React.createElement(View, { testID: 'mock-svg', ...props }, children),
    Svg: ({ children, ...props }) => React.createElement(View, { testID: 'mock-svg', ...props }, children),
    Path: (props) => React.createElement(View, { testID: 'mock-path', ...props }),
  };
});

// Note: hydroChatService mock is handled in individual test files

// Global test timeout
jest.setTimeout(10000);
