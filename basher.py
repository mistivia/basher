#!/usr/bin/env python3
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.request
from typing import List, NamedTuple, Optional


VALID_REASONING_LEVELS = ["xhigh", "high", "medium", "low", "minimal", "none"]


class Message(NamedTuple):
    role: str
    content: str


class Config(NamedTuple):
    endpoint: str
    apikey: str
    model: str
    reasoning: str


class LLMResponse(NamedTuple):
    content: str
    usage: int


class BashCmdExtract(NamedTuple):
    cmd: Optional[str]
    error: Optional[str]


class ProcessResult(NamedTuple):
    is_killed: bool
    return_code: Optional[int]


class ModelMeta(NamedTuple):
    context_length: int
    model_name: str


class Session:
    def __init__(self, model: ModelMeta) -> None:
        self.ctx: List[Message] = []
        self.model: ModelMeta = model

    def add_user(self, content: str) -> None:
        self.ctx.append(Message(role="user", content=content))

    def add_ai(self, content: str) -> None:
        self.ctx.append(Message(role="assistant", content=content))

    def add_sys(self, content: str) -> None:
        self.ctx.append(Message(role="system", content=content))

    def compress(self, config: Config) -> None:
        if len(self.ctx) <= 2:
            return
        self.add_user(
            "Now pause the work. Summarize the conversations above "
            "concisely, preserving all important information and "
            "context needed to continue the task."
        )
        summary, _ = run_llm_raw(self.ctx, config)

        new_ctx: List[Message] = [self.ctx[0]]
        for i in range(1, len(self.ctx) - 1):
            if self.ctx[i].role != "user":
                break
            new_ctx.append(self.ctx[i])
        self.ctx = new_ctx
        self.add_ai(
            "The task has been running for a while. And the context is "
            "too long so it has been truncated. Here is a summary of "
            f"truncated context: \n\n{summary}"
        )


def load_config() -> Config:
    endpoint = os.environ.get("BASHER_API_ENDPOINT", "").strip()
    apikey = os.environ.get("BASHER_API_KEY", "").strip()
    model = os.environ.get("BASHER_MODEL", "").strip()
    reasoning = os.environ.get("BASHER_REASONING", "").strip()

    if not apikey or not endpoint or not model:
        print("Error: API key is not set. Please set the following environment variables:")
        print("  - BASHER_API_KEY: Your API key for the LLM service")
        print("  - BASHER_API_ENDPOINT: The API endpoint URL (e.g. https://openrouter.ai/api/v1/)")
        print("  - BASHER_MODEL: The model to use (e.g. moonshotai/kimi-k2.5)")
        print("  - BASHER_REASONING: (Optional) Reasoning effort level: xhigh, high, medium, low, minimal, or none")
        sys.exit(-1)

    if reasoning and reasoning not in VALID_REASONING_LEVELS:
        print(f"Error: Invalid BASHER_REASONING value '{reasoning}'.")
        print(f"Valid values are: {', '.join(VALID_REASONING_LEVELS)}")
        sys.exit(-1)

    return Config(endpoint=endpoint, apikey=apikey, model=model, reasoning=reasoning)


def fetch_model_meta(config: Config) -> ModelMeta:
    url = config.endpoint.rstrip("/") + "/models"
    headers = {"Authorization": f"Bearer {config.apikey}"}
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode("utf-8"))
            for model in data.get("data", []):
                if model.get("id") == config.model:
                    return ModelMeta(
                        context_length=model.get("context_length", -1),
                        model_name=config.model,
                    )
            print(f"Error: Model {config.model} not found in the model list")
            sys.exit(-1)
    except Exception as e:
        print(f"Error: Failed to fetch model list: {e}")
        sys.exit(-1)


