import json
import pathlib
import html
import re
import sys
from datetime import datetime


def format_ts(ts):
    if not ts:
        return ""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ts


def pretty_json(obj, max_len=120000):
    s = json.dumps(obj, indent=2, ensure_ascii=False)
    if len(s) > max_len:
        s = s[:max_len] + "\n…(truncated)…"
    return s


def extract_text(payload):
    if isinstance(payload.get("message"), str):
        return payload["message"]

    if isinstance(payload.get("text"), str):
        return payload["text"]

    if payload.get("type") in ("message", "agent_message"):
        parts = []
        for c in payload.get("content", []):
            if isinstance(c, dict) and c.get("type") in ("input_text", "output_text"):
                parts.append(c.get("text", ""))
        return "\n".join(parts)

    return ""


CODE_BLOCK = re.compile(r"```([^\n`]*)\n(.*?)\n```", re.DOTALL)


def markdown_to_html(text):

    def repl(match):
        lang = match.group(1).strip()
        code = match.group(2)
        badge = f'<span class="lang">{html.escape(lang)}</span>' if lang else ""
        return f'<div class="codeblock">{badge}<pre><code>{html.escape(code)}</code></pre></div>'

    out = []
    last = 0

    for m in CODE_BLOCK.finditer(text):
        seg = text[last:m.start()]
        if seg:
            seg = html.escape(seg).replace("\n", "<br>")
            out.append(f'<div class="text">{seg}</div>')
        out.append(repl(m))
        last = m.end()

    tail = text[last:]
    if tail:
        tail = html.escape(tail).replace("\n", "<br>")
        out.append(f'<div class="text">{tail}</div>')

    html_text = "".join(out)
    html_text = re.sub(
        r"`([^`\n]+)`",
        lambda m: f"<code class='inline'>{html.escape(m.group(1))}</code>",
        html_text,
    )

    return html_text


def classify(item):

    ptype = item["ptype"]
    payload = item["payload"]

    if ptype == "user_message":
        return "right", "User", "bubble user"

    if ptype in ("message", "agent_message"):
        role = payload.get("role")
        if role == "assistant":
            return "left", "Codex", "bubble assistant"
        if role == "user":
            return "right", "User", "bubble user"

    if ptype in ("function_call", "custom_tool_call"):
        return "left", "Tool Call", "bubble toolcall"

    if ptype in ("function_call_output", "custom_tool_call_output"):
        return "left", "Tool Output", "bubble toolout"

    if ptype in ("reasoning", "agent_reasoning"):
        return "left", "Reasoning", "bubble reasoning"

    if ptype == "token_count":
        return "left", "Token Count", "bubble token"

    return "left", ptype, "bubble meta"


def convert(input_file, output_file):

    rows = [
        json.loads(l)
        for l in pathlib.Path(input_file).read_text().splitlines()
    ]

    session_meta = None
    items = []

    for r in rows:

        if r.get("type") == "session_meta":
            session_meta = r.get("payload")

        if r.get("type") == "response_item":
            p = r.get("payload", {})
            items.append({
                "ts": r.get("timestamp"),
                "ptype": p.get("type", "unknown"),
                "payload": p
            })

    cards = []

    for it in items:

        side, label, css = classify(it)

        ts = format_ts(it["ts"])
        payload = it["payload"]
        ptype = it["ptype"]

        text = extract_text(payload)

        header_extra = ""
        body = ""

        if ptype in ("function_call", "custom_tool_call"):

            name = payload.get("name") or payload.get("tool_name")
            args = payload.get("arguments") or payload.get("args")

            header_extra = f"<span class='pill'>{html.escape(str(name))}</span>" if name else ""

            try:
                args = json.loads(args) if isinstance(args, str) else args
            except Exception:
                pass

            body = f"""
            <details open>
            <summary>arguments</summary>
            <pre class="mono"><code>{html.escape(pretty_json(args))}</code></pre>
            </details>
            """

        elif ptype in ("function_call_output", "custom_tool_call_output"):

            name = payload.get("name")
            out = payload.get("output") or payload.get("result")

            header_extra = f"<span class='pill'>{html.escape(str(name))}</span>" if name else ""

            if isinstance(out, str):
                try:
                    out = json.loads(out)
                except Exception:
                    pass

            body = f"""
            <details open>
            <summary>output</summary>
            <pre class="mono"><code>{html.escape(pretty_json(out))}</code></pre>
            </details>
            """

        elif text:

            body = markdown_to_html(text)

        else:

            body = f"""
            <details>
            <summary>payload</summary>
            <pre class="mono"><code>{html.escape(pretty_json(payload))}</code></pre>
            </details>
            """

        cards.append(f"""
        <div class="row {side}">
        <div class="{css}">
        <div class="meta">
        <span class="name">{label}</span>
        <span class="rightmeta">{header_extra}<span class="time">{ts}</span></span>
        </div>
        <div class="body">{body}</div>
        </div>
        </div>
        """)

    sid = (session_meta or {}).get("id", "")
    started = (session_meta or {}).get("timestamp", "")

    subtitle = f"Session {sid} • Started {format_ts(started)} • {len(items)} events"

    html_page = f"""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Codex Trace</title>

<style>

body {{
background:#0b1220;
color:white;
font-family:system-ui;
margin:0;
}}

.wrap {{
max-width:1100px;
margin:auto;
padding:30px;
}}

.chat {{
background:#111827;
border-radius:15px;
padding:20px;
}}

.row {{
display:flex;
margin:12px 0;
}}

.row.right {{
justify-content:flex-end;
}}

.bubble {{
max-width:850px;
padding:12px 14px;
border-radius:16px;
border:1px solid #334155;
}}

.user {{ background:#3b82f6; }}
.assistant {{ background:#1f2937; }}
.toolcall {{ background:#5b21b6; }}
.toolout {{ background:#065f46; }}
.reasoning {{ background:#92400e; }}
.token {{ background:#334155; }}
.meta {{ background:#1e293b; }}

.meta {{
font-size:12px;
margin-bottom:8px;
display:flex;
justify-content:space-between;
}}

pre {{
overflow-x:auto;
background:#020617;
padding:10px;
border-radius:8px;
}}

</style>
</head>

<body>

<div class="wrap">
<h2>Codex Trace</h2>
<div>{subtitle}</div>

<div class="chat">
{"".join(cards)}
</div>

</div>

</body>
</html>
"""

    pathlib.Path(output_file).write_text(html_page)
    print("HTML written to:", output_file)


if __name__ == "__main__":

    if len(sys.argv) != 3:
        print("Usage:")
        print("python3 convert_jsonl_to_html.py input.jsonl output.html")
        sys.exit(1)

    convert(sys.argv[1], sys.argv[2])
