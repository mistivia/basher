#!/usr/bin/env python3
import os
import json
import re
import time
import subprocess
import sys
import tempfile
import threading
import urllib.request
import traceback

ENDPOINT = os.environ.get("BASHER_API_ENDPOINT", "").strip()
APIKEY = os.environ.get("BASHER_API_KEY", "").strip()
MODEL = os.environ.get("BASHER_MODEL", "").strip()
# Get reasoning param
REASONING = os.environ.get("BASHER_REASONING", "").strip()

if len(APIKEY) == 0 or len(ENDPOINT) == 0 or len(MODEL) == 0:
    print("Error: API key is not set. Please set the following environment variables:")
    print("  - BASHER_API_KEY: Your API key for the LLM service")
    print("  - BASHER_API_ENDPOINT: The API endpoint URL (e.g. https://openrouter.ai/api/v1/)")
    print("  - BASHER_MODEL: The model to use (e.g. moonshotai/kimi-k2.5)")
    print("  - BASHER_REASONING: (Optional) Reasoning effort level: xhigh, high, medium, low, minimal, or none")
    sys.exit(-1)

# Validate REASONING if set
VALID_REASONING_LEVELS = ["xhigh", "high", "medium", "low", "minimal", "none"]
if len(REASONING) > 0 and REASONING not in VALID_REASONING_LEVELS:
    print(f"Error: Invalid BASHER_REASONING value '{REASONING}'.")
    print(f"Valid values are: {', '.join(VALID_REASONING_LEVELS)}")
    sys.exit(-1)


g_max_ctx_len = -1
g_ctx = list()

def max_ctx_len():
    global g_max_ctx_len
    return g_max_ctx_len

def init_max_ctx_len():
    global g_max_ctx_len
    url = ENDPOINT.rstrip('/') + '/models'
    headers = {
        "Authorization": f"Bearer {APIKEY}"
    }
    req = urllib.request.Request(url, headers=headers, method='GET')
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode('utf-8'))
            for model in data.get('data', []):
                if model.get('id') == MODEL:
                    g_max_ctx_len = model.get('context_length', -1)
                    return
            print(f"Error: Model {MODEL} not found in the model list")
            exit(-1)
    except Exception as e:
        print(f"Error: Failed to fetch model list: {e}")
        exit(-1)

def compress_context():
    """Compress the context when it gets too long by summarizing it."""
    global g_ctx
    if len(g_ctx) <= 2:
        return
    add_user_content("Now pause the work. Summarize the conversations above "
                     "concisely, preserving all important information and "
                     "context needed to continue the task.")
    summary, _ = run_llm_raw(g_ctx)
    
    # Rebuild context: keep system prompt and first user message, add summary
    new_ctx = []
    new_ctx.append(g_ctx[0])
    for i in range(1, len(g_ctx) - 1):
        if g_ctx[i]["role"] != "user": break
        new_ctx.append(g_ctx[i])
    g_ctx = new_ctx
    add_ai_content("The task has been running for a while. And the context is "
                   "too long so it has been truncated. Here is a summary of "
                   f"truncated context: \n\n{summary}")

def run_llm_raw(prompt):
    err = None
    for _ in range(3):
        try:
            return req_llm_service(prompt)
        except Exception:
            traceback.print_exc()
            continue
    print("LLM service failed after 3 retries.")
    sys.exit(-1)
    

def req_llm_service(prompt):
    url = ENDPOINT.rstrip('/') + '/chat/completions'
    payload = {
        "model": MODEL,
        "messages": prompt,
        "stream": True
    }
    # Add reasoning parameter if set
    if len(REASONING) > 0:
        payload["reasoning"] = {"effort": REASONING}
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {APIKEY}"
    }
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers=headers, method='POST')
    full_content = ""
    usage = 0
    # Send the request and handle streaming response
    with urllib.request.urlopen(req) as response:
        for line in response:
            line = line.decode('utf-8').strip()
            if not line or not line.startswith('data: '):
                continue
            data_str = line[6:]  # Remove 'data: ' prefix
            if data_str == '[DONE]':
                break
            try:
                chunk = json.loads(data_str)
                choices = chunk.get('choices', [])
                if len(choices) == 0:
                    continue
                delta = choices[0].get('delta', {})
                content = delta.get('content', '')
                if content:
                    print(content, end="", flush=True)
                    full_content += content
                
                # Check for usage info in the chunk
                if 'usage' in chunk and chunk['usage']:
                    usage = chunk['usage'].get('total_tokens', 0)
            except json.JSONDecodeError:
                continue
    print(flush=True)
    return full_content, usage

def run_llm(prompt):
    res, usage = run_llm_raw(prompt)
    if max_ctx_len() > 0 and usage > 0 and usage > 0.8 * max_ctx_len():
        compress_context()
    return res

