import asyncio
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
from ultimate_rvc.control.frontend import HTML

_TEST_USER = "test_user"
_TEST_PASSWORD = secrets.token_urlsafe(16)
_TEST_SECRET = secrets.token_urlsafe(32)


class ControlFrontendTest(unittest.TestCase):
    def test_interactive_training_controls_are_wired(self) -> None:
        self.assertIn('id="clean-strength" type="number"', HTML)
        self.assertIn("el.dataset.field==='detect-overtrain'", HTML)
        self.assertIn("$('#overtrain-threshold')", HTML)
        self.assertIn("fmt(p.elapsed_seconds)", HTML)
        self.assertIn("selectModel('model'", HTML)
        self.assertIn("confirmDataset()", HTML)
        self.assertIn('id="side-stage-card"', HTML)
        self.assertIn("function renderStageCard()", HTML)
        self.assertIn("/api/v1/datasets/confirm", HTML)


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
        self.assertEqual(
            response.json(),
            {"configured": True, "owner": "owner", "resume_dataset": None},
        )
        self.assertNotIn(token, response.text)
        self.assertEqual(os.environ["KAGGLE_API_TOKEN"], token)

    async def test_training_history_requires_explicit_restore(self) -> None:
        await self._login()
        os.environ["RVC_RESUME_DATASET"] = "owner/rvc-voice-resume"
        downloads: list[tuple[tuple, dict]] = []
        fake = SimpleNamespace(
            whoami=lambda **kwargs: {"username": "owner"},
            dataset_download=lambda *args, **kwargs: downloads.append((args, kwargs))
            or str(Path(self.temporary.name) / "resume_download"),
        )
        with patch.dict("sys.modules", {"kagglehub": fake}):
            configured = await self.client.post(
                "/api/v1/kaggle-auth", json={"token": "secret"}
            )
            self.assertEqual(configured.status_code, 200)
            self.assertEqual(configured.json()["resume_dataset"], "owner/rvc-voice-resume")
            self.assertEqual(downloads, [])
            self.assertNotIn("RVC_RESUME_ROOT", os.environ)

            restored = await self.client.post(
                "/api/v1/resume", json={"dataset": "owner/rvc-voice-resume"}
            )

        self.assertEqual(restored.status_code, 200)
        self.assertEqual(restored.json(), {"dataset": "owner/rvc-voice-resume", "status": "ready"})
        self.assertEqual(downloads[0][0], ("owner/rvc-voice-resume",))
        self.assertTrue(downloads[0][1]["force_download"])
        self.assertIn("RVC_RESUME_ROOT", os.environ)

    async def test_dataset_confirm_registers_and_appears_in_options(self) -> None:
        await self._login()
        with patch(
            "ultimate_rvc.control.registry.REGISTRY_PATH",
            Path(self.temporary.name) / "registry.json",
        ):
            response = await self.client.post(
                "/api/v1/datasets/confirm", json={"name": "MyDataset"}
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["dataset"], "MyDataset")

            options = await self.client.get("/api/v1/options")
            self.assertEqual(options.status_code, 200)
            body = options.json()
            models = {item["name"]: item for item in body["models"]}
            self.assertIn("MyDataset", models)
            self.assertIn("stages", models["MyDataset"])
            self.assertIn("preprocess", models["MyDataset"]["stages"])
            self.assertIn("progress", body)

            rejected = await self.client.post(
                "/api/v1/datasets/confirm", json={"name": "bad/name"}
            )
            self.assertEqual(rejected.status_code, 400)

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

    async def test_auth_etag_and_direct_upload(self) -> None:
        session = await self.client.get("/api/v1/session")
        self.assertEqual(session.status_code, 200)
        self.assertFalse(session.json()["authenticated"])
        self.assertEqual((await self.client.get("/favicon.ico")).status_code, 204)
        self.assertEqual((await self.client.get("/api/v1/jobs")).status_code, 401)
        login = await self.client.post(
            "/api/v1/auth/login",
            json={"username": _TEST_USER, "password": _TEST_PASSWORD},
        )
        self.assertEqual(login.status_code, 200)
        self.assertTrue((await self.client.get("/api/v1/session")).json()["authenticated"])

        jobs = await self.client.get("/api/v1/jobs")
        self.assertEqual(jobs.status_code, 200)
        etag = jobs.headers["etag"]
        cached = await self.client.get(
            "/api/v1/jobs", headers={"If-None-Match": etag}
        )
        self.assertEqual(cached.status_code, 304)

        content = b"RIFF" + b"audio" * 300
        begin = await self.client.post(
            "/api/v1/uploads/direct",
            json={
                "dataset": "DemoSet",
                "filename": "demo.wav",
                "size": len(content),
            },
        )
        self.assertEqual(begin.status_code, 201)
        upload_id = begin.json()["id"]
        self.assertEqual(begin.json()["received"], 0)
        self.assertEqual(begin.json()["status"], "uploading")
        uploaded = await self.client.put(
            f"/api/v1/uploads/direct/{upload_id}",
            content=content,
        )
        self.assertEqual(uploaded.status_code, 200)
        self.assertEqual(uploaded.json()["sha256"], hashlib.sha256(content).hexdigest())
        status = await self.client.get(f"/api/v1/uploads/{upload_id}")
        self.assertEqual(status.json()["received"], len(content))
        self.assertEqual(status.json()["status"], "completed")
        self.assertFalse((control_app.UPLOADS_DIR / upload_id / "parts").exists())
        destination = control_app.TRAINING_AUDIO_DIR / "DemoSet" / "demo.wav"
        self.assertEqual(destination.read_bytes(), content)

    async def test_upload_quota_is_enforced(self) -> None:
        await self.client.post(
            "/api/v1/auth/login",
            json={"username": _TEST_USER, "password": _TEST_PASSWORD},
        )
        response = await self.client.post(
            "/api/v1/uploads/direct",
            json={
                "dataset": "DemoSet",
                "filename": "too-large.wav",
                "size": control_app.MAX_UPLOAD_SIZE + 1,
            },
        )
        self.assertEqual(response.status_code, 413)

    async def test_upload_progress_does_not_wait_for_stream_lock(self) -> None:
        await self._login()
        first = b"RIFF" + b"a" * 32
        rest = b"b" * 32
        begin = await self.client.post(
            "/api/v1/uploads/direct",
            json={
                "dataset": "DemoSet",
                "filename": "paused.wav",
                "size": len(first) + len(rest),
            },
        )
        self.assertEqual(begin.status_code, 201)
        upload_id = begin.json()["id"]
        release = asyncio.Event()

        class PausingStream(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield first
                await release.wait()
                yield rest

        upload_task = asyncio.create_task(
            self.client.put(
                f"/api/v1/uploads/direct/{upload_id}",
                content=PausingStream(),
            )
        )
        temporary = control_app.UPLOADS_DIR / upload_id / ".uploading"
        for _ in range(100):
            if temporary.exists():
                break
            await asyncio.sleep(0.01)
        else:
            self.fail("上传流未开始")

        progress = await asyncio.wait_for(
            self.client.post(
                f"/api/v1/uploads/direct/{upload_id}/progress",
                json={"received": len(first)},
            ),
            timeout=1,
        )
        self.assertEqual(progress.status_code, 200)
        self.assertGreaterEqual(progress.json()["received"], len(first))

        release.set()
        uploaded = await upload_task
        self.assertEqual(uploaded.status_code, 200)
        status = await self.client.get(f"/api/v1/uploads/{upload_id}")
        self.assertEqual(status.json()["status"], "completed")

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
