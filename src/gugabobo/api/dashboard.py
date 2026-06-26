def dashboard_html() -> str:
    return """
    <!doctype html>
    <html lang="zh-CN">
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>咕嘎BoBo Dashboard</title>
        <style>
          :root {
            color-scheme: light;
            --bg: #f6f7f9;
            --panel: #ffffff;
            --line: #d8dde6;
            --text: #17202a;
            --muted: #667085;
            --accent: #0b6bcb;
            --good: #127c42;
            --warn: #b25e00;
          }
          * { box-sizing: border-box; }
          body {
            margin: 0;
            background: var(--bg);
            color: var(--text);
            font-family: "Segoe UI", system-ui, sans-serif;
            font-size: 14px;
          }
          header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 14px 20px;
            border-bottom: 1px solid var(--line);
            background: var(--panel);
            position: sticky;
            top: 0;
            z-index: 2;
          }
          h1 {
            margin: 0;
            font-size: 20px;
            font-weight: 650;
            letter-spacing: 0;
          }
          main {
            display: grid;
            grid-template-columns: minmax(320px, 1fr) minmax(380px, 1.3fr);
            gap: 16px;
            padding: 16px;
          }
          section {
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 6px;
            overflow: hidden;
          }
          h2 {
            margin: 0;
            padding: 10px 12px;
            border-bottom: 1px solid var(--line);
            font-size: 14px;
            font-weight: 650;
            background: #fbfcfd;
          }
          .grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 10px;
            padding: 12px;
          }
          .metric {
            border: 1px solid var(--line);
            border-radius: 6px;
            padding: 10px;
            min-width: 0;
          }
          .metric span {
            display: block;
            color: var(--muted);
            font-size: 12px;
          }
          .metric strong {
            display: block;
            margin-top: 4px;
            font-size: 22px;
            line-height: 1.1;
          }
          table {
            width: 100%;
            border-collapse: collapse;
            table-layout: fixed;
          }
          th, td {
            padding: 8px 10px;
            border-bottom: 1px solid var(--line);
            text-align: left;
            vertical-align: top;
            overflow-wrap: anywhere;
          }
          th {
            color: var(--muted);
            font-size: 12px;
            font-weight: 600;
            background: #fbfcfd;
          }
          .muted { color: var(--muted); }
          .ok { color: var(--good); font-weight: 650; }
          .warn { color: var(--warn); font-weight: 650; }
          .stack {
            display: grid;
            gap: 16px;
          }
          pre {
            margin: 0;
            padding: 12px;
            max-height: 320px;
            overflow: auto;
            background: #111827;
            color: #e5e7eb;
            font: 12px/1.5 Consolas, monospace;
          }
          .toolbar {
            display: flex;
            gap: 12px;
            align-items: center;
            color: var(--muted);
            font-size: 13px;
          }
          button {
            border: 1px solid var(--line);
            background: #fff;
            border-radius: 6px;
            padding: 6px 10px;
            cursor: pointer;
          }
          button:hover { border-color: var(--accent); }
          @media (max-width: 960px) {
            main { grid-template-columns: 1fr; }
            .grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
          }
        </style>
      </head>
      <body>
        <header>
          <h1>咕嘎BoBo Dashboard</h1>
          <div class="toolbar">
            <span id="refreshState">等待刷新</span>
            <button id="refreshButton" type="button">刷新</button>
          </div>
        </header>
        <main>
          <div class="stack">
            <section>
              <h2>运行状态</h2>
              <div class="grid" id="metrics"></div>
            </section>
            <section>
              <h2>会话</h2>
              <table>
                <thead>
                  <tr><th>conversation_id</th><th style="width: 96px;">消息</th><th style="width: 160px;">最近时间</th></tr>
                </thead>
                <tbody id="conversations"></tbody>
              </table>
            </section>
            <section>
              <h2>反馈</h2>
              <table>
                <thead>
                  <tr><th style="width: 56px;">ID</th><th style="width: 90px;">状态</th><th>内容</th></tr>
                </thead>
                <tbody id="feedbacks"></tbody>
              </table>
            </section>
          </div>
          <div class="stack">
            <section>
              <h2>最近消息</h2>
              <table>
                <thead>
                  <tr><th style="width: 56px;">ID</th><th style="width: 90px;">角色</th><th>内容</th><th style="width: 180px;">会话</th></tr>
                </thead>
                <tbody id="messages"></tbody>
              </table>
            </section>
            <section>
              <h2>长期记忆</h2>
              <table>
                <thead>
                  <tr><th style="width: 56px;">ID</th><th style="width: 170px;">Subject</th><th>内容</th></tr>
                </thead>
                <tbody id="memories"></tbody>
              </table>
            </section>
            <section>
              <h2>日志</h2>
              <pre id="logs"></pre>
            </section>
          </div>
        </main>
        <script>
          const byId = (id) => document.getElementById(id);
          function esc(value) {
            return String(value ?? "").replace(/[&<>"']/g, (c) => {
              switch (c) {
                case "&": return "&amp;";
                case "<": return "&lt;";
                case ">": return "&gt;";
                case '"': return "&quot;";
                case "'": return "&#39;";
                default: return c;
              }
            });
          }
          function metric(label, value, className = "") {
            return `<div class="metric"><span>${esc(label)}</span><strong class="${className}">${esc(value)}</strong></div>`;
          }
          function row(cells) {
            return `<tr>${cells.map((cell) => `<td>${cell}</td>`).join("")}</tr>`;
          }
          async function loadDashboard() {
            const state = byId("refreshState");
            state.textContent = "刷新中";
            const response = await fetch("/dashboard-data", { cache: "no-store" });
            const data = await response.json();
            byId("metrics").innerHTML = [
              metric("状态", data.status.status, "ok"),
              metric("消息", data.status.messages),
              metric("反馈", data.status.feedbacks),
              metric("记忆", data.status.memory_items),
              metric("摘要", data.status.conversation_summaries),
              metric("LLM", data.config.llm_provider),
              metric("回复", data.config.napcat_passive_reply_enabled ? "被动" : (data.config.napcat_reply_enabled ? "主动" : "关闭"), data.config.napcat_passive_reply_enabled || data.config.napcat_reply_enabled ? "ok" : "warn"),
              metric("窗口", data.config.llm_context_messages)
            ].join("");
            byId("conversations").innerHTML = data.conversations.map((item) => row([
              esc(item.conversation_id),
              esc(item.message_count),
              `<span class="muted">${esc(item.last_message_at)}</span>`
            ])).join("");
            byId("feedbacks").innerHTML = data.feedbacks.map((item) => row([
              esc(item.id),
              esc(item.status),
              esc(item.content)
            ])).join("");
            byId("messages").innerHTML = data.messages.map((item) => row([
              esc(item.id),
              esc(item.role),
              esc(item.content),
              `<span class="muted">${esc(item.conversation_id)}</span>`
            ])).join("");
            byId("memories").innerHTML = data.memories.map((item) => row([
              esc(item.id),
              esc(item.subject),
              esc(item.content)
            ])).join("");
            byId("logs").textContent = data.logs.join("\\n");
            state.textContent = `已刷新 ${new Date().toLocaleTimeString()}`;
          }
          byId("refreshButton").addEventListener("click", loadDashboard);
          loadDashboard().catch((error) => { byId("refreshState").textContent = error.message; });
          setInterval(() => loadDashboard().catch((error) => {
            byId("refreshState").textContent = error.message;
          }), 3000);
        </script>
      </body>
    </html>
    """
