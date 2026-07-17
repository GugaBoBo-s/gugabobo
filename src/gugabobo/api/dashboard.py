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
            columns: 2;
            column-gap: 12px;
            padding: 12px;
          }
          .control-box {
            border: 1px solid var(--line);
            border-radius: 6px;
            padding: 10px;
            display: grid;
            gap: 8px;
            align-content: start;
            break-inside: avoid;
            margin-bottom: 12px;
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
          button.danger {
            border-color: #dc2626;
            color: #b91c1c;
          }
          button.danger:hover {
            background: #fef2f2;
            border-color: #b91c1c;
          }
          @media (max-width: 960px) {
            main { grid-template-columns: 1fr; }
            .grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
            .control-grid { columns: 1; }
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
                    <option value="openai">openai</option>
                  </select>
                  <input id="configMoonshotBaseUrl" placeholder="Moonshot base URL">
                  <input id="configMoonshotModel" placeholder="Moonshot model">
                  <input id="configDeepseekBaseUrl" placeholder="DeepSeek base URL">
                  <input id="configDeepseekModel" placeholder="DeepSeek model">
                  <input id="configOpenaiBaseUrl" placeholder="OpenAI base URL">
                  <input id="configOpenaiModel" placeholder="OpenAI model">
                  <input id="configLlmTimeout" type="number" min="1" placeholder="LLM timeout seconds">
                  <input id="configContextMessages" type="number" min="1" placeholder="上下文消息数">
                  <input id="configMemoryItems" type="number" min="0" placeholder="长期记忆条数">
                  <input id="configHistoryTokenBudget" type="number" min="1" placeholder="历史 token 预算">
                  <input id="configSummaryTriggerTokens" type="number" min="1" placeholder="摘要触发 token">
                  <input id="configSummaryKeepRecentTokens" type="number" min="1" placeholder="摘要保留 token">
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
                  <input id="configTelegramProxy" placeholder="Telegram proxy URL">
                  <input id="configRunnerRuntime" placeholder="Container runtime">
                  <input id="configRunnerImage" placeholder="Runner image">
                  <input id="configClaudeBaseUrl" placeholder="Claude gateway base URL">
                  <input id="configCodeClaudeModel" placeholder="Code primary: Claude model">
                  <input id="configCodeOpenaiModel" placeholder="Code fallback 1: GPT model">
                  <input id="configCodeDeepseekModel" placeholder="Code fallback 2: DeepSeek model">
                  <input id="configCodeDeepseekRunnerModel" placeholder="DeepSeek runner model">
                  <input id="configCodeModelTimeout" type="number" min="1" placeholder="Code model timeout seconds">
                  <label><input id="configGithubReviewEnabled" type="checkbox"> 自动审查组织 PR</label>
                  <input id="configGithubOrganization" placeholder="GitHub organization">
                  <input id="configGithubReviewInterval" type="number" min="30" placeholder="审查扫描周期（秒）">
                  <input id="configGithubReviewMaxFiles" type="number" min="1" max="3000" placeholder="单个 PR 最大文件数">
                  <input id="configGithubReviewMaxPatchChars" type="number" min="1000" max="1000000" placeholder="单个 PR diff 字符预算">
                  <label><input id="configGithubIssueEnabled" type="checkbox"> 自动发现并处理 Issue</label>
                  <label><input id="configGithubIssueAutoFixEnabled" type="checkbox"> 自动修改并提交 PR</label>
                  <label><input id="configAutoDeployEnabled" type="checkbox"> main 合并后自动部署</label>
                  <input id="configGithubIssueInterval" type="number" min="30" placeholder="Issue 扫描周期（秒）">
                  <input id="configGithubIssueMaxPerScan" type="number" min="1" max="500" placeholder="每轮最多评估 Issue 数">
                  <input id="configGithubIssueMinConfidence" type="number" min="0" max="1" step="0.05" placeholder="自动修改最低置信度">
                  <input id="configGithubIssueRepositories" placeholder="允许自动修改的 owner/repo，逗号分隔；* 表示全部">
                  <div id="configSecrets" class="muted"></div>
                  <button id="loadConfigButton" type="button">加载配置</button>
                  <button id="saveConfigButton" type="button">保存配置</button>
                </div>
                <div class="control-box">
                  <h3>运行管理</h3>
                  <div id="runtimePanel" class="muted"></div>
                  <button id="startTelegramButton" type="button">启动 Telegram polling</button>
                  <button id="stopTelegramButton" class="danger" type="button">停止 Telegram polling</button>
                  <button id="startNapcatButton" type="button">启动 NapCat</button>
                  <button id="stopNapcatButton" class="danger" type="button">停止 NapCat</button>
                  <button id="openNapcatWebuiButton" type="button">打开 NapCat WebUI</button>
                </div>
                <div class="control-box">
                  <h3>组织 Code Review</h3>
                  <button id="scanCodeReviewsButton" type="button">立即扫描开放 PR</button>
                </div>
                <div class="control-box">
                  <h3>GitHub Issue 自动化</h3>
                  <button id="scanGithubIssuesButton" type="button">立即发现并评估 Issue</button>
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
                  <button id="clearConversationButton" class="danger" type="button">清空会话消息</button>
                  <button id="deleteSummaryButton" class="danger" type="button">删除会话摘要</button>
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
                  <button id="deleteMemoryButton" class="danger" type="button">删除记忆</button>
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
                  <h3>自改进</h3>
                  <input id="improvementFeedbackId" type="number" min="1" placeholder="反馈 ID">
                  <input id="improvementScope" placeholder="scope">
                  <select id="improvementRisk">
                    <option value="normal">normal</option>
                    <option value="low">low</option>
                    <option value="high">high</option>
                  </select>
                  <button id="createImprovementButton" type="button">创建改进任务</button>
                  <input id="improvementId" type="number" min="1" placeholder="改进任务 ID">
                  <button id="approveImprovementButton" class="danger" type="button">批准</button>
                  <button id="rejectImprovementButton" type="button">拒绝</button>
                  <button id="runImprovementButton" class="danger" type="button">运行隔离修改</button>
                  <button id="shipImprovementButton" class="danger" type="button">检查并提交 PR</button>
                  <button id="openProposalPrButton" class="danger" type="button">仅创建提案 PR</button>
                  <select id="executionType">
                    <option value="improvement">improvement</option>
                    <option value="github_issue">github_issue</option>
                    <option value="code_review">code_review</option>
                  </select>
                  <input id="executionId" type="number" min="1" placeholder="运行记录 ID">
                  <button id="cancelExecutionButton" class="danger" type="button">取消运行</button>
                  <button id="retryExecutionButton" class="danger" type="button">允许重试</button>
                  <input id="pullRequestId" type="number" min="1" placeholder="PR 记录 ID">
                  <button id="syncPullRequestButton" type="button">同步 PR 状态</button>
                  <button id="approvePullRequestButton" class="danger" type="button">批准自动合并</button>
                  <button id="rejectPullRequestButton" class="danger" type="button">拒绝并关闭</button>
                  <button id="syncAllPullRequestsButton" type="button">同步全部 PR</button>
                  <button id="recordDeploymentButton" class="danger" type="button">确认当前部署</button>
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
              <h2>Telegram 诊断</h2>
              <div class="diagnostic-list" id="telegramDiagnostics"></div>
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
            <section>
              <h2>发送草稿</h2>
              <table>
                <thead>
                  <tr><th style="width: 54px;">ID</th><th style="width: 90px;">状态</th><th style="width: 150px;">发起人</th><th style="width: 150px;">收件人</th><th>内容</th><th style="width: 150px;">过期时间</th></tr>
                </thead>
                <tbody id="outboundDrafts"></tbody>
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
              <h2>任务</h2>
              <table>
                <thead>
                  <tr><th style="width: 54px;">ID</th><th style="width: 90px;">状态</th><th>标题</th><th style="width: 130px;">能力</th><th style="width: 150px;">更新时间</th></tr>
                </thead>
                <tbody id="tasks"></tbody>
              </table>
            </section>
            <section>
              <h2>自改进任务</h2>
              <table>
                <thead>
                  <tr><th style="width: 54px;">ID</th><th style="width: 70px;">反馈</th><th style="width: 100px;">批准</th><th style="width: 120px;">运行</th><th>分支</th><th style="width: 90px;">风险</th></tr>
                </thead>
                <tbody id="improvements"></tbody>
              </table>
            </section>
            <section>
              <h2>Pull Requests</h2>
              <table>
                <thead>
                  <tr><th style="width: 54px;">ID</th><th style="width: 70px;">#</th><th style="width: 90px;">状态</th><th style="width: 90px;">检查</th><th>分支</th><th style="width: 100px;">链接</th></tr>
                </thead>
                <tbody id="pullRequests"></tbody>
              </table>
            </section>
            <section>
              <h2>组织 Code Reviews</h2>
              <table>
                <thead>
                  <tr><th style="width: 54px;">ID</th><th>仓库</th><th style="width: 70px;">PR</th><th style="width: 110px;">Head</th><th style="width: 100px;">状态</th><th style="width: 70px;">发现</th><th style="width: 70px;">尝试</th><th style="width: 90px;">链接</th><th>错误</th><th style="width: 150px;">时间</th></tr>
                </thead>
                <tbody id="codeReviews"></tbody>
              </table>
            </section>
            <section>
              <h2>GitHub Issue 自动化</h2>
              <table>
                <thead>
                  <tr><th style="width: 54px;">ID</th><th>仓库 / Issue</th><th style="width: 100px;">状态</th><th style="width: 90px;">价值</th><th style="width: 80px;">置信度</th><th style="width: 150px;">模型</th><th>判断</th><th style="width: 70px;">改进</th><th style="width: 70px;">PR</th><th>错误</th><th style="width: 150px;">时间</th></tr>
                </thead>
                <tbody id="githubIssueRuns"></tbody>
              </table>
            </section>
            <section>
              <h2>运行控制</h2>
              <table>
                <thead>
                  <tr><th>类型 / ID</th><th style="width: 120px;">状态</th><th style="width: 70px;">尝试</th><th>Worker</th><th style="width: 160px;">心跳</th><th style="width: 160px;">租约到期</th><th>容器</th><th>错误</th><th style="width: 150px;">操作</th></tr>
                </thead>
                <tbody id="executionRuns"></tbody>
              </table>
            </section>
            <section>
              <h2>合并授权</h2>
              <table>
                <thead>
                  <tr><th style="width: 70px;">PR ID</th><th style="width: 90px;">决定</th><th style="width: 120px;">状态</th><th style="width: 180px;">授权人</th><th>详情</th><th style="width: 160px;">时间</th></tr>
                </thead>
                <tbody id="mergeAuthorizations"></tbody>
              </table>
            </section>
            <section>
              <h2>改进反思</h2>
              <table>
                <thead>
                  <tr><th style="width: 70px;">PR ID</th><th style="width: 100px;">结果</th><th>总结</th><th>经验</th></tr>
                </thead>
                <tbody id="improvementReflections"></tbody>
              </table>
            </section>
            <section>
              <h2>部署记录</h2>
              <table>
                <thead>
                  <tr><th style="width: 60px;">ID</th><th style="width: 70px;">PR ID</th><th style="width: 90px;">环境</th><th style="width: 100px;">状态</th><th>目标版本</th><th>部署版本</th><th style="width: 160px;">时间</th></tr>
                </thead>
                <tbody id="deploymentRecords"></tbody>
              </table>
            </section>
            <section>
              <h2>主人通知</h2>
              <table>
                <thead>
                  <tr><th style="width: 60px;">ID</th><th style="width: 90px;">平台</th><th style="width: 120px;">接收者</th><th style="width: 120px;">事件</th><th style="width: 90px;">状态</th><th style="width: 70px;">尝试</th><th>错误</th><th style="width: 160px;">时间</th></tr>
                </thead>
                <tbody id="ownerNotifications"></tbody>
              </table>
            </section>
            <section>
              <h2>审计日志</h2>
              <table>
                <thead>
                  <tr><th style="width: 56px;">ID</th><th style="width: 150px;">操作</th><th style="width: 80px;">风险</th><th style="width: 160px;">目标</th><th>详情</th><th style="width: 160px;">时间</th></tr>
                </thead>
                <tbody id="auditLogs"></tbody>
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
          let refreshInFlight = false;
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
          function githubLink(value) {
            const url = String(value || "");
            if (!url.startsWith("https://github.com/")) {
              return esc(url || "-");
            }
            return `<a href="${esc(url)}" target="_blank" rel="noreferrer">打开</a>`;
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
            byId("configMoonshotBaseUrl").value = values.GUGABOBO_MOONSHOT_BASE_URL || "";
            byId("configMoonshotModel").value = values.GUGABOBO_MOONSHOT_MODEL || "";
            byId("configDeepseekBaseUrl").value = values.GUGABOBO_DEEPSEEK_BASE_URL || "";
            byId("configDeepseekModel").value = values.GUGABOBO_DEEPSEEK_MODEL || "";
            byId("configOpenaiBaseUrl").value = values.GUGABOBO_OPENAI_BASE_URL || "";
            byId("configOpenaiModel").value = values.GUGABOBO_OPENAI_MODEL || "";
            byId("configLlmTimeout").value = values.GUGABOBO_LLM_TIMEOUT_SECONDS || 60;
            byId("configContextMessages").value = values.GUGABOBO_LLM_CONTEXT_MESSAGES || 400;
            byId("configMemoryItems").value = values.GUGABOBO_LLM_MEMORY_ITEMS || 12;
            byId("configHistoryTokenBudget").value = values.GUGABOBO_LLM_HISTORY_TOKEN_BUDGET || 24000;
            byId("configSummaryTriggerTokens").value = values.GUGABOBO_LLM_SUMMARY_TRIGGER_TOKENS || 24000;
            byId("configSummaryKeepRecentTokens").value = values.GUGABOBO_LLM_SUMMARY_KEEP_RECENT_TOKENS || 8000;
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
            byId("configTelegramProxy").value = values.GUGABOBO_TELEGRAM_PROXY || "";
            byId("configRunnerRuntime").value = values.GUGABOBO_RUNNER_CONTAINER_RUNTIME || "docker";
            byId("configRunnerImage").value = values.GUGABOBO_RUNNER_CONTAINER_IMAGE || "gugabobo-runner:local";
            byId("configClaudeBaseUrl").value = values.GUGABOBO_CLAUDE_BASE_URL || "";
            byId("configCodeClaudeModel").value = values.GUGABOBO_CODE_CLAUDE_MODEL || "";
            byId("configCodeOpenaiModel").value = values.GUGABOBO_CODE_OPENAI_MODEL || "";
            byId("configCodeDeepseekModel").value = values.GUGABOBO_CODE_DEEPSEEK_MODEL || "";
            byId("configCodeDeepseekRunnerModel").value = values.GUGABOBO_CODE_DEEPSEEK_RUNNER_MODEL || "";
            byId("configCodeModelTimeout").value = values.GUGABOBO_CODE_MODEL_TIMEOUT_SECONDS || 120;
            byId("configGithubReviewEnabled").checked = Boolean(values.GUGABOBO_GITHUB_REVIEW_ENABLED);
            byId("configGithubOrganization").value = values.GUGABOBO_GITHUB_ORGANIZATION || "GugaBoBo-s";
            byId("configGithubReviewInterval").value = values.GUGABOBO_GITHUB_REVIEW_INTERVAL_SECONDS || 300;
            byId("configGithubReviewMaxFiles").value = values.GUGABOBO_GITHUB_REVIEW_MAX_FILES || 100;
            byId("configGithubReviewMaxPatchChars").value = values.GUGABOBO_GITHUB_REVIEW_MAX_PATCH_CHARS || 120000;
            byId("configGithubIssueEnabled").checked = Boolean(values.GUGABOBO_GITHUB_ISSUE_ENABLED);
            byId("configGithubIssueAutoFixEnabled").checked = Boolean(values.GUGABOBO_GITHUB_ISSUE_AUTO_FIX_ENABLED);
            byId("configGithubIssueInterval").value = values.GUGABOBO_GITHUB_ISSUE_INTERVAL_SECONDS || 600;
            byId("configGithubIssueMaxPerScan").value = values.GUGABOBO_GITHUB_ISSUE_MAX_PER_SCAN || 20;
            byId("configGithubIssueMinConfidence").value = values.GUGABOBO_GITHUB_ISSUE_MIN_CONFIDENCE ?? 0.75;
            byId("configGithubIssueRepositories").value = values.GUGABOBO_GITHUB_ISSUE_AUTO_FIX_REPOSITORIES || "";
            byId("configAutoDeployEnabled").checked = Boolean(values.GUGABOBO_AUTO_DEPLOY_ENABLED);
            byId("configSecrets").innerHTML = Object.entries(config.secrets)
              .map(([key, configured]) => `${esc(key.replace("GUGABOBO_", ""))}: ${pill(configured ? "configured" : "missing", configured)}`)
              .join("<br>");
          }
          function collectEditableConfig() {
            return {
              GUGABOBO_LLM_PROVIDER: byId("configLlmProvider").value,
              GUGABOBO_MOONSHOT_BASE_URL: byId("configMoonshotBaseUrl").value,
              GUGABOBO_MOONSHOT_MODEL: byId("configMoonshotModel").value,
              GUGABOBO_DEEPSEEK_BASE_URL: byId("configDeepseekBaseUrl").value,
              GUGABOBO_DEEPSEEK_MODEL: byId("configDeepseekModel").value,
              GUGABOBO_OPENAI_BASE_URL: byId("configOpenaiBaseUrl").value,
              GUGABOBO_OPENAI_MODEL: byId("configOpenaiModel").value,
              GUGABOBO_LLM_TIMEOUT_SECONDS: Number(byId("configLlmTimeout").value || 60),
              GUGABOBO_LLM_CONTEXT_MESSAGES: Number(byId("configContextMessages").value || 400),
              GUGABOBO_LLM_MEMORY_ITEMS: Number(byId("configMemoryItems").value || 12),
              GUGABOBO_LLM_HISTORY_TOKEN_BUDGET: Number(byId("configHistoryTokenBudget").value || 24000),
              GUGABOBO_LLM_SUMMARY_TRIGGER_TOKENS: Number(byId("configSummaryTriggerTokens").value || 24000),
              GUGABOBO_LLM_SUMMARY_KEEP_RECENT_TOKENS: Number(byId("configSummaryKeepRecentTokens").value || 8000),
              GUGABOBO_TELEGRAM_REPLY_ENABLED: byId("configTelegramReplyEnabled").checked,
              GUGABOBO_NAPCAT_REPLY_ENABLED: byId("configNapcatReplyEnabled").checked,
              GUGABOBO_NAPCAT_PASSIVE_REPLY_ENABLED: byId("configNapcatPassiveReplyEnabled").checked,
              GUGABOBO_QQ_GROUP_WAKE_WORDS: byId("configQqWakeWords").value,
              GUGABOBO_TELEGRAM_GROUP_WAKE_WORDS: byId("configTelegramWakeWords").value,
              GUGABOBO_OWNER_QQ_IDS: byId("configOwnerQqIds").value,
              GUGABOBO_OWNER_TELEGRAM_IDS: byId("configOwnerTelegramIds").value,
              GUGABOBO_NAPCAT_DIR: byId("configNapcatDir").value,
              GUGABOBO_NAPCAT_API_URL: byId("configNapcatApiUrl").value,
              GUGABOBO_TELEGRAM_BOT_USERNAME: byId("configTelegramBotUsername").value,
              GUGABOBO_TELEGRAM_PROXY: byId("configTelegramProxy").value,
              GUGABOBO_RUNNER_CONTAINER_RUNTIME: byId("configRunnerRuntime").value,
              GUGABOBO_RUNNER_CONTAINER_IMAGE: byId("configRunnerImage").value,
              GUGABOBO_CLAUDE_BASE_URL: byId("configClaudeBaseUrl").value,
              GUGABOBO_CODE_CLAUDE_MODEL: byId("configCodeClaudeModel").value,
              GUGABOBO_CODE_OPENAI_MODEL: byId("configCodeOpenaiModel").value,
              GUGABOBO_CODE_DEEPSEEK_MODEL: byId("configCodeDeepseekModel").value,
              GUGABOBO_CODE_DEEPSEEK_RUNNER_MODEL: byId("configCodeDeepseekRunnerModel").value,
              GUGABOBO_CODE_MODEL_TIMEOUT_SECONDS: Number(byId("configCodeModelTimeout").value || 120),
              GUGABOBO_GITHUB_REVIEW_ENABLED: byId("configGithubReviewEnabled").checked,
              GUGABOBO_GITHUB_ORGANIZATION: byId("configGithubOrganization").value,
              GUGABOBO_GITHUB_REVIEW_INTERVAL_SECONDS: Number(byId("configGithubReviewInterval").value || 300),
              GUGABOBO_GITHUB_REVIEW_MAX_FILES: Number(byId("configGithubReviewMaxFiles").value || 100),
              GUGABOBO_GITHUB_REVIEW_MAX_PATCH_CHARS: Number(byId("configGithubReviewMaxPatchChars").value || 120000),
              GUGABOBO_GITHUB_ISSUE_ENABLED: byId("configGithubIssueEnabled").checked,
              GUGABOBO_GITHUB_ISSUE_AUTO_FIX_ENABLED: byId("configGithubIssueAutoFixEnabled").checked,
              GUGABOBO_GITHUB_ISSUE_INTERVAL_SECONDS: Number(byId("configGithubIssueInterval").value || 600),
              GUGABOBO_GITHUB_ISSUE_MAX_PER_SCAN: Number(byId("configGithubIssueMaxPerScan").value || 20),
              GUGABOBO_GITHUB_ISSUE_MIN_CONFIDENCE: Number(byId("configGithubIssueMinConfidence").value || 0.75),
              GUGABOBO_GITHUB_ISSUE_AUTO_FIX_REPOSITORIES: byId("configGithubIssueRepositories").value,
              GUGABOBO_AUTO_DEPLOY_ENABLED: byId("configAutoDeployEnabled").checked
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
          function requireConfirmText(expectedText, label) {
            const value = prompt(`${label}\\n请输入 ${expectedText} 确认`);
            if (value !== expectedText) {
              showControlResult(`cancelled: expected ${expectedText}`);
              return null;
            }
            return { confirm_text: expectedText };
          }
          async function loadDashboard() {
            if (refreshInFlight) {
              return;
            }
            refreshInFlight = true;
            const state = byId("refreshState");
            state.textContent = "刷新中";
            try {
              const token = byId("adminToken").value.trim();
              if (!token) {
                throw new Error("请输入管理员令牌后加载控制面板");
              }
              const query = new URLSearchParams();
              const memorySubject = byId("memoryFilter").value.trim();
              const messageConversation = byId("messageConversationFilter").value.trim();
              if (memorySubject) {
                query.set("memory_subject", memorySubject);
              }
              if (messageConversation) {
                query.set("conversation_id", messageConversation);
              }
              const response = await fetch(`/dashboard-data?${query.toString()}`, {
                cache: "no-store",
                headers: adminHeaders()
              });
              const data = await response.json();
              if (!response.ok) {
                throw new Error(data.detail || response.statusText);
              }
              currentMemories = data.memories;
              const currentMessages = data.messages;
              currentSummaries = data.summaries;
            const autoDeploy = data.runtime.auto_deploy || { status: "unknown" };
            byId("metrics").innerHTML = [
              metric("状态", data.status.status, "ok"),
              metric("API", data.runtime.api.running ? `运行 ${data.runtime.api.pid}` : "停止", data.runtime.api.running ? "ok" : "warn"),
              metric("Telegram", data.runtime.telegram_polling.running ? `运行 ${data.runtime.telegram_polling.pid}` : "停止", data.runtime.telegram_polling.running ? "ok" : "warn"),
              metric("生命周期", data.runtime.lifecycle_agent.running ? `运行 ${data.runtime.lifecycle_agent.pid}` : "停止", data.runtime.lifecycle_agent.running ? "ok" : "warn"),
              metric("自动部署", autoDeploy.status, ["deployed", "current"].includes(autoDeploy.status) ? "ok" : "warn"),
              metric("消息", data.status.messages),
              metric("反馈", data.status.feedbacks),
              metric("记忆", data.status.memory_items),
              metric("摘要", data.status.conversation_summaries),
              metric("权限", data.status.access_rules),
              metric("审计", data.status.audit_logs),
              metric("LLM", data.config.llm_provider),
              metric("Code Review", data.config.github_review_enabled ? data.config.github_organization : "关闭", data.config.github_review_enabled ? "ok" : "warn"),
              metric("Issue 自动化", data.config.github_issue_enabled ? "开启" : "关闭", data.config.github_issue_enabled ? "ok" : "warn"),
              metric("回复", data.config.napcat_passive_reply_enabled ? "被动" : (data.config.napcat_reply_enabled ? "主动" : "关闭"), data.config.napcat_passive_reply_enabled || data.config.napcat_reply_enabled ? "ok" : "warn"),
              metric("历史预算", data.config.llm_history_token_budget),
              metric("摘要阈值", data.config.llm_summary_trigger_tokens)
            ].join("");
            byId("runtimePanel").innerHTML = [
              `<div>API ${pill(data.runtime.api.running ? `running pid=${data.runtime.api.pid}` : "stopped", data.runtime.api.running)}</div>`,
              `<div>Telegram ${pill(data.runtime.telegram_polling.running ? `running pid=${data.runtime.telegram_polling.pid} (${data.runtime.telegram_polling.managed_by})` : "stopped", data.runtime.telegram_polling.running)}</div>`,
              `<div>Telegram token ${pill(data.runtime.telegram_polling.configured ? "configured" : "missing", data.runtime.telegram_polling.configured)}</div>`,
              `<div>Telegram send ${pill(data.runtime.telegram_polling.reply_enabled ? "enabled" : "disabled", data.runtime.telegram_polling.reply_enabled)}</div>`,
              `<div>Lifecycle agent ${pill(data.runtime.lifecycle_agent.running ? `running pid=${data.runtime.lifecycle_agent.pid}` : "stopped", data.runtime.lifecycle_agent.running)}</div>`,
              `<div>Auto deploy ${pill(autoDeploy.status, ["deployed", "current"].includes(autoDeploy.status))}</div>`,
              `<div class="muted">${esc(autoDeploy.detail || "")}</div>`,
              `<div>NapCat ${pill(data.runtime.napcat.reply_enabled ? "active reply" : (data.runtime.napcat.passive_reply_enabled ? "passive reply" : "reply off"), data.runtime.napcat.reply_enabled || data.runtime.napcat.passive_reply_enabled)}</div>`,
              `<div>NapCat process ${pill(data.runtime.napcat.running ? `running ${data.runtime.napcat.pids.join(",")}` : "stopped", data.runtime.napcat.running)}</div>`,
              `<div>NapCat WebUI ${pill(data.runtime.napcat.webui.configured ? "configured" : "missing", data.runtime.napcat.webui.configured)}</div>`,
              `<div>Runner ${pill(data.runtime.self_improvement.runtime_configured ? data.runtime.self_improvement.runtime : "missing", data.runtime.self_improvement.runtime_configured)}</div>`,
              `<div>Runner image ${pill(data.runtime.self_improvement.image_available ? data.runtime.self_improvement.image : "missing", data.runtime.self_improvement.image_available)}</div>`,
              `<div>Claude gateway ${pill(data.runtime.self_improvement.claude_gateway_configured ? "configured" : "missing", data.runtime.self_improvement.claude_gateway_configured)}</div>`,
              `<div class="muted">${esc(data.runtime.self_improvement.claude_base_url || "default Anthropic endpoint")}</div>`,
              `<div>Code models ${data.runtime.self_improvement.code_models.order.map((name) => {
                const item = data.runtime.self_improvement.code_models[name];
                return pill(`${name}:${item.model}`, item.configured);
              }).join(" ")}</div>`,
              `<div>GitHub ${pill(data.runtime.self_improvement.github_configured ? "configured" : "missing", data.runtime.self_improvement.github_configured)}</div>`,
              `<div>Code review ${pill(data.config.github_review_enabled ? `enabled ${data.config.github_organization}` : "disabled", data.config.github_review_enabled)}</div>`,
              `<div>Issue automation ${pill(data.config.github_issue_enabled ? "enabled" : "disabled", data.config.github_issue_enabled)}</div>`,
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
              diagnosticItem("操作", `<button id="onebotTestButton" type="button">检查 OneBot 事件解析</button>`)
            ].join("");
            const tg = data.telegram_diagnostics;
            byId("telegramDiagnostics").innerHTML = [
              diagnosticItem("Token", pill(tg.configured ? "configured" : "missing", tg.configured)),
              diagnosticItem("Bot", `<span class="muted">${esc(tg.bot_username || "unknown")}</span>`),
              diagnosticItem("Polling", `${pill(tg.polling.running ? `running pid=${tg.polling.pid} (${tg.polling.managed_by})` : "stopped", tg.polling.running)}<br><span class="muted">本地 getUpdates</span>`),
              diagnosticItem("发送回复", pill(tg.reply_enabled ? "enabled" : "disabled", tg.reply_enabled)),
              diagnosticItem("群聊唤醒词", `<span class="muted">${esc(tg.group_wake_words)}</span>`),
              diagnosticItem("最近 Telegram 事件", tg.last_telegram_message
                ? `#${esc(tg.last_telegram_message.id)} ${esc(tg.last_telegram_message.source)} ${esc(tg.last_telegram_message.created_at)}<br>${esc(tg.last_telegram_message.content)}`
                : `<span class="muted">暂无</span>`),
              diagnosticItem("检查项", tg.checks.map((item) => `${pill(item.ok ? "OK" : "WARN", item.ok)} ${esc(item.name)} <span class="muted">${esc(item.detail)}</span>`).join("<br>")),
              diagnosticItem("操作", `<button id="telegramTestButton" type="button">检查 Telegram 事件解析</button> <button id="telegramGetMeButton" type="button">检查 getMe</button>`)
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
              `<button type="button" data-rule-id="${esc(item.id)}" class="delete-access-rule danger">删除</button>`
            ])).join("");
            byId("outboundDrafts").innerHTML = data.outbound_drafts.map((item) => row([
              esc(item.id),
              esc(item.status),
              `${esc(item.actor_source)}:${esc(item.actor_user_id)}`,
              `${esc(item.recipient_label)} (${esc(item.recipient_user_id)})`,
              esc(item.content),
              `<span class="muted">${esc(item.expires_at)}</span>`
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
            byId("tasks").innerHTML = data.tasks.map((item) => row([
              esc(item.id),
              esc(item.status),
              esc(item.title),
              esc(item.assigned_skill),
              `<span class="muted">${esc(item.updated_at)}</span>`
            ])).join("");
            byId("improvements").innerHTML = data.improvements.map((item) => row([
              esc(item.id),
              esc(item.feedback_id),
              esc(item.approval_status),
              esc(item.runner_status),
              esc(item.branch_name),
              esc(item.risk_level)
            ])).join("");
            byId("pullRequests").innerHTML = data.pull_requests.map((item) => row([
              esc(item.id),
              esc(item.number),
              esc(item.status),
              esc(item.checks_status),
              esc(item.branch_name),
              githubLink(item.url)
            ])).join("");
            byId("codeReviews").innerHTML = data.code_reviews.map((item) => row([
              esc(item.id),
              `${esc(item.github_owner)}/${esc(item.github_repo)}`,
              esc(item.pr_number),
              `<span class="muted">${esc(String(item.head_sha).slice(0, 12))}</span>`,
              esc(item.status),
              esc(item.findings_count),
              esc(item.attempt_count),
              githubLink(item.review_url || item.pr_url),
              esc(item.last_error),
              `<span class="muted">${esc(item.completed_at || item.updated_at)}</span>`
            ])).join("");
            byId("githubIssueRuns").innerHTML = data.github_issue_runs.map((item) => row([
              esc(item.id),
              `${esc(item.github_owner)}/${esc(item.github_repo)} #${esc(item.issue_number)}<br>${githubLink(item.issue_url)}`,
              esc(item.status),
              esc(Boolean(item.worthwhile)),
              esc(Number(item.confidence || 0).toFixed(2)),
              `${esc(item.provider)}/${esc(item.model)}`,
              `${esc(item.rationale)}<br><span class="muted">${esc(item.implementation_summary)}</span>`,
              esc(item.improvement_task_id || "-"),
              item.pr_url ? githubLink(item.pr_url) : esc(item.pr_number || "-"),
              esc(item.last_error),
              `<span class="muted">${esc(item.completed_at || item.updated_at)}</span>`
            ])).join("");
            byId("executionRuns").innerHTML = data.execution_runs.map((item) => row([
              `${esc(item.run_type)} #${esc(item.run_id)}`,
              esc(item.status),
              esc(item.attempt_count),
              `<span class="muted">${esc(item.worker_id || "-")}</span>`,
              `<span class="muted">${esc(item.heartbeat_at)}</span>`,
              `<span class="muted">${esc(item.lease_expires_at)}</span>`,
              `<span class="muted">${esc(item.container_name || "-")}</span>`,
              esc(item.last_error),
              `<button type="button" class="select-execution" data-run-type="${esc(item.run_type)}" data-run-id="${esc(item.run_id)}">选择</button>`
            ])).join("");
            byId("mergeAuthorizations").innerHTML = data.merge_authorizations.map((item) => row([
              esc(item.pull_request_id),
              esc(item.decision),
              esc(item.status),
              `${esc(item.actor_platform)}:${esc(item.actor_user_id)}`,
              esc(item.detail),
              `<span class="muted">${esc(item.updated_at)}</span>`
            ])).join("");
            byId("improvementReflections").innerHTML = data.improvement_reflections.map((item) => row([
              esc(item.pull_request_id),
              esc(item.outcome),
              esc(item.summary),
              esc(item.lessons)
            ])).join("");
            byId("deploymentRecords").innerHTML = data.deployment_records.map((item) => row([
              esc(item.id),
              esc(item.pull_request_id),
              esc(item.environment),
              esc(item.status),
              `<span class="muted">${esc(item.target_revision)}</span>`,
              `<span class="muted">${esc(item.deployed_revision)}</span>`,
              `<span class="muted">${esc(item.deployed_at || item.updated_at)}</span>`
            ])).join("");
            byId("ownerNotifications").innerHTML = data.owner_notifications.map((item) => row([
              esc(item.id),
              esc(item.platform),
              esc(item.recipient_id),
              esc(item.event_type),
              esc(item.status),
              esc(item.attempts),
              esc(item.last_error),
              `<span class="muted">${esc(item.sent_at || item.updated_at)}</span>`
            ])).join("");
            byId("auditLogs").innerHTML = data.audit_logs.map((item) => row([
              esc(item.id),
              esc(item.action),
              esc(item.risk_level),
              esc(item.target),
              `${esc(item.status)} ${esc(item.detail)}`,
              `<span class="muted">${esc(item.created_at)}</span>`
            ])).join("");
              byId("logs").textContent = data.logs.join("\\n");
              state.textContent = `已刷新 ${new Date().toLocaleTimeString()}`;
            } finally {
              refreshInFlight = false;
            }
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
          byId("scanCodeReviewsButton").addEventListener("click", () => {
            controlFetch("/code-reviews/scan", {
              method: "POST",
              headers: adminHeaders()
            }).catch((error) => showControlResult(error.message));
          });
          byId("scanGithubIssuesButton").addEventListener("click", () => {
            controlFetch("/github-issues/scan", {
              method: "POST",
              headers: adminHeaders()
            }).catch((error) => showControlResult(error.message));
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
            const confirmation = requireConfirmText("STOP", "停止 Telegram polling");
            if (!confirmation) {
              return;
            }
            controlFetch("/dashboard-control/runtime/telegram/stop", {
              method: "POST",
              headers: adminHeaders(),
              body: JSON.stringify(confirmation)
            }).catch((error) => showControlResult(error.message));
          });
          byId("startNapcatButton").addEventListener("click", () => {
            controlFetch("/dashboard-control/runtime/napcat/start", {
              method: "POST",
              headers: adminHeaders()
            }).catch((error) => showControlResult(error.message));
          });
          byId("stopNapcatButton").addEventListener("click", () => {
            const confirmation = requireConfirmText("STOP", "停止 NapCat");
            if (!confirmation) {
              return;
            }
            controlFetch("/dashboard-control/runtime/napcat/stop", {
              method: "POST",
              headers: adminHeaders(),
              body: JSON.stringify(confirmation)
            }).catch((error) => showControlResult(error.message));
          });
          byId("openNapcatWebuiButton").addEventListener("click", () => {
            const resultText = byId("controlResult").textContent;
            fetch("/runtime/status", { cache: "no-store", headers: adminHeaders() })
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
          byId("telegramDiagnostics").addEventListener("click", (event) => {
            if (event.target.id === "telegramTestButton") {
              controlFetch("/dashboard-control/diagnostics/telegram-test", {
                method: "POST",
                headers: adminHeaders()
              }).catch((error) => showControlResult(error.message));
              return;
            }
            if (event.target.id === "telegramGetMeButton") {
              controlFetch("/dashboard-control/diagnostics/telegram-getme", {
                method: "POST",
                headers: adminHeaders()
              }).catch((error) => showControlResult(error.message));
            }
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
            const confirmation = requireConfirmText("CLEAR", `清空会话消息 ${conversationId}`);
            if (!confirmation) {
              return;
            }
            controlFetch(`/dashboard-control/conversations/${encodeURIComponent(conversationId)}/messages`, {
              method: "DELETE",
              headers: adminHeaders(),
              body: JSON.stringify(confirmation)
            }).catch((error) => showControlResult(error.message));
          });
          byId("deleteSummaryButton").addEventListener("click", () => {
            const conversationId = byId("selectedConversationId").value || byId("summaryConversationId").value;
            if (!conversationId) {
              showControlResult("missing conversation_id");
              return;
            }
            const confirmation = requireConfirmText("DELETE", `删除会话摘要 ${conversationId}`);
            if (!confirmation) {
              return;
            }
            controlFetch(`/dashboard-control/summaries/${encodeURIComponent(conversationId)}`, {
              method: "DELETE",
              headers: adminHeaders(),
              body: JSON.stringify(confirmation)
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
            const confirmation = requireConfirmText("DELETE", `删除记忆 #${memoryId}`);
            if (!confirmation) {
              return;
            }
            controlFetch(`/dashboard-control/memories/${memoryId}`, {
              method: "DELETE",
              headers: adminHeaders(),
              body: JSON.stringify(confirmation)
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
          byId("createImprovementButton").addEventListener("click", () => {
            controlFetch("/improvements", {
              method: "POST",
              headers: adminHeaders(),
              body: JSON.stringify({
                feedback_id: Number(byId("improvementFeedbackId").value),
                scope: byId("improvementScope").value,
                risk_level: byId("improvementRisk").value
              })
            }).then((data) => {
              byId("improvementId").value = data.improvement_id;
            }).catch((error) => showControlResult(error.message));
          });
          byId("approveImprovementButton").addEventListener("click", () => {
            const improvementId = byId("improvementId").value;
            if (!improvementId) {
              showControlResult("missing improvement id");
              return;
            }
            const confirmation = requireConfirmText("APPROVE", `批准改进任务 #${improvementId}`);
            if (!confirmation) {
              return;
            }
            controlFetch(`/improvements/${improvementId}/approve`, {
              method: "POST",
              headers: adminHeaders(),
              body: JSON.stringify(confirmation)
            }).catch((error) => showControlResult(error.message));
          });
          byId("rejectImprovementButton").addEventListener("click", () => {
            const improvementId = byId("improvementId").value;
            if (!improvementId) {
              showControlResult("missing improvement id");
              return;
            }
            controlFetch(`/improvements/${improvementId}/reject`, {
              method: "POST",
              headers: adminHeaders()
            }).catch((error) => showControlResult(error.message));
          });
          byId("runImprovementButton").addEventListener("click", () => {
            const improvementId = byId("improvementId").value;
            if (!improvementId) {
              showControlResult("missing improvement id");
              return;
            }
            const confirmation = requireConfirmText("RUN", `运行改进任务 #${improvementId}`);
            if (!confirmation) {
              return;
            }
            controlFetch(`/improvements/${improvementId}/run`, {
              method: "POST",
              headers: adminHeaders(),
              body: JSON.stringify(confirmation)
            }).catch((error) => showControlResult(error.message));
          });
          byId("shipImprovementButton").addEventListener("click", () => {
            const improvementId = byId("improvementId").value;
            if (!improvementId) {
              showControlResult("missing improvement id");
              return;
            }
            const confirmation = requireConfirmText("SHIP", `检查并提交改进任务 #${improvementId}`);
            if (!confirmation) {
              return;
            }
            controlFetch(`/improvements/${improvementId}/ship`, {
              method: "POST",
              headers: adminHeaders(),
              body: JSON.stringify(confirmation)
            }).catch((error) => showControlResult(error.message));
          });
          byId("openProposalPrButton").addEventListener("click", () => {
            const improvementId = byId("improvementId").value;
            if (!improvementId) {
              showControlResult("missing improvement id");
              return;
            }
            const confirmation = requireConfirmText("OPEN", `创建提案 PR #${improvementId}`);
            if (!confirmation) {
              return;
            }
            controlFetch(`/improvements/${improvementId}/pull-request`, {
              method: "POST",
              headers: adminHeaders(),
              body: JSON.stringify(confirmation)
            }).then((data) => {
              byId("pullRequestId").value = data.pull_request_id;
            }).catch((error) => showControlResult(error.message));
          });
          byId("cancelExecutionButton").addEventListener("click", () => {
            const runType = byId("executionType").value;
            const runId = byId("executionId").value;
            if (!runId) {
              showControlResult("missing execution id");
              return;
            }
            const confirmation = requireConfirmText("CANCEL", `取消 ${runType} #${runId}`);
            if (!confirmation) {
              return;
            }
            controlFetch(`/executions/${runType}/${runId}/cancel`, {
              method: "POST",
              headers: adminHeaders(),
              body: JSON.stringify(confirmation)
            }).catch((error) => showControlResult(error.message));
          });
          byId("retryExecutionButton").addEventListener("click", () => {
            const runType = byId("executionType").value;
            const runId = byId("executionId").value;
            if (!runId) {
              showControlResult("missing execution id");
              return;
            }
            const confirmation = requireConfirmText("RETRY", `重试 ${runType} #${runId}`);
            if (!confirmation) {
              return;
            }
            controlFetch(`/executions/${runType}/${runId}/retry`, {
              method: "POST",
              headers: adminHeaders(),
              body: JSON.stringify(confirmation)
            }).catch((error) => showControlResult(error.message));
          });
          byId("syncPullRequestButton").addEventListener("click", () => {
            const pullRequestId = byId("pullRequestId").value;
            if (!pullRequestId) {
              showControlResult("missing pull request id");
              return;
            }
            controlFetch(`/prs/${pullRequestId}/sync`, {
              method: "POST",
              headers: adminHeaders()
            }).catch((error) => showControlResult(error.message));
          });
          byId("approvePullRequestButton").addEventListener("click", () => {
            const pullRequestId = byId("pullRequestId").value;
            if (!pullRequestId) {
              showControlResult("missing pull request id");
              return;
            }
            const confirmation = requireConfirmText("MERGE", `批准 PR 记录 #${pullRequestId} 自动合并`);
            if (!confirmation) {
              return;
            }
            controlFetch(`/prs/${pullRequestId}/approve-merge`, {
              method: "POST",
              headers: adminHeaders(),
              body: JSON.stringify(confirmation)
            }).catch((error) => showControlResult(error.message));
          });
          byId("rejectPullRequestButton").addEventListener("click", () => {
            const pullRequestId = byId("pullRequestId").value;
            if (!pullRequestId) {
              showControlResult("missing pull request id");
              return;
            }
            const confirmation = requireConfirmText("REJECT", `拒绝 PR 记录 #${pullRequestId}`);
            if (!confirmation) {
              return;
            }
            controlFetch(`/prs/${pullRequestId}/reject-merge`, {
              method: "POST",
              headers: adminHeaders(),
              body: JSON.stringify(confirmation)
            }).catch((error) => showControlResult(error.message));
          });
          byId("syncAllPullRequestsButton").addEventListener("click", () => {
            controlFetch("/prs/sync-all", {
              method: "POST",
              headers: adminHeaders()
            }).catch((error) => showControlResult(error.message));
          });
          byId("recordDeploymentButton").addEventListener("click", () => {
            const confirmation = requireConfirmText("DEPLOYED", "确认当前代码版本已部署");
            if (!confirmation) {
              return;
            }
            controlFetch("/deployments/record-current", {
              method: "POST",
              headers: adminHeaders(),
              body: JSON.stringify(confirmation)
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
            const confirmation = requireConfirmText("DELETE", `删除权限规则 #${ruleId}`);
            if (!confirmation) {
              return;
            }
            controlFetch(`/dashboard-control/access-rules/${ruleId}`, {
              method: "DELETE",
              headers: adminHeaders(),
              body: JSON.stringify(confirmation)
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
          byId("improvements").addEventListener("click", (event) => {
            const rowElement = event.target.closest("tr");
            if (!rowElement || !rowElement.firstElementChild) {
              return;
            }
            byId("improvementId").value = rowElement.firstElementChild.textContent;
          });
          byId("pullRequests").addEventListener("click", (event) => {
            const rowElement = event.target.closest("tr");
            if (!rowElement || !rowElement.firstElementChild) {
              return;
            }
            byId("pullRequestId").value = rowElement.firstElementChild.textContent;
          });
          byId("executionRuns").addEventListener("click", (event) => {
            if (!event.target.classList.contains("select-execution")) {
              return;
            }
            byId("executionType").value = event.target.dataset.runType;
            byId("executionId").value = event.target.dataset.runId;
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
          }), 5000);
        </script>
      </body>
    </html>
    """