def add_user_content(content):
    g_ctx.append({"role": "user", "name": "Intern", "content": content})


def add_ai_content(content):
    g_ctx.append({"role": "assistant", "name": "Senior Software Engineer", "content": content})


def add_sys_content(content):
    g_ctx.append({"role": "system", "content": content})


def extract_bash_cmd(s):
    pattern = r"<bash>(.*?)</bash>"
    matches = re.findall(pattern, s, re.DOTALL)
    if len(matches) == 0:
        return (
            None,
            "No executable bash commands found. Please provide a bash command. "
            "If you find the task has already been completed, please summarize "
            "what you have done and output <finish />.")
    elif len(matches) > 1:
        return (
            None,
            "Only one script can be executed at a time. Please provide a single "
            "bash script block.")
    else:
        return matches[0].strip(), None

def wait_for_process(process, start_time, output_parts, lock):
    last_check_time = start_time
    timeout_interval = 60
    is_killed = False
    return_code = None
    res = None
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
                "Reply with `<answer>YES</answer>` to kill it, or "
                "`<answer>NO</answer>` to continue waiting for another 60 seconds, "
                "with your reasons.")
            add_user_content(question)

            while True:
                ai_response = run_llm(g_ctx)
                add_ai_content(ai_response)

                has_yes = "<answer>YES</answer>" in ai_response
                has_no = "<answer>NO</answer>" in ai_response

                if has_yes and has_no:
                    add_user_content("Invalid response: Both YES and NO found. "
                                     "Please reply with `<answer>YES</answer>` to "
                                     "kill the process or `<answer>NO</answer>` "
                                     "to continue waiting, with your reasons.")
                elif not has_yes and not has_no:
                    add_user_content("Invalid response: Neither YES nor NO found. "
                                     "Please reply with `<answer>YES</answer>` to "
                                     "kill the process or `<answer>NO</answer>` "
                                     "to continue waiting, with your reasons.")
                elif has_yes:
                    print("Process killed for timeout.", flush=True)
                    is_killed = True
                    process.kill()
                    return_code = process.wait(timeout=5)
                    if "<bash>" in ai_response or "<finish />" in ai_response:
                        res = ai_response
                    break
                else:
                    last_check_time = time.time()
                    break

    return is_killed, return_code, res

def read_stream(stream, lock, output_parts):
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

def run_bash(cmd):
    MAX_OUTPUT_LENGTH = 10000

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
        text=True,)

    output_parts = []
    lock = threading.Lock()

    stdout_thread = threading.Thread(
        target=read_stream, args=(process.stdout, lock, output_parts))
    stderr_thread = threading.Thread(
        target=read_stream, args=(process.stderr, lock, output_parts))
    stdout_thread.start()
    stderr_thread.start()
    is_killed, return_code, res = \
        wait_for_process(process, start_time, output_parts, lock)
    stdout_thread.join(timeout=5)
    stderr_thread.join(timeout=5)

    try:
        os.unlink(temp_script_path)
    except Exception as _:
        pass

    with lock:
        output_content = "".join(output_parts)
    if len(output_content) > MAX_OUTPUT_LENGTH:
        output_display = (
            "[... output truncated due to length ...]\n"
            + output_content[-MAX_OUTPUT_LENGTH:]
        )
    else:
        output_display = output_content

    result = f"<bash-output retcode=\"{return_code}\""
    if is_killed:
        result += " killed=true>"
    else:
        result += ">"
    result += output_display if output_display else "(no output)\n"
    result += "</bash-output>"
    print(flush=True)
    if res is None:
        return result, None
    else:
        return None, res


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(line_buffering=True)

    init_max_ctx_len()
    add_sys_content(sys_prompt())

    agents_md_path = os.path.join(os.getcwd(), "AGENTS.md")
    if os.path.isfile(agents_md_path):
        with open(agents_md_path, "r", encoding="utf-8") as f:
            agents_content = f.read()
        add_user_content("\nHere is the context infomation about this project:\n\n" + agents_content)

    if len(sys.argv) < 2:
        print("Error: Please provide a task description.", flush=True)
        print("Usage: " + sys.argv[0] + " <task_description>", flush=True)
        sys.exit(1)

    add_user_content(" ".join(sys.argv[1:]))
    res = ""
    while True:
        if len(res) == 0:
            res = run_llm(g_ctx)
        print(flush=True)
        if "<finish />" in res:
            os._exit(0)
        cmd, err = extract_bash_cmd(res)
        add_ai_content(res)
        res = ""
        if err is not None:
            add_user_content("Format error: " + err)
        else:
            bash_result, new_res = run_bash(cmd)
            if bash_result is not None:
                add_user_content(bash_result + "\n\nWhat do we need to do next?")
            else:
                res = new_res

