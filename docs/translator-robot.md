# Hướng dẫn bản slim: robot phiên dịch Việt · Anh · Trung

Tài liệu này chỉ áp dụng cho nhánh `slim`. Kế hoạch phần cứng và roadmap nằm ở `xiaozhi_translator_robot.md` (ngoài repo).

## 1. Cấu hình

Server đọc `config.yaml`, rồi ghi đè bằng `main/xiaozhi-server/data/.config.yaml` nếu có. **Đặt khóa API và lựa chọn module trong `data/.config.yaml`** (đã nằm trong `.gitignore`), không đặt trong `config.yaml`.

### Chọn module (`selected_module`)

| Mục | Giá trị có sẵn |
| :--- | :--- |
| `ASR` | `OpenaiASR`, `GroqASR`, `GoogleChirpASR` |
| `LLM` | `OpenAILLM`, `GeminiLLM`, `DeepSeekLLM`, `GroqLLM` |
| `TTS` | `SilentTTS` (không loa), `EdgeTTS`, `OpenAITTS` |

### ASR

`GroqASR` và `OpenaiASR` dùng chung provider `type: openai` (endpoint `/audio/transcriptions` tương thích OpenAI). Các tùy chọn:

| Khóa | Ý nghĩa |
| :--- | :--- |
| `api_key`, `base_url`, `model_name` | Bắt buộc. Groq: `whisper-large-v3-turbo` hoặc `whisper-large-v3`. OpenAI: `gpt-4o-mini-transcribe` hoặc `gpt-4o-transcribe` |
| `language` | Tùy chọn, mã ISO-639-1 (`vi`, `en`, `zh`). **Để trống hoặc `auto` khi cần nhận diện nhiều ngôn ngữ**, đây là trường hợp của robot phiên dịch |
| `temperature` | Tùy chọn. `0` cho kết quả ổn định hơn |

`GoogleChirpASR` (Google Speech-to-Text v2, model `chirp_3`) cần `pip install google-auth`, `project_id` và file service account (`credentials_file`). Mới test bằng mock.

### LLM

Mọi LLM dùng `type: openai`, chỉ khác `url`, `api_key`, `model_name`. Với Gemini, tên model cần còn được Google hỗ trợ: tên cũ (`gemini-2.0-flash`) đã trả lỗi 404 và bản mặc định hiện là `gemini-3.8-flash`. Nếu gặp 404 "model no longer available", hãy đổi `model_name`.

### Prompt và lệnh giọng nói

Prompt nằm ở `translator-prompt.txt` (template) và khóa `prompt` trong `config.yaml`. Chế độ mặc định là **phiên dịch**; LLM tự nhận ngôn ngữ nói vào:

- Nghe Anh hoặc Trung: dịch sang tiếng Việt.
- Nghe tiếng Việt: dịch sang ngôn ngữ đích (mặc định tiếng Anh).

| Lệnh nói | Tác dụng |
| :--- | :--- |
| "dich sang tieng Trung" / "dich sang tieng Anh" | Đổi ngôn ngữ đích |
| "robot oi" / "hey robot" | Vào chế độ hỏi đáp |
| "tiep tuc dich" / "resume translation" | Quay lại phiên dịch |

Các lệnh này nằm trong prompt, nên độ tin cậy phụ thuộc vào LLM; chưa được thử bằng giọng thật.

### LLM: lưu ý hạn mức free tier

Gemini free tier giới hạn rất thấp: `gemini-3.8-flash` chỉ **20 yêu cầu mỗi ngày** cho mỗi model (lỗi `429 ... GenerateRequestsPerDayPerProjectPerModel-FreeTier`, phải chờ hàng giờ). Mỗi lượt dịch, và mỗi lần ngắt kết nối (câu chào tạm biệt `end_prompt`), tốn một yêu cầu. Khối `GroqLLM` (`openai/gpt-oss-120b`, free tier của Groq, dùng chung khóa với `GroqASR`) là phương án thay thế đã chạy được; kiểm tra danh sách model còn hiệu lực bằng `GET https://api.groq.com/openai/v1/models`.

### Chế độ không loa và bộ lọc mic

