import React, { useState } from 'react';
import LoginScreen from './LoginScreen';
import ScreenShareStep from './ScreenShareStep';
import FaceVerifyStep from './FaceVerifyStep';
import ExamRoom from './ExamRoom';
import MobileCam from './MobileCam';
import ProctorDashboard from './ProctorDashboard';

export default function App() {
  const queryParams = new URLSearchParams(window.location.search);
  if (queryParams.get('mode') === 'mobile') {
    return <MobileCam />;
  }
  if (queryParams.get('mode') === 'proctor') {
    return <ProctorDashboard />;
  }

  const [currentStep, setCurrentStep] = useState('login');
  const [sessionData, setSessionData] = useState(null);

  const handleLoginSuccess = (data) => {
    setSessionData(data);
    setCurrentStep('screen_share');
  };

  const handleScreenShareSuccess = (screenStream) => {
    setSessionData((prev) => ({ ...prev, screenStream }));
    setCurrentStep('face_verify');
  };

  const handleFaceVerifySuccess = () => {
    setCurrentStep('exam');
  };

  return (
    <div style={{ backgroundColor: '#0f172a', minHeight: '100vh', color: 'white' }}>
      {currentStep === 'login' && <LoginScreen onJoin={handleLoginSuccess} />}
      {currentStep === 'screen_share' && (
        <ScreenShareStep studentData={sessionData} onNext={handleScreenShareSuccess} />
      )}
      {currentStep === 'face_verify' && (
        <FaceVerifyStep studentData={sessionData} onNext={handleFaceVerifySuccess} />
      )}
      {currentStep === 'exam' && sessionData && (
        <ExamRoom
          erpToken={sessionData.erpToken}
          examCode={sessionData.examCode}
          cameraId={sessionData.cameraId}
          micId={sessionData.micId}
          studentId={sessionData.studentId}
          studentName={sessionData.studentName}
        />
      )}
    </div>
  );
}
