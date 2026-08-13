"""
Web application for the Ultimate RVC project (Training Only).
"""

from __future__ import annotations

from typing import Annotated

import json
import os
import re
import signal
import time
import urllib.parse
from html import escape
from pathlib import Path
from os.path import basename

import gradio as gr
import requests
from fastapi import HTTPException, Request
from fastapi.responses import FileResponse

import typer

from ultimate_rvc.common import AUDIO_DIR, MODELS_DIR, TEMP_DIR, TRAINING_MODELS_DIR
from ultimate_rvc.core.manage.audio import get_audio_datasets, get_named_audio_datasets
from ultimate_rvc.core.manage.config import get_config_names, load_config
from ultimate_rvc.core.manage.models import (
    get_custom_embedder_model_names,
    get_custom_pretrained_model_names,
    get_training_model_names,
)
from ultimate_rvc.web.common import initialize_dropdowns
from ultimate_rvc.web.config.main import TotalConfig
from ultimate_rvc.rvc.train.delivery import (
    atomic_json_dump,
    delivery_files,
    prepare_delivery_files,
    validate_delivery,
    validate_model_name,
)
from ultimate_rvc.rvc.train.progress import TERMINAL_PHASES, read_progress
from ultimate_rvc.web.tabs.train.multi_step_generation import (
    render as render_training_tab,
)

config_name = os.environ.get("URVC_CONFIG")
total_config = load_config(config_name, TotalConfig) if config_name else TotalConfig()


RVC_PROGRESS_JS = r"""
() => {
  if (window.__rvcProgressPoller) return;
  const state = window.__rvcProgressPoller = {timer: null, failures: 0, unauthorized: false, wasTraining: false, lastData: {history: []}};
  const $ = (root, role) => root && root.querySelector(`[data-role="${role}"]`);
  const fmt = (seconds) => {
    const value = Math.max(0, Math.round(Number(seconds) || 0));
    return [Math.floor(value / 3600), Math.floor(value % 3600 / 60), value % 60]
      .map(n => String(n).padStart(2, '0')).join(':');
  };
  const setText = (node, value) => { if (node) node.textContent = value; };
  const render = (p, data) => {
    document.querySelectorAll('[data-rvc-progress]').forEach(root => {
      const pct = Math.max(0, Math.min(100, Number(p.percent) || 0));
      setText($(root, 'model'), p.model_name || '等待任务');
      setText($(root, 'phase'), p.phase_label || '等待训练开始');
      setText($(root, 'percent'), `${pct.toFixed(1)}%`);
      const bar = $(root, 'bar'); if (bar) bar.style.width = `${pct}%`;
      setText($(root, 'epoch'), `${Number(p.epoch)||0} / ${Number(p.total_epochs)||0}`);
      setText($(root, 'batch'), p.total_batches ? `${Number(p.batch)||0} / ${p.total_batches}` : '--');
      setText($(root, 'elapsed'), fmt(p.elapsed_seconds));
      setText($(root, 'eta'), p.eta_seconds ? fmt(p.eta_seconds) : '--:--:--');
      setText($(root, 'loss'), `G ${Number(p.loss_g||0).toFixed(4)} · D ${Number(p.loss_d||0).toFixed(4)}`);
      const alert = $(root, 'alert');
      const message = state.unauthorized ? '登录已失效，请刷新页面重新登录。' :
        state.failures >= 3 ? '无法连接进度服务，正在自动重试。' :
        p.error ? `训练失败：${p.error}` : p.warning || (p.stale ? '超过 30 秒没有训练心跳，训练可能已中断。' : '');
      if (alert) { alert.hidden = !message; alert.textContent = message; }
      const log = $(root, 'log');
      if (log) log.textContent = Array.isArray(p.recent_log) ? p.recent_log.slice(-20).join('\n') : '';
    });
    const history = document.querySelector('[data-role="history"]');
    if (history) {
      history.replaceChildren();
      (data.history || []).forEach(item => {
        const row = document.createElement('div'); row.className = 'rvc-history-row';
        const name = document.createElement('strong'); name.textContent = item.model_name || '';
        const phase = document.createElement('span'); phase.textContent = item.phase_label || '';
        const percent = document.createElement('span'); percent.textContent = `${Number(item.percent||0).toFixed(1)}%`;
        row.append(name, phase, percent); history.append(row);
      });
    }
  };
  const schedule = () => {
    clearTimeout(state.timer);
    if (!state.unauthorized) state.timer = setTimeout(poll, document.hidden ? 10000 : 2000);
  };
  const poll = async () => {
    try {
      const response = await fetch('/api/progress', {cache: 'no-store'});
      if (response.status === 401) { state.unauthorized = true; const d=state.lastData; render(d.active&&d.models[d.active]||{}, d); return; }
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json(); state.failures = 0; state.lastData = data;
      const p = data.active && data.models[data.active] ? data.models[data.active] : {};
      render(p, data);
      if (data.active_training && !state.wasTraining) {
        const tab = document.querySelector('#progress-tab-button, button[aria-controls="progress-tab"]');
        if (tab) tab.click();
      }
      state.wasTraining = !!data.active_training;
      const train = document.querySelector('#rvc-train-btn'), stop = document.querySelector('#rvc-stop-train-btn');
      if (train) train.style.display = data.active_training ? 'none' : '';
      if (stop) stop.style.display = data.active_training ? '' : 'none';
      const select = document.getElementById('result-model-select');
      if (select) {
        const names = Array.isArray(data.model_names) ? data.model_names : [];
        if (select.dataset.rvcModels !== names.join('\n')) {
          const current = select.value; select.replaceChildren();
          (names.length ? names : ['']).forEach(value => { const option = document.createElement('option'); option.value=value; option.textContent=value||'暂无模型'; select.append(option); });
          select.dataset.rvcModels = names.join('\n'); if (names.includes(current)) select.value = current;
        }
      }
    } catch (_) { state.failures += 1; if (state.failures >= 3) { const d=state.lastData; render(d.active&&d.models[d.active]||{}, d); } }
    schedule();
  };
  document.addEventListener('visibilitychange', () => { if (!document.hidden && !state.unauthorized) poll(); });
  document.addEventListener('change', async event => {
    const select = event.target.closest('#result-model-select'); if (!select) return;
    try { const response = await fetch('/api/downloads?model='+encodeURIComponent(select.value), {cache:'no-store'}); if (!response.ok) return; const data=await response.json(); const target=document.querySelector('#result-downloads'); if(target) target.innerHTML=data.html||''; } catch (_) {}
  });
  document.addEventListener('click', async event => {
    if (event.target.closest('#rvc-train-btn')) setTimeout(() => {
      const tab=document.querySelector('#progress-tab-button, button[aria-controls="progress-tab"]'); if(tab) tab.click();
    }, 100);
    const cleanup=event.target.closest('#rvc-cleanup-btn'); if(!cleanup) return;
    try { const response=await fetch('/api/cleanup',{method:'POST'}); const data=await response.json(); const count=(data.killed||[]).length; cleanup.textContent=count?`已清理 ${count} 个残留训练进程`:'无残留进程需要清理'; setTimeout(()=>cleanup.textContent='清理残留训练进程',3000); } catch (_) { cleanup.textContent='清理失败，请稍后重试'; }
  });
  const year = document.getElementById('rvc-footer-year'); if (year) year.textContent = new Date().getFullYear();
  poll();
}
"""