| Tùy chọn | Ý nghĩa |
| :--- | :--- |
| `selected_module.TTS: SilentTTS` | Không tạo âm thanh, **không gửi `tts start`** cho thiết bị. Nếu không, thiết bị tắt mic từ lúc nhận dạng đến lúc dịch xong và mất phần đầu câu kế tiếp. Văn bản dịch vẫn log ra `[DICH]` |
| `audio_highpass_hz: 100` | Lọc thông cao (Butterworth bậc 2) trước VAD/ASR để cắt tiếng ù tần số thấp của mic MEMS (đo được 94–98% năng lượng dưới 100 Hz ở đoạn im lặng). `0` = tắt |
| `VAD.SileroVAD.min_silence_duration_ms: 800` | Ngưỡng im lặng để chốt câu. Giá trị 200 làm câu bị cắt ở dấu phẩy ("Hello, how are you" → chỉ nhận "Hello?") |

Nhược điểm đã biết: Whisper đôi khi "bịa" câu từ âm thanh nền gần như im lặng (đã thấy một câu tiếng Pháp), và nhầm âm gần giống ("for two" → "for Drew").

## 2. Chạy và test

1. Khởi động server: `python app.py` (từ `main/xiaozhi-server`). Cần khoảng 20 giây; **kết nối đầu tiên sau khi khởi động còn khởi tạo ASR/VAD/LLM nên chậm hơn**.
2. Chạy `scripts/sim_client.py` ở cửa sổ khác. Client:
   - tạo giọng nói bằng EdgeTTS (hoặc đọc `--wav`), mã hóa Opus rồi gửi lên;
   - **không** gửi `listen stop` mà để VAD tự chốt câu (như thiết bị ở chế độ auto): nó gửi phần giọng nhanh gấp 4 lần và phần im lặng cuối theo thời gian thực, vì VAD đo khoảng im lặng bằng đồng hồ thật;
   - chờ 4 giây sau `hello` để server khởi tạo xong, nếu không âm thanh gửi sớm sẽ bị bỏ.
3. Xem `[NGHE]` và `[DICH]` ở console server (client cũng in `[PHAT]`, `[NGHE]`, `[DICH]`).

Ví dụ đã chạy thật (Groq + Gemini):

| Câu gửi | `[DICH]` |
| :--- | :--- |
| Hello, how are you today? | Xin chào / hôm nay bạn khỏe không? |
| Xin chào, tôi muốn thuê một chiếc xe máy. | Hello / I would like to rent a motorbike |
| 我想订一张去河内的机票。 | Tôi muốn đặt vé đi Hà Nội |

## 3. Xử lý lỗi thường gặp

| Hiện tượng | Nguyên nhân và cách xử lý |
| :--- | :--- |
| `[NGHE]` ra "Thank you" hoặc câu vô nghĩa | Whisper "ảo giác" khi audio quá ngắn hoặc im lặng. Kiểm tra audio đã đủ dài; đặt `temperature: 0` |
| Không có `[NGHE]`, client hết thời gian chờ | Audio gửi trước khi server khởi tạo xong, hoặc VAD chưa thấy đủ im lặng để chốt câu |
| `[DICH]` ra "Xin loi, toi dang ban..." | LLM lỗi. Xem log server: 401 là sai khóa, 404 là sai tên model |
| Cổng 8000 hoặc 8003 bị chiếm | Còn tiến trình `python app.py` cũ; tắt nó (trên Windows `timeout` không tắt được tiến trình con) |
| `NoAudioReceived` từ `edge_tts` | EdgeTTS không ổn định; thử lại |
| Thiếu Opus | Linux: `apt install libopus0`. Windows: đặt `opus.dll` vào PATH |

## 4. Đã làm và chưa làm

- Đã: server chạy thật với Groq (ASR + LLM) và mic INMP441 trên ESP32-S3, nói liên tiếp nhiều câu Anh/Việt, log `[NGHE]`/`[DICH]` ra console, client giả lập.
- Chưa: chạy trên Pi 3B (đo RAM; trên Windows khoảng 137 MB khi có 1 kết nối), Chirp 3 với API thật, firmware ESP32 (khung bo ở `firmware-board/translator-robot-s3`, chưa build), half-duplex.
