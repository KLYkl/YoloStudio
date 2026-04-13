# GitHub 推送整理清单

这份清单用于避免再次出现“`git add .` 把本地杂物一并推上去”的情况。

---

## 一、建议保留在仓库中的内容

这些属于项目源码或文档，通常应该保留：

- `main.py`
- `config.py`
- `requirements.txt`
- `pyrightconfig.json`
- `core/`
- `ui/`
- `utils/`
- `resources/`
- `tests/`
- `docs/`
- `README.md`
- `.gitignore`

---

## 二、默认不要推到 GitHub 的内容

### 1. 工具 / 助手本地目录
- `.codex/`
- `.agent/`
- `.gemini/`

### 2. 缓存 / 临时文件
- `__pycache__/`
- `.pytest_cache/`
- `tmp/`
- `scratch/`
- `D:/`（误生成目录）

### 3. 运行产物
- `logs/`
- `runs/`
- `assets/`（当前更像本地产物目录，不作为正式仓库资源目录）

### 4. 模型 / 大文件
- `weights/`
- `*.pt`
- `*.onnx`

### 5. 备份 / 快捷方式 / 本机杂项
- `*.bak`
- `*.bak.*`
- `*.orig`
- `*.lnk`
- `run_yolodo.bat`（本机启动脚本）
- `agent_plan/`

### 6. 本机配置 / 敏感信息
- `.env`
- `.env.*`
- `config.json`

---

## 三、需要你自己决定是否保留的内容

### `designs/`
里面是设计图/导出图，不影响程序运行。

建议：
- **如果仓库以“源码交付”为主**：可以不放
- **如果你想保留设计过程或展示 UI 演进**：可以保留

### `pencil-new.pen`
这是设计源文件，不是运行依赖。

建议：
- **想公开设计稿**：保留
- **只想交付程序源码**：不保留

---

## 四、推送前检查步骤

### 1. 先看工作区

```bash
git status --short --ignored
```

重点确认：
- 没有把 `.codex/`、`tmp/`、`logs/`、`runs/` 之类东西加进去
- 没有奇怪的本机路径目录
- 没有 `.bak`、`.lnk`、缓存文件

### 2. 不要直接 `git add .`

推荐做法：

```bash
git add README.md docs/ .gitignore
git add main.py config.py requirements.txt
git add core/ ui/ utils/ resources/ tests/
```

然后检查：

```bash
git diff --cached --name-only
```

确认暂存区里只有你真的想发的文件。

### 3. 如果不确定某个路径会不会被忽略

```bash
git check-ignore -v <路径>
```

---

## 五、首次公开仓库建议补齐的内容

### 必做
- `README.md`

### 强烈建议
- `LICENSE`

### 可选
- `docs/assets/`（如果 README 需要放截图，建议放这里，而不是放到当前被忽略的 `assets/`）
- GitHub Release 说明
- 示例数据说明

---

## 六、建议的首发提交思路

### 提交 1：仓库卫生整理
- `.gitignore`
- `README.md`
- 测试中的本机路径清理
- 不该跟踪文件的移除

### 提交 2：功能代码
- 真正准备发布的源码改动

这样以后回头看提交历史时，会清楚很多。

---

## 七、发布前最后确认

发布前至少确认这几件事：

1. 程序能启动
2. 关键测试能过（如未安装 `pytest`，先执行 `pip install pytest`）
3. README 能说明项目是干什么的
4. 仓库里没有模型、日志、输出结果、缓存和本机配置
5. Git 暂存区文件列表是你逐项确认过的

---

## 八、当前仓库已经做过的整理

已处理：
- 增强 `.gitignore`
- 移除已被误跟踪的 `.agent/...` 与 `.bak` 文件
- 清理测试里的硬编码本机路径
- 去掉 `pyrightconfig.json` 里的本机 Conda 路径

还需要你决定：
- 是否保留 `designs/`
- 是否保留 `pencil-new.pen`
- 公开仓库使用什么 License
