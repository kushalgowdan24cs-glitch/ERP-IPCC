import cv2
import numpy as np
from insightface.app import FaceAnalysis

# Function to calculate how similar two faces are
def compute_similarity(emb1, emb2):
    return np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2))

def proctor_identity_check():
    print("Initializing ProctorShield Identity Verification...")
    app = FaceAnalysis(name='buffalo_l', providers=['CPUExecutionProvider'])
    app.prepare(ctx_id=-1, det_size=(640, 640))
    
    cap = cv2.VideoCapture(0)
    
    if not cap.isOpened():
        print("❌ Error: Could not access the webcam.")
        return

    registered_embedding = None
    # 0.4 is a standard threshold. Above 0.4 = Same person. Below = Stranger.
    similarity_threshold = 0.4 

    print("Webcam active.")
    print("Press 'r' to REGISTER your face.")
    print("Press 'q' to QUIT.")

    while True:
        ret, frame = cap.read()
        if not ret:
            break
            
        faces = app.get(frame)
        num_faces = len(faces)
        
        # On-screen instructions
        if registered_embedding is None:
            cv2.putText(frame, "Press 'r' to Register Face", (20, 50), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        
        if num_faces > 0:
            # We grab the first face detected
            live_face = faces[0]
            bbox = live_face.bbox.astype(int)
            
            if registered_embedding is not None:
                # Compare the live face to the registered face
                live_embedding = live_face.embedding
                similarity = compute_similarity(registered_embedding, live_embedding)
                
                # Check if it passes our threshold
                if similarity > similarity_threshold:
                    status = f"Verified Student (Sim: {similarity:.2f})"
                    color = (0, 255, 0) # Green for match
                else:
                    status = f"UNKNOWN PERSON! (Sim: {similarity:.2f})"
                    color = (0, 0, 255) # Red for stranger
                    
                # Draw the status and box
                cv2.putText(frame, status, (bbox[0], bbox[1] - 10), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
                cv2.rectangle(frame, (bbox[0], bbox[1]), (bbox[2], bbox[3]), color, 2)
            else:
                # Just draw a plain white box if not registered yet
                cv2.rectangle(frame, (bbox[0], bbox[1]), (bbox[2], bbox[3]), (255, 255, 255), 2)

        cv2.imshow('ProctorShield - Identity Check', frame)
        
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('r'):
            if num_faces == 1:
                # Save the embedding of the current face
                registered_embedding = faces[0].embedding
                print("✅ Face Registered Successfully!")
            else:
                print("⚠️ Please ensure exactly ONE face is in the frame to register.")

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    proctor_identity_check()