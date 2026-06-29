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
          .status-pill {
            display: inline-flex;
            align-items: center;
            width: fit-content;
            border: 1px solid var(--line);
            border-radius: 999px;
            padding: 3px 8px;
            font-size: 12px;
            font-weight: 650;
          }
          .status-pill.ok {
            border-color: #b7e1c8;
            background: #eefaf3;
          }
          .status-pill.warn {
            border-color: #ffd9a8;
            background: #fff7ed;
          }
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
          .control-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 12px;
            padding: 12px;
          }
          .control-box {
            border: 1px solid var(--line);
            border-radius: 6px;
            padding: 10px;
            display: grid;
            gap: 8px;
            align-content: start;
          }
          .control-box h3 {
            margin: 0;
            font-size: 13px;
            font-weight: 650;
          }
          .diagnostic-list {
            display: grid;
            gap: 8px;
            padding: 12px;
          }
          .diagnostic-item {
            display: grid;
            grid-template-columns: minmax(120px, 180px) 1fr;
            gap: 8px;
            align-items: start;
            border-bottom: 1px solid var(--line);
            padding-bottom: 8px;
          }
          .diagnostic-item:last-child {
            border-bottom: 0;
            padding-bottom: 0;
          }
          input, select, textarea {
            width: 100%;
            border: 1px solid var(--line);
            border-radius: 6px;
            padding: 7px 8px;
            font: inherit;
            background: #fff;
          }
          input[type="checkbox"] {
            width: auto;
          }
          textarea {
            min-height: 72px;
            resize: vertical;
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
            .control-grid { grid-template-columns: 1fr; }
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
              <h2>控制台</h2>
              <div class="control-grid">
                <div class="control-box">
                  <h3>Admin Token</h3>
                  <input id="adminToken" type="password" placeholder="GUGABOBO_ADMIN_TOKEN">
                  <button id="saveTokenButton" type="button">保存到本机浏览器</button>
                </div>
                <div class="control-box">
                  <h3>配置编辑器</h3>
                  <select id="configLlmProvider">
                    <option value="moonshot">moonshot</option>
                    <option value="deepseek">deepseek</option>
                  </select>
                  <input id="configMoonshotModel" placeholder="Moonshot model">
                  <input id="configDeepseekModel" placeholder="DeepSeek model">
                  <input id="configContextMessages" type="number" min="1" placeholder="上下文消息数">
                  <input id="configMemoryItems" type="number" min="0" placeholder="长期记忆条数">
                  <label><input id="configTelegramReplyEnabled" type="checkbox"> Telegram 发送回复</label>
                  <label><input id="configNapcatReplyEnabled" type="checkbox"> NapCat 主动回复</label>
                  <label><input id="configNapcatPassiveReplyEnabled" type="checkbox"> NapCat 被动回复</label>
                  <input id="configQqWakeWords" placeholder="QQ 群聊唤醒词，逗号分隔">
                  <input id="configTelegramWakeWords" placeholder="Telegram 群聊唤醒词，逗号分隔">
                  <input id="configOwnerQqIds" placeholder="owner QQ IDs，逗号分隔">
                  <input id="configOwnerTelegramIds" placeholder="owner Telegram IDs，逗号分隔">
                  <input id="configNapcatDir" placeholder="NapCat 目录">
                  <input id="configNapcatApiUrl" placeholder="NapCat API URL">
                  <input id="configTelegramBotUsername" placeholder="Telegram bot username">
                  <div id="configSecrets" class="muted"></div>
                  <button id="loadConfigButton" type="button">加载配置</button>
                  <button id="saveConfigButton" type="button">保存配置</button>
                </div>
                <div class="control-box">
                  <h3>运行管理</h3>
                  <div id="runtimePanel" class="muted"></div>
                  <button id="startTelegramButton" type="button">启动 Telegram polling</button>
                  <button id="stopTelegramButton" type="button">停止 Telegram polling</button>
                  <button id="startNapcatButton" type="button">启动 NapCat</button>
                  <button id="stopNapcatButton" type="button">停止 NapCat</button>
                  <button id="openNapcatWebuiButton" type="button">打开 NapCat WebUI</button>
                </div>
                <div class="control-box">
                  <h3>发送测试消息</h3>
                  <input id="chatConversationId" placeholder="conversation_id，可空">
                  <textarea id="chatMessage" placeholder="消息内容"></textarea>
                  <button id="chatButton" type="button">发送</button>
                </div>
                <div class="control-box">
                  <h3>会话上下文</h3>
                  <input id="selectedConversationId" placeholder="conversation_id">
                  <button id="loadConversationButton" type="button">查看会话消息</button>
                  <button id="clearConversationButton" type="button">清空会话消息</button>
                  <button id="deleteSummaryButton" type="button">删除会话摘要</button>
                </div>
                <div class="control-box">
                  <h3>添加长期记忆</h3>
                  <input id="memorySubject" value="global" placeholder="subject">
                  <input id="memoryType" value="note" placeholder="memory_type">
                  <input id="memoryImportance" type="number" value="5" min="1" max="10">
                  <textarea id="memoryContent" placeholder="记忆内容"></textarea>
                  <button id="memoryButton" type="button">添加记忆</button>
                </div>
                <div class="control-box">
                  <h3>编辑长期记忆</h3>
                  <input id="editMemoryId" type="number" placeholder="记忆 ID">
                  <input id="editMemorySubject" placeholder="subject">
                  <input id="editMemoryType" placeholder="memory_type">
                  <input id="editMemoryImportance" type="number" min="1" max="10" placeholder="importance">
                  <textarea id="editMemoryContent" placeholder="记忆内容"></textarea>
                  <button id="updateMemoryButton" type="button">更新记忆</button>
                  <button id="deleteMemoryButton" type="button">删除记忆</button>
                </div>
                <div class="control-box">
                  <h3>设置会话摘要</h3>
                  <input id="summaryConversationId" placeholder="conversation_id">
                  <textarea id="summaryContent" placeholder="摘要内容"></textarea>
                  <button id="summaryButton" type="button">保存摘要</button>
                </div>
                <div class="control-box">
                  <h3>修改反馈状态</h3>
                  <input id="feedbackId" type="number" placeholder="反馈 ID">
                  <select id="feedbackStatus">
                    <option value="new">new</option>
                    <option value="triaged">triaged</option>
                    <option value="resolved">resolved</option>
                    <option value="ignored">ignored</option>
                  </select>
                  <button id="feedbackButton" type="button">更新反馈</button>
                </div>
                <div class="control-box">
                  <h3>访问权限</h3>
                  <select id="accessPlatform">
                    <option value="telegram">telegram</option>
                    <option value="qq">qq</option>
                    <option value="web">web</option>
                  </select>
                  <input id="accessUserId" placeholder="user_id">
                  <select id="accessRole">
                    <option value="user">user</option>
                    <option value="trusted">trusted</option>
                    <option value="owner">owner</option>
                    <option value="blocked">blocked</option>
                  </select>
                  <input id="accessDisplayName" placeholder="display_name">
                  <textarea id="accessNotes" placeholder="备注"></textarea>
                  <button id="accessRuleButton" type="button">保存权限</button>
                </div>
                <div class="control-box">
                  <h3>操作结果</h3>
                  <pre id="controlResult"></pre>
                </div>
              </div>
            </section>
            <section>
              <h2>QQ/NapCat 诊断</h2>
              <div class="diagnostic-list" id="qqDiagnostics"></div>
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
            <section>
              <h2>数据库表状态</h2>
              <table>
                <thead>
                  <tr><th>表</th><th style="width: 120px;">行数</th></tr>
                </thead>
                <tbody id="tableCounts"></tbody>
              </table>
            </section>
            <section>
              <h2>访问权限</h2>
              <table>
                <thead>
                  <tr><th style="width: 54px;">ID</th><th style="width: 90px;">平台</th><th style="width: 120px;">用户</th><th style="width: 90px;">角色</th><th>备注</th><th style="width: 92px;">操作</th></tr>
                </thead>
                <tbody id="accessRules"></tbody>
              </table>
            </section>
          </div>
          <div class="stack">
            <section>
              <h2>最近消息</h2>
              <div class="toolbar" style="padding: 10px 12px;">
                <input id="messageConversationFilter" placeholder="按 conversation_id 查看，留空显示最近消息">
                <button id="messageFilterButton" type="button">查看</button>
              </div>
              <table>
                <thead>
                  <tr><th style="width: 56px;">ID</th><th style="width: 90px;">角色</th><th style="width: 120px;">来源</th><th>内容</th><th style="width: 180px;">会话</th></tr>
                </thead>
                <tbody id="messages"></tbody>
              </table>
            </section>
            <section>
              <h2>长期记忆</h2>
              <div class="toolbar" style="padding: 10px 12px;">
                <input id="memoryFilter" placeholder="按 subject 过滤，留空显示全部">
                <button id="memoryFilterButton" type="button">过滤</button>
              </div>
              <table>
                <thead>
                  <tr><th style="width: 56px;">ID</th><th style="width: 160px;">Subject</th><th style="width: 90px;">类型</th><th style="width: 70px;">重要度</th><th>内容</th><th style="width: 92px;">操作</th></tr>
                </thead>
                <tbody id="memories"></tbody>
              </table>
            </section>
            <section>
              <h2>会话摘要</h2>
              <table>
                <thead>
                  <tr><th style="width: 190px;">conversation_id</th><th>摘要</th><th style="width: 160px;">更新时间</th><th style="width: 92px;">操作</th></tr>
                </thead>
                <tbody id="summaries"></tbody>
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
          const tokenStorageKey = "gugabobo.adminToken";
          let currentMemories = [];
          let currentSummaries = [];
          byId("adminToken").value = localStorage.getItem(tokenStorageKey) || "";
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
          function pill(label, active) {
            return `<span class="status-pill ${active ? "ok" : "warn"}">${esc(label)}</span>`;
          }
          function row(cells) {
            return `<tr>${cells.map((cell) => `<td>${cell}</td>`).join("")}</tr>`;
          }
          function diagnosticItem(label, value) {
            return `<div class="diagnostic-item"><strong>${esc(label)}</strong><div>${value}</div></div>`;
          }
          function adminHeaders() {
            return {
              "Content-Type": "application/json",
              "X-Gugabobo-Admin-Token": byId("adminToken").value
            };
          }
          function showControlResult(value) {
            byId("controlResult").textContent = typeof value === "string"
              ? value
              : JSON.stringify(value, null, 2);
          }
          function applyEditableConfig(config) {
            const values = config.values;
            byId("configLlmProvider").value = values.GUGABOBO_LLM_PROVIDER || "moonshot";
            byId("configMoonshotModel").value = values.GUGABOBO_MOONSHOT_MODEL || "";
            byId("configDeepseekModel").value = values.GUGABOBO_DEEPSEEK_MODEL || "";
            byId("configContextMessages").value = values.GUGABOBO_LLM_CONTEXT_MESSAGES || 40;
            byId("configMemoryItems").value = values.GUGABOBO_LLM_MEMORY_ITEMS || 12;
            byId("configTelegramReplyEnabled").checked = Boolean(values.GUGABOBO_TELEGRAM_REPLY_ENABLED);
            byId("configNapcatReplyEnabled").checked = Boolean(values.GUGABOBO_NAPCAT_REPLY_ENABLED);
            byId("configNapcatPassiveReplyEnabled").checked = Boolean(values.GUGABOBO_NAPCAT_PASSIVE_REPLY_ENABLED);
            byId("configQqWakeWords").value = values.GUGABOBO_QQ_GROUP_WAKE_WORDS || "";
            byId("configTelegramWakeWords").value = values.GUGABOBO_TELEGRAM_GROUP_WAKE_WORDS || "";
            byId("configOwnerQqIds").value = values.GUGABOBO_OWNER_QQ_IDS || "";
            byId("configOwnerTelegramIds").value = values.GUGABOBO_OWNER_TELEGRAM_IDS || "";
            byId("configNapcatDir").value = values.GUGABOBO_NAPCAT_DIR || "";
            byId("configNapcatApiUrl").value = values.GUGABOBO_NAPCAT_API_URL || "";
            byId("configTelegramBotUsername").value = values.GUGABOBO_TELEGRAM_BOT_USERNAME || "";
            byId("configSecrets").innerHTML = Object.entries(config.secrets)
              .map(([key, configured]) => `${esc(key.replace("GUGABOBO_", ""))}: ${pill(configured ? "configured" : "missing", configured)}`)
              .join("<br>");
          }
          function collectEditableConfig() {
            return {
              GUGABOBO_LLM_PROVIDER: byId("configLlmProvider").value,
              GUGABOBO_MOONSHOT_MODEL: byId("configMoonshotModel").value,
              GUGABOBO_DEEPSEEK_MODEL: byId("configDeepseekModel").value,
              GUGABOBO_LLM_CONTEXT_MESSAGES: Number(byId("configContextMessages").value || 40),
              GUGABOBO_LLM_MEMORY_ITEMS: Number(byId("configMemoryItems").value || 12),
              GUGABOBO_TELEGRAM_REPLY_ENABLED: byId("configTelegramReplyEnabled").checked,
              GUGABOBO_NAPCAT_REPLY_ENABLED: byId("configNapcatReplyEnabled").checked,
              GUGABOBO_NAPCAT_PASSIVE_REPLY_ENABLED: byId("configNapcatPassiveReplyEnabled").checked,
              GUGABOBO_QQ_GROUP_WAKE_WORDS: byId("configQqWakeWords").value,
              GUGABOBO_TELEGRAM_GROUP_WAKE_WORDS: byId("configTelegramWakeWords").value,
              GUGABOBO_OWNER_QQ_IDS: byId("configOwnerQqIds").value,
              GUGABOBO_OWNER_TELEGRAM_IDS: byId("configOwnerTelegramIds").value,
              GUGABOBO_NAPCAT_DIR: byId("configNapcatDir").value,
              GUGABOBO_NAPCAT_API_URL: byId("configNapcatApiUrl").value,
              GUGABOBO_TELEGRAM_BOT_USERNAME: byId("configTelegramBotUsername").value
            };
          }
          async function loadEditableConfig() {
            const response = await fetch("/dashboard-control/config", {
              headers: { "X-Gugabobo-Admin-Token": byId("adminToken").value },
              cache: "no-store"
            });
            const data = await response.json();
            if (!response.ok) {
              throw new Error(data.detail || response.statusText);
            }
            applyEditableConfig(data);
            showControlResult("config loaded");
          }
          async function controlFetch(url, options) {
            const response = await fetch(url, options);
            const data = await response.json();
            if (!response.ok) {
              throw new Error(data.detail || response.statusText);
            }
            showControlResult(data);
            await loadDashboard();
            return data;
          }
          async function loadDashboard() {
            const state = byId("refreshState");
            state.textContent = "刷新中";
            const response = await fetch("/dashboard-data", { cache: "no-store" });
            const data = await response.json();
            const memorySubject = byId("memoryFilter").value.trim();
            const messageConversation = byId("messageConversationFilter").value.trim();
            const memoriesResponse = await fetch(`/memories?limit=50${memorySubject ? `&subject=${encodeURIComponent(memorySubject)}` : ""}`, { cache: "no-store" });
            const messagesResponse = await fetch(`/messages?limit=50${messageConversation ? `&conversation_id=${encodeURIComponent(messageConversation)}` : ""}`, { cache: "no-store" });
            currentMemories = await memoriesResponse.json();
            const currentMessages = await messagesResponse.json();
            currentSummaries = data.summaries;
            byId("metrics").innerHTML = [
              metric("状态", data.status.status, "ok"),
              metric("API", data.runtime.api.running ? `运行 ${data.runtime.api.pid}` : "停止", data.runtime.api.running ? "ok" : "warn"),
              metric("Telegram", data.runtime.telegram_polling.running ? `运行 ${data.runtime.telegram_polling.pid}` : "停止", data.runtime.telegram_polling.running ? "ok" : "warn"),
              metric("消息", data.status.messages),
              metric("反馈", data.status.feedbacks),
              metric("记忆", data.status.memory_items),
              metric("摘要", data.status.conversation_summaries),
              metric("权限", data.status.access_rules),
              metric("LLM", data.config.llm_provider),
              metric("回复", data.config.napcat_passive_reply_enabled ? "被动" : (data.config.napcat_reply_enabled ? "主动" : "关闭"), data.config.napcat_passive_reply_enabled || data.config.napcat_reply_enabled ? "ok" : "warn"),
              metric("窗口", data.config.llm_context_messages)
            ].join("");
            byId("runtimePanel").innerHTML = [
              `<div>API ${pill(data.runtime.api.running ? `running pid=${data.runtime.api.pid}` : "stopped", data.runtime.api.running)}</div>`,
              `<div>Telegram ${pill(data.runtime.telegram_polling.running ? `running pid=${data.runtime.telegram_polling.pid}` : "stopped", data.runtime.telegram_polling.running)}</div>`,
              `<div>Telegram token ${pill(data.runtime.telegram_polling.configured ? "configured" : "missing", data.runtime.telegram_polling.configured)}</div>`,
              `<div>Telegram send ${pill(data.runtime.telegram_polling.reply_enabled ? "enabled" : "disabled", data.runtime.telegram_polling.reply_enabled)}</div>`,
              `<div>NapCat ${pill(data.runtime.napcat.reply_enabled ? "active reply" : (data.runtime.napcat.passive_reply_enabled ? "passive reply" : "reply off"), data.runtime.napcat.reply_enabled || data.runtime.napcat.passive_reply_enabled)}</div>`,
              `<div>NapCat process ${pill(data.runtime.napcat.running ? `running ${data.runtime.napcat.pids.join(",")}` : "stopped", data.runtime.napcat.running)}</div>`,
              `<div>NapCat WebUI ${pill(data.runtime.napcat.webui.configured ? "configured" : "missing", data.runtime.napcat.webui.configured)}</div>`,
              `<div class="muted">${esc(data.runtime.napcat.api_url)}</div>`
            ].join("");
            const qq = data.qq_diagnostics;
            byId("qqDiagnostics").innerHTML = [
              diagnosticItem("API", `${pill(`running pid=${qq.api.pid}`, true)}<br><span class="muted">${esc(qq.api.onebot_url)}</span>`),
              diagnosticItem("NapCat WebUI", `${pill(qq.napcat_webui.running ? "online" : "offline", qq.napcat_webui.running)}<br><span class="muted">127.0.0.1:6099</span>`),
              diagnosticItem("NapCat 进程", `${pill(qq.napcat_process.running ? `running ${qq.napcat_process.pids.join(",")}` : "stopped", qq.napcat_process.running)}<br><span class="muted">${esc(qq.napcat_process.dir)}</span>`),
              diagnosticItem("NapCat OneBot API", `${pill(qq.napcat_api.running ? "online" : "offline", qq.napcat_api.running)}<br><span class="muted">${esc(qq.napcat_api.url)}</span>`),
              diagnosticItem("HTTP Client URL", `<span class="muted">${esc(qq.api.onebot_url)}</span>`),
              diagnosticItem("回复模式", pill(qq.reply_mode, qq.reply_mode !== "off")),
              diagnosticItem("群聊唤醒词", `<span class="muted">${esc(qq.settings.qq_group_wake_words)}</span>`),
              diagnosticItem("最近 QQ 事件", qq.last_qq_message
                ? `#${esc(qq.last_qq_message.id)} ${esc(qq.last_qq_message.source)} ${esc(qq.last_qq_message.created_at)}<br>${esc(qq.last_qq_message.content)}`
                : `<span class="muted">暂无</span>`),
              diagnosticItem("检查项", qq.checks.map((item) => `${pill(item.ok ? "OK" : "WARN", item.ok)} ${esc(item.name)} <span class="muted">${esc(item.detail)}</span>`).join("<br>")),
              diagnosticItem("操作", `<button id="onebotTestButton" type="button">模拟 OneBot 私聊测试</button>`)
            ].join("");
            byId("conversations").innerHTML = data.conversations.map((item) => (
              `<tr data-conversation-id="${esc(item.conversation_id)}">` +
              `<td>${esc(item.conversation_id)}</td>` +
              `<td>${esc(item.message_count)}</td>` +
              `<td><span class="muted">${esc(item.last_message_at)}</span></td>` +
              "</tr>"
            )).join("");
            byId("feedbacks").innerHTML = data.feedbacks.map((item) => row([
              esc(item.id),
              esc(item.status),
              esc(item.content)
            ])).join("");
            byId("tableCounts").innerHTML = data.table_counts.map((item) => row([
              esc(item.table),
              esc(item.rows)
            ])).join("");
            byId("accessRules").innerHTML = data.access_rules.map((item) => row([
              esc(item.id),
              esc(item.platform),
              esc(item.user_id),
              esc(item.role),
              `${esc(item.display_name)} ${esc(item.notes)}`,
              `<button type="button" data-rule-id="${esc(item.id)}" class="delete-access-rule">删除</button>`
            ])).join("");
            byId("messages").innerHTML = currentMessages.map((item) => row([
              esc(item.id),
              esc(item.role),
              esc(item.source),
              esc(item.content),
              `<span class="muted">${esc(item.conversation_id)}</span>`
            ])).join("");
            byId("memories").innerHTML = currentMemories.map((item) => row([
              esc(item.id),
              esc(item.subject),
              esc(item.memory_type),
              esc(item.importance),
              esc(item.content),
              `<button type="button" data-memory-id="${esc(item.id)}" class="edit-memory">编辑</button>`
            ])).join("");
            byId("summaries").innerHTML = currentSummaries.map((item) => row([
              esc(item.conversation_id),
              esc(item.summary),
              `<span class="muted">${esc(item.updated_at)}</span>`,
              `<button type="button" data-conversation-id="${esc(item.conversation_id)}" class="edit-summary">编辑</button>`
            ])).join("");
            byId("logs").textContent = data.logs.join("\\n");
            state.textContent = `已刷新 ${new Date().toLocaleTimeString()}`;
          }
          byId("saveTokenButton").addEventListener("click", () => {
            localStorage.setItem(tokenStorageKey, byId("adminToken").value);
            showControlResult("admin token saved");
            loadEditableConfig().catch((error) => showControlResult(error.message));
          });
          byId("loadConfigButton").addEventListener("click", () => {
            loadEditableConfig().catch((error) => showControlResult(error.message));
          });
          byId("saveConfigButton").addEventListener("click", () => {
            controlFetch("/dashboard-control/config", {
              method: "POST",
              headers: adminHeaders(),
              body: JSON.stringify({ values: collectEditableConfig() })
            }).then(() => loadEditableConfig()).catch((error) => showControlResult(error.message));
          });
          byId("chatButton").addEventListener("click", () => {
            controlFetch("/dashboard-control/chat", {
              method: "POST",
              headers: adminHeaders(),
              body: JSON.stringify({
                message: byId("chatMessage").value,
                conversation_id: byId("chatConversationId").value || null
              })
            }).catch((error) => showControlResult(error.message));
          });
          byId("startTelegramButton").addEventListener("click", () => {
            controlFetch("/dashboard-control/runtime/telegram/start", {
              method: "POST",
              headers: adminHeaders()
            }).catch((error) => showControlResult(error.message));
          });
          byId("stopTelegramButton").addEventListener("click", () => {
            controlFetch("/dashboard-control/runtime/telegram/stop", {
              method: "POST",
              headers: adminHeaders()
            }).catch((error) => showControlResult(error.message));
          });
          byId("startNapcatButton").addEventListener("click", () => {
            controlFetch("/dashboard-control/runtime/napcat/start", {
              method: "POST",
              headers: adminHeaders()
            }).catch((error) => showControlResult(error.message));
          });
          byId("stopNapcatButton").addEventListener("click", () => {
            controlFetch("/dashboard-control/runtime/napcat/stop", {
              method: "POST",
              headers: adminHeaders()
            }).catch((error) => showControlResult(error.message));
          });
          byId("openNapcatWebuiButton").addEventListener("click", () => {
            const resultText = byId("controlResult").textContent;
            fetch("/runtime/status", { cache: "no-store" })
              .then((response) => response.json())
              .then((data) => {
                window.open(data.napcat.webui.url, "_blank");
                byId("controlResult").textContent = resultText;
              })
              .catch((error) => showControlResult(error.message));
          });
          byId("qqDiagnostics").addEventListener("click", (event) => {
            if (event.target.id !== "onebotTestButton") {
              return;
            }
            controlFetch("/dashboard-control/diagnostics/onebot-test", {
              method: "POST",
              headers: adminHeaders()
            }).catch((error) => showControlResult(error.message));
          });
          function selectConversation(conversationId) {
            byId("selectedConversationId").value = conversationId;
            byId("chatConversationId").value = conversationId;
            byId("memoryFilter").value = conversationId;
            byId("summaryConversationId").value = conversationId;
            byId("messageConversationFilter").value = conversationId;
            showControlResult(`selected conversation ${conversationId}`);
            loadDashboard().catch((error) => showControlResult(error.message));
          }
          byId("loadConversationButton").addEventListener("click", () => {
            const conversationId = byId("selectedConversationId").value;
            byId("messageConversationFilter").value = conversationId;
            byId("memoryFilter").value = conversationId;
            byId("summaryConversationId").value = conversationId;
            loadDashboard().catch((error) => showControlResult(error.message));
          });
          byId("clearConversationButton").addEventListener("click", () => {
            const conversationId = byId("selectedConversationId").value;
            if (!conversationId) {
              showControlResult("missing conversation_id");
              return;
            }
            if (!confirm(`清空会话消息 ${conversationId}?`)) {
              return;
            }
            controlFetch(`/dashboard-control/conversations/${encodeURIComponent(conversationId)}/messages`, {
              method: "DELETE",
              headers: adminHeaders()
            }).catch((error) => showControlResult(error.message));
          });
          byId("deleteSummaryButton").addEventListener("click", () => {
            const conversationId = byId("selectedConversationId").value || byId("summaryConversationId").value;
            if (!conversationId) {
              showControlResult("missing conversation_id");
              return;
            }
            if (!confirm(`删除会话摘要 ${conversationId}?`)) {
              return;
            }
            controlFetch(`/dashboard-control/summaries/${encodeURIComponent(conversationId)}`, {
              method: "DELETE",
              headers: adminHeaders()
            }).catch((error) => showControlResult(error.message));
          });
          byId("memoryButton").addEventListener("click", () => {
            controlFetch("/dashboard-control/memories", {
              method: "POST",
              headers: adminHeaders(),
              body: JSON.stringify({
                subject: byId("memorySubject").value || "global",
                memory_type: byId("memoryType").value || "note",
                importance: Number(byId("memoryImportance").value || 5),
                content: byId("memoryContent").value
              })
            }).catch((error) => showControlResult(error.message));
          });
          byId("updateMemoryButton").addEventListener("click", () => {
            controlFetch(`/dashboard-control/memories/${byId("editMemoryId").value}`, {
              method: "PATCH",
              headers: adminHeaders(),
              body: JSON.stringify({
                subject: byId("editMemorySubject").value,
                memory_type: byId("editMemoryType").value,
                importance: Number(byId("editMemoryImportance").value || 5),
                content: byId("editMemoryContent").value
              })
            }).catch((error) => showControlResult(error.message));
          });
          byId("deleteMemoryButton").addEventListener("click", () => {
            const memoryId = byId("editMemoryId").value;
            if (!memoryId) {
              showControlResult("missing memory id");
              return;
            }
            if (!confirm(`删除记忆 #${memoryId}?`)) {
              return;
            }
            controlFetch(`/dashboard-control/memories/${memoryId}`, {
              method: "DELETE",
              headers: adminHeaders()
            }).catch((error) => showControlResult(error.message));
          });
          byId("summaryButton").addEventListener("click", () => {
            controlFetch("/dashboard-control/summaries", {
              method: "POST",
              headers: adminHeaders(),
              body: JSON.stringify({
                conversation_id: byId("summaryConversationId").value,
                summary: byId("summaryContent").value
              })
            }).catch((error) => showControlResult(error.message));
          });
          byId("feedbackButton").addEventListener("click", () => {
            controlFetch(`/dashboard-control/feedbacks/${byId("feedbackId").value}`, {
              method: "PATCH",
              headers: adminHeaders(),
              body: JSON.stringify({ status: byId("feedbackStatus").value })
            }).catch((error) => showControlResult(error.message));
          });
          byId("accessRuleButton").addEventListener("click", () => {
            controlFetch("/dashboard-control/access-rules", {
              method: "POST",
              headers: adminHeaders(),
              body: JSON.stringify({
                platform: byId("accessPlatform").value,
                user_id: byId("accessUserId").value,
                role: byId("accessRole").value,
                display_name: byId("accessDisplayName").value,
                notes: byId("accessNotes").value
              })
            }).catch((error) => showControlResult(error.message));
          });
          byId("accessRules").addEventListener("click", (event) => {
            if (!event.target.classList.contains("delete-access-rule")) {
              return;
            }
            const ruleId = event.target.dataset.ruleId;
            if (!confirm(`删除权限规则 #${ruleId}?`)) {
              return;
            }
            controlFetch(`/dashboard-control/access-rules/${ruleId}`, {
              method: "DELETE",
              headers: adminHeaders()
            }).catch((error) => showControlResult(error.message));
          });
          byId("memoryFilterButton").addEventListener("click", loadDashboard);
          byId("messageFilterButton").addEventListener("click", loadDashboard);
          byId("conversations").addEventListener("click", (event) => {
            const rowElement = event.target.closest("tr");
            if (!rowElement || !rowElement.dataset.conversationId) {
              return;
            }
            selectConversation(rowElement.dataset.conversationId);
          });
          byId("summaries").addEventListener("click", (event) => {
            if (!event.target.classList.contains("edit-summary")) {
              return;
            }
            const conversationId = event.target.dataset.conversationId;
            const summary = currentSummaries.find((item) => item.conversation_id === conversationId);
            if (!summary) {
              return;
            }
            byId("selectedConversationId").value = conversationId;
            byId("summaryConversationId").value = conversationId;
            byId("summaryContent").value = summary.summary;
            byId("messageConversationFilter").value = conversationId;
            byId("memoryFilter").value = conversationId;
            showControlResult(`loaded summary ${conversationId}`);
          });
          byId("memories").addEventListener("click", (event) => {
            if (!event.target.classList.contains("edit-memory")) {
              return;
            }
            const memory = currentMemories.find((item) => String(item.id) === event.target.dataset.memoryId);
            if (!memory) {
              return;
            }
            byId("editMemoryId").value = memory.id;
            byId("editMemorySubject").value = memory.subject;
            byId("editMemoryType").value = memory.memory_type;
            byId("editMemoryImportance").value = memory.importance;
            byId("editMemoryContent").value = memory.content;
            showControlResult(`loaded memory #${memory.id}`);
          });
          byId("refreshButton").addEventListener("click", loadDashboard);
          loadDashboard().catch((error) => { byId("refreshState").textContent = error.message; });
          setInterval(() => loadDashboard().catch((error) => {
            byId("refreshState").textContent = error.message;
          }), 3000);
        </script>
      </body>
    </html>
    """
