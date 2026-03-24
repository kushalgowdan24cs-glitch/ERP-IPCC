import cv2
from insightface.app import FaceAnalysis

def proctor_basic_alerts():
    print("Initializing ProctorShield Alerts...")
    app = FaceAnalysis(name='buffalo_l', providers=['CPUExecutionProvider'])
    app.prepare(ctx_id=-1, det_size=(640, 640))
    
    cap = cv2.VideoCapture(0)
    
    if not cap.isOpened():
        print("❌ Error: Could not access the webcam.")
        return

    print("Webcam active. Press 'q' to quit.")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("❌ Error: Failed to grab frame.")
            break
            
        # Get faces from InsightFace
        faces = app.get(frame)
        num_faces = len(faces)
        
        # --- PROCTORING LOGIC ---
        if num_faces == 0:
            status_text = "ALERT: Student Absent!"
            color = (0, 0, 255) # Red text
        elif num_faces > 1:
            status_text = f"ALERT: Multiple People ({num_faces})!"
            color = (0, 0, 255) # Red text
        else:
            status_text = "Status: Normal"
            color = (0, 255, 0) # Green text
            
        # Display the alert status prominently on the screen
        cv2.putText(frame, status_text, (20, 50), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1.2, color, 3)
        
        # Draw bounding boxes for anyone found
        for face in faces:
            bbox = face.bbox.astype(int)
            cv2.rectangle(frame, (bbox[0], bbox[1]), (bbox[2], bbox[3]), color, 2)

        cv2.imshow('ProctorShield - Live Alerts', frame)
        
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    proctor_basic_alerts()