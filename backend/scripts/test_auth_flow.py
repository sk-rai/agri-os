"""Test the complete auth flow: OTP request → verify → device login."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
PASS = "\033[92m✅\033[0m"
FAIL = "\033[91m❌\033[0m"

print("=" * 60)
print("AUTH FLOW TEST")
print("=" * 60)

# Step 1: Request OTP
print("\n[1] Request OTP")
r = client.post("/api/v1/auth/otp/request", json={
    "mobile_number": "+919876543210"
})
print(f"  Status: {r.status_code}")
data = r.json()
print(f"  Response: {data}")
assert r.status_code == 200

# Extract OTP from dev response
otp = data["message"].split("Dev OTP: ")[-1]
print(f"  {PASS} OTP received: {otp}")

# Step 2: Verify OTP (get JWT + device_key)
print("\n[2] Verify OTP")
r = client.post("/api/v1/auth/otp/verify", json={
    "mobile_number": "+919876543210",
    "otp_code": otp,
    "device_id": "android-test-device-001",
    "device_name": "Pixel 6a",
})
print(f"  Status: {r.status_code}")
data = r.json()
print(f"  Token: {data.get('access_token', '')[:50]}...")
print(f"  Device key: {data.get('device_key', '')[:30]}...")
print(f"  User ID: {data.get('user_id')}")
print(f"  Role: {data.get('role')}")
assert r.status_code == 200
assert data["access_token"]
assert data["device_key"]
device_key = data["device_key"]
user_id = data["user_id"]
print(f"  {PASS} JWT + device_key issued")

# Step 3: Device login (no SMS needed)
print("\n[3] Device Login (SMS-free)")
r = client.post("/api/v1/auth/device", json={
    "device_key": device_key,
    "device_id": "android-test-device-001",
})
print(f"  Status: {r.status_code}")
data = r.json()
print(f"  Token: {data.get('access_token', '')[:50]}...")
print(f"  User ID: {data.get('user_id')}")
assert r.status_code == 200
assert data["user_id"] == user_id
print(f"  {PASS} Device login successful (no SMS)")

# Step 4: Invalid device key
print("\n[4] Invalid device key (should fail)")
r = client.post("/api/v1/auth/device", json={
    "device_key": "invalid-key-12345",
    "device_id": "android-test-device-001",
})
print(f"  Status: {r.status_code}")
assert r.status_code == 401
print(f"  {PASS} Correctly rejected invalid device key")

# Step 5: Wrong device ID (should fail)
print("\n[5] Wrong device ID (should fail)")
r = client.post("/api/v1/auth/device", json={
    "device_key": device_key,
    "device_id": "different-device-999",
})
print(f"  Status: {r.status_code}")
assert r.status_code == 401
print(f"  {PASS} Correctly rejected wrong device ID")

# Step 6: Invalid OTP
print("\n[6] Invalid OTP (should fail)")
client.post("/api/v1/auth/otp/request", json={"mobile_number": "+919876543210"})
r = client.post("/api/v1/auth/otp/verify", json={
    "mobile_number": "+919876543210",
    "otp_code": "000000",
    "device_id": "android-test-device-001",
})
assert r.status_code == 401
print(f"  {PASS} Correctly rejected invalid OTP")

print(f"\n{'=' * 60}")
print(f"🟢 All auth flow tests passed!")
print(f"{'=' * 60}")
