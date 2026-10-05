# 最小可执行工程格式

依赖：Python 3.10+ 标准库，FFmpeg（包含 libx264、libass）。可选 ffprobe。无需 Node、MoviePy、商业剪辑软件或特定 agent 框架。

如果不在 PATH 上，设置 `FFMPEG_BIN` 为 FFmpeg 可执行文件路径；可选 `FFPROBE_BIN`。在新机器上先检查 `ffmpeg -version` 和 `ffmpeg -filters`，再运行合成素材自检：

```sh
python /path/to/narrated-demo-video/scripts/smoke_test.py
```

PowerShell 示例：`$env:FFMPEG_BIN = 'D:\tools\ffmpeg.exe'`；Bash 示例：`export FFMPEG_BIN=/opt/ffmpeg/bin/ffmpeg`。这些只是用户按本机替换的路径示例，不需要在工程里保存。

## project.json

从 [example-project.json](example-project.json) 复制并替换素材路径。模板不附带用户视频或商业音乐，直接执行前必须有对应文件。

| 字段 | 含义 |
| --- | --- |
| `version` | 固定 1 |
| `canvas` | `width` / `height` 为正偶数，`fps` 为 1–120 整数；默认 1920×1080、30 fps |
| `clips` | 按数组顺序拼接；总片长为各 `duration` 之和，不另外填 total |
| `clips[].source` | 相对 project.json 的本地素材路径，可包含中文和空格 |
| `clips[].kind` | `video`（默认）或 `image`；图片会保持整个镜头时长 |
| `clips[].in` | 视频源入点秒数，默认 0；图片不使用此字段 |
| `clips[].duration` | 镜头秒数，必须落在帧边界，如 30 fps 下的 1、1.5、2 秒 |
| `clips[].fit` | `contain` 等比补边（默认）或 `cover` 等比居中裁切 |
| `audio` | 独立音轨片段，可以重叠；视频声音不会自动混入 |
| `audio[].role` | `voice`、`music`、`sfx`，输出对应分轨 |
| `audio[].source` | WAV/MP3/有音轨的视频等本地文件路径 |
| `audio[].start` | 在最终视频中的开始秒数，默认 0 |
| `audio[].in` | 源素材入点，默认 0 |
| `audio[].duration` | 在时间线上占用的槽位秒数，不得超出视频总长 |
| `audio[].source_duration` | 可选，取用源音频的长度；默认取源文件从 in 开始的全部剩余音频 |
| `audio[].gain` | 线性音量倍率，默认 1；20% 写 0.2 |
| `audio[].loop` | 默认 false；音乐/音效可循环填满槽位，不支持与 source_duration 同时使用 |
| `audio[].fade_in/out` | 首尾淡入/淡出秒数，默认 0 |
| `audio[].normalize` | 仅 voice 生效，默认 true，先做高通与单遍 loudnorm，再乘 gain |
| `audio[].max_tempo` | 仅 voice 生效，默认 1.2；必须在 1–2 之间，超出所需倍率即报错 |
| `subtitles` | `{start, end, text}`，时间为秒，文本中 `\n` 表示换行；默认无字幕 |
| `subtitle_style` | 可选 `font`、`size`、`margin_v`；字体必须在本机存在，默认 sans-serif 可能无中文字形 |

voice 的 source_duration 全部内容必须放进槽位，不能因为槽位短而静默截断。music/sfx 可按槽位结束裁切；较短非循环音频末尾补静音。循环音频按完整源文件循环，若要无缝循环源文件的一小段，请先裁出这一段作为新素材。

渲染是顺序剪辑，不支持轨道级画面叠加、转场、自动字幕对齐或自动精确节拍检测。这些可由 agent 额外调用 FFmpeg 制作成单独镜头后输入；不应假称脚本已经具备。

```sh
python scripts/render_video.py render --project project.json --out output/v1
```

输出 `picture.mp4` 为静音画面，`clean.mp4` 为不烧字幕的成片，`final.mp4` 为烧字幕的成片。字幕为空时 clean/final 画面相同。分轨为 `voice.wav`、`music.wav`、`sfx.wav`，混音为 `mix.wav`；混音分轨使用浮点 WAV 保留峰值余量。`build.json` 记录时长、画面签名、视频流哈希和仍需人工检查的项。

输出目录还含 `project.snapshot.json` 方便追溯，但其中路径依然相对原 project.json；迁移工程应连同原 project.json 和其素材目录一起复制，不能只移动快照就当作完整工程。缓存/ffconcat 文件可能含本机路径，不适合直接公开。

修改音量后，保留旧版，再在含原构建结果的目录中运行：

```sh
python scripts/render_video.py remix --project project.json --out output/v1
```

remix 不接受变更后的画面/字幕。如果字体安装或渲染环境改变，需要重新 `render --force`；同一个输出目录不要并发渲染。

## 分段 TTS

`voice-request.json`：

```json
{
  "defaults": {"text_lang": "zh", "speed_factor": 1.05, "max_sec": 15},
  "segments": [
    {"id": "01", "text": "我只是想做个小玩具，结果开了一家公司。"},
    {"id": "02", "text": "看，这就是我们的第一位员工。", "params": {"speed_factor": 1.0}}
  ]
}
```

在私有环境中设置用户给的 `MAMBO_TTS_URL`；若需要鉴权，再设置 `TTS_HEADERS_JSON` 为 JSON 请求头对象。不要把变量值贴到公开仓库或输出日志，也不要启用 shell trace。客户端不自动跟随重定向。

```sh
python scripts/tts_client.py --input voice-request.json --out voice --timeout 120
```

默认最多对暂时性错误重试两次。`--endpoint-env` / `--headers-env` 可更换变量名称。每段写入独立 WAV；`manifest.json` 含文本、实际时长、采样率、内容哈希、请求签名，供安排时间线；不包含服务地址和认证头。已完成分段在后续段落失败后仍可复用。默认串行，适用于服务自己带排队锁的情况。

TTS 输出只被技术检查为完整 PCM WAV；是否说完、是否读错需要试听。接近 max_sec 会给 warning，但远低于上限也不能保证语义正确。
