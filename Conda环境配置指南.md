# Conda 环境配置指南（基于 Dockerfile）

## 是否需要完全按照 Dockerfile 配置？

**简短答案**：**不需要完全按照 Dockerfile**，但可以参考关键配置。

### Dockerfile vs Conda 环境的区别

| 方面 | Dockerfile | Conda 环境（本地开发） |
|------|-----------|---------------------|
| **目的** | 生产部署，完整隔离 | 本地开发，灵活配置 |
| **系统依赖** | 完整安装所有系统库 | 按需安装，conda 已提供部分 |
| **Python 包** | 固定版本，完整安装 | 可以灵活调整 |
| **模型预下载** | 预下载 embedding/whisper 模型 | 按需下载（首次使用时） |
| **包管理器** | 使用 `uv` | 使用 `pip` 或 `conda` |
| **Torch 安装** | 明确指定 CPU/CUDA 版本 | 根据需求选择 |

## 推荐的 Conda 环境配置

### 1. Python 版本 ✅ 已满足

```bash
# 当前环境
conda activate smart-work
python --version  # Python 3.11.14 ✅
```

**要求**：Python >= 3.11, < 3.13  
**状态**：✅ 已满足

### 2. 安装项目依赖

#### 方式一：使用 requirements.txt（推荐）

```bash
cd /home/sai/open-webui/backend
conda activate smart-work
pip install -r requirements.txt
```

#### 方式二：使用开发模式安装（推荐用于开发）

```bash
cd /home/sai/open-webui
conda activate smart-work
pip install -e .
```

这会安装所有依赖，并允许代码修改后立即生效。

### 3. 系统依赖（按需安装）

Dockerfile 中安装的系统依赖：
```dockerfile
git build-essential pandoc gcc netcat-openbsd curl jq \
python3-dev ffmpeg libsm6 libxext6
```

**Conda 环境建议**：
- ✅ `git` - 通常已安装
- ✅ `curl` - 通常已安装
- ⚠️ `ffmpeg` - 如果使用语音功能需要安装
- ⚠️ `pandoc` - 如果使用文档转换功能需要安装
- ⚠️ `build-essential` / `gcc` - 编译某些 Python 包时需要

**安装系统依赖（Ubuntu/Debian）**：
```bash
sudo apt-get update
sudo apt-get install -y \
    build-essential \
    pandoc \
    ffmpeg \
    libsm6 \
    libxext6
```

**或使用 conda 安装**：
```bash
conda install -c conda-forge ffmpeg pandoc
```

### 4. PyTorch 安装（可选）

Dockerfile 会根据 `USE_CUDA` 安装不同版本的 PyTorch：

**CPU 版本**（如果不需要 GPU）：
```bash
conda activate smart-work
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
```

**CUDA 版本**（如果需要 GPU）：
```bash
conda activate smart-work
# CUDA 11.8
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# CUDA 12.1
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

**注意**：如果只是使用 ModelScope API，不需要安装 PyTorch。

### 5. 模型预下载（可选）

Dockerfile 会预下载：
- Embedding 模型（sentence-transformers）
- Whisper 模型（语音识别）
- Tiktoken 编码

**本地开发**：这些模型会在首次使用时自动下载，无需预下载。

如果希望预下载（可选）：
```bash
conda activate smart-work
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"
python -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8')"
python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')"
```

## 完整配置步骤

### 步骤 1：激活环境并检查 Python 版本

```bash
conda activate smart-work
python --version  # 应该是 3.11.x
```

### 步骤 2：安装项目依赖

```bash
cd /home/sai/open-webui
conda activate smart-work

# 方式一：开发模式安装（推荐）
pip install -e .

# 或方式二：仅安装后端依赖
cd backend
pip install -r requirements.txt
```

### 步骤 3：安装系统依赖（如果需要）

```bash
# 检查是否已安装
which ffmpeg pandoc gcc

# 如果缺少，使用 conda 安装
conda install -c conda-forge ffmpeg pandoc

# 或使用系统包管理器
sudo apt-get install -y build-essential pandoc ffmpeg
```

### 步骤 4：配置环境变量

确保 `.env` 文件已创建（之前已创建）：
```bash
cat .env
```

### 步骤 5：验证安装

```bash
conda activate smart-work
cd /home/sai/open-webui

# 检查关键包
python -c "import fastapi; print(f'FastAPI: {fastapi.__version__}')"
python -c "import uvicorn; print(f'Uvicorn: {uvicorn.__version__}')"
python -c "import open_webui; print('Open WebUI installed')"
```

### 步骤 6：启动后端

```bash
conda activate smart-work
cd /home/sai/open-webui
open-webui serve

# 或
cd backend
python -m open_webui.main
```

## 与 Dockerfile 的主要差异

### ✅ 可以省略的部分

1. **模型预下载** - 按需下载即可
2. **Ollama 安装** - 如果只使用 ModelScope API，不需要
3. **完整的系统依赖** - 按需安装
4. **uv 包管理器** - 使用 pip 即可
5. **权限配置** - 本地开发不需要

### ⚠️ 需要注意的部分

1. **Python 版本** - 必须 3.11.x
2. **依赖版本** - 建议使用 requirements.txt 中的版本
3. **系统依赖** - 某些功能需要特定系统库
4. **环境变量** - 需要正确配置 `.env`

## 检查清单

- [ ] Python 版本 3.11.x
- [ ] 已安装项目依赖（`pip install -e .`）
- [ ] 已创建 `.env` 文件并配置 ModelScope API
- [ ] 系统依赖已安装（如果需要）
- [ ] 可以成功导入 `open_webui` 模块
- [ ] 可以启动后端服务

## 常见问题

### Q: 是否需要安装 PyTorch？

**A**: 如果只使用 ModelScope API（外部 API），不需要安装 PyTorch。如果需要本地 RAG、语音识别等功能，则需要安装。

### Q: 是否需要预下载模型？

**A**: 不需要。模型会在首次使用时自动下载到缓存目录。

### Q: 依赖版本不匹配怎么办？

**A**: 优先使用 `requirements.txt` 中的版本。如果遇到兼容性问题，可以：
1. 使用 `pip install --upgrade` 升级
2. 或使用 `pip install --force-reinstall` 重新安装

### Q: 系统依赖缺失导致编译失败？

**A**: 安装缺失的系统依赖：
```bash
sudo apt-get install build-essential python3-dev
```

## 总结

**不需要完全按照 Dockerfile 配置**，但应该：

1. ✅ 使用 Python 3.11.x
2. ✅ 安装 `requirements.txt` 中的依赖
3. ✅ 按需安装系统依赖
4. ✅ 配置环境变量
5. ⚠️ 根据功能需求安装 PyTorch（可选）

**推荐配置方式**：
```bash
conda activate smart-work
cd /home/sai/open-webui
pip install -e .  # 开发模式安装
```

这样既满足开发需求，又保持环境简洁。

