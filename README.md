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
| `RVC_RESUME_DATASET` | 可手动恢复的私有状态数据集，如 `user/rvc-name-resume` | 无 |
| `RVC_CONTROL_SECRET` | 可选的登录会话签名密钥（至少 32 字符） | 自动生成 |

首次登录控制台时输入新版 Kaggle Access Token。后端使用官方
`kagglehub==1.0.2` 验证 Token 并自动取得 Dataset owner，Token 只保留在当前
控制服务进程中，不写入 Secrets 或磁盘。不输入或 Token 失效时仍可训练及从浏览器
下载，但会禁用私有 Dataset 上传、跨 Session checkpoint 保存和恢复。训练历史不会
自动恢复：配置 `RVC_RESUME_DATASET` 后，验证 Token，再点击控制台顶部“恢复历史”
才会下载并启用它。控制台固定
绑定本机 `127.0.0.1:7860`，公网入口由自动重启的 Cloudflare Quick Tunnel 提供。

## 项目结构

```
HRVC/
├── models/rvc/
│   ├── embedders/hubert_base/   # 本地 RVC 同源 HuBERT（自动下载）
│   ├── pretraineds/hifi-gan/     # v2 48k F0 预训练模型（自动下载并验真）
│   └── training/                # 训练输出
├── src/ultimate_rvc/
│   ├── rvc/train/train.py       # 训练核心
│   └── control/                 # 训练控制服务与 Web 界面
├── tools/                       # Kaggle 环境准备与启动脚本
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