def _get_model_names() -> list[str]:
    if not TRAINING_MODELS_DIR.is_dir():
        return []
    return sorted(
        d.name for d in TRAINING_MODELS_DIR.iterdir()
        if d.is_dir() and (d / "progress.json").is_file()
    )


def _get_completed_model_names() -> list[str]:
    """Return only completed models that passed the delivery gate."""
    completed = []
    for name in _get_model_names():
        try:
            with (TRAINING_MODELS_DIR / name / "progress.json").open("r", encoding="utf-8") as f:
                delivery_path = TRAINING_MODELS_DIR / name / "delivery.json"
                if json.load(f).get("done", False) and delivery_path.is_file():
                    completed.append(name)
        except (OSError, ValueError, TypeError):
            continue
    return completed


def _require_api_login(request: Request) -> None:
    """Apply Gradio's cookie authentication to custom FastAPI routes."""
    auth = getattr(app.app, "auth", None)
    if auth is None:
        return
    tokens = getattr(app.app, "tokens", {}) or {}
    if tokens.get(request.cookies.get("access-token")) is None:
        raise HTTPException(status_code=401, detail="Not authenticated")


def _api_progress(request: Request) -> dict:
    """Return progress data for lightweight browser polling."""
    _require_api_login(request)
    models = {}
    candidates = []
    if TRAINING_MODELS_DIR.is_dir():
        for model_dir in TRAINING_MODELS_DIR.iterdir():
            progress_path = model_dir / "progress.json"
            if not model_dir.is_dir() or not progress_path.is_file():
                continue
            try:
                mtime = progress_path.stat().st_mtime
                progress = read_progress(progress_path)
                progress["model_name"] = model_dir.name
                progress.setdefault("updated_at", mtime)
                progress.setdefault("heartbeat_at", mtime)
                progress["stale"] = (
                    progress.get("phase") not in TERMINAL_PHASES
                    and time.time() - float(progress.get("heartbeat_at", mtime)) > 30
                )
                models[model_dir.name] = progress
                candidates.append((model_dir.name, mtime))
            except (OSError, ValueError):
                continue
    live_names = []
    for name, _mtime in candidates:
        if models[name].get("phase") in TERMINAL_PHASES:
            continue
        try:
            config = json.loads(
                (TRAINING_MODELS_DIR / name / "config.json").read_text("utf-8")
            )
            for pid in config.get("process_pids", []):
                try:
                    os.kill(int(pid), 0)
                    live_names.append(name)
                    break
                except (ProcessLookupError, PermissionError, ValueError):
                    continue
        except (OSError, ValueError, TypeError):
            pass
    choices = live_names or [name for name, _mtime in candidates]
    active_name = max(
        choices,
        key=lambda name: float(models[name].get("updated_at", 0)),
        default=None,
    )
    active_training = False
    if active_name:
        active_dir = TRAINING_MODELS_DIR / active_name
        if not (active_dir / "stop_requested").is_file():
            try:
                with (active_dir / "config.json").open("r", encoding="utf-8") as f:
                    pids = json.load(f).get("process_pids", [])
                for pid in pids:
                    try:
                        os.kill(int(pid), 0)
                        active_training = True
                        break
                    except (ProcessLookupError, PermissionError, ValueError):
                        continue
            except (OSError, ValueError, TypeError):
                pass
    return {
        "active": active_name,
        "active_training": active_training,
        "models": models,
        "history": sorted(
            models.values(),
            key=lambda item: float(item.get("updated_at", 0)),
            reverse=True,
        ),
        "model_names": _get_completed_model_names(),
    }


