import hashlib
import os
import secrets
import tempfile
import unittest
from pathlib import Path

import httpx
from types import SimpleNamespace
from unittest.mock import patch

import ultimate_rvc.control.app as control_app

_TEST_USER = "test_user"
_TEST_PASSWORD = secrets.token_urlsafe(16)
_TEST_SECRET = secrets.token_urlsafe(32)


class ControlApiTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.original_audio = control_app.TRAINING_AUDIO_DIR
        self.original_uploads = control_app.UPLOADS_DIR
        control_app.TRAINING_AUDIO_DIR = root / "audio"
        control_app.UPLOADS_DIR = root / "uploads"
        os.environ.update(
            RVC_CONTROL_USER=_TEST_USER,
            RVC_CONTROL_PASSWORD=_TEST_PASSWORD,
            RVC_CONTROL_SECRET=_TEST_SECRET,
        )
        os.environ.pop("KAGGLE_API_TOKEN", None)
        os.environ.pop("RVC_KAGGLE_USERNAME", None)
        control_app._kaggle_setup_complete = False
        transport = httpx.ASGITransport(app=control_app.app)
        self.client = httpx.AsyncClient(transport=transport, base_url="http://test")

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        control_app.TRAINING_AUDIO_DIR = self.original_audio
        control_app.UPLOADS_DIR = self.original_uploads
        os.environ.pop("KAGGLE_API_TOKEN", None)
        os.environ.pop("RVC_KAGGLE_USERNAME", None)
        os.environ.pop("RVC_RESUME_DATASET", None)
        os.environ.pop("RVC_RESUME_ROOT", None)
        control_app._kaggle_setup_complete = False
        self.temporary.cleanup()

    async def _login(self) -> None:
        response = await self.client.post(
            "/api/v1/auth/login",
            json={"username": _TEST_USER, "password": _TEST_PASSWORD},
        )
        self.assertEqual(response.status_code, 200)

    async def test_kaggle_token_setup_can_be_skipped(self) -> None:
        await self._login()
        status = await self.client.get("/api/v1/kaggle-auth")
        self.assertTrue(status.json()["setup_required"])

        skipped = await self.client.post("/api/v1/kaggle-auth", json={"token": ""})

        self.assertEqual(skipped.status_code, 200)
        self.assertFalse(skipped.json()["configured"])
        self.assertIn("不能上传私有模型", skipped.json()["warning"])
        self.assertNotIn("KAGGLE_API_TOKEN", os.environ)
        self.assertFalse((await self.client.get("/api/v1/kaggle-auth")).json()["setup_required"])

    async def test_kaggle_token_is_validated_without_echoing_it(self) -> None:
        await self._login()
        token = "super-secret-access-token"
        fake = SimpleNamespace(whoami=lambda **kwargs: {"username": "owner"})
        with patch.dict("sys.modules", {"kagglehub": fake}):
            response = await self.client.post(
                "/api/v1/kaggle-auth", json={"token": token}
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"configured": True, "owner": "owner"})
        self.assertNotIn(token, response.text)
        self.assertEqual(os.environ["KAGGLE_API_TOKEN"], token)

    async def test_invalid_kaggle_token_is_removed_and_not_echoed(self) -> None:
        await self._login()
        token = "revoked-secret-token"
        fake = SimpleNamespace(
            whoami=lambda **kwargs: (_ for _ in ()).throw(RuntimeError(token))
        )
        with patch.dict("sys.modules", {"kagglehub": fake}):
            response = await self.client.post(
                "/api/v1/kaggle-auth", json={"token": token}
            )

        self.assertEqual(response.status_code, 400)
        self.assertNotIn(token, response.text)
        self.assertNotIn("KAGGLE_API_TOKEN", os.environ)

    async def test_auth_etag_and_resumable_upload(self) -> None:
        self.assertEqual((await self.client.get("/api/v1/jobs")).status_code, 401)
        login = await self.client.post(
            "/api/v1/auth/login",
            json={"username": _TEST_USER, "password": _TEST_PASSWORD},
        )
        self.assertEqual(login.status_code, 200)

        jobs = await self.client.get("/api/v1/jobs")
        self.assertEqual(jobs.status_code, 200)
        etag = jobs.headers["etag"]
        cached = await self.client.get(
            "/api/v1/jobs", headers={"If-None-Match": etag}
        )
        self.assertEqual(cached.status_code, 304)

        content = b"RIFF" + b"audio" * 300
        digest = hashlib.sha256(content).hexdigest()
        begin = await self.client.post(
            "/api/v1/uploads",
            json={
                "dataset": "DemoSet",
                "filename": "demo.wav",
                "size": len(content),
                "sha256": digest,
            },
        )
        self.assertEqual(begin.status_code, 201)
        upload_id = begin.json()["id"]
        part = await self.client.put(
            f"/api/v1/uploads/{upload_id}/parts/0",
            content=content,
            headers={"X-Part-SHA256": digest},
        )
        self.assertEqual(part.status_code, 200)
        status = await self.client.get(f"/api/v1/uploads/{upload_id}")
        self.assertEqual(status.json()["completed_parts"], [0])
        complete = await self.client.post(f"/api/v1/uploads/{upload_id}/complete")
        self.assertEqual(complete.status_code, 200)
        destination = control_app.TRAINING_AUDIO_DIR / "DemoSet" / "demo.wav"
        self.assertEqual(destination.read_bytes(), content)

    async def test_upload_quota_is_enforced(self) -> None:
        await self.client.post(
            "/api/v1/auth/login",
            json={"username": _TEST_USER, "password": _TEST_PASSWORD},
        )
        response = await self.client.post(
            "/api/v1/uploads",
            json={
                "dataset": "DemoSet",
                "filename": "too-large.wav",
                "size": control_app.MAX_UPLOAD_SIZE + 1,
            },
        )
        self.assertEqual(response.status_code, 413)

    async def test_token_is_bound_to_configured_user(self) -> None:
        expires = int(__import__("time").time()) + 60
        forged = control_app._token("other-user", expires)
        self.client.cookies.set(control_app.COOKIE_NAME, forged)
        response = await self.client.get("/api/v1/jobs")
        self.assertEqual(response.status_code, 401)

    async def test_weak_session_secret_fails_closed(self) -> None:
        os.environ["RVC_CONTROL_SECRET"] = "weak"
        response = await self.client.post(
            "/api/v1/auth/login",
            json={"username": _TEST_USER, "password": _TEST_PASSWORD},
        )
        self.assertEqual(response.status_code, 503)


if __name__ == "__main__":
    unittest.main()
