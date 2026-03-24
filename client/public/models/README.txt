Place these model files in this folder for FaceVerifyStep:

1) face_landmark_68_model-weights_manifest.json
2) face_landmark_68_model-shard1
3) face_recognition_model-weights_manifest.json
4) face_recognition_model-shard1
5) ssd_mobilenetv1_model-weights_manifest.json
6) ssd_mobilenetv1_model-shard1
7) ssd_mobilenetv1_model-shard2

Optional profile image for ERP comparison:
- Put student_profile.jpg in client/public/

Notes:
- These files must be served at /models/* for loadFromUri('/models') to work.
- File names vary by model package source. Keep JSON manifest names and shard names aligned with your downloaded set.