def _api_downloads(request: Request, model: str = "") -> dict[str, str]:
    """Return download markup for one model without opening a Gradio event stream."""
    _require_api_login(request)
    if model not in _get_completed_model_names():
        return {"html": _build_download_html(None)}
    return {"html": _build_download_html(model)}


def _api_download_file(request: Request, model: str, kind: str) -> FileResponse:
    """Stream one validated delivery artifact from the current Kaggle session."""
    _require_api_login(request)
    try:
        name = validate_model_name(model)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if name not in _get_completed_model_names() or kind not in {"pth", "index", "log"}:
        raise HTTPException(status_code=404, detail="模型或文件不存在")
    path = delivery_files(TRAINING_MODELS_DIR / name, name)[kind]
    if not path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(path, filename=path.name, media_type="application/octet-stream")


KAGGLE_API = "https://www.kaggle.com/api/v1"
UPLOAD_TIMEOUT = 600


def _post_multipart(
    url: str,
    field: str,
    file_path: str,
    upload_name: str | None = None,
    data: dict | None = None,
    headers: dict | None = None,
    auth: tuple | None = None,
    timeout: int = UPLOAD_TIMEOUT,
) -> requests.Response | None:
    """POST a file as multipart and return the response, or None on failure."""
    try:
        with open(file_path, "rb") as f:
            return requests.post(
                url,
                data=data or {},
                files={field: (upload_name or basename(file_path), f)},
                headers=headers,
                auth=auth,
                timeout=timeout,
            )
    except Exception as e:  # noqa: BLE001
        print(f"[Upload] POST {url} failed: {e}")
        return None


def _kaggle_backend_available() -> bool:
    """Kaggle kernels auto-inject these env vars; local CLI users have them too."""
    return bool(os.environ.get("KAGGLE_USERNAME")) and bool(
        os.environ.get("KAGGLE_KEY")
    )


def _upload_to_kaggle_dataset(
    model_dir: Path,
    model_name: str,
    files: list[tuple[str, str]],
) -> dict[str, str] | None:
    """Upload model files (pth / index / log) as a private Kaggle dataset."""
    if not _kaggle_backend_available():
        print("[Kaggle] KAGGLE_USERNAME/KAGGLE_KEY 未设置，跳过数据集上传")
        return None
    username = os.environ["KAGGLE_USERNAME"]
    auth = (username, os.environ["KAGGLE_KEY"])
    base = re.sub(r"[^a-zA-Z0-9]+", "-", model_name.lower()).strip("-") or "rvc-model"
    slug = f"{base[:40]}-{int(time.time())}"
    tokens: list[dict[str, str]] = []
    for local_filename, download_filename in files:
        fpath = model_dir / local_filename
        if not fpath.is_file():
            continue
        resp = _post_multipart(
            f"{KAGGLE_API}/datasets/new/upload/file?fileName={urllib.parse.quote(download_filename)}",
            "file",
            str(fpath),
            download_filename,
            auth=auth,
        )
        if not resp or resp.status_code != 200:
            print(
                f"[Kaggle] file upload failed ({download_filename}): "
                f"{resp.status_code if resp else 'no response'}"
            )
            continue
        try:
            tokens.append({"token": resp.json()["token"]})
        except (ValueError, KeyError):
            print(f"[Kaggle] unexpected upload response: {resp.text[:200]}")
            continue
    if not tokens:
        print("[Kaggle] 没有任何文件上传成功")
        return None
    payload = {
        "ownerSlug": username,
        "slug": slug,
        "title": f"RVC {model_name}",
        "subtitle": "RVC trained voice model",
        "description": f"RVC {model_name} model (auto-uploaded)",
        "isPrivate": True,
        "licenseName": "other",
        "keywords": [],
        "collaborators": [],
        "sources": [],
        "resources": tokens,
        "data": tokens,
    }
    try:
        resp = requests.post(
            f"{KAGGLE_API}/datasets/create/new",
            json=payload,
            auth=auth,
            timeout=120,
        )
    except Exception as e:  # noqa: BLE001
        print(f"[Kaggle] create failed: {e}")
        return None
    if resp.status_code not in (200, 201):
        print(f"[Kaggle] create failed: {resp.status_code} {resp.text[:200]}")
        return None
    try:
        view = requests.get(
            f"{KAGGLE_API}/datasets/view/{username}/{slug}",
            auth=auth,
            timeout=60,
        )
        if view.status_code != 200:
            print(f"[Kaggle] verify failed: {view.status_code}")
            return None
    except Exception as e:  # noqa: BLE001
        print(f"[Kaggle] verify failed: {e}")
        return None
    return {
        "url": f"https://www.kaggle.com/datasets/{username}/{slug}",
        "slug": f"{username}/{slug}",
    }


