"""Module defining common component configurations for UI tabs."""

from __future__ import annotations

from pydantic import BaseModel

from ultimate_rvc.typing_extra import (
    AudioExt,
    AudioNormalizationMode,
    AudioSplitMethod,
    DeviceType,
    EmbedderModel,
    F0Method,
    IndexAlgorithm,
    PrecisionType,
    PretrainedType,
    RVCVersion,
    SampleRate,
    TrainingSampleRate,
    Vocoder,
)
from ultimate_rvc.web.config.component import (
    CheckboxConfig,
    DropdownConfig,
    NumberConfig,
    SliderConfig,
    TextboxConfig,
)
from ultimate_rvc.web.typing_extra import DatasetType, SongSourceType, SpeechSourceType


class BaseTabConfig(BaseModel):
    """
    Base model defining common component configuration settings for
    UI tabs.

    Attributes
    ----------
    embedder_model : DropdownConfig
        Configuration settings for an embedder model dropdown component.
    custom_embedder_model : DropdownConfig
        Configuration settings for a custom embedder model dropdown
        component.

    """

    embedder_model: DropdownConfig = DropdownConfig(
        label="嵌入模型",
        info="用于生成说话人嵌入的模型。",
        value=EmbedderModel.LOCAL_HUBERT_BASE,
        choices=list(EmbedderModel),
        exclude_value=True,
    )
    custom_embedder_model: DropdownConfig = DropdownConfig(
        label="自定义嵌入模型",
        info="从下拉列表中选择自定义嵌入模型。",
        value=None,
        visible=False,
        render=False,
        exclude_value=True,
    )


class GenerationConfig(BaseTabConfig):
    """
    Common component configuration settings for generation tabs.

    voice_model : DropdownConfig
        Configuration settings for a voice model dropdown component.
    f0_method : DropdownConfig
        Configuration settings for a pitch extraction algorithm
        dropdown component.
    index_rate : SliderConfig
        Configuration settings for an index rate slider component.
    rms_mix_rate : SliderConfig
        Configuration settings for a RMS mix rate slider component.
    protect_rate : SliderConfig
        Configuration settings for a protect rate slider component.
    split_voice : CheckboxConfig
        Configuration settings for a split voice checkbox component.
    autotune_voice: CheckboxConfig
        Configuration settings for an autotune voice checkbox component.
    autotune_strength: SliderConfig
        Configuration settings for an autotune strength slider
        component.
    proposed_pitch: CheckboxConfig
        Configuration settings for a proposed pitch checkbox component.
    proposed_pitch_threshold: SliderConfig
        Configuration settings for a proposed pitch threshold slider
        component.
    sid : NumberConfig
        Configuration settings for a speaker ID number component.
    output_sr : DropdownConfig
        Configuration settings for an output sample rate dropdown
        component.
    output_format : DropdownConfig
        Configuration settings for an output format dropdown
        component.
    output_name : TextboxConfig
        Configuration settings for an output name textbox component.

    See Also
    --------
    BaseTabConfig
        Parent model defining common component configuration settings
        for UI tabs.

    """

    voice_model: DropdownConfig = DropdownConfig(
        label="Voice model",
        info="Select a model to use for voice conversion.",
        value=None,
        render=False,
        exclude_value=True,
    )
    f0_method: DropdownConfig = DropdownConfig(
        label="Pitch extraction algorithm",
        info="RMVPE is recommended for most cases and is the default.",
        value=F0Method.RMVPE,
        choices=list(F0Method),
        multiselect=False,
    )
    index_rate: SliderConfig = SliderConfig(
        label="Index rate",
        info=(
            "Increase to bias the conversion towards the accent of the voice model."
            " Decrease to potentially reduce artifacts coming from the voice"
            " model.<br><br><br>"
        ),
        value=0.3,
        minimum=0.0,
        maximum=1.0,
    )
    rms_mix_rate: SliderConfig = SliderConfig(
        label="RMS mix rate",
        info=(
            "How much to mimic the loudness (0) of the input voice or a fixed loudness"
            " (1). A value of 1 is recommended for most cases.<br><br>"
        ),
        value=1.0,
        minimum=0.0,
        maximum=1.0,
    )
    protect_rate: SliderConfig = SliderConfig(
        label="Protect rate",
        info=(
            "Controls the extent to which consonants and breathing sounds are protected"
            " from artifacts. A higher value offers more protection but may worsen the"
            " indexing effect.<br><br>"
        ),
        value=0.33,
        minimum=0.0,
        maximum=0.5,
    )

    split_voice: CheckboxConfig = CheckboxConfig(
        label="Split input voice",
        info=(
            "Whether to split the input voice track into smaller segments before"
            " converting it. This can improve output quality for longer voice tracks."
        ),
        value=False,
    )
    autotune_voice: CheckboxConfig = CheckboxConfig(
        label="Autotune converted voice",
        info="Whether to apply autotune to the converted voice.",
        value=False,
        exclude_value=True,
    )
    autotune_strength: SliderConfig = SliderConfig(
        label="Autotune intensity",
        info=(
            "Higher values result in stronger snapping to the chromatic grid and"
            " artifacting."
        ),
        value=1.0,
        minimum=0.0,
        maximum=1.0,
        visible=False,
    )
    proposed_pitch: CheckboxConfig = CheckboxConfig(
        label="Proposed pitch",
        info=(
            "Whether to adjust the pitch of the converted voice so that it matches the"
            " range of the voice model used."
        ),
        value=False,
        exclude_value=True,
    )
    proposed_pitch_threshold: SliderConfig = SliderConfig(
        label="Proposed pitch threshold",
        info=(
            "Male voice models typically use 155.0 and female voice models typically"
            " use 255.0."
        ),
        value=155.0,
        minimum=50.0,
        maximum=1200.0,
        visible=False,
    )
    sid: NumberConfig = NumberConfig(
        label="Speaker ID",
        info="Speaker ID for multi-speaker-models.",
        value=0,
        precision=0,
    )
    output_sr: DropdownConfig = DropdownConfig(
        label="Output sample rate",
        info="The sample rate of the mixed output track.",
        value=SampleRate.HZ_44K,
        choices=list(SampleRate),
    )
    output_format: DropdownConfig = DropdownConfig(
        label="Output format",
        info="The audio format of the mixed output track.",
        value=AudioExt.MP3,
        choices=list(AudioExt),
    )
    output_name: TextboxConfig = TextboxConfig(
        label="Output name",
        info="If no name is provided, a suitable name will be generated automatically.",
        value=None,
        placeholder="Ultimate RVC output",
        exclude_value=True,
    )


