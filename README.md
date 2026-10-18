# xiaozhi-esp32-server (slim) — Robot phiên dịch Việt · Anh · Trung

Fork tinh gọn của [xinnan-tech/xiaozhi-esp32-server](https://github.com/xinnan-tech/xiaozhi-esp32-server) (MIT) cho một robot phiên dịch dùng firmware [xiaozhi-esp32](https://github.com/78/xiaozhi-esp32).
Server **không chạy model AI cục bộ**: mọi bước ASR, LLM, TTS đều gọi API cloud, nên chạy được trên máy nhỏ như Raspberry Pi 3B.

README gốc (tiếng Trung) được giữ ở [docs/readme/README_upstream_zh.md](docs/readme/README_upstream_zh.md). Phần lớn tài liệu gốc trong `docs/` mô tả bản đầy đủ và **không còn áp dụng** cho bản này (xem mục "Đã bỏ").

## Luồng xử lý

```
ESP32-S3 (mic + loa) ──WebSocket/Opus──▶ server (Python)
   VAD (Silero, onnx) → ASR (Whisper qua Groq/OpenAI, hoặc Google Chirp 3)
   → LLM (Gemini/DeepSeek/OpenAI, API tương thích OpenAI) → TTS (EdgeTTS/OpenAI)
```

Mỗi lượt hội thoại được log ra console:

```
[NGHE] <lời nhận dạng được>
[DICH] <bản dịch của LLM>
```

## Chạy nhanh (Windows/Linux)

Yêu cầu: Python 3.10+, thư viện Opus (`apt install libopus0 ffmpeg` trên Linux/Pi; trên Windows cần `opus.dll` trong PATH).

```bash
cd main/xiaozhi-server
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
mkdir -p data                                     # data/ đã nằm trong .gitignore
```

Tạo `data/.config.yaml` để ghi đè cấu hình và giữ khóa API ngoài git (đừng sửa khóa trực tiếp trong `config.yaml`):

```yaml
selected_module:
  ASR: GroqASR
  LLM: GeminiLLM
ASR:
  GroqASR:
    api_key: gsk_...
LLM:
  GeminiLLM:
    api_key: ...
```

Khởi động server (mất khoảng 20 giây, cổng 8000 là WebSocket, 8003 là OTA):

```bash
python app.py
```

Test không cần ESP32 hay loa, bằng client giả lập:

```bash
python scripts/sim_client.py --text "Hello, how are you today?" --lang en
python scripts/sim_client.py --text "Xin chào, bạn khỏe không?" --lang vi
python scripts/sim_client.py --wav file.wav
```

Chi tiết cấu hình, lệnh giọng nói, test và xử lý lỗi: [docs/translator-robot.md](docs/translator-robot.md).

## Đã giữ

| Thành phần | Nội dung |
| :--- | :--- |
| Server | WebSocket, OTA, MCP |
| VAD | Silero (onnxruntime) |
| ASR | `openai` (dùng cho OpenAI và Groq), `google_chirp` (Chirp 3) |
| LLM | `openai` (OpenAI, Gemini, DeepSeek qua endpoint tương thích OpenAI) |
| TTS | EdgeTTS, OpenAI TTS |
| Intent / Memory | `function_call`, `nomem` |
| Plugin | `get_time`, `handle_exit_intent` |

## Đã bỏ

Console quản lý (`manager-api`, `manager-web`, `manager-mobile`), digital-human, ASR/TTS/LLM cục bộ hoặc của các nhà cung cấp khác, 4 provider Memory, `intent_llm`, 11 plugin, dữ liệu nhạc, model SenseVoice. Các gói `torch`, `funasr`, `sherpa-onnx`, `vosk` đã bị loại khỏi `requirements.txt`.

## Trạng thái và giới hạn

- Đã chạy thật trên Windows với Groq (ASR) và Gemini (LLM), test bằng `sim_client.py`. Chưa chạy trên Raspberry Pi 3B và chưa chạy với ESP32 thật (firmware chưa build).
- Provider Chirp 3 mới test bằng mock, chưa gọi API thật.
- EdgeTTS là API không chính thức, có thể hỏng bất cứ lúc nào.
- Chưa có chống echo (AEC); dự kiến half-duplex (tắt mic khi loa phát), chưa làm trong firmware.

## Giấy phép

MIT, giữ nguyên theo dự án gốc ([LICENSE](LICENSE)).