def _get_kaggle_urls(model_name: str) -> dict[str, str]:
    """读取某个模型的 Kaggle Dataset 缓存链接。"""
    url_file = TRAINING_MODELS_DIR / model_name / "kaggle_urls.json"
    if url_file.is_file():
        try:
            with open(url_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {
                    key: value for key, value in data.items()
                    if key in {"kaggle", "kaggle_slug"} and isinstance(value, str)
                }
        except (OSError, ValueError, TypeError):
            pass
    return {}


def _save_kaggle_urls(model_name: str, urls: dict[str, str]) -> None:
    """写入某个模型的 Kaggle Dataset 缓存链接。"""
    url_file = TRAINING_MODELS_DIR / model_name / "kaggle_urls.json"
    atomic_json_dump(urls, url_file)


def _training_is_complete(model_dir: Path) -> bool:
    try:
        with (model_dir / "progress.json").open("r", encoding="utf-8") as f:
            return bool(json.load(f).get("done", False))
    except (OSError, ValueError, TypeError):
        return False


def upload_model_to_kaggle(model_name: str) -> dict[str, str | list[str]]:
    """Validate and upload the three inference artifacts to a private dataset."""
    try:
        model_name = validate_model_name(model_name)
    except ValueError as error:
        return {"errors": [str(error)]}
    model_dir = TRAINING_MODELS_DIR / model_name
    if not model_dir.is_dir() or not _training_is_complete(model_dir):
        return {"errors": ["训练未完成"]}
    if (model_dir / "stop_requested").is_file():
        return {"errors": ["训练已停止，不上传未完成模型"]}
    index_path = model_dir / f"{model_name}.index"
    if not index_path.is_file():
        try:
            from ultimate_rvc.rvc.train.process.extract_index import main as extract_index
            extract_index(str(model_dir), "Auto")
        except Exception as error:  # noqa: BLE001
            return {"errors": [f"{index_path.name} 生成失败：{error}"]}
    try:
        files = prepare_delivery_files(model_dir, model_name)
        validate_delivery(model_dir, model_name)
    except Exception as error:  # noqa: BLE001
        return {"errors": [f"本地推理兼容性校验失败：{error}"]}
    cached = _get_kaggle_urls(model_name)
    if cached.get("kaggle"):
        return cached
    kaggle_files = [(path.name, path.name) for path in files.values()]
    missing = [
        local for local, _ in kaggle_files if not (model_dir / local).is_file()
    ]
    if missing:
        return {"errors": [f"{name} 不存在" for name in missing]}
    result = _upload_to_kaggle_dataset(model_dir, model_name, kaggle_files)
    if not result:
        return {"errors": ["Kaggle 数据集上传失败，请稍后在 Result 页面重试"]}
    urls = {"kaggle": result["url"], "kaggle_slug": result["slug"]}
    _save_kaggle_urls(model_name, urls)
    return urls


def _repair_all_models() -> dict[str, object]:
    """Create missing indexes and upload every completed usable model."""
    repaired: list[str] = []
    incomplete: dict[str, list[str]] = {}
    for model_name in _get_model_names():
        model_dir = TRAINING_MODELS_DIR / model_name
        if not _training_is_complete(model_dir):
            continue
        missing: list[str] = []
        pth_path = model_dir / f"{model_name}_best.pth"
        index_path = model_dir / f"{model_name}.index"
        if not pth_path.is_file():
            missing.append(f"{pth_path.name}（无法自动恢复）")
        if not index_path.is_file() and pth_path.is_file():
            try:
                from ultimate_rvc.rvc.train.process.extract_index import main as extract_index
                extract_index(str(model_dir), "Auto")
            except Exception as error:
                missing.append(f"{index_path.name}（生成失败：{error}）")
        if not index_path.is_file():
            missing.append(f"{index_path.name}（无法生成）")
        if not (model_dir / "train.log").is_file():
            missing.append("train.log（未找到，不自动补全）")
            # train.log is informational only; it does not block model upload.
            log_missing = True
        else:
            log_missing = False
        core_missing = [item for item in missing if not item.startswith("train.log")]
        if core_missing:
            incomplete[model_name] = missing
            continue
        result = upload_model_to_kaggle(model_name)
        if "errors" in result:
            incomplete[model_name] = missing + [str(item) for item in result["errors"]]
        else:
            repaired.append(model_name)
            if log_missing:
                incomplete[model_name] = missing
    return {"repaired": repaired, "incomplete": incomplete}


def _api_repair_models() -> dict[str, object]:
    return _repair_all_models()


def _cleanup_finished_training() -> dict[str, object]:
    """Kill leftover trainer processes for models whose training is done or stopped."""
    killed: list[int] = []
    if not TRAINING_MODELS_DIR.is_dir():
        return {"killed": killed}
    for model_dir in TRAINING_MODELS_DIR.iterdir():
        if not model_dir.is_dir():
            continue
        if not (model_dir / "config.json").is_file():
            continue
        done = _training_is_complete(model_dir)
        stopped = (model_dir / "stop_requested").is_file()
        if not (done or stopped):
            continue
        try:
            with (model_dir / "config.json").open("r", encoding="utf-8") as f:
                pids = json.load(f).get("process_pids", [])
        except (OSError, ValueError, TypeError):
            continue
        for pid in pids:
            try:
                os.kill(int(pid), 0)
            except (ProcessLookupError, ValueError, TypeError):
                continue
            try:
                os.kill(int(pid), signal.SIGTERM)
                killed.append(int(pid))
            except (PermissionError, ProcessLookupError, OSError):
                pass
    return {"killed": killed}


def _api_cleanup(request: Request) -> dict[str, object]:
    _require_api_login(request)
    return _cleanup_finished_training()


def _build_download_html(model_name: str | None) -> str:
    """Build direct links for the three validated delivery files."""
    if not model_name:
        return (
            '<div style="text-align:center;padding:30px;color:rgba(44,47,54,.35);">'
            '<div style="font-size:14px;">选择模型后显示下载链接</div></div>'
        )
    try:
        model_name = validate_model_name(model_name)
        validation = json.loads(
            (TRAINING_MODELS_DIR / model_name / "delivery.json").read_text("utf-8")
        )
    except (ValueError, OSError, json.JSONDecodeError):
        return '<div style="padding:18px;color:#b42318;">模型尚未通过本地推理兼容性校验。</div>'
    buttons = []
    labels = {"pth": "下载 .pth", "index": "下载 .index", "log": "下载 train.log"}
    for kind in ("pth", "index", "log"):
        meta = validation.get("files", {}).get(kind, {})
        size_mb = float(meta.get("size", 0)) / 1024 / 1024
        buttons.append(
            f'<a href="/api/files/{escape(model_name, quote=True)}/{kind}" '
            f'style="display:inline-flex;padding:10px 16px;margin:4px;color:#fff;'
            f'background:#176b57;border-radius:6px;text-decoration:none;font-weight:600;">'
            f'{labels[kind]} ({size_mb:.1f} MB)</a>'
        )
    urls = _get_kaggle_urls(model_name)
    kaggle_url = urls.get("kaggle")
    kaggle_slug = urls.get("kaggle_slug")
    remote = ""
    if kaggle_url:
        slug_display = escape(kaggle_slug) if kaggle_slug else escape(kaggle_url)
        remote = (
            f'<div style="margin-top:10px;font-size:12px;color:#666;">私有 Kaggle Dataset：'
            f'<a href="{escape(kaggle_url, quote=True)}" target="_blank">{slug_display}</a></div>'
        )
    return (
        f'<div style="padding:12px;">'
        f'<div style="font-size:13px;color:rgba(44,47,54,.55);margin-bottom:10px;">'
        f'<b>{escape(model_name)}</b> · RVC v2 / 48k / F0，已通过结构和索引校验。</div>'
        f'{"".join(buttons)}{remote}'
        f'</div>'
    )


def _build_result_model_selector() -> str:
    options = _get_model_names()
    if not options:
        options_html = '<option value="">暂无模型</option>'
    else:
        options_html = ''.join(
            f'<option value="{escape(name, quote=True)}">{escape(name)}</option>'
            for name in options
        )
    return (
        '<label for="result-model-select" style="display:block;font-size:13px;'
        'font-weight:600;margin:0 0 7px;color:rgba(44,47,54,.72);">选择模型</label>'
        f'<select id="result-model-select" style="width:100%;padding:10px 12px;'
        'border:1px solid rgba(0,0,0,.12);border-radius:9px;background:#fff;'
        'font-size:14px;box-sizing:border-box;">'
        f'{options_html}</select>'
    )


def _build_result_html() -> str:
    models_dir = TRAINING_MODELS_DIR
    if not models_dir.is_dir():
        return (
            '<div style="text-align:center;padding:60px 20px;color:rgba(44,47,54,.35);">'
            '<div style="font-size:48px;margin-bottom:16px;animation:lm-float 4s ease-in-out infinite;">&#127925;</div>'
            '<div style="font-size:16px;">暂无训练模型</div>'
            '<div style="font-size:13px;margin-top:8px;color:rgba(44,47,54,.25);">开始训练后这里会自动显示进度</div></div>'
        )
    html = ""
    for model_dir in sorted(models_dir.iterdir()):
        if not model_dir.is_dir():
            continue
        name = model_dir.name
        progress_path = model_dir / "progress.json"
        if progress_path.is_file():
            try:
                with open(progress_path, "r") as f:
                    p = json.load(f)
                epoch = p.get("epoch", 0)
                total = p.get("total", 0)
                loss_g = p.get("loss_g", 0)
                loss_d = p.get("loss_d", 0)
                best_loss = p.get("best_loss", 0)
                best_epoch = p.get("best_epoch", 0)
                done = p.get("done", False)
                recent_times = p.get("recent_epoch_times", [])
                pct = round(epoch / total * 100) if total > 0 else 0

                eta_str = ""
                if not done and recent_times and total > epoch:
                    avg_time = sum(recent_times) / len(recent_times)
                    remaining = (total - epoch) * avg_time
                    h = int(remaining // 3600)
                    m = int((remaining % 3600) // 60)
                    s = int(remaining % 60)
                    eta_str = f"{h:02d}:{m:02d}:{s:02d}"
                if done:
                    badge = '<span style="background:rgba(43,133,181,.1);color:#2b85b5;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600;letter-spacing:.5px;">已完成</span>'
                    bar_gradient = "linear-gradient(90deg,#2b85b5,#4fb8e8)"
                    pct_color = "#2b85b5"
                    avatar_bg = "background:linear-gradient(135deg,rgba(79,182,255,.15),rgba(93,212,184,.1));border:1px solid rgba(79,182,255,.15);"
                    avatar_stroke = "#2b85b5"
                else:
                    badge = '<span style="background:rgba(29,138,106,.1);color:#1d8a6a;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600;letter-spacing:.5px;">训练中</span>'
                    bar_gradient = "linear-gradient(90deg,#1d8a6a,#38b08a)"
                    pct_color = "#1d8a6a"
                    avatar_bg = "background:linear-gradient(135deg,rgba(29,138,106,.15),rgba(56,176,138,.1));border:1px solid rgba(29,138,106,.15);"
                    avatar_stroke = "#1d8a6a"
                html += f'''
                <div class="lm-card lm-fade">
                    <div style="display:flex;align-items:center;gap:14px;margin-bottom:16px;">
                        <div style="width:46px;height:46px;border-radius:14px;{avatar_bg}display:flex;align-items:center;justify-content:center;animation:lm-float 4s ease-in-out infinite;">
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="{avatar_stroke}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/></svg>
                        </div>
                        <div style="flex:1;">
                            <div style="font-size:18px;font-weight:700;color:#2c2f36;">{name}</div>
                            <div style="margin-top:4px;">{badge}</div>
                        </div>
                        <div style="text-align:right;">
                            <div style="font-size:30px;font-weight:800;color:{pct_color};line-height:1;">{pct}%</div>
                            <div style="font-size:12px;color:rgba(44,47,54,.4);margin-top:2px;">{epoch} / {total} 轮</div>
                            {'<div style="font-size:11px;color:rgba(44,47,54,.35);margin-top:4px;">⏱ 预计剩余 ' + eta_str + '</div>' if eta_str else ''}
                        </div>
                    </div>
                    <div style="background:rgba(0,0,0,.05);border-radius:10px;height:10px;width:100%;overflow:hidden;">
                        <div style="background:{bar_gradient};height:10px;border-radius:10px;width:{pct}%;transition:width .5s ease;"></div>
                    </div>
                    <div style="display:flex;gap:0;margin-top:14px;padding-top:14px;border-top:1px solid rgba(0,0,0,.05);">
                        <div style="flex:1;text-align:center;">
                            <div style="font-size:11px;color:rgba(44,47,54,.4);text-transform:uppercase;letter-spacing:1px;">生成器损失</div>
                            <div style="font-size:17px;font-weight:700;color:#2c2f36;margin-top:3px;">{loss_g:.4f}</div>
                        </div>
                        <div style="border-left:1px solid rgba(0,0,0,.05);"></div>
                        <div style="flex:1;text-align:center;">
                            <div style="font-size:11px;color:rgba(44,47,54,.4);text-transform:uppercase;letter-spacing:1px;">判别器损失</div>
                            <div style="font-size:17px;font-weight:700;color:#2c2f36;margin-top:3px;">{loss_d:.4f}</div>
                        </div>
                        <div style="border-left:1px solid rgba(0,0,0,.05);"></div>
                        <div style="flex:1;text-align:center;">
                            <div style="font-size:11px;color:rgba(44,47,54,.4);text-transform:uppercase;letter-spacing:1px;">最佳损失</div>
                            <div style="font-size:17px;font-weight:700;color:#1d8a6a;margin-top:3px;">{best_loss:.4f}</div>
                            <div style="font-size:10px;color:rgba(44,47,54,.3);">第 {best_epoch} 轮</div>
                        </div>
                    </div>
                </div>
                '''
            except Exception:
                continue
        else:
            html += (
                '<div class="lm-card lm-fade" style="opacity:.6;">'
                '<div style="display:flex;align-items:center;gap:14px;">'
                f'<div style="width:46px;height:46px;border-radius:14px;background:rgba(0,0,0,.04);border:1px dashed rgba(0,0,0,.1);display:flex;align-items:center;justify-content:center;animation:lm-float 4s ease-in-out infinite;">'
                f'<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#bbb" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>'
                f'</div>'
                f'<div><div style="font-size:18px;font-weight:700;color:#aaa;">{name}</div>'
                f'<div style="margin-top:4px;"><span style="background:rgba(0,0,0,.04);color:#bbb;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600;">等待训练</span></div></div></div></div>'
            )
    if not html:
        html = (
            '<div style="text-align:center;padding:60px 20px;color:rgba(44,47,54,.35);">'
            '<div style="font-size:48px;margin-bottom:16px;animation:lm-float 4s ease-in-out infinite;">&#127925;</div>'
            '<div style="font-size:16px;">暂无训练模型</div></div>'
        )
    return html


def render_app() -> gr.Blocks:
    css = """
    h1 { text-align: center; margin-top: 20px; margin-bottom: 20px; }
    #training-tab-button { font-weight: bold !important;}
    @keyframes lm-shimmer{0%{background-position:-200% center}100%{background-position:200% center}}
    @keyframes lm-float{0%,100%{transform:translateY(0)}50%{transform:translateY(-4px)}}
    .lm-card{background:rgba(255,255,255,.75)!important;border:1px solid rgba(0,0,0,.06)!important;backdrop-filter:blur(12px);border-radius:18px!important;padding:24px 28px!important;box-shadow:0 2px 16px rgba(0,0,0,.04)!important;transition:transform .4s cubic-bezier(.22,1,.36,1),box-shadow .4s ease!important;margin-bottom:20px!important;}
    .lm-card:hover{transform:translateY(-3px);box-shadow:0 12px 36px rgba(0,0,0,.08)!important;}
    .lm-btn{transition:all .35s cubic-bezier(.22,1,.36,1)!important;position:relative;overflow:hidden;display:inline-flex;align-items:center;gap:6px;padding:10px 22px;color:#fff;border-radius:11px;text-decoration:none;font-size:13px;font-weight:600;letter-spacing:.5px;}
    .lm-btn:hover{transform:translateY(-2px);filter:brightness(.95);}
    .lm-btn:active{transform:scale(.97);}
    .lm-green{background:linear-gradient(135deg,#1d8a6a,#38b08a);box-shadow:0 3px 16px rgba(29,138,106,.2);}
    .lm-blue{background:linear-gradient(135deg,#2b85b5,#4fb8e8);box-shadow:0 3px 16px rgba(43,133,181,.2);}
    .lm-card, .lm-card *{opacity:1!important;transition:none!important;}
    .lm-fade{opacity:1!important;}
    #result-cards{width:100%!important;max-width:100%!important;overflow-x:hidden!important;box-sizing:border-box!important;}
    #result-cards > div{width:100%!important;max-width:100%!important;box-sizing:border-box!important;overflow-x:hidden!important;}
    #result-cards .lm-card{width:100%!important;max-width:100%!important;box-sizing:border-box!important;overflow:hidden!important;}
    #result-cards *{box-sizing:border-box;max-width:100%;}
    .rvc-progress{padding:18px;border:1px solid rgba(0,0,0,.1);border-radius:8px;background:#fff;box-sizing:border-box}
    .rvc-progress-head{display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:12px}.rvc-progress-head strong{font-size:17px;overflow-wrap:anywhere}.rvc-progress-head span{font-size:13px;color:#1d715b}
    .rvc-progress-track{height:24px;border-radius:6px;background:#e7eaec;overflow:hidden;position:relative}.rvc-progress-track>div{height:100%;width:0;background:#21866b;transition:width .35s}.rvc-progress-track>b{position:absolute;inset:0;display:grid;place-items:center;font-size:12px;color:#202429}
    .rvc-progress-stats{display:grid;grid-template-columns:repeat(5,minmax(110px,1fr));gap:8px;margin-top:13px;font-size:12px;color:#687077}.rvc-progress-stats b{display:block;margin-top:3px;color:#292e33;font-size:13px}
    .rvc-progress-alert{margin-top:12px;padding:9px 11px;border:1px solid #dc9c3d;background:#fff8e8;color:#805410;border-radius:6px;font-size:13px}
    .rvc-progress-log{margin-top:12px;font-size:13px}.rvc-progress-log pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:230px;overflow:auto;background:#f5f6f7;padding:10px;border-radius:6px;font-size:11px}
    .rvc-history{margin-top:18px}.rvc-history-row{display:grid;grid-template-columns:minmax(120px,1fr) minmax(120px,1fr) 70px;gap:12px;padding:9px 4px;border-bottom:1px solid rgba(0,0,0,.07);font-size:13px}.rvc-history-row span:last-child{text-align:right}
    @media(max-width:720px){.rvc-progress-stats{grid-template-columns:repeat(2,minmax(0,1fr))}.rvc-progress-head{align-items:flex-start;flex-direction:column}.rvc-history-row{grid-template-columns:minmax(90px,1fr) minmax(100px,1fr) 55px}}
    footer.svelte-czcr5b,
    footer[class*="svelte-"]{display:none!important;}
    """
    cache_delete_frequency = 86400
    cache_delete_cutoff = 86400

    with gr.Blocks(
        title="Ultimate RVC - Training",
        theme=gr.Theme.load(str(Path(__file__).parent / "config/theme.json")),
        css=css,
        delete_cache=(cache_delete_frequency, cache_delete_cutoff),
        js=RVC_PROGRESS_JS,
    ) as app:
        gr.HTML("<h1>Ultimate RVC - Training Only</h1>")
        hidden_result_json = gr.Textbox(visible=False, elem_id="hd-result")
        hidden_download_json = gr.Textbox(visible=False, elem_id="hd-downloads")
        hidden_train_json = gr.Textbox(visible=False, elem_id="hd-train")

        for component_config in [
            total_config.training.multi_step.dataset,
            total_config.training.multi_step.preprocess_model,
            total_config.training.multi_step.extract_model,
            total_config.training.multi_step.train_model,
            total_config.training.multi_step.custom_embedder_model,
            total_config.training.multi_step.custom_pretrained_model,
        ]:
            component_config.instantiate()

        with gr.Tab("Training", elem_id="training-tab"):
            train_progress = render_training_tab(total_config)

        with gr.Tab("Progress", elem_id="progress-tab"):
            gr.HTML(
                '<div style="text-align:center;margin:20px auto 8px;">'
                '<div style="font-size:clamp(24px,3vw,32px);font-weight:900;letter-spacing:clamp(2px,.5vw,6px);background:linear-gradient(135deg,#2b85b5 0%,#1d8a6a 35%,#38b08a 65%,#2b85b5 100%);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;background-size:300% auto;animation:lm-shimmer 8s linear infinite;">训练进度</div>'
                '<div style="width:120px;height:1px;margin:16px auto 0;background:linear-gradient(90deg,transparent,rgba(42,160,130,.2),rgba(58,159,216,.2),transparent);"></div>'
                '</div>'
                '<div id="progress-panel" style="max-width:1100px;margin:20px auto;">'
                '<div class="rvc-progress" data-rvc-progress><div class="rvc-progress-head"><strong data-role="model">等待任务</strong><span data-role="phase">等待训练开始</span></div>'
                '<div class="rvc-progress-track"><div data-role="bar"></div><b data-role="percent">0.0%</b></div>'
                '<div class="rvc-progress-stats"><span>轮次<b data-role="epoch">0 / 0</b></span><span>批次<b data-role="batch">--</b></span><span>已用<b data-role="elapsed">00:00:00</b></span><span>剩余<b data-role="eta">--:--:--</b></span><span>损失<b data-role="loss">G 0.0000 · D 0.0000</b></span></div>'
                '<div class="rvc-progress-alert" data-role="alert" hidden></div><details class="rvc-progress-log"><summary>最近日志</summary><pre data-role="log"></pre></details></div>'
                '<div class="rvc-history"><h3>历史模型</h3><div data-role="history"></div></div>'
                '<div style="margin-top:16px;text-align:center;">'
                '<button id="rvc-cleanup-btn" type="button" style="padding:8px 18px;border:1px solid rgba(0,0,0,.12);border-radius:8px;background:#fff;color:#555;font-size:12px;cursor:pointer;">清理残留训练进程</button>'
                '</div>'
                '</div>'
            )

        with gr.Tab("Result"):
            gr.HTML("""
            <div style="text-align:center;margin-bottom:8px;">
                <div style="font-size:clamp(24px,3vw,32px);font-weight:900;letter-spacing:clamp(2px,.5vw,6px);background:linear-gradient(135deg,#2b85b5 0%,#1d8a6a 35%,#38b08a 65%,#2b85b5 100%);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;background-size:300% auto;animation:lm-shimmer 8s linear infinite;">模型下载</div>
                <div style="width:120px;height:1px;margin:16px auto 0;background:linear-gradient(90deg,transparent,rgba(42,160,130,.2),rgba(58,159,216,.2),transparent);"></div>
            </div>
            """)
            gr.HTML(_build_result_model_selector(), elem_id="result-model-selector")
            result_downloads = gr.HTML(value=_build_download_html(None), elem_id="result-downloads")


        gr.HTML(
            '<div id="rvc-footer" style="text-align:center;padding:20px 0 8px;color:rgba(44,47,54,.42);font-size:12px;letter-spacing:.3px;">'
            '<span id="rvc-footer-year"></span>&nbsp;&nbsp;·&nbsp;&nbsp;<a href="https://github.com/lingrana/rvc_train_kaggle" target="_blank" rel="noopener noreferrer" style="color:inherit;text-decoration:none;">@lingran</a>'
            '</div>'
        )

        app.load(
            _init_dropdowns,
            outputs=[
                total_config.training.multi_step.custom_embedder_model.instance,
                total_config.training.multi_step.custom_pretrained_model.instance,
                total_config.training.multi_step.extract_model.instance,
                total_config.training.multi_step.train_model.instance,
                total_config.training.multi_step.preprocess_model.instance,
                total_config.training.multi_step.dataset.instance,
            ],
            show_progress="hidden",
        )

    return app


def _init_dropdowns() -> list[gr.Dropdown]:
    custom_embedder_models = initialize_dropdowns(
        get_custom_embedder_model_names,
        1,
        value_indices=range(1),
    )
    custom_pretrained_models = initialize_dropdowns(
        get_custom_pretrained_model_names,
        1,
        value_indices=range(1),
    )
    training_models = initialize_dropdowns(
        get_training_model_names,
        3,
        value_indices=range(2),
    )
    dataset = gr.Dropdown(get_audio_datasets())
    return [
        *custom_embedder_models,
        *custom_pretrained_models,
        *training_models,
        dataset,
    ]


def _register_api_routes() -> None:
    """Register custom routes even if Gradio rebuilds its FastAPI app on launch."""
    existing = {getattr(route, "path", None) for route in app.app.routes}
    if "/api/progress" not in existing:
        app.app.add_api_route("/api/progress", _api_progress, methods=["GET"])
    if "/api/downloads" not in existing:
        app.app.add_api_route("/api/downloads", _api_downloads, methods=["GET"])
    if "/api/files/{model}/{kind}" not in existing:
        app.app.add_api_route(
            "/api/files/{model}/{kind}", _api_download_file, methods=["GET"]
        )
    if "/api/cleanup" not in existing:
        app.app.add_api_route("/api/cleanup", _api_cleanup, methods=["POST"])


app = render_app()
app_wrapper = typer.Typer()


@app_wrapper.command()
def start_app(
    share: Annotated[
        bool,
        typer.Option("--share", "-s", help="Enable sharing"),
    ] = False,
    listen: Annotated[
        bool,
        typer.Option(
            "--listen",
            "-l",
            help="Make the web application reachable from your local network.",
        ),
    ] = False,
    listen_host: Annotated[
        str | None,
        typer.Option(
            "--listen-host",
            "-h",
            help="The hostname that the server will use.",
        ),
    ] = None,
    listen_port: Annotated[
        int | None,
        typer.Option(
            "--listen-port",
            "-p",
            help="The listening port that the server will use.",
        ),
    ] = None,
    ssr_mode: Annotated[
        bool,
        typer.Option(
            "--ssr-mode",
            help="Enable server-side rendering mode.",
        ),
    ] = False,
    auth_user: Annotated[
        str | None,
        typer.Option("--auth-user", help="Username for the web application."),
    ] = None,
    auth_password: Annotated[
        str | None,
        typer.Option("--auth-password", help="Password for the web application."),
    ] = None,
) -> None:
    """Run the Ultimate RVC training web application."""
    os.environ["GRADIO_TEMP_DIR"] = str(TEMP_DIR)
    gr.set_static_paths([MODELS_DIR, AUDIO_DIR])
    app.queue()
    _register_api_routes()
    if bool(auth_user) != bool(auth_password):
        raise typer.BadParameter("--auth-user and --auth-password must be provided together")
    app.launch(
        share=share,
        server_name=(None if not listen else (listen_host or "0.0.0.0")),
        server_port=listen_port,
        ssr_mode=ssr_mode,
        prevent_thread_lock=True,
        auth=(auth_user, auth_password) if auth_user and auth_password else None,
    )
    _register_api_routes()
    app.block_thread()


if __name__ == "__main__":
    app_wrapper()