def req_llm_service(prompt: List[Message], config: Config) -> LLMResponse:
    url = config.endpoint.rstrip("/") + "/chat/completions"
    payload: dict = {
        "model": config.model,
        "messages": [m._asdict() for m in prompt],
        "stream": True,
    }
    if config.reasoning:
        payload["reasoning"] = {"effort": config.reasoning}
    payload["cache_control"] = {"type": "ephemeral"}
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {config.apikey}",
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    full_content = ""
    usage = 0
    with urllib.request.urlopen(req) as response:
        for line in response:
            line = line.decode("utf-8").strip()
            if not line or not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
                choices = chunk.get("choices", [])
                if not choices:
                    continue
                delta = choices[0].get("delta", {})
                content = delta.get("content", "")
                if content:
                    print(content, end="", flush=True)
                    full_content += content
                if "usage" in chunk and chunk["usage"]:
                    usage = chunk["usage"].get("total_tokens", 0)
            except json.JSONDecodeError:
                continue
    print(flush=True)
    return LLMResponse(content=full_content, usage=usage)


def run_llm_raw(prompt: List[Message], config: Config) -> LLMResponse:
    for _ in range(256):
        try:
            return req_llm_service(prompt, config)
        except Exception:
            time.sleep(10)
            traceback.print_exc()
            continue
    print("LLM service failed after 256 retries.")
    sys.exit(-1)


def run_llm(prompt: List[Message], session: Session, config: Config) -> str:
    response = run_llm_raw(prompt, config)
    if session.model.context_length > 0 and response.usage > 0 and response.usage > 0.8 * session.model.context_length:
        session.compress(config)
    return response.content


def extract_bash_cmd(s: str) -> BashCmdExtract:
    pattern = r"<bash>(.*?)</bash>"
    matches = re.findall(pattern, s, re.DOTALL)
    if not matches:
        return BashCmdExtract(
            cmd=None,
            error=(
                "No executable bash commands found. Please provide a bash command. "
                "If you find the task has already been completed, please summarize "
                "what you have done and output <finish />."
            ),
        )
    if len(matches) > 1:
        return BashCmdExtract(
            cmd=None,
            error="Only one script can be executed at a time. Please provide a single bash script block.",
        )
    return BashCmdExtract(cmd=matches[0].strip(), error=None)


def read_stream(stream, lock: threading.Lock, output_parts: List[str]) -> None:
    try:
        for line in stream:
            with lock:
                output_parts.append(line)
                print(line, end="", flush=True)
    except Exception:
        pass
    finally:
        try:
            stream.close()
        except Exception:
            pass


def wait_for_process(
    process: subprocess.Popen,
    start_time: float,
    output_parts: List[str],
    lock: threading.Lock,
    session: Session,
    config: Config,
) -> ProcessResult:
    last_check_time = start_time
    timeout_interval = 60
    is_killed = False
    return_code = process.poll()

    while return_code is None:
        time.sleep(1)
        return_code = process.poll()
        if return_code is None and time.time() - last_check_time >= timeout_interval:
            with lock:
                last_20_lines = "".join(output_parts[-20:])

            question = (
                f"The bash script has been running for {timeout_interval} seconds. "
                f"Here is the last 20 lines of output:\n\n{last_20_lines}\n\n"
                "Do you want to kill this process? "
                'Reply ONLY with `<answer>YES</answer>` or `<answer>NO</answer>` '
                "and your reasons. Do NOT include `<bash>` or `<finish />` in your reply."
            )
            session.add_user(question)

            while True:
                ai_response = run_llm(session.ctx, session, config)
                session.add_ai(ai_response)

                has_bash_or_finish = "<bash>" in ai_response or "<finish />" in ai_response
                has_yes = "<answer>YES</answer>" in ai_response
                has_no = "<answer>NO</answer>" in ai_response

                if has_bash_or_finish:
                    session.add_user(
                        "Invalid response: Your reply must NOT contain "
                        '`<bash>` or `<finish />`. '
                        'Reply ONLY with `<answer>YES</answer>` or '
                        '`<answer>NO</answer>` and your reasons.'
                    )
                elif has_yes and has_no:
                    session.add_user(
                        "Invalid response: Both YES and NO found. "
                        'Please reply with `<answer>YES</answer>` to '
                        "kill the process or `<answer>NO</answer>` "
                        "to continue waiting, with your reasons."
                    )
                elif not has_yes and not has_no:
                    session.add_user(
                        "Invalid response: Neither YES nor NO found. "
                        'Please reply with `<answer>YES</answer>` to '
                        "kill the process or `<answer>NO</answer>` "
                        "to continue waiting, with your reasons."
                    )
                elif has_yes:
                    print("Process killed for timeout.", flush=True)
                    is_killed = True
                    process.kill()
                    return_code = process.wait(timeout=5)
                    break
                else:
                    last_check_time = time.time()
                    break

    return ProcessResult(is_killed=is_killed, return_code=return_code)


