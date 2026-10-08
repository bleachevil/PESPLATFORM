# Manager Desk (Android)

Flutter client for the PES Data manager league. It talks to the Python API in this repo (`/api/...`).

```powershell
cd android_app
flutter pub get
flutter run
```

On the PC, bind the server to all interfaces so a phone can reach it:

```powershell
python -m uvicorn web.app:app --reload --host 0.0.0.0 --port 8000
```

- Emulator API URL: `http://10.0.2.2:8000`
- Physical phone: `http://YOUR_PC_LAN_IP:8000`

Package id: `com.pesdata.manager_desk`. Google sign-in needs a web client ID (serverClientId) and an Android client ID with this package and your debug SHA-1. See the Android section in the repo README.
