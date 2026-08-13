# Kaggle RVC 训练工具

> 基于 [Ultimate RVC](https://github.com/JackismyShephard/ultimate-rvc) v0.6.0 修改
> 修改人：lingran

## 简介

在 Kaggle 免费 GPU 上训练 RVC 声音模型，专为 AI 翻唱优化。仅保留训练功能，移除推理、翻唱、TTS 等无关模块。

## 功能

- **中文界面**：所有标签、按钮、提示信息均为中文
- **GPU 自适应**：双卡自动使用 DDP，单卡自动降级
- **认证公网访问**：通过 cloudflared 访问，密码从 Kaggle Secret 读取或临时生成
- **标准训练底模**：下载并校验与本地新版 RVC 相同的 v2 48k F0 G/D 和 HuBERT
- **Result 页面**：实时显示所有模型训练进度、ETA、损失值
- **三文件下载**：分别下载 `.pth`、`.index` 和 `train.log`，不生成 ZIP
- **过拟合检测**：自动检测过拟合并停止训练
- **私有持久化**：训练完成后把三个文件上传到私有 Kaggle Dataset
- **本地兼容门禁**：模型结构、生成器短帧推理和 768 维 FAISS 索引校验通过后才开放下载

## 使用方法

详见 [Kaggle RVC 教程](KAGGLE_RVC教程.md)

### 快速开始

1. 登录 Kaggle，创建 Notebook
2. 在 Kaggle Secret 中设置 `RVC_REPO_COMMIT` 为已审查发布提交的完整 40 位哈希
3. 上传并打开仓库中的 `rvc_train.ipynb`
4. 设置任一 GPU（推荐 T4 x2）并开启 Internet
5. 按顺序运行所有 Cell
6. 使用输出的 Cloudflare 地址、用户名和密码登录

## 推荐训练参数

| 参数 | 推荐值 | 说明 |
|------|--------|------|
| 模型版本 | v2 | 最新版本 |
| 采样率 | 48000 | 适合 AI 翻唱 |
| F0 预测 | 开启 | 提高音色准确度 |
| F0 方法 | rmvpe | 最准确 |
| Batch Size | 8 | T4x2 安全值 |
| Epochs | 300 | 训练轮数 |
| 保存间隔 | 25 | 每 25 轮保存一次 |
| 精度 | FP32 | 更稳定 |

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `URVC_MODELS_DIR` | 模型存储目录 | `./models` |
| `URVC_CONFIG` | 加载的配置名称 | 默认配置 |
| `RVC_WEB_PASSWORD` | WebUI 登录密码（Kaggle Secret） | 随机生成 |
| `RVC_REPO_COMMIT` | 允许 Notebook detached checkout 的已审查提交（40 位） | 必填 |
| `KAGGLE_USERNAME` | 私有 Dataset 上传账号（Kaggle Secret） | 无 |
| `KAGGLE_KEY` | 私有 Dataset API Key（Kaggle Secret） | 无 |
| `RVC_RESUME_DATASET` | 要恢复的私有状态数据集，如 `user/rvc-name-resume` | 无 |

## 项目结构

```
HRVC/
├── models/rvc/
│   ├── embedders/hubert_base/   # 本地 RVC 同源 HuBERT（自动下载）
│   ├── pretraineds/hifi-gan/     # v2 48k F0 预训练模型（自动下载并验真）
│   └── training/                # 训练输出
├── src/ultimate_rvc/
│   ├── rvc/train/train.py       # 训练核心
│   ├── web/main.py              # Web 界面
│   └── web/tabs/train/          # 训练步骤
├── rvc_train.ipynb              # Kaggle Notebook
└── pyproject.toml               # 项目配置
```

## 本地推理

训练完成后在 Result 页分别下载三个文件。将 `模型名.pth` 放到
`<你的RVC本地目录>\assets\weights`，将同名的 `模型名.index` 放到
`<你的RVC本地目录>\assets\indices`。刷新本地 RVC 模型列表后选择该模型，
索引会按同名规则自动匹配；`模型名_train.log` 只用于查看训练记录。

## 致谢

感谢 [JackismyShephard](https://github.com/JackismyShephard) 的 [Ultimate RVC](https://github.com/JackismyShephard/ultimate-rvc) 项目。

## 许可证

MIT License - 基于 Ultimate RVC 修改
