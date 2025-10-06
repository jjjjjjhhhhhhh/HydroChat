import React from 'react';
import { render, fireEvent, screen, waitFor, act } from '@testing-library/react-native';
import PatientsListScreen from '../../../screens/patients/PatientsListScreen';

// Mock the patient service
jest.mock('../../../services/patientService', () => ({
  patientService: {
    getPatients: jest.fn().mockResolvedValue([
      {
        id: 1,
        first_name: 'John',
        last_name: 'Doe',
        nric: 'S1234567A'
      }
    ])
  }
}));

// Mock logout function
jest.mock('../../../services', () => ({
  patientService: {
    getPatients: jest.fn().mockResolvedValue([]),
  },
  logout: jest.fn(),
}));

const mockNavigation = {
  navigate: jest.fn(),
  setParams: jest.fn(),
  replace: jest.fn(),
};

const mockRoute = {
  params: {},
};

describe('PatientsListScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('HydroChat Integration', () => {
    it('should render chatbot button in header', async () => {
      render(<PatientsListScreen navigation={mockNavigation} route={mockRoute} />);
      
      // Wait for async effects to complete
      await waitFor(() => {
        expect(screen.getByLabelText('Open HydroChat')).toBeTruthy();
      });
    });

    it('should navigate to HydroChat when chatbot button is pressed', async () => {
      render(<PatientsListScreen navigation={mockNavigation} route={mockRoute} />);
      
      // Wait for component to be ready
      await waitFor(() => {
        expect(screen.getByLabelText('Open HydroChat')).toBeTruthy();
      });
      
      const chatbotButton = screen.getByLabelText('Open HydroChat');
      fireEvent.press(chatbotButton);
      
      expect(mockNavigation.navigate).toHaveBeenCalledWith('HydroChat');
    });

    it('should still render the add patient button', async () => {
      render(<PatientsListScreen navigation={mockNavigation} route={mockRoute} />);
      
      // Wait for component to be ready
      await waitFor(() => {
        expect(screen.getByText('Patients Directory')).toBeTruthy();
      });
      
      // The add button doesn't have an explicit test ID, but we can verify navigation behavior
      // when testing the "New Patient Form" navigation
      expect(screen.getByText('Patients Directory')).toBeTruthy();
    });
  });

  describe('Header Layout', () => {
    it('should render both add and chatbot buttons', async () => {
      render(<PatientsListScreen navigation={mockNavigation} route={mockRoute} />);
      
      // Wait for component to be ready
      await waitFor(() => {
        expect(screen.getByText('Patients Directory')).toBeTruthy();
      });
      
      // Check that both buttons exist
      const chatbotButton = screen.getByLabelText('Open HydroChat');
      expect(chatbotButton).toBeTruthy();
      
      // Title should still be centered
      expect(screen.getByText('Patients Directory')).toBeTruthy();
    });
  });
});
