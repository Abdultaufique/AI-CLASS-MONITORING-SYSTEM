# LSOYS AI Monitoring — Live Demo

A simple, working demo for real-time face detection, recognition, talking detection, and warning system using your webcam.

## Quick Start

### 1. Open terminal in the `demo/` folder

```bash
cd demo
```

### 2. Create virtual environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Run the app

```bash
python app.py
```

### 5. Open in browser

```
http://127.0.0.1:5000
```

---

## How to Use

### Step 1: Upload Faces
1. Go to **Upload Faces** page
2. Enter a person's name
3. Upload 1 or more clear face photos
4. Repeat for each person you want to recognize

### Step 2: Start Live Camera
1. Go to **Live Camera** page
2. Click **Start Monitoring**
3. Your webcam will start — detected faces show bounding boxes and names

### Step 3: Enable Talking Detection
1. Toggle **Talking Detection** switch ON
2. Allow microphone access in browser
3. When talking is detected, warnings are issued to recognized faces:
   - Warning 1: "Please maintain silence"
   - Warning 2: "Final warning!"
   - Warning 3: "Please leave the room"

### Step 4: View Logs
1. Go to **Logs** page to see all warning history

---

## Tips for Best Results

- **Face photos**: Use clear, well-lit photos with the face visible
- **Multiple angles**: Upload 2-3 photos per person for better recognition
- **Webcam distance**: Sit 1-3 feet from the camera
- **Lighting**: Ensure good lighting on your face

## Optional: Better Face Recognition

For higher accuracy, install the `face_recognition` library:

```bash
pip install cmake
pip install dlib
pip install face-recognition
```

> Note: Requires Visual Studio Build Tools (C++) on Windows.

## File Structure

```
demo/
├── app.py              # Main Flask application
├── requirements.txt    # Python dependencies
├── README.md           # This file
├── data/
│   ├── faces/          # Uploaded face images
│   ├── encodings.pkl   # Saved face encodings
│   └── logs.json       # Event logs
├── static/
│   └── css/style.css   # UI styling
└── templates/
    ├── base.html       # Base layout
    ├── upload.html     # Face upload page
    ├── live.html       # Live camera page
    └── logs.html       # Logs page
```
