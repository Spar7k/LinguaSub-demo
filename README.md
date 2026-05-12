# LinguaSub

LinguaSub 是一款 Windows 桌面字幕工具，提供以下核心功能：

- 本地媒体语音识别（基于 `faster-whisper`）
- 云端字幕翻译（支持 OpenAI 兼容接口和 DeepSeek）
- 双语字幕预览、编辑与导出
- AI 工作台：字幕质量分析、内容总结、指令代理

## 技术栈

- 前端：Tauri + React + TypeScript
- 后端：Python
- 媒体工具：FFmpeg + faster-whisper

## 已实现功能

- 视频、音频、SRT 文件导入
- SRT 字幕解析与导出
- Word 导出（双语对照表 + 纯文本转写 `.docx`）
- 视频字幕烧录导出
- 本地语音识别服务
- 翻译配置与多提供商适配器
- 可编辑的双语字幕预览页
- AI 工作台（字幕质量分析、内容总结、指令代理）
- 导出页（支持 SRT、Word、视频烧录）
- 启动环境检测，引导 Windows 打包
- 设置页内置 Windows 卸载入口
- 最近任务面板

## 本地环境依赖

- Rust 和 Tauri 工具链（桌面打包）
- FFmpeg 和 `faster-whisper` 运行环境（开发模式媒体识别）
- Whisper 模型下载（首次本地转录前）
- 有效的翻译 API 密钥（翻译功能）

## 开发运行

1. 安装前端依赖：

```powershell
cd D:\codetest\LinguaSub
npm.cmd install
```

2. 创建 Python 虚拟环境：

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
py -m pip install -r backend\requirements.txt
```

3. 启动后端：

```powershell
npm.cmd run backend:dev
```

4. 启动前端（浏览器模式）：

```powershell
npm.cmd run dev
```

5. 启动 Tauri 桌面应用（需先配置好 Rust 环境）：

```powershell
npm.cmd run tauri:dev
```

## 构建命令

前端生产构建：

```powershell
npm.cmd run build
```

桌面打包构建：

```powershell
npm.cmd run tauri:build
```

当前 Windows 安装程序：

- NSIS 安装包（`-setup.exe`）
- 保留 Tauri 默认的开始菜单快捷方式
- 通过 `src-tauri/windows/hooks.nsh` 自动创建桌面快捷方式
- 安装后可从设置页触发 Windows 卸载流程

后端测试：

```powershell
py -3 -m unittest discover -s backend/tests -p "test_*.py"
```

## 启动检测

LinguaSub 提供本地启动状态报告接口：

- `GET /environment/check`

报告内容包括：

- 当前配置文件路径
- 推荐的 Windows 用户数据路径
- FFmpeg 可用性
- `faster-whisper` 可用性
- 当前默认翻译提供商是否已配置 API 密钥
- 媒体工作流和 SRT 工作流就绪状态

导入页面会直接在 UI 中展示此报告。

## 配置与用户数据

开发环境默认：

- 配置文件：`backend/storage/app-config.json`

发布版本推荐：

- 配置文件：`%APPDATA%\LinguaSub\app-config.json`
- 环境变量：`LINGUASUB_CONFIG_PATH`

用户设置与应用程序安装目录分离。

## 导出行为

默认导出逻辑：

- 导出路径：与导入的源文件同目录
- 双语字幕默认名：`<源文件名>.bilingual.srt`
- 单语字幕默认名：`<源文件名>.single.srt`
- Word 对照表默认名：`<源文件名>_bilingual.docx`
- Word 转写稿默认名：`<源文件名>_transcript.docx`
- 编码：`utf-8-sig`

## Windows 打包

两种发布方式详见：

- [step-10-windows-packaging.md](docs/step-10-windows-packaging.md)

简要说明：

- 开发演示构建：分别运行 Tauri 前端和 Python 后端
- 发布交付构建：打包 Tauri 应用，附带后端运行时文件夹或打包后的后端可执行文件
- 当前安装包格式：NSIS，含安装后桌面快捷方式钩子

## 注意事项

- 缺少 `ffmpeg` 时，视频和音频转录将失败，后端会返回明确的错误信息
- 缺少 `faster-whisper` 时，本地语音识别将失败，后端会返回明确的错误信息
- 翻译提供商未配置 API 密钥时，翻译功能不可用
- 本仓库已包含完整的工作流、校验和打包文档，但一键式 Windows 安装程序仍需目标机器上的打包工具支持
