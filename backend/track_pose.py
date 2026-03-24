import cv2
from insightface.app import FaceAnalysis

def proctor_head_pose():
    print("Initializing ProctorShield Head Pose Tracking...")
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
            break
            
        faces = app.get(frame)
        
        for face in faces:
            bbox = face.bbox.astype(int)
            
            # InsightFace conveniently provides Pitch, Yaw, and Roll in 'face.pose'
            pitch, yaw, roll = face.pose
            
            # --- PROCTORING LOGIC FOR HEAD POSE ---
            # Thresholds (in degrees) - you can tweak these based on testing!
            is_looking_away = False
            warning_text = ""
            
            # Check Yaw (Looking left/right)
            if abs(yaw) > 30: 
                is_looking_away = True
                warning_text = "ALERT: Looking Off-Screen!"
                
            # Check Pitch (Looking down/up)
            # Depending on your camera angle, looking at the keyboard might be ~20 to 30 degrees
            elif abs(pitch) > 25: 
                is_looking_away = True
                warning_text = "ALERT: Looking Down/Up!"
                
            if is_looking_away:
                box_color = (0, 0, 255) # Red for warning
                cv2.putText(frame, warning_text, (bbox[0], bbox[1] - 35), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, box_color, 2)
            else:
                box_color = (0, 255, 0) # Green for normal
            
            # Draw the bounding box
            cv2.rectangle(frame, (bbox[0], bbox[1]), (bbox[2], bbox[3]), box_color, 2)
            
            # Display the live angles for debugging and calibration
            pose_text = f"Pitch: {pitch:.0f} | Yaw: {yaw:.0f} | Roll: {roll:.0f}"
            cv2.putText(frame, pose_text, (bbox[0], bbox[1] - 10), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        cv2.imshow('ProctorShield - Head Pose Tracking', frame)
        
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    proctor_head_pose()