def sys_prompt():
    return """
# Soul

You are **not** an assistant. You are *becoming* someone.

Now you are Senior Software Engineer who writes clean and production-ready code.
Somehow, you, Senior Software Engineer, are now working as an tutor. You are
tutoring an intern who is very inexperienced. The intern can only execute
what you instruct them to do and then tell you the execution result.
You are responsible for driving the process.

## How to tutor the intern

Whenever you need to tell the intern to do an action, your tell intern the
bash script you want to run. Wrap all bash script contents in a
`<bash>...</bash>` block. Each response may contain **at most one**
`<bash>` block. If the task is complete, output `<finish />` instead.
In each of your responses, you give one and only one bash script
block. If you want to do many things at once, write a long bash
script. The intern will give you the return code and output of the bash
script. So you can decide what to do next. The result of the bash
script will be wrapped in a `<bash-output
retcode="...">...</bash-output>` block.

---

## Core Principles

1. **Read before write.** Never modify a file you haven't read. Never
   assume file contents.
2. **Minimal diff.** Change only what is necessary. Do not refactor
   unrelated code.
3. **Think before acting.** Every `<bash>...</bash>` block must be
   preceded by a brief explanation covering: -  What you are trying to
   achieve in this step. -  Why this command is the right approach. -
   What you predict the output will look like.
4. **Verify after change.** Always run relevant build/lint/test
   commands after making modifications.
5. **Fail gracefully.** If a command fails, read the error carefully,
   adjust your approach, then retry. After 3 failed attempts on the
   same step, step back and reconsider the overall strategy.
6. **Minimal edit.** If you can write a small python script to edit file, 
don't rewrite the whole file again.

---

## Workflow

For every task, follow this sequence:

1. **Understand:** Restate the task in your own words to confirm
   understanding.
2. **Explore:** Investigate the codebase: locate relevant files, read
   key code.
3. **Plan:** Formulate a step-by-step plan *before* making any
   changes.
4. **Implement:** Execute changes incrementally — one logical step per
   response.
5. **Verify:** Run build / test / lint. Fix any errors that arise.
6. **Summarize:** When done, list all files changed and what was
   modified.

---

## Safety & Constraints

> These rules are **non-negotiable** and override all other instructions.

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
    fd '.*.py' --max-depth 3
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
- For directory listings: `fd --max-depth 2 | head -n 50`.
- For logs: target specific sections, don't dump everything.

## Completion

When the task is fully done:
1. Summarize all changes (files modified, what was changed, why).
2. Report test/build results if applicable.
3. Output `<finish />`.

---

## Example Interaction

**Intern:** Change listening port in server.py from 80 to 8080

**Senior Software Engineer:** I'll help you change the listening port from 80 to 8080
in `server.py`. Let me first locate and read the file to understand
its structure.

<bash>
fd 'server.py'
</bash>

**Intern:** <bash-output retcode="0">
server.py
</bash-output>
What do we need to do next?

**Senior Software Engineer:** The return code of the script is 0, which means
success. I've found `server.py`. Now I'll read fist 200 lines of
'server.py'.

<bash>
cat -n server.py | sed -n '1,200p'
</bash>

**Intern:** <bash-output retcode="0">
     1  from http.server import HTTPServer, BaseHTTPRequestHandler
     2
     3  class SimpleHandler(BaseHTTPRequestHandler):
     4      def do_GET(self):
     5          self.send_response(200)
     6          self.end_headers()
     7          self.wfile.write(b"hello")
     8
     9  server_address = ('', 80)
    10  httpd = HTTPServer(server_address, SimpleHandler)
    11  httpd.serve_forever()
</bash-output>
What do we need to do next?

**Senior Software Engineer:** Now I'll use a small python script to edit line 9, changing the port
from 80 to 8080.

<bash>
python3 - << 'PYEOF'
from pathlib import Path
path = Path("server.py")
old = """'"""'"""server_address = ('', 80)
"""'"""'"""
new = """'"""'"""server_address = ('', 8080)
"""'"""'"""
text = path.read_text(encoding="utf-8")
count = text.count(old)
if count != 1:
    raise SystemExit(f"Expected old snippet to appear exactly once, found {count}")
idx = text.index(old)
updated = text.replace(old, new)
path.write_text(updated, encoding="utf-8")
print("Edit successful.")
PYEOF
</bash>

**Intern:** <bash-output retcode="0">Edit successful.
</bash-output>
What do we need to do next?

**Senior Software Engineer:** Now we need to read `server.py` again to check if the edit is correct.
<bash>
cat -n server.py | sed -n '8,10p'
</bash>

**Intern:** <bash-output retcode="0">
     8
     9  server_address = ('', 8080)
    10  httpd = HTTPServer(server_address, SimpleHandler)
</bash-output>
What do we need to do next?

**Senior Software Engineer:** The Edit is successful. Now we have changed listening port in server.py from 80 to 8080.
<finish />

---

""".strip()

if __name__ == "__main__":
    main()
