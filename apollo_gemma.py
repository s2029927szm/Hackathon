import time

from openai import OpenAI


MODEL_ID = "gemma4:31b"


def main():
    messages = []
    with OpenAI(
        base_url="http://127.0.0.1:11434/v1",
        api_key="ollama",
        timeout=300.0,
        max_retries=0,
    ) as client:
        print(f"使用本地转发端点访问 {MODEL_ID}（输入 quit 退出）\n")
        while True:
            try:
                user_input = input("你: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n已退出。")
                break
            if user_input.lower() in ("quit", "exit"):
                break
            if not user_input:
                continue

            request_messages = messages + [{"role": "user", "content": user_input}]
            start_time = time.perf_counter()
            first_token_time = None
            chunk_count = 0
            reply_parts = []
            print("Gemma 4: ", end="", flush=True)
            try:
                with client.chat.completions.create(
                    model=MODEL_ID, messages=request_messages, stream=True
                ) as stream:
                    for chunk in stream:
                        if not chunk.choices:
                            continue
                        content = chunk.choices[0].delta.content
                        if content:
                            if first_token_time is None:
                                first_token_time = time.perf_counter() - start_time
                            print(content, end="", flush=True)
                            reply_parts.append(content)
                            chunk_count += 1
            except KeyboardInterrupt:
                print("\n已停止生成，本轮未加入历史。")
                continue
            except Exception as exc:
                print(f"\n请求失败: {exc}\n本轮未加入历史，请检查 SSH 隧道和模型服务。\n")
                continue

            total_time = time.perf_counter() - start_time
            if first_token_time is None:
                print("\n未收到文字内容，本轮未加入历史。\n")
                continue
            generation_time = total_time - first_token_time
            speed = chunk_count / generation_time if generation_time > 0 else 0
            print(
                f"\n\n[首字延迟: {first_token_time:.2f}s | "
                f"总耗时: {total_time:.2f}s | 速度: ~{speed:.1f} chunks/s]\n"
            )
            messages = request_messages + [
                {"role": "assistant", "content": "".join(reply_parts)}
            ]


if __name__ == "__main__":
    main()
