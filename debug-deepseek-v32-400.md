# [OPEN] Debug Session: deepseek-v32-400

## Symptom
- `answer_model` 使用 `Pro/deepseek-ai/DeepSeek-V3.2` 时，调用 SiliconFlow `chat/completions` 返回 `400 Bad Request`。
- 复现场景：聊天问题为 `coffee maker用什么做lvd`。

## Hypotheses
- H1: 当前请求体中某个通用参数不被 `Pro/deepseek-ai/DeepSeek-V3.2` 接受。
- H2: “关闭思考”相关参数对该模型不兼容，导致 `400`。
- H3: answer 阶段输入载荷比 route/summary 更大或结构不同，触发该模型限制。
- H4: 该模型名在当前 API 路径/账户能力下并不支持 answer 阶段的调用方式。

## Evidence Plan
- 对 `answer_model` 请求做最小插桩，记录模型名、关键参数键、messages 大小、rows 数量、HTTP 状态与错误体。
- 复现同一问题，抓取 pre-fix 证据。
- 同时测量聊天链路各阶段耗时：route、load_rows、answer、verify_citations、total。

## Status
- In progress

## Evidence Collected
- `route` for `coffee maker用什么做lvd` selected 2 documents and attached them successfully.
- `answer_model=Pro/deepseek-ai/DeepSeek-V3.2` failed with HTTP `400`.
- Debug log captured:
  - `document_count=2`
  - `row_count=1559`
  - `user_prompt_chars=523619`
  - response body: `{"code":20015,"message":"number of input tokens (241964) has exceeded max_prompt_tokens (163840) limit.","data":null}`
- Same answer payload succeeded with `deepseek-ai/DeepSeek-V4-Pro` in about `85.208s`.

## Hypothesis Status
- H1: Rejected. Current failing request only carries `model/messages/temperature`; no unsupported extra parameter was sent.
- H2: Rejected. No thinking-control parameter was sent for `Pro/deepseek-ai/DeepSeek-V3.2`.
- H3: Confirmed. Answer-stage payload size exceeded the model prompt-token limit.
- H4: Rejected. The model name/path is accepted by the platform; failure reason is explicit token overflow.
