import { useState, useRef, useCallback } from 'react';

export function useMediaCapture() {
  const [isCapturing, setIsCapturing] = useState(false);
  const videoRef = useRef(null);
  const canvasRef = useRef(document.createElement('canvas'));
  const streamRef = useRef(null);
  const audioContextRef = useRef(null);
  const analyserRef = useRef(null);
  const audioBufferRef = useRef([]);

  const startCapture = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          width: { ideal: 640 },
          height: { ideal: 480 },
          facingMode: 'user',
        },
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          sampleRate: 16000,
        },
      });

      streamRef.current = stream;

      if (videoRef.current) {
        videoRef.current.srcObject = stream;
      }

      // Setup audio processing
      const audioContext = new (window.AudioContext || window.webkitAudioContext)({
        sampleRate: 16000,
      });
      const source = audioContext.createMediaStreamSource(stream);
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 2048;
      source.connect(analyser);

      // Capture audio samples using ScriptProcessor (deprecated but widely supported)
      const processor = audioContext.createScriptProcessor(4096, 1, 1);
      source.connect(processor);
      processor.connect(audioContext.destination);

      processor.onaudioprocess = (e) => {
        const data = e.inputBuffer.getChannelData(0);
        audioBufferRef.current.push(...data);

        // Keep only last 1 second of audio
        const maxSamples = 16000;
        if (audioBufferRef.current.length > maxSamples * 2) {
          audioBufferRef.current = audioBufferRef.current.slice(-maxSamples);
        }
      };

      audioContextRef.current = audioContext;
      analyserRef.current = analyser;
      setIsCapturing(true);

      console.log('[Media] Capture started');
    } catch (err) {
      console.error('[Media] Failed to start capture:', err);
    }
  }, []);

  const stopCapture = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop());
      streamRef.current = null;
    }
    if (audioContextRef.current) {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }
    setIsCapturing(false);
    console.log('[Media] Capture stopped');
  }, []);

  const captureFrame = useCallback(() => {
    const video = videoRef.current;
    if (!video || video.readyState < 2) return null;

    const canvas = canvasRef.current;
    canvas.width = 640;
    canvas.height = 480;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0, 640, 480);

    // Get base64 JPEG (strip the data:image/jpeg;base64, prefix)
    const dataUrl = canvas.toDataURL('image/jpeg', 0.7);
    return dataUrl.split(',')[1];
  }, []);

  const captureAudio = useCallback(() => {
    if (audioBufferRef.current.length < 8000) return null; // need at least 0.5s

    const samples = audioBufferRef.current.splice(0, 16000); // take 1 second
    return {
      samples: Array.from(samples),
      sampleRate: 16000,
    };
  }, []);

  return {
    videoRef,
    startCapture,
    stopCapture,
    captureFrame,
    captureAudio,
    isCapturing,
  };
}