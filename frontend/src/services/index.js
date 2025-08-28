// API Configuration
export { default as api } from './api';

// Service Exports
export { authService } from './authService';
export { patientService } from './patientService';
export { scanService } from './scanService';
export { hydroChatService } from './hydroChatService';

// Import services first to ensure they're available
import { authService } from './authService';
import { patientService } from './patientService';
import { scanService } from './scanService';
import { hydroChatService } from './hydroChatService';

// Convenience exports for common functions
export const { login, register, logout, getUserInfo, isAuthenticated } = authService;
export const { getAllPatients, getPatient, createPatient, updatePatient, deletePatient } = patientService;
export const { getAllScans, getPatientScans, createScan, processInitialCrop, processCroppedSegmentation, processDepthAnalysis, processMeshGeneration } = scanService;
export const { sendMessage: sendHydroChatMessage, getStats: getHydroChatStats } = hydroChatService; 