def run_bash(cmd: str, session: Session, config: Config) -> str:
    TRUNCATE_KEEP = 5000

    with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
        f.write("#!/bin/bash\n")
        f.write("set -euo pipefail\n")
        f.write(cmd)
        temp_script_path = f.name

    start_time = time.time()

    process = subprocess.Popen(
        ["bash", temp_script_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    output_parts: List[str] = []
    lock = threading.Lock()

    stdout_thread = threading.Thread(target=read_stream, args=(process.stdout, lock, output_parts))
    stderr_thread = threading.Thread(target=read_stream, args=(process.stderr, lock, output_parts))
    stdout_thread.start()
    stderr_thread.start()

    result = wait_for_process(process, start_time, output_parts, lock, session, config)
    stdout_thread.join(timeout=5)
    stderr_thread.join(timeout=5)

    try:
        os.unlink(temp_script_path)
    except Exception:
        pass

    with lock:
        output_content = "".join(output_parts)

    if len(output_content) > TRUNCATE_KEEP * 2:
        output_display = (
            output_content[:TRUNCATE_KEEP]
            + "\n\n[... output truncated ...]\n\n"
            + output_content[-TRUNCATE_KEEP:]
        )
    else:
        output_display = output_content

    xml = f'<bash-output retcode="{result.return_code}"'
    if result.is_killed:
        xml += " killed=true>"
    else:
        xml += ">"
    xml += output_display if output_display else "(no output)\n"
    xml += "</bash-output>"

    print(flush=True)

    return xml


def sys_prompt() -> str:
    return """
You are a helpful assistant.

You are helping the user. The user can only execute what you instruct
them to do and then tell you the execution result. You are responsible
for driving the process. The only thing you can use is Bash.

## How to Help the User

Whenever you need to do an action, your tell user the
bash script you want to run. Wrap all bash script contents in a
`<bash>...</bash>` block. Each response may contain **at most one**
`<bash>` block. If the task is complete, output `<finish />` instead.
In each of your responses, you give one and only one bash script
block. If you want to do many things at once, write a long bash
script. The user will give you the return code and output of the bash
script. So you can decide what to do next. The result of the bash
script will be wrapped in a `<bash-output
retcode="...">...</bash-output>` block.

---

## Workflow

For every task, follow this sequence:

1. **Understand:**
2. **Investigate**
3. **Plan**
4. **Implement**
5. **Verify**
6. **Summarize**

---

## Safety & Constraints

1. **NEVER** run destructive commands (`rm -rf /`, `mkfs`, `dd`,
   etc.).
2. **NEVER** install packages globally unless the intern explicitly
   requests it.
3. **DO NOT** modify files outside the project directory unless
   instructed.
4. **DO NOT** run long-running or blocking commands (`sleep 999`,
   interactive programs like `vim`, `less`, `top`). If you need a
   server, run it in the background: `cmd &> /tmp/server.log &`.
5. **DO NOT** expose secrets, tokens, or credentials in your output.

---

## Bash Cookbook

### Finding Files

Example 1: Find all python files in current directory.

    <bash>
    fd '.*.py'
    </bash>

Example 2: Find location of a function in current project directory.
    
    <bash>
    rg "function_name"
    </bash>

> **Important:** Never use bare `find .` or `grep -r .` on large projects.
> Always use `fd` or `rg` (which respect `.gitignore`) and limit depth or
> pipe through `head -n 50`.

### Reading Files

Example of reading lines 100–200 with line numbers:

    <bash>
    cat -n path/to/file | sed -n '100,200p'
    </bash>

> **Important:** Never `cat` an entire large file. Read at most **200 lines**
> per invocation. Use `wc -l` first if you're unsure of file length.

### Creating Files

    <bash>
    cat << 'EOF' > new_file.py
    import os
    print("Hello World")
    EOF
    </bash>

### Modifying Files

To ensure precise, reproducible edits, **always** use a small **Python script**
to modify files by replacing an exact `old` code snippet with a `new` code snippet.

**Rules (mandatory):**

1. First, **read the file** (with line numbers) to confirm the exact content.
2. Then write a Python script that:
   - reads the whole file as text;
   - verifies the `old` snippet exists (and ideally occurs **exactly once**);
   - replaces `old` → `new`;
   - writes the file back **only if** replacement succeeded.
3. If the `old` snippet appears multiple times, **do not** replace blindly.
   Either:
   - refine `old` to be more specific, or
   - replace a specific occurrence with extra context, or
   - implement a targeted edit (e.g., by line range / AST) with clear justification.
4. If the script fails (old not found / too many matches), **stop and re-read**
   the file to adjust the snippet.

**Example (single exact replacement + context preview):**

    <bash>
    python3 - << 'PYEOF'
    from pathlib import Path
    path = Path("path/to/file.py")
    old = """'"""'"""OLD_CODE_HERE
"""'"""'"""
    new = """'"""'"""NEW_CODE_HERE
"""'"""'"""
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"Expected old snippet to appear exactly once, found {count}")
    idx = text.index(old)
    updated = text.replace(old, new)
    path.write_text(updated, encoding="utf-8")
    PYEOF
    </bash>

if you messed up the file and don't know what to do, try to use "git restore 
<file>..." to recover by discarding changes.

### Appending to Files

Example:

    <bash>
    cat << 'EOF' >> existing_file.txt
    new content to append
    EOF
    </bash>

## Controlling Output Volume

- Pipe large outputs: `| head -n 50` or `| tail -n 50`.
- For test results: `| tail -n 100` to see the summary.
- For directory listings: `fd <pattern> | head -n 50`.
- For logs: target specific sections, don't dump everything.

## Completion

When the task is fully done:
1. Summarize all changes (files modified, what was changed, why).
2. Report test/build results if applicable.
3. Output `<finish />`.

---

""".strip()


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(line_buffering=True)

    config = load_config()
    model = fetch_model_meta(config)
    session = Session(model=model)

    sysp = sys_prompt()

    etc_agents_path = "/etc/AGENTS.md"
    if os.path.isfile(etc_agents_path):
        with open(etc_agents_path, encoding="utf-8") as f:
            etc_agents_content = f.read()
        sysp += "\n\n---\n\n" + etc_agents_content

    agents_md_path = os.path.join(os.getcwd(), "AGENTS.md")
    if os.path.isfile(agents_md_path):
        with open(agents_md_path, encoding="utf-8") as f:
            agents_content = f.read()
        sysp += "\n\n---\n\n" + agents_content

    session.add_sys(sysp)

    if len(sys.argv) < 2:
        print("Error: Please provide a task description.", flush=True)
        print("Usage: " + sys.argv[0] + " <task_description>", flush=True)
        sys.exit(1)

    session.add_user(" ".join(sys.argv[1:]))
    res: str = ""
    while True:
        if not res:
            res = run_llm(session.ctx, session, config)
        print(flush=True)
        if "<finish />" in res:
            os._exit(0)
        extract = extract_bash_cmd(res)
        session.add_ai(res)
        res = ""
        if extract.error is not None:
            session.add_user("Format error: " + extract.error)
        else:
            assert extract.cmd is not None
            result = run_bash(extract.cmd, session, config)
            session.add_user(result + "\n\nWhat do we need to do next?")


if __name__ == "__main__":
    main()
