import torch
import torchaudio
import numpy as np

bundle = torchaudio.pipelines.WAV2VEC2_BASE
device = torch.device("cpu")
model = bundle.get_model().to(device)

# fake audio 4 seconds
audio = np.random.uniform(-1, 1, 64000).astype(np.float32)
tensor = torch.tensor(audio).unsqueeze(0).to(device)

try:
    with torch.no_grad():
        out = model(tensor)
        print("Model output type:", type(out))
        if isinstance(out, tuple):
            print("Tuple len:", len(out))
            features, _ = out
        else:
            features = out
        print("Features shape:", features.shape)
        embedding = features.mean(dim=1).squeeze(0).numpy()
        print("Embedding shape:", embedding.shape)
        print("SUCCESS")
except Exception as e:
    print("ERROR:", e)
