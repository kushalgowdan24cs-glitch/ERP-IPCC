let warmupPromise = null;
let modelsReady = false;
let faceApiModule = null;

export async function warmupFaceModels(modelUrl = '/models') {
  if (modelsReady) {
    return;
  }

  if (!warmupPromise) {
    warmupPromise = (async () => {
      faceApiModule = await import('@vladmandic/face-api');

      await Promise.all([
        faceApiModule.nets.ssdMobilenetv1.loadFromUri(modelUrl),
        faceApiModule.nets.faceLandmark68Net.loadFromUri(modelUrl),
        faceApiModule.nets.faceRecognitionNet.loadFromUri(modelUrl),
      ]);

      modelsReady = true;
      return faceApiModule;
    })().catch((error) => {
      warmupPromise = null;
      throw error;
    });
  }

  return warmupPromise;
}

export function areFaceModelsReady() {
  return modelsReady;
}

export async function getFaceApi() {
  if (faceApiModule) {
    return faceApiModule;
  }
  return warmupFaceModels();
}
