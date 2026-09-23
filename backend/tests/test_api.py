import sys
import os
import unittest
import json

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import app
from database import get_db, init_db


class MedicareAPITestCase(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        init_db()

        # Unique email per test run
        import time
        self.test_email = f"test_{int(time.time() * 1000)}@example.com"
        self.test_password = "password123"

    def test_health_check(self):
        """Test health check returns 200 and healthy status."""
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data.get("status"), "healthy")

    def test_signup_and_login_flow(self):
        """Test complete auth cycle: signup, me, change password, login."""
        # 1. Signup
        signup_res = self.client.post("/api/auth/signup", json={
            "name": "Dr. Test User",
            "email": self.test_email,
            "password": self.test_password
        })
        self.assertEqual(signup_res.status_code, 201)
        signup_data = signup_res.get_json()
        self.assertIn("token", signup_data)
        token = signup_data["token"]

        # 2. Get Me
        headers = {"Authorization": f"Bearer {token}"}
        me_res = self.client.get("/api/auth/me", headers=headers)
        self.assertEqual(me_res.status_code, 200)
        me_data = me_res.get_json()
        self.assertEqual(me_data["user"]["email"], self.test_email)

        # 3. Change Password
        new_pw = "newpassword456"
        pw_res = self.client.post("/api/auth/change-password", headers=headers, json={
            "old_password": self.test_password,
            "new_password": new_pw
        })
        self.assertEqual(pw_res.status_code, 200)

        # 4. Login with new password
        login_res = self.client.post("/api/auth/login", json={
            "email": self.test_email,
            "password": new_pw
        })
        self.assertEqual(login_res.status_code, 200)

    def test_chat_history_crud(self):
        """Test creating, listing, reading, and deleting chat sessions."""
        # Create user
        signup_res = self.client.post("/api/auth/signup", json={
            "name": "History Tester",
            "email": f"history_{self.test_email}",
            "password": "password123"
        })
        token = signup_res.get_json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Create a session
        create_res = self.client.post("/api/history", headers=headers, json={
            "title": "Diabetes Symptoms",
            "messages": [
                {"role": "user", "content": "What are diabetes symptoms?"},
                {"role": "assistant", "content": "Common symptoms include increased thirst, frequent urination..."}
            ]
        })
        self.assertEqual(create_res.status_code, 201)
        session_id = create_res.get_json()["session"]["id"]

        # 2. List sessions
        list_res = self.client.get("/api/history", headers=headers)
        self.assertEqual(list_res.status_code, 200)
        sessions = list_res.get_json()["sessions"]
        self.assertTrue(any(s["id"] == session_id for s in sessions))

        # 3. Get session detail
        get_res = self.client.get(f"/api/history/{session_id}", headers=headers)
        self.assertEqual(get_res.status_code, 200)
        session_data = get_res.get_json()["session"]
        self.assertEqual(len(session_data["messages"]), 2)

        # 4. Share session
        share_res = self.client.post(f"/api/history/{session_id}/share", headers=headers)
        self.assertEqual(share_res.status_code, 200)
        share_token = share_res.get_json()["share_token"]
        self.assertTrue(len(share_token) > 0)

        # 5. Public read of shared session (no auth header needed)
        public_res = self.client.get(f"/api/share/{share_token}")
        self.assertEqual(public_res.status_code, 200)
        pub_data = public_res.get_json()["session"]
        self.assertEqual(pub_data["title"], "Diabetes Symptoms")
        self.assertEqual(len(pub_data["messages"]), 2)
        self.assertEqual(pub_data["user_name"], "History Tester")

        # 6. Delete session
        del_res = self.client.delete(f"/api/history/{session_id}", headers=headers)
        self.assertEqual(del_res.status_code, 200)


if __name__ == "__main__":
    unittest.main()