class SongGenerationConfig(GenerationConfig):
    """
    Common component configuration settings for song generation tabs.

    Attributes
    ----------
    source_type : DropdownConfig
        Configuration settings for a source type dropdown component.
    source : TextboxConfig
        Configuration settings for an input source textbox component.
    cached_song : DropdownConfig
        Configuration settings for a cached song dropdown component.
    clean_strength : SliderConfig
        Configuration settings for a clean strength slider component.
    clean_voice : CheckboxConfig
        Configuration settings for a clean voice checkbox component.
    room_size : SliderConfig
        Configuration settings for a room size slider component.
    wet_level : SliderConfig
        Configuration settings for a wetness level slider component.
    dry_level : SliderConfig
        Configuration settings for a dryness level slider component.
    damping : SliderConfig
        Configuration settings for a damping level slider component.
    main_gain : SliderConfig
        Configuration settings for a main gain slider component.
    inst_gain : SliderConfig
        Configuration settings for an instrumentals gain slider
        component.
    backup_gain : SliderConfig
        Configuration settings for a backup vocals gain slider
        component.

    See Also
    --------
    GenerationConfig
        Parent model defining common component configuration settings
        for song generation tabs.

    """

    source_type: DropdownConfig = DropdownConfig(
        label="Source type",
        info="The type of source to retrieve a song from.",
        value=SongSourceType.PATH,
        choices=list(SongSourceType),
        type="index",
        exclude_value=True,
    )
    source: TextboxConfig = TextboxConfig(
        label="Source",
        info="Link to a song on YouTube or the full path of a local audio file.",
        value=None,
        exclude_value=True,
    )
    cached_song: DropdownConfig = DropdownConfig(
        label="Source",
        info="Select a song from the list of cached songs.",
        value=None,
        visible=False,
        render=False,
        exclude_value=True,
    )
    clean_voice: CheckboxConfig = CheckboxConfig(
        label="Clean converted voice",
        info="Whether to clean the converted voice using noise reduction algorithms.",
        value=False,
        exclude_value=True,
    )
    clean_strength: SliderConfig = SliderConfig.clean_strength(visible=False)
    room_size: SliderConfig = SliderConfig(
        label="Room size",
        info=(
            "Size of the room which reverb effect simulates. Increase for longer reverb"
            " time."
        ),
        value=0.15,
        minimum=0.0,
        maximum=1.0,
    )
    wet_level: SliderConfig = SliderConfig(
        label="Wetness level",
        info="Loudness of converted vocals with reverb effect applied.",
        value=0.2,
        minimum=0.0,
        maximum=1.0,
    )
    dry_level: SliderConfig = SliderConfig(
        label="Dryness level",
        info="Loudness of converted vocals without reverb effect applied.",
        value=0.8,
        minimum=0.0,
        maximum=1.0,
    )
    damping: SliderConfig = SliderConfig(
        label="Damping level",
        info="Absorption of high frequencies in reverb effect.",
        value=0.7,
        minimum=0.0,
        maximum=1.0,
    )
    main_gain: SliderConfig = SliderConfig.gain(
        label="Main gain",
        info="The gain to apply to the main vocals.",
    )
    inst_gain: SliderConfig = SliderConfig.gain(
        label="Instrumentals gain",
        info="The gain to apply to the instrumentals.",
    )
    backup_gain: SliderConfig = SliderConfig.gain(
        label="Backup gain",
        info="The gain to apply to the backup vocals.",
    )


