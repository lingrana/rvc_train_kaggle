"""
Module which defines the code for the
"Model train - multi-step generation" tab.
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

from functools import partial
from multiprocessing import cpu_count

import gradio as gr

from ultimate_rvc.core.manage.audio import get_audio_datasets_choices, get_dataset_files
from ultimate_rvc.core.manage.models import (
    get_training_model_names,
)
from ultimate_rvc.common import TRAINING_MODELS_DIR
from ultimate_rvc.core.train.common import get_gpu_info
from ultimate_rvc.core.train.extract import extract_features
from ultimate_rvc.core.train.prepare import (
    populate_dataset,
    preprocess_dataset,
)
from ultimate_rvc.core.train.train import run_training, stop_training
from ultimate_rvc.typing_extra import (
    AudioExt,
    AudioSplitMethod,
    DeviceType,
    EmbedderModel,
    PretrainedType,
)
from ultimate_rvc.web.common import (
    exception_harness,
    render_msg,
    toggle_visibilities,
    toggle_visibility,
    toggle_visible_component,
    update_dropdowns,
    update_value,
)
from ultimate_rvc.web.typing_extra import ConcurrencyId, DatasetType

if TYPE_CHECKING:
    from ultimate_rvc.web.config.main import MultiStepTrainingConfig, TotalConfig

CPU_CORES = cpu_count()
GPU_CHOICES = get_gpu_info()

TRAINING_MODELS_BASE = str(TRAINING_MODELS_DIR)


def _training_is_active(model_name: str | None) -> bool:
    """Detect a running training process after a browser reconnects."""
    if not isinstance(model_name, str) or not model_name.strip():
        return False
    model_dir = TRAINING_MODELS_DIR / model_name.strip()
    if (model_dir / "stop_requested").is_file():
        return False
    try:
        with (model_dir / "config.json").open("r", encoding="utf-8") as f:
            process_ids = json.load(f).get("process_pids", [])
        for pid in process_ids:
            try:
                os.kill(int(pid), 0)
                return True
            except (ProcessLookupError, PermissionError, ValueError):
                continue
    except (OSError, ValueError, TypeError):
        pass
    return False


def _restore_training_buttons(model_name: str | None):
    """Restore train/stop button visibility from backend state."""
    active = _training_is_active(model_name)
    return gr.update(visible=not active), gr.update(visible=active)


def _read_training_progress(model_name: str) -> str:
    """Read progress.json and return HTML progress display."""
    _empty = """
    <div style="padding:12px; border:1px solid #e8ecef; border-radius:10px; background:#fff;">
        <div style="font-size:13px; font-weight:600; color:#5a6072; margin-bottom:8px;">等待训练开始...</div>
        <div style="background:#f0f2f5; border-radius:6px; height:20px; width:100%;"></div>
    </div>
    """
    if not model_name:
        return _empty
    progress_path = os.path.join(TRAINING_MODELS_BASE, model_name, "progress.json")
    if not os.path.isfile(progress_path):
        return _empty
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
        pct = round(epoch / total * 100) if total > 0 else 0
        status = "训练已完成！" if done else f"训练中... 第 {epoch}/{total} 轮"
        detail = f"生成器损失: {loss_g:.4f} | 判别器损失: {loss_d:.4f} | 最佳: {best_loss:.4f} (第{best_epoch}轮)"
        bar_color = "#10b981" if done else "#0066ff"
        log_path = os.path.join(TRAINING_MODELS_BASE, model_name, "train.log")
        log_html = ""
        if os.path.isfile(log_path):
            with open(log_path, "r", encoding="utf-8") as lf:
                lines = lf.readlines()
            recent = lines[-3:] if len(lines) > 3 else lines
            if recent:
                log_lines = "".join(l.strip() + "<br>" for l in recent)
                log_html = f'<div style="margin-top:8px; padding:8px; background:#fafbfc; border:1px solid #e8ecef; border-radius:8px; font-family:monospace; font-size:11px; color:#5a6072; max-height:80px; overflow-y:auto;">{log_lines}</div>'
        return f"""
        <div style="padding:12px; border:1px solid #e8ecef; border-radius:10px; background:#fff;">
            <div style="font-size:14px; font-weight:700; color:#1a1a2e; margin-bottom:8px;">{status}</div>
            <div style="background:#f0f2f5; border-radius:6px; height:20px; width:100%; position:relative;">
                <div style="background:linear-gradient(90deg,{bar_color},{bar_color}aa); height:20px; border-radius:6px; width:{pct}%; transition:width 0.5s;"></div>
                <div style="position:absolute; top:0; left:0; right:0; bottom:0; display:flex; align-items:center; justify-content:center; font-size:11px; font-weight:600; color:#1a1a2e;">{pct}%</div>
            </div>
            <div style="margin-top:8px; font-size:12px; color:#5a6072;">{detail}</div>
            {log_html}
        </div>
        """
    except Exception:
        return _empty


def _read_training_progress_json(model_name: str) -> str:
    """Read progress.json and return HTML for JS DOM injection (no Gradio render)."""
    return _read_training_progress(model_name)


def render(total_config: TotalConfig) -> gr.HTML:
    """
    Render the "Model train - multi-step generation" tab.

    Returns
    -------
    gr.HTML
        The training progress HTML component for timer binding.

    """
    with gr.Tab("多步骤训练"):
        _render_step_1(total_config)
        _render_step_2(total_config)
        return _render_step_3(total_config)


_UPLOAD_PROGRESS_JS = """
<script>
(function(){
  if(window.__rvcUploadPatched) return;
  window.__rvcUploadPatched = true;
  var origOpen = XMLHttpRequest.prototype.open;
  var origSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function(method, url) {
    this._rvcUrl = url;
    return origOpen.apply(this, arguments);
  };
  XMLHttpRequest.prototype.send = function(body) {
    if(this._rvcUrl && this._rvcUrl.includes('/upload')) {
      var xhr = this;
      var bar = document.getElementById('rvc-upload-bar');
      var text = document.getElementById('rvc-upload-text');
      if(bar) bar.style.width = '0%';
      if(text) text.textContent = '上传中 0%';
      xhr.upload.addEventListener('progress', function(e) {
        if(e.lengthComputable) {
          var pct = Math.round(e.loaded / e.total * 100);
          if(bar) bar.style.width = pct + '%';
          if(text) text.textContent = pct >= 100 ? '上传完成 ✓' : '上传中 ' + pct + '%';
        }
      });
      xhr.addEventListener('load', function() {
        if(bar) bar.style.width = '100%';
        if(text) text.textContent = '上传完成 ✓';
        setTimeout(function(){ if(bar) bar.style.width='0%'; }, 2000);
      });
    }
    return origSend.apply(this, arguments);
  };
})();
</script>
"""


def _render_step_1(total_config: TotalConfig) -> None:
    tab_config = total_config.training.multi_step

    current_dataset = gr.State()
    with gr.Accordion("步骤 1：数据集预处理", open=True):
        gr.HTML(_UPLOAD_PROGRESS_JS)
        with gr.Row():
            tab_config.dataset_type.instantiate()
            tab_config.dataset.instance.render()
            tab_config.dataset_name.instantiate()
        upload_progress_html = gr.HTML(
            value="""
            <div style="margin:4px 0 8px 0;">
              <div style="background:#f0f2f5;border-radius:6px;height:6px;width:100%;">
                <div id="rvc-upload-bar" style="background:#0066ff;height:6px;border-radius:6px;width:0%;transition:width 0.3s;"></div>
              </div>
              <div id="rvc-upload-text" style="font-size:11px;color:#9ca3b0;margin-top:3px;"></div>
            </div>
            """,
        )
        audio_files = gr.File(
            file_count="multiple",
            label="音频文件（支持拖拽上传）",
            file_types=[f".{e.value}" for e in AudioExt],
        )
        upload_status = gr.Markdown(value="", visible=True)

        dataset_files_html = gr.HTML(
            value='<div style="padding:8px;color:#9ca3b0;font-size:12px;">选择数据集后显示文件列表</div>',
        )
        audio_preview = gr.Audio(
            label="音频预览",
            type="filepath",
            interactive=False,
            visible=False,
        )

        tab_config.dataset_type.instance.change(
            _toggle_dataset_input,
            inputs=tab_config.dataset_type.instance,
            outputs=[
                tab_config.dataset_name.instance,
                audio_files,
                tab_config.dataset.instance,
            ],
            show_progress="hidden",
        )

        tab_config.dataset.instance.change(
            _update_dataset_files_display,
            inputs=tab_config.dataset.instance,
            outputs=[dataset_files_html, audio_preview],
            show_progress="hidden",
        )

        audio_files.upload(
            exception_harness(
                _upload_audio_files,
                info_msg="[+] 音频文件已成功添加到数据集中！",
            ),
            inputs=[tab_config.dataset_name.instance, audio_files],
            outputs=[current_dataset, upload_status],
        ).then(
            partial(update_dropdowns, get_audio_datasets_choices, 1, value_indices=[0]),
            inputs=current_dataset,
            outputs=tab_config.dataset.instance,
            show_progress="hidden",
        ).then(
            _update_dataset_files_display,
            inputs=tab_config.dataset.instance,
            outputs=[dataset_files_html, audio_preview],
            show_progress="hidden",
        )
        with gr.Row():
            tab_config.preprocess_model.instance.render()
        with gr.Accordion("选项", open=False):
            with gr.Row():
                tab_config.sample_rate.instantiate()
                tab_config.normalization_mode.instantiate()
            with gr.Row():
                with gr.Column():
                    tab_config.filter_audio.instantiate()
                with gr.Column():
                    tab_config.clean_audio.instantiate()
                    tab_config.clean_strength.instantiate()
                    tab_config.clean_audio.instance.change(
                        partial(toggle_visibility, targets={True}),
                        inputs=tab_config.clean_audio.instance,
                        outputs=tab_config.clean_strength.instance,
                        show_progress="hidden",
                    )
            with gr.Row():
                tab_config.split_method.instantiate()
            with gr.Row():
                tab_config.chunk_len.instantiate()
                tab_config.overlap_len.instantiate()
            tab_config.split_method.instance.change(
                partial(
                    toggle_visibilities,
                    2,
                    targets={AudioSplitMethod.SIMPLE},
                ),
                inputs=tab_config.split_method.instance,
                outputs=[
                    tab_config.chunk_len.instance,
                    tab_config.overlap_len.instance,
                ],
                show_progress="hidden",
            )
            with gr.Row():
                tab_config.preprocess_cores.instantiate(
                    maximum=CPU_CORES,
                    value=CPU_CORES,
                )
        with gr.Row(equal_height=True):
            reset_preprocess_btn = gr.Button(
                "重置选项",
                variant="secondary",
                scale=2,
            )
            preprocess_btn = gr.Button(
                "预处理数据集",
                variant="primary",
                scale=2,
            )
            preprocess_msg = gr.Textbox(
                label="输出信息",
                interactive=False,
                scale=3,
            )
            preprocess_btn.click(
                exception_harness(preprocess_dataset),
                inputs=[
                    tab_config.preprocess_model.instance,
                    tab_config.dataset.instance,
                    tab_config.sample_rate.instance,
                    tab_config.normalization_mode.instance,
                    tab_config.filter_audio.instance,
                    tab_config.clean_audio.instance,
                    tab_config.clean_strength.instance,
                    tab_config.split_method.instance,
                    tab_config.chunk_len.instance,
                    tab_config.overlap_len.instance,
                    tab_config.preprocess_cores.instance,
                ],
                outputs=preprocess_msg,
                concurrency_limit=1,
                concurrency_id=ConcurrencyId.GPU,
            ).success(
                partial(render_msg, "[+] 数据集预处理成功！"),
                outputs=preprocess_msg,
                show_progress="hidden",
            ).then(
                partial(update_dropdowns, get_training_model_names, 3, [], [2]),
                outputs=[
                    tab_config.preprocess_model.instance,
                    tab_config.extract_model.instance,
                    tab_config.train_model.instance,
                ],
                show_progress="hidden",
            ).then(
                _normalize_and_update,
                inputs=tab_config.preprocess_model.instance,
                outputs=tab_config.preprocess_model.instance,
                show_progress="hidden",
            ).then(
                update_value,
                inputs=tab_config.preprocess_model.instance,
                outputs=tab_config.extract_model.instance,
                show_progress="hidden",
            )
            reset_preprocess_btn.click(
                lambda: [
                    tab_config.sample_rate.value,
                    tab_config.filter_audio.value,
                    tab_config.clean_audio.value,
                    tab_config.clean_strength.value,
                    tab_config.split_method.value,
                    tab_config.chunk_len.value,
                    tab_config.overlap_len.value,
                    CPU_CORES,
                ],
                outputs=[
                    tab_config.sample_rate.instance,
                    tab_config.filter_audio.instance,
                    tab_config.clean_audio.instance,
                    tab_config.clean_strength.instance,
                    tab_config.split_method.instance,
                    tab_config.chunk_len.instance,
                    tab_config.overlap_len.instance,
                    tab_config.preprocess_cores.instance,
                ],
                show_progress="hidden",
            )


def _render_step_2(total_config: TotalConfig) -> None:
    tab_config = total_config.training.multi_step
    with gr.Accordion("步骤 2：特征提取", open=True):
        with gr.Row():
            tab_config.extract_model.instance.render()
        with gr.Accordion("选项", open=False):
            with gr.Row():
                with gr.Column():
                    tab_config.f0_method.instantiate()
                with gr.Column():
                    tab_config.embedder_model.instantiate()
                    tab_config.custom_embedder_model.instance.render()

                tab_config.embedder_model.instance.change(
                    partial(toggle_visibility, targets={EmbedderModel.CUSTOM}),
                    inputs=tab_config.embedder_model.instance,
                    outputs=tab_config.custom_embedder_model.instance,
                    show_progress="hidden",
                )
            with gr.Row():
                tab_config.include_mutes.instantiate()
            with gr.Row():
                with gr.Column():
                    tab_config.extraction_cores.instantiate(
                        maximum=CPU_CORES,
                        value=CPU_CORES,
                    )
                with gr.Column():
                    tab_config.extraction_acceleration.instantiate()
                    tab_config.extraction_gpus.instantiate(
                        choices=GPU_CHOICES,
                        value=GPU_CHOICES[0][1] if GPU_CHOICES else None,
                    )
            tab_config.extraction_acceleration.instance.change(
                partial(toggle_visibility, targets={DeviceType.GPU}),
                inputs=tab_config.extraction_acceleration.instance,
                outputs=tab_config.extraction_gpus.instance,
                show_progress="hidden",
            )
        with gr.Row(equal_height=True):
            reset_extract_btn = gr.Button(
                "重置选项",
                variant="secondary",
                scale=2,
            )
            extract_btn = gr.Button("提取特征", variant="primary", scale=2)
            extract_msg = gr.Textbox(label="输出信息", interactive=False, scale=3)
            extract_btn.click(
                exception_harness(extract_features),
                inputs=[
                    tab_config.extract_model.instance,
                    tab_config.f0_method.instance,
                    tab_config.embedder_model.instance,
                    tab_config.custom_embedder_model.instance,
                    tab_config.include_mutes.instance,
                    tab_config.extraction_cores.instance,
                    tab_config.extraction_acceleration.instance,
                    tab_config.extraction_gpus.instance,
                ],
                outputs=extract_msg,
                concurrency_limit=1,
                concurrency_id=ConcurrencyId.GPU,
            ).success(
                partial(render_msg, "[+] 特征提取成功！"),
                outputs=extract_msg,
                show_progress="hidden",
            ).then(
                update_value,
                inputs=tab_config.extract_model.instance,
                outputs=tab_config.train_model.instance,
                show_progress="hidden",
            )
            reset_extract_btn.click(
                lambda: [
                    tab_config.f0_method.value,
                    tab_config.embedder_model.value,
                    tab_config.include_mutes.value,
                    CPU_CORES,
                    tab_config.extraction_acceleration.value,
                    GPU_CHOICES[0][1] if GPU_CHOICES else None,
                ],
                outputs=[
                    tab_config.f0_method.instance,
                    tab_config.embedder_model.instance,
                    tab_config.include_mutes.instance,
                    tab_config.extraction_cores.instance,
                    tab_config.extraction_acceleration.instance,
                    tab_config.extraction_gpus.instance,
                ],
                show_progress="hidden",
            )


def _render_step_3(total_config: TotalConfig) -> None:
    tab_config = total_config.training.multi_step
    with gr.Accordion("步骤 3：模型训练"):
        with gr.Row():
            tab_config.train_model.instance.render()

        with gr.Accordion("训练进度", open=True):
            train_progress = gr.HTML(
                value="""
                <div class="rvc-progress" data-rvc-progress>
                  <div class="rvc-progress-head"><strong data-role="model">等待任务</strong><span data-role="phase">等待训练开始</span></div>
                  <div class="rvc-progress-track"><div data-role="bar"></div><b data-role="percent">0.0%</b></div>
                  <div class="rvc-progress-stats"><span>轮次 <b data-role="epoch">0 / 0</b></span><span>批次 <b data-role="batch">--</b></span><span>已用 <b data-role="elapsed">00:00:00</b></span><span>剩余 <b data-role="eta">--:--:--</b></span><span>损失 <b data-role="loss">G 0.0000 · D 0.0000</b></span></div>
                  <div class="rvc-progress-alert" data-role="alert" hidden></div>
                  <details class="rvc-progress-log"><summary>最近日志</summary><pre data-role="log"></pre></details>
                </div>
                """,
                elem_id="train-progress",
            )

        with gr.Accordion("选项", open=False):
            _render_step_3_main_settings(tab_config)
            _render_step_3_algorithmic_settings(tab_config)
            _render_step_3_data_storage_settings(tab_config)
            _render_step_3_device_settings(tab_config)

        with gr.Row(equal_height=True):
            reset_train_btn = gr.Button("重置选项", variant="secondary", scale=2)
            train_btn = gr.Button("训练语音模型", variant="primary", scale=2, elem_id="rvc-train-btn")
            stop_train_btn = gr.Button(
                "停止训练",
                variant="primary",
                scale=2,
                visible=False,
                elem_id="rvc-stop-train-btn",
            )
            train_msg = gr.Textbox(label="输出信息", interactive=False, scale=3)
        voice_model_files = gr.File(            label="语音模型文件", interactive=False)
        train_btn.click(
            partial(toggle_visible_component, 2, 1, reset_values=False),
            outputs=[train_btn, stop_train_btn],
            show_progress="hidden",
        )
        train_btn_click = train_btn.click(
            exception_harness(run_training),
            inputs=[
                tab_config.train_model.instance,
                tab_config.version.instance,
                tab_config.f0_guidance.instance,
                tab_config.num_epochs.instance,
                tab_config.batch_size.instance,
                tab_config.detect_overtraining.instance,
                tab_config.overtraining_threshold.instance,
                tab_config.vocoder.instance,
                tab_config.index_algorithm.instance,
                tab_config.pretrained_type.instance,
                tab_config.custom_pretrained_model.instance,
                tab_config.save_interval.instance,
                tab_config.save_all_checkpoints.instance,
                tab_config.save_all_weights.instance,
                tab_config.clear_saved_data.instance,
                tab_config.upload_model.instance,
                tab_config.upload_name.instance,
                tab_config.training_acceleration.instance,
                tab_config.training_gpus.instance,
                tab_config.precision.instance,
                tab_config.preload_dataset.instance,
                tab_config.reduce_memory_usage.instance,
            ],
            outputs=voice_model_files,
            concurrency_limit=1,
            concurrency_id=ConcurrencyId.GPU,
        )

        tab_config.train_model.instance.change(
            _restore_training_buttons,
            inputs=tab_config.train_model.instance,
            outputs=[train_btn, stop_train_btn],
            show_progress="hidden",
        )

        train_btn_click.then(
            partial(toggle_visible_component, 2, 0, reset_values=False),
            outputs=[train_btn, stop_train_btn],
            show_progress="hidden",
        )

        train_btn_click.success(
            partial(render_msg, "[+] 语音模型训练成功！正在上传到 Kaggle 数据集..."),
            outputs=train_msg,
            show_progress="hidden",
        ).then(
            _auto_upload_to_kaggle,
            inputs=[tab_config.train_model.instance],
            outputs=train_msg,
            show_progress="hidden",
        )

        stop_train_btn.click(
            stop_training,
            inputs=tab_config.train_model.instance,
            show_progress="hidden",
        )
        reset_train_btn.click(
            lambda: [
                tab_config.version.value,
                tab_config.f0_guidance.value,
                tab_config.num_epochs.value,
                tab_config.batch_size.value,
                tab_config.detect_overtraining.value,
                tab_config.overtraining_threshold.value,
                tab_config.vocoder.value,
                tab_config.index_algorithm.value,
                tab_config.pretrained_type.value,
                tab_config.save_interval.value,
                tab_config.save_all_checkpoints.value,
                tab_config.save_all_weights.value,
                tab_config.clear_saved_data.value,
                tab_config.upload_model.value,
                tab_config.training_acceleration.value,
                GPU_CHOICES[0][1] if GPU_CHOICES else None,
                tab_config.precision.value,
                tab_config.preload_dataset.value,
                tab_config.reduce_memory_usage.value,
            ],
            outputs=[
                tab_config.version.instance,
                tab_config.f0_guidance.instance,
                tab_config.num_epochs.instance,
                tab_config.batch_size.instance,
                tab_config.detect_overtraining.instance,
                tab_config.overtraining_threshold.instance,
                tab_config.vocoder.instance,
                tab_config.index_algorithm.instance,
                tab_config.pretrained_type.instance,
                tab_config.save_interval.instance,
                tab_config.save_all_checkpoints.instance,
                tab_config.save_all_weights.instance,
                tab_config.clear_saved_data.instance,
                tab_config.upload_model.instance,
                tab_config.training_acceleration.instance,
                tab_config.training_gpus.instance,
                tab_config.precision.instance,
                tab_config.preload_dataset.instance,
                tab_config.reduce_memory_usage.instance,
            ],
            show_progress="hidden",
        )

    return train_progress


def _render_step_3_main_settings(tab_config: MultiStepTrainingConfig) -> None:
    with gr.Row():
        tab_config.version.instantiate()
        tab_config.f0_guidance.instantiate()
    with gr.Row():
        tab_config.num_epochs.instantiate()
        tab_config.batch_size.instantiate()
    with gr.Column():
        tab_config.detect_overtraining.instantiate()
        tab_config.overtraining_threshold.instantiate()
    tab_config.detect_overtraining.instance.change(
        partial(toggle_visibility, targets={True}),
        inputs=tab_config.detect_overtraining.instance,
        outputs=tab_config.overtraining_threshold.instance,
        show_progress="hidden",
    )
    tab_config.f0_guidance.instance.change(
        partial(toggle_visibility, targets={True}),
        inputs=tab_config.f0_guidance.instance,
        outputs=tab_config.f0_method.instance,
        show_progress="hidden",
    )


def _get_pretrained_info(tab_config, vocoder=None, sample_rate=None):
    from ultimate_rvc.common import PRETRAINED_MODELS_DIR
    v = vocoder or "HiFi-GAN"
    sr = sample_rate or "48"
    base = PRETRAINED_MODELS_DIR / v.lower()
    pg = base / f"f0G{sr}k.pth"
    pd = base / f"f0D{sr}k.pth"
    exists_g = pg.is_file()
    exists_d = pd.is_file()
    status = "✅" if (exists_g and exists_d) else "❌"
    return (
        f"**底模信息** {status}\n\n"
        f"- 生成器: `{pg}` ({'存在' if exists_g else '缺失'})\n"
        f"- 判别器: `{pd}` ({'存在' if exists_d else '缺失'})\n"
        f"- 预训练类型: Default | 声码器: {v} | 采样率: {sr}k"
    )


def _render_step_3_algorithmic_settings(tab_config: MultiStepTrainingConfig) -> None:
    with gr.Accordion("算法设置", open=False):
        with gr.Row():
            tab_config.vocoder.instantiate()
            tab_config.index_algorithm.instantiate()
        with gr.Column():
            tab_config.pretrained_type.instantiate()
            tab_config.custom_pretrained_model.instance.render()

        tab_config.pretrained_type.instance.change(
            partial(toggle_visibility, targets={PretrainedType.CUSTOM}),
            inputs=tab_config.pretrained_type.instance,
            outputs=tab_config.custom_pretrained_model.instance,
            show_progress="hidden",
        )

        pretrained_info = gr.Markdown(
            value=_get_pretrained_info(tab_config),
            label="底模信息",
        )
        tab_config.vocoder.instance.change(
            lambda v: gr.Markdown(value=_get_pretrained_info(None, vocoder=v)),
            inputs=tab_config.vocoder.instance,
            outputs=pretrained_info,
            show_progress="hidden",
        )


def _render_step_3_data_storage_settings(tab_config: MultiStepTrainingConfig) -> None:
    with gr.Accordion("数据存储", open=False):
        with gr.Row():
            tab_config.save_interval.instantiate()
        with gr.Row():
            tab_config.save_all_checkpoints.instantiate()
            tab_config.save_all_weights.instantiate()
            tab_config.clear_saved_data.instantiate()

        with gr.Column():
            tab_config.upload_model.instantiate()
            tab_config.upload_name.instantiate(
                value=update_value,
                inputs=tab_config.train_model.instance,
            )
        tab_config.upload_model.instance.change(
            partial(toggle_visibility, targets={True}),
            inputs=tab_config.upload_model.instance,
            outputs=tab_config.upload_name.instance,
            show_progress="hidden",
        )


def _render_step_3_device_settings(tab_config: MultiStepTrainingConfig) -> None:
    with gr.Accordion("设备与显存", open=False):
        with gr.Row():
            with gr.Column():
                tab_config.training_acceleration.instantiate()
                tab_config.training_gpus.instantiate(
                    choices=GPU_CHOICES,
                    value=[choice[1] for choice in GPU_CHOICES] if GPU_CHOICES else None,
                )
            with gr.Column():
                tab_config.precision.instantiate()
            tab_config.training_acceleration.instance.change(
                partial(toggle_visibility, targets={DeviceType.GPU}),
                inputs=tab_config.training_acceleration.instance,
                outputs=tab_config.training_gpus.instance,
                show_progress="hidden",
            )
        with gr.Row():
            tab_config.preload_dataset.instantiate()
            tab_config.reduce_memory_usage.instantiate()


def _upload_audio_files(
    dataset_name: str,
    files: list,
) -> tuple:
    """Upload audio files and return status message."""
    result = populate_dataset(dataset_name, files)
    file_count = len(files) if files else 0
    file_names = [f.split("/")[-1] if "/" in f else f.split("\\")[-1] for f in (files or [])]
    status = f"**已上传 {file_count} 个文件：**\n\n" + "\n".join(f"- {name}" for name in file_names[:10])
    if file_count > 10:
        status += f"\n- ... 还有 {file_count - 10} 个文件"

    return result, status


def _update_dataset_files_display(dataset_path: str) -> tuple[str, gr.update]:
    if not dataset_path:
        return '<div style="padding:10px; color:#9ca3b0; font-size:12px;">选择数据集后显示文件列表</div>', gr.update(visible=False)

    files = get_dataset_files(dataset_path)
    if not files:
        return '<div style="padding:10px; color:#9ca3b0; font-size:12px;">数据集为空</div>', gr.update(visible=False)

    html_parts = ['<div style="padding:8px 12px; background:#fafbfc; border:1px solid #e8ecef; border-radius:8px; font-size:12px; font-weight:600; color:#5a6072;">文件列表</div>']
    for i, (name, path, size) in enumerate(files[:20]):
        size_mb = size / (1024 * 1024)
        html_parts.append(f'<div style="padding:6px 12px; font-size:12px; border-bottom:1px solid #f0f2f5; color:#5a6072;">{i+1}. {name} <span style="color:#9ca3b0;">({size_mb:.1f} MB)</span></div>')
    if len(files) > 20:
        html_parts.append(f'<div style="padding:6px 12px; font-size:11px; color:#9ca3b0;">... 还有 {len(files)-20} 个文件</div>')

    first_audio = files[0][1] if files else None
    if first_audio:
        return ''.join(html_parts), gr.update(value=first_audio, visible=True)
    return ''.join(html_parts), gr.update(visible=False)


def _toggle_dataset_input(
    dataset_type: DatasetType,
) -> tuple[gr.Textbox, gr.File, gr.Dropdown]:
    is_new_dataset = dataset_type == DatasetType.NEW_DATASET
    return (
        gr.Textbox(
            visible=is_new_dataset,
            value="My dataset",  # TODO this should be component_config.value
        ),
        gr.File(visible=is_new_dataset, value=None),
        gr.Dropdown(visible=not is_new_dataset, value=None),
    )


def _normalize_and_update(value: str) -> gr.Dropdown:
    """
    Normalize the value of the given string and update the dropdown.

    Parameters
    ----------
    value : str
        The value to normalize and update.

    Returns
    -------
    gr.Dropdown
        The updated dropdown.

    """
    return gr.Dropdown(value=value.strip())


def _auto_upload_to_kaggle(model_name: str) -> str:
    """训练完成后将模型上传到 Kaggle Dataset，提示用户上传位置。"""
    if not isinstance(model_name, str):
        model_name = getattr(model_name, "value", "")
    if not isinstance(model_name, str):
        model_name = ""
    model_name = model_name.strip()
    if not model_name:
        return "[+] 语音模型训练成功！"
    try:
        model_dir = TRAINING_MODELS_BASE + os.sep + model_name
        from pathlib import Path
        from ultimate_rvc.rvc.train.progress import update_progress

        progress_path = os.path.join(model_dir, "progress.json")
        stop_path = os.path.join(model_dir, "stop_requested")
        if os.path.isfile(stop_path):
            return "[!] 训练已停止，不上传未完成模型。"
        if os.path.isfile(progress_path):
            with open(progress_path, "r", encoding="utf-8") as f:
                progress = json.load(f)
            if not progress.get("done", False):
                return "[!] 训练未完成，不上传模型。"
        update_progress(Path(model_dir), phase="uploading", done=True)
        from ultimate_rvc.web.main import upload_model_to_kaggle
        result = upload_model_to_kaggle(model_name)
        errors = result.get("errors", []) if isinstance(result, dict) else []
        if errors:
            update_progress(
                Path(model_dir), phase="completed", done=True,
                warning=f"Kaggle 上传失败：{'；'.join(str(e) for e in errors)}",
            )
            return f"[!] 模型上传到 Kaggle 数据集失败：{'；'.join(str(e) for e in errors)}"
        update_progress(Path(model_dir), phase="completed", done=True, warning="")
        dataset_url = result.get("kaggle", "") if isinstance(result, dict) else ""
        dataset_slug = result.get("kaggle_slug", "") if isinstance(result, dict) else ""
        if dataset_slug:
            return (
                f"[+] 训练完成！模型已上传至 Kaggle 数据集 "
                f"<code>{dataset_slug}</code>（含 pth/index/log）。"
                f"请到 Result 页面或访问 {dataset_url} 下载。"
            )
        if dataset_url:
            return (
                f"[+] 训练完成！模型已上传至 Kaggle 数据集（含 pth/index/log）：{dataset_url}。"
                f"请到 Result 页面下载。"
            )
        return "[+] 训练完成！但未能获取 Kaggle 数据集链接，请到 Result 页面查看。"
    except Exception as e:
        try:
            update_progress(Path(model_dir), phase="completed", done=True, warning=f"Kaggle 上传出错：{e}")
        except Exception:
            pass
        return f"[+] 训练完成！Kaggle 数据集上传出错: {e}"
