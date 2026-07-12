#!/usr/bin/env python3
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.request
from typing import IO, List, NamedTuple, Optional, Union


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


class BashCmd(NamedTuple):
    cmd: str


class BashError(NamedTuple):
    error: str


# Sum type: either a BashCmd (success) or BashError (failure)
BashCmdExtract = Union[BashCmd, BashError]


class ProcessResult(NamedTuple):
    is_killed: bool
    return_code: Optional[int]


class ModelMeta(NamedTuple):
    context_length: int
    model_name: str


class Session(NamedTuple):
    ctx: List[Message]
    model: ModelMeta


def session_add_user(session: Session, content: str) -> None:
    session.ctx.append(Message(role="user", content=content))


def session_add_ai(session: Session, content: str) -> None:
    session.ctx.append(Message(role="assistant", content=content))


def session_add_sys(session: Session, content: str) -> None:
    session.ctx.append(Message(role="system", content=content))


def session_compress(session: Session, config: Config) -> None:
    if len(session.ctx) <= 2:
        return
    session_add_user(
        session,
        "Now pause the work. Summarize the conversations above "
        "concisely, preserving all important information and "
        "context needed to continue the task."
    )
    summary, _ = run_llm_raw(session.ctx, config)

    new_ctx: List[Message] = [session.ctx[0]]
    for i in range(1, len(session.ctx) - 1):
        if session.ctx[i].role != "user":
            break
        new_ctx.append(session.ctx[i])
    session.ctx.clear()
    session.ctx.extend(new_ctx)
    session_add_ai(
        session,
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
                    full_content += content
                if "usage" in chunk and chunk["usage"]:
                    usage = chunk["usage"].get("total_tokens", 0)
            except json.JSONDecodeError:
                continue
    print(full_content, flush=True)
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
        session_compress(session, config)
    return response.content


def extract_bash_cmd(s: str) -> BashCmdExtract:
    pattern = r"<bash>(.*?)</bash>"
    matches = re.findall(pattern, s, re.DOTALL)
    if not matches:
        return BashError(
            error=(
                "No executable bash commands found. Please provide a bash command. "
                "If you find the task has already been completed, please summarize "
                "what you have done and output <finish />."
            ),
        )
    if len(matches) > 1:
        return BashError(
            error="Only one script can be executed at a time. Please provide a single bash script block.",
        )
    return BashCmd(cmd=matches[0].strip())


def read_stream(stream: IO[str], lock: threading.Lock, output_parts: List[str]) -> None:
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


def kill_process(process: subprocess.Popen) -> int:
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        return process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass
    finally:
        if process.stdout is not None:
            try:
                process.stdout.close()
            except Exception:
                pass
        if process.stderr is not None:
            try:
                process.stderr.close()
            except Exception:
                pass
    return -9


def wait_for_process(
    process: subprocess.Popen,
    start_time: float,
    output_parts: List[str],
    lock: threading.Lock,
    session: Session,
    config: Config,
) -> ProcessResult:
    last_check_time = start_time
    timeout_interval = 180
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
            session_add_user(session, question)

            while True:
                ai_response = run_llm(session.ctx, session, config)
                session_add_ai(session, ai_response)

                has_bash_or_finish = "<bash>" in ai_response or "<finish />" in ai_response
                has_yes = "<answer>YES</answer>" in ai_response
                has_no = "<answer>NO</answer>" in ai_response

                if has_bash_or_finish:
                    session_add_user(session, 
                        "Invalid response: Your reply must NOT contain "
                        '`<bash>` or `<finish />`. '
                        'Reply ONLY with `<answer>YES</answer>` or '
                        '`<answer>NO</answer>` and your reasons.'
                    )
                elif has_yes and has_no:
                    session_add_user(session, 
                        "Invalid response: Both YES and NO found. "
                        'Please reply with `<answer>YES</answer>` to '
                        "kill the process or `<answer>NO</answer>` "
                        "to continue waiting, with your reasons."
                    )
                elif not has_yes and not has_no:
                    session_add_user(session, 
                        "Invalid response: Neither YES nor NO found. "
                        'Please reply with `<answer>YES</answer>` to '
                        "kill the process or `<answer>NO</answer>` "
                        "to continue waiting, with your reasons."
                    )
                elif has_yes:
                    print("Process killed for timeout.", flush=True)
                    is_killed = True
                    return_code = kill_process(process)
                    break
                else:
                    last_check_time = time.time()
                    break

    return ProcessResult(is_killed=is_killed, return_code=return_code)


def check_firejail() -> bool:
    firejail_profile = "/etc/firejail/basher.firejail.profile"
    if not shutil.which("firejail"):
        print("Error: firejail is not installed. Please install firejail or use --no-firejail.", file=sys.stderr)
        sys.exit(-1)
    if not os.path.isfile(firejail_profile):
        print(f"Error: firejail profile not found at {firejail_profile}.", file=sys.stderr)
        print("Please ensure basher.firejail.profile is installed to /etc/firejail/ or use --no-firejail.", file=sys.stderr)
        sys.exit(-1)
    return True


def run_bash(cmd: str, session: Session, config: Config, use_firejail: bool = True) -> str:
    TRUNCATE_KEEP = 5000

    with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
        f.write("#!/bin/bash\n")
        f.write("set -euo pipefail\n")
        f.write(cmd)
        temp_script_path = f.name

    start_time: float = time.time()
    process: Optional[subprocess.Popen] = None
    output_parts: List[str] = []
    lock = threading.Lock()
    stdout_thread: Optional[threading.Thread] = None
    stderr_thread: Optional[threading.Thread] = None

    try:
        if use_firejail:
            cmd_list = ["firejail", "--profile=/etc/firejail/basher.firejail.profile", "bash", temp_script_path]
        else:
            cmd_list = ["bash", temp_script_path]
        process = subprocess.Popen(
            cmd_list,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )

        stdout_thread = threading.Thread(target=read_stream, args=(process.stdout, lock, output_parts))
        stderr_thread = threading.Thread(target=read_stream, args=(process.stderr, lock, output_parts))
        stdout_thread.start()
        stderr_thread.start()

        result = wait_for_process(process, start_time, output_parts, lock, session, config)
        stdout_thread.join(timeout=5)
        stderr_thread.join(timeout=5)

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
    finally:
        if process is not None:
            if process.poll() is None:
                kill_process(process)
        for t in (stdout_thread, stderr_thread):
            if t is not None and t.is_alive():
                t.join(timeout=5)
        try:
            os.unlink(temp_script_path)
        except Exception:
            pass


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
5. **Escaping backslashes:** In Python string literals (including triple-quoted
   strings), a single `\\` is an escape character. If your `old`/`new` snippets
   contain literal backslashes, either:
   - double them (`\\\\` represents one literal `\\`), or
   - use a raw string: `r'''...'''` / `r\"\"\"...\"\"\"`.

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


def print_help() -> None:
    print(
        "Usage: basher.py [OPTIONS] [TASK]\n"
        "\n"
        "A CLI tool that uses an LLM to execute bash commands for a given task.\n"
        "\n"
        "Options:\n"
        "  --help              Show this help message and exit.\n"
        "  --no-firejail       Disable firejail sandboxing for bash commands.\n"
        "  --no-interactive    Exit after the task completes instead of prompting\n"
        "                      for further input.\n"
        "\n"
        "Environment Variables:\n"
        "  BASHER_API_ENDPOINT  API endpoint URL (required)\n"
        "                       e.g. https://openrouter.ai/api/v1/\n"
        "  BASHER_API_KEY       API key for authentication (required)\n"
        "  BASHER_MODEL         Model to use (required)\n"
        "                       e.g. moonshotai/kimi-k2.5\n"
        "  BASHER_REASONING     Reasoning effort level (optional)\n"
        "                       Valid values: xhigh, high, medium, low, minimal, none\n"
    )


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(line_buffering=True)

    # Parse command line arguments
    args = sys.argv[1:]
    use_firejail = True
    no_interactive = False

    # Parse flag arguments
    while args and args[0].startswith("--"):
        if args[0] == "--help":
            print_help()
            sys.exit(0)
        elif args[0] == "--no-firejail":
            use_firejail = False
            args = args[1:]
        elif args[0] == "--no-interactive":
            no_interactive = True
            args = args[1:]
        else:
            print(f"Unknown flag: {args[0]}", file=sys.stderr)
            sys.exit(-1)

    if use_firejail:
        check_firejail()

    config = load_config()
    model = fetch_model_meta(config)
    session = Session(ctx=[], model=model)

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

    session_add_sys(session, sysp)
    task = " ".join(args).strip()
    while len(task) == 0:
        if no_interactive:
            print("Error: no task provided and --no-interactive specified.", file=sys.stderr)
            sys.exit(-1)
        try:
            task = input("> ")
        except (KeyboardInterrupt, EOFError):
            print("Exit...", file=sys.stderr)
            sys.exit(0)
    session_add_user(session, " ".join(task))
    while True:
        try:
            ai_response = run_llm(session.ctx, session, config)
            session_add_ai(session, ai_response)
            print(flush=True)
            extract = extract_bash_cmd(ai_response)
            if isinstance(extract, BashError):
                if "<finish />" in ai_response:
                    if no_interactive or not sys.stdin.isatty():
                        os._exit(0)
                    print(file=sys.stderr)
                    try:
                        hint = input("> ")
                    except (KeyboardInterrupt, EOFError):
                        print("Exit...", file=sys.stderr)
                        sys.exit(0)
                    if hint.strip():
                        session_add_user(session, hint.strip())
                    else:
                        session_add_user(session, "continue")
                    continue
                session_add_user(session, "Format error: " + extract.error)
            else:
                assert isinstance(extract, BashCmd)
                bash_result = run_bash(extract.cmd, session, config, use_firejail)
                session_add_user(session, bash_result)
        except KeyboardInterrupt:
            if no_interactive or not sys.stdin.isatty():
                print("Exit...", file=sys.stderr)
                sys.exit(0)
            print(file=sys.stderr)
            try:
                hint = input("> ")
            except (KeyboardInterrupt, EOFError):
                print("Exit...", file=sys.stderr)
                sys.exit(0)
            if hint.strip():
                session_add_user(session, "(User interruption) " + hint.strip())
            else:
                session_add_user(session, "(User interrupted, please continue)")


if __name__ == "__main__":
    main()