class SpeechGenerationConfig(GenerationConfig):
    """
    Common component configuration settings for speech generation tabs.

    Attributes
    ----------
    source_type : DropdownConfig
        Configuration settings for a source type dropdown component.
    source : TextboxConfig
        Configuration settings for an input source textbox component.
    edge_tts_voice : DropdownConfig
        Configuration settings for an Edge TTS voice dropdown
        component.
    n_octaves : SliderConfig
        Configuration settings for an octave pitch shift slider
        component.
    n_semitones : SliderConfig
        Configuration settings for a semitone pitch shift slider
        component.
    tts_pitch_shift : SliderConfig
        Configuration settings for a TTS pitch shift slider
        component.
    tts_speed_change : SliderConfig
        Configuration settings for a TTS speed change slider
        component.
    tts_volume_change : SliderConfig
        Configuration settings for a TTS volume change slider
        component.
    clean_voice : CheckboxConfig
        Configuration settings for a clean voice checkbox
        component.
    clean_strength : SliderConfig
        Configuration settings for a clean strength slider
        component.
    output_gain : GainSliderConfig
        Configuration settings for an output gain slider component.

    See Also
    --------
    GenerationConfig
        Parent model defining common component configuration settings
        for generation tabs.

    """

    source_type: DropdownConfig = DropdownConfig(
        label="Source type",
        info="The type of source to generate speech from.",
        value=SpeechSourceType.TEXT,
        choices=list(SpeechSourceType),
        type="index",
        exclude_value=True,
    )
    source: TextboxConfig = TextboxConfig(
        label="Source",
        info="Text to generate speech from",
        value=None,
        exclude_value=True,
    )
    edge_tts_voice: DropdownConfig = DropdownConfig(
        label="Edge TTS voice",
        info="Select a voice to use for text to speech conversion.",
        value=None,
        render=False,
        exclude_value=True,
    )
    n_octaves: SliderConfig = SliderConfig.octave_shift(
        label="Octave shift",
        info=(
            "The number of octaves to pitch-shift the converted speech by. Use 1 for"
            " male-to-female and -1 for vice-versa."
        ),
    )
    n_semitones: SliderConfig = SliderConfig.semitone_shift(
        label="Semitone shift",
        info="The number of semi-tones to pitch-shift the converted speech by.",
    )
    tts_pitch_shift: SliderConfig = SliderConfig(
        label="Edge TTS pitch shift",
        info=(
            "The number of hertz to shift the pitch of the speech generated by Edge"
            " TTS."
        ),
        value=0,
        minimum=-100,
        maximum=100,
        step=1,
    )
    tts_speed_change: SliderConfig = SliderConfig(
        label="TTS speed change",
        info="The percentual change to the speed of the speech generated by Edge TTS.",
        value=0,
        minimum=-50,
        maximum=100,
        step=1,
    )
    tts_volume_change: SliderConfig = SliderConfig(
        label="TTS volume change",
        info="The percentual change to the volume of the speech generated by Edge TTS.",
        value=0,
        minimum=-100,
        maximum=100,
        step=1,
    )
    clean_voice: CheckboxConfig = CheckboxConfig(
        label="Clean converted voice",
        info="Whether to clean the converted voice using noise reduction algorithms.",
        value=True,
        exclude_value=True,
    )
    clean_strength: SliderConfig = SliderConfig.clean_strength(visible=True)
    output_gain: SliderConfig = SliderConfig.gain(
        label="Output gain",
        info="The gain to apply to the converted speech.<br><br>",
    )


