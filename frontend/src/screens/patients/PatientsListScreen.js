import React, { useState, useEffect, useRef } from 'react';
import { 
  ScrollView, 
  KeyboardAvoidingView, 
  Pressable, 
  View, 
  Text, 
  StyleSheet, 
  TouchableOpacity, 
  Image, 
  Keyboard, 
  TouchableWithoutFeedback,
  Dimensions
} from 'react-native';
import { patientService, logout } from '../../services';
import { LogoHeader } from '../../components';
import { TextInput } from 'react-native-gesture-handler';
import { Alert } from 'react-native';
import Svg, { Path } from 'react-native-svg';
import { useFocusEffect } from '@react-navigation/native';

const PatientListItem = ({ name, id, onPress }) => {
  return (
    <TouchableOpacity onPress={onPress} style={styles.patientListItem}>
      <Text style={styles.patientName}>{name}</Text>
      <Text style={styles.patientId}>{id}</Text>
      <View style={styles.divider} />
    </TouchableOpacity>
  );
};

const PatientsListScreen = ({navigation, route}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [patients, setPatients] = useState([]);
  const [isInputFocused, setIsInputFocused] = useState(false);
  const scrollViewRef = useRef(null);
  const [isLoading, setIsLoading] = useState(false);

  // Function to fetch patients data
  const fetchPatients = async () => {
    console.log('[PatientsListScreen] Fetching patients list from server...');
    setIsLoading(true);
    try {
      const patients = await patientService.getPatients();
      console.log(`[PatientsListScreen] Successfully fetched ${patients.length} patients from server`);
      setPatients(patients);
    } catch (error) {
      console.error('[PatientsListScreen] Error fetching patients:', error);
    } finally {
      setIsLoading(false);
    }
  };

  // Initial fetch on component mount
  useEffect(() => {
    console.log('[PatientsListScreen] Component mounted, performing initial patient fetch...');
    fetchPatients();
  }, []);

  // Refresh patient list when screen comes into focus
  useFocusEffect(
    React.useCallback(() => {
      console.log('[PatientsListScreen] Screen focused, refreshing patient list...');
      // Fetch patients when the screen comes into focus
      fetchPatients();
      
      return () => {
        console.log('[PatientsListScreen] Screen unfocused');
        // This is the cleanup function
        // No need to do anything here
      };
    }, []) // Empty dependency array means this only re-runs when the component mounts/unmounts
  );

  // Check if route and route.params exist before accessing route.params.refresh
  useEffect(() => {
    if (route && route.params && route.params.refresh) {
      fetchPatients();
      // Reset the parameter after use
      navigation.setParams({ refresh: undefined });
    }
  }, [route && route.params ? route.params.refresh : null]);

  const filteredPatients = (patients || []).filter((patient) => {
    const name = `${patient.first_name || ''} ${patient.last_name || ''}`.toLowerCase();
    return name.includes(searchQuery.toLowerCase());
  }).sort((a, b) => {
    const nameA = `${a.first_name || ''} ${a.last_name || ''}`.toLowerCase();
    const nameB = `${b.first_name || ''} ${b.last_name || ''}`.toLowerCase();
    return nameA.localeCompare(nameB);
  });

  const handlePressOutside = () => {
    if (!isInputFocused) {
      Keyboard.dismiss();
    }
  };

  const handleLogout = async () => {
    console.log('[PatientsListScreen] User initiated logout...');
    try {
      await logout(); // This will clear the auth tokens from AsyncStorage
      console.log('[PatientsListScreen] Logout successful, clearing auth tokens');
      Alert.alert(
        "Logged Out",
        "You have been successfully logged out.",
        [{ text: "OK", onPress: () => {
          console.log('[PatientsListScreen] Navigating to Login screen after logout');
          navigation.replace('Login');
        }}]
      );
    } catch (error) {
      console.error('[PatientsListScreen] Logout error:', error);
      Alert.alert("Error", "Failed to log out. Please try again.");
    }
  };

  return (
    <TouchableWithoutFeedback onPress={handlePressOutside}>
      <View style={styles.container}>
        {/* Header with back/logout button and title */}
        <View style={styles.header}>
          <TouchableOpacity 
            style={styles.backButton}
            onPress={handleLogout}
          >
            <Svg width="18" height="16" viewBox="0 0 18 16" fill="none">
              <Path d="M16 9.01626C16.5613 9.01626 17.0163 8.56126 17.0163 8C17.0163 7.43874 16.5613 6.98374 16 6.98374L16 9.01626ZM1.2814 7.2814C0.884525 7.67827 0.884525 8.32173 1.2814 8.7186L7.74882 15.186C8.14569 15.5829 8.78915 15.5829 9.18602 15.186C9.58289 14.7891 9.58289 14.1457 9.18602 13.7488L3.4372 8L9.18602 2.25118C9.58289 1.85431 9.58289 1.21085 9.18602 0.813981C8.78915 0.417108 8.14569 0.417108 7.74881 0.813981L1.2814 7.2814ZM16 6.98374L2 6.98375L2 9.01626L16 9.01626L16 6.98374Z" fill="black"/>
            </Svg>
          </TouchableOpacity>
          
          <Text style={styles.patientsListTitle}>Patients Directory</Text>
          
          <View style={styles.headerButtons}>
            <TouchableOpacity 
              style={styles.addButton}
              onPress={() => navigation.navigate('New Patient Form')}
            >
              <Svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <Path d="M1 7H13" stroke="black" strokeWidth="2" strokeLinecap="round"/>
                <Path d="M7 1L7 13" stroke="black" strokeWidth="2" strokeLinecap="round"/>
              </Svg>
            </TouchableOpacity>
            
            <TouchableOpacity 
              style={styles.chatbotButton}
              onPress={() => navigation.navigate('HydroChat')}
              accessibilityLabel="Open HydroChat"
            >
              <Svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                <Path d="M10 4.31055C8.55795 4.31055 7.11941 4.80223 5.94759 5.78535C5.24241 6.37708 4.69721 7.09706 4.31869 7.88547C4.26616 7.88055 4.21504 7.86908 4.16111 7.86908C3.21924 7.86908 2.46087 8.62744 2.46087 9.56929V11.6706C2.46087 12.6125 3.21924 13.3708 4.16111 13.3708C4.21505 13.3708 4.26617 13.3591 4.31869 13.3544C4.38646 13.4949 4.45658 13.6343 4.53561 13.7713C4.84455 14.3227 5.66992 13.8506 5.35121 13.305C4.04625 11.0447 4.55164 8.18053 6.55093 6.50292C8.55023 4.82527 11.4542 4.82527 13.4535 6.50292C15.4528 8.18053 15.9582 11.0447 14.6533 13.305L14.6392 13.3284L14.6298 13.3518C14.6298 13.3518 13.996 14.7539 12.7515 14.7539L11.1761 14.7398C11.0284 14.524 10.7919 14.3738 10.5096 14.3738H9.49405C9.03871 14.3738 8.67241 14.741 8.67241 15.1967C8.67241 15.4776 8.85064 15.6908 9.25847 15.6911L12.7515 15.6911C14.6191 15.6911 15.4268 13.8576 15.4636 13.7727V13.7677C15.5419 13.6319 15.6109 13.4925 15.6782 13.3533C15.7331 13.3583 15.7866 13.3697 15.8431 13.3697C16.785 13.3697 17.5434 12.6113 17.5434 11.6695V9.56821C17.5434 8.62636 16.785 7.868 15.8431 7.868C15.7889 7.868 15.7374 7.877 15.6844 7.8844C15.3068 7.096 14.7621 6.37607 14.0569 5.78436C12.8851 4.80124 11.4419 4.31055 10 4.31055ZM7.95079 7.29773C7.58477 7.27383 7.25046 7.35126 6.95827 7.65887C6.17922 8.47905 5.69794 9.59537 5.69794 10.7842C5.69794 11.7648 6.02566 12.8636 6.5778 12.9037C7.36431 12.9609 8.60546 12.4444 10.0025 12.4444C11.4829 12.4444 12.7893 13.024 13.5641 12.8867C14.0336 12.8037 14.3081 11.6813 14.3081 10.7842C14.3081 9.59537 13.8268 8.47905 13.0478 7.65887C12.2687 6.83866 11.1925 7.65887 10.0036 7.65887C9.26066 7.65887 8.562 7.33778 7.95215 7.29773ZM7.77632 9.31907C8.21063 9.31924 8.56267 9.67126 8.56284 10.1056C8.5627 10.5399 8.21066 10.8919 7.77632 10.8921C7.34198 10.8919 6.98996 10.5399 6.98979 10.1056C6.99 9.67126 7.34202 9.31924 7.77637 9.31907ZM12.2288 9.31907C12.6631 9.31924 13.0151 9.67126 13.0153 10.1056C13.0151 10.5399 12.6631 10.8919 12.2288 10.8921C11.7944 10.8919 11.4424 10.5399 11.4422 10.1056C11.4424 9.67126 11.7944 9.31924 11.4422 9.31907Z" fill="black"/>
              </Svg>
            </TouchableOpacity>
          </View>
        </View>

        {/* Search Bar */}
        <View style={styles.searchBarContainer}>
          {/* Search Icon */}
          <Image
            source={require('../../assets/icons/searchIcon.png')}
            style={styles.searchIcon}
          />

          {/* Search Input */}
          <TextInput
            style={styles.searchInput}
            placeholder="Search for patient"
            placeholderTextColor="dimgray"
            onChangeText={(text) => setSearchQuery(text)}
            value={searchQuery}
            underlineColorAndroid="transparent"
            onFocus={() => setIsInputFocused(true)} 
            onBlur={() => setIsInputFocused(false)} 
          />
        </View>

        {/* Patient list */}
        <ScrollView 
          ref={scrollViewRef}
          style={styles.patientListContainer}
        >
          {filteredPatients.map((patient) => (
            <PatientListItem
              key={patient.id}
              name={`${patient.first_name || ''} ${patient.last_name || ''}`}
              id={patient.nric}
              onPress={() => {
                const patientName = `${patient.first_name || ''} ${patient.last_name || ''}`.trim();
                console.log(`[PatientsListScreen] Patient selected: "${patientName}" (ID: ${patient.id}, NRIC: ${patient.nric})`);
                console.log(`[PatientsListScreen] Navigating to Patient Detail screen for patient: ${patientName}`);
                // Navigate to Patient Detail page with patient ID
                navigation.navigate('Patient Detail', { patientId: patient.id });
              }}
            />
          ))}
        </ScrollView>
      </View>
    </TouchableWithoutFeedback>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    width: '100%',
    height: '100%',
    backgroundColor: '#FCFFF8',
    padding: 30,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    width: '100%',
    marginBottom: 20,
    marginLeft: -10,
    marginRight: -10,
  },
  backButton: {
    width: 40,
    height: 40,
    justifyContent: 'center',
    alignItems: 'center',
  },
  backButtonText: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#707070',
  },
  headerButtons: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  addButton: {
    width: 40,
    height: 40,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: 'transparent',
  },
  chatbotButton: {
    width: 40,
    height: 40,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: 'transparent',
    marginLeft: 5,
  },
  searchBarContainer: {
    width: '100%',
    height: 43,
    backgroundColor: '#ECECEC',
    borderRadius: 13,
    flexDirection: 'row',
    alignItems: 'center',
    paddingLeft: 20,
    marginBottom: 20,
  },
  searchIcon: {
    width: 23,
    height: 23,
    marginRight: 10,
  },
  searchInput: {
    width: '100%',
    fontSize: 16,
    fontFamily: 'Urbanist',
  },
  patientsListTitle: {
    fontSize: 20,
    fontWeight: '700',
    textAlign: 'center',
    fontFamily: 'Urbanist',
  },
  patientListContainer: {
    flex: 1,
    width: '100%',
    height: '100%',
    backgroundColor: '#EEEEEE',
    borderRadius: 13,
    padding: 10,
  },
  patientListItem: {
    width: '100%',
    paddingVertical: 10,
    marginBottom: 10,
    position: 'relative',
  },
  patientName: {
    fontSize: 12,
    color: '#707070',
    fontFamily: 'Urbanist',
    fontWeight: '700',
  },
  patientId: {
    fontSize: 14,
    color: '#707070',
    position: 'absolute',
    right: 0,
    top: 10,
    fontFamily: 'Urbanist',
  },
  divider: {
    height: 1,
    width: '100%',
    backgroundColor: 'white',
    position: 'absolute',
    bottom: 0,
  },
});

export default PatientsListScreen; 