class TrainingConfig(BaseTabConfig):
    """
    Common component configuration settings for training tabs.

    Attributes
    ----------
    dataset_type : DropdownConfig
        Configuration settings for a dataset type dropdown component.
    dataset : DropdownConfig
        Configuration settings for a dataset dropdown component.
    dataset_name : TextboxConfig
        Configuration settings for a dataset name textbox component.
    preprocess_model : DropdownConfig
        Configuration settings for a model name dropdown component
        for audio preprocessing.
    version : DropdownConfig
        Configuration settings for a model version dropdown component.
    f0_guidance : CheckboxConfig
        Configuration settings for an F0 guidance checkbox component.
    sample_rate : DropdownConfig
        Configuration settings for a sample rate dropdown component.
    normalization_mode: DropdownConfig
        Configuration settings for a normalization mode dropdown
        component.
    filter_audio : CheckboxConfig
        Configuration settings for a filter audio checkbox component.
    clean_audio : CheckboxConfig
        Configuration settings for a clean audio checkbox component.
    clean_strength : SliderConfig
        Configuration settings for a clean strength slider component.
    split_method : DropdownConfig
        Configuration settings for an audio splitting method dropdown
        component.
    chunk_len : SliderConfig
        Configuration settings for a chunk length slider component.
    overlap_len : SliderConfig
        Configuration settings for an overlap length slider component.
    preprocess_cores : SliderConfig
        Configuration settings for a CPU cores slider component for
        preprocessing.
    extract_model : DropdownConfig
        Configuration settings for a model name dropdown component for
        feature extraction.
    f0_method : DropdownConfig
        Configuration settings for an F0 method dropdown component.
    include_mutes : SliderConfig
        Configuration settings for an include mutes slider component.
    extract_cores : SliderConfig
        Configuration settings for a CPU cores slider component for
        feature extraction.
    extraction_acceleration : HardwareAccelerationConfig
        Configuration settings for a hardware acceleration component for
        feature extraction.
    extraction_gpus : DropdownConfig
        Configuration settings for a GPU dropdown compoennt for feature
        extraction.
    train_model : DropdownConfig
        Configuration settings for a model name dropdown component for
        training.
    num_epochs : SliderConfig
        Configuration settings for a number of epochs slider component.
    batch_size : SliderConfig
        Configuration settings for a batch size slider component.
    detect_overtraining : CheckboxConfig
        Configuration settings for a detect overtraining checkbox
        component.
    overtraining_threshold : SliderConfig
        Configuration settings for an overtraining threshold slider
        component.
    vocoder : DropdownConfig
        Configuration settings for a vocoder dropdown component.
    index_algorithm : DropdownConfig
        Configuration settings for an index algorithm dropdown
        component.
    pretrained_type : DropdownConfig
        Configuration settings for a pretrained model type dropdown
        component.
    custom_pretrained_model : DropdownConfig
        Configuration settings for a custom pretrained model dropdown
        component.
    save_interval : SliderConfig
        Configuration settings for a save-interval slider component.
    save_all_checkpoints : CheckboxConfig
        Configuration settings for a save-all-checkpoints checkbox
        component.
    save_all_weights : CheckboxConfig
        Configuration settings for a save-all-weights checkbox
        component.
    clear_saved_data : CheckboxConfig
        Configuration settings for a clear-saved-data checkbox
        component.
    upload_model : CheckboxConfig
        Configuration settings for an upload voice model checkbox
        component.
    upload_name : TextboxConfig
        Configuration settings for an upload name textbox component.
    training_acceleration : HardwareAccelerationConfig
        Configuration settings for a hardware acceleration component for
        training.
    training_gpus : DropdownConfig
        Configuration settings for a GPU dropdown component for
        training.
    precision: DropdownConfig
        Configuration settings for a precision type dropdown component.
    preload_dataset : CheckboxConfig
        Configuration settings for a preload dataset checkbox component.
    reduce_memory_usage : CheckboxConfig
        Configuration settings for a reduce-memory-usage checkbox
        component.

    See Also
    --------
    BaseTabConfig
        Parent model defining common component configuration settings
        for UI tabs.

    """

    dataset_type: DropdownConfig = DropdownConfig(
        label="数据集类型",
        info="选择要预处理的数据集类型。",
        value=DatasetType.NEW_DATASET,
        choices=list(DatasetType),
        exclude_value=True,
    )
    dataset: DropdownConfig = DropdownConfig(
        label="数据集路径",
        info="现有数据集的路径。选择之前创建的数据集或提供外部数据集路径。",
        value=None,
        allow_custom_value=True,
        visible=False,
        render=False,
        exclude_value=True,
    )
    dataset_name: TextboxConfig = TextboxConfig(
        label="数据集名称",
        info="新数据集的名称。如果数据集已存在，音频文件将被添加到其中。",
        value="My dataset",
        exclude_value=True,
    )
    preprocess_model: DropdownConfig = DropdownConfig(
        label="模型名称",
        info="用于预处理数据集的模型名称。选择现有模型或输入新模型名称。",
        value="My model",
        allow_custom_value=True,
        render=False,
        exclude_value=True,
    )
    version: DropdownConfig = DropdownConfig(
        label="模型版本",
        info="RVC 模型版本。V2 使用 768 维特征，质量更高。",
        value=RVCVersion.V2,
        choices=list(RVCVersion),
        exclude_value=True,
    )
    f0_guidance: CheckboxConfig = CheckboxConfig(
        label="F0音高引导",
        info="是否启用 F0 音高引导。AI 翻唱必须开启，确保生成的歌声保持原曲音高。",
        value=True,
        exclude_value=True,
    )
    sample_rate: DropdownConfig = DropdownConfig(
        label="采样率",
        info="数据集中音频文件的目标采样率。AI翻唱建议选48k。",
        value=TrainingSampleRate.HZ_48K,
        choices=list(TrainingSampleRate),
    )
    normalization_mode: DropdownConfig = DropdownConfig(
        label="归一化模式",
        info="数据集中音频文件使用的归一化方法。",
        value=AudioNormalizationMode.POST,
        choices=list(AudioNormalizationMode),
    )
    filter_audio: CheckboxConfig = CheckboxConfig(
        label="过滤音频",
        info="是否通过高通巴特沃斯滤波器去除音频文件中的低频声音。",
        value=True,
    )
    clean_audio: CheckboxConfig = CheckboxConfig(
        label="清理音频",
        info="是否使用降噪算法清理数据集中的音频文件。",
        value=False,
        exclude_value=True,
    )
    clean_strength: SliderConfig = SliderConfig.clean_strength(visible=False)
    split_method: DropdownConfig = DropdownConfig(
        label="音频分割方法",
        info="分割数据集中音频文件的方法。跳过=已分割；简单=已去静音；自动=自动检测静音并分割。",
        value=AudioSplitMethod.AUTOMATIC,
        choices=list(AudioSplitMethod),
        exclude_value=True,
    )
    chunk_len: SliderConfig = SliderConfig(
        label="分段长度",
        info="分割后音频片段的长度。",
        value=3.0,
        minimum=0.5,
        maximum=5.0,
        step=0.1,
        visible=False,
    )
    overlap_len: SliderConfig = SliderConfig(
        label="重叠长度",
        info="分割音频片段之间的重叠长度。",
        value=0.3,
        minimum=0.0,
        maximum=0.4,
        step=0.1,
        visible=False,
    )
    preprocess_cores: SliderConfig = SliderConfig.cpu_cores()

    extract_model: DropdownConfig = DropdownConfig(
        label="模型名称",
        info="用于提取训练特征的模型名称。预处理新数据集后会自动选中其关联模型。",
        value=None,
        render=False,
        exclude_value=True,
    )
    f0_method: DropdownConfig = DropdownConfig(
        label="F0提取方法",
        info="用于提取音高特征的方法。RMVPE 适合大多数场景，速度更快。",
        value=F0Method.RMVPE,
        choices=list(F0Method),
        exclude_value=True,
    )

    include_mutes: SliderConfig = SliderConfig(
        label="包含静音数",
        info="在生成的训练文件列表中包含的静音音频文件数量。如果预处理数据已包含纯静音片段，设为0。",
        value=2,
        minimum=0,
        maximum=10,
        step=1,
    )
    extraction_cores: SliderConfig = SliderConfig.cpu_cores()
    extraction_acceleration: DropdownConfig = DropdownConfig.hardware_acceleration()
    extraction_gpus: DropdownConfig = DropdownConfig.gpu()

    train_model: DropdownConfig = DropdownConfig(
        label="模型名称",
        info="要训练的模型名称。为新模型提取训练特征后会自动选中其名称。",
        value=None,
        render=False,
        exclude_value=True,
    )
    num_epochs: SliderConfig = SliderConfig(
        label="训练轮数",
        info="训练语音模型的轮数。更高的数值可以提升模型性能，但可能导致过拟合。",
        value=300,
        minimum=1,
        maximum=1000,
        step=1,
    )
    batch_size: SliderConfig = SliderConfig(
        label="批次大小",
        info="每个GPU的批次大小。T4建议4-8，A100建议16-32。多GPU时每个GPU独立运行此大小。",
        value=8,
        minimum=1,
        maximum=64,
        step=1,
    )
    detect_overtraining: CheckboxConfig = CheckboxConfig(
        label="检测过拟合",
        info="是否检测过拟合，防止模型过度学习训练数据而丧失泛化能力。",
        value=True,
        exclude_value=True,
    )
    overtraining_threshold: SliderConfig = SliderConfig(
        label="过拟合阈值",
        info="在模型性能没有改善的情况下继续训练的最大轮数。",
        value=30,
        minimum=1,
        maximum=100,
        visible=True,
        step=1,
    )
    vocoder: DropdownConfig = DropdownConfig(
        label="声码器",
        info="训练时用于音频合成的声码器。HiFi-GAN 是唯一支持的声码器。",
        value=Vocoder.HIFI_GAN,
        choices=list(Vocoder),
    )
    index_algorithm: DropdownConfig = DropdownConfig(
        label="索引算法",
        info="为训练模型生成索引文件的方法。Faiss 适合大多数场景。",
        value=IndexAlgorithm.FAISS,
        choices=list(IndexAlgorithm),
    )
    pretrained_type: DropdownConfig = DropdownConfig(
        label="预训练模型类型",
        info="用于微调的预训练模型类型。无=从头训练；默认=使用匹配架构的预训练模型；自定义=使用你提供的模型。",
        value=PretrainedType.DEFAULT,
        choices=list(PretrainedType),
        exclude_value=True,
    )
    custom_pretrained_model: DropdownConfig = DropdownConfig(
        label="自定义预训练模型",
        info="从下拉列表中选择自定义预训练模型进行微调。",
        value=None,
        visible=False,
        render=False,
        exclude_value=True,
    )
    save_interval: SliderConfig = SliderConfig(
        label="保存间隔",
        info="保存模型权重和检查点的轮数间隔。最佳模型权重始终会保存。",
        value=25,
        minimum=1,
        maximum=100,
        step=1,
    )
    save_all_checkpoints: CheckboxConfig = CheckboxConfig(
        label="保存所有检查点",
        info="是否在每个保存间隔保存唯一的检查点。未启用则只保存最新检查点。",
        value=False,
    )
    save_all_weights: CheckboxConfig = CheckboxConfig(
        label="保存所有权重",
        info="是否在每个保存间隔保存唯一的模型权重。未启用则只保存最佳权重。",
        value=False,
    )
    clear_saved_data: CheckboxConfig = CheckboxConfig(
        label="清除已保存数据",
        info="是否在训练开始前删除关联的训练数据。仅在从头训练或重新训练时启用。",
        value=False,
    )
    upload_model: CheckboxConfig = CheckboxConfig(
        label="上传语音模型",
        info="是否自动上传训练好的语音模型以便在 Ultimate RVC 中使用。",
        value=False,
        exclude_value=True,
    )
    upload_name: TextboxConfig = TextboxConfig(
        label="上传名称",
        info="上传的语音模型名称。",
        value=None,
        visible=False,
        exclude_value=True,
    )
    training_acceleration: DropdownConfig = DropdownConfig(
        label="Hardware acceleration",
        info="T4 x2 默认使用 GPU 双卡训练。",
        value=DeviceType.GPU,
        choices=list(DeviceType),
        exclude_value=True,
    )
    training_gpus: DropdownConfig = DropdownConfig.gpu()
    precision: DropdownConfig = DropdownConfig(
        label="精度",
        info="FP16 和 BF16 可以减少显存使用并加速训练。",
        value=PrecisionType.FP32,
        choices=list(PrecisionType),
    )
    preload_dataset: CheckboxConfig = CheckboxConfig(
        label="预加载数据集",
        info="是否将所有训练数据预加载到GPU显存中。可以提高训练速度但需要大量显存。",
        value=False,
    )
    reduce_memory_usage: CheckboxConfig = CheckboxConfig(
        label="减少显存使用",
        info="是否通过激活检查点降低显存使用（代价是训练速度变慢）。适合显存有限的GPU（如<6GB）。",
        value=False,
